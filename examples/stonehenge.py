"""Stonehenge as it stands today, at roughly 1 stud to 1 m (about 1:125).

Prompt: "Build Stonehenge as it stands today."

Model north (+y) is the solstice axis, which runs north-east in reality. The horseshoe opens toward
+y and the Heel Stone sits near the north edge of the base. Stone numbers follow the usual scheme:
sarsen uprights 1-30 clockwise from the entrance, trilithon uprights 51-60.
"""

import itertools
import math

from bricky import ModelBuilder

WIDTH, DEPTH = 40, 48  # base, in studs
CX, CY = 20, 20  # centre of the circle
GROUND = 1  # top of the base plates, in plates
BRICK = 3  # plates per brick

SARSEN = "Light Bluish Gray"
BLUESTONE = "Dark Bluish Gray"

# Sarsen circle.
SARSEN_RADIUS = 15
STANDING = {1, 2, 3, 4, 5, 6, 7, 10, 11, 16, 21, 22, 23, 27, 28, 29, 30}
SHORT = {11}  # stone 11 is a stump about half the height of the rest
LINTELS = [(30, 1), (1, 2), (2, 3), (5, 6), (6, 7), (21, 22)]
FALLEN = [8, 9, 12, 14, 15, 19, 25, 26]  # lie outward from their sockets
UPRIGHT_BRICKS = 3

# Plates by (short side, long side), as listed by `bricky parts plate`.
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


def snap(value: float) -> int:
    """Round half up (Python's round() rounds half to even)."""
    return math.floor(value + 0.5)


def angle(stone: int) -> float:
    """Angle of a sarsen stone, in radians anticlockwise from +x; stone 1 is just east of +y."""
    return math.radians(90 - 12 * (stone - 0.5))


def base(builder: ModelBuilder) -> None:
    for x in range(0, WIDTH, 2):
        for y in range(0, DEPTH, 8):
            builder.place("3034", at=(x, y, 0), color="Green", name=f"grass.{x}.{y}")


def sarsen_cells(stone: int, along_y: bool) -> list[Cell]:
    a = angle(stone)
    cx, cy = CX + SARSEN_RADIUS * math.cos(a), CY + SARSEN_RADIUS * math.sin(a)
    if along_y:
        x0, y0 = math.floor(cx), snap(cy - 1)
        return [(x0, y0), (x0, y0 + 1)]
    x0, y0 = snap(cx - 1), math.floor(cy)
    return [(x0, y0), (x0 + 1, y0)]


def lintel_box(a: list[Cell], b: list[Cell]) -> tuple[Cell, int, int] | None:
    """The smallest plate box joining the nearest top studs of two uprights, if a plate fits."""
    ca, cb = min(
        ((p, q) for p in a for q in b),
        key=lambda pq: (pq[0][0] - pq[1][0]) ** 2 + (pq[0][1] - pq[1][1]) ** 2,
    )
    x0, y0 = min(ca[0], cb[0]), min(ca[1], cb[1])
    w, n = abs(ca[0] - cb[0]) + 1, abs(ca[1] - cb[1]) + 1
    if (min(w, n), max(w, n)) not in PLATES:
        return None
    return (x0, y0), w, n


def box_cells(box: tuple[Cell, int, int]) -> set[Cell]:
    (x0, y0), w, n = box
    return {(x, y) for x in range(x0, x0 + w) for y in range(y0, y0 + n)}


def orientations() -> dict[int, bool]:
    """Choose each standing stone's orientation.

    Stones face along the circle's tangent, except for the fewest flips that let every lintel fit
    without two lintels sharing a stud.
    """
    tangent = {s: abs(math.cos(angle(s))) > abs(math.sin(angle(s))) for s in STANDING}
    involved = sorted({s for pair in LINTELS for s in pair})
    best: tuple[int, dict[int, bool]] | None = None
    for flips in itertools.product((False, True), repeat=len(involved)):
        trial = dict(tangent)
        for stone, flip in zip(involved, flips, strict=True):
            trial[stone] ^= flip
        boxes = [
            lintel_box(sarsen_cells(a, trial[a]), sarsen_cells(b, trial[b])) for a, b in LINTELS
        ]
        if any(box is None for box in boxes):
            continue
        cells = [box_cells(box) for box in boxes if box is not None]
        if sum(map(len, cells)) != len(set().union(*cells)):
            continue
        if best is None or sum(flips) < best[0]:
            best = (sum(flips), trial)
    if best is None:
        print("no orientation lets every lintel fit; using tangents")
        return tangent
    return best[1]


