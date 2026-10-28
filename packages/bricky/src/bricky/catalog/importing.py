# Copyright 2026 Maxence Faldor
"""Build a catalog: BrickLink for what exists, names and LDraw for shapes.

Each source supplies what it knows best:

- **BrickLink**, the LEGO Group's marketplace, lists every part and color: ids, names,
  categories, and the colors each part comes in (:mod:`bricky.catalog.bricklink`).
- **Names**: a part whose official name follows a pattern, such as "Slope 45 2 x 4",
  gets that family's shape, exact and oriented by bricky's conventions
  (:mod:`bricky.catalog.names`).
- **Printed parts** take the shape of the part they are printed on.
- **LDraw**, the LDraw.org Parts Library, gives every other part its shape, converted
  into boxes and connectors (:mod:`bricky.catalog.ldraw`).

An import without BrickLink's downloads takes the parts from LDraw alone, with LDraw's
names, and the colors from the sample catalog. The import compares the two shapes of a
part that has both a shape from its name and an LDraw file. The two agree for almost
every part, which checks both.

The import reports every disagreement. Where LDraw's shape only lacks anti-studs that
the name gives, the part keeps its name's shape: the conversion finds anti-studs by the
room under a body on a 0.8 mm grid, which misses sockets under thin and curved bodies.
Any other disagreement means the name hides a detail that changes the part, so the part
takes LDraw's shape.
"""

import re
import tomllib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from pydantic import BaseModel, Field

from bricky.catalog import SAMPLE_CATALOG, Catalog, CatalogFile
from bricky.catalog.bricklink import Downloads, bricklink_parts, downloaded
from bricky.catalog.families import build_part
from bricky.catalog.ldraw import Library, ldraw_parts, ldraw_shape
from bricky.catalog.models import (
    CatalogPart,
    Color,
    Connector,
    ConnectorKind,
    Part,
)
from bricky.errors import BrickyError
from bricky.geometry import ALIASES, Box, Pose, Rotation, Vector

_PRINTED: Final = re.compile(r"p[a-z]{0,3}\d")
"""The suffix of a printed part's id after its base part's id.

The suffix is p, then up to three letters, then a digit.
"""


class Coverage(BaseModel):
    """What an import found: parts and colors, each shape's source, and the checks."""

    sources: tuple[str, ...] = Field(
        description="The sources read, with their dates or releases."
    )
    parts: int = Field(description="Parts imported.")
    shaped: int = Field(description="Parts with a shape, which can be placed.")
    by_source: dict[str, int] = Field(
        description="Shaped parts by the source of their shape: 'name', 'printed' "
        "or 'LDraw'."
    )
    by_family: dict[str, int] = Field(description="Shaped parts by family.")
    unshaped_by_category: dict[str, int] = Field(
        description="Parts without a shape by category, most first."
    )
    colors: int = Field(description="Colors imported.")
    skipped_colors: tuple[str, ...] = Field(
        default=(),
        description="Colors left out, each with its reason: "
        "no RGB value, or a repeated name.",
    )
    ldraw_failures: dict[str, int] = Field(
        default_factory=dict,
        description="LDraw files the import failed to convert, "
        "counted by reason, most first.",
    )
    compared: int = Field(
        default=0,
        description="Parts shaped from their name and compared with their LDraw file.",
    )
    disagreements: tuple[str, ...] = Field(
        default=(),
        description="Parts whose name and LDraw file disagree, "
        "which shape each keeps, and how.",
    )


type Progress = Callable[[int, int], None]
"""A callback given the count of the part being shaped and the total number of parts."""


