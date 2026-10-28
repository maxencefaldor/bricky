# Copyright 2026 Maxence Faldor
"""The parts and colors bricky knows.

The catalog keys parts and colors by their BrickLink ids. BrickLink, the LEGO Group's
marketplace, lists every part. ``bricky catalog import`` imports BrickLink's catalog
into a catalog file (see :mod:`bricky.catalog.importing`), and bricky uses the small
sample shipped with it until then.

Each catalog part carries BrickLink's facts and, when bricky has one, a shape: the
family that generates the part's geometry and the numbers the family needs. The catalog
generates a part's geometry on first use, so a catalog of every part loads quickly.
"""

import json
import re
import tomllib
from collections import Counter
from collections.abc import Iterable, Mapping
from difflib import get_close_matches
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import Any, Final, Literal, Self

from platformdirs import user_data_path
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    model_validator,
)

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
"""The format tag of every catalog file."""

SAMPLE_CATALOG: Final = Path(
    str(files("bricky.catalog").joinpath("data", "sample.toml"))
)
"""The sample catalog shipped with bricky.

The sample holds common parts and colors, with shapes written by hand.
"""

IMPORTED_CATALOG: Final = user_data_path("bricky", appauthor=False) / "catalog.json"
"""The file ``bricky catalog import`` writes by default.

bricky also looks for a catalog in this file.
"""


