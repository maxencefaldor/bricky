"""Build a catalog from its sources: BrickLink for what exists, names and LDraw for shapes.

Each source supplies what it knows best:

- **BrickLink**, the LEGO Group's marketplace, lists every part and color: ids, names,
  categories, and the colors each part comes in (:mod:`bricky.catalog.bricklink`).
- **Names**: a part whose official name follows a pattern, such as "Slope 45 2 x 4", gets that
  family's shape, exact and oriented by bricky's conventions (:mod:`bricky.catalog.names`).
- **Printed parts** take the shape of the part they are printed on.
- **LDraw**, the LDraw.org Parts Library, gives every other part its shape, converted into boxes
  and connectors (:mod:`bricky.catalog.ldraw`).

An import without BrickLink's downloads takes the parts from LDraw alone, with LDraw's names, and
the colors from the sample catalog. The import compares the two shapes of a part that has both a
shape from its name and an LDraw file. The two agree for almost every part, which checks both. A
disagreement means the name hides a detail that changes the part: the part then takes LDraw's
shape, and the import reports the disagreement.
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
    BoxesShape,
    CatalogPart,
    Color,
    Connector,
    ConnectorKind,
    Part,
    Shape,
)
from bricky.errors import BrickyError
from bricky.geometry import ALIASES, Box, Pose, Rotation, Vector

_PRINTED: Final = re.compile(r"p[a-z]{0,3}\d")
"""The suffix of a printed part's id after its base part's id: p, up to three letters, a digit."""


class Coverage(BaseModel):
    """What an import found: parts and colors, the source of each part's shape, and the checks."""

    sources: tuple[str, ...] = Field(description="The sources read, with their dates or releases.")
    parts: int = Field(description="Parts imported.")
    shaped: int = Field(description="Parts with a shape, which can be placed.")
    by_source: dict[str, int] = Field(
        description="Shaped parts by the source of their shape: 'name', 'printed' or 'LDraw'."
    )
    by_family: dict[str, int] = Field(description="Shaped parts by family.")
    unshaped_by_category: dict[str, int] = Field(
        description="Parts without a shape by category, most first."
    )
    colors: int = Field(description="Colors imported.")
    skipped_colors: tuple[str, ...] = Field(
        default=(),
        description="Colors left out, each with its reason: no RGB value, or a repeated name.",
    )
    ldraw_failures: dict[str, int] = Field(
        default_factory=dict,
        description="LDraw files the import failed to convert, counted by reason, most first.",
    )
    compared: int = Field(
        default=0, description="Parts shaped from their name and compared with their LDraw file."
    )
    disagreements: tuple[str, ...] = Field(
        default=(),
        description="Parts whose name and LDraw file disagree, and how; they take LDraw's shape.",
    )


type Progress = Callable[[int, int], None]
"""A callback that receives the count of the part being shaped and the total number of parts."""


def import_catalog(
    bricklink: Downloads | None, ldraw: Library | None, progress: Progress | None = None
) -> tuple[CatalogFile, Coverage]:
    """Build a catalog file and its coverage from BrickLink's downloads, an LDraw library, or both.

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
        sources.append(f"LDraw.org Parts Library, CC BY, {ldraw.release}, at {ldraw.root}")
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

    def shape(self, entries: dict[str, CatalogPart], key: str, ldraw: Library | None) -> None:
        """Record the source of a part's shape, converting its LDraw file to shape or check it."""
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
        difference = _difference(entry, entry.shape, converted)
        if difference:
            self.disagreements.append(f"{key} {entry.name}: {difference}")
            rotation = _closest_rotation(entry, entry.shape, converted)
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
    """Set each printed part's base to the part it is printed on, so it takes that part's shape.

    A printed part's id is its base part's id followed by p, letters and digits, such as
    3068bpb0001 for a print on 3068b, and its name starts with the base part's name. Both must
    hold. The base part must itself be unprinted and have a shape, from its name or from LDraw.
    """
    for key, entry in entries.items():
        if entry.shape is not None:
            continue
        for match in _PRINTED.finditer(key):
            base = entries.get(key[: match.start()])
            if base is None or base.base is not None or not entry.name.startswith(base.name + " "):
                continue
            if base.shape is not None or (ldraw is not None and _ldraw_number(ldraw, base)):
                entries[key] = entry.model_copy(update={"base": base.id})
                break


def _ldraw_number(library: Library, entry: CatalogPart) -> str | None:
    """Return a catalog part's LDraw number: its own id, else the first alternate id LDraw has."""
    for number in (entry.id, *entry.alternates):
        if number in library:
            return number
    return None


def _difference(entry: CatalogPart, named: Shape, converted: Shape) -> str:
    """Describe how a part's shapes from its name and from LDraw differ; empty when they agree.

    LDraw orients parts its own way, so the shapes agree when a rotation about the vertical axis
    brings LDraw's onto the name's: the same size, and studs and anti-studs in the same places.
    """
    a, b = build_part(entry, named), build_part(entry, converted)
    if any(_placed(b, rotation) == _placed(a, "R0") for rotation in ALIASES):
        return ""
    facts = [_facts(a), _facts(b)]
    where = " in other places" if facts[0] == facts[1] else ""
    return f"its name gives {_describe(facts[0])}; LDraw gives {_describe(facts[1])}{where}"


def _closest_rotation(entry: CatalogPart, named: Shape, converted: BoxesShape) -> str:
    """The rotation of LDraw's shape that best matches the name's: its size, then connectors."""
    a, b = build_part(entry, named), build_part(entry, converted)
    target_size, target_connectors = _placed(a, "R0")

    def closeness(rotation: str) -> tuple[bool, int]:
        size, connectors = _placed(b, rotation)
        return size == target_size, len(connectors & target_connectors)

    return max(ALIASES, key=closeness)


def _placed(part: Part, rotation: str) -> tuple[Vector, frozenset[Connector]]:
    """A part's size and connectors after a rotation, with its minimum corner at the origin."""
    rotated = Box(Vector(0, 0, 0), part.size).transformed(Pose(Rotation.parse(rotation)))
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
    return re.sub(r"LDraw part \S+ ", "", re.sub(r"which \S+ uses", "which a part uses", error))


def _sample_colors() -> tuple[Color, ...]:
    data = tomllib.loads(SAMPLE_CATALOG.read_text(encoding="utf-8"))
    return tuple(Color.model_validate(color) for color in data["colors"])