def import_catalog(
    bricklink: Downloads | None, ldraw: Library | None, progress: Progress | None = None
) -> tuple[CatalogFile, Coverage]:
    """Build a catalog file and its coverage.

    The import reads BrickLink's downloads, an LDraw library, or both.

    Raises:
        BrickyError: If neither source is given.
    """
    if bricklink is not None:
        colors, skipped, entries = bricklink_parts(bricklink)
        sources = [f"BrickLink catalog downloads of {downloaded(bricklink)}"]
    elif ldraw is not None:
        colors, skipped, entries = list(_sample_colors()), (), ldraw_parts(ldraw)
        sources = ["colors from bricky's sample"]
    else:
        message = "an import needs BrickLink's downloads, an LDraw library, or both"
        raise BrickyError(message)
    if ldraw is not None:
        sources.append(
            f"LDraw.org Parts Library, CC BY, {ldraw.release}, at {ldraw.root}"
        )
    _name_printed_parts(entries, ldraw)
    shaping = _Shaping()
    for count, key in enumerate(list(entries), start=1):
        if progress is not None:
            progress(count, len(entries))
        shaping.shape(entries, key, ldraw)
    catalog = CatalogFile(
        source="; ".join(sources), colors=tuple(colors), parts=tuple(entries.values())
    )
    return catalog, shaping.coverage(catalog, sources, skipped)


@dataclass(slots=True)
class _Shaping:
    """Gives parts their LDraw shapes and records the source of every shape."""

    origin: dict[str, str] = field(default_factory=dict)
    failures: Counter[str] = field(default_factory=Counter)
    compared: int = 0
    disagreements: list[str] = field(default_factory=list)

    def shape(
        self, entries: dict[str, CatalogPart], key: str, ldraw: Library | None
    ) -> None:
        """Record the source of a part's shape.

        The part's converted LDraw file gives the part its shape, or checks the shape
        its name gives.
        """
        entry = entries[key]
        if entry.base is not None:
            self.origin[key] = "printed"
            return
        if entry.shape is not None:
            self.origin[key] = "name"
        number = None if ldraw is None else _ldraw_number(ldraw, entry)
        if ldraw is None or number is None:
            return
        try:
            converted = ldraw_shape(ldraw, number)
        except BrickyError as error:
            self.failures[_reason(str(error))] += 1
            return
        if entry.shape is None:
            entries[key] = entry.model_copy(update={"shape": converted})
            self.origin[key] = "LDraw"
            return
        self.compared += 1
        named, from_ldraw = build_part(entry, entry.shape), build_part(entry, converted)
        difference = _difference(named, from_ldraw)
        if not difference:
            return
        if _lacks_anti_studs(named, from_ldraw):
            self.disagreements.append(
                f"{key} {entry.name} keeps its name's shape: {difference}"
            )
            return
        self.disagreements.append(
            f"{key} {entry.name} takes LDraw's shape: {difference}"
        )
        rotation = _closest_rotation(named, from_ldraw)
        entries[key] = entry.model_copy(
            update={"shape": converted.model_copy(update={"rotation": rotation})}
        )
        self.origin[key] = "LDraw"

    def coverage(
        self, catalog: CatalogFile, sources: list[str], skipped: tuple[str, ...]
    ) -> Coverage:
        """Count what the catalog holds, by source, family and category."""
        shapes = Catalog(catalog.parts)
        families: Counter[str] = Counter()
        unshaped: Counter[str] = Counter()
        origins: Counter[str] = Counter()
        for entry in catalog.parts:
            shape = shapes.shape(entry.id)
            if shape is None:
                unshaped[entry.category or "no category"] += 1
            else:
                families[shape.family.value] += 1
                origins[self.origin[entry.id]] += 1
        return Coverage(
            sources=tuple(sources),
            parts=len(catalog.parts),
            shaped=families.total(),
            by_source=dict(origins.most_common()),
            by_family=dict(families.most_common()),
            unshaped_by_category=dict(unshaped.most_common()),
            colors=len(catalog.colors),
            skipped_colors=skipped,
            ldraw_failures=dict(self.failures.most_common()),
            compared=self.compared,
            disagreements=tuple(self.disagreements),
        )


