# Copyright 2026 Maxence Faldor
"""The families: generators that convert a part's shape into its solids and connectors.

A shape holds a few numbers from the catalog, and its family converts them into
geometry, so many parts share one tested definition. Every generator works in exact base
units (see :mod:`bricky.units`) and puts the minimum corner of the part's bounding box
at the origin.

A body that is not a box is a union of convex solids with integer corners. A few flat
facets draw each curved surface, with their corners on the grid: close to the real part,
and exact.
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
from bricky.geometry import (
    AXES,
    DOWN,
    ORIGIN,
    UP,
    Box,
    Convex,
    Pose,
    Rotation,
    Solid,
    Vector,
)
from bricky.units import PLATE, STUD

BLOCK_HEIGHTS: Final[dict[Family, int]] = {
    Family.BRICK: 3,
    Family.PLATE: 1,
    Family.TILE: 1,
}
"""Default height of bricks, plates and tiles, in plates."""

BASEPLATE_HEIGHT: Final = PLATE // 2
"""A baseplate's thickness: half a plate, 1.6 mm."""

LIP: Final = PLATE // 2
"""Height of the upright edge at the low end of a slope: half a plate."""

_ROUND_SIDES: Final = 16
_CURVE_STEPS: Final = 6

type Profile = list[tuple[int, int]]
"""A polygon in a plane, counterclockwise, as (a, b) pairs: see :meth:`Convex.prism`."""


def build_part(entry: CatalogPart, shape: Shape) -> Part:
    """Generate a catalog part's solids and connectors from its shape or its base's."""
    solids, connectors, note = _geometry(shape)
    bounds = Box.bounding(solid.bounds for solid in solids)
    if isinstance(shape, BoxesShape):
        bounds = Box(ORIGIN, Vector(*shape.size)).transformed(_upright(shape))
    elif bounds.min != ORIGIN:  # pragma: no cover - every family builds from the origin
        message = (
            f"part {entry.id}: its bounding box starts at {bounds.min}, "
            "not at the origin"
        )
        raise ValueError(message)
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
    message = (
        f"no family generates {shape!r}"  # pragma: no cover - the shape union is closed
    )
    raise TypeError(message)


