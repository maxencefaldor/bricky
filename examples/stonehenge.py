# Copyright 2026 Maxence Faldor
"""Stonehenge as it stands today, at roughly 1 stud to 1 m (about 1:125).

Prompt: "Build Stonehenge as it stands today."

Model north (+y) is the solstice axis, which runs northeast in reality. The horseshoe
opens toward +y and the Heel Stone sits near the north edge of the base. Stone numbers
follow the usual scheme: sarsen uprights 1-30 clockwise from the entrance, trilithon
uprights 51-60.
"""

import itertools
import math

from bricky import ModelBuilder

WIDTH, DEPTH = 40, 48  # base, in studs
CENTER_X, CENTER_Y = 20, 20  # center of the circle
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
type PlateBox = tuple[Cell, int, int]
"""A plate's minimum corner, its width along x and its depth along y, in studs."""


def snap(value: float) -> int:
    """Round half up (Python's round() rounds half to even)."""
    return math.floor(value + 0.5)


def angle(stone: int) -> float:
    """Angle of a sarsen stone, in radians counterclockwise from +x.

    Stone 1 stands just east of +y.
    """
    return math.radians(90 - 12 * (stone - 0.5))


def base(builder: ModelBuilder) -> None:
    """Cover the ground with Green 2 x 8 plates."""
    for x in range(0, WIDTH, 2):
        for y in range(0, DEPTH, 8):
            builder.place("3034", at=(x, y, 0), color="Green", id=f"grass.{x}.{y}")


def sarsen_cells(stone: int, *, along_y: bool) -> list[Cell]:
    """The two cells of a standing sarsen, a 1 x 2 brick on the circle."""
    direction = angle(stone)
    center_x = CENTER_X + SARSEN_RADIUS * math.cos(direction)
    center_y = CENTER_Y + SARSEN_RADIUS * math.sin(direction)
    if along_y:
        x, y = math.floor(center_x), snap(center_y - 1)
        return [(x, y), (x, y + 1)]
    x, y = snap(center_x - 1), math.floor(center_y)
    return [(x, y), (x + 1, y)]


def lintel_box(first: list[Cell], second: list[Cell]) -> PlateBox | None:
    """The smallest plate box joining two uprights' nearest top studs, if one fits."""
    near_first, near_second = min(
        ((one, other) for one in first for other in second),
        key=lambda pair: (
            (pair[0][0] - pair[1][0]) ** 2 + (pair[0][1] - pair[1][1]) ** 2
        ),
    )
    corner = min(near_first[0], near_second[0]), min(near_first[1], near_second[1])
    width = abs(near_first[0] - near_second[0]) + 1
    depth = abs(near_first[1] - near_second[1]) + 1
    if (min(width, depth), max(width, depth)) not in PLATES:
        return None
    return corner, width, depth


def box_cells(box: PlateBox) -> set[Cell]:
    """The cells a plate box covers."""
    (corner_x, corner_y), width, depth = box
    return {
        (x, y)
        for x in range(corner_x, corner_x + width)
        for y in range(corner_y, corner_y + depth)
    }


