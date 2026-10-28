"""The parts and colors bricky knows about.

Parts and colors are keyed by their BrickLink ids: BrickLink is the LEGO Group's own marketplace,
and its catalog lists every part. ``bricky import-catalog`` imports that catalog into a catalog
file (see :mod:`bricky.catalog.bricklink`); until then, bricky uses a small sample shipped with it.

Each catalog part carries BrickLink's facts and, when bricky has one, a shape: the family that
generates its geometry and the numbers the family needs. Geometry is generated on first use, so a
catalog of every part loads quickly.
"""

import json
import re
import tomllib
from collections import Counter
from collections.abc import Iterable, Mapping
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import Any, Final, Literal, Self

from platformdirs import user_data_path
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from bricky.catalog.families import build_part
from bricky.catalog.models import (
    CatalogPart,
    Color,
    ColorType,
    Connector,
    ConnectorKind,
    Family,
    Part,
    Shape,
)
from bricky.errors import BrickyError
from bricky.settings import Settings

__all__ = [
    "CATALOG_FORMAT",
    "IMPORTED_CATALOG",
    "SAMPLE_CATALOG",
    "Catalog",
    "CatalogFile",
    "CatalogPart",
    "Color",
    "ColorType",
    "Connector",
    "ConnectorKind",
    "Family",
    "Part",
    "Shape",
    "catalog_path",
    "default_catalog",
    "load_catalog",
]

CATALOG_FORMAT: Final = "bricky.catalog/1"
"""Format tag written into every catalog file."""

SAMPLE_CATALOG: Final = Path(str(files("bricky.catalog").joinpath("data", "sample.toml")))
"""The sample catalog shipped with bricky: common parts and colors, entered by hand."""

IMPORTED_CATALOG: Final = user_data_path("bricky", appauthor=False) / "catalog.json"
"""Where ``bricky import-catalog`` writes the catalog by default, and where bricky looks for it."""


