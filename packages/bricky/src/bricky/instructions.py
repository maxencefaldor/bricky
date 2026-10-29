# Copyright 2026 Maxence Faldor
"""Instructions: the order to build a model in, a few elements per step.

Each element goes on along one direction, its approach. Elements resting on the ground
or on studs below them go on downward. An element held from above only goes on attached
under the element that holds it, and the two move as one. Other elements go on along
the side where they join the most studs.

An element going on downward arrives straight from above the model. An element going
on sideways drops from above to a stud's height away from its place, then slides in.

Three rules make an order buildable with these moves:

1. Something holds each element as it goes on: the ground, or an element it presses
   onto along its approach.
2. Each connection forms as its second element goes on, so that element's approach
   points at the first.
3. An element goes on before every element in its way: the space its solids sweep as
   they arrive.

The sweeps are exact, slopes included, since every solid is convex with integer corners.

Among the elements the rules allow next, the order keeps to one section of the build
script, the outermost function that placed them, and goes bottom up. A step takes up
to six elements of its section, about one brick high and within 8 studs of one another,
nearest first.

Elements that lock one another in leave no order that follows every rule. The order
then places the element that breaks the fewest, and notes what it breaks.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from bricky.analysis import SpatialHash, World, build_world
from bricky.analysis.connections import anti_stud_index
from bricky.catalog import Catalog, ConnectorKind
from bricky.geometry import AXES, DOWN, ORIGIN, UP, Box, Convex, Solid, Vector
from bricky.model import Model
from bricky.provenance import Provenance
from bricky.units import BRICK, STUD, STUD_HEIGHT

ELEMENTS_PER_STEP: Final = 6
"""How many elements a step adds at most, by default; LEGO® sets add about five."""

STEP_SPAN: Final = 8 * STUD
"""How far apart, across, the elements of one step may lie, unless one is wider."""

STEP_RISE: Final = BRICK
"""How far apart in height the bottoms of one step's elements may lie."""

_SCRIPT_ROOTS: Final = frozenset({"build", "<module>"})

_AXIS_ORDER: Final = tuple(AXES.values())

_GRID_AXES: Final = (AXES["+x"], AXES["+y"], AXES["+z"])
"""The face normals and edge directions of every box."""


class Reason(StrEnum):
    """Why an element should have gone on later."""

    HELD = "held"
    """An element that holds it was still to go on."""

    WAY = "way"
    """It stands in the way of an element still to go on."""


@dataclass(frozen=True, slots=True)
class Step:
    """The elements that go on together."""

    elements: tuple[int, ...]
    """Indices into the world's elements, in the order they go on."""

    approaches: tuple[Vector, ...]
    """The direction each element goes on along, such as ``DOWN``."""

    section: str
    """The build script's function that placed them, or an empty string."""


@dataclass(frozen=True, slots=True)
class Forced:
    """An element placed against a rule, because elements lock one another in."""

    element: int
    """Index into the world's elements."""

    step: int
    """Index of the step that places it."""

    pending: tuple[tuple[int, Reason], ...]
    """The elements it should have followed, each with why."""

    def describe(self, uids: Sequence[str]) -> str:
        """Say what the element breaks, such as ``"e7 goes on before e3, which..."``."""
        holders = [uids[j] for j, reason in self.pending if reason is Reason.HELD]
        blocked = [uids[j] for j, reason in self.pending if reason is Reason.WAY]
        clauses: list[str] = []
        if holders:
            verb = "holds" if len(holders) == 1 else "hold"
            clauses.append(f"before {_names(holders)}, which {verb} it")
        if blocked:
            clauses.append(f"into the way of {_names(blocked)}")
        if not clauses:
            clauses.append("before anything holds it")
        return f"{uids[self.element]} goes on {' and '.join(clauses)}"


@dataclass(frozen=True, slots=True)
class Instructions:
    """The steps to build a model, and every element placed against a rule."""

    steps: tuple[Step, ...]
    forced: tuple[Forced, ...]


