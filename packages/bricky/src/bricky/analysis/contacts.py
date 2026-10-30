# Copyright 2026 Maxence Faldor
"""Contacts: where elements press on one another and on the ground, and where studs sit.

The solids of each element give faces, each in a plane with an integer normal. Two faces
press where they lie in one plane, face each other and share some area. Faces that face
up and down press, since weight closes any gap. Faces that face sideways press only
where each is the top or bottom of its part or holds its studs or anti-studs: the sides
of LEGO® parts stand 0.1 mm in from the grid, so neighbors' sides never touch. The area
two faces share is a polygon with exact rational corners. The ground presses on every
element that reaches z = 0, at its lowest corners. A joint is one stud in another
element's anti-stud.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from bricky.analysis.connections import AntiStudIndex
from bricky.analysis.spatial import SpatialHash
from bricky.analysis.world import PlacedElement
from bricky.catalog import ConnectorKind
from bricky.geometry import DOWN, UP, Box, Vector
from bricky.units import STUD_DIAMETER, STUD_HEIGHT

_ONE: Final = Vector(1, 1, 1)

type _Corners = tuple[tuple[int, int, int], ...]
type _Plane = tuple[Vector, int]
type _Point = tuple[Fraction, Fraction, Fraction]


@dataclass(frozen=True, slots=True)
class Joint:
    """One stud of an element in an anti-stud of another."""

    stud: int
    """Index into :attr:`World.elements` of the element with the stud."""

    anti_stud: int
    """Index into :attr:`World.elements` of the element with the anti-stud."""

    position: Vector
    """The stud's center, on its face."""

    normal: Vector
    """The stud's outward axis."""

    @property
    def bounds(self) -> Box:
        """The box the stud occupies as it stands out of its face."""
        radius = STUD_DIAMETER // 2
        side = Vector(*(0 if component else radius for component in self.normal))
        tip = self.position + self.normal * STUD_HEIGHT
        return Box.spanning(self.position - side, tip + side)


@dataclass(frozen=True, slots=True)
class Faces:
    """The faces of an element's solids that can press on other elements' faces."""

    faces: dict[_Plane, list[tuple[_Corners, bool]]]
    """Each face by plane, counter-clockwise seen from outside, and whether it bears:
    whether it is the top or bottom of its part, or holds the part's studs or
    anti-studs. Faces that neither bear nor face up or down never press."""

    lowest: tuple[tuple[int, int, int], ...]
    """The corners at the element's lowest height, when that reaches the ground."""

    @classmethod
    def of(cls, element: PlacedElement) -> Faces:
        """Return the faces of an element, and where it reaches the ground."""
        axis = element.pose.rotation.apply(UP)
        holders = {
            (connector.normal, connector.normal.dot(connector.position))
            for connector in element.connectors
        }
        faces: defaultdict[_Plane, list[tuple[_Corners, bool]]] = defaultdict(list)
        corners: set[tuple[int, int, int]] = set()
        for solid in element.solids:
            vertices = [vertex.as_tuple() for vertex in solid.vertices]
            corners.update(vertices)
            for face, plane in zip(solid.faces, solid.planes, strict=True):
                bears = plane[0] in (axis, -axis) or plane in holders
                if bears or plane[0] in (UP, DOWN):
                    faces[plane].append((tuple(vertices[k] for k in face), bears))
        low = element.bounds.min.z
        lowest = tuple(sorted(c for c in corners if c[2] == low)) if low <= 0 else ()
        return cls(dict(faces), lowest)


@dataclass(frozen=True, slots=True)
class Contact:
    """Faces that press together over a polygon: ``first`` pushes ``second``."""

    first: int | None
    """The element on the far side of the normal, or ``None`` for the ground."""

    second: int
    normal: Vector
    """The normal of ``first``'s face, pointing into ``second``."""

    points: tuple[tuple[int | Fraction, ...], ...]
    """The corners of the polygon where the faces touch, in base units."""


def ground_contacts(faces: Sequence[Faces]) -> Iterator[Contact]:
    """Yield where elements reach the ground, at their lowest corners."""
    for i, element in enumerate(faces):
        if element.lowest:
            yield Contact(None, i, UP, element.lowest)


def face_contacts(
    elements: Sequence[PlacedElement],
    faces: Sequence[Faces],
    index: SpatialHash[int],
) -> Iterator[Contact]:
    """Yield where faces of two elements press together over some area.

    Faces press when they face up or down, since weight closes any gap between them,
    or when both bear: the sides of parts stand 0.1 mm in from the grid, so neighbors'
    sides never touch.
    """
    for i, element in enumerate(elements):
        grown = Box(element.bounds.min - _ONE, element.bounds.max + _ONE)
        for j in sorted(index.query(grown)):
            if j <= i:
                continue
            for (normal, offset), mine in faces[i].faces.items():
                level = normal in (UP, DOWN)
                for first, bears in mine:
                    for second, too in faces[j].faces.get((-normal, -offset), ()):
                        if level or (bears and too):
                            points = _overlap(first, second, normal)
                            if points:
                                yield Contact(i, j, normal, points)