class CatalogFile(BaseModel):
    """A catalog file: colors and parts, as ``bricky import-catalog`` writes them."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["bricky.catalog/1"] = CATALOG_FORMAT
    source: str = Field(default="", description="Where the data comes from, and when.")
    colors: tuple[Color, ...] = ()
    parts: tuple[CatalogPart, ...] = ()

    @model_validator(mode="after")
    def _unique(self) -> Self:
        _check_unique(
            [part.id for part in self.parts],
            [color.id for color in self.colors],
            [color.name for color in self.colors],
        )
        return self

    def dump(self) -> bytes:
        """Encode the file as JSON, one color or part per line, leaving out default values."""
        head = {"format": self.format, "source": self.source}
        lines = [json.dumps(head, ensure_ascii=False)[:-1] + ', "colors": [']
        lines += _rows(self.colors)
        lines.append('], "parts": [')
        lines += _rows(self.parts)
        lines.append("]}")
        return ("\n".join(lines) + "\n").encode()


_ENTRY: Final = TypeAdapter(CatalogPart)
_COLORS: Final = TypeAdapter(tuple[Color, ...])


class Catalog:
    """An immutable index of parts and colors.

    Entries can be given as :class:`CatalogPart` or as raw data, which is validated the first time
    the entry is needed, so a catalog of every BrickLink part loads in a fraction of a second.
    """

    def __init__(
        self,
        parts: Iterable[CatalogPart | Mapping[str, Any]] = (),
        colors: Iterable[Color] = (),
        *,
        source: str = "",
    ) -> None:
        self.source = source
        self._entries: dict[str, CatalogPart | Mapping[str, Any]] = {}
        for entry in parts:
            self._entries[entry.id if isinstance(entry, CatalogPart) else str(entry["id"])] = entry
        self._aliases: dict[str, str] = {}
        for key, entry in self._entries.items():
            for alternate in _raw_list(entry, "alternates"):
                if alternate not in self._entries:
                    self._aliases.setdefault(alternate, key)
        self._colors = {color.id: color for color in colors}
        self._color_names = {color.name.casefold(): color for color in self._colors.values()}
        self._parts: dict[str, Part | None] = {}

    @classmethod
    def from_data(cls, data: Mapping[str, Any], *, origin: str = "catalog data") -> Catalog:
        """Build a catalog from data as a catalog file holds it.

        Colors are validated at once and parts when first used.

        Raises:
            BrickyError: If the data is not a catalog, or an id or name repeats.
        """
        if data.get("format") != CATALOG_FORMAT:
            msg = f"{origin} is not a bricky catalog: expected format {CATALOG_FORMAT!r}"
            raise BrickyError(msg)
        parts = data.get("parts", [])
        try:
            colors = _COLORS.validate_python(data.get("colors", []))
            if not isinstance(parts, list) or not all(
                isinstance(p, dict) and isinstance(p.get("id"), str) for p in parts
            ):
                msg = "every part needs a string id"
                raise ValueError(msg)  # noqa: TRY301 - reported with the validation errors below
            _check_unique(
                [p["id"] for p in parts], [c.id for c in colors], [c.name for c in colors]
            )
        except (ValidationError, ValueError) as error:
            msg = f"{origin} is not a valid catalog: {error}"
            raise BrickyError(msg) from None
        return cls(parts, colors, source=str(data.get("source", "")))

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> tuple[CatalogPart, ...]:
        """Every catalog part, with or without a shape, in catalog order."""
        return tuple(self._entry(key) for key in self._entries)

    @property
    def parts(self) -> tuple[Part, ...]:
        """Every part with a shape, in catalog order. This generates every part's geometry."""
        return tuple(part for key in self._entries if (part := self.part(key)) is not None)

    @property
    def colors(self) -> tuple[Color, ...]:
        """All colors, in catalog order."""
        return tuple(self._colors.values())

    def entry(self, part_id: str) -> CatalogPart | None:
        """Return what the catalog lists for a BrickLink item number, with or without a shape.

        A part's other numbers find it too: ``3068b`` finds the part BrickLink lists as ``3068``.
        """
        key = part_id if part_id in self._entries else self._aliases.get(part_id)
        return None if key is None else self._entry(key)

    def shape(self, part_id: str) -> Shape | None:
        """Return a part's shape: its own, or for a printed part, its base's; ``None`` if none."""
        entry = self.entry(part_id)
        if entry is None:
            return None
        if entry.shape is None and entry.base is not None:
            base = self.entry(entry.base)
            return None if base is None else base.shape
        return entry.shape

    def part(self, part_id: str) -> Part | None:
        """Return the part with this BrickLink item number, if the catalog has a shape for it."""
        if part_id not in self._parts:
            entry, shape = self.entry(part_id), self.shape(part_id)
            self._parts[part_id] = (
                None if entry is None or shape is None else build_part(entry, shape)
            )
        return self._parts[part_id]

    def color(self, color_id: int) -> Color | None:
        """Return the color with this BrickLink color id, if known."""
        return self._colors.get(color_id)

    def resolve_color(self, value: int | str) -> Color:
        """Find a color by BrickLink id or by name, ignoring case.

        Raises:
            ValueError: If no color matches.
        """
        if isinstance(value, int) or value.isdigit():
            color = self._colors.get(int(value))
        else:
            color = self._color_names.get(value.casefold())
        if color is None:
            msg = f"unknown color {value!r}; search the catalog with `bricky colors <words>`"
            raise ValueError(msg)
        return color

    def find(
        self, *, family: Family | str | None = None, size: tuple[int, int] | None = None
    ) -> list[Part]:
        """Return the parts of a family and footprint, in catalog order.

        Args:
            family: Part family, such as ``"plate"``; any family when omitted.
            size: Footprint in studs, in either order: ``(1, 6)`` and ``(6, 1)`` both find a
                1 x 6 part. Any footprint when omitted.

        Example:
            >>> [p.id for p in default_catalog().find(family="plate", size=(6, 1))]
            ['3666']
        """
        wanted = None if family is None else Family(family).value
        footprint = None if size is None else sorted(size)
        found = []
        for key in self._entries:
            shape = self._raw_shape(key)
            if shape is None or (wanted is not None and shape.get("family") != wanted):
                continue
            if footprint is not None and sorted(shape.get("size", ())) != footprint:
                continue
            if (part := self.part(key)) is not None:
                found.append(part)
        return found

    def search_colors(self, query: str = "") -> list[Color]:
        """Return colors whose id, name or type contain every word of the query."""
        words = query.casefold().split()
        return [
            color
            for color in self._colors.values()
            if all(w in f"{color.id} {color.name.casefold()} {color.type}" for w in words)
        ]

    def search(self, query: str, *, shapeless: bool = False) -> list[CatalogPart]:
        """Return the catalog parts whose id, name, category or family match every word of a query.

        A word matches when the part's text contains it, except a size, which must match a whole
        size of the part's name, in either order and either spelling: ``"1x2"``, ``"2x1"`` and
        ``"1 x 2"`` all find ``Plate 1 x 2`` and not ``Plate 1 x 12``. Parts with a shape come
        first, plainer names before longer ones; parts without a shape are left out unless
        ``shapeless`` is set.
        """
        words = _SIZE.sub(r"\1x\2", query.casefold()).split()
        hits: list[tuple[bool, int, int, str]] = []
        for order, (key, entry) in enumerate(self._entries.items()):
            shape = self._raw_shape(key)
            if shape is None and not shapeless:
                continue
            name = _raw(entry, "name")
            text = _search_text(key, name, _raw(entry, "category"), shape)
            text += " " + " ".join(_raw_list(entry, "alternates")).casefold()
            if all(_matches(word, text) for word in words):
                hits.append((shape is None, len(name), order, key))
        hits.sort()
        return [self._entry(key) for *_, key in hits]

    def _raw_shape(self, key: str) -> Mapping[str, Any] | None:
        """A part's shape, or its base's, as raw data, without validating the whole entry."""
        entry = self._entries[key]
        shape = _raw_field(entry, "shape")
        if shape is None and (base := _raw(entry, "base")) and base in self._entries:
            shape = _raw_field(self._entries[base], "shape")
        return shape

    def _entry(self, key: str) -> CatalogPart:
        entry = self._entries[key]
        if isinstance(entry, CatalogPart):
            return entry
        try:
            validated = _ENTRY.validate_python(entry)
        except ValidationError as error:
            msg = f"catalog part {key!r} is not valid: {error}"
            raise BrickyError(msg) from None
        self._entries[key] = validated
        return validated


