"""The Elizabeth Tower (Big Ben) at roughly 1 stud to 1 m (about 1:125).

Prompt: "Build the Elizabeth Tower (Big Ben) in London."
References: Wikipedia, "Big Ben": 96 m tall, 12 m square base, four 6.9 m dials centred 54.9 m up,
gilded dial surrounds, a cast-iron spire, the Ayrton Light above the belfry.

The tower is drawn as voxels (one stud by one stud by one plate), then packed into bricks and
plates course by course. x runs along the south face, y along the east face, z is up in plates.
"""

from collections.abc import Callable

from bricky import ModelBuilder

STONE, BAND, GOLD = "Tan", "Dark Tan", "Yellow"
DARK, GLASS, DIAL, IRON = "Black", "Trans-Clear", "White", "Dark Bluish Gray"

BODY = range(1, 14)  # the shaft is 13 studs square
OUTER = range(15)  # projecting bands and the plinth add a stud all round
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
    (2, 8): "3007",
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


def ring(x: int, y: int, lo: int, hi: int, thickness: int = 1) -> bool:
    """Whether (x, y) lies in a square ring spanning lo..max-1 on both axes."""
    if not (lo <= x < hi and lo <= y < hi):
        return False
    return min(x - lo, y - lo, hi - 1 - x, hi - 1 - y) < thickness


def square(x: int, y: int, lo: int, hi: int) -> bool:
    return lo <= x < hi and lo <= y < hi


def face_u(x: int, y: int) -> int:
    """Position along whichever face of the body (x, y) sits on, 0..12 from that face's left."""
    if y == BODY.start:
        return x - BODY.start
    if y == BODY.stop - 1:
        return BODY.stop - 1 - x
    if x == BODY.start:
        return BODY.stop - 1 - y
    return y - BODY.start


def shaft(x: int, y: int, z: int) -> Color:
    if not ring(x, y, BODY.start, BODY.stop):
        return None
    u, floor = face_u(x, y), (z - 6) % 12
    if (z - 6) // 3 % 8 == 7:
        return BAND  # a darker course every eight
    if 3 <= floor < 9:
        if u == 6:
            return DARK  # a narrow window, two bricks tall, on every floor
        if u in {3, 9}:
            return BAND  # blind Gothic panels either side
    return STONE


def clock(x: int, y: int, z: int) -> Color:
    if not ring(x, y, BODY.start, BODY.stop):
        return None
    u = face_u(x, y)
    dx, dz = (u + 0.5 - 6.5) / 3.5, (z + 0.5 - 138.5) / 8.75
    d2 = dx * dx + dz * dz
    if d2 <= 1:
        if d2 > (2.5 / 3.5) ** 2:
            return DARK  # the dial's iron frame
        if (u == 6 and 138 <= z <= 144) or (z == 138 and 6 <= u <= 8):
            return DARK  # hands at three o'clock
        return DIAL
    if abs(u - 6) <= 3 and 129 <= z <= 147:
        return GOLD  # gilded spandrels round the dial
    if 2 <= u <= 10 and 125 <= z <= 126:
        return GOLD  # the gilded inscription under the dial
    return STONE


def belfry(x: int, y: int, z: int) -> Color:
    if not ring(x, y, BODY.start, BODY.stop):
        return None
    u = face_u(x, y)
    if u in {3, 4, 8, 9} and 162 <= z < 183:
        return DARK  # louvred openings onto the bells
    if z == 185:
        return GOLD  # the frieze of gilded shields
    return STONE


def spire(x: int, y: int, z: int) -> Color:
    if z < 195:  # the Ayrton Light: iron posts and glass round a solid core
        if square(x, y, 4, 11):
            return IRON
        if not ring(x, y, 3, 12):
            return None
        return IRON if (x + y) % 2 == 0 else GLASS
    for lo, z0, z1 in ((3, 195, 205), (4, 205, 214), (5, 214, 223), (6, 223, 232), (7, 232, 238)):
        if z0 <= z < z1:
            return IRON if square(x, y, lo, 15 - lo) else None
    return GOLD if (x, y) == (7, 7) else None  # the finial


