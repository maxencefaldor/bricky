# Copyright 2026 Maxence Faldor
"""The catalog: search its parts and colors, import it, and inspect it."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from typing import Final

from platformdirs import user_cache_path
from pydantic import BaseModel, Field
from pydantic_settings import CliPositionalArg

from bricky.catalog import (
    IMPORTED_CATALOG,
    SAMPLE_CATALOG,
    Catalog,
    CatalogPart,
    Color,
    ColorType,
    ConnectorKind,
    Family,
    Part,
    catalog_path,
)
from bricky.catalog.bricklink import DOWNLOAD_PAGE, read_downloads
from bricky.catalog.importing import Coverage, Progress, import_catalog
from bricky.catalog.ldraw import Library
from bricky.errors import BrickyError
from bricky.files import write_file
from bricky.geometry import AXES, DOWN, ORIGIN, UP, Box, Solid
from bricky.model import Element, Model
from bricky.render import View
from bricky.service.session import Image, Session, describe_images, plural, render_views
from bricky.units import PLATE, STUD, to_plates, to_studs

_LISTED_CATEGORIES: Final = 25
_LISTED_DISAGREEMENTS: Final = 40
_FALLBACK_COLOR: Final = 86
"""Light Bluish Gray: `catalog show` renders a part in it when no color is listed."""
PART_IMAGES: Final = user_cache_path("bricky", appauthor=False) / "parts"
"""Where `catalog show --render` renders parts by default: out of every workspace."""


class PartsRequest(BaseModel):
    """Search the parts catalog."""

    query: CliPositionalArg[str] = Field(
        default="",
        description="Words to match against ids, names, categories and sizes, such as "
        "'plate 2x4' (quoted).",
    )
    limit: int = Field(
        default=20, ge=1, le=500, description="Maximum number of parts to return."
    )
    shapeless: bool = Field(
        default=False,
        description="Also list the parts without a shape, which cannot be placed.",
    )


class PartInfo(BaseModel):
    """A catalog part, summarized for choosing parts."""

    id: str = Field(description="BrickLink item number.")
    name: str = Field(description="BrickLink item name.")
    category: str | None = Field(default=None, description="BrickLink category.")
    family: Family | None = Field(
        default=None,
        description=(
            "The family that turns the part's shape into geometry; "
            "null without a shape."
        ),
    )
    footprint: tuple[int, int] | None = Field(
        default=None,
        description="Studs along x, then along y, when the part is unrotated.",
    )
    height: float | None = Field(default=None, description="Body height in plates.")
    studs: int | None = Field(
        default=None, description="Number of studs, on top and on sides."
    )
    note: str = Field(
        default="",
        description="How the part sits when placed unrotated, where that matters.",
    )
    base: str | None = Field(
        default=None, description="For a printed part, the part it is printed on."
    )


class PartsResult(BaseModel):
    """Parts matching a search."""

    parts: tuple[PartInfo, ...]
    total: int = Field(description="Matching parts before the limit applied.")
    sample: bool = Field(
        default=False,
        description="Whether the search ran on the sample catalog of common parts.",
    )

    def describe(self) -> str:
        """Return the result as a table, with each part's note under it."""
        table: list[tuple[list[str], str]] = []
        for part in self.parts:
            if part.family is None:
                table.append(([part.id, part.name, "no shape: cannot be placed"], ""))
                continue
            x, y = part.footprint or (0, 0)
            cells = [
                part.id,
                part.name,
                part.family,
                f"{x} x {y}",
                plural(part.height or 0, "plate"),
                plural(part.studs or 0, "stud"),
            ]
            table.append((cells, part.note))
        header = ["id", "name", "family", "x by y", "height", "studs"]
        widths = [
            max([len(title), *(len(cells[i]) for cells, _ in table if len(cells) > i)])
            for i, title in enumerate(header)
        ]
        rows = [_row(header, widths)] if table else []
        for cells, note in table:
            rows.append(_row(cells, widths))
            if note:
                rows.append(" " * (widths[0] + 2) + note)
        shown = f"{len(self.parts)} of {self.total:,} matching parts"
        rows.append(
            shown + ("; --limit shows more" if len(self.parts) < self.total else "")
        )
        if self.sample and not self.total:
            rows.append(
                "the sample catalog in use holds only common parts; "
                "`bricky catalog import` imports every BrickLink part"
            )
        return "\n".join(rows)


