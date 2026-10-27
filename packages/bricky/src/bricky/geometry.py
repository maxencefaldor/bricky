"""Integer geometry: vectors, the 24 grid rotations, poses and boxes.

Every part sits in one of the 24 orientations that map grid axes onto grid axes, so a rotation is
a signed permutation and all arithmetic stays exact. Boxes stay axis-aligned under any rotation,
which keeps collision tests to a handful of integer comparisons.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True, slots=True, order=True)
class Vec3:
    """An integer vector, in base units unless stated otherwise."""

    x: int
    y: int
    z: int

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __neg__(self) -> Vec3:
        return Vec3(-self.x, -self.y, -self.z)

    def __mul__(self, factor: int) -> Vec3:
        return Vec3(self.x * factor, self.y * factor, self.z * factor)

    def __iter__(self) -> Iterator[int]:
        yield self.x
        yield self.y
        yield self.z

    def dot(self, other: Vec3) -> int:
        """Return the dot product."""
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vec3) -> Vec3:
        """Return the cross product."""
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def as_tuple(self) -> tuple[int, int, int]:
        """Return the components as a tuple."""
        return (self.x, self.y, self.z)


ORIGIN: Final = Vec3(0, 0, 0)

AXES: Final[dict[str, Vec3]] = {
    "+x": Vec3(1, 0, 0),
    "-x": Vec3(-1, 0, 0),
    "+y": Vec3(0, 1, 0),
    "-y": Vec3(0, -1, 0),
    "+z": Vec3(0, 0, 1),
    "-z": Vec3(0, 0, -1),
}
"""The six signed grid axes by name."""

UP: Final = AXES["+z"]
DOWN: Final = AXES["-z"]

_AXIS_NAMES: Final = {vector: name for name, vector in AXES.items()}


def axis_name(vector: Vec3) -> str:
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

    ex: Vec3
    ey: Vec3
    ez: Vec3 = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.ex not in _AXIS_NAMES or self.ey not in _AXIS_NAMES or self.ex.dot(self.ey) != 0:
            msg = f"{self.ex} and {self.ey} are not two perpendicular grid axes"
            raise ValueError(msg)
        object.__setattr__(self, "ez", self.ex.cross(self.ey))

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
        return axis_name(self.ex) + axis_name(self.ey)

    def apply(self, vector: Vec3) -> Vec3:
        """Rotate a vector."""
        ex, ey, ez = self.ex, self.ey, self.ez
        return Vec3(
            ex.x * vector.x + ey.x * vector.y + ez.x * vector.z,
            ex.y * vector.x + ey.y * vector.y + ez.y * vector.z,
            ex.z * vector.x + ey.z * vector.y + ez.z * vector.z,
        )

    def inverse(self) -> Rotation:
        """Return the rotation that undoes this one."""
        ex, ey, ez = self.ex, self.ey, self.ez
        return Rotation(Vec3(ex.x, ey.x, ez.x), Vec3(ex.y, ey.y, ez.y))

    def __matmul__(self, other: Rotation) -> Rotation:
        """Compose rotations: ``(a @ b).apply(v) == a.apply(b.apply(v))``."""
        return Rotation(self.apply(other.ex), self.apply(other.ey))

    def __str__(self) -> str:
        return self.name


IDENTITY: Final = Rotation(AXES["+x"], AXES["+y"])

ROTATIONS: Final[tuple[Rotation, ...]] = tuple(
    Rotation(ex, ey) for ex in AXES.values() for ey in AXES.values() if ex.dot(ey) == 0
)
"""All 24 grid rotations."""


@dataclass(frozen=True, slots=True)
class Pose:
    """A rigid placement: rotate about the local origin, then translate."""

    rot: Rotation = IDENTITY
    pos: Vec3 = ORIGIN

    def apply(self, point: Vec3) -> Vec3:
        """Map a point from the local frame to the parent frame."""
        return self.rot.apply(point) + self.pos

    def apply_direction(self, direction: Vec3) -> Vec3:
        """Map a direction from the local frame to the parent frame."""
        return self.rot.apply(direction)

    def __matmul__(self, inner: Pose) -> Pose:
        """Compose poses: ``(outer @ inner).apply(p) == outer.apply(inner.apply(p))``."""
        return Pose(self.rot @ inner.rot, self.apply(inner.pos))


@dataclass(frozen=True, slots=True)
class Box:
    """A half-open, axis-aligned box ``[lo, hi)`` with integer corners."""

    lo: Vec3
    hi: Vec3

    def __post_init__(self) -> None:
        if self.lo.x > self.hi.x or self.lo.y > self.hi.y or self.lo.z > self.hi.z:
            msg = f"box corners out of order: {self.lo} > {self.hi}"
            raise ValueError(msg)

    @classmethod
    def spanning(cls, a: Vec3, b: Vec3) -> Box:
        """Return the box with opposite corners ``a`` and ``b``, in any order."""
        return cls(
            Vec3(min(a.x, b.x), min(a.y, b.y), min(a.z, b.z)),
            Vec3(max(a.x, b.x), max(a.y, b.y), max(a.z, b.z)),
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
            Vec3(
                min(b.lo.x for b in boxes), min(b.lo.y for b in boxes), min(b.lo.z for b in boxes)
            ),
            Vec3(
                max(b.hi.x for b in boxes), max(b.hi.y for b in boxes), max(b.hi.z for b in boxes)
            ),
        )

    @property
    def size(self) -> Vec3:
        """Extent along each axis."""
        return self.hi - self.lo

    @property
    def volume(self) -> int:
        """Volume in cubic base units."""
        size = self.size
        return size.x * size.y * size.z

    def contains(self, point: Vec3) -> bool:
        """Return whether a point lies in the box, counting low faces in and high faces out."""
        return (
            self.lo.x <= point.x < self.hi.x
            and self.lo.y <= point.y < self.hi.y
            and self.lo.z <= point.z < self.hi.z
        )

    def overlaps(self, other: Box) -> bool:
        """Return whether the boxes share positive volume; touching faces do not count."""
        return (
            self.lo.x < other.hi.x
            and other.lo.x < self.hi.x
            and self.lo.y < other.hi.y
            and other.lo.y < self.hi.y
            and self.lo.z < other.hi.z
            and other.lo.z < self.hi.z
        )

    def intersection(self, other: Box) -> Box | None:
        """Return the shared box, or ``None`` if the boxes share no volume."""
        if not self.overlaps(other):
            return None
        return Box(
            Vec3(
                max(self.lo.x, other.lo.x), max(self.lo.y, other.lo.y), max(self.lo.z, other.lo.z)
            ),
            Vec3(
                min(self.hi.x, other.hi.x), min(self.hi.y, other.hi.y), min(self.hi.z, other.hi.z)
            ),
        )

    def transformed(self, pose: Pose) -> Box:
        """Return the box placed by a pose; grid rotations keep boxes axis-aligned."""
        return Box.spanning(pose.apply(self.lo), pose.apply(self.hi))
