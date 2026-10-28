"""The Elizabeth Tower (Big Ben) at roughly 1 stud to 1 m (about 1:125).

Prompt: "Build the Elizabeth Tower (Big Ben) in London."
References: Wikipedia, "Big Ben": 96 m tall, 12 m square base, four 6.9 m dials centered 54.9 m up,
gilded dial surrounds, a cast-iron spire, the Ayrton Light above the belfry.

The script draws the tower as voxels, one stud square and one plate tall, then packs them into
bricks and plates course by course. x runs along the south face, y along the east face, and z
points up, in plates.
"""

from collections.abc import Callable

from bricky import ModelBuilder

STONE, BAND, GOLD = "Tan", "Dark Tan", "Yellow"
DARK, GLASS, DIAL, IRON = "Black", "Trans-Clear", "White", "Dark Bluish Gray"

BODY = range(1, 14)  # the shaft is 13 studs square
OUTER = range(15)  # projecting bands and the plinth add a stud all around
TOP = 241  # plates
ROOF = 188

BRICKS = {
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
}
PLATES = {
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
}

type Cell = tuple[int, int]
type Color = str | None


def ring(x: int, y: int, start: int, stop: int, thickness: int = 1) -> bool:
    """Whether (x, y) lies in a square ring from ``start`` to ``stop - 1`` on both axes."""
    if not (start <= x < stop and start <= y < stop):
        return False
    return min(x - start, y - start, stop - 1 - x, stop - 1 - y) < thickness


def square(x: int, y: int, start: int, stop: int) -> bool:
    """Whether (x, y) lies in the square from ``start`` to ``stop - 1`` on both axes."""
    return start <= x < stop and start <= y < stop


def along_face(x: int, y: int) -> int:
    """Position along whichever face of the body (x, y) sits on, 0 to 12 from that face's left."""
    if y == BODY.start:
        return x - BODY.start
    if y == BODY.stop - 1:
        return BODY.stop - 1 - x
    if x == BODY.start:
        return BODY.stop - 1 - y
    return y - BODY.start


def shaft(x: int, y: int, z: int) -> Color:
    """The shaft: stone floors with darker courses, windows and panels."""
    if not ring(x, y, BODY.start, BODY.stop):
        return None
    along, floor = along_face(x, y), (z - 6) % 12
    if (z - 6) // 3 % 8 == 7:
        return BAND  # a darker course every eight
    if 3 <= floor < 9:
        if along == 6:
            return DARK  # a narrow window, two bricks tall, on every floor
        if along in {3, 9}:
            return BAND  # blind Gothic panels on either side
    return STONE


def clock(x: int, y: int, z: int) -> Color:
    """The clock stage: a dial on each face, framed in gold."""
    if not ring(x, y, BODY.start, BODY.stop):
        return None
    along = along_face(x, y)
    horizontal, vertical = (along + 0.5 - 6.5) / 3.5, (z + 0.5 - 138.5) / 8.75
    radius_squared = horizontal * horizontal + vertical * vertical
    if radius_squared <= 1:
        if radius_squared > (2.5 / 3.5) ** 2:
            return DARK  # the dial's iron frame
        if (along == 6 and 138 <= z <= 144) or (z == 138 and 6 <= along <= 8):
            return DARK  # hands at three o'clock
        return DIAL
    if abs(along - 6) <= 3 and 129 <= z <= 147:
        return GOLD  # gilded spandrels around the dial
    if 2 <= along <= 10 and 125 <= z <= 126:
        return GOLD  # the gilded inscription under the dial
    return STONE


def belfry(x: int, y: int, z: int) -> Color:
    """The belfry: louvered openings under a frieze of gilded shields."""
    if not ring(x, y, BODY.start, BODY.stop):
        return None
    along = along_face(x, y)
    if along in {3, 4, 8, 9} and 162 <= z < 183:
        return DARK  # louvered openings onto the bells
    if z == 185:
        return GOLD  # the frieze of gilded shields
    return STONE


def spire(x: int, y: int, z: int) -> Color:
    """The Ayrton Light, the iron spire in steps, and the finial."""
    if z < 195:  # the Ayrton Light: iron posts and glass around a solid core
        if square(x, y, 4, 11):
            return IRON
        if not ring(x, y, 3, 12):
            return None
        return IRON if (x + y) % 2 == 0 else GLASS
    for inset, bottom, top in (
        (3, 195, 205),
        (4, 205, 214),
        (5, 214, 223),
        (6, 223, 232),
        (7, 232, 238),
    ):
        if bottom <= z < top:
            return IRON if square(x, y, inset, 15 - inset) else None
    return GOLD if (x, y) == (7, 7) else None  # the finial