def build_instructions(
    model: Model,
    catalog: Catalog,
    *,
    provenance: Provenance | None = None,
    elements_per_step: int = ELEMENTS_PER_STEP,
) -> Instructions:
    """Order a model's elements into steps, bottom up and one script section at a time.

    Args:
        model: The model.
        catalog: The catalog that resolves parts.
        provenance: The script lines that placed each element; with it, each step keeps
            to one section of the build script.
        elements_per_step: How many elements a step adds at most.
    """
    world = build_world(model, catalog)
    if not world.elements:
        return Instructions(steps=(), forced=())
    units, of = _units(world)
    _constrain(world, units, of)
    sections = _sections(model, world, provenance)
    schedule = _Schedule(units, [sections[unit.members[0]] for unit in units])
    return schedule.run(elements_per_step)


@dataclass(slots=True)
class _Unit:
    """Elements that go on as one: an element and those attached under it."""

    members: list[int]
    """Element indices; the first holds the rest."""

    approach: Vector
    bounds: Box
    bottom: int
    """The bottom of the first member, where the unit lands."""

    grounded: bool = False
    before: dict[int, Reason] = field(default_factory=dict)
    """The units that go on before this one, with why."""

    after: set[int] = field(default_factory=set)
    """The units that go on after this one."""

    holders: set[int] = field(default_factory=set)
    """The units this one presses onto along its approach."""


type _Joins = list[defaultdict[Vector, Counter[int]]]
"""For each element and direction, the elements it meets moving that way, with studs."""


def _joins(world: World) -> _Joins:
    anti_studs = anti_stud_index(world)
    joins: _Joins = [defaultdict(Counter) for _ in world.elements]
    for i, element in enumerate(world.elements):
        for connector in element.connectors:
            if connector.kind is not ConnectorKind.STUD:
                continue
            for j in anti_studs.get((connector.position, -connector.normal), ()):
                if j != i:
                    joins[i][connector.normal][j] += 1
                    joins[j][-connector.normal][i] += 1
    return joins


def _units(world: World) -> tuple[list[_Unit], list[int]]:
    """Group elements into units, and return each element's unit."""
    elements = world.elements
    joins = _joins(world)
    grounded = [element.bounds.min.z == 0 for element in elements]
    depth = _depths(joins, grounded)
    approach = [
        _approach(sides, depth, grounded=down)
        for sides, down in zip(joins, grounded, strict=True)
    ]
    # An element going on upward hangs under an element above, which carries it: the
    # one nearest the ground, then the one it joins most. Carriers sit higher, so
    # following them always ends.
    carrier: list[int] = list(range(len(elements)))
    for i, sides in enumerate(joins):
        if approach[i] == UP:
            above = sides[UP]
            carrier[i] = min(above, key=lambda j: (depth[j], -above[j], j))

    roots: list[int] = []
    for i in range(len(elements)):
        top = i
        while carrier[top] != top:
            top = carrier[top]
        roots.append(top)
    index_of: dict[int, int] = {}
    units: list[_Unit] = []
    for i in sorted(range(len(elements)), key=lambda i: (roots[i] != i, i)):
        top = roots[i]
        if top not in index_of:
            index_of[top] = len(units)
            bounds = elements[top].bounds
            units.append(_Unit([], approach[top], bounds, bounds.min.z))
        unit = units[index_of[top]]
        unit.members.append(i)
        unit.bounds = Box.bounding((unit.bounds, elements[i].bounds))
        unit.grounded = unit.grounded or grounded[i]
    of = [index_of[top] for top in roots]
    for u, unit in enumerate(units):
        unit.holders = {
            of[j]
            for i in unit.members
            for j in joins[i].get(unit.approach, ())
            if of[j] != u
        }
    _connect(joins, units, of)
    return units, of


def _depths(joins: _Joins, grounded: Sequence[bool]) -> list[float]:
    """How many connections separate each element from one on the ground."""
    depth: list[float] = [0 if down else math.inf for down in grounded]
    frontier = [i for i, down in enumerate(grounded) if down]
    while frontier:
        following: list[int] = []
        for i in frontier:
            for neighbors in joins[i].values():
                for j in neighbors:
                    if depth[j] == math.inf:
                        depth[j] = depth[i] + 1
                        following.append(j)
        frontier = following
    return depth