def sarsen_circle(builder: ModelBuilder) -> None:
    along_y = orientations()
    tops = {}
    for stone in sorted(STANDING):
        cells = sarsen_cells(stone, along_y[stone])
        x0, y0 = cells[0]
        bricks = 2 if stone in SHORT else UPRIGHT_BRICKS
        for level in range(bricks):
            builder.place(
                "3004",
                at=(x0, y0, GROUND + BRICK * level),
                rot="R0" if along_y[stone] else "R90",
                color=SARSEN,
                name=f"sarsen{stone}.{level}",
            )
        tops[stone] = cells
    for a, b in LINTELS:
        box = lintel_box(tops[a], tops[b])
        if box is None:
            print(f"no plate fits lintel {a}-{b}; leaving it out")
            continue
        (x0, y0), w, n = box
        part = PLATES[min(w, n), max(w, n)]
        builder.place(
            part,
            at=(x0, y0, GROUND + BRICK * UPRIGHT_BRICKS),
            rot="R0" if n >= w else "R90",
            color=SARSEN,
            name=f"lintel{a}-{b}",
        )
    for stone in FALLEN:
        a = angle(stone)
        dx, dy = math.cos(a), math.sin(a)
        if abs(dx) > abs(dy):  # lies along x, outward
            x = CX + SARSEN_RADIUS + 1 if dx > 0 else CX - SARSEN_RADIUS - 5
            builder.place(
                "3001",
                at=(x, snap(CY + SARSEN_RADIUS * dy - 1), GROUND),
                rot="R90",
                color=SARSEN,
                name=f"fallen{stone}",
            )
        else:  # lies along y, outward
            y = CY + SARSEN_RADIUS + 1 if dy > 0 else CY - SARSEN_RADIUS - 5
            builder.place(
                "3001",
                at=(snap(CX + SARSEN_RADIUS * dx - 1), y, GROUND),
                color=SARSEN,
                name=f"fallen{stone}",
            )


def trilithon(builder: ModelBuilder) -> None:
    """Two 5-brick uprights with a 1 x 6 brick lintel, laid along local x."""
    component = builder.component("trilithon")
    for side, x in (("a", 0), ("b", 4)):
        for level in range(5):
            component.place(
                "3004",
                at=(x, 0, BRICK * level),
                rot="R90",
                color=SARSEN,
                name=f"upright{side}.{level}",
            )
    component.place("3009", at=(0, 0, BRICK * 5), rot="R90", color=SARSEN, name="lintel")


def upright(builder: ModelBuilder, name: str, corner: Cell, along_y: bool, bricks: int) -> None:
    for level in range(bricks):
        builder.place(
            "3004",
            at=(*corner, GROUND + BRICK * level),
            rot="R0" if along_y else "R90",
            color=SARSEN,
            name=f"{name}.{level}",
        )


def horseshoe(builder: ModelBuilder) -> None:
    trilithon(builder)
    # Trilithons stand along y on the sides of the horseshoe: turn the component a quarter.
    builder.instance("trilithon", at=(27, 21, GROUND), rot="R90", name="tri51-52")
    builder.instance("trilithon", at=(26, 13, GROUND), rot="R90", name="tri53-54")
    builder.instance("trilithon", at=(13, 13, GROUND), rot="R90", name="tri57-58")
    upright(builder, "stone60", (12, 25), along_y=True, bricks=5)
    builder.place("2456", at=(15, 24, GROUND), color=SARSEN, name="fallen59")
    builder.place("3009", at=(10, 15, GROUND), color=SARSEN, name="lintel160")
    # The Great Trilithon: 56 stands; 55 fell in two across the Altar Stone, with lintel 156.
    upright(builder, "stone56", (17, 12), along_y=False, bricks=6)
    builder.place("3710", at=(18, 16, GROUND), rot="R90", color=BLUESTONE, name="altar")
    builder.place("3002", at=(20, 14, GROUND + 1), color=SARSEN, name="fallen55a")
    builder.place("3003", at=(22, 15, GROUND), color=SARSEN, name="fallen55b")
    builder.place("3009", at=(15, 18, GROUND), rot="R90", color=SARSEN, name="lintel156")


def bluestones(builder: ModelBuilder) -> None:
    # Outer circle: 1 x 1 stones at radius 11.5, with gaps where stones are lost.
    for k in range(36):
        if k % 4 == 3 or k in {8, 9, 26}:
            continue
        a = math.radians(5 + 10 * k)
        x, y = snap(CX + 11.5 * math.cos(a) - 0.5), snap(CY + 11.5 * math.sin(a) - 0.5)
        for level in range(1 + (k % 3 == 0)):
            builder.place(
                "3005", at=(x, y, GROUND + BRICK * level), color=BLUESTONE, name=f"blue{k}.{level}"
            )
    # Inner horseshoe: taller dressed pillars at radius 6, opening north.
    for k, degrees in enumerate((150, 170, 195, 345, 10, 30)):
        a = math.radians(degrees)
        x, y = snap(CX + 6 * math.cos(a) - 0.5), snap(CY + 6 * math.sin(a) - 0.5)
        for level in range(2):
            builder.place(
                "3005",
                at=(x, y, GROUND + BRICK * level),
                color=BLUESTONE,
                name=f"pillar{k}.{level}",
            )


def outliers(builder: ModelBuilder) -> None:
    for level in range(4):  # the Heel Stone, just east of the axis
        builder.place(
            "3003", at=(22, 43, GROUND + BRICK * level), color=SARSEN, name=f"heel.{level}"
        )
    builder.place("3020", at=(17, 38, GROUND), rot="R90", color=SARSEN, name="slaughter")


def build() -> ModelBuilder:
    builder = ModelBuilder("stonehenge")
    base(builder)
    sarsen_circle(builder)
    horseshoe(builder)
    bluestones(builder)
    outliers(builder)
    return builder