async def parts(request: PartsRequest, session: Session) -> PartsResult:
    """Search the parts catalog."""
    catalog = session.catalog
    hits = await asyncio.to_thread(
        catalog.search_parts, request.query, shapeless=request.shapeless
    )
    shown = hits[: request.limit]
    infos = await asyncio.to_thread(
        lambda: tuple(_part_info(catalog, entry) for entry in shown)
    )
    return PartsResult(parts=infos, total=len(hits), sample=catalog.is_sample)


class ColorsRequest(BaseModel):
    """Search the catalog's colors."""

    query: CliPositionalArg[str] = Field(
        default="",
        description=(
            "Words to match against ids, names and types, such as 'gray', "
            "or an RGB value, such as '#F2CD37', to list the nearest colors."
        ),
    )


class ColorInfo(BaseModel):
    """A catalog color."""

    id: int = Field(description="BrickLink color id.")
    name: str = Field(description="BrickLink color name.")
    type: ColorType
    rgb: str = Field(description="Display color used by renders.")


class ColorsResult(BaseModel):
    """Colors matching a search."""

    colors: tuple[ColorInfo, ...]

    def describe(self) -> str:
        """Return the result as a table."""
        rows = [
            f"{color.id:>4}  {color.name:<22} {color.type:<12} {color.rgb}"
            for color in self.colors
        ]
        rows.append(plural(len(self.colors), "color"))
        return "\n".join(rows)


async def colors(request: ColorsRequest, session: Session) -> ColorsResult:
    """Search the catalog's colors."""
    found = await asyncio.to_thread(session.catalog.search_colors, request.query)
    return ColorsResult(colors=tuple(_color_info(color) for color in found))


class CatalogImportRequest(BaseModel):
    """Import the catalog: BrickLink parts and colors, shapes from names and LDraw."""

    bricklink: Path | None = Field(
        default=None,
        description=(
            "Folder holding BrickLink's catalog downloads as XML, from "
            f"{DOWNLOAD_PAGE}: Catalog Items (Parts), Colors, Categories and Codes, "
            "under any file names. Without it, parts come from LDraw and colors from "
            "bricky's sample."
        ),
    )
    ldraw: Path | None = Field(
        default=None,
        description=(
            "LDraw parts library folder, holding parts and p, such as an unzipped "
            "complete.zip from library.ldraw.org; LDraw shapes the parts that no name "
            "describes."
        ),
    )
    output: Path | None = Field(
        default=None,
        description=(
            "Catalog file to write; defaults to bricky's data folder, "
            "where bricky looks for it."
        ),
    )