def _approach(
    sides: dict[Vector, Counter[int]], depth: Sequence[float], *, grounded: bool
) -> Vector:
    """The direction an element goes on along, before units group elements.

    An element goes on downward when it rests on the ground or on studs below it, and
    otherwise toward the side nearest the ground, so it joins the standing structure
    first. Ties go to the side with more studs, then to the earlier axis.
    """
    if grounded or not sides or DOWN in sides:
        return DOWN
    return min(
        sides,
        key=lambda side: (
            min(depth[j] for j in sides[side]),
            -sides[side].total(),
            _AXIS_ORDER.index(side),
        ),
    )


def _precede(units: Sequence[_Unit], first: int, then: int, reason: Reason) -> None:
    units[then].before.setdefault(first, reason)
    units[first].after.add(then)


def _connect(joins: _Joins, units: Sequence[_Unit], of: Sequence[int]) -> None:
    """Order the units of each connection so its second unit moves toward the first."""
    for i, sides in enumerate(joins):
        for direction, neighbors in sides.items():
            for j in neighbors:
                u, v = of[i], of[j]
                if j < i or u == v:
                    continue
                # Unit u meets v moving along direction; v meets u moving back.
                u_moves = units[u].approach == direction
                v_moves = units[v].approach == -direction
                if u_moves and not v_moves:
                    _precede(units, v, u, Reason.HELD)
                elif v_moves and not u_moves:
                    _precede(units, u, v, Reason.HELD)


@dataclass(frozen=True, slots=True)
class _Leg:
    """One straight move: from ``offset`` back along ``direction`` by ``length``."""

    offset: Vector
    direction: Vector
    length: int | None
    """How far the move runs, or None for a move from beyond the model."""


def _motion(approach: Vector) -> tuple[_Leg, ...]:
    """The moves that bring a unit to its place along its approach."""
    if approach == DOWN:
        return (_Leg(ORIGIN, DOWN, None),)
    back = -(approach * STUD_HEIGHT)
    return (_Leg(back, DOWN, None), _Leg(ORIGIN, approach, STUD_HEIGHT))


def _constrain(world: World, units: Sequence[_Unit], of: Sequence[int]) -> None:
    """Order each unit before every unit in its way."""
    ways = _Ways(world, of)
    for u, unit in enumerate(units):
        for v in ways.blocked(u, unit):
            _precede(units, u, v, Reason.WAY)


class _Ways:
    """Find the units in the way of each unit's moves, with a spatial index."""

    def __init__(self, world: World, of: Sequence[int]) -> None:
        self.elements = world.elements
        self.of = of
        self.index: SpatialHash[int] = SpatialHash()
        for i, element in enumerate(self.elements):
            for solid in element.solids:
                self.index.insert(i, solid.bounds)
        self.reach = Box.bounding(element.bounds for element in self.elements)
        self.solids = _Solids()

    def blocked(self, u: int, unit: _Unit) -> set[int]:
        """The units that a unit's solids pass through on their way in."""
        found: set[int] = set()
        for leg in _motion(unit.approach):
            for i in unit.members:
                for solid in self.elements[i].solids:
                    sweep = _Sweep(solid, leg, self.reach, self.solids)
                    for j in self.index.query(sweep.path):
                        v = self.of[j]
                        if (
                            v != u
                            and v not in found
                            and sweep.crosses_any(self.elements[j].solids)
                        ):
                            found.add(v)
        return found


class _Solids:
    """The extents and separating axes of solids, each computed once.

    The keys are the solids' ids, since every solid lives as long as its world.
    """

    def __init__(self) -> None:
        self._extents: dict[tuple[int, Vector], tuple[int, int]] = {}
        self._axes: dict[int, tuple[Vector, ...]] = {}

    def extent(self, solid: Solid, axis: Vector) -> tuple[int, int]:
        """The least and greatest of ``axis.dot(point)`` over a solid's points."""
        key = (id(solid), axis)
        extent = self._extents.get(key)
        if extent is None:
            extent = _extent(solid, axis)
            self._extents[key] = extent
        return extent

    def axes(self, solid: Solid) -> tuple[Vector, ...]:
        """The axes that separate a box from a solid, when any does."""
        axes = self._axes.get(id(solid))
        if axes is None:
            crossed = (
                axis.cross(edge) for axis in _GRID_AXES for edge in _edges(solid)
            )
            axes = tuple({*_GRID_AXES, *_faces(solid), *crossed} - {ORIGIN})
            self._axes[id(solid)] = axes
        return axes


