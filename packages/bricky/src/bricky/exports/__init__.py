# Copyright 2026 Maxence Faldor
"""Exports: files that other tools read, listing what a model needs.

A model's lots are what it needs: each part in each color, with a quantity. Each format
is a module that writes lots as one file, registered in :data:`FORMATS`, so adding or
removing a format touches one module and one line here.

An export states only what bricky knows exactly. bricky's parts and colors are
BrickLink's, so a format joins only when it reads BrickLink ids. A format that needs ids
from elsewhere, such as LEGO element numbers or LDraw colors, would need a mapping that
no source gives exactly, and stays out.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from bricky.catalog import Catalog
from bricky.errors import BrickyError
from bricky.exports import wanted_list
from bricky.exports.lots import Lot
from bricky.model import Element, Instance, Model

__all__ = ["FORMATS", "Exporter", "Format", "Lot", "model_lots"]


class Format(StrEnum):
    """A file format that another tool reads."""

    WANTED_LIST = "wanted-list"
    """A BrickLink Wanted List, in BrickLink's XML: buy the parts on BrickLink."""


@dataclass(frozen=True, slots=True)
class Exporter:
    """How to write one format."""

    title: str
    """The format's name, such as ``BrickLink Wanted List``."""

    suffix: str
    """What an exported file's name ends with, such as ``.wanted.xml``."""

    media_type: str
    """The file's media type, such as ``application/xml``."""

    usage: str
    """One sentence on how to use the file in its tool."""

    write: Callable[[Sequence[Lot]], bytes]
    """Writes lots as the file's bytes."""


FORMATS: Final[Mapping[Format, Exporter]] = {
    Format.WANTED_LIST: Exporter(
        title="BrickLink Wanted List",
        suffix=".wanted.xml",
        media_type="application/xml",
        usage=(
            "On BrickLink, open Want, then Upload, choose Upload BrickLink XML format, "
            "and paste the file's contents."
        ),
        write=wanted_list.write,
    ),
}
"""Every format bricky exports, by name."""


def model_lots(model: Model, catalog: Catalog) -> tuple[Lot, ...]:
    """Return a model's lots, sorted by part then color.

    Each lot names a part by its BrickLink id, as the catalog lists it, so an alternate
    id in the model counts with the part it stands for. Every instance counts its
    component's elements again.

    Raises:
        BrickyError: If the catalog lacks a part or a color the model uses.
    """
    counts: Counter[tuple[str, int]] = Counter()

    def visit(elements: Sequence[Element], instances: Sequence[Instance]) -> None:
        for element in elements:
            counts[element.part, element.color] += 1
        for instance in instances:
            component = model.components[instance.component]
            visit(component.elements, component.instances)

    visit(model.elements, model.instances)
    lots: Counter[tuple[str, int]] = Counter()
    unknown_parts: set[str] = set()
    unknown_colors: set[int] = set()
    for (part, color), quantity in counts.items():
        entry = catalog.entry(part)
        if entry is None:
            unknown_parts.add(part)
        if catalog.color(color) is None:
            unknown_colors.add(color)
        if entry is not None:
            lots[entry.id, color] += quantity
    if unknown_parts or unknown_colors:
        missing = [
            *(f"part {part}" for part in sorted(unknown_parts)),
            *(f"color {color}" for color in sorted(unknown_colors)),
        ]
        message = (
            f"the catalog lacks {', '.join(missing)}: "
            "an export lists only parts and colors the catalog has"
        )
        raise BrickyError(message)
    return tuple(
        Lot(part=part, color=color, quantity=quantity)
        for (part, color), quantity in sorted(lots.items(), key=_lot_order)
    )


def _lot_order(item: tuple[tuple[str, int], int]) -> tuple[str, int]:
    (part, color), _ = item
    return part, color