def _positions(
    width: int, length: int, rows: Iterable[int] | None = None
) -> list[tuple[int, int]]:
    """Stud centers of a footprint, in base units; ``rows`` limits the y positions."""
    ys = range(length) if rows is None else rows
    return [
        (i * STUD + STUD // 2, j * STUD + STUD // 2) for i in range(width) for j in ys
    ]


def _studs(positions: Iterable[tuple[int, int]], z: int) -> list[Connector]:
    return [Connector(ConnectorKind.STUD, Vector(x, y, z), UP) for x, y in positions]


def _anti_studs(positions: Iterable[tuple[int, int]]) -> list[Connector]:
    return [
        Connector(ConnectorKind.ANTI_STUD, Vector(x, y, 0), DOWN) for x, y in positions
    ]


def _block(shape: BlockShape) -> Geometry:
    """A box with an anti-stud under every stud position, and studs on top.

    A tile leaves out the studs on top.
    """
    width, length = shape.size
    height = (shape.height or BLOCK_HEIGHTS[Family(shape.family)]) * PLATE
    grid = _positions(width, length)
    connectors = _anti_studs(grid)
    if shape.family != Family.TILE:
        connectors += _studs(grid, height)
    return [Box(ORIGIN, Vector(width * STUD, length * STUD, height))], connectors, ""


def _baseplate(shape: BaseplateShape) -> Geometry:
    """A thin box with studs on top and a flat underside."""
    width, length = shape.size
    body = Box(ORIGIN, Vector(width * STUD, length * STUD, BASEPLATE_HEIGHT))
    note = "half a plate thick: parts standing on it start at z = 0.5"
    return [body], _studs(_positions(width, length), BASEPLATE_HEIGHT), note


def _slope(shape: SlopeShape) -> Geometry:
    """A slope falling from its flat top at the back to a low front lip (y = 0)."""
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
    """A slope underneath: flat at the back, the bottom rising to the front (y = 0)."""
    width, length = shape.size
    run = min(shape.run, length - 1)
    height = shape.height * PLATE
    back, bottom_front = length * STUD, run * STUD
    profile: Profile = [(bottom_front, 0), (back, 0), (back, height), (0, height)]
    profile.append((0, height - min(LIP, height)))
    body = Convex.prism(profile, "x", 0, width * STUD)
    connectors = _studs(_positions(width, length), height)
    connectors += _anti_studs(_positions(width, length, range(run, length)))
    return (
        [body],
        connectors,
        "the underside rises toward -y (the front) when unrotated",
    )


def _curved_slope(shape: CurvedSlopeShape) -> Geometry:
    """A smooth, studless top curving down from the back to a low front lip (y = 0).

    The curve is a quarter ellipse, flat at the back and steep at the front, drawn as a
    few facets with corners on whole base units. The underside is hollow, so every row
    has an anti-stud: a curved slope sits flat on studs.
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
    connectors = _anti_studs(_positions(width, length))
    return [body], connectors, "curves down toward -y (the front) when unrotated"


def _round(shape: RoundShape) -> Geometry:
    """A cylinder filling a square footprint, as a near-regular polygon on the grid."""
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
    """A brick with studs on top, anti-studs underneath, and studs on the named faces.

    Side studs sit half a stud below the top, one per stud position along the face, so a
    plate rotated on its side to grip them lines up with the stud grid along the face
    and ends flush with the brick's top.
    """
    width, length = shape.size
    height = shape.height * PLATE
    grid = _positions(width, length)
    connectors = _anti_studs(grid) + _studs(grid, height)
    middle = height - STUD // 2
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
    return (
        [body],
        connectors,
        f"side studs face {', '.join(shape.sides)} when unrotated",
    )


def _jumper(shape: JumperShape) -> Geometry:
    """A plate with one stud centered on top, half a stud off the grid on a 1 x 2."""
    width, length = shape.size
    center = (width * STUD // 2, length * STUD // 2)
    anti_studs = _positions(width, length)
    if shape.center_anti_stud:
        anti_studs.append(center)
    body = Box(ORIGIN, Vector(width * STUD, length * STUD, PLATE))
    return [body], _anti_studs(anti_studs) + _studs([center], PLATE), ""


def _arch(shape: ArchShape) -> Geometry:
    """An arch along y: a leg at each end and a half-ellipse opening between them.

    The opening rises to one plate below the top. Convex slices, one per facet of the
    curve, form the body over it.
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
        # A vertical facet beside a leg has no body between it and the leg.
        if y0 == y1:
            continue
        slice_ = [(y0, z0), (y1, z1), (y1, height), (y0, height)]
        solids.append(Convex.prism(slice_, "x", 0, thickness))
    legs = [j for j in range(length) if j * STUD < start or j * STUD >= end]
    connectors = _studs(_positions(width, length), height)
    connectors += _anti_studs(_positions(width, length, legs))
    return solids, connectors, "spans along y when unrotated"


def _boxes(shape: BoxesShape) -> Geometry:
    """A body of boxes, with studs and anti-studs where the shape lists them.

    The geometry takes the rotation that the shape names.
    """
    pose = _upright(shape)
    solids = [
        Box(Vector(x0, y0, z0), Vector(x1, y1, z1)).transformed(pose)
        for x0, y0, z0, x1, y1, z1 in shape.boxes
    ]
    connectors = _anti_studs(shape.anti_studs)
    connectors += [
        Connector(ConnectorKind.STUD, Vector(x, y, z), AXES[axis])
        for x, y, z, axis in shape.studs
    ]
    connectors = [connector.transformed(pose) for connector in connectors]
    if shape.rotation == "R0":
        return (
            solids,
            connectors,
            f"converted from {shape.source}, as it is oriented there",
        )
    return (
        solids,
        connectors,
        f"converted from {shape.source}, rotated {shape.rotation}",
    )


def _upright(shape: BoxesShape) -> Pose:
    """The pose that rotates a converted shape and keeps its corner at the origin."""
    rotation = Rotation.parse(shape.rotation)
    rotated = Box(ORIGIN, Vector(*shape.size)).transformed(Pose(rotation))
    return Pose(rotation, -rotated.min)


def _distinct(points: Sequence[tuple[int, int]]) -> Profile:
    """Drop each point equal to the one before it, and a last point equal to the first.

    Rounding to the grid can make neighboring points equal.
    """
    kept: Profile = []
    for point in points:
        if not kept or kept[-1] != point:
            kept.append(point)
    if len(kept) > 1 and kept[0] == kept[-1]:
        kept.pop()
    return kept