class CatalogImportResult(BaseModel):
    """What an import wrote, where each shape came from, and what the checks found."""

    catalog: Path = Field(description="The catalog file written.")
    coverage: Coverage
    in_use: bool = Field(description="Whether bricky uses this catalog from now on.")

    def describe(self) -> str:
        """Return the result as text."""
        coverage = self.coverage
        unshaped = coverage.parts - coverage.shaped
        lines = [
            f"imported {coverage.parts:,} parts and {coverage.colors:,} colors from:",
            *(f"  {source}" for source in coverage.sources),
            "",
            (
                f"{coverage.shaped:,} parts have a shape and can be placed; "
                f"{unshaped:,} have none"
            ),
            "shapes by source: " + _pairs(coverage.by_source),
            "shapes by family: " + _pairs(coverage.by_family),
        ]
        _section(
            lines,
            "parts without a shape, by category (most first)",
            coverage.unshaped_by_category,
        )
        _section(
            lines,
            "LDraw files that could not be converted, by reason",
            coverage.ldraw_failures,
        )
        if coverage.compared:
            disagreements = coverage.disagreements
            lines += [
                "",
                f"compared {coverage.compared:,} named shapes with LDraw: "
                + plural(len(disagreements), "disagreement"),
                *(
                    f"  {disagreement}"
                    for disagreement in disagreements[:_LISTED_DISAGREEMENTS]
                ),
            ]
            hidden = len(disagreements) - _LISTED_DISAGREEMENTS
            if hidden > 0:
                lines.append(f"  ... and {hidden} more, in the JSON output")
        if coverage.skipped_colors:
            lines += [
                "",
                "colors left out:",
                *(f"  {color}" for color in coverage.skipped_colors),
            ]
        lines += ["", f"wrote {self.catalog}"]
        if not self.in_use:
            lines.append(
                "bricky does not use it yet: set catalog to this file in "
                "[tool.bricky] or BRICKY_CATALOG"
            )
        return "\n".join(lines)


async def catalog_import(
    request: CatalogImportRequest, session: Session, progress: Progress | None = None
) -> CatalogImportResult:
    """Import the catalog from BrickLink's downloads, an LDraw library, or both.

    Args:
        request: The sources and where to write.
        session: The session, whose settings say which catalog bricky uses.
        progress: Receives how many parts the import has looked at, out of how many.

    Raises:
        BrickyError: If no source is given, a source is missing or invalid, or the file
            cannot be written.
    """
    bricklink = None
    if request.bricklink is not None:
        bricklink = await asyncio.to_thread(read_downloads, request.bricklink)
    ldraw = (
        None
        if request.ldraw is None
        else await asyncio.to_thread(Library, request.ldraw)
    )
    catalog, coverage = await asyncio.to_thread(
        import_catalog, bricklink, ldraw, progress
    )
    output = request.output or IMPORTED_CATALOG
    await asyncio.to_thread(write_file, output, catalog.dump())
    in_use = catalog_path(session.settings).resolve() == output.resolve()
    return CatalogImportResult(catalog=output, coverage=coverage, in_use=in_use)


class CatalogStatusRequest(BaseModel):
    """Show which catalog bricky uses and what it holds."""


class CatalogStatusResult(BaseModel):
    """The catalog bricky uses."""

    catalog: Path = Field(description="The catalog file.")
    source: str
    sample: bool = Field(
        description="Whether the catalog is the small sample shipped with bricky."
    )
    parts: int
    shaped: int = Field(description="Parts with a shape, which can be placed.")
    printed: int = Field(
        description="Printed parts shaped like the part they are printed on."
    )
    colors: int
    by_family: dict[str, int] = Field(description="Shaped parts by family.")

    def describe(self) -> str:
        """Return the result as text."""
        counts = (
            f"{self.parts:,} parts, {self.shaped:,} with a shape "
            f"({self.printed:,} printed), "
            f"{self.colors:,} colors"
        )
        lines = [
            f"catalog: {self.catalog}",
            f"source: {self.source}",
            counts,
            *(f"  {family}: {count:,}" for family, count in self.by_family.items()),
        ]
        if self.sample:
            lines.append(
                "the sample shipped with bricky holds a small set of parts; "
                "`bricky catalog import <folder of BrickLink downloads>` "
                "imports every part"
            )
        return "\n".join(lines)


async def catalog_status(
    request: CatalogStatusRequest,  # noqa: ARG001 - every command takes its request
    session: Session,
) -> CatalogStatusResult:
    """Describe the catalog bricky uses."""
    catalog = session.catalog
    path = catalog_path(session.settings)
    families: Counter[str] = Counter()
    printed = 0
    for entry in await asyncio.to_thread(lambda: catalog.entries):
        shape = catalog.shape(entry.id)
        if shape is not None:
            families[shape.family.value] += 1
            printed += entry.base is not None
    return CatalogStatusResult(
        catalog=path,
        source=catalog.source,
        sample=path == SAMPLE_CATALOG,
        parts=len(catalog),
        shaped=families.total(),
        printed=printed,
        colors=len(catalog.colors),
        by_family=dict(families.most_common()),
    )


