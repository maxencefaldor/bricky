# Copyright 2026 Maxence Faldor
"""Instructions: the order to build a model in, a few elements per step.

Each element goes on along one direction, its approach, onto an element already placed
or onto the ground. Downward, it arrives from above the model. Sideways, it drops from
above to a stud's height away from its place, then slides in. Upward, a hand pushes it
up from a brick's height below its place.

Three rules make an order buildable with these moves:

1. Something holds each element as it goes on: the ground, or an element it presses
   onto along its approach.
2. Each connection forms as its second element goes on, so every element already
   placed that it joins lies along its approach.
3. Nothing already placed stands in its way: the space its solids sweep as they arrive.

The sweeps are exact, slopes included, since every solid is convex with integer corners.
Every step thus leaves what is built joined to the ground, and nothing floats.

Each element has a natural approach toward the ground: it rests on what lies below it
wherever it can, and otherwise goes on sideways, or hangs from what lies above. An
element that hangs, with no room below to push it up, goes on attached under the
element it hangs from, the two moving as one.

The order places elements along their natural approaches, and never closes the last
natural approach of an element still to go on. When no element can go on that way, an
element goes on along another approach the rules allow, leaving every element still to
go on at least one approach. Among the elements that may go on, the order keeps to one
section of the build script, the function that ``build()`` called, and goes bottom up.
A step takes up to six elements of its section, about one brick high and within 8 studs
of one another, nearest first.

Elements that lock one another in leave no order that follows every rule. The order
then places the element that breaks the fewest, and notes what it breaks. When some
lock in, a second order also lets elements slide in across from a side before the last
stud's height, and the order that breaks fewer rules wins.
"""

from __future__ import annotations

import heapq
import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
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

_GRID_AXES: Final = (AXES["+x"], AXES["+y"], AXES["+z"])
"""The face normals and edge directions of every box."""

_SIDES: Final = (AXES["+x"], AXES["-x"], AXES["+y"], AXES["-y"])
"""The directions elements can slide across in, level."""

_PREFERENCE: Final = (DOWN, AXES["+x"], AXES["-x"], AXES["+y"], AXES["-y"], UP)
"""The approaches in the order an element takes them, when several are open."""


class Reason(StrEnum):
    """Which rule an element placed out of order breaks."""

    WAY = "way"
    """It closes the last approach of an element still to go on."""

    BLOCKED = "blocked"
    """An element already placed stands in its way, or joins it off its approach."""


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
    """The elements involved, each with the rule the placement breaks."""

    def describe(self, uids: Sequence[str]) -> str:
        """Say what the element breaks, such as ``"e7 goes on into the way of e3"``."""
        closed = [uids[j] for j, reason in self.pending if reason is Reason.WAY]
        blocking = [uids[j] for j, reason in self.pending if reason is Reason.BLOCKED]
        clauses: list[str] = []
        if blocking:
            verb = "stands" if len(blocking) == 1 else "stand"
            clauses.append(f"though {_names(blocking)} {verb} in its way")
        if closed:
            clauses.append(f"into the way of {_names(closed)}")
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
    ways = _Ways(world)
    sections = _sections(model, world, provenance)
    best: Instructions | None = None
    # Elements first arrive from above; if that locks some in, they may also slide in
    # across from a side, and the order that breaks fewer rules wins.
    for slides in (False, True):
        units = _units(world, ways, slides=slides)
        schedule = _Schedule(units, [sections[unit.members[0]] for unit in units])
        attempt = schedule.run(elements_per_step)
        if best is None or len(attempt.forced) < len(best.forced):
            best = attempt
        if not best.forced:
            break
    assert best is not None  # noqa: S101 - the loop runs at least once
    return best


@dataclass(frozen=True, slots=True)
class _Option:
    """One approach a unit may take, with what holds it and what rules it out."""

    approach: Vector
    holders: frozenset[int]
    """The units it presses onto along the approach: one placed holds it."""

    spoilers: frozenset[int]
    """The units that rule the approach out once placed: in its way, or off its axis."""

    held: bool
    """Whether it is held from the start: grounded, or with nothing to hold onto."""

    natural: bool
    """Whether it goes on along the unit's natural approach, toward the ground."""


