"""A cottage on a baseplate: a tour of slopes, arches, round parts, side studs and jumpers.

- The baseplate is half a plate thick, so everything on it starts at z = 0.5.
- The walls are one stud thick, in running bond. An Arch 1 x 4, rotated to run along the front
  wall, spans the doorway.
- The roof is rows of Slope 45 2 x 4: unrotated they fall toward -y (the front), and rotated R180
  toward +y (the back). Tan bricks fill each level and show as the gables at the ends. Cheese
  slopes finish the ridge.
- A brick with a stud on its side holds a tile rotated upright: a house sign.
- A jumper puts the lamp post half a stud off the grid, centered on its 1 x 2 base.

Run: ``uv run bricky build examples/cottage.py``
"""

from bricky import ModelBuilder

BASE = 0.5  # the top of the baseplate, in plates
X0, X1 = 3, 13  # outer walls, west to east
Y0, Y1 = 4, 10  # outer walls, south (front) to north (back)
COURSES = 4
WALL = "Tan"
BRICKS = {4: "3010", 3: "3622", 2: "3004", 1: "3005"}


def opening(x: int, y: int, course: int) -> str | None:
    """What fills a wall cell instead of the wall: the doorway, a window, or the sign's brick."""
    front, back, side = y == Y0, y == Y1 - 1, x in {X0, X1 - 1}
    if front and 7 <= x < 9 and course < 2:
        return "door"
    if front and 6 <= x < 10 and course == 2:  # the arch's legs stand beside the door
        return "arch"
    if front and x == 11 and course == 1:
        return "sign"
    if (back and 5 <= x < 7) or (side and 6 <= y < 8):
        return "Trans-Light Blue" if course in {1, 2} else None
    return None


def lay(
    builder: ModelBuilder, cells: list[tuple[int, int]], along_x: bool, z: float, course: int
) -> None:
    """Fill a straight run of wall cells with bricks, one color at a time, longest first."""
    i = 0
    while i < len(cells):
        kind = opening(*cells[i], course)
        j = i + 1
        while j < len(cells) and opening(*cells[j], course) == kind:
            j += 1
        if kind in {None, "Trans-Light Blue"}:
            start = i
            while start < j:
                n = next(k for k in BRICKS if k <= j - start)
                x, y = cells[start]
                rotation = "R90" if along_x else "R0"
                builder.place(BRICKS[n], at=(x, y, z), rotation=rotation, color=kind or WALL)
                start += n
        i = j


def walls(builder: ModelBuilder) -> None:
    for course in range(COURSES):
        z = BASE + 3 * course
        full_x = course % 2 == 0
        xs = range(X0, X1) if full_x else range(X0 + 1, X1 - 1)
        ys = range(Y0 + 1, Y1 - 1) if full_x else range(Y0, Y1)
        for y in (Y0, Y1 - 1):
            lay(builder, [(x, y) for x in xs], along_x=True, z=z, course=course)
        for x in (X0, X1 - 1):
            lay(builder, [(x, y) for y in ys], along_x=False, z=z, course=course)
    # The doorway's arch: an Arch 1 x 4 rotated to run along x, its legs either side of the door.
    builder.place("3659", at=(6, Y0, BASE + 6), rotation="R90", color=WALL, id="door-arch")
    # The sign: a brick with a stud on its front, and a tile rotated upright onto that stud.
    builder.place("87087", at=(11, Y0, BASE + 3), color=WALL, id="sign-holder")
    builder.place("3070b", at=(11, Y0 - 0.4, BASE + 3.25), rotation="+x+z", color="Blue", id="sign")


def roof(builder: ModelBuilder) -> None:
    """Plates over the walls, then three levels of slopes and a ridge of cheese slopes."""
    z = BASE + 3 * COURSES
    for y in range(Y0 - 1, Y1 + 1, 2):  # a 12 x 8 plate layer, overhanging a stud all round
        builder.place("3034", at=(X0 - 1, y, z), rotation="R90", color="Dark Bluish Gray")
        builder.place("3020", at=(X0 + 7, y, z), rotation="R90", color="Dark Bluish Gray")
    z += 1
    lo, hi = Y0 - 1, Y1 + 1
    while True:
        for x in range(X0 - 1, X1 + 1, 4):
            builder.place("3037", at=(x, lo, z), color="Red")  # Slope 45 2 x 4, falls to -y
            builder.place("3037", at=(x, hi - 2, z), rotation="R180", color="Red")  # falls to +y
        if hi - lo == 4:
            break
        for x in range(X0 - 1, X1 + 1, 2):  # the gable: bricks the next level stands on
            for y in range(lo + 2, hi - 2, 2):
                builder.place("3003", at=(x, y, z), color=WALL)
        lo, hi, z = lo + 2, hi - 2, z + 3
    # The ridge: cheese slopes on the studs of the last two slopes' flat tops.
    for x in range(X0 - 1, X1 + 1):
        builder.place("54200", at=(x, lo + 1, z + 3), color="Red")  # falls to -y
        builder.place("54200", at=(x, hi - 2, z + 3), rotation="R180", color="Red")  # falls to +y


def garden(builder: ModelBuilder) -> None:
    for x in (7, 8):  # a path of tiles to the door
        for y in range(0, Y0, 2):
            builder.place("3069b", at=(x, y, BASE), color="Light Bluish Gray")  # Tile 1 x 2
    # A lamp post on a jumper, so it stands half a stud off the grid.
    builder.place("15573", at=(4, 1, BASE), color="Black")  # Jumper 1 x 2, along y
    for level in range(3):
        builder.place("3062b", at=(4, 1.5, BASE + 1 + 3 * level), color="Black")  # round brick
    builder.place("4073", at=(4, 1.5, BASE + 10), color="Trans-Yellow", id="lamp")
    # A round bush.
    builder.place("3941", at=(12, 1, BASE), color="Green")  # Brick, Round 2 x 2
    builder.place("4032", at=(12, 1, BASE + 3), color="Bright Light Orange")  # flowers


def build() -> ModelBuilder:
    builder = ModelBuilder("cottage")
    builder.place("3867", at=(0, 0, 0), color="Green", id="baseplate")  # Baseplate 16 x 16
    walls(builder)
    roof(builder)
    garden(builder)
    return builder