def load_catalog(path: Path) -> Catalog:
    """Read a catalog file, JSON as ``bricky import-catalog`` writes it or TOML as the sample is.

    Raises:
        BrickyError: If the file cannot be read or is not a valid catalog.
    """
    try:
        text = path.read_text(encoding="utf-8")
        data = tomllib.loads(text) if path.suffix == ".toml" else json.loads(text)
    except OSError as error:
        msg = f"cannot read catalog {path}: {error.strerror or error}"
        raise BrickyError(msg) from None
    except (tomllib.TOMLDecodeError, json.JSONDecodeError) as error:
        msg = f"{path} is not a valid catalog: {error}"
        raise BrickyError(msg) from None
    if not isinstance(data, dict):
        msg = f"{path} is not a bricky catalog"
        raise BrickyError(msg)
    return Catalog.from_data(data, origin=str(path))


def catalog_path(settings: Settings | None = None) -> Path:
    """The catalog file bricky uses.

    That is the configured catalog when there is one, else the catalog imported into bricky's data
    folder, else the sample shipped with bricky.
    """
    configured = (settings or Settings()).catalog
    if configured is not None:
        return configured
    return IMPORTED_CATALOG if IMPORTED_CATALOG.is_file() else SAMPLE_CATALOG


@cache
def default_catalog() -> Catalog:
    """Return the catalog bricky uses (see :func:`catalog_path`), loaded once per process."""
    return load_catalog(catalog_path())


_SIZE: Final = re.compile(r"(\d+)\s*x\s*(\d+)")
_SIZE_WORD: Final = re.compile(r"(\d+)x(\d+)")


def _raw(entry: CatalogPart | Mapping[str, Any], field: str) -> str:
    value = getattr(entry, field) if isinstance(entry, CatalogPart) else entry.get(field)
    return value if isinstance(value, str) else ""


def _raw_list(entry: CatalogPart | Mapping[str, Any], field: str) -> list[str]:
    value = getattr(entry, field) if isinstance(entry, CatalogPart) else entry.get(field, ())
    return [str(item) for item in value] if isinstance(value, (list, tuple)) else []


def _raw_field(entry: CatalogPart | Mapping[str, Any], field: str) -> Mapping[str, Any] | None:
    if isinstance(entry, CatalogPart):
        value = getattr(entry, field)
        return None if value is None else value.model_dump()
    value = entry.get(field)
    return value if isinstance(value, dict) else None


def _matches(word: str, text: str) -> bool:
    size = _SIZE_WORD.fullmatch(word)
    if size is None:
        return word in text
    a, b = size.groups()
    words = set(text.split())
    return f"{a}x{b}" in words or f"{b}x{a}" in words


def _search_text(key: str, name: str, category: str, shape: Mapping[str, Any] | None) -> str:
    plain = f"{name} {category}".casefold().replace(",", " ")
    family = "" if shape is None else str(shape.get("family", ""))
    return f"{key.casefold()} {plain} {family} {_SIZE.sub(r'\1x\2', plain)}"


def _check_unique(part_ids: list[str], color_ids: list[int], color_names: list[str]) -> None:
    for what, keys in (
        ("part id", part_ids),
        ("color id", [str(key) for key in color_ids]),
        ("color name", [name.casefold() for name in color_names]),
    ):
        repeated = sorted(key for key, count in Counter(keys).items() if count > 1)
        if repeated:
            msg = f"repeated {what}: {', '.join(repeated)}"
            raise ValueError(msg)


def _rows(items: Iterable[BaseModel]) -> list[str]:
    rows = [item.model_dump_json(exclude_defaults=True) for item in items]
    return [row + "," for row in rows[:-1]] + rows[-1:]