@dataclass(slots=True)
class _Unit:
    """Elements that go on as one: an element and those that hang under it."""

    members: list[int]
    """Element indices; the first holds the rest."""

    bounds: Box
    bottom: int
    """The bottom of the first member, where the unit lands."""

    options: tuple[_Option, ...] = ()
    """The approaches the unit may take, in order of preference."""


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


def _units(world: World, ways: _Ways, *, slides: bool) -> list[_Unit]:
    """Group elements into units, each with the approaches it may take.

    With ``slides``, each approach also lets its unit slide in across from a side.
    """
    elements = world.elements
    joins = _joins(world)
    grounded = [element.bounds.min.z == 0 for element in elements]
    toward, anchor = _anchors(joins, grounded)
    roots = _roots(joins, toward, anchor, ways)
    index_of: dict[int, int] = {}
    units: list[_Unit] = []
    for i in sorted(range(len(elements)), key=lambda i: (roots[i] != i, i)):
        top = roots[i]
        if top not in index_of:
            index_of[top] = len(units)
            bounds = elements[top].bounds
            units.append(_Unit([], bounds, bounds.min.z))
        unit = units[index_of[top]]
        unit.members.append(i)
        unit.bounds = Box.bounding((unit.bounds, elements[i].bounds))
    of = [index_of[top] for top in roots]
    for u, unit in enumerate(units):
        sides = _sides(unit.members, joins, of, u)
        on_ground = any(grounded[i] for i in unit.members)
        # Every side with something to press onto is an approach; the natural one
        # leads toward the ground along the anchor's chain.
        approaches = set(sides) | ({DOWN} if on_ground or not sides else set())
        natural = toward[unit.members[0]]
        if natural not in approaches:
            natural = DOWN
        options: list[_Option] = []
        for approach in _PREFERENCE:
            if approach not in approaches:
                continue
            off_axis = set().union(
                *(near for side, near in sides.items() if side != approach)
            )
            seen: set[frozenset[int]] = set()
            for motion in _motions(approach)[: None if slides else 1]:
                crossed = {of[j] for j in ways.crossed(unit.members, motion)}
                spoilers = frozenset((crossed | off_axis) - {u})
                if spoilers in seen:
                    continue
                seen.add(spoilers)
                options.append(
                    _Option(
                        approach,
                        frozenset(sides.get(approach, ())),
                        spoilers,
                        held=(approach == DOWN and on_ground) or not sides,
                        natural=approach == natural,
                    )
                )
        unit.options = tuple(sorted(options, key=lambda option: not option.natural))
    return units


def _sides(
    members: Iterable[int], joins: _Joins, of: Sequence[int], u: int
) -> dict[Vector, set[int]]:
    """The units that a unit's members join outside it, by the direction they lie in."""
    sides: defaultdict[Vector, set[int]] = defaultdict(set)
    for i in members:
        for direction, neighbors in joins[i].items():
            outside = {of[j] for j in neighbors if of[j] != u}
            if outside:
                sides[direction] |= outside
    return dict(sides)


def _roots(
    joins: _Joins,
    approach: Sequence[Vector],
    anchor: Sequence[int | None],
    ways: _Ways,
) -> list[int]:
    """The element each element goes on with: itself, or one it hangs from.

    A group of elements that only hangs from what lies above goes on pushed up from a
    brick's height below. When something that does not hang from the group stands
    there, the group goes on attached under the element it hangs from, before that
    goes on, and the larger group faces the same test.
    """
    count = len(approach)
    children: list[list[int]] = [[] for _ in range(count)]
    for i, above in enumerate(anchor):
        if above is not None:
            children[above].append(i)
    carrier = list(range(count))
    changed = True
    while changed:
        changed = False
        of = [_root(carrier, i) for i in range(count)]
        groups: defaultdict[int, list[int]] = defaultdict(list)
        for i, top in enumerate(of):
            groups[top].append(i)
        for top, members in groups.items():
            above = anchor[top]
            if approach[top] != UP or above is None:
                continue
            if set(_sides(members, joins, of, top)) != {UP}:
                continue
            if ways.crossed(members, _motion(UP)) - _hanging_from(children, members):
                carrier[top] = above
                changed = True
    return [_root(carrier, i) for i in range(count)]


