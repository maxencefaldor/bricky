"""Fill voxels with bricks and plates, the way a builder lays courses.

Many models are easiest to draw as voxels: which color fills each stud square, one plate tall.
:func:`plan_fill` turns such a drawing into parts a script places: bricks where three plate levels
of a course share a color, plates everywhere else, each part as large as fits.

The courses bond. Each level lays its parts along x or along y, alternating from level to level,
so joints rarely line up above each other. Every part rests on at least one voxel of the level
below, so an overhang takes a part that reaches back over what holds it. A voxel with nothing
below it and no supported neighbor still gets a part; the checks then report it as floating.
"""

from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Final

type Square = tuple[int, int]
"""A stud square, ``(x, y)`` in studs."""

BRICKS: Final[dict[tuple[int, int], str]] = {
    (1, 1): "3005",
    (1, 2): "3004",
    (1, 3): "3622",
    (1, 4): "3010",
    (1, 6): "3009",
    (1, 8): "3008",
    (2, 2): "3003",
    (2, 3): "3002",
    (2, 4): "3001",
    (2, 6): "2456",
    (2, 8): "3007",
    (2, 10): "3006",
}
"""Bricks a fill uses, by footprint: the shorter side first, along x when unrotated."""

PLATES: Final[dict[tuple[int, int], str]] = {
    (1, 1): "3024",
    (1, 2): "3023",
    (1, 3): "3623",
    (1, 4): "3710",
    (1, 6): "3666",
    (1, 8): "3460",
    (2, 2): "3022",
    (2, 3): "3021",
    (2, 4): "3020",
    (2, 6): "3795",
    (2, 8): "3034",
    (2, 10): "3832",
    (4, 4): "3031",
    (4, 6): "3032",
    (4, 8): "3035",
    (6, 6): "3958",
    (6, 8): "3036",
}
"""Plates a fill uses, by footprint: the shorter side first, along x when unrotated."""

COURSE: Final = 3
"""Plate levels in a brick's height, and so in a course."""


@dataclass(frozen=True, slots=True)
class Placement:
    """One part a fill places: what, where, how rotated, and in which color."""

    part: str
    at: tuple[int, int, int]
    """Minimum corner, in studs, studs and plates."""

    rotation: str
    """``R0`` keeps the part's shorter side along x; ``R90`` turns its longer side along x."""

    color: int | str


def plan_fill(voxels: Mapping[tuple[int, int, int], int | str]) -> list[Placement]:
    """Return the bricks and plates that fill exactly the given voxels, bottom level first.

    Args:
        voxels: The color of every voxel to fill, keyed ``(x, y, z)`` in studs, studs and plates.

    Examples:
        >>> wall = {(x, 0, z): "Red" for x in range(4) for z in range(3)}
        >>> [(p.part, p.at, p.rotation) for p in plan_fill(wall)]
        [('3010', (0, 0, 0), 'R90')]
    """
    levels: defaultdict[int, dict[Square, int | str]] = defaultdict(dict)
    for (x, y, z), color in voxels.items():
        levels[z][x, y] = color
    placements: list[Placement] = []
    bricked: defaultdict[int, set[Square]] = defaultdict(set)
    for z in sorted(levels):
        level = levels[z]
        below = None if z == 0 else set(levels.get(z - 1, ()))
        if z % COURSE == 0:
            whole = {
                square: color
                for square, color in level.items()
                if all(levels.get(z + k, {}).get(square) == color for k in range(1, COURSE))
            }
            bricks = _pack(whole, z, BRICKS, along_x=(z // COURSE) % 2 == 0, below=below)
            placements += bricks
            for brick in bricks:
                for square in _squares(brick, BRICKS):
                    for k in range(COURSE):
                        bricked[z + k].add(square)
        rest = {square: color for square, color in level.items() if square not in bricked[z]}
        placements += _pack(rest, z, PLATES, along_x=z % 2 == 1, below=below)
    return placements


def _pack(
    squares: Mapping[Square, int | str],
    z: int,
    parts: Mapping[tuple[int, int], str],
    *,
    along_x: bool,
    below: set[Square] | None,
) -> list[Placement]:
    """Cover same-colored squares of one level with the largest parts that fit and rest on below.

    Squares that overhang go first, since few parts can hold them; the rest follow in rows along
    the chosen axis, each covered by a part whose corner is that square.
    """
    packer = _Packer(dict(squares), z, parts, along_x=along_x, below=below)
    order = sorted(packer.free, key=lambda square: (square[1], square[0]) if along_x else square)
    for start in order:
        if below is not None and start not in below and start in packer.free:
            packer.cover(start, anywhere=True)
    for start in order:
        if start in packer.free and not packer.cover(start, anywhere=False):
            packer.take(start, 1, 1, (1, 1))  # nothing below holds it: a 1 x 1 part, floating
    return packer.placed


@dataclass(slots=True)
class _Packer:
    """The squares of one level still free, and the parts placed over the others."""

    free: dict[Square, int | str]
    z: int
    parts: Mapping[tuple[int, int], str]
    along_x: bool
    below: set[Square] | None
    placed: list[Placement] = field(default_factory=list)

    def cover(self, start: Square, *, anywhere: bool) -> bool:
        """Place the largest part over ``start`` that fits; return whether one did."""
        color = self.free[start]
        for short, long in sorted(self.parts, key=_area, reverse=True):
            shapes = (long, short), (short, long)
            for width, depth in dict.fromkeys(shapes if self.along_x else shapes[::-1]):
                for corner in _corners(start, width, depth, anywhere=anywhere):
                    if self.fits(corner, width, depth, color):
                        self.take(corner, width, depth, (short, long))
                        return True
        return False

    def fits(self, corner: Square, width: int, depth: int, color: int | str) -> bool:
        """Whether a part there covers only free squares of one color, and rests on below."""
        span = [(corner[0] + i, corner[1] + j) for i in range(width) for j in range(depth)]
        return all(self.free.get(square) == color for square in span) and (
            self.below is None or any(square in self.below for square in span)
        )

    def take(self, corner: Square, width: int, depth: int, size: tuple[int, int]) -> None:
        """Place the part of ``size`` at ``corner``, ``width`` studs along x."""
        rotation = "R0" if (width, depth) == size else "R90"
        self.placed.append(
            Placement(self.parts[size], (*corner, self.z), rotation, self.free[corner])
        )
        for i in range(width):
            for j in range(depth):
                del self.free[corner[0] + i, corner[1] + j]


def _area(size: tuple[int, int]) -> tuple[int, int]:
    return size[0] * size[1], size[1]


def _corners(start: Square, width: int, depth: int, *, anywhere: bool) -> Iterator[Square]:
    """Corners of the footprints that cover ``start``: only ``start`` itself, unless anywhere."""
    if not anywhere:
        yield start
        return
    for i in range(width):
        for j in range(depth):
            yield start[0] - i, start[1] - j


def _squares(placement: Placement, parts: Mapping[tuple[int, int], str]) -> Iterator[Square]:
    """The stud squares a placed part covers."""
    short, long = next(size for size, part in parts.items() if part == placement.part)
    width, depth = (short, long) if placement.rotation == "R0" else (long, short)
    x, y, _ = placement.at
    for i in range(width):
        for j in range(depth):
            yield x + i, y + j
