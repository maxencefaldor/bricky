# Copyright 2026 Maxence Faldor
"""The Elizabeth Tower (Big Ben) at roughly 1 stud to 1 m (about 1:125).

Prompt: "Build the Elizabeth Tower (Big Ben) in London." References: Wikipedia, "Big
Ben": 96 m tall, 12 m square base, four 6.9 m dials centered 54.9 m up, gilded dial
surrounds, a cast-iron spire, the Ayrton Light above the belfry.

The script draws the tower as voxels, one stud square and one plate tall, then fills
them with bricks and plates (``builder.fill``). x runs along the south face, y along the
east face, and z points up, in plates.
"""

from bricky import ModelBuilder

STONE, BAND, GOLD = "Tan", "Dark Tan", "Yellow"
DARK, GLASS, DIAL, IRON = "Black", "Trans-Clear", "White", "Dark Bluish Gray"

BODY = range(1, 14)  # the shaft is 13 studs square
OUTER = range(15)  # projecting bands and the plinth add a stud all around
TOP = 241  # plates
ROOF = 188

type Color = str | None


def ring(x: int, y: int, start: int, stop: int, thickness: int = 1) -> bool:
    """Whether (x, y) lies in a square ring, ``start`` to ``stop - 1`` on both axes."""
    if not (start <= x < stop and start <= y < stop):
        return False
    return min(x - start, y - start, stop - 1 - x, stop - 1 - y) < thickness


def square(x: int, y: int, start: int, stop: int) -> bool:
    """Whether (x, y) lies in the square from ``start`` to ``stop - 1`` on both axes."""
    return start <= x < stop and start <= y < stop


def along_face(x: int, y: int) -> int:
    """Position along whichever face of the body (x, y) sits on.

    The position runs from 0 to 12, counted from that face's left.
    """
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
        return dial(along, z, radius_squared)
    spandrels = abs(along - 6) <= 3 and 129 <= z <= 147
    inscription = 2 <= along <= 10 and 125 <= z <= 126
    return GOLD if spandrels or inscription else STONE


def dial(along: int, z: int, radius_squared: float) -> Color:
    """A white dial in an iron frame, its hands at three o'clock."""
    frame = radius_squared > (2.5 / 3.5) ** 2
    hands = (along == 6 and 138 <= z <= 144) or (z == 138 and 6 <= along <= 8)
    return DARK if frame or hands else DIAL


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


def crown(x: int, y: int, z: int) -> Color:
    """The pinnacles over the corner buttresses, gilded at the tip, then the spire."""
    if x in {1, 13} and y in {1, 13} and z <= 201:
        return GOLD if z == 201 else STONE
    return spire(x, y, z)


def tower(x: int, y: int, z: int) -> Color:
    """Color of the voxel at (x, y, z), or None for air."""
    if z < 6 or z in {120, 157}:  # the plinth and the string courses
        return BAND if ring(x, y, OUTER.start, OUTER.stop, thickness=2) else None
    if z == ROOF:  # the cornice and the roof
        return BAND if square(x, y, OUTER.start, OUTER.stop) else None
    section = shaft if z < 120 else clock if z < 157 else belfry if z < ROOF else crown
    return section(x, y, z)


def build() -> ModelBuilder:
    """Draw the tower as voxels and fill them with bricks and plates."""
    builder = ModelBuilder("elizabeth_tower")
    voxels = {
        (x, y, z): color
        for z in range(TOP)
        for x in OUTER
        for y in OUTER
        if (color := tower(x, y, z)) is not None
    }
    builder.fill(voxels, id="tower")
    return builder