def _root(carrier: list[int], start: int) -> int:
    """The element at the end of an element's chain of carriers."""
    path = [start]
    while carrier[path[-1]] != path[-1]:
        path.append(carrier[path[-1]])
    return path[-1]


def _hanging_from(children: Sequence[Sequence[int]], start: Iterable[int]) -> set[int]:
    """The elements that anchor through some of the given ones, and those ones."""
    found: set[int] = set()
    stack = list(start)
    while stack:
        j = stack.pop()
        if j not in found:
            found.add(j)
            stack.extend(children[j])
    return found


def _anchors(
    joins: _Joins, grounded: Sequence[bool]
) -> tuple[list[Vector], list[int | None]]:
    """Each element's approach toward the ground, and the element it goes on onto.

    Every element anchors to the ground through a chain of connections, each from an
    element to the one it goes on onto. The chain keeps to the fewest elements that
    hang under the next, then to the fewest that go on sideways, so elements rest on
    what lies below them wherever they can. Ties go to more studs, then the lower
    index. An element no chain reaches, which floats, goes on downward.
    """
    count = len(grounded)
    best: list[tuple[int, int, int, int] | None] = [
        (0, 0, 0, i) if down else None for i, down in enumerate(grounded)
    ]
    approach = [DOWN] * count
    anchor: list[int | None] = [None] * count
    done = [False] * count
    heap = [(0, 0, 0, i, i) for i, down in enumerate(grounded) if down]
    while heap:
        hanging, sideways, _, _, i = heapq.heappop(heap)
        if done[i]:
            continue
        done[i] = True
        # Whatever meets i moving along a direction goes on onto i along it.
        for direction, neighbors in joins[i].items():
            toward = -direction
            for j, studs in neighbors.items():
                if done[j]:
                    continue
                cost = (
                    hanging + int(toward == UP),
                    sideways + int(toward not in {UP, DOWN}),
                    -studs,
                    i,
                )
                known = best[j]
                if known is None or cost < known:
                    best[j] = cost
                    approach[j] = toward
                    anchor[j] = i
                    heapq.heappush(heap, (*cost, j))
    return approach, anchor


def _motion(approach: Vector) -> tuple[_Leg, ...]:
    """The first of the moves that bring elements in along an approach.

    Downward, they arrive from above. Sideways, they drop from above to a stud's height
    away, then slide in. Upward, a hand pushes them up from a brick's height below.
    """
    return _motions(approach)[0]


def _motions(approach: Vector) -> tuple[tuple[_Leg, ...], ...]:
    """Every way to bring elements in along an approach, the most direct first.

    Each way ends with the last stud's height along the approach, where studs engage.
    Before that, the elements arrive at that point from above the model, or slide in
    across from one side of it, or, sideways, straight along the approach.
    """
    back = -(approach * STUD_HEIGHT)
    engage = _Leg(ORIGIN, approach, STUD_HEIGHT)
    across = tuple((_Leg(back, side, None), engage) for side in _SIDES)
    if approach == DOWN:
        return ((_Leg(ORIGIN, DOWN, None),), *across)
    if approach == UP:
        return ((_Leg(ORIGIN, UP, BRICK),), *across)
    return ((_Leg(back, DOWN, None), engage), (_Leg(ORIGIN, approach, None),))


@dataclass(frozen=True, slots=True)
class _Leg:
    """One straight move: from ``offset`` back along ``direction`` by ``length``."""

    offset: Vector
    direction: Vector
    length: int | None
    """How far the move runs, or None for a move from beyond the model."""


