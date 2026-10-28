"""Integer geometry: vectors, the 24 grid rotations, poses, boxes and convex solids.

Every part sits in one of the 24 orientations that map grid axes onto grid axes, so a rotation is
a signed permutation and all arithmetic stays exact. Boxes stay axis-aligned under any rotation,
which keeps most collision tests to a handful of integer comparisons. Parts that are not boxes,
such as slopes and round parts, are unions of convex solids with integer corners: their faces'
planes have integer normals, and whether two solids overlap is decided exactly, by separating axes.
"""

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from functools import cache
from math import gcd
from typing import Final, Literal


@dataclass(frozen=True, slots=True, order=True)
class Vector:
    """An integer vector, in base units unless stated otherwise."""

    x: int
    y: int
    z: int

    def __add__(self, other: Vector) -> Vector:
        return Vector(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vector) -> Vector:
        return Vector(self.x - other.x, self.y - other.y, self.z - other.z)

    def __neg__(self) -> Vector:
        return Vector(-self.x, -self.y, -self.z)

    def __mul__(self, factor: int) -> Vector:
        return Vector(self.x * factor, self.y * factor, self.z * factor)

    def __iter__(self) -> Iterator[int]:
        yield self.x
        yield self.y
        yield self.z

    def dot(self, other: Vector) -> int:
        """Return the dot product."""
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vector) -> Vector:
        """Return the cross product."""
        return Vector(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def as_tuple(self) -> tuple[int, int, int]:
        """Return the components as a tuple."""
        return (self.x, self.y, self.z)


ORIGIN: Final = Vector(0, 0, 0)

AXES: Final[dict[str, Vector]] = {
    "+x": Vector(1, 0, 0),
    "-x": Vector(-1, 0, 0),
    "+y": Vector(0, 1, 0),
    "-y": Vector(0, -1, 0),
    "+z": Vector(0, 0, 1),
    "-z": Vector(0, 0, -1),
}
"""The six signed grid axes by name."""

UP: Final = AXES["+z"]
DOWN: Final = AXES["-z"]

_AXIS_NAMES: Final = {vector: name for name, vector in AXES.items()}


def axis_name(vector: Vector) -> str:
    """Name a signed unit grid axis, such as ``"+x"``.

    Raises:
        ValueError: If the vector is not a signed unit grid axis.
    """
    try:
        return _AXIS_NAMES[vector]
    except KeyError:
        msg = f"{vector} is not a unit grid axis"
        raise ValueError(msg) from None


ALIASES: Final[dict[str, str]] = {"R0": "+x+y", "R90": "+y-x", "R180": "-x-y", "R270": "-y+x"}
"""Short names for the four turns about the vertical axis, counter-clockwise seen from above."""


@dataclass(frozen=True, slots=True)
class Rotation:
    """A proper rotation mapping grid axes onto grid axes: one of 24.

    A rotation is named by the images of the local x and y axes, so ``"+x+y"`` is the identity and
    ``"+y-x"`` turns a part 90° counter-clockwise seen from above. :data:`ALIASES` gives short names
    for the four vertical-axis turns.
    """

    x_axis: Vector
    """Where the rotation takes the x axis."""

    y_axis: Vector
    """Where the rotation takes the y axis."""

    z_axis: Vector = field(init=False, repr=False, compare=False)
    """Where the rotation takes the z axis: the cross product of the other two."""

    def __post_init__(self) -> None:
        if (
            self.x_axis not in _AXIS_NAMES
            or self.y_axis not in _AXIS_NAMES
            or self.x_axis.dot(self.y_axis) != 0
        ):
            msg = f"{self.x_axis} and {self.y_axis} are not two perpendicular grid axes"
            raise ValueError(msg)
        object.__setattr__(self, "z_axis", self.x_axis.cross(self.y_axis))

    @classmethod
    def parse(cls, text: str) -> Rotation:
        """Parse a rotation name such as ``"+y-x"`` or an alias such as ``"R90"``.

        Raises:
            ValueError: If the text names no rotation.
        """
        key = ALIASES.get(text.upper(), text)
        try:
            return cls(AXES[key[:2]], AXES[key[2:]])
        except KeyError, ValueError:
            msg = (
                f"unknown rotation {text!r}: use a name like '+y-x' or one of {', '.join(ALIASES)}"
            )
            raise ValueError(msg) from None

    @property
    def name(self) -> str:
        """The canonical name: images of local x and y, for example ``"+y-x"``."""
        return axis_name(self.x_axis) + axis_name(self.y_axis)

    def apply(self, vector: Vector) -> Vector:
        """Rotate a vector."""
        x, y, z = self.x_axis, self.y_axis, self.z_axis
        return Vector(
            x.x * vector.x + y.x * vector.y + z.x * vector.z,
            x.y * vector.x + y.y * vector.y + z.y * vector.z,
            x.z * vector.x + y.z * vector.y + z.z * vector.z,
        )

    def inverse(self) -> Rotation:
        """Return the rotation that undoes this one."""
        x, y, z = self.x_axis, self.y_axis, self.z_axis
        return Rotation(Vector(x.x, y.x, z.x), Vector(x.y, y.y, z.y))

    def __matmul__(self, other: Rotation) -> Rotation:
        """Compose rotations: ``(a @ b).apply(v) == a.apply(b.apply(v))``."""
        return Rotation(self.apply(other.x_axis), self.apply(other.y_axis))

    def __str__(self) -> str:
        return self.name


IDENTITY: Final = Rotation(AXES["+x"], AXES["+y"])

ROTATIONS: Final[tuple[Rotation, ...]] = tuple(
    Rotation(x, y) for x in AXES.values() for y in AXES.values() if x.dot(y) == 0
)
"""All 24 grid rotations."""


@dataclass(frozen=True, slots=True)
class Pose:
    """A rigid placement: rotate about the local origin, then translate."""

    rotation: Rotation = IDENTITY
    position: Vector = ORIGIN

    def apply(self, point: Vector) -> Vector:
        """Map a point from the local frame to the parent frame."""
        return self.rotation.apply(point) + self.position

    def apply_direction(self, direction: Vector) -> Vector:
        """Map a direction from the local frame to the parent frame."""
        return self.rotation.apply(direction)

    def __matmul__(self, inner: Pose) -> Pose:
        """Compose poses: ``(outer @ inner).apply(p) == outer.apply(inner.apply(p))``."""
        return Pose(self.rotation @ inner.rotation, self.apply(inner.position))


@dataclass(frozen=True, slots=True)
class Box:
    """A half-open, axis-aligned box ``[min, max)`` with integer corners."""

    min: Vector
    """The minimum corner: the smallest coordinate on every axis."""

    max: Vector
    """The maximum corner: the largest coordinate on every axis."""

    def __post_init__(self) -> None:
        if self.min.x > self.max.x or self.min.y > self.max.y or self.min.z > self.max.z:
            msg = f"box corners out of order: {self.min} > {self.max}"
            raise ValueError(msg)

    @classmethod
    def spanning(cls, a: Vector, b: Vector) -> Box:
        """Return the box with opposite corners ``a`` and ``b``, in any order."""
        return cls(
            Vector(min(a.x, b.x), min(a.y, b.y), min(a.z, b.z)),
            Vector(max(a.x, b.x), max(a.y, b.y), max(a.z, b.z)),
        )

    @classmethod
    def bounding(cls, boxes: Iterable[Box]) -> Box:
        """Return the smallest box containing all the given boxes.

        Raises:
            ValueError: If no boxes are given.
        """
        boxes = list(boxes)
        if not boxes:
            msg = "cannot bound an empty set of boxes"
            raise ValueError(msg)
        return cls(
            Vector(
                min(b.min.x for b in boxes),
                min(b.min.y for b in boxes),
                min(b.min.z for b in boxes),
            ),
            Vector(
                max(b.max.x for b in boxes),
                max(b.max.y for b in boxes),
                max(b.max.z for b in boxes),
            ),
        )

    @property
    def size(self) -> Vector:
        """Extent along each axis."""
        return self.max - self.min

    @property
    def bounds(self) -> Box:
        """The box itself, so a box and a :class:`Convex` both answer ``bounds``."""
        return self

    def corners(self) -> tuple[Vector, ...]:
        """The eight corners: bit 1 of the index picks the high x, bit 2 high y, bit 4 high z."""
        low, high = self.min, self.max
        return tuple(
            Vector(
                high.x if i & 1 else low.x, high.y if i & 2 else low.y, high.z if i & 4 else low.z
            )
            for i in range(8)
        )

    def as_convex(self) -> Convex:
        """The same solid as a :class:`Convex`, for exact tests against other convex solids.

        Raises:
            ValueError: If the box has no volume.
        """
        return _box_convex(self)

    @property
    def volume(self) -> int:
        """Volume in cubic base units."""
        size = self.size
        return size.x * size.y * size.z

    def contains(self, point: Vector) -> bool:
        """Return whether a point lies in the box, counting low faces in and high faces out."""
        return (
            self.min.x <= point.x < self.max.x
            and self.min.y <= point.y < self.max.y
            and self.min.z <= point.z < self.max.z
        )

    def overlaps(self, other: Box) -> bool:
        """Return whether the boxes share positive volume; touching faces do not count."""
        return (
            self.min.x < other.max.x
            and other.min.x < self.max.x
            and self.min.y < other.max.y
            and other.min.y < self.max.y
            and self.min.z < other.max.z
            and other.min.z < self.max.z
        )

    def intersection(self, other: Box) -> Box | None:
        """Return the shared box, or ``None`` if the boxes share no volume."""
        if not self.overlaps(other):
            return None
        return Box(
            Vector(
                max(self.min.x, other.min.x),
                max(self.min.y, other.min.y),
                max(self.min.z, other.min.z),
            ),
            Vector(
                min(self.max.x, other.max.x),
                min(self.max.y, other.max.y),
                min(self.max.z, other.max.z),
            ),
        )

    def transformed(self, pose: Pose) -> Box:
        """Return the box placed by a pose; grid rotations keep boxes axis-aligned."""
        return Box.spanning(pose.apply(self.min), pose.apply(self.max))


_BOX_FACES: Final = (
    (0, 4, 6, 2),
    (1, 3, 7, 5),
    (0, 1, 5, 4),
    (2, 6, 7, 3),
    (0, 2, 3, 1),
    (4, 5, 7, 6),
)
"""Faces of a box by :meth:`Box.corners` index, counter-clockwise seen from outside."""


type Plane = tuple[Vector, int]
"""An outward normal and an offset: points ``p`` with ``normal.dot(p) <= offset`` are inside."""


@dataclass(frozen=True, slots=True)
class Convex:
    """A convex solid with integer corners, such as the body of a slope.

    Faces list corner indices counter-clockwise seen from outside. Every face's plane is kept as an
    integer outward normal and offset, so whether a point is inside, or two solids overlap, is
    decided without rounding.

    Raises:
        ValueError: If a face has fewer than three corners, is not flat, or faces inward, or the
            solid is not convex.
    """

    vertices: tuple[Vector, ...]
    faces: tuple[tuple[int, ...], ...]
    planes: tuple[Plane, ...] = field(init=False, repr=False, compare=False)
    bounds: Box = field(init=False, repr=False, compare=False)
    directions: tuple[Vector, ...] = field(init=False, repr=False, compare=False)
    """The distinct directions of the edges, each as a primitive vector."""

    def __post_init__(self) -> None:
        planes: list[Plane] = []
        directions: set[Vector] = set()
        for face in self.faces:
            corners = [self.vertices[i] for i in face]
            normal = _primitive(_newell(corners))
            if len(corners) < 3 or normal == ORIGIN:  # noqa: PLR2004 - a face needs three corners
                msg = f"face {face} is degenerate"
                raise ValueError(msg)
            offset = normal.dot(corners[0])
            if any(normal.dot(corner) != offset for corner in corners):
                msg = f"face {face} is not flat"
                raise ValueError(msg)
            if any(normal.dot(vertex) > offset for vertex in self.vertices):
                msg = f"face {face} faces inward, or the solid is not convex"
                raise ValueError(msg)
            planes.append((normal, offset))
            for a, b in zip(corners, corners[1:] + corners[:1], strict=True):
                if a != b:
                    directions.add(_direction(b - a))
        xs, ys, zs = zip(*(v.as_tuple() for v in self.vertices), strict=True)
        object.__setattr__(self, "planes", tuple(planes))
        object.__setattr__(
            self,
            "bounds",
            Box(Vector(min(xs), min(ys), min(zs)), Vector(max(xs), max(ys), max(zs))),
        )
        object.__setattr__(self, "directions", tuple(sorted(directions)))

    @classmethod
    def prism(
        cls,
        polygon: Sequence[tuple[int, int]],
        axis: Literal["x", "y", "z"],
        start: int,
        end: int,
    ) -> Convex:
        """Extrude a convex polygon along an axis, from ``start`` to ``end``.

        The polygon runs counter-clockwise in its plane, in coordinates ``(a, b)`` chosen so that
        a, b and the axis are right-handed: ``(x, y)`` along z, ``(y, z)`` along x, and
        ``(z, x)`` along y.

        Raises:
            ValueError: If the polygon is not convex and counter-clockwise, or ``start >= end``.
        """
        if start >= end:
            msg = f"a prism needs start < end, not {start} and {end}"
            raise ValueError(msg)

        def point(a: int, b: int, c: int) -> Vector:
            if axis == "z":
                return Vector(a, b, c)
            if axis == "x":
                return Vector(c, a, b)
            return Vector(b, c, a)

        n = len(polygon)
        vertices = tuple(point(a, b, start) for a, b in polygon) + tuple(
            point(a, b, end) for a, b in polygon
        )
        bottom = tuple(reversed(range(n)))
        top = tuple(range(n, 2 * n))
        sides = tuple((i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n))
        return cls(vertices, (bottom, top, *sides))

    def transformed(self, pose: Pose) -> Convex:
        """Return the solid placed by a pose; proper rotations keep faces wound outward."""
        return Convex(tuple(pose.apply(v) for v in self.vertices), self.faces)

    def contains(self, point: Vector) -> bool:
        """Return whether a point lies in the solid.

        A point on a face counts as inside when the face looks toward lower coordinates (its
        normal's first nonzero component is negative) and outside otherwise, as with
        :meth:`Box.contains`, so solids that share a face never both contain a point on it.
        """
        for normal, offset in self.planes:
            value = normal.dot(point)
            if value > offset or (value == offset and _looks_up(normal)):
                return False
        return True

    def extent(self, axis: Vector) -> tuple[int, int]:
        """The lowest and highest values of ``axis.dot(corner)`` over the corners."""
        values = [axis.dot(v) for v in self.vertices]
        return min(values), max(values)


type Solid = Box | Convex
"""A part's body is a union of solids: boxes, or convex solids where a box will not do."""


def overlaps(a: Solid, b: Solid) -> bool:
    """Return whether two solids share positive volume; touching faces or edges do not count.

    Convex solids are tested by separating axes: two convex solids keep their insides apart exactly
    when some axis from their face normals, or the cross products of their edge directions, has
    them on opposite sides, touching at most.
    """
    if not a.bounds.overlaps(b.bounds):
        return False
    if isinstance(a, Box) and isinstance(b, Box):
        return True
    first = a if isinstance(a, Convex) else a.as_convex()
    second = b if isinstance(b, Convex) else b.as_convex()
    axes = [normal for normal, _ in (*first.planes, *second.planes)]
    axes += [u.cross(v) for u in first.directions for v in second.directions]
    for axis in axes:
        if axis == ORIGIN:
            continue
        a_low, a_high = first.extent(axis)
        b_low, b_high = second.extent(axis)
        if a_high <= b_low or b_high <= a_low:
            return False
    return True


@cache
def _box_convex(box: Box) -> Convex:
    return Convex(box.corners(), _BOX_FACES)


def _newell(points: Sequence[Vector]) -> Vector:
    """Newell's normal of a polygon: outward for corners counter-clockwise seen from outside."""
    x = y = z = 0
    for p, q in zip(points, [*points[1:], points[0]], strict=True):
        x += (p.y - q.y) * (p.z + q.z)
        y += (p.z - q.z) * (p.x + q.x)
        z += (p.x - q.x) * (p.y + q.y)
    return Vector(x, y, z)


def _primitive(vector: Vector) -> Vector:
    """The vector divided by the greatest common divisor of its components."""
    divisor = gcd(vector.x, vector.y, vector.z)
    if divisor == 0:
        return vector
    return Vector(vector.x // divisor, vector.y // divisor, vector.z // divisor)


def _direction(vector: Vector) -> Vector:
    """A primitive vector along the same line, its first nonzero component positive."""
    primitive = _primitive(vector)
    return -primitive if _looks_up(-primitive) else primitive


def _looks_up(vector: Vector) -> bool:
    """Whether the first nonzero component is positive."""
    for component in vector:
        if component:
            return component > 0
    return False
