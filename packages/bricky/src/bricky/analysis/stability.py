# Copyright 2026 Maxence Faldor
"""Stability: whether a model stands under its own weight, and how hard its studs pull.

The analysis treats every element as a rigid body that weighs its volume times a
density. Forces act only where elements touch, and where they touch the ground:

- A face presses on a face it rests against when the two face up and down, since weight
  closes any gap. Faces that face sideways press only when each is the top or bottom of
  its part or holds the part's studs or anti-studs: the sides of LEGO® parts stand
  0.1 mm in from the grid, so neighbors' sides never touch.
- Faces that no stud joins also rub, with friction, inscribed in a pyramid.
- A stud bears any sideways force, and resists pulling out of its anti-stud up to its
  clutch. A stud alone between two bodies also resists twisting, up to its clutch at its
  2.4 mm radius; studs that share a seat resist any twist as a couple.
- The ground, the plane z = 0, presses up wherever an element reaches it, with friction.

A body stands still when some set of these forces balances its weight: the forces and
torques on it sum to zero. Finding such forces is a linear program, the lower bound of
limit analysis that masonry and LEGO® studies use (Whiting et al., 2009; Liu et al.,
"StableLego", 2024).

The first program groups the elements that studs join, since studs that grip without
limit hold them rigidly, and asks HiGHS for the smallest push that holds every group
still. When a push is needed, the program's dual is a motion of the groups that fall.

The second program holds the falling groups and keeps the most loaded stud at the least
share of its clutch. Clarabel, an interior point solver, finds near-optimal forces in a
few seconds; when they keep every stud within the threshold, they settle the question.
Otherwise HiGHS turns them into an exact vertex by crossover, and the simplex method
takes the rounds from there. The studs that set the share form sites, one for each
motion of the dual that pulls them out. The next round lets those studs hold without
limit, and the rounds go on until the share falls within the threshold.

Where elements touch and where studs sit comes from :mod:`bricky.analysis.contacts`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

import highspy
import numpy as np
from clarabel import (
    DefaultSettings,
    DefaultSolver,
    NonnegativeConeT,
    SolverStatus,
    ZeroConeT,
)
from scipy.sparse import csc_array, eye_array, hstack, vstack

from bricky.analysis.contacts import (
    Contact,
    Faces,
    Joint,
    adjacency,
    face_contacts,
    ground_contacts,
    reach,
    stud_clusters,
    stud_joints,
    touching_groups,
)
from bricky.analysis.context import Context
from bricky.analysis.world import PlacedElement
from bricky.errors import BrickyError
from bricky.geometry import Box, Vector
from bricky.settings import Settings
from bricky.units import MM_PER_UNIT, STUD, STUD_DIAMETER

GRAVITY: Final = 9.80665
"""Standard gravity, in meters per second squared."""

_CUBIC_CENTIMETERS: Final = (MM_PER_UNIT / 10) ** 3
"""Cubic centimeters in a cubic base unit."""

_RADIUS: Final = STUD_DIAMETER / 2 / STUD
"""A stud's radius in studs, the length unit of the programs."""

_HELD: Final = 1e-6
"""Share of the weight below which a push, or a miss of the balance, counts as none."""

_MOVING: Final = 1e-6
"""Share of the fastest speed, in the dual of a program, below which a body stays
still."""

_TIE: Final = 1e-9
"""Cost of each millinewton of force for Clarabel, which keeps the forces bounded."""

_MAX_SITES: Final = 16
"""Sites found at most; the rounds stop once they reach it."""

_BINDING: Final = 1e-7
"""Dual value, as a share of all, below which a stud's limit sets no load."""


@dataclass(frozen=True, slots=True)
class Material:
    """What the analysis assumes about elements, studs and faces."""

    clutch: float
    """Newtons that pull one stud out of its anti-stud."""

    friction: float
    """Coefficient of friction between faces that press together."""

    density: float
    """Grams per cubic centimeter of an element's body, its hollows averaged in."""

    @classmethod
    def of(cls, settings: Settings) -> Material:
        """Return the material that settings describe."""
        return cls(
            clutch=settings.clutch, friction=settings.friction, density=settings.density
        )


@dataclass(frozen=True, slots=True)
class Site:
    """Studs that need a share of their clutch for any forces to hold the model."""

    load: float
    """The share: no forces hold the model with every stud of the site below it."""

    joints: tuple[Joint, ...]
    """The studs, in their anti-studs."""

    @property
    def elements(self) -> tuple[int, ...]:
        """Indices of the elements the studs join, in order."""
        return tuple(
            sorted({i for joint in self.joints for i in (joint.stud, joint.anti_stud)})
        )