class CatalogFile(BaseModel):
    """A catalog file: colors and parts, as ``bricky catalog import`` writes them."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["bricky.catalog/1"] = CATALOG_FORMAT
    source: str = Field(
        default="", description="The sources of the data, and their dates."
    )
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
        """Encode the file as JSON, one color or part per line, without defaults."""
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

    A part entry is a :class:`CatalogPart` or raw data. The catalog validates raw data
    the first time the entry is needed, so a catalog of every BrickLink part loads in a
    fraction of a second.
    """

    def __init__(
        self,
        parts: Iterable[CatalogPart | Mapping[str, Any]] = (),
        colors: Iterable[Color] = (),
        *,
        source: str = "",
    ) -> None:
        """Index parts and colors by id; a part stays raw data until first used."""
        self.source = source
        self._entries: dict[str, CatalogPart | Mapping[str, Any]] = {}
        for entry in parts:
            self._entries[
                entry.id if isinstance(entry, CatalogPart) else str(entry["id"])
            ] = entry
        self._aliases: dict[str, str] = {}
        for key, entry in self._entries.items():
            for alternate in _raw_list(entry, "alternates"):
                if alternate not in self._entries:
                    self._aliases.setdefault(alternate, key)
        self._colors = {color.id: color for color in colors}
        self._color_names = {
            color.name.casefold(): color for color in self._colors.values()
        }
        self._parts: dict[str, Part | None] = {}

    @classmethod
    def from_data(
        cls, data: Mapping[str, Any], *, origin: str = "catalog data"
    ) -> Catalog:
        """Build a catalog from the data of a catalog file.

        The catalog validates colors at once and each part when first used.

        Raises:
            BrickyError: If the data is not a catalog, or an id or name repeats.
        """
        if data.get("format") != CATALOG_FORMAT:
            message = (
                f"{origin} is not a bricky catalog: expected format {CATALOG_FORMAT!r}"
            )
            raise BrickyError(message)
        parts = data.get("parts", [])
        try:
            colors = _COLORS.validate_python(data.get("colors", []))
            if not isinstance(parts, list) or not all(
                isinstance(part, dict) and isinstance(part.get("id"), str)
                for part in parts
            ):
                message = "every part needs a string id"
                raise ValueError(message)  # noqa: TRY301 - reported like the validation errors
            _check_unique(
                [part["id"] for part in parts],
                [color.id for color in colors],
                [color.name for color in colors],
            )
        except (ValidationError, ValueError) as error:
            message = f"{origin} is not a valid catalog: {error}"
            raise BrickyError(message) from None
        return cls(parts, colors, source=str(data.get("source", "")))

    def __len__(self) -> int:
        """The number of parts."""
        return len(self._entries)

    @property
    def entries(self) -> tuple[CatalogPart, ...]:
        """Every catalog part, with or without a shape, in catalog order."""
        return tuple(self._entry(key) for key in self._entries)

    @property
    def parts(self) -> tuple[Part, ...]:
        """Every part with a shape, in catalog order.

        Reading the property generates every part's geometry.
        """
        return tuple(
            part for key in self._entries if (part := self.part(key)) is not None
        )

    @property
    def colors(self) -> tuple[Color, ...]:
        """Every color, in catalog order."""
        return tuple(self._colors.values())

    def entry(self, part_id: str) -> CatalogPart | None:
        """Return the catalog part with a BrickLink id, with or without a shape.

        A part's alternate ids find it too: ``3068b`` finds the part BrickLink lists as
        ``3068``.
        """
        key = part_id if part_id in self._entries else self._aliases.get(part_id)
        return None if key is None else self._entry(key)

    def shape(self, part_id: str) -> Shape | None:
        """Return a part's shape, or a printed part's base's shape, or ``None``."""
        entry = self.entry(part_id)
        if entry is None:
            return None
        if entry.shape is None and entry.base is not None:
            base = self.entry(entry.base)
            return None if base is None else base.shape
        return entry.shape

    def part(self, part_id: str) -> Part | None:
        """Return the part with a BrickLink id, or ``None`` when it has no shape."""
        if part_id not in self._parts:
            entry, shape = self.entry(part_id), self.shape(part_id)
            self._parts[part_id] = (
                None if entry is None or shape is None else build_part(entry, shape)
            )
        return self._parts[part_id]

    def color(self, color_id: int) -> Color | None:
        """Return the color with a BrickLink id, or ``None`` if the catalog lacks it."""
        return self._colors.get(color_id)

    def resolve_color(self, value: int | str) -> Color:
        """Return the color with a BrickLink color id or a name, ignoring case.

        Raises:
            ValueError: If no color matches.
        """
        if isinstance(value, int) or value.isdigit():
            color = self._colors.get(int(value))
        else:
            color = self._color_names.get(value.casefold())
        if color is None:
            message = f"unknown color {value!r}"
            names = [color.name for color in self._colors.values()]
            if similar := get_close_matches(str(value), names, n=3, cutoff=0.6):
                message += f"; similar names: {', '.join(similar)}"
            message += "; `bricky colors <words>` searches the catalog"
            raise ValueError(message)
        return color

    def find(
        self, *, family: Family | str | None = None, size: tuple[int, int] | None = None
    ) -> list[Part]:
        """Return the parts of a family and footprint, plain parts before printed ones.

        Args:
            family: A family, such as ``"plate"``; any family when omitted.
            size: A footprint in studs, in either order: ``(1, 6)`` and ``(6, 1)`` both
                find a 1 x 6 part; any footprint when omitted.

        Examples:
            >>> [
            ...     part.id
            ...     for part in default_catalog().find(family="plate", size=(6, 1))
            ... ]
            ['3666']
        """
        wanted = None if family is None else Family(family).value
        footprint = None if size is None else sorted(size)
        plain: list[Part] = []
        printed: list[Part] = []
        for key, entry in self._entries.items():
            shape = self._raw_shape(key)
            if shape is None or (wanted is not None and shape.get("family") != wanted):
                continue
            if footprint is not None and sorted(shape.get("size", ())) != footprint:
                continue
            if (part := self.part(key)) is not None:
                (printed if _raw(entry, "base") else plain).append(part)
        return plain + printed

    def search_colors(self, query: str = "") -> list[Color]:
        """Return colors whose id, name and type together contain every word of a query.

        A query that is an RGB value, such as ``#F2CD37``, returns the colors nearest to
        it instead, nearest first.
        """
        if _RGB.fullmatch(query.strip()):
            target = _channels(query.strip())
            ranked = sorted(
                self._colors.values(),
                key=lambda color: sum(
                    (a - b) ** 2
                    for a, b in zip(_channels(color.rgb), target, strict=True)
                ),
            )
            return ranked[:_NEAREST_COLORS]
        words = query.casefold().split()
        return [
            color
            for color in self._colors.values()
            if all(
                word in f"{color.id} {color.name.casefold()} {color.type}"
                for word in words
            )
        ]

    def search_parts(self, query: str, *, shapeless: bool = False) -> list[CatalogPart]:
        """Return the catalog parts whose text matches every word of a query.

        A part's text is its id, alternate ids, name, category and family. A word
        matches when the text contains it. A size matches a whole size of the text only,
        in either order and either spelling: ``"1x2"``, ``"2x1"`` and ``"1 x 2"`` all
        find ``Plate 1 x 2`` and not ``Plate 1 x 12``. Parts without a shape appear only
        when ``shapeless`` is set.

        Parts with a shape come first. DUPLO, Quatro, Primo and Modulex parts, which
        belong to other building systems, follow the rest unless the query names their
        system. Plain parts come before printed ones, and shorter names before longer
        ones.
        """
        words = _SIZE.sub(r"\1x\2", query.casefold()).split()
        hits: list[tuple[bool, bool, bool, int, int, str]] = []
        for order, (key, entry) in enumerate(self._entries.items()):
            shape = self._raw_shape(key)
            if shape is None and not shapeless:
                continue
            name = _raw(entry, "name")
            text = _search_text(key, name, _raw(entry, "category"), shape)
            text += " " + " ".join(_raw_list(entry, "alternates")).casefold()
            if all(_matches(word, text) for word in words):
                elsewhere = any(
                    system in text and system not in words for system in _SYSTEMS
                )
                printed = bool(_raw(entry, "base"))
                hits.append((shape is None, elsewhere, printed, len(name), order, key))
        hits.sort()
        return [self._entry(key) for *_, key in hits]

    def _raw_shape(self, key: str) -> Mapping[str, Any] | None:
        """A part's shape, or its base's, as raw data.

        The method reads the shape without validating the whole entry.
        """
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
            message = f"catalog part {key!r} is not valid: {error}"
            raise BrickyError(message) from None
        self._entries[key] = validated
        return validated


