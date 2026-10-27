"""The parts and colours bricky knows about.

Parts and colours are keyed by their BrickLink ids, the LEGO Group's own marketplace catalog.
Geometry is generated from each part's family, so the data files stay small and reviewable.
"""

import re
import tomllib
from collections.abc import Iterable
from functools import cache
from importlib.resources import files
from typing import Final

from pydantic import BaseModel, ConfigDict

from bricky.catalog.families import build_part
from bricky.catalog.models import (
    Color,
    ColorType,
    Connector,
    ConnectorKind,
    Family,
    Part,
    PartSpec,
)

__all__ = [
    "Catalog",
    "Color",
    "ColorType",
    "Connector",
    "ConnectorKind",
    "Family",
    "Part",
    "PartSpec",
    "default_catalog",
]


class _CatalogData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parts: tuple[PartSpec, ...] = ()
    colors: tuple[Color, ...] = ()


class Catalog:
    """An immutable index of parts and colours."""

    def __init__(self, parts: Iterable[Part], colors: Iterable[Color]) -> None:
        self._parts = {part.id: part for part in parts}
        self._colors = {color.id: color for color in colors}
        self._color_names = {color.name.casefold(): color for color in self._colors.values()}

    @classmethod
    def from_specs(cls, parts: Iterable[PartSpec], colors: Iterable[Color]) -> Catalog:
        """Build a catalog from data-file entries, generating each part's geometry."""
        return cls((build_part(spec) for spec in parts), colors)

    @property
    def parts(self) -> tuple[Part, ...]:
        """All parts, in data-file order."""
        return tuple(self._parts.values())

    @property
    def colors(self) -> tuple[Color, ...]:
        """All colours, in data-file order."""
        return tuple(self._colors.values())

    def part(self, part_id: str) -> Part | None:
        """Return the part with this BrickLink item number, if known."""
        return self._parts.get(part_id)

    def color(self, color_id: int) -> Color | None:
        """Return the colour with this BrickLink colour id, if known."""
        return self._colors.get(color_id)

    def resolve_color(self, value: int | str) -> Color:
        """Find a colour by BrickLink id or by name, ignoring case.

        Raises:
            ValueError: If no colour matches.
        """
        if isinstance(value, int) or value.isdigit():
            color = self._colors.get(int(value))
        else:
            color = self._color_names.get(value.casefold())
        if color is None:
            known = ", ".join(c.name for c in self._colors.values())
            msg = f"unknown colour {value!r}; known colours: {known}"
            raise ValueError(msg)
        return color

    def find(
        self, *, family: Family | str | None = None, size: tuple[int, int] | None = None
    ) -> list[Part]:
        """Return the parts of a family and footprint, in data-file order.

        Args:
            family: Part family, such as ``"plate"``; any family when omitted.
            size: Footprint in studs, in either order: ``(1, 6)`` and ``(6, 1)`` both find a
                1 x 6 part. Any footprint when omitted.

        Example:
            >>> [p.id for p in default_catalog().find(family="plate", size=(6, 1))]
            ['3666']
        """
        wanted = None if family is None else Family(family)
        footprint = None if size is None else tuple(sorted(size))
        return [
            part
            for part in self._parts.values()
            if (wanted is None or part.family is wanted)
            and (footprint is None or tuple(sorted(part.footprint)) == footprint)
        ]

    def search_colors(self, query: str = "") -> list[Color]:
        """Return colours whose id, name or type contain every word of the query."""
        words = query.casefold().split()
        return [
            color
            for color in self._colors.values()
            if all(w in f"{color.id} {color.name.casefold()} {color.type}" for w in words)
        ]

    def search(self, query: str, limit: int | None = None) -> list[Part]:
        """Return parts whose id, name, family or size match every word of the query.

        Sizes match in either spelling, so ``"2x4"`` and ``"2 x 4"`` both find ``Brick 2 x 4``.
        """
        words = _SIZE.sub(r"\1x\2", query.casefold()).split()
        hits = [
            part for part in self._parts.values() if all(w in _search_text(part) for w in words)
        ]
        return hits if limit is None else hits[:limit]


_SIZE: Final = re.compile(r"(\d+)\s*x\s*(\d+)")


def _search_text(part: Part) -> str:
    name = part.name.casefold()
    return f"{part.id} {name} {part.family} {_SIZE.sub(r'\1x\2', name)}"


@cache
def default_catalog() -> Catalog:
    """Return the catalog shipped with bricky."""
    data = files("bricky.catalog").joinpath("data")
    raw = {
        **tomllib.loads(data.joinpath("parts.toml").read_text(encoding="utf-8")),
        **tomllib.loads(data.joinpath("colors.toml").read_text(encoding="utf-8")),
    }
    parsed = _CatalogData.model_validate(raw)
    return Catalog.from_specs(parsed.parts, parsed.colors)
