"""Reference for project 04: a small house with a door, glazed windows, a flat roof and a chimney.

The walls are one stud thick and five bricks tall, laid in running bond with interlocking corners:
on even courses the front and back walls run the full width, on odd courses the side walls run the
full depth.
"""

from bricky import ModelBuilder

X0, X1 = 2, 14  # outer walls, west to east
Y0, Y1 = 2, 10  # outer walls, south (front) to north (back)
COURSES = 5
WALL = "White"
GLASS = "Trans-Light Blue"
DOOR = "Reddish Brown"

# Bricks by length, longest first; each lies along its wall.
BRICKS = {8: "3008", 6: "3009", 4: "3010", 3: "3622", 2: "3004", 1: "3005"}


def opening(x: int, y: int, course: int) -> str | None:
    """The colour of a door or window cell, if the cell is in one."""
    front, back, west, east = y == Y0, y == Y1 - 1, x == X0, x == X1 - 1
    if front and 7 <= x < 9 and course <= 2:
        return DOOR
    windows = (
        (front and (3 <= x < 5 or 11 <= x < 13))
        or (back and (5 <= x < 7 or 9 <= x < 11))
        or ((west or east) and 5 <= y < 7)
    )
    if windows and course in {1, 2}:
        return GLASS
    return None


def lay(
    builder: ModelBuilder, cells: list[tuple[int, int]], along_x: bool, z: int, course: int
) -> None:
    """Fill a straight run of wall cells with bricks, one colour at a time, longest first."""
    i = 0
    while i < len(cells):
        color = opening(*cells[i], course) or WALL
        j = i
        while j < len(cells) and (opening(*cells[j], course) or WALL) == color:
            j += 1
        start = i
        while start < j:
            length = next(n for n in BRICKS if n <= j - start)
            x, y = cells[start]
            builder.place(
                BRICKS[length], at=(x, y, z), rotation="R90" if along_x else "R0", color=color
            )
            start += length
        i = j


def walls(builder: ModelBuilder) -> None:
    for course in range(COURSES):
        z = 1 + 3 * course
        full_x = course % 2 == 0
        xs = range(X0, X1) if full_x else range(X0 + 1, X1 - 1)
        ys = range(Y0 + 1, Y1 - 1) if full_x else range(Y0, Y1)
        for y in (Y0, Y1 - 1):
            lay(builder, [(x, y) for x in xs], along_x=True, z=z, course=course)
        for x in (X0, X1 - 1):
            lay(builder, [(x, y) for y in ys], along_x=False, z=z, course=course)


def build() -> ModelBuilder:
    builder = ModelBuilder("house")
    # Lawn: Green 2 x 8 plates, 16 x 12 studs.
    for y in range(0, 12, 2):
        for x in (0, 8):
            builder.place("3034", at=(x, y, 0), rotation="R90", color="Green")
    # Doorstep.
    builder.place("3023", at=(7, 1, 1), rotation="R90", color="Light Bluish Gray")
    walls(builder)
    # Roof: Dark Bluish Gray plates, 12 x 8 studs, on top of the walls.
    roof_z = 1 + 3 * COURSES
    for y in range(Y0, Y1, 2):
        builder.place("3034", at=(X0, y, roof_z), rotation="R90", color="Dark Bluish Gray")
        builder.place("3020", at=(X0 + 8, y, roof_z), rotation="R90", color="Dark Bluish Gray")
    # Chimney: two courses of Red 2 x 2 bricks.
    for course in range(2):
        builder.place("3003", at=(10, 6, roof_z + 1 + 3 * course), color="Red")
    return builder
