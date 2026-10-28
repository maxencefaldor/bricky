# Copyright 2026 Maxence Faldor
"""Fill voxels with bricks and plates, the way a builder lays courses.

Many models are easiest to draw as voxels: which color fills each stud square, one plate tall.
:func:`plan_fill` turns such a drawing into parts a script places: bricks where three plate levels
of a course share a color, plates everywhere else, each part as large as fits.

The courses bond. Each level lays its parts along x or along y, alternating from level to level,
so joints rarely line up above each other. Every part rests on at least one voxel of the level
below, so an overhang takes a part that reaches back over what holds it. Overhangs, and the
squares beside them, take plates, so each level of an overhang reaches back on its own. A voxel
that no part can hold still gets a part; the checks then report it as floating.
"""

from collections import defaultdict, deque
from collections.abc import Callable, Container, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Final

type Square = tuple[int, int]
"""A stud square, ``(x, y)`` in studs."""

type MadeIn = Callable[[str, int | str], bool]
"""Whether a part, by id, comes in a color, by id or name."""

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
    """``R0`` keeps the part's shorter side along x; ``R90`` lays its longer side along x."""

    color: int | str


def plan_fill(
    voxels: Mapping[tuple[int, int, int], int | str], *, made_in: MadeIn | None = None
) -> list[Placement]:
    """Return the bricks and plates that fill exactly the given voxels, bottom level first.

    Args:
        voxels: The color of every voxel to fill, keyed ``(x, y, z)`` in studs, studs and plates.
        made_in: Whether a part comes in a color; the fill then uses only parts that do, and a
            1 x 1 part where none does. Every part is allowed when omitted.

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
        below = set(levels.get(z - 1, ()))
        if z % COURSE == 0:
            course = [levels.get(z + k, {}) for k in range(COURSE)]
            hanging = {  # the course's overhanging squares, with their colors
                (square, color)
                for k in range(COURSE)
                if z + k > 0
                for square, color in course[k].items()
                if square not in levels.get(z + k - 1, {})
            }
            whole = {
                square: color
                for square, color in level.items()
                if all(course[k].get(square) == color for k in range(1, COURSE))
                and not any(
                    (near, color) in hanging for near in (square, *_neighbors(square))
                )
            }
            along_x = (z // COURSE) % 2 == 0
            bricks = _Packer(
                whole, z, BRICKS, along_x, below, made_in, floating=False
            ).pack()
            placements += bricks
            for brick in bricks:
                for square in _squares(brick, BRICKS):
                    for k in range(COURSE):
                        bricked[z + k].add(square)
        rest = {
            square: color for square, color in level.items() if square not in bricked[z]
        }
        placements += _Packer(rest, z, PLATES, z % 2 == 1, below, made_in).pack()
    return placements


@dataclass(slots=True)
class _Packer:
    """The squares of one level still free, and the parts placed over the others."""

    free: dict[Square, int | str]
    z: int
    parts: Mapping[tuple[int, int], str]
    along_x: bool
    below: set[Square]
    """The squares the level below fills; on the ground, z = 0, every square is held."""

    made_in: MadeIn | None
    floating: bool = True
    """Whether a square no part can hold still gets a 1 x 1 part; otherwise it stays free."""

    placed: list[Placement] = field(default_factory=list)
    longest: int = field(init=False)
    """The longest side of any part, and so the farthest a part reaches."""

    def __post_init__(self) -> None:
        self.longest = max(long for _, long in self.parts)

    def pack(self) -> list[Placement]:
        """Cover every square with the largest parts that fit and rest on the level below.

        Squares that overhang go first: those with the fewest lines back to support, then the
        farthest from it, since few parts can hold them. The rest follow in rows along the chosen
        axis, each covered by a part whose corner is that square.
        """
        order = sorted(
            self.free, key=lambda square: square[::-1] if self.along_x else square
        )
        if self.z != 0:
            reach = self.reach()
            overhanging = [square for square in order if reach.get(square, 0) > 0]
            overhanging.sort(key=lambda square: (self.lines(square), -reach[square]))
            for start in overhanging:
                if start in self.free:
                    self.cover(start, anywhere=True)
        for start in order:
            if (
                start in self.free
                and not self.cover(start, anywhere=False)
                and self.floating
            ):
                # No part both rests on the level below and comes in this color: a 1 x 1 part.
                self.take(start, 1, 1, (1, 1))
        return self.placed

    def reach(self) -> dict[Square, int]:
        """How many squares each square lies from one the level below holds, through its color.

        Squares that no path of their color joins to a held square are left out: no part can
        hold them.
        """
        steps = {square: 0 for square in self.free if square in self.below}
        queue = deque(steps)
        while queue:
            square = queue.popleft()
            for neighbor in _neighbors(square):
                if (
                    neighbor not in steps
                    and self.free.get(neighbor) == self.free[square]
                ):
                    steps[neighbor] = steps[square] + 1
                    queue.append(neighbor)
        return steps

    def cover(self, start: Square, *, anywhere: bool) -> bool:
        """Place the largest part over ``start`` that fits; return whether one did.

        With ``anywhere``, the part may take any offset over ``start``, and gives way to the next
        part that fits while it would strand an overhanging neighbor, leaving it no line back to
        support. When every part that fits strands one, the part that strands the fewest is placed.
        """
        color = self.free[start]
        best: tuple[int, tuple[Square, int, int, tuple[int, int]]] | None = None
        for short, long in sorted(self.parts, key=_area, reverse=True):
            if self.made_in is not None and not self.made_in(
                self.parts[short, long], color
            ):
                continue
            shapes = (long, short), (short, long)
            for width, depth in dict.fromkeys(shapes if self.along_x else shapes[::-1]):
                for corner in _corners(start, width, depth, anywhere=anywhere):
                    if not self.fits(corner, width, depth, color):
                        continue
                    candidate = corner, width, depth, (short, long)
                    stranded = (
                        self.stranded(_span(corner, width, depth)) if anywhere else 0
                    )
                    if stranded == 0:
                        self.take(*candidate)
                        return True
                    if best is None or stranded < best[0]:
                        best = stranded, candidate
        if best is not None:
            self.take(*best[1])
        return best is not None

    def fits(self, corner: Square, width: int, depth: int, color: int | str) -> bool:
        """Whether a part there covers only free squares of one color, and rests on below."""
        span = _span(corner, width, depth)
        return all(self.free.get(square) == color for square in span) and (
            self.z == 0 or any(square in self.below for square in span)
        )

    def stranded(self, span: set[Square]) -> int:
        """How many overhanging neighbors a part over ``span`` would leave with no line back."""
        border = {neighbor for square in span for neighbor in _neighbors(square)} - span
        return sum(
            square in self.free
            and square not in self.below
            and self.lines(square) > 0
            and self.lines(square, span) == 0
            for square in border
        )

    def lines(self, square: Square, blocked: Container[Square] = frozenset()) -> int:
        """How many lines run from ``square`` to a held square, around ``blocked``.

        A line is a row of free squares of one color, straight along x or y and shorter than the
        longest part, that ends on a square the level below holds.
        """
        color = self.free[square]
        count = 0
        for step_x, step_y in (1, 0), (-1, 0), (0, 1), (0, -1):
            for distance in range(1, self.longest):
                ahead = square[0] + distance * step_x, square[1] + distance * step_y
                if ahead in blocked or self.free.get(ahead) != color:
                    break
                if ahead in self.below:
                    count += 1
                    break
        return count

    def take(
        self, corner: Square, width: int, depth: int, size: tuple[int, int]
    ) -> None:
        """Place the part of ``size`` at ``corner``, ``width`` studs along x."""
        rotation = "R0" if (width, depth) == size else "R90"
        self.placed.append(
            Placement(self.parts[size], (*corner, self.z), rotation, self.free[corner])
        )
        for square in _span(corner, width, depth):
            del self.free[square]


def _neighbors(square: Square) -> tuple[Square, ...]:
    """The four squares that share a side with a square."""
    x, y = square
    return (x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)


def _span(corner: Square, width: int, depth: int) -> set[Square]:
    """The squares of a footprint ``width`` by ``depth`` studs, from its minimum corner."""
    return {(corner[0] + i, corner[1] + j) for i in range(width) for j in range(depth)}


def _area(size: tuple[int, int]) -> tuple[int, int]:
    return size[0] * size[1], size[1]


def _corners(
    start: Square, width: int, depth: int, *, anywhere: bool
) -> Iterator[Square]:
    """Corners of the footprints that cover ``start``: only ``start`` itself, unless anywhere."""
    if not anywhere:
        yield start
        return
    for i in range(width):
        for j in range(depth):
            yield start[0] - i, start[1] - j


def _squares(
    placement: Placement, parts: Mapping[tuple[int, int], str]
) -> Iterator[Square]:
    """The stud squares a placed part covers."""
    short, long = next(size for size, part in parts.items() if part == placement.part)
    width, depth = (short, long) if placement.rotation == "R0" else (long, short)
    x, y, _ = placement.at
    for i in range(width):
        for j in range(depth):
            yield x + i, y + j