def _name_printed_parts(entries: dict[str, CatalogPart], ldraw: Library | None) -> None:
    """Set each printed part's base to the part it is printed on, whose shape it takes.

    A printed part's id is its base part's id followed by p, letters and digits, such as
    3068bpb0001 for a print on 3068b, and its name starts with the base part's name.
    Both must hold. The base part must itself be unprinted and have a shape, from its
    name or from LDraw.
    """
    for key, entry in entries.items():
        if entry.shape is not None:
            continue
        for match in _PRINTED.finditer(key):
            base = entries.get(key[: match.start()])
            if (
                base is None
                or base.base is not None
                or not entry.name.startswith(base.name + " ")
            ):
                continue
            if base.shape is not None or (
                ldraw is not None and _ldraw_number(ldraw, base) is not None
            ):
                entries[key] = entry.model_copy(update={"base": base.id})
                break


def _ldraw_number(library: Library, entry: CatalogPart) -> str | None:
    """A part's LDraw number: its own id, else the first alternate id LDraw has."""
    for number in (entry.id, *entry.alternates):
        if number in library:
            return number
    return None


def _difference(named: Part, from_ldraw: Part) -> str:
    """How a part built from its name and from LDraw differ; empty when they agree.

    LDraw orients parts its own way, so the two agree when a rotation about the vertical
    axis brings LDraw's onto the name's: the same size, and studs and anti-studs in the
    same places.
    """
    if any(
        _placed(from_ldraw, rotation) == _placed(named, "R0") for rotation in ALIASES
    ):
        return ""
    facts = [_facts(named), _facts(from_ldraw)]
    where = " in other places" if facts[0] == facts[1] else ""
    return (
        f"its name gives {_describe(facts[0])}; "
        f"LDraw gives {_describe(facts[1])}{where}"
    )


def _lacks_anti_studs(named: Part, from_ldraw: Part) -> bool:
    """Whether a rotation of LDraw's part is the name's with only anti-studs missing."""
    size, connectors = _placed(named, "R0")
    return any(
        rotated_size == size
        and rotated < connectors
        and all(
            missing.kind is ConnectorKind.ANTI_STUD for missing in connectors - rotated
        )
        for rotated_size, rotated in (
            _placed(from_ldraw, rotation) for rotation in ALIASES
        )
    )


def _closest_rotation(named: Part, from_ldraw: Part) -> str:
    """The rotation of LDraw's part closest to the name's: its size, then connectors."""
    target_size, target_connectors = _placed(named, "R0")

    def closeness(rotation: str) -> tuple[bool, int]:
        size, connectors = _placed(from_ldraw, rotation)
        return size == target_size, len(connectors & target_connectors)

    return max(ALIASES, key=closeness)


def _placed(part: Part, rotation: str) -> tuple[Vector, frozenset[Connector]]:
    """A rotated part's size and connectors, with its minimum corner at the origin."""
    rotated = Box(Vector(0, 0, 0), part.size).transformed(
        Pose(Rotation.parse(rotation))
    )
    pose = Pose(Rotation.parse(rotation), -rotated.min)
    connectors = frozenset(connector.transformed(pose) for connector in part.connectors)
    return rotated.max - rotated.min, connectors


def _facts(part: Part) -> tuple[tuple[int, int], int, int, int]:
    studs = sum(connector.kind is ConnectorKind.STUD for connector in part.connectors)
    across = tuple(sorted((part.size.x, part.size.y)))
    return (across[0], across[1]), part.size.z, studs, len(part.connectors) - studs


def _describe(facts: tuple[tuple[int, int], int, int, int]) -> str:
    (x, y), z, studs, anti_studs = facts
    return (
        f"{x} x {y} x {z} units, {studs} stud{'' if studs == 1 else 's'}, "
        f"{anti_studs} anti-stud{'' if anti_studs == 1 else 's'}"
    )


def _reason(error: str) -> str:
    """Remove the part number from an error, so failures group by reason."""
    return re.sub(
        r"LDraw part \S+ ", "", re.sub(r"which \S+ uses", "which a part uses", error)
    )


def _sample_colors() -> tuple[Color, ...]:
    data = tomllib.loads(SAMPLE_CATALOG.read_text(encoding="utf-8"))
    return tuple(Color.model_validate(color) for color in data["colors"])