def tower(x: int, y: int, z: int) -> Color:
    """Color of the voxel at (x, y, z), or None for air."""
    if z < 6:
        return BAND if ring(x, y, OUTER.start, OUTER.stop, thickness=2) else None  # plinth
    if z < 120:
        return shaft(x, y, z)
    if z in {120, 157}:
        return BAND if ring(x, y, OUTER.start, OUTER.stop, thickness=2) else None  # string courses
    if z < 157:
        return clock(x, y, z)
    if z < 188:
        return belfry(x, y, z)
    if z == 188:
        return BAND if square(x, y, OUTER.start, OUTER.stop) else None  # cornice and roof
    corner = x in {1, 13} and y in {1, 13}  # pinnacles over the corner buttresses
    if corner and z < 201:
        return STONE
    if corner and z == 201:
        return GOLD
    return spire(x, y, z)


def pack(
    builder: ModelBuilder,
    cells: dict[Cell, str],
    z: int,
    parts: dict[tuple[int, int], str],
    along_x: bool,
    label: str,
    below: set[Cell] | None,
) -> None:
    """Greedily cover same-colored cells with the biggest parts that fit, scanning along one axis.

    Alternating the axis from course to course staggers the joints and interlocks the corners.
    Every part rests on at least one cell of the layer below (``below=None`` means the ground), so
    overhanging bands take wide parts that reach back over the wall.
    """
    sizes = sorted(parts, key=lambda size: (size[1] * size[0], size[0], size[1]), reverse=True)
    free = dict(cells)

    def overhang(cell: Cell) -> bool:
        return below is not None and cell not in below

    def fits(span: list[Cell], color: str) -> bool:
        return all(free.get(cell) == color for cell in span) and (
            below is None or any(cell in below for cell in span)
        )

    def options(cell: Cell) -> int:
        """How many placements could cover ``cell``; the cells with fewest go first."""
        return sum(
            fits(
                [
                    (cell[0] - offset_x + i, cell[1] - offset_y + j)
                    for i in range(width)
                    for j in range(depth)
                ],
                free[cell],
            )
            for short, long in parts
            for width, depth in {(short, long), (long, short)}
            for offset_x in range(width)
            for offset_y in range(depth)
        )

    scan = sorted(free, key=lambda cell: (cell[1], cell[0]) if along_x else cell)
    hard = sorted((cell for cell in scan if overhang(cell)), key=options)
    order = hard + [cell for cell in scan if not overhang(cell)]

    def place(start: Cell) -> None:
        color = free[start]
        for short, long in sizes:
            footprints = (
                ((long, short), (short, long)) if along_x else ((short, long), (long, short))
            )
            for width, depth in footprints:
                for offset_x in range(width):  # any cell of the part may be the start cell
                    for offset_y in range(depth):
                        corner_x, corner_y = start[0] - offset_x, start[1] - offset_y
                        span = [
                            (corner_x + i, corner_y + j) for i in range(width) for j in range(depth)
                        ]
                        if fits(span, color):
                            rotation = "R0" if (width, depth) == (short, long) else "R90"
                            builder.place(
                                parts[short, long],
                                at=(corner_x, corner_y, z),
                                rotation=rotation,
                                color=color,
                                id=f"{label}.{corner_x}.{corner_y}",
                            )
                            for cell in span:
                                del free[cell]
                            return

    for start in order:
        if start in free:
            place(start)
    if free:
        print(f"{label}: no part fits {len(free)} cell(s): {sorted(free)[:6]}")


def voxelize(color_at: Callable[[int, int, int], Color], top: int) -> list[dict[Cell, str]]:
    """The colored cells of every plate level from the ground up to ``top``."""
    return [
        {(x, y): color for x in OUTER for y in OUTER if (color := color_at(x, y, z)) is not None}
        for z in range(top)
    ]


def build() -> ModelBuilder:
    """Pack the tower's voxels into bricks where three levels agree, and plates elsewhere."""
    builder = ModelBuilder("elizabeth_tower")
    layers = voxelize(tower, TOP)
    for course, z in enumerate(range(0, TOP, 3)):
        course_layers = layers[z : z + 3]
        along_x = course % 2 == 0
        bricks = {}
        if len(course_layers) == 3:
            bricks = {
                cell: color
                for cell, color in course_layers[0].items()
                if course_layers[1].get(cell) == color and course_layers[2].get(cell) == color
            }
        pack(builder, bricks, z, BRICKS, along_x, f"b{z}", set(layers[z - 1]) if z else None)
        for offset, layer in enumerate(course_layers):
            level = z + offset
            plates = {cell: color for cell, color in layer.items() if cell not in bricks}
            below = set(layers[level - 1]) if level else None
            if below is not None and level == ROOF:  # inner roof plates hang from the spire
                below |= {(x, y) for x in range(2, 13) for y in range(2, 13)}
            pack(builder, plates, level, PLATES, (course + offset) % 2 == 0, f"p{level}", below)
    return builder
