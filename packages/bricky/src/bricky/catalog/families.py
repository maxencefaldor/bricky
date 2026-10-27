"""Geometry generators for part families.

A family turns a few numbers from the catalog data files into a part's solids and connectors, so
dozens of parts share one tested definition. Every generator places the part's bounding box with
its minimum corner at the origin, and works in exact base units (see :mod:`bricky.units`).

Shapes that are not boxes are convex solids with integer corners. Curved surfaces are drawn as a
few flat facets, chosen so the corners stay on the grid: close to the real part, and exact.
"""

from collections.abc import Iterable, Sequence
from itertools import pairwise
from math import cos, pi, sin
from typing import Final

from bricky.catalog.models import (
    ArchSpec,
    BaseplateSpec,
    BlockSpec,
    Connector,
    ConnectorKind,
    CurvedSlopeSpec,
    Family,
    InvertedSlopeSpec,
    JumperSpec,
    Part,
    PartSpec,
    RoundSpec,
    SideStudsSpec,
    SlopeSpec,
)
from bricky.geometry import AXES, DOWN, ORIGIN, UP, Box, Convex, Solid, Vec3
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


def build_part(spec: PartSpec) -> Part:  # noqa: PLR0911 - one return per family
    """Generate a part's solids and connectors from its catalog entry."""
    match spec:
        case BlockSpec():
            return _block(spec)
        case BaseplateSpec():
            return _baseplate(spec)
        case SlopeSpec():
            return _slope(spec)
        case InvertedSlopeSpec():
            return _inverted_slope(spec)
        case CurvedSlopeSpec():
            return _curved_slope(spec)
        case RoundSpec():
            return _round(spec)
        case SideStudsSpec():
            return _side_studs(spec)
        case JumperSpec():
            return _jumper(spec)
        case ArchSpec():
            return _arch(spec)


def _part(
    spec: PartSpec,
    solids: Sequence[Solid],
    connectors: Iterable[Connector],
    note: str = "",
) -> Part:
    bounds = Box.bounding(solid.bounds for solid in solids)
    if bounds.lo != ORIGIN:
        msg = f"part {spec.id}: its bounding box starts at {bounds.lo}, not at the origin"
        raise ValueError(msg)
    return Part(
        id=spec.id,
        name=spec.name,
        family=Family(spec.family),
        size=bounds.hi,
        solids=tuple(solids),
        connectors=tuple(connectors),
        note=note,
    )


