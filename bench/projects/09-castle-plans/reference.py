"""Reference for project 09: a castle with four corner towers, a gatehouse and a keep.

Walls are two studs thick and laid in running bond. Hollow towers interlock at their corners:
on even courses the walls along x run the full width, on odd courses the walls along y do.
"""

from collections.abc import Set as AbstractSet

from bricky import ModelBuilder

STONE = "Light Bluish Gray"
FOOTING = "Dark Bluish Gray"
ROOF = "Dark Bluish Gray"
# Bricks two studs wide by length, longest first; a 1 x 2 brick fills a single cell of a strip.
STRIP = {8: "3007", 6: "2456", 4: "3001", 3: "3002", 2: "3003", 1: "3004"}

type Cell = tuple[int, int]


def strip(
    builder: ModelBuilder,
    start: Cell,
    length: int,
    *,
    along_x: bool,
    z: int,
    color: str,
    gaps: AbstractSet[Cell] = frozenset(),
) -> None:
    """Fill a strip two studs wide, from ``start`` along x or y, skipping gap cells.

    A gap cell removes the strip's whole width at that position along it.
    """
    x0, y0 = start
    cells = [(x0 + i, y0) if along_x else (x0, y0 + i) for i in range(length)]
    i = 0
    while i < length:
        if cells[i] in gaps:
            i += 1
            continue
        j = i
        while j < length and cells[j] not in gaps:
            j += 1
        while i < j:
            n = next(k for k in STRIP if k <= j - i)
            x, y = cells[i]
            if n == 1:  # a 1 x 2 brick lies across the strip
                builder.place(STRIP[1], at=(x, y, z), rot="R0" if along_x else "R90", color=color)
            else:
                builder.place(STRIP[n], at=(x, y, z), rot="R90" if along_x else "R0", color=color)
            i += n


def tower(
    builder: ModelBuilder,
    x0: int,
    y0: int,
    size: int,
    courses: int,
    *,
    slits: bool,
    roof: bool = False,
) -> None:
    """A hollow square tower, walls two studs thick, crenellated on top, roofed if asked."""
    x1, y1 = x0 + size, y0 + size
    for course in range(courses):
        z = 1 + 3 * course
        color = FOOTING if course == 0 else STONE
        gaps: set[Cell] = set()
        if slits and course in {4, 5}:
            middle = size // 2 - 1
            gaps = {
                (x0 + middle, y0),
                (x0, y0 + middle),
                (x1 - 2, y0 + middle),
                (x0 + middle, y1 - 2),
            }
        if course % 2 == 0:
            strip(builder, (x0, y0), size, along_x=True, z=z, color=color, gaps=gaps)
            strip(builder, (x0, y1 - 2), size, along_x=True, z=z, color=color, gaps=gaps)
            strip(builder, (x0, y0 + 2), size - 4, along_x=False, z=z, color=color, gaps=gaps)
            strip(builder, (x1 - 2, y0 + 2), size - 4, along_x=False, z=z, color=color, gaps=gaps)
        else:
            strip(builder, (x0, y0), size, along_x=False, z=z, color=color, gaps=gaps)
            strip(builder, (x1 - 2, y0), size, along_x=False, z=z, color=color, gaps=gaps)
            strip(builder, (x0 + 2, y0), size - 4, along_x=True, z=z, color=color, gaps=gaps)
            strip(builder, (x0 + 2, y1 - 2), size - 4, along_x=True, z=z, color=color, gaps=gaps)
    top = 1 + 3 * courses
    if roof:
        # Rows of plates across the whole tower, so the roof rests on all four walls.
        for y in range(y0, y1, 2):
            strip_plates(builder, (x0, y), size, top)
        top += 1
    battlements(builder, x0, y0, size, top)


def strip_plates(builder: ModelBuilder, start: Cell, length: int, z: int) -> None:
    """A row of plates two studs deep along x: 2 x 8, 2 x 4 and 2 x 2 plates, longest first."""
    plates = {8: "3034", 6: "3795", 4: "3020", 2: "3022"}
    x, y = start
    end = x + length
    while x < end:
        n = next(k for k in plates if k <= end - x)
        builder.place(plates[n], at=(x, y, z), rot="R0" if n == 2 else "R90", color=ROOF)
        x += n


def battlements(builder: ModelBuilder, x0: int, y0: int, size: int, z: int) -> None:
    """2 x 2 merlons on a tower's corners and every four studs between them."""
    spots = {(x0 + i, y0) for i in range(0, size - 1, 4)}
    spots |= {(x0 + i, y0 + size - 2) for i in range(0, size - 1, 4)}
    spots |= {(x0, y0 + i) for i in range(0, size - 1, 4)}
    spots |= {(x0 + size - 2, y0 + i) for i in range(0, size - 1, 4)}
    spots |= {(x0 + size - 2, y0 + size - 2)}
    for x, y in sorted(spots):
        builder.place("3003", at=(x, y, z), color=STONE)


def curtain(
    builder: ModelBuilder, start: Cell, length: int, *, along_x: bool, gate: range | None = None
) -> None:
    """A wall two studs thick between two towers: five courses, merlons every four studs."""
    x0, y0 = start
    for course in range(5):
        z = 1 + 3 * course
        color = FOOTING if course == 0 else STONE
        gaps: set[Cell] = set()
        if gate is not None and course < 3:
            gaps = {(x, y0) for x in gate}
        # Odd courses start half a brick in, so joints never line up.
        if course % 2 and length > 2:
            first = (x0 + 1, y0) if along_x else (x0, y0 + 1)
            strip(builder, start, 1, along_x=along_x, z=z, color=color, gaps=gaps)
            strip(builder, first, length - 1, along_x=along_x, z=z, color=color, gaps=gaps)
        else:
            strip(builder, start, length, along_x=along_x, z=z, color=color, gaps=gaps)
    for i in range(1, length - 1, 4):
        x, y = (x0 + i, y0) if along_x else (x0, y0 + i)
        builder.place("3003", at=(x, y, 16), color=STONE)


def keep(builder: ModelBuilder) -> None:
    """A tall hollow keep with a roof, battlements and a flag."""
    tower(builder, 15, 18, 10, 10, slits=True, roof=True)
    roof_top = 1 + 3 * 10 + 1
    for z in range(roof_top, roof_top + 9, 3):  # flagpole: three Black 1 x 1 bricks
        builder.place("3005", at=(19, 22, z), color="Black")
    builder.place("3004", at=(19, 22, roof_top + 9), rot="R90", color="Blue")  # the flag


def build() -> ModelBuilder:
    builder = ModelBuilder("castle")
    # Lawn: 40 x 40 studs of Green 2 x 8 plates.
    for y in range(0, 40, 2):
        for x in range(0, 40, 8):
            builder.place("3034", at=(x, y, 0), rot="R90", color="Green")
    for x0, y0 in ((0, 0), (32, 0), (0, 32), (32, 32)):
        tower(builder, x0, y0, 8, 8, slits=True)
    curtain(builder, (8, 4), 24, along_x=True, gate=range(18, 22))
    curtain(builder, (8, 34), 24, along_x=True)
    curtain(builder, (4, 8), 24, along_x=False)
    curtain(builder, (34, 8), 24, along_x=False)
    keep(builder)
    # A path from the gate to the keep.
    for y in range(0, 18, 2):
        builder.place("3020", at=(18, y, 1), rot="R90", color="Tan")
    return builder