class _Sweep:
    """The space a solid sweeps along one leg, tested exactly by separating axes.

    The swept space is convex. Its faces face along the solid's own normals, or across
    the move and the solid's edges, so those axes and the cross products of edges decide
    overlap exactly.
    """

    def __init__(self, solid: Solid, leg: _Leg, reach: Box, solids: _Solids) -> None:
        self.solid = solid
        self.leg = leg
        self.solids = solids
        self.path = _path(solid.bounds, leg, reach)
        self._extents: dict[Vector, tuple[float, float]] = {}
        self.edges: tuple[Vector, ...] = ()
        self.axes: set[Vector] = set()
        if isinstance(solid, Convex):
            self.edges = (*solid.directions, leg.direction)
            self.axes = {normal for normal, _ in solid.planes}
            self.axes.update(leg.direction.cross(edge) for edge in solid.directions)
            self.axes.discard(ORIGIN)

    def crosses_any(self, solids: Iterable[Solid]) -> bool:
        """Whether the sweep shares positive volume with any of the solids."""
        return any(self.crosses(other) for other in solids)

    def crosses(self, other: Solid) -> bool:
        """Whether the sweep shares positive volume with a solid."""
        if not other.bounds.overlaps(self.path):
            return False
        if isinstance(self.solid, Box):
            # A box sweeps exactly its path, itself a box.
            if isinstance(other, Box):
                return True
            return not any(
                self._apart(_extent(self.path, axis), other, axis)
                for axis in self.solids.axes(other)
            )
        return not any(
            self._apart(self._extent(axis), other, axis) for axis in self._axes(other)
        )

    def _axes(self, other: Solid) -> Iterator[Vector]:
        yield from self.axes
        yield from _faces(other)
        for edge in self.edges:
            for along in _edges(other):
                axis = edge.cross(along)
                if axis != ORIGIN:
                    yield axis

    def _extent(self, axis: Vector) -> tuple[float, float]:
        """The sweep's extent along an axis."""
        extent = self._extents.get(axis)
        if extent is not None:
            return extent
        low, high = _extent(self.solid, axis)
        shift = axis.dot(self.leg.offset)
        start: float = low + shift
        end: float = high + shift
        drift = axis.dot(self.leg.direction)
        length = self.leg.length
        if drift > 0:
            start = -math.inf if length is None else start - length * drift
        elif drift < 0:
            end = math.inf if length is None else end - length * drift
        self._extents[axis] = (start, end)
        return start, end

    def _apart(self, extent: tuple[float, float], other: Solid, axis: Vector) -> bool:
        low, high = extent
        other_low, other_high = self.solids.extent(other, axis)
        return high <= other_low or other_high <= low


def _faces(solid: Solid) -> Iterable[Vector]:
    if isinstance(solid, Box):
        return _GRID_AXES
    return (normal for normal, _ in solid.planes)


def _edges(solid: Solid) -> Sequence[Vector]:
    return _GRID_AXES if isinstance(solid, Box) else solid.directions


def _extent(solid: Solid, axis: Vector) -> tuple[int, int]:
    """The least and greatest of ``axis.dot(point)`` over a solid's points."""
    if isinstance(solid, Convex):
        return solid.extent(axis)
    low = high = 0
    for a, lo, hi in zip(axis, solid.min, solid.max, strict=True):
        low += a * (lo if a > 0 else hi)
        high += a * (hi if a > 0 else lo)
    return low, high


def _path(box: Box, leg: _Leg, reach: Box) -> Box:
    """The box around the space a box sweeps along a leg."""
    low = list((box.min + leg.offset).as_tuple())
    high = list((box.max + leg.offset).as_tuple())
    for axis, step in enumerate(leg.direction):
        if step > 0:
            far = tuple(reach.min)[axis]
            low[axis] = (
                min(low[axis], far)
                if leg.length is None
                else low[axis] - leg.length * step
            )
        elif step < 0:
            far = tuple(reach.max)[axis]
            high[axis] = (
                max(high[axis], far)
                if leg.length is None
                else high[axis] - leg.length * step
            )
    return Box(Vector(*low), Vector(*high))