def _overlap(
    first: _Corners, second: _Corners, normal: Vector
) -> tuple[tuple[int | Fraction, ...], ...]:
    """Return the corners of the area two faces share, or nothing when they share none.

    The faces lie in one plane, ``first`` counter-clockwise seen from where ``normal``
    points and ``second`` the other way round. The face with fewer corners clips the
    other.
    """
    first_low, first_high = _span(first)
    second_low, second_high = _span(second)
    low = tuple(map(max, first_low, second_low))
    high = tuple(map(min, first_high, second_high))
    if any(
        a > b or (a == b and not component)
        for a, b, component in zip(low, high, normal, strict=True)
    ):
        return ()
    if _rectangle(first, normal) and _rectangle(second, normal):
        return tuple(
            dict.fromkeys(
                tuple(high[k] if (corner >> k) & 1 else low[k] for k in range(3))
                for corner in range(8)
            )
        )
    subject, clipper = first, tuple(reversed(second))
    if len(clipper) > len(subject):
        subject, clipper = clipper, subject
    polygon: list[_Point] = [_exact(corner) for corner in subject]
    edges = [Vector(*corner) for corner in clipper]
    for start, end in zip(edges, [*edges[1:], edges[0]], strict=True):
        polygon = _clip(polygon, normal.cross(end - start), start)
        if not polygon:
            return ()
    if sum(a * b for a, b in zip(_newell(polygon), normal, strict=True)) <= 0:
        return ()
    return tuple(dict.fromkeys(polygon))


def _span(corners: _Corners) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return the lowest and highest coordinates of some corners on each axis."""
    low = tuple(min(corner[k] for corner in corners) for k in range(3))
    high = tuple(max(corner[k] for corner in corners) for k in range(3))
    return low, high


def _rectangle(corners: _Corners, normal: Vector) -> bool:
    """Return whether a face is a rectangle along grid axes."""
    if len(corners) != 4 or sum(map(abs, normal)) != 1:  # noqa: PLR2004 - four corners
        return False
    low, high = _span(corners)
    return len(set(corners)) == 4 and all(  # noqa: PLR2004 - four corners
        value in (low[k], high[k])
        for corner in corners
        for k, value in enumerate(corner)
    )


def _clip(polygon: list[_Point], inward: Vector, start: Vector) -> list[_Point]:
    """Keep the part of a polygon on the side of a line that ``inward`` points to."""
    limit = inward.dot(start)

    def side(point: _Point) -> Fraction:
        return inward.x * point[0] + inward.y * point[1] + inward.z * point[2] - limit

    kept: list[_Point] = []
    for current, following in zip(polygon, [*polygon[1:], polygon[0]], strict=True):
        here, there = side(current), side(following)
        if here >= 0:
            kept.append(current)
        if (here > 0 > there) or (here < 0 < there):
            share = here / (here - there)
            kept.append(
                (
                    current[0] + share * (following[0] - current[0]),
                    current[1] + share * (following[1] - current[1]),
                    current[2] + share * (following[2] - current[2]),
                )
            )
    return kept


def _newell(polygon: Sequence[_Point]) -> _Point:
    """Return twice the area vector of a polygon, normal to it."""
    x = y = z = Fraction(0)
    for point, following in zip(polygon, [*polygon[1:], polygon[0]], strict=True):
        x += (point[1] - following[1]) * (point[2] + following[2])
        y += (point[2] - following[2]) * (point[0] + following[0])
        z += (point[0] - following[0]) * (point[1] + following[1])
    return x, y, z


def _exact(corner: tuple[int, int, int]) -> _Point:
    return Fraction(corner[0]), Fraction(corner[1]), Fraction(corner[2])


def stud_joints(
    elements: Sequence[PlacedElement], anti_studs: AntiStudIndex
) -> Iterator[Joint]:
    """Yield every stud that sits in another element's anti-stud."""
    for i, element in enumerate(elements):
        for connector in element.connectors:
            if connector.kind is not ConnectorKind.STUD:
                continue
            for j in anti_studs.get((connector.position, -connector.normal), ()):
                if j != i:
                    yield Joint(i, j, connector.position, connector.normal)


def adjacency(
    count: int, contacts: Iterable[Contact], joints: Iterable[Joint]
) -> list[set[int]]:
    """Return the elements that each element touches or joins by studs."""
    links: list[set[int]] = [set() for _ in range(count)]
    pairs = [(c.first, c.second) for c in contacts if c.first is not None]
    pairs += [(joint.stud, joint.anti_stud) for joint in joints]
    for a, b in pairs:
        links[a].add(b)
        links[b].add(a)
    return links


def reach(start: set[int], links: Sequence[set[int]], within: set[int]) -> set[int]:
    """Return ``start`` and the elements of ``within`` that links join to it."""
    reached = set(start)
    stack = list(start)
    while stack:
        for j in (links[stack.pop()] & within) - reached:
            reached.add(j)
            stack.append(j)
    return reached


def stud_clusters(
    elements: Sequence[int], joints: Sequence[Joint]
) -> list[tuple[int, ...]]:
    """Group elements that studs join, directly or through other elements."""
    links: dict[int, set[int]] = {i: set() for i in elements}
    for joint in joints:
        if joint.stud in links and joint.anti_stud in links:
            links[joint.stud].add(joint.anti_stud)
            links[joint.anti_stud].add(joint.stud)
    left = set(elements)
    clusters: list[tuple[int, ...]] = []
    for start in elements:
        if start in left:
            cluster, stack = {start}, [start]
            while stack:
                for j in links[stack.pop()] - cluster:
                    cluster.add(j)
                    stack.append(j)
            left -= cluster
            clusters.append(tuple(sorted(cluster)))
    return clusters


def touching_groups(
    moving: set[int], links: Sequence[set[int]]
) -> tuple[tuple[int, ...], ...]:
    """Split moving elements into groups that touch or join one another."""
    groups: list[tuple[int, ...]] = []
    left = set(moving)
    for start in sorted(moving):
        if start in left:
            group = reach({start}, links, moving)
            left -= group
            groups.append(tuple(sorted(group)))
    return tuple(groups)
