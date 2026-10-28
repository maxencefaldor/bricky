"""Geometry generators for part families.

A family turns a part's shape, a few numbers from the catalog, into the part's solids and
connectors, so many parts share one tested definition. Every generator places the part's bounding
box with its minimum corner at the origin, and works in exact base units (see :mod:`bricky.units`).

Shapes that are not boxes are convex solids with integer corners. Curved surfaces are drawn as a
few flat facets, chosen so the corners stay on the grid: close to the real part, and exact.
"""

from collections.abc import Iterable, Sequence
from itertools import pairwise
from math import cos, pi, sin
from typing import Final

from bricky.catalog.models import (
    ArchShape,
    BaseplateShape,
    BlockShape,
    BoxesShape,
    CatalogPart,
    Connector,
    ConnectorKind,
    CurvedSlopeShape,
    Family,
    InvertedSlopeShape,
    JumperShape,
    Part,
    RoundShape,
    Shape,
    SideStudsShape,
    SlopeShape,
)
from bricky.geometry import AXES, DOWN, ORIGIN, UP, Box, Convex, Solid, Vector
from bricky.units import PLATE, STUD

BLOCK_HEIGHTS: Final[dict[Family, int]] = {Family.BRICK: 3, Family.PLATE: 1, Family.TILE: 1}
"""Default height of bricks, plates and tiles, in plates."""

BASEPLATE_HEIGHT: Final = PLATE // 2
"""A baseplate's thickness: half a plate, 1.6 mm."""

LIP: Final = PLATE // 2
"""Height of the upright edge at the low end of a slope: half a plate."""

_ROUND_SIDES: Final = 16
_CURVE_STEPS: Final = 6

type Profile = list[tuple[int, int]]
"""A polygon in a plane, counter-clockwise, as (a, b) pairs: see :meth:`Convex.prism`."""


def build_part(entry: CatalogPart, shape: Shape) -> Part:
    """Generate a catalog part's solids and connectors from a shape: its own, or its base's."""
    solids, connectors, note = _geometry(shape)
    bounds = Box.bounding(solid.bounds for solid in solids)
    if isinstance(shape, BoxesShape):
        bounds = Box(ORIGIN, Vector(*shape.size))
    elif bounds.min != ORIGIN:  # pragma: no cover - every family builds from the origin
        msg = f"part {entry.id}: its bounding box starts at {bounds.min}, not at the origin"
        raise ValueError(msg)
    return Part(
        id=entry.id,
        name=entry.name,
        family=Family(shape.family),
        size=bounds.max,
        solids=tuple(solids),
        connectors=tuple(connectors),
        note=note,
        category=entry.category,
    )


type Geometry = tuple[Sequence[Solid], list[Connector], str]
"""A part's solids, its connectors, and a note on how it sits when placed unrotated."""


def _geometry(shape: object) -> Geometry:  # noqa: C901, PLR0911 - one return per family
    match shape:
        case BlockShape():
            return _block(shape)
        case BaseplateShape():
            return _baseplate(shape)
        case SlopeShape():
            return _slope(shape)
        case InvertedSlopeShape():
            return _inverted_slope(shape)
        case CurvedSlopeShape():
            return _curved_slope(shape)
        case RoundShape():
            return _round(shape)
        case SideStudsShape():
            return _side_studs(shape)
        case JumperShape():
            return _jumper(shape)
        case ArchShape():
            return _arch(shape)
        case BoxesShape():
            return _boxes(shape)
    msg = f"no family generates {shape!r}"  # pragma: no cover - the shape union is closed
    raise TypeError(msg)