def orientations() -> dict[int, bool]:
    """Choose each standing stone's orientation: whether its long side runs along y.

    Stones face along the circle's tangent, except for the fewest flips that let every
    lintel fit without two lintels sharing a stud.
    """
    tangent = {
        stone: abs(math.cos(angle(stone))) > abs(math.sin(angle(stone)))
        for stone in STANDING
    }
    involved = sorted({stone for pair in LINTELS for stone in pair})
    best: tuple[int, dict[int, bool]] | None = None
    for flips in itertools.product((False, True), repeat=len(involved)):
        trial = dict(tangent)
        for stone, flip in zip(involved, flips, strict=True):
            trial[stone] ^= flip
        boxes = [
            lintel_box(
                sarsen_cells(first, along_y=trial[first]),
                sarsen_cells(second, along_y=trial[second]),
            )
            for first, second in LINTELS
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
    """The standing sarsens, the lintels that remain on them, and the fallen stones."""
    along_y = orientations()
    tops = {}
    for stone in sorted(STANDING):
        cells = sarsen_cells(stone, along_y=along_y[stone])
        x, y = cells[0]
        bricks = 2 if stone in SHORT else UPRIGHT_BRICKS
        for level in range(bricks):
            builder.place(
                "3004",
                at=(x, y, GROUND + BRICK * level),
                rotation="R0" if along_y[stone] else "R90",
                color=SARSEN,
                id=f"sarsen{stone}.{level}",
            )
        tops[stone] = cells
    for first, second in LINTELS:
        box = lintel_box(tops[first], tops[second])
        if box is None:
            print(f"no plate fits lintel {first}-{second}; leaving it out")
            continue
        (x, y), width, depth = box
        part = PLATES[min(width, depth), max(width, depth)]
        builder.place(
            part,
            at=(x, y, GROUND + BRICK * UPRIGHT_BRICKS),
            rotation="R0" if depth >= width else "R90",
            color=SARSEN,
            id=f"lintel{first}-{second}",
        )
    for stone in FALLEN:
        direction = angle(stone)
        outward_x, outward_y = math.cos(direction), math.sin(direction)
        if abs(outward_x) > abs(outward_y):  # lies along x, outward
            x = (
                CENTER_X + SARSEN_RADIUS + 1
                if outward_x > 0
                else CENTER_X - SARSEN_RADIUS - 5
            )
            builder.place(
                "3001",
                at=(x, snap(CENTER_Y + SARSEN_RADIUS * outward_y - 1), GROUND),
                rotation="R90",
                color=SARSEN,
                id=f"fallen{stone}",
            )
        else:  # lies along y, outward
            y = (
                CENTER_Y + SARSEN_RADIUS + 1
                if outward_y > 0
                else CENTER_Y - SARSEN_RADIUS - 5
            )
            builder.place(
                "3001",
                at=(snap(CENTER_X + SARSEN_RADIUS * outward_x - 1), y, GROUND),
                color=SARSEN,
                id=f"fallen{stone}",
            )


def trilithon(builder: ModelBuilder) -> None:
    """Two 5-brick uprights with a 1 x 6 brick lintel, laid along local x."""
    component = builder.component("trilithon")
    for side, x in (("a", 0), ("b", 4)):
        for level in range(5):
            component.place(
                "3004",
                at=(x, 0, BRICK * level),
                rotation="R90",
                color=SARSEN,
                id=f"upright{side}.{level}",
            )
    component.place(
        "3009", at=(0, 0, BRICK * 5), rotation="R90", color=SARSEN, id="lintel"
    )


def upright(
    builder: ModelBuilder, name: str, corner: Cell, *, along_y: bool, bricks: int
) -> None:
    """A standing stone of 1 x 2 bricks, ``bricks`` tall."""
    for level in range(bricks):
        builder.place(
            "3004",
            at=(*corner, GROUND + BRICK * level),
            rotation="R0" if along_y else "R90",
            color=SARSEN,
            id=f"{name}.{level}",
        )


def horseshoe(builder: ModelBuilder) -> None:
    """The trilithon horseshoe, with its fallen stones and the Altar Stone."""
    trilithon(builder)
    # Trilithons stand along y on the sides of the horseshoe, so their instances rotate
    # by R90.
    builder.instance("trilithon", at=(27, 21, GROUND), rotation="R90", id="tri51-52")
    builder.instance("trilithon", at=(26, 13, GROUND), rotation="R90", id="tri53-54")
    builder.instance("trilithon", at=(13, 13, GROUND), rotation="R90", id="tri57-58")
    upright(builder, "stone60", (12, 25), along_y=True, bricks=5)
    builder.place("2456", at=(15, 24, GROUND), color=SARSEN, id="fallen59")
    builder.place("3009", at=(10, 15, GROUND), color=SARSEN, id="lintel160")
    # The Great Trilithon: 56 stands; 55 fell in two across the Altar Stone, with lintel
    # 156.
    upright(builder, "stone56", (17, 12), along_y=False, bricks=6)
    builder.place(
        "3710", at=(18, 16, GROUND), rotation="R90", color=BLUESTONE, id="altar"
    )
    builder.place("3002", at=(20, 14, GROUND + 1), color=SARSEN, id="fallen55a")
    builder.place("3003", at=(22, 15, GROUND), color=SARSEN, id="fallen55b")
    builder.place(
        "3009", at=(15, 18, GROUND), rotation="R90", color=SARSEN, id="lintel156"
    )


def bluestones(builder: ModelBuilder) -> None:
    """The bluestone circle and the bluestone horseshoe inside it."""
    # Outer circle: 1 x 1 stones at radius 11.5, with gaps where stones are lost.
    for k in range(36):
        if k % 4 == 3 or k in {8, 9, 26}:
            continue
        direction = math.radians(5 + 10 * k)
        x = snap(CENTER_X + 11.5 * math.cos(direction) - 0.5)
        y = snap(CENTER_Y + 11.5 * math.sin(direction) - 0.5)
        for level in range(1 + (k % 3 == 0)):
            builder.place(
                "3005",
                at=(x, y, GROUND + BRICK * level),
                color=BLUESTONE,
                id=f"blue{k}.{level}",
            )
    # Inner horseshoe: taller dressed pillars at radius 6, opening north.
    for k, degrees in enumerate((150, 170, 195, 345, 10, 30)):
        direction = math.radians(degrees)
        x = snap(CENTER_X + 6 * math.cos(direction) - 0.5)
        y = snap(CENTER_Y + 6 * math.sin(direction) - 0.5)
        for level in range(2):
            builder.place(
                "3005",
                at=(x, y, GROUND + BRICK * level),
                color=BLUESTONE,
                id=f"pillar{k}.{level}",
            )


def outliers(builder: ModelBuilder) -> None:
    """The Heel Stone and the Slaughter Stone, outside the circle."""
    for level in range(4):  # the Heel Stone, just east of the axis
        builder.place(
            "3003",
            at=(22, 43, GROUND + BRICK * level),
            color=SARSEN,
            id=f"heel.{level}",
        )
    builder.place(
        "3020", at=(17, 38, GROUND), rotation="R90", color=SARSEN, id="slaughter"
    )


def build() -> ModelBuilder:
    """Build Stonehenge on its base."""
    builder = ModelBuilder("stonehenge")
    base(builder)
    sarsen_circle(builder)
    horseshoe(builder)
    bluestones(builder)
    outliers(builder)
    return builder
