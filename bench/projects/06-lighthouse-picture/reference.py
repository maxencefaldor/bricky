# Copyright 2026 Maxence Faldor
"""Reference for project 06: a striped lighthouse on a rocky islet.

The tower is two hollow square shafts, one stud thick: 6 x 6 studs for eight courses, then 4 x 4
for four, striped Red and White every two courses. A Black gallery with a railing rings the top,
a Trans-Yellow lantern sits inside it, and a Red roof with a Black finial caps the lantern.
"""

from bricky import ModelBuilder

ROCK = "Dark Bluish Gray"
STONE = "Light Bluish Gray"
BRICKS = {4: "3010", 3: "3622", 2: "3004", 1: "3005"}


def ring(
    builder: ModelBuilder, start: int, stop: int, z: int, course: int, color: str
) -> None:
    """One course of a hollow square shaft, one stud thick.

    The shaft spans ``start`` to ``stop - 1`` in both x and y. Corners alternate between the walls
    along x and the walls along y, so courses interlock.
    """
    full_x = course % 2 == 0
    xs = range(start, stop) if full_x else range(start + 1, stop - 1)
    ys = range(start + 1, stop - 1) if full_x else range(start, stop)
    for y in (start, stop - 1):
        run(builder, [(x, y) for x in xs], along_x=True, z=z, color=color)
    for x in (start, stop - 1):
        run(builder, [(x, y) for y in ys], along_x=False, z=z, color=color)


def run(
    builder: ModelBuilder,
    cells: list[tuple[int, int]],
    along_x: bool,
    z: int,
    color: str,
) -> None:
    """Fill a straight run of cells with 1 x N bricks, longest first."""
    i = 0
    while i < len(cells):
        length = next(size for size in BRICKS if size <= len(cells) - i)
        x, y = cells[i]
        builder.place(
            BRICKS[length],
            at=(x, y, z),
            rotation="R90" if along_x else "R0",
            color=color,
        )
        i += length


def islet(builder: ModelBuilder) -> None:
    """A 14 x 14 base of plates, two layers, with boulders around the shore."""
    for y in range(0, 14, 2):
        builder.place("3034", at=(0, y, 0), rotation="R90", color=ROCK)
        builder.place("3021", at=(8, y, 0), rotation="R90", color=ROCK)
        builder.place("3021", at=(11, y, 0), rotation="R90", color=ROCK)
    for x in range(0, 14, 2):
        builder.place("3034", at=(x, 0, 1), color=ROCK)
        builder.place("3022", at=(x, 8, 1), color=ROCK)
        builder.place("3022", at=(x, 10, 1), color=ROCK)
        builder.place("3022", at=(x, 12, 1), color=ROCK)
    for x, y, color in (
        (0, 2, STONE),
        (1, 9, ROCK),
        (11, 0, STONE),
        (12, 11, STONE),
        (5, 12, ROCK),
    ):
        builder.place("3003", at=(x, y, 2), color=color)


def build() -> ModelBuilder:
    """Build the lighthouse on its islet."""
    builder = ModelBuilder("lighthouse")
    islet(builder)
    # Lower shaft: 6 x 6, from x and y 4 to 10, eight courses; a Reddish Brown door at the front.
    for course in range(8):
        z = 2 + 3 * course
        color = "Red" if course // 2 % 2 == 0 else "White"
        ring(builder, 4, 10, z, course, color)
    builder.place(
        "3004", at=(6, 3, 2), rotation="R90", color="Reddish Brown"
    )  # door step
    # Upper shaft: 4 x 4, from 5 to 9, four courses, on a plate collar.
    collar_z = 2 + 3 * 8
    for y in (4, 6, 8):
        builder.place(
            "3795", at=(4, y, collar_z), rotation="R90", color="Black"
        )  # Plate 2 x 6
    for course in range(4):
        z = collar_z + 1 + 3 * course
        color = "Red" if (course + 8) // 2 % 2 == 0 else "White"
        ring(builder, 5, 9, z, course, color)
    # Gallery: an 8 x 8 Black deck of two crossed layers of 1 x 8 plates, so the rows that
    # overhang the shaft hold on to the rows above them, with a railing of 1 x 1 bricks.
    deck_z = collar_z + 1 + 3 * 4
    for line in range(3, 11):
        builder.place(
            "3460", at=(3, line, deck_z), rotation="R90", color="Black"
        )  # Plate 1 x 8
        builder.place("3460", at=(line, 3, deck_z + 1), color="Black")
    top = deck_z + 2
    for x in range(3, 11):
        for y in (3, 10):
            if x % 2 == 1:
                builder.place("3005", at=(x, y, top), color="Black")
    for y in (5, 7):
        for x in (3, 10):
            builder.place("3005", at=(x, y, top), color="Black")
    # Lantern: a hollow 4 x 4 ring of Trans-Yellow, two courses.
    for course in range(2):
        ring(builder, 5, 9, top + 3 * course, course, "Trans-Yellow")
    # Roof: Red plates stepping in, then a 2 x 2 brick and a Black finial.
    roof_z = top + 3 * 2
    builder.place("3020", at=(5, 5, roof_z), color="Red")
    builder.place("3020", at=(7, 5, roof_z), color="Red")
    builder.place("3022", at=(6, 6, roof_z + 1), color="Red")
    builder.place("3003", at=(6, 6, roof_z + 2), color="Red")
    builder.place("3005", at=(6, 6, roof_z + 5), color="Black")
    return builder