class _Ways:
    """Find the elements in the way of moving elements, with a spatial index."""

    def __init__(self, world: World) -> None:
        self.elements = world.elements
        self.index: SpatialHash[int] = SpatialHash()
        for i, element in enumerate(self.elements):
            for solid in element.solids:
                self.index.insert(i, solid.bounds)
        self.reach = Box.bounding(element.bounds for element in self.elements)
        self.solids = _Solids()

    def crossed(self, moving: Iterable[int], motion: Iterable[_Leg]) -> set[int]:
        """The other elements that moving elements pass through on their way in."""
        moving = set(moving)
        found: set[int] = set()
        for leg in motion:
            for i in moving:
                for solid in self.elements[i].solids:
                    sweep = _Sweep(solid, leg, self.reach, self.solids)
                    for j in self.index.query(sweep.path):
                        if (
                            j not in moving
                            and j not in found
                            and sweep.crosses_any(self.elements[j].solids)
                        ):
                            found.add(j)
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
    """Place units one by one, gathering them into steps.

    Each unit tracks which of its approaches stay open and which are held. A unit goes
    on along its natural approach while it can, leaving every other unit its natural
    approaches. When no unit can, a unit goes on along any approach, leaving every
    other unit at least one approach. The danger counts track both conditions.
    """

    def __init__(self, units: Sequence[_Unit], sections: Sequence[str]) -> None:
        self.units = units
        self.sections = sections
        count = len(units)
        self.footprints = [
            _Footprint(u.bounds.min.x, u.bounds.min.y, u.bounds.max.x, u.bounds.max.y)
            for u in units
        ]
        self.open = [[True] * len(unit.options) for unit in units]
        self.held = [[option.held for option in unit.options] for unit in units]
        # closes[w]: the approaches that w closes once placed; holds[w]: those it holds.
        self.closes: list[list[tuple[int, int]]] = [[] for _ in units]
        self.holds: list[list[tuple[int, int]]] = [[] for _ in units]
        for v, unit in enumerate(units):
            for k, option in enumerate(unit.options):
                for w in option.spoilers:
                    self.closes[w].append((v, k))
                for w in option.holders:
                    self.holds[w].append((v, k))
        # dangers[t][w]: how many units w would leave with no open natural approach
        # (t = 0) or no open approach at all (t = 1); guarding[t][v]: the units that
        # would do that to v.
        self.dangers = ([0] * count, [0] * count)
        self.guarding: tuple[list[frozenset[int]], list[frozenset[int]]] = (
            [frozenset()] * count,
            [frozenset()] * count,
        )
        self.placed = [False] * count
        self.pooled = [False] * count
        self.unplaced = set(range(count))
        self.ready = _Ready()
        for v in range(count):
            self._guard(v)
            if any(self.held[v]):
                self._pool(v)

    def run(self, limit: int) -> Instructions:
        """Place every unit; a step closes when no unit that may go on joins it."""
        steps: list[Step] = []
        forced: list[Forced] = []
        step: list[_Placed] = []
        section: str | None = None
        while self.unplaced:
            u = (
                self._nearest(section, [placed.unit for placed in step], limit)
                if step and section is not None
                else None
            )
            if u is None:
                if step:
                    steps.append(self._step(step))
                    step = []
                section, u = self._start(section)
                if u is None:
                    u = self._force()
                    first = self.units[u].members[0]
                    forced.append(Forced(first, len(steps), self._broken(u)))
                    section = self.sections[u]
            step.append(self._place(u))
        steps.append(self._step(step))
        return Instructions(steps=tuple(steps), forced=tuple(forced))

    def _start(self, section: str | None) -> tuple[str | None, int | None]:
        """The unit that starts the next step, and its section: naturally if any can."""
        for tier in (0, 1):
            if section is not None:
                u = self._lowest(section, tier)
                if u is not None:
                    return section, u
            chosen = self._lowest_section(tier)
            if chosen is not None:
                return chosen, self._lowest(chosen, tier)
        return section, None

    def _step(self, placed: Sequence[_Placed]) -> Step:
        members = tuple(i for item in placed for i in self.units[item.unit].members)
        approaches = tuple(
            item.approach for item in placed for _ in self.units[item.unit].members
        )
        return Step(members, approaches, self.sections[placed[0].unit])

    def _may(self, u: int, tier: int = 0) -> bool:
        """Whether a unit may go on: naturally (tier 0), or along any approach (1)."""
        if self.placed[u] or self.dangers[1][u]:
            return False
        options = self.units[u].options
        if tier == 0:
            return self.dangers[0][u] == 0 and any(
                self.open[u][k] and self.held[u][k] and option.natural
                for k, option in enumerate(options)
            )
        return any(self.open[u][k] and self.held[u][k] for k in range(len(options)))

    def _guard(self, v: int) -> None:
        """Track the units that would close v's natural approaches, or all of them.

        Those units lie in the way of, or off the axis of, every approach of the kind v
        has left, so placing one before v would close them all.
        """
        options = self.units[v].options
        for tier in (0, 1):
            wanted = frozenset[int]()
            if not self.placed[v]:
                left = [
                    option.spoilers
                    for k, option in enumerate(options)
                    if self.open[v][k] and (tier == 1 or option.natural)
                ]
                if left:
                    wanted = left[0].intersection(*left[1:])
            current = self.guarding[tier][v]
            if wanted == current:
                continue
            dangers = self.dangers[tier]
            for w in current - wanted:
                dangers[w] -= 1
            for w in wanted - current:
                dangers[w] += 1
            self.guarding[tier][v] = wanted

    def _pool(self, v: int) -> None:
        if not self.pooled[v] and not self.placed[v]:
            self.pooled[v] = True
            self.ready.add(
                self.sections[v], self.units[v].bottom, v, self.footprints[v]
            )

    def _place(self, u: int) -> _Placed:
        """Place a unit along its best open, held approach, and update the others."""
        options = self.units[u].options
        k = next(
            (k for k in range(len(options)) if self.open[u][k] and self.held[u][k]),
            next((k for k in range(len(options)) if self.open[u][k]), 0),
        )
        if self.pooled[u]:
            self.ready.remove(
                self.sections[u], self.units[u].bottom, u, self.footprints[u]
            )
        self.placed[u] = True
        self.unplaced.discard(u)
        self._guard(u)
        for v, j in self.closes[u]:
            if not self.placed[v] and self.open[v][j]:
                self.open[v][j] = False
                self._guard(v)
        for v, j in self.holds[u]:
            if not self.placed[v] and not self.held[v][j]:
                self.held[v][j] = True
                self._pool(v)
        return _Placed(u, options[k].approach)

    def _lowest(self, section: str, tier: int) -> int | None:
        for z in self.ready.heights(section):
            u = min(
                (u for u in self.ready.levels[section][z] if self._may(u, tier)),
                default=None,
            )
            if u is not None:
                return u
        return None

    def _lowest_section(self, tier: int) -> str | None:
        best: tuple[int, int] | None = None
        chosen: str | None = None
        for section in list(self.ready.levels):
            u = self._lowest(section, tier)
            if u is None:
                continue
            key = (self.units[u].bottom, u)
            if best is None or key < best:
                best, chosen = key, section
        return chosen

    def _nearest(self, section: str, step: Sequence[int], limit: int) -> int | None:
        """The section's unit that joins the step best, if any goes on naturally."""
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
                if size + len(self.units[u].members) > limit or not self._may(u):
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
        """The unit to place against a rule: held if any is, then endangering fewest."""

        def key(u: int) -> tuple[bool, bool, int, int, int]:
            pairs = list(zip(self.open[u], self.held[u], strict=True))
            return (
                not any(is_open and held for is_open, held in pairs),
                not any(held for _, held in pairs),
                self.dangers[1][u],
                self.units[u].bottom,
                u,
            )

        return min(self.unplaced, key=key)

    def _broken(self, u: int) -> tuple[tuple[int, Reason], ...]:
        """The elements whose rules placing a unit now breaks, each with the rule."""
        units = self.units
        broken: dict[int, Reason] = {}
        options = units[u].options
        usable = [k for k in range(len(options)) if self.open[u][k] and self.held[u][k]]
        if not usable:
            # Its held approaches are closed: what closed the best one is in its way.
            held = [k for k in range(len(options)) if self.held[u][k]] or [0]
            for w in sorted(options[held[0]].spoilers):
                if self.placed[w]:
                    broken.setdefault(units[w].members[0], Reason.BLOCKED)
        for v in range(len(units)):
            if not self.placed[v] and u in self.guarding[1][v]:
                broken.setdefault(units[v].members[0], Reason.WAY)
        return tuple(sorted(broken.items()))


@dataclass(frozen=True, slots=True)
class _Placed:
    """A unit as it went on, along one approach."""

    unit: int
    approach: Vector


def _names(uids: Iterable[str]) -> str:
    """List up to three ids, then how many more."""
    uids = list(uids)
    shown = ", ".join(uids[:3])
    rest = len(uids) - 3
    return f"{shown} and {rest} more" if rest > 0 else shown