@dataclass(frozen=True, slots=True)
class Stability:
    """What holds a model still, and what does not."""

    falls: tuple[tuple[int, ...], ...]
    """Groups of touching elements that move under their weight, however firmly studs
    grip, each as indices into :attr:`World.elements`."""

    sites: tuple[Site, ...]
    """Sites that need more than the threshold asked, most loaded first."""


def analyze_stability(
    context: Context, material: Material, *, threshold: float | None = 1.0
) -> Stability:
    """Find the elements that fall and the sites that need more than ``threshold``.

    The analysis covers the elements that a chain of contacts and studs joins to the
    ground; the rest float, as the connectivity pass reports. A ``threshold`` of
    ``None`` skips the search for sites, the slow part, and finds only what falls.

    Raises:
        BrickyError: If HiGHS finds no optimal forces.
    """
    elements = context.world.elements
    faces = [Faces.of(element) for element in elements]
    contacts = [
        *ground_contacts(faces),
        *face_contacts(elements, faces, context.solid_index),
    ]
    joints = list(stud_joints(elements, context.anti_studs))
    links = adjacency(len(elements), contacts, joints)
    grounded = {contact.second for contact in contacts if contact.first is None}
    standing = sorted(reach(grounded, links, set(range(len(elements)))))
    if not standing:
        return Stability(falls=(), sites=())
    clusters = stud_clusters(standing, joints)
    rigid = _Statics(elements, clusters, contacts, joints, material, held=None)
    moving = {i for k in rigid.moving() for i in clusters[k]}
    falls = touching_groups(moving, links)
    if threshold is None:
        return Stability(falls=falls, sites=())
    held = [k for k, i in enumerate(standing) if i in moving]
    single = [(i,) for i in standing]
    statics = _Statics(elements, single, contacts, joints, material, held=held)
    return Stability(falls=falls, sites=statics.sites(threshold))


type _Seat = tuple[int, int, Vector]
"""Where two bodies meet: the two, in order, and the axis of their faces' normal."""

type _Entries = tuple[np.ndarray, np.ndarray, np.ndarray]
"""Entries of a sparse matrix: values, rows and columns."""


def _mass(element: PlacedElement) -> tuple[float, tuple[float, float, float]]:
    """Return the volume of an element's body and its center, in base units."""
    six_volume = 0
    moment = Vector(0, 0, 0)
    for solid in element.solids:
        if isinstance(solid, Box):
            volume = 6 * solid.volume
            six_volume += volume
            moment += (solid.min + solid.max) * (2 * volume)
            continue
        apex = solid.vertices[0]
        for face in solid.faces:
            first = solid.vertices[face[0]]
            for k in range(1, len(face) - 1):
                second, third = solid.vertices[face[k]], solid.vertices[face[k + 1]]
                volume = (first - apex).dot((second - apex).cross(third - apex))
                six_volume += volume
                moment += (apex + first + second + third) * volume
    scale = 4 * six_volume
    return six_volume / 6, (moment.x / scale, moment.y / scale, moment.z / scale)


def _joint_key(joint: Joint) -> tuple[int, int, tuple[int, int, int]]:
    return joint.stud, joint.anti_stud, joint.position.as_tuple()