class CatalogShowRequest(BaseModel):
    """Show everything the catalog knows about one part."""

    part: CliPositionalArg[str] = Field(
        description="BrickLink item number, such as '3001'."
    )
    render: bool = Field(
        default=False,
        description="Also render the part, in the first color it comes in.",
    )
    output: Path | None = Field(
        default=None,
        description=(
            "Image file to write; defaults to <part>.png in bricky's cache "
            "folder, outside the workspace."
        ),
    )


class CatalogShowResult(BaseModel):
    """One catalog part: BrickLink's facts, and the geometry bricky generates for it."""

    part: CatalogPart
    info: PartInfo
    colors: tuple[str, ...] = Field(
        description="Names of the colors the part comes in."
    )
    anti_studs: int | None = Field(
        description="Number of anti-studs; null without a shape."
    )
    connectors: tuple[str, ...] = Field(
        default=(),
        description=(
            "Where the part's studs and anti-studs are, as text: maps of its top and "
            "its underside, north up, then the connectors off those maps."
        ),
    )
    heights: tuple[str, ...] = Field(
        default=(),
        description=(
            "How tall the part stands over the center of each stud square, in plates, "
            "as a map north up; empty when the top is flat."
        ),
    )
    images: tuple[Image, ...] = ()

    def describe(self) -> str:
        """Return the result as text."""
        part, info = self.part, self.info
        lines = [f"{part.id}: {part.name}", f"category: {part.category or 'none'}"]
        if part.alternates:
            lines.append(f"other numbers: {', '.join(part.alternates)}")
        if part.base is not None:
            lines.append(f"printed on: {part.base}, whose shape it has")
        if info.family is None:
            lines.append("shape: none, so it cannot be placed")
        else:
            x, y = info.footprint or (0, 0)
            lines.append(
                f"shape: {info.family}, {x} x {y} studs (x by y, unrotated), "
                f"{plural(info.height or 0, 'plate')} tall, "
                f"{plural(info.studs or 0, 'stud')}, "
                f"{plural(self.anti_studs or 0, 'anti-stud')}"
            )
            if info.note:
                lines.append(f"  {info.note}")
            lines.extend(self.connectors)
            lines.extend(self.heights)
        if self.colors:
            lines.append(f"colors ({len(self.colors)}): {', '.join(self.colors)}")
        lines.extend(describe_images(self.images))
        return "\n".join(lines)


async def catalog_show(
    request: CatalogShowRequest, session: Session
) -> CatalogShowResult:
    """Describe one catalog part, and render it when asked.

    Raises:
        BrickyError: If the catalog does not list the part, or the part has no shape.
    """
    catalog = session.catalog
    entry = catalog.entry(request.part)
    if entry is None:
        message = (
            f"the catalog has no part {request.part!r}; "
            "search it with `bricky parts <words>`"
        )
        raise BrickyError(message)
    part = catalog.part(entry.id)
    names = tuple(
        color.name
        for color_id in entry.colors
        if (color := catalog.color(color_id)) is not None
    )
    images: tuple[Image, ...] = ()
    if request.render:
        if part is None:
            message = f"part {entry.id} has no shape to render"
            raise BrickyError(message)
        color = next(iter(entry.colors), _FALLBACK_COLOR)
        model = Model(
            name=entry.id, elements=(Element(id=entry.id, part=entry.id, color=color),)
        )
        path = request.output or PART_IMAGES / f"{entry.id}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        images = await render_views(
            session,
            model,
            provenance=None,
            report=None,
            views=[View.SHEET],
            paths=[path],
        )
    return CatalogShowResult(
        part=entry,
        info=_part_info(catalog, entry),
        colors=names,
        anti_studs=None
        if part is None
        else sum(
            connector.kind is ConnectorKind.ANTI_STUD for connector in part.connectors
        ),
        connectors=() if part is None else _connector_maps(part),
        heights=() if part is None else _heights(part),
        images=images,
    )