def _positions(width: int, length: int, rows: Iterable[int] | None = None) -> list[tuple[int, int]]:
    """Stud centers of a footprint, in base units; ``rows`` limits the y positions."""
    ys = range(length) if rows is None else rows
    return [(i * STUD + STUD // 2, j * STUD + STUD // 2) for i in range(width) for j in ys]


def _studs(positions: Iterable[tuple[int, int]], z: int) -> list[Connector]:
    return [Connector(ConnectorKind.STUD, Vector(x, y, z), UP) for x, y in positions]


def _anti_studs(positions: Iterable[tuple[int, int]]) -> list[Connector]:
    return [Connector(ConnectorKind.ANTI_STUD, Vector(x, y, 0), DOWN) for x, y in positions]


def _block(shape: BlockShape) -> Geometry:
    """A box with anti-studs under every stud position, and studs on top unless it is a tile."""
    width, length = shape.size
    height = (shape.height or BLOCK_HEIGHTS[Family(shape.family)]) * PLATE
    grid = _positions(width, length)
    connectors = _anti_studs(grid)
    if shape.family != Family.TILE:
        connectors += _studs(grid, height)
    return [Box(ORIGIN, Vector(width * STUD, length * STUD, height))], connectors, ""


def _baseplate(shape: BaseplateShape) -> Geometry:
    """A thin box with studs on top and a flat underside that grips nothing."""
    width, length = shape.size
    body = Box(ORIGIN, Vector(width * STUD, length * STUD, BASEPLATE_HEIGHT))
    note = "half a plate thick: parts standing on it start at z = 0.5"
    return [body], _studs(_positions(width, length), BASEPLATE_HEIGHT), note


def _slope(shape: SlopeShape) -> Geometry:
    """A slope falling from its flat top at the back to a low lip at the front (y = 0)."""
    width, length = shape.size
    run = min(shape.run, length)
    height = shape.height * PLATE
    back, top_front = length * STUD, run * STUD
    lip = min(LIP, height)
    profile: Profile = [(0, 0), (back, 0), (back, height)]
    if top_front < back:
        profile.append((top_front, height))
    profile.append((0, lip))
    body = Convex.prism(profile, "x", 0, width * STUD)
    connectors = _anti_studs(_positions(width, length))
    if shape.studs:
        connectors += _studs(_positions(width, length, range(run, length)), height)
    return [body], connectors, "falls toward -y (the front) when unrotated"


def _inverted_slope(shape: InvertedSlopeShape) -> Geometry:
    """A slope underneath: flat bottom at the back, the underside rising to the front (y = 0)."""
    width, length = shape.size
    run = min(shape.run, length - 1)
    height = shape.height * PLATE
    back, bottom_front = length * STUD, run * STUD
    profile: Profile = [(bottom_front, 0), (back, 0), (back, height), (0, height)]
    profile.append((0, height - min(LIP, height)))
    body = Convex.prism(profile, "x", 0, width * STUD)
    connectors = _studs(_positions(width, length), height)
    connectors += _anti_studs(_positions(width, length, range(run, length)))
    return [body], connectors, "its underside rises toward -y (the front) when unrotated"


def _curved_slope(shape: CurvedSlopeShape) -> Geometry:
    """A smooth top curving down from the back to a low lip at the front (y = 0), no studs.

    The curve is a quarter ellipse, flat at the back and steep at the front, drawn as a few facets
    with corners on whole base units. Under the front row the part is too low for a stud, so a
    curved slope longer than one stud has anti-studs under every row but that one.
    """
    width, length = shape.size
    height = shape.height * PLATE
    back = length * STUD
    lip = min(LIP, height)
    arc = [
        (round(back * (1 - cos(t))), round(lip + (height - lip) * sin(t)))
        for t in (pi / 2 * k / _CURVE_STEPS for k in range(_CURVE_STEPS, -1, -1))
    ]
    profile: Profile = [(0, 0), (back, 0), *_distinct(arc)]
    body = Convex.prism(profile, "x", 0, width * STUD)
    rows = range(1, length) if length > 1 else range(1)  # the front row is too low for a stud
    connectors = _anti_studs(_positions(width, length, rows))
    return [body], connectors, "curves down toward -y (the front) when unrotated"


def _round(shape: RoundShape) -> Geometry:
    """A cylinder filling a square footprint, drawn as a regular polygon with integer corners."""
    width, length = shape.size
    radius = width * STUD // 2
    height = shape.height * PLATE
    polygon = [
        (radius + round(radius * cos(2 * pi * k / _ROUND_SIDES)),
         radius + round(radius * sin(2 * pi * k / _ROUND_SIDES)))
        for k in range(_ROUND_SIDES)
    ]  # fmt: skip
    body = Convex.prism(_distinct(polygon), "z", 0, height)
    grid = _positions(width, length)
    connectors = _anti_studs(grid)
    if shape.studs:
        connectors += _studs(grid, height)
    return [body], connectors, ""


def _side_studs(shape: SideStudsShape) -> Geometry:
    """A brick with studs on top, anti-studs underneath, and studs on the faces it names.

    Side studs sit at the middle of the face's height, one per stud position along it, so a
    plate rotated on its side to grip them lines up with the stud grid.
    """
    width, length = shape.size
    height = shape.height * PLATE
    grid = _positions(width, length)
    connectors = _anti_studs(grid) + _studs(grid, height)
    middle = height // 2
    for side in shape.sides:
        normal = AXES[side]
        if side in {"-y", "+y"}:
            y = 0 if side == "-y" else length * STUD
            spots = [Vector(i * STUD + STUD // 2, y, middle) for i in range(width)]
        else:
            x = 0 if side == "-x" else width * STUD
            spots = [Vector(x, j * STUD + STUD // 2, middle) for j in range(length)]
        connectors += [Connector(ConnectorKind.STUD, spot, normal) for spot in spots]
    body = Box(ORIGIN, Vector(width * STUD, length * STUD, height))
    return [body], connectors, f"side studs face {', '.join(shape.sides)} when unrotated"


def _jumper(shape: JumperShape) -> Geometry:
    """A plate with one stud in the middle of its top, half a stud off the grid on a 1 x 2."""
    width, length = shape.size
    center = (width * STUD // 2, length * STUD // 2)
    anti_studs = _positions(width, length)
    if shape.center_anti_stud:
        anti_studs.append(center)
    body = Box(ORIGIN, Vector(width * STUD, length * STUD, PLATE))
    return [body], _anti_studs(anti_studs) + _studs([center], PLATE), ""


def _arch(shape: ArchShape) -> Geometry:
    """An arch along y: a leg at each end and an opening under a half-ellipse between them.

    The opening rises to one plate below the top. The body over it is cut into convex slices, one
    per facet of the curve.
    """
    width, length = shape.size
    height = shape.height * PLATE
    span = shape.span * STUD
    start = (length * STUD - span) // 2
    end = start + span
    rise = height - PLATE
    thickness = width * STUD
    curve = _distinct(
        [
            (start + round(span / 2 * (1 - cos(t))), round(rise * sin(t)))
            for t in (pi * k / (2 * _CURVE_STEPS) for k in range(2 * _CURVE_STEPS + 1))
        ]
    )
    solids: list[Solid] = [
        Box(ORIGIN, Vector(thickness, start, height)),
        Box(Vector(0, end, 0), Vector(thickness, length * STUD, height)),
    ]
    for (y0, z0), (y1, z1) in pairwise(curve):
        if y0 == y1:  # a steep facet beside a leg: no body between it and the leg
            continue
        slice_ = [(y0, z0), (y1, z1), (y1, height), (y0, height)]
        solids.append(Convex.prism(slice_, "x", 0, thickness))
    legs = [j for j in range(length) if j * STUD < start or j * STUD >= end]
    connectors = _studs(_positions(width, length), height)
    connectors += _anti_studs(_positions(width, length, legs))
    return solids, connectors, "spans along y when unrotated"


def _boxes(shape: BoxesShape) -> Geometry:
    """A body of boxes, with studs and anti-studs where the shape says."""
    solids = [Box(Vector(x0, y0, z0), Vector(x1, y1, z1)) for x0, y0, z0, x1, y1, z1 in shape.boxes]
    connectors = _anti_studs(shape.anti_studs)
    connectors += [
        Connector(ConnectorKind.STUD, Vector(x, y, z), AXES[axis]) for x, y, z, axis in shape.studs
    ]
    return solids, connectors, f"converted from {shape.source}, as it is oriented there"


def _distinct(points: Sequence[tuple[int, int]]) -> Profile:
    """Drop points that repeat the one before, which rounding can produce."""
    kept: Profile = []
    for point in points:
        if not kept or kept[-1] != point:
            kept.append(point)
    if len(kept) > 1 and kept[0] == kept[-1]:
        kept.pop()
    return kept