def _across(normals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return two unit vectors across each unit normal, on grid axes if they can be."""
    axes = np.eye(3)[np.argmin(np.abs(normals), axis=1)]
    first = np.cross(normals, axes)
    first /= np.linalg.norm(first, axis=1, keepdims=True)
    return first, np.cross(normals, first)


def _units(vectors: Sequence[Vector]) -> np.ndarray:
    """Return integer vectors as unit vectors, one per row."""
    array = np.array([vector.as_tuple() for vector in vectors], dtype=float)
    return array / np.linalg.norm(array, axis=1, keepdims=True)


class _Statics:
    """The balance of rigid bodies, as linear equations in unknown forces.

    A body is one element, or a group of elements whose studs grip without limit.
    Lengths are in studs and forces in millinewtons, so the numbers stay near one.
    Each body has six equations: forces along x, y and z, and torques about its center
    of mass. Each column is an unknown force or torque, with its bounds.

    Faces that studs join need no friction, since the studs bear any sideways force.
    Two or more studs in one seat also resist any twist as a couple, at no cost to their
    clutch, so only a stud alone in its seat twists with its clutch.
    """

    def __init__(  # noqa: PLR0913 - the parts of one program
        self,
        elements: Sequence[PlacedElement],
        bodies: Sequence[Sequence[int]],
        contacts: Sequence[Contact],
        joints: Sequence[Joint],
        material: Material,
        *,
        held: Iterable[int] | None,
    ) -> None:
        """Write the equations of the bodies.

        Each body in ``held`` gets an upward push at its center of mass, or every body
        when ``held`` is ``None``.
        """
        self._members = bodies
        self._body = np.full(len(elements), -1)
        for k, members in enumerate(bodies):
            self._body[list(members)] = k
        self._centers, self._weights = self._masses(elements, material.density)
        self._clutch = material.clutch * 1000
        self._values: list[np.ndarray] = []
        self._rows: list[np.ndarray] = []
        self._columns: list[np.ndarray] = []
        self._free: list[np.ndarray] = []
        self._count = 0
        self._joints = [
            joint
            for joint in joints
            if self._body[joint.stud] >= 0
            and self._body[joint.stud] != self._body[joint.anti_stud]
        ]
        seats = Counter(
            self._seat(joint.stud, joint.anti_stud, joint.normal)
            for joint in self._joints
        )
        self._press(contacts, seats, material.friction)
        self._uses = self._hold(seats)
        self._links: list[set[int]] = [set() for _ in bodies]
        pairs = [(c.first, c.second) for c in contacts if c.first is not None]
        pairs += [(joint.stud, joint.anti_stud) for joint in self._joints]
        for first, second in pairs:
            a, b = int(self._body[first]), int(self._body[second])
            if a >= 0 and b >= 0 and a != b:
                self._links[a].add(b)
                self._links[b].add(a)
        pushed = (
            np.arange(len(bodies))
            if held is None
            else np.array(sorted(held), dtype=int)
        )
        self._held = pushed
        self._push = self._add(len(pushed))
        self._force(
            self._push,
            pushed,
            self._centers[pushed],
            np.tile([0.0, 0.0, 1.0], (len(pushed), 1)),
        )

    def moving(self) -> set[int]:
        """Return the bodies that fall, from the smallest push that holds them all.

        The dual of the program is a motion of the bodies that gravity drives as hard
        as it can, and the bodies that move are those that fall.
        """
        cost = np.zeros(self._count)
        cost[self._push] = 1
        highs = self._highs(cost)
        _run(highs)
        solution = highs.getSolution()
        forces = np.asarray(solution.col_value)
        if forces[self._push].sum() <= _HELD * self._weights.sum():
            return set()
        motion = np.asarray(solution.row_dual)
        speeds = np.abs(motion.reshape(-1, 6)).max(axis=1)
        return {int(k) for k in np.flatnonzero(speeds > _MOVING * speeds.max())}

    def sites(self, threshold: float) -> tuple[Site, ...]:
        """Return the sites that need more than ``threshold``, most loaded first.

        Each round finds the least load that the most loaded stud can keep to, and the
        studs that set it. The next round lets those studs hold without limit, so each
        site's load holds however much the sites before it hold. The pushes hold up
        the bodies that fall anyway, at no cost, and their studs use no clutch.
        """
        held = set(self._held.tolist())
        rows = np.array(
            [
                k
                for k, joint in enumerate(self._joints)
                if self._body[joint.stud] not in held
                and self._body[joint.anti_stud] not in held
            ],
            dtype=int,
        )
        if not len(rows):
            return ()
        load = self._count
        joint_of, use_columns, use_values = self._uses
        place = np.full(len(self._joints), -1)
        place[rows] = np.arange(len(rows))
        kept = place[joint_of] >= 0
        limits = (
            np.concatenate([use_values[kept], -np.ones(len(rows))]),
            np.concatenate([place[joint_of[kept]], np.arange(len(rows))]),
            np.concatenate([use_columns[kept], np.full(len(rows), load)]),
        )
        cost = np.zeros(load + 1)
        cost[load] = 1
        start = self._interior(cost, limits)
        if start is not None and start[load] <= threshold:
            return ()
        highs = self._highs(cost, limits)
        if start is not None:
            # Crossover moves Clarabel's forces to a vertex, an optimal basis that the
            # simplex method starts each round from. Should it fail, the first round
            # solves from scratch.
            near = highspy.HighsSolution()
            near.col_value = start
            near.value_valid = True
            highs.crossover(near)
        equations = 6 * len(self._members)
        found: list[Site] = []
        while len(found) < _MAX_SITES:
            _run(highs)
            solution = highs.getSolution()
            share = float(solution.col_value[load])
            if share <= threshold:
                break
            duals = -np.asarray(solution.row_dual)[equations:]
            binding = np.flatnonzero(duals > _BINDING)
            if not len(binding):
                break
            motion = np.asarray(solution.row_dual)[:equations]
            setting = [self._joints[rows[k]] for k in binding]
            found.extend(
                Site(share, tuple(sorted(group, key=_joint_key)))
                for group in self._mechanisms(setting, motion)
            )
            for row in equations + binding:
                highs.changeRowBounds(int(row), -highspy.kHighsInf, highspy.kHighsInf)
        return tuple(found[:_MAX_SITES])

    def _mechanisms(self, joints: list[Joint], motion: np.ndarray) -> list[list[Joint]]:
        """Split the studs that set a load by the motions that pull them out.

        The dual of the program moves some bodies and pulls out the studs that set the
        load. Bodies that move and touch move together, and the studs they pull out
        form one site.
        """
        speeds = np.abs(motion.reshape(-1, 6)).max(axis=1)
        moving = set(np.flatnonzero(speeds > _MOVING * speeds.max()).tolist())
        parent = {body: body for body in moving}

        def root(body: int) -> int:
            while parent[body] != body:
                parent[body] = parent[parent[body]]
                body = parent[body]
            return body

        for body in moving:
            for other in self._links[body] & moving:
                parent[root(other)] = root(body)
        grouped: dict[int, list[Joint]] = {}
        for joint in joints:
            ends = [int(self._body[joint.stud]), int(self._body[joint.anti_stud])]
            movers = [end for end in ends if end in moving] or ends[:1]
            for end in movers:
                parent.setdefault(end, end)
            for end in movers[1:]:
                parent[root(end)] = root(movers[0])
        for joint in joints:
            ends = [int(self._body[joint.stud]), int(self._body[joint.anti_stud])]
            first = next((end for end in ends if end in moving), ends[0])
            grouped.setdefault(root(first), []).append(joint)
        return sorted(
            grouped.values(),
            key=lambda group: min(min(j.stud, j.anti_stud) for j in group),
        )

    def _masses(
        self, elements: Sequence[PlacedElement], density: float
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return each body's center of mass, in studs, and its weight."""
        centers, weights = [], []
        for members in self._members:
            masses = [_mass(elements[i]) for i in members]
            volumes = np.array([volume for volume, _ in masses])
            middles = np.array([center for _, center in masses])
            centers.append(volumes @ middles / volumes.sum() / STUD)
            weights.append(volumes.sum() * _CUBIC_CENTIMETERS * density * GRAVITY)
        return np.array(centers), np.array(weights)

    def _seat(self, first: int, second: int, normal: Vector) -> _Seat:
        """Return where two elements meet: their bodies, in order, and the axis."""
        a, b = int(self._body[first]), int(self._body[second])
        axis = -normal if next(c for c in normal if c) < 0 else normal
        return min(a, b), max(a, b), axis

    def _add(self, count: int, *, free: bool = False) -> np.ndarray:
        """Add ``count`` columns, free or not negative; return their indices."""
        columns = np.arange(self._count, self._count + count)
        self._count += count
        self._free.append(np.full(count, free))
        return columns

    def _force(
        self,
        columns: np.ndarray,
        bodies: np.ndarray,
        points: np.ndarray,
        directions: np.ndarray,
    ) -> None:
        """Let each column be a unit force along a direction, at a point, on a body."""
        torques = np.cross(points - self._centers[bodies], directions)
        self._values.append(np.hstack([directions, torques]).ravel())
        self._rows.append((6 * bodies[:, None] + np.arange(6)).ravel())
        self._columns.append(np.repeat(columns, 6))

    def _torque(
        self, columns: np.ndarray, bodies: np.ndarray, axes: np.ndarray
    ) -> None:
        """Let each column be a unit torque about an axis, on a body."""
        self._values.append(axes.ravel())
        self._rows.append((6 * bodies[:, None] + np.arange(3, 6)).ravel())
        self._columns.append(np.repeat(columns, 3))

    def _press(
        self, contacts: Sequence[Contact], seats: Counter[_Seat], friction: float
    ) -> None:
        """Add the forces with which faces press on faces, and on the ground.

        Faces that studs join press along their normal, since the studs bear any
        sideways force; other faces rub, with friction.
        """
        rubbing: list[Contact] = []
        pressing: list[Contact] = []
        for contact in contacts:
            second = self._body[contact.second]
            if second < 0:
                continue
            if contact.first is None:
                rubbing.append(contact)
            elif self._body[contact.first] != second:
                seat = self._seat(contact.first, contact.second, contact.normal)
                (pressing if seats[seat] else rubbing).append(contact)
        if pressing:
            self._corners(pressing, 0.0)
        if rubbing:
            self._corners(rubbing, friction)

    def _corners(self, contacts: Sequence[Contact], friction: float) -> None:
        """Add forces at the corners of contacts, along their normals.

        With friction, four forces at each corner span it along two axes across the
        normal: the friction cone, inscribed in a pyramid.
        """
        corners = [len(contact.points) for contact in contacts]
        normals = np.repeat(_units([c.normal for c in contacts]), corners, axis=0)
        points = np.array(
            [point for contact in contacts for point in contact.points], dtype=float
        )
        first = np.repeat(
            [-1 if c.first is None else c.first for c in contacts], corners
        )
        second = np.repeat([c.second for c in contacts], corners)
        directions = normals
        if friction:
            across = _across(normals)
            spans = [
                normals + friction * across[0],
                normals - friction * across[0],
                normals + friction * across[1],
                normals - friction * across[1],
            ]
            directions = np.stack(spans, axis=1).reshape(-1, 3)
            points, first, second = (
                np.repeat(array, len(spans), axis=0)
                for array in (points, first, second)
            )
        points /= STUD
        columns = self._add(len(directions))
        self._force(columns, self._body[second], points, directions)
        pushed = first >= 0
        self._force(
            columns[pushed],
            self._body[first[pushed]],
            points[pushed],
            -directions[pushed],
        )

    def _hold(self, seats: Counter[_Seat]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Add the forces with which studs hold their anti-studs.

        Each stud pulls on its own. The studs of one seat bear one sideways force
        between them, and a free twist when two or more share it, as a couple. A stud
        alone in its seat twists with its clutch.

        Return what uses each stud's clutch: the stud's index, the column and the share
        of the clutch a unit of it uses.
        """
        joints = self._joints
        count = len(joints)
        if not count:
            empty = np.zeros(0, dtype=int)
            return empty, empty, np.zeros(0)
        axes = _units([joint.normal for joint in joints])
        points = np.array([joint.position.as_tuple() for joint in joints]) / STUD
        holders = self._body[[joint.stud for joint in joints]]
        held = self._body[[joint.anti_stud for joint in joints]]
        pull = self._add(count)
        self._force(pull, held, points, -axes)
        self._force(pull, holders, points, axes)
        keys = [self._seat(j.stud, j.anti_stud, j.normal) for j in joints]
        firsts: dict[_Seat, int] = {}
        for k, key in enumerate(keys):
            firsts.setdefault(key, k)
        leaders = np.array(sorted(firsts.values()), dtype=int)
        for across in _across(axes[leaders]):
            bear = self._add(len(leaders), free=True)
            self._force(bear, held[leaders], points[leaders], across)
            self._force(bear, holders[leaders], points[leaders], -across)
        counts = np.array([seats[keys[k]] for k in leaders])
        shared = leaders[counts > 1]
        couple = self._add(len(shared), free=True)
        self._torque(couple, held[shared], axes[shared])
        self._torque(couple, holders[shared], -axes[shared])
        alone = leaders[counts == 1]
        uses = [(np.arange(count), pull, np.full(count, 1 / self._clutch))]
        for sign in (1.0, -1.0):
            twist = self._add(len(alone))
            self._torque(twist, held[alone], sign * axes[alone])
            self._torque(twist, holders[alone], -sign * axes[alone])
            share = 1 / (_RADIUS * self._clutch)
            uses.append((alone, twist, np.full(len(alone), share)))
        joint_of, columns, values = (
            np.concatenate([use[k] for use in uses]) for k in range(3)
        )
        return joint_of, columns, values

    def _equations(
        self, width: int, limits: _Entries | None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
        """Return the equations, then the limits, as compressed columns, and their rows.

        The equations come first, one row each, then each limit, one row each.
        """
        equations = 6 * len(self._members)
        values = [*self._values]
        rows = [*self._rows]
        columns = [*self._columns]
        count = equations
        if limits is not None:
            values.append(limits[0])
            rows.append(limits[1] + equations)
            columns.append(limits[2])
            count += int(limits[1].max()) + 1
        value, row, column = (np.concatenate(part) for part in (values, rows, columns))
        nonzero = value != 0
        value, row, column = value[nonzero], row[nonzero], column[nonzero]
        order = np.lexsort((row, column))
        starts = np.searchsorted(column[order], np.arange(width + 1))
        return starts, row[order], value[order], count

    def _balance(self) -> np.ndarray:
        """Return what each equation sums to: each body's weight, upward."""
        balance = np.zeros(6 * len(self._members))
        balance[2::6] = self._weights
        return balance

    def _highs(self, cost: np.ndarray, limits: _Entries | None = None) -> highspy.Highs:
        """Return HiGHS loaded with the balance, the limits and the cost."""
        width = len(cost)
        starts, index, value, count = self._equations(width, limits)
        balance = self._balance()
        free = np.zeros(width, dtype=bool)
        free[: self._count] = np.concatenate(self._free)
        program = highspy.HighsLp()
        program.num_col_ = width
        program.num_row_ = count
        program.col_cost_ = cost
        program.col_lower_ = np.where(free, -highspy.kHighsInf, 0.0)
        program.col_upper_ = np.full(width, highspy.kHighsInf)
        limited = count - len(balance)
        program.row_lower_ = np.concatenate(
            [balance, np.full(limited, -highspy.kHighsInf)]
        )
        program.row_upper_ = np.concatenate([balance, np.zeros(limited)])
        program.a_matrix_.format_ = highspy.MatrixFormat.kColwise
        program.a_matrix_.start_ = starts
        program.a_matrix_.index_ = index
        program.a_matrix_.value_ = value
        highs = highspy.Highs()
        highs.silent()
        highs.setOptionValue("threads", 1)
        highs.setOptionValue("solver", "simplex")
        highs.setOptionValue("simplex_strategy", 4)
        highs.passModel(program)
        return highs

    def _interior(self, cost: np.ndarray, limits: _Entries) -> np.ndarray | None:
        """Return forces that balance every body, from Clarabel, or ``None``.

        Clarabel's interior point method finds near-optimal forces much faster than the
        simplex method. Its last column is set to the largest share of clutch that any
        stud uses, so the forces settle whether every stud keeps within a threshold, and
        they give the simplex method a start. Each free column splits into two that
        cannot go negative, and every column costs a little, so the forces stay bounded
        where the cost leaves them free. Return ``None`` when Clarabel finds no forces
        or when they miss a balance by more than a millionth of the heaviest weight.
        """
        width = len(cost)
        starts, index, value, count = self._equations(width, limits)
        matrix = csc_array((value, index, starts), shape=(count, width))
        free = np.flatnonzero(np.concatenate(self._free))
        split = hstack([matrix, -matrix[:, free]], format="csc")
        size = split.shape[1]
        stacked = vstack([split, -eye_array(size, format="csc")], format="csc")
        balance = self._balance()
        targets = np.concatenate([balance, np.zeros(stacked.shape[0] - len(balance))])
        prices = np.concatenate([cost, np.zeros(len(free))]) + _TIE
        cones = [
            ZeroConeT(len(balance)),
            NonnegativeConeT(stacked.shape[0] - len(balance)),
        ]
        settings = DefaultSettings()
        settings.verbose = False
        settings.iterative_refinement_max_iter = 50
        settings.iterative_refinement_reltol = 1e-15
        settings.iterative_refinement_abstol = 1e-15
        solution = DefaultSolver(
            csc_array((size, size)), prices, stacked, targets, cones, settings
        ).solve()
        if solution.status != SolverStatus.Solved:
            return None
        values = np.asarray(solution.x)
        forces = values[:width].copy()
        forces[free] -= values[width:]
        bounded = np.flatnonzero(~np.concatenate(self._free))
        forces[bounded] = np.maximum(forces[bounded], 0.0)
        forces[-1] = 0.0
        forces[-1] = max(0.0, float((matrix[len(balance) :] @ forces).max()))
        miss = np.abs(matrix[: len(balance)] @ forces - balance).max()
        return forces if miss <= _HELD * balance.max() else None


def _run(highs: highspy.Highs) -> None:
    """Solve the program in HiGHS.

    Raises:
        BrickyError: If HiGHS finds no optimal solution.
    """
    highs.run()
    status = highs.getModelStatus()
    if status != highspy.HighsModelStatus.kOptimal:
        message = f"the stability analysis failed: HiGHS stopped with {status.name}"
        raise BrickyError(message)
