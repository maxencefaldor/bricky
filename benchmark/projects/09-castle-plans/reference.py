# Copyright 2026 Maxence Faldor
"""Reference for project 09: a castle with four corner towers, a gatehouse and a keep.

The walls are two studs thick, in running bond. Hollow towers interlock at their
corners: on even courses the walls along x run the full width, on odd courses the walls
along y do.
"""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from bricky import ModelBuilder

STONE = "Light Bluish Gray"
FOOTING = "Dark Bluish Gray"
ROOF = "Dark Bluish Gray"
# Bricks two studs wide by length, longest first; a 1 x 2 brick fills a single cell of a
# strip.
STRIP = {8: "3007", 6: "2456", 4: "3001", 3: "3002", 2: "3003", 1: "3004"}

type Cell = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Run:
    """A strip two studs wide, from ``start``, ``length`` cells along x or along y."""

    start: Cell
    length: int
    along_x: bool


def strip(
    builder: ModelBuilder,
    run: Run,
    *,
    z: int,
    color: str,
    gaps: AbstractSet[Cell] = frozenset(),
) -> None:
    """Fill a strip with bricks, skipping gap cells.

    A gap cell removes the strip's whole width at that position along it.
    """
    start_x, start_y = run.start
    cells = [
        (start_x + i, start_y) if run.along_x else (start_x, start_y + i)
        for i in range(run.length)
    ]
    i = 0
    while i < run.length:
        if cells[i] in gaps:
            i += 1
            continue
        j = i
        while j < run.length and cells[j] not in gaps:
            j += 1
        while i < j:
            size = next(candidate for candidate in STRIP if candidate <= j - i)
            x, y = cells[i]
            across = size == 1  # a 1 x 2 brick lies across the strip
            builder.place(
                STRIP[size],
                at=(x, y, z),
                rotation="R0" if run.along_x == across else "R90",
                color=color,
            )
            i += size


def tower(
    builder: ModelBuilder, corner: Cell, size: int, courses: int, *, roof: bool = False
) -> None:
    """A hollow, crenellated square tower with arrow slits and walls two studs thick.

    A roof, when asked for, covers the tower under its battlements.
    """
    west, south = corner
    east, north = west + size, south + size
    for course in range(courses):
        z = 1 + 3 * course
        color = FOOTING if course == 0 else STONE
        gaps: set[Cell] = set()
        if course in {4, 5}:
            middle = size // 2 - 1
            gaps = {
                (west + middle, south),
                (west, south + middle),
                (east - 2, south + middle),
                (west + middle, north - 2),
            }
        if course % 2 == 0:  # the walls along x run the full width
            runs = [
                Run((west, south), size, along_x=True),
                Run((west, north - 2), size, along_x=True),
                Run((west, south + 2), size - 4, along_x=False),
                Run((east - 2, south + 2), size - 4, along_x=False),
            ]
        else:  # the walls along y do
            runs = [
                Run((west, south), size, along_x=False),
                Run((east - 2, south), size, along_x=False),
                Run((west + 2, south), size - 4, along_x=True),
                Run((west + 2, north - 2), size - 4, along_x=True),
            ]
        for run in runs:
            strip(builder, run, z=z, color=color, gaps=gaps)
    top = 1 + 3 * courses
    if roof:
        # Rows of plates across the whole tower, so the roof rests on all four walls.
        for y in range(south, north, 2):
            strip_plates(builder, (west, y), size, top)
        top += 1
    battlements(builder, west, south, size, top)


def strip_plates(builder: ModelBuilder, start: Cell, length: int, z: int) -> None:
    """A row of 2 x 8, 2 x 6, 2 x 4 and 2 x 2 plates along x, longest first."""
    plates = {8: "3034", 6: "3795", 4: "3020", 2: "3022"}
    x, y = start
    end = x + length
    while x < end:
        size = next(candidate for candidate in plates if candidate <= end - x)
        builder.place(
            plates[size],
            at=(x, y, z),
            rotation="R0" if size == 2 else "R90",
            color=ROOF,
        )
        x += size


def battlements(
    builder: ModelBuilder, west: int, south: int, size: int, z: int
) -> None:
    """2 x 2 merlons on a tower's corners and every four studs between them."""
    spots = {(west + i, south) for i in range(0, size - 1, 4)}
    spots |= {(west + i, south + size - 2) for i in range(0, size - 1, 4)}
    spots |= {(west, south + i) for i in range(0, size - 1, 4)}
    spots |= {(west + size - 2, south + i) for i in range(0, size - 1, 4)}
    spots |= {(west + size - 2, south + size - 2)}
    for x, y in sorted(spots):
        builder.place("3003", at=(x, y, z), color=STONE)


def curtain(
    builder: ModelBuilder,
    start: Cell,
    length: int,
    *,
    along_x: bool,
    gate: range | None = None,
) -> None:
    """A wall two studs thick between towers: five courses, merlons every four studs."""
    start_x, start_y = start
    for course in range(5):
        z = 1 + 3 * course
        color = FOOTING if course == 0 else STONE
        gaps: set[Cell] = set()
        if gate is not None and course < 3:
            gaps = {(x, start_y) for x in gate}
        # Odd courses start half a brick in, so joints never line up.
        if course % 2 and length > 2:
            rest = (start_x + 1, start_y) if along_x else (start_x, start_y + 1)
            runs = [
                Run(start, 1, along_x=along_x),
                Run(rest, length - 1, along_x=along_x),
            ]
        else:
            runs = [Run(start, length, along_x=along_x)]
        for run in runs:
            strip(builder, run, z=z, color=color, gaps=gaps)
    for i in range(1, length - 1, 4):
        x, y = (start_x + i, start_y) if along_x else (start_x, start_y + i)
        builder.place("3003", at=(x, y, 16), color=STONE)


def keep(builder: ModelBuilder) -> None:
    """A tall hollow keep with a roof, battlements and a flag."""
    tower(builder, (15, 18), 10, 10, roof=True)
    roof_top = 1 + 3 * 10 + 1
    for z in range(roof_top, roof_top + 9, 3):  # flagpole: three Black 1 x 1 bricks
        builder.place("3005", at=(19, 22, z), color="Black")
    builder.place(
        "3004", at=(19, 22, roof_top + 9), rotation="R90", color="Blue"
    )  # the flag


def build() -> ModelBuilder:
    """Build the castle on its lawn."""
    builder = ModelBuilder("castle")
    # Lawn: 40 x 40 studs of Green 2 x 8 plates.
    for y in range(0, 40, 2):
        for x in range(0, 40, 8):
            builder.place("3034", at=(x, y, 0), rotation="R90", color="Green")
    for corner in ((0, 0), (32, 0), (0, 32), (32, 32)):
        tower(builder, corner, 8, 8)
    curtain(builder, (8, 4), 24, along_x=True, gate=range(18, 22))
    curtain(builder, (8, 34), 24, along_x=True)
    curtain(builder, (4, 8), 24, along_x=False)
    curtain(builder, (34, 8), 24, along_x=False)
    keep(builder)
    # A path from the gate to the keep.
    for y in range(0, 18, 2):
        builder.place("3020", at=(18, y, 1), rotation="R90", color="Tan")
    return builder