def load_catalog(path: Path) -> Catalog:
    """Read a catalog file in JSON or TOML.

    ``bricky catalog import`` writes JSON, and the sample catalog is TOML.

    Raises:
        BrickyError: If the file cannot be read or is not a valid catalog.
    """
    try:
        text = path.read_text(encoding="utf-8")
        data = tomllib.loads(text) if path.suffix == ".toml" else json.loads(text)
    except OSError as error:
        message = f"cannot read catalog {path}: {error.strerror or error}"
        raise BrickyError(message) from None
    except (tomllib.TOMLDecodeError, json.JSONDecodeError) as error:
        message = f"{path} is not a valid catalog: {error}"
        raise BrickyError(message) from None
    if not isinstance(data, dict):
        message = f"{path} is not a bricky catalog"
        raise BrickyError(message)
    return Catalog.from_data(data, origin=str(path))


def catalog_path(settings: Settings | None = None) -> Path:
    """Return the catalog file bricky uses.

    The configured catalog comes first, then the catalog imported into bricky's data
    folder, then the sample shipped with bricky.
    """
    configured = (settings or Settings()).catalog
    if configured is not None:
        return configured
    return IMPORTED_CATALOG if IMPORTED_CATALOG.is_file() else SAMPLE_CATALOG


@cache
def default_catalog() -> Catalog:
    """Return the catalog at :func:`catalog_path`, loaded once per process."""
    return load_catalog(catalog_path())


_RGB: Final = re.compile(r"#?[0-9A-Fa-f]{6}")
_NEAREST_COLORS: Final = 5
_SIZE: Final = re.compile(r"(\d+)\s*x\s*(\d+)")
_SYSTEMS: Final = ("duplo", "quatro", "primo", "modulex")
"""Building systems other than that of bricks and plates, as search text spells them."""
_SIZE_WORD: Final = re.compile(r"(\d+)x(\d+)")


def _channels(rgb: str) -> tuple[int, int, int]:
    """The red, green and blue channels of an RGB value such as ``#F2CD37``."""
    digits = rgb.removeprefix("#")
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def _raw(entry: CatalogPart | Mapping[str, Any], field: str) -> str:
    value = (
        getattr(entry, field) if isinstance(entry, CatalogPart) else entry.get(field)
    )
    return value if isinstance(value, str) else ""


def _raw_list(entry: CatalogPart | Mapping[str, Any], field: str) -> list[str]:
    value = (
        getattr(entry, field)
        if isinstance(entry, CatalogPart)
        else entry.get(field, ())
    )
    return [str(item) for item in value] if isinstance(value, (list, tuple)) else []


def _raw_field(
    entry: CatalogPart | Mapping[str, Any], field: str
) -> Mapping[str, Any] | None:
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


def _search_text(
    key: str, name: str, category: str, shape: Mapping[str, Any] | None
) -> str:
    plain = f"{name} {category}".casefold().replace(",", " ")
    family = "" if shape is None else str(shape.get("family", ""))
    return f"{key.casefold()} {plain} {family} {_SIZE.sub(r'\1x\2', plain)}"


def _check_unique(
    part_ids: list[str], color_ids: list[int], color_names: list[str]
) -> None:
    for what, keys in (
        ("part id", part_ids),
        ("color id", [str(key) for key in color_ids]),
        ("color name", [name.casefold() for name in color_names]),
    ):
        repeated = sorted(key for key, count in Counter(keys).items() if count > 1)
        if repeated:
            message = f"repeated {what}: {', '.join(repeated)}"
            raise ValueError(message)


def _rows(items: Iterable[BaseModel]) -> list[str]:
    rows = [item.model_dump_json(exclude_defaults=True) for item in items]
    return [row + "," for row in rows[:-1]] + rows[-1:]