def _positions(width: int, length: int, rows: Iterable[int] | None = None) -> list[tuple[int, int]]:
    """Stud centres of a footprint, in base units; ``rows`` limits the y positions."""
    ys = range(length) if rows is None else rows
    return [(i * STUD + STUD // 2, j * STUD + STUD // 2) for i in range(width) for j in ys]


def _studs(positions: Iterable[tuple[int, int]], z: int) -> list[Connector]:
    return [Connector(ConnectorKind.STUD, Vec3(x, y, z), UP) for x, y in positions]


def _receptors(positions: Iterable[tuple[int, int]]) -> list[Connector]:
    return [Connector(ConnectorKind.ANTI_STUD, Vec3(x, y, 0), DOWN) for x, y in positions]


def _block(spec: BlockSpec) -> Part:
    """A box with receptors under every stud position, and studs on top unless it is a tile."""
    width, length = spec.size
    height = (spec.height or BLOCK_HEIGHTS[Family(spec.family)]) * PLATE
    grid = _positions(width, length)
    connectors = _receptors(grid)
    if spec.family != Family.TILE:
        connectors += _studs(grid, height)
    return _part(spec, [Box(ORIGIN, Vec3(width * STUD, length * STUD, height))], connectors)


def _baseplate(spec: BaseplateSpec) -> Part:
    """A thin box with studs on top and a flat underside that grips nothing."""
    width, length = spec.size
    body = Box(ORIGIN, Vec3(width * STUD, length * STUD, BASEPLATE_HEIGHT))
    note = "half a plate thick: parts standing on it start at z = 0.5"
    return _part(spec, [body], _studs(_positions(width, length), BASEPLATE_HEIGHT), note)


def _slope(spec: SlopeSpec) -> Part:
    """A slope falling from its flat top at the back to a low lip at the front (y = 0)."""
    width, depth = spec.size
    run = min(spec.run, depth)
    height = spec.height * PLATE
    back, top_front = depth * STUD, run * STUD
    lip = min(LIP, height)
    profile: Profile = [(0, 0), (back, 0), (back, height)]
    if top_front < back:
        profile.append((top_front, height))
    profile.append((0, lip))
    body = Convex.prism(profile, "x", 0, width * STUD)
    connectors = _receptors(_positions(width, depth))
    if spec.studs:
        connectors += _studs(_positions(width, depth, range(run, depth)), height)
    return _part(spec, [body], connectors, "falls toward -y (the front) when unturned")


def _inverted_slope(spec: InvertedSlopeSpec) -> Part:
    """A slope underneath: flat bottom at the back, the underside rising to the front (y = 0)."""
    width, depth = spec.size
    run = min(spec.run, depth - 1)
    height = spec.height * PLATE
    back, bottom_front = depth * STUD, run * STUD
    profile: Profile = [(bottom_front, 0), (back, 0), (back, height), (0, height)]
    profile.append((0, height - min(LIP, height)))
    body = Convex.prism(profile, "x", 0, width * STUD)
    connectors = _studs(_positions(width, depth), height)
    connectors += _receptors(_positions(width, depth, range(run, depth)))
    note = "its underside rises toward -y (the front) when unturned"
    return _part(spec, [body], connectors, note)


def _curved_slope(spec: CurvedSlopeSpec) -> Part:
    """A smooth top curving down from the back to a low lip at the front (y = 0), no studs.

    The curve is a quarter ellipse, flat at the back and steep at the front, drawn as a few facets
    with corners on whole base units.
    """
    width, depth = spec.size
    height = spec.height * PLATE
    back = depth * STUD
    lip = min(LIP, height)
    arc = [
        (round(back * (1 - cos(t))), round(lip + (height - lip) * sin(t)))
        for t in (pi / 2 * k / _CURVE_STEPS for k in range(_CURVE_STEPS, -1, -1))
    ]
    profile: Profile = [(0, 0), (back, 0), *_distinct(arc)]
    body = Convex.prism(profile, "x", 0, width * STUD)
    connectors = _receptors(_positions(width, depth))
    return _part(spec, [body], connectors, "curves down toward -y (the front) when unturned")


def _round(spec: RoundSpec) -> Part:
    """A cylinder filling a square footprint, drawn as a regular polygon with integer corners."""
    width, length = spec.size
    if width != length:
        msg = f"part {spec.id}: a round part needs a square footprint, not {width} x {length}"
        raise ValueError(msg)
    radius = width * STUD // 2
    height = spec.height * PLATE
    polygon = [
        (radius + round(radius * cos(2 * pi * k / _ROUND_SIDES)),
         radius + round(radius * sin(2 * pi * k / _ROUND_SIDES)))
        for k in range(_ROUND_SIDES)
    ]  # fmt: skip
    body = Convex.prism(_distinct(polygon), "z", 0, height)
    grid = _positions(width, length)
    connectors = _receptors(grid)
    if spec.studs:
        connectors += _studs(grid, height)
    return _part(spec, [body], connectors)


def _side_studs(spec: SideStudsSpec) -> Part:
    """A brick with studs on top, receptors underneath, and studs on the faces it names.

    Side studs sit at the middle of the face's height, one per stud position along it, so a
    plate turned on its side to grip them lines up with the stud grid.
    """
    width, length = spec.size
    height = spec.height * PLATE
    grid = _positions(width, length)
    connectors = _receptors(grid) + _studs(grid, height)
    middle = height // 2
    for side in spec.sides:
        normal = AXES[side]
        if side in {"-y", "+y"}:
            y = 0 if side == "-y" else length * STUD
            spots = [Vec3(i * STUD + STUD // 2, y, middle) for i in range(width)]
        else:
            x = 0 if side == "-x" else width * STUD
            spots = [Vec3(x, j * STUD + STUD // 2, middle) for j in range(length)]
        connectors += [Connector(ConnectorKind.STUD, spot, normal) for spot in spots]
    body = Box(ORIGIN, Vec3(width * STUD, length * STUD, height))
    note = f"side studs face {', '.join(spec.sides)} when unturned"
    return _part(spec, [body], connectors, note)


def _jumper(spec: JumperSpec) -> Part:
    """A plate with one stud in the middle of its top, half a stud off the grid on a 1 x 2."""
    width, length = spec.size
    centre = (width * STUD // 2, length * STUD // 2)
    receptors = _positions(width, length)
    if spec.centre_receptor:
        receptors.append(centre)
    body = Box(ORIGIN, Vec3(width * STUD, length * STUD, PLATE))
    return _part(spec, [body], _receptors(receptors) + _studs([centre], PLATE))


def _arch(spec: ArchSpec) -> Part:
    """An arch along y: a leg at each end and an opening under a half-ellipse between them.

    The opening rises to one plate below the top. The body over it is cut into convex slices, one
    per facet of the curve.
    """
    width, length = spec.size
    height = spec.height * PLATE
    span = spec.span * STUD
    start = (length * STUD - span) // 2
    end = start + span
    rise = height - PLATE
    if start <= 0 or start % STUD:
        msg = f"part {spec.id}: the opening must leave a whole-stud leg at each end"
        raise ValueError(msg)
    thickness = width * STUD
    curve = _distinct(
        [
            (start + round(span / 2 * (1 - cos(t))), round(rise * sin(t)))
            for t in (pi * k / (2 * _CURVE_STEPS) for k in range(2 * _CURVE_STEPS + 1))
        ]
    )
    solids: list[Solid] = [
        Box(ORIGIN, Vec3(thickness, start, height)),
        Box(Vec3(0, end, 0), Vec3(thickness, length * STUD, height)),
    ]
    for (y0, z0), (y1, z1) in pairwise(curve):
        slice_ = [(y0, z0), (y1, z1), (y1, height), (y0, height)]
        solids.append(Convex.prism(slice_, "x", 0, thickness))
    legs = [j for j in range(length) if j * STUD < start or j * STUD >= end]
    connectors = _studs(_positions(width, length), height)
    connectors += _receptors(_positions(width, length, legs))
    return _part(spec, solids, connectors, "spans along y when unturned")


def _distinct(points: Sequence[tuple[int, int]]) -> Profile:
    """Drop points that repeat the one before, which rounding can produce."""
    kept: Profile = []
    for point in points:
        if not kept or kept[-1] != point:
            kept.append(point)
    if len(kept) > 1 and kept[0] == kept[-1]:
        kept.pop()
    return kept
