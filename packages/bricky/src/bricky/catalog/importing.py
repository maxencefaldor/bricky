"""Build a catalog from its sources: BrickLink for what exists, names and LDraw for shapes.

Each source does what it is best at:

- **BrickLink**, the LEGO Group's marketplace, lists every part and color: ids, names,
  categories, and the colors each part comes in (:mod:`bricky.catalog.bricklink`).
- **Names**: a part whose official name follows a pattern, such as "Slope 45 2 x 4", gets that
  family's shape, exact and oriented by bricky's conventions (:mod:`bricky.catalog.names`).
- **Printed parts** take the shape of the part they are printed on.
- **LDraw**, the community library of part shapes, gives every other part its shape, converted
  into boxes and connectors (:mod:`bricky.catalog.ldraw`).

Without BrickLink's downloads, the parts come from LDraw alone, named as LDraw names them, and the
colors from the sample catalog. Where a part has both a shape from its name and an LDraw file, the
two are compared, and every disagreement is reported: a check on both.
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
from bricky.catalog.models import CatalogPart, Color, ConnectorKind, Part, Shape
from bricky.errors import BrickyError

_PRINTED: Final = re.compile(r"p[a-z]{0,3}\d")
"""How printed parts are numbered: the base part's number, then p, maybe letters, and digits."""


class Coverage(BaseModel):
    """What an import found: parts and colors, where each part's shape came from, and checks."""

    sources: tuple[str, ...] = Field(description="The sources read, with their dates.")
    parts: int = Field(description="Parts imported.")
    shaped: int = Field(description="Parts with a shape, which can be placed.")
    by_source: dict[str, int] = Field(
        description="Shaped parts by where the shape came from: 'name', 'printed' or 'LDraw'."
    )
    by_family: dict[str, int] = Field(description="Shaped parts by family.")
    unshaped_by_category: dict[str, int] = Field(
        description="Parts without a shape by category, most first."
    )
    colors: int = Field(description="Colors imported.")
    skipped_colors: tuple[str, ...] = Field(
        default=(), description="Colors left out, with why: no RGB value, or a repeated name."
    )
    ldraw_failures: dict[str, int] = Field(
        default_factory=dict,
        description="LDraw files that could not be converted, by reason, most first.",
    )
    compared: int = Field(
        default=0, description="Parts shaped from their name that LDraw also has, compared."
    )
    disagreements: tuple[str, ...] = Field(
        default=(), description="Parts whose name and LDraw file disagree, and how."
    )


type Progress = Callable[[int, int], None]
"""Told how many parts have been looked at, out of how many."""


def import_catalog(
    bricklink: Downloads | None, ldraw: Library | None, progress: Progress | None = None
) -> tuple[CatalogFile, Coverage]:
    """Build a catalog file from BrickLink's downloads, an LDraw library, or both.

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
        msg = "an import needs BrickLink's downloads, an LDraw library, or both"
        raise BrickyError(msg)
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
    """Gives parts their shapes from LDraw, and keeps count of where every shape came from."""

    origin: dict[str, str] = field(default_factory=dict)
    failures: Counter[str] = field(default_factory=Counter)
    compared: int = 0
    disagreements: list[str] = field(default_factory=list)

    def shape(self, entries: dict[str, CatalogPart], key: str, ldraw: Library | None) -> None:
        """Note where a part's shape comes from, converting it from LDraw if it has none yet."""
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
    """Name the part each printed part is printed on, as its base, so it takes that shape.

    A printed part's number is its base part's number followed by p, letters and digits, such as
    3068bpb0001 for a print on 3068b, and its name starts with the base part's name. Both must
    hold, and the base part must have a shape: from its name, or from LDraw.
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
    """The LDraw file for a catalog part: its own number, else one of its other numbers."""
    for number in (entry.id, *entry.alternates):
        if number in library:
            return number
    return None


def _difference(entry: CatalogPart, named: Shape, converted: Shape) -> str:
    """How a part's shape from its name and from LDraw differ, or nothing when they agree.

    They are compared by what does not depend on orientation: the size of the body, in either
    order across, and the numbers of studs and anti-studs.
    """
    a, b = build_part(entry, named), build_part(entry, converted)
    facts = [_facts(a), _facts(b)]
    if facts[0] == facts[1]:
        return ""
    return f"its name gives {_describe(facts[0])}; LDraw gives {_describe(facts[1])}"


def _facts(part: Part) -> tuple[tuple[int, int], int, int, int]:
    studs = sum(c.kind is ConnectorKind.STUD for c in part.connectors)
    across = tuple(sorted((part.size.x, part.size.y)))
    return (across[0], across[1]), part.size.z, studs, len(part.connectors) - studs


def _describe(facts: tuple[tuple[int, int], int, int, int]) -> str:
    (x, y), z, studs, anti_studs = facts
    return f"{x} x {y} x {z} units, {studs} studs, {anti_studs} anti-studs"


def _reason(error: str) -> str:
    """An error without the part number, so failures group by reason."""
    return re.sub(r"LDraw part \S+ ", "", re.sub(r"which \S+ uses", "which a part uses", error))


def _sample_colors() -> tuple[Color, ...]:
    data = tomllib.loads(SAMPLE_CATALOG.read_text(encoding="utf-8"))
    return tuple(Color.model_validate(color) for color in data["colors"])