def _sections(model: Model, world: World, provenance: Provenance | None) -> list[str]:
    """The function that the build script's ``build()`` called to place each element.

    An element of a component belongs where the script placed the outermost instance.
    An element that ``build()`` placed itself belongs to no section. A call stack too
    deep to keep whole belongs to its outermost kept function.
    """
    if provenance is None:
        return [""] * len(world.elements)
    sections: list[str] = []
    for element in world.elements:
        trace = provenance.trace(model, element.uid)
        source = trace.via[0].source if trace.via else trace.source
        names = [
            frame.function
            for frame in (source.frames if source is not None else ())
            if not frame.function.startswith("<") or frame.function == "<module>"
        ]
        root = next((k for k, name in enumerate(names) if name in _SCRIPT_ROOTS), None)
        if root is None:
            sections.append(names[-1] if names else "")
        else:
            sections.append(names[root - 1] if root else "")
    return sections


@dataclass(frozen=True, slots=True)
class _Footprint:
    """A unit's extent across, as plain integers for the scheduler's inner loop."""

    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return max(self.x1 - self.x0, self.y1 - self.y0)


class _Ready:
    """The units free to go on, by section and landing height, in a grid across."""

    def __init__(self) -> None:
        # levels[section][z]: every ready unit; cells[section][z][cell]: narrow ones.
        self.levels: defaultdict[str, defaultdict[int, set[int]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self.cells: defaultdict[
            str, defaultdict[int, defaultdict[tuple[int, int], set[int]]]
        ] = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
        self.wide: defaultdict[str, defaultdict[int, set[int]]] = defaultdict(
            lambda: defaultdict(set)
        )

    @staticmethod
    def cell(footprint: _Footprint) -> tuple[int, int]:
        return footprint.x0 // STEP_SPAN, footprint.y0 // STEP_SPAN

    def add(self, section: str, z: int, u: int, footprint: _Footprint) -> None:
        self.levels[section][z].add(u)
        if footprint.width > STEP_SPAN:
            self.wide[section][z].add(u)
        else:
            self.cells[section][z][self.cell(footprint)].add(u)

    def remove(self, section: str, z: int, u: int, footprint: _Footprint) -> None:
        self.levels[section][z].discard(u)
        self.wide[section][z].discard(u)
        self.cells[section][z][self.cell(footprint)].discard(u)

    def heights(self, section: str) -> list[int]:
        levels = self.levels[section]
        for z in [z for z, members in levels.items() if not members]:
            del levels[z]
        return sorted(levels)

    def near(
        self, section: str, z: int, low: tuple[int, int], high: tuple[int, int]
    ) -> Iterator[int]:
        """The ready units at one height whose minimum corner may lie in a range."""
        yield from self.wide[section][z]
        cells = self.cells[section][z]
        for cx in range(low[0] // STEP_SPAN, high[0] // STEP_SPAN + 1):
            for cy in range(low[1] // STEP_SPAN, high[1] // STEP_SPAN + 1):
                if (cx, cy) in cells:
                    yield from cells[cx, cy]


class _Schedule:
    """Place units one by one, gathering them into steps."""

    def __init__(self, units: Sequence[_Unit], sections: Sequence[str]) -> None:
        self.units = units
        self.sections = sections
        self.footprints = [
            _Footprint(u.bounds.min.x, u.bounds.min.y, u.bounds.max.x, u.bounds.max.y)
            for u in units
        ]
        self.waiting = [len(unit.before) for unit in units]
        self.held = [unit.grounded or not unit.holders for unit in units]
        self.holds: list[list[int]] = [[] for _ in units]
        for u, unit in enumerate(units):
            for v in unit.holders:
                self.holds[v].append(u)
        self.placed = [False] * len(units)
        self.released = [False] * len(units)
        self.unplaced = set(range(len(units)))
        self.ready = _Ready()
        for u in range(len(units)):
            self._release(u)

    def run(self, limit: int) -> Instructions:
        """Place every unit; a step closes when no ready unit joins it."""
        steps: list[Step] = []
        forced: list[Forced] = []
        step: list[int] = []
        section: str | None = None
        while self.unplaced:
            u = (
                self._nearest(section, step, limit)
                if step and section is not None
                else None
            )
            if u is None:
                if step:
                    steps.append(self._step(step))
                    step = []
                if section is None or not self.ready.heights(section):
                    section = self._lowest_section()
                if section is None:
                    u = self._force()
                    first = self.units[u].members[0]
                    forced.append(Forced(first, len(steps), self._pending(u)))
                    section = self.sections[u]
                else:
                    u = self._lowest(section)
            self._place(u)
            step.append(u)
        steps.append(self._step(step))
        return Instructions(steps=tuple(steps), forced=tuple(forced))

    def _step(self, units: Sequence[int]) -> Step:
        members = tuple(i for u in units for i in self.units[u].members)
        approaches = tuple(
            self.units[u].approach for u in units for _ in self.units[u].members
        )
        return Step(members, approaches, self.sections[units[0]])

    def _release(self, u: int) -> None:
        if self.released[u] or self.placed[u] or self.waiting[u] or not self.held[u]:
            return
        self.released[u] = True
        self.ready.add(self.sections[u], self.units[u].bottom, u, self.footprints[u])

    def _place(self, u: int) -> None:
        if self.released[u]:
            self.ready.remove(
                self.sections[u], self.units[u].bottom, u, self.footprints[u]
            )
        self.placed[u] = True
        self.unplaced.discard(u)
        for v in self.units[u].after:
            self.waiting[v] -= 1
            self._release(v)
        for v in self.holds[u]:
            self.held[v] = True
            self._release(v)

    def _lowest(self, section: str) -> int:
        return min(self.ready.levels[section][self.ready.heights(section)[0]])

    def _lowest_section(self) -> str | None:
        best: tuple[int, int] | None = None
        chosen: str | None = None
        for section in list(self.ready.levels):
            heights = self.ready.heights(section)
            if not heights:
                continue
            key = (heights[0], min(self.ready.levels[section][heights[0]]))
            if best is None or key < best:
                best, chosen = key, section
        return chosen

    def _nearest(self, section: str, step: Sequence[int], limit: int) -> int | None:
        """The ready unit of the section that joins the step best, if any may."""
        size = sum(len(self.units[u].members) for u in step)
        if size >= limit:
            return None
        prints = [self.footprints[u] for u in step]
        bottoms = [self.units[u].bottom for u in step]
        x0 = min(p.x0 for p in prints)
        y0 = min(p.y0 for p in prints)
        x1 = max(p.x1 for p in prints)
        y1 = max(p.y1 for p in prints)
        reach = max(STEP_SPAN, *(p.width for p in prints))
        middle_x, middle_y = x0 + x1, y0 + y1
        best: tuple[int, int, int] | None = None
        chosen: int | None = None
        for z in self.ready.heights(section):
            if max(*bottoms, z) - min(*bottoms, z) > STEP_RISE:
                continue
            for u in self.ready.near(
                section, z, (x1 - reach, y1 - reach), (x0 + reach, y0 + reach)
            ):
                if size + len(self.units[u].members) > limit:
                    continue
                p = self.footprints[u]
                span = max(reach, p.width)
                if max(x1, p.x1) - min(x0, p.x0) > span:
                    continue
                if max(y1, p.y1) - min(y0, p.y0) > span:
                    continue
                distance = abs(p.x0 + p.x1 - middle_x) + abs(p.y0 + p.y1 - middle_y)
                key = (z, distance, u)
                if best is None or key < best:
                    best, chosen = key, u
        return chosen

    def _force(self) -> int:
        """The unplaced unit that breaks the fewest rules, lowest first."""
        return min(
            self.unplaced,
            key=lambda u: (
                self.waiting[u],
                not self.held[u],
                self.units[u].bottom,
                u,
            ),
        )

    def _pending(self, u: int) -> tuple[tuple[int, Reason], ...]:
        return tuple(
            (self.units[v].members[0], reason)
            for v, reason in sorted(self.units[u].before.items())
            if not self.placed[v]
        )


def _names(uids: Iterable[str]) -> str:
    """List up to three ids, then how many more."""
    uids = list(uids)
    shown = ", ".join(uids[:3])
    rest = len(uids) - 3
    return f"{shown} and {rest} more" if rest > 0 else shown