def _connector_maps(part: Part) -> tuple[str, ...]:
    """Maps of a part's top studs and underside anti-studs, then its other connectors.

    Each map, north up, has one character per stud square of the footprint: ``o``
    where a stud stands, or an anti-stud opens, at the square's center, and ``.``
    elsewhere.
    """
    width, length = part.footprint
    top: set[tuple[int, int]] = set()
    underside: set[tuple[int, int]] = set()
    others: list[str] = []
    for connector in part.connectors:
        position = connector.position
        square = ((position.x - STUD // 2) // STUD, (position.y - STUD // 2) // STUD)
        on_grid = position.x % STUD == STUD // 2 and position.y % STUD == STUD // 2
        if on_grid and connector.normal == UP and position.z == part.size.z:
            top.add(square)
        elif on_grid and connector.normal == DOWN and position.z == 0:
            underside.add(square)
        else:
            kind = "stud" if connector.kind is ConnectorKind.STUD else "anti-stud"
            facing = next(
                name for name, axis in AXES.items() if axis == connector.normal
            )
            others.append(
                f"  {kind} facing {facing} at x {to_studs(position.x):g}, "
                f"y {to_studs(position.y):g}, z {to_plates(position.z):g}"
            )

    def plotted(squares: set[tuple[int, int]]) -> list[str]:
        return [
            "    " + " ".join("o" if (x, y) in squares else "." for x in range(width))
            for y in reversed(range(length))
        ]

    lines = ["top studs, north up:", *plotted(top), "underside anti-studs, north up:"]
    lines += plotted(underside)
    if others:
        lines += ["other connectors:", *others]
    return tuple(lines)


def _heights(part: Part) -> tuple[str, ...]:
    """A north-up map of a part's height at each stud square's center; empty if flat."""
    width, length = part.footprint

    def height(x: int, y: int) -> str:
        center = x * STUD + STUD // 2, y * STUD + STUD // 2
        tops = [
            top for solid in part.solids if (top := _top(solid, *center)) is not None
        ]
        return _plates_text(max(tops, default=Fraction(0)))

    tops = [[height(x, y) for x in range(width)] for y in reversed(range(length))]
    if all(cell == tops[0][0] for row in tops for cell in row):
        return ()
    span = max(len(cell) for row in tops for cell in row)
    return (
        "height over each square in plates, north up:",
        *("    " + " ".join(cell.rjust(span) for cell in row) for row in tops),
    )


def _top(solid: Solid, x: int, y: int) -> Fraction | None:
    """The height of a solid's top over (x, y) in base units; ``None`` off the solid."""
    low, high = Fraction(-(10**9)), Fraction(10**9)
    for normal, offset in solid.planes:
        rest = (
            offset - normal.x * x - normal.y * y
        )  # the plane holds normal.z * z <= rest
        if normal.z > 0:
            high = min(high, Fraction(rest, normal.z))
        elif normal.z < 0:
            low = max(low, Fraction(rest, normal.z))
        elif rest < 0:
            return None
    return high if low < high else None


def _plates_text(units: Fraction) -> str:
    """A height in base units, as plates to three decimals at most: 1.875, 3, 10.125."""
    return f"{float(units / PLATE):.3f}".rstrip("0").rstrip(".")


class CatalogVerifyRequest(BaseModel):
    """Generate the geometry of every part with a shape and check it."""


class CatalogVerifyResult(BaseModel):
    """Parts whose geometry breaks a promise every family makes."""

    checked: int = Field(
        description="Parts whose geometry the command generated and checked."
    )
    problems: tuple[str, ...] = Field(description="Each problem, naming its part.")

    def describe(self) -> str:
        """Return the result as text."""
        lines = [
            *self.problems,
            f"checked {self.checked:,} parts: {plural(len(self.problems), 'problem')}",
        ]
        return "\n".join(lines)


async def catalog_verify(
    request: CatalogVerifyRequest,  # noqa: ARG001 - every command takes its request
    session: Session,
) -> CatalogVerifyResult:
    """Generate every shaped part's geometry and check what every family promises.

    A part's body fills its bounding box from the origin; anti-studs sit on its bottom
    face, pointing down and inside its footprint; studs stand on its top face or on a
    side face; and no two connectors of one kind share a position and a direction.
    """
    return await asyncio.to_thread(_verify, session.catalog)


def _part_info(catalog: Catalog, entry: CatalogPart) -> PartInfo:
    info = PartInfo(
        id=entry.id, name=entry.name, category=entry.category, base=entry.base
    )
    part = catalog.part(entry.id)
    if part is None:
        return info
    return info.model_copy(
        update={
            "family": part.family,
            "footprint": part.footprint,
            "height": to_plates(part.size.z),
            "studs": part.stud_count,
            "note": part.note,
        }
    )


def _verify(catalog: Catalog) -> CatalogVerifyResult:
    problems: list[str] = []
    checked = 0
    for entry in catalog.entries:
        try:
            part = catalog.part(entry.id)
        except ValueError as error:
            problems.append(
                f"{entry.id} {entry.name}: its shape cannot be generated: {error}"
            )
            continue
        if part is not None:
            checked += 1
            problems += [
                f"{entry.id} {entry.name}: {problem}"
                for problem in _part_problems(part)
            ]
    return CatalogVerifyResult(checked=checked, problems=tuple(problems))


def _part_problems(part: Part) -> list[str]:
    """List the promises every family makes that a part's geometry breaks."""
    size = part.size
    problems = []
    if Box.bounding(solid.bounds for solid in part.solids) != Box(ORIGIN, size):
        problems.append("its body does not fill its bounding box from the origin")
    sides = {AXES["-x"]: 0, AXES["+x"]: size.x, AXES["-y"]: 0, AXES["+y"]: size.y}
    places = Counter(
        (connector.kind, connector.position, connector.normal)
        for connector in part.connectors
    )
    problems += [
        f"two {kind}s at {position}"
        for (kind, position, _), count in places.items()
        if count > 1
    ]
    for connector in part.connectors:
        position, normal = connector.position, connector.normal
        inside = 0 < position.x < size.x and 0 < position.y < size.y
        if connector.kind is ConnectorKind.ANTI_STUD:
            if normal != DOWN or position.z != 0 or not inside:
                problems.append(
                    f"the anti-stud at {position} is not on the bottom face"
                )
        elif normal == UP:
            if position.z != size.z or not inside:
                problems.append(f"the stud at {position} is not on the top face")
        elif (
            normal not in sides
            or (position.x if normal.x else position.y) != sides[normal]
        ):
            problems.append(
                f"the stud at {position} facing {normal} is not on a side face"
            )
    return problems


def _color_info(color: Color) -> ColorInfo:
    return ColorInfo(id=color.id, name=color.name, type=color.type, rgb=color.rgb)


def _row(cells: Sequence[str], widths: Sequence[int]) -> str:
    """A table row: each cell padded to its column's width, the last left as it is."""
    padded = [
        cell.ljust(width) for cell, width in zip(cells[:-1], widths, strict=False)
    ]
    return "  ".join([*padded, cells[-1]])


def _pairs(counts: dict[str, int]) -> str:
    return ", ".join(f"{name} {count:,}" for name, count in counts.items()) or "none"


def _section(lines: list[str], title: str, counts: dict[str, int]) -> None:
    if not counts:
        return
    lines += ["", f"{title}:"]
    lines += [
        f"  {name}: {count:,}"
        for name, count in list(counts.items())[:_LISTED_CATEGORIES]
    ]
    hidden = len(counts) - _LISTED_CATEGORIES
    if hidden > 0:
        lines.append(f"  ... and {hidden} more")