def tower(x: int, y: int, z: int) -> Color:
    """Colour of the voxel at (x, y, z), or None for air."""
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
        return STONE  # corner pinnacles
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
    """Greedily cover same-coloured cells with the biggest parts that fit, scanning along one axis.

    Alternating the axis from course to course staggers the joints and interlocks the corners.
    Every part must rest on at least one cell of the layer below (``below=None`` means the ground),
    so overhanging bands are made of wide parts that reach back over the wall.
    """
    sizes = sorted(parts, key=lambda s: (s[1] * s[0], s[0], s[1]), reverse=True)
    free = dict(cells)

    def overhang(c: Cell) -> bool:
        return below is not None and c not in below

    def fits(span: list[Cell], color: str) -> bool:
        return all(free.get(c) == color for c in span) and (
            below is None or any(c in below for c in span)
        )

    def options(c: Cell) -> int:
        """How many placements could cover c: hard cells (overhang corners) go first."""
        return sum(
            fits([(c[0] - ox + i, c[1] - oy + j) for i in range(w) for j in range(n)], free[c])
            for short, long_ in parts
            for w, n in {(short, long_), (long_, short)}
            for ox in range(w)
            for oy in range(n)
        )

    scan = sorted(free, key=lambda c: (c[1], c[0]) if along_x else c)
    hard = sorted((c for c in scan if overhang(c)), key=options)
    order = hard + [c for c in scan if not overhang(c)]

    def place(start: Cell) -> None:
        color = free[start]
        for short, long_ in sizes:
            dims = ((long_, short), (short, long_)) if along_x else ((short, long_), (long_, short))
            for w, n in dims:
                for ox in range(w):  # any cell of the part may be the start cell
                    for oy in range(n):
                        x0, y0 = start[0] - ox, start[1] - oy
                        span = [(x0 + i, y0 + j) for i in range(w) for j in range(n)]
                        if fits(span, color):
                            rotation = "R0" if (w, n) == (short, long_) else "R90"
                            builder.place(
                                parts[short, long_],
                                at=(x0, y0, z),
                                rotation=rotation,
                                color=color,
                                id=f"{label}.{x0}.{y0}",
                            )
                            for c in span:
                                del free[c]
                            return

    for start in order:
        if start in free:
            place(start)
    if free:
        print(f"{label}: no part fits {len(free)} cell(s): {sorted(free)[:6]}")


def voxelize(color_at: Callable[[int, int, int], Color], top: int) -> list[dict[Cell, str]]:
    return [
        {(x, y): c for x in OUTER for y in OUTER if (c := color_at(x, y, z)) is not None}
        for z in range(top)
    ]


def build() -> ModelBuilder:
    builder = ModelBuilder("elizabeth_tower")
    layers = voxelize(tower, TOP)
    for course, z in enumerate(range(0, TOP, 3)):
        group = layers[z : z + 3]
        along_x = course % 2 == 0
        bricks = {}
        if len(group) == 3:
            bricks = {
                c: col
                for c, col in group[0].items()
                if group[1].get(c) == col and group[2].get(c) == col
            }
        pack(builder, bricks, z, BRICKS, along_x, f"b{z}", set(layers[z - 1]) if z else None)
        for k, layer in enumerate(group):
            plates = {c: col for c, col in layer.items() if c not in bricks}
            below = set(layers[z + k - 1]) if z + k else None
            if below is not None and z + k == ROOF:  # inner roof plates hang from the spire
                below |= {(x, y) for x in range(2, 13) for y in range(2, 13)}
            pack(builder, plates, z + k, PLATES, (course + k) % 2 == 0, f"p{z + k}", below)
    return builder
