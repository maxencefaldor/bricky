# Copyright 2026 Maxence Faldor
"""The Colosseum in Rome, at 1:150: a stud is 1.2 m and a plate 0.48 m.

References: Wikipedia, "Colosseum": an ellipse 189 m by 156 m and 48 m tall, around an
arena of 87 m by 55 m. Three stories of 80 arches, framed by Tuscan, Ionic and
Corinthian half-columns, stand under an attic with pilasters, small windows and corbels.
The outer ring survives on the north side only, held at each end by a brick buttress;
the south shows the arcades of the second ring. Inside, the seating is gone down to its
radial walls, the arena lies open over the hypogeum, and a stage of wooden boards covers
the east end.

The script draws the monument as voxels on elliptical rings, then fills them with bricks
and plates (``builder.fill``). The half-columns are round bricks, placed one by one. x
runs east, y north, and z up, in plates; the monument stands on a plaza of baseplates.

Run: ``uv run bricky build examples/colosseum.py``
"""

from functools import cache
from math import atan2, pi, sqrt

from bricky import ModelBuilder

SIZE = 160  # the plaza: 5 x 5 baseplates of 32 x 32 studs
CENTER_X, CENTER_Y = 80.0, 80.0
OUTER_X, OUTER_Y = 77.5, 64.5  # the outer ellipse's semi-axes, in studs
BAYS = 80

STONE, CORNICE, STEPS = "Tan", "Dark Tan", "Light Bluish Gray"
BRICKWORK, BUTTRESS, MARBLE, WOOD = (
    "Medium Nougat",
    "Dark Orange",
    "White",
    "Reddish Brown",
)

# Depths inward from the outer face, in studs.
OUTER_WALL = (0.0, 2.5)
AMBULATORY = (2.5, 6.5)
SECOND_RING = (6.5, 9.5)
CAVEA = (9.5, 42.0)
PODIUM = (42.0, 43.0)
ANNULAR_WALLS = ((16.0, 17.5), (25.5, 27.0), (34.5, 36.0))

# Heights, in plates: three arcades of 21-plate half-columns, cornices, the attic and
# its crown.
ARCADES = ((1, 22), (24, 45), (48, 69))
CORNICES = ((22, 24), (45, 48), (69, 72))
ATTIC = (72, 95)
CROWN = (95, 98)
TOP = CROWN[1]
SECOND_RING_TOP = 72
PODIUM_TOP = 10
HYPOGEUM_TOP = 6

SURVIVING = (
    15.0,
    195.0,
)  # degrees of the outer ring standing to full height, counter-clockwise
BUTTRESS_LENGTH = 9.0  # studs along the ring
SEATS = range(8, 14)  # bays of the rebuilt seating, north-east
STAGE_FROM = 14.0  # studs east of the center where the arena's stage begins

type Voxel = tuple[int, int, int]


@cache
def depth_at(x: int, y: int) -> float:
    """How far a stud square lies inside the outer ellipse, in studs; negative outside.

    A square at depth 3 lies on the ellipse whose semi-axes are 3 studs shorter, so
    equal depths draw rings of equal width, like the monument's concentric walls.
    """
    east, north = x + 0.5 - CENTER_X, y + 0.5 - CENTER_Y
    low, high = -6.0, OUTER_Y - 0.5
    for _ in range(40):
        middle = (low + high) / 2
        inside = (east / (OUTER_X - middle)) ** 2 + (
            north / (OUTER_Y - middle)
        ) ** 2 <= 1
        low, high = (middle, high) if inside else (low, middle)
    return low


@cache
def angle(x: int, y: int) -> float:
    """The square's angle around the ellipse, in degrees from east, counterclockwise."""
    depth = min(depth_at(x, y), OUTER_Y - 1)
    east, north = x + 0.5 - CENTER_X, y + 0.5 - CENTER_Y
    return atan2(north / (OUTER_Y - depth), east / (OUTER_X - depth)) * 180 / pi % 360


def bay(x: int, y: int) -> tuple[int, float]:
    """The bay a square lies in, and how far across it, from 0 to 1."""
    position = angle(x, y) / 360 * BAYS
    return int(position) % BAYS, position % 1


def bay_width(depth: float) -> float:
    """The width of one bay at a depth, in studs: the ring's perimeter over 80.

    The perimeter follows Ramanujan's approximation for an ellipse.
    """
    semi_x, semi_y = OUTER_X - depth, OUTER_Y - depth
    ramanujan = 3 * (semi_x + semi_y) - sqrt(
        (3 * semi_x + semi_y) * (semi_x + 3 * semi_y)
    )
    return pi * ramanujan / BAYS


def from_pier(x: int, y: int) -> float:
    """How far a square lies from the nearest pier, which divides two bays, in studs."""
    _, across = bay(x, y)
    return min(across, 1 - across) * bay_width(depth_at(x, y))


def surviving(x: int, y: int) -> bool:
    """Whether the outer ring stands to its full height at this square."""
    return SURVIVING[0] <= angle(x, y) < SURVIVING[1]


def noise(*key: int) -> float:
    """A fixed pseudo-random number in [0, 1) for a key.

    The fixed numbers make ruins look broken yet build the same every time.
    """
    value = 0
    for part in key:
        value = (value * 1_000_003 + part * 7_919 + 104_729) % 2_147_483_647
    return (value * 48_271 % 2_147_483_647) / 2_147_483_647


def arch_top(across: float, width: float) -> int:
    """The height of an arched opening above its sill, in plates.

    The opening is 13 plates tall at the sides and 17 at the top.
    """
    side = (across - 0.5) / (width / 2)  # from -1 at one side to 1 at the other
    return 13 + round(4 * sqrt(max(0.0, 1 - side * side)))


def within(value: float, band: tuple[float, float]) -> bool:
    """Whether a value lies in a band, which includes its start and excludes its end."""
    return band[0] <= value < band[1]


def ruin_top(bay_index: int) -> int:
    """How tall the broken outer ring still stands in a bay, in plates.

    The ring stands to whole bricks: below the arches' springing, or over the first
    story.
    """
    return 3 * (2, 3, 4, 7)[int(4 * noise(bay_index, 1))]


def outer_ring(x: int, y: int) -> dict[int, str]:
    """The outer wall's voxel column at a square, with its arches, windows and ruins."""
    column: dict[int, str] = {}
    bay_index, across = bay(x, y)
    intact = surviving(x, y)
    top = TOP if intact else ruin_top(bay_index)
    for z in range(top):
        if any(within(z, band) for band in CORNICES) or z >= CROWN[0]:
            column[z] = CORNICE
        else:
            column[z] = STONE
    for story, (base, _) in enumerate(ARCADES):
        if not within(across, (0.25, 0.75)):
            continue
        sill = 0 if story == 0 else base + 2
        for z in range(sill, base - 1 + arch_top(across, 0.5)):
            column.pop(z, None)
    if intact and bay_index % 2 == 0 and within(across, (0.42, 0.58)):
        for z in range(80, 86):  # the attic's small windows, in every other bay
            column.pop(z, None)
    return column


def outer_skin(x: int, y: int, depth: float) -> dict[int, str]:
    """What juts from the outer face: the stylobate, cornices, pilasters and corbels."""
    column = {0: STEPS} if depth >= -2 else {}
    if depth < -1.5 or not surviving(x, y):
        return column
    column.update({z: CORNICE for band in CORNICES for z in range(*band)})
    if depth < -1:
        return column
    column.update(dict.fromkeys(range(*CROWN), CORNICE))
    _, across = bay(x, y)
    if from_pier(x, y) < 0.5:
        column.update(dict.fromkeys(range(*ATTIC), STONE))  # pilasters
    elif min(abs(across - 1 / 3), abs(across - 2 / 3)) * bay_width(depth) < 0.5 and any(
        depth_at(*neighbor) >= 0
        for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
    ):
        column[88] = STONE  # corbels, which held the masts of the awning
    return column


def ambulatory(x: int, y: int) -> dict[int, str]:
    """The vaults between the outer and second rings, as floors.

    The vaults stand only where the outer ring stands.
    """
    if not surviving(x, y):
        return {}
    return {z: CORNICE for band in CORNICES for z in range(*band)}


def second_ring(x: int, y: int) -> dict[int, str]:
    """The second ring of piers and arches, to the top of the third story."""
    column = dict.fromkeys(range(SECOND_RING_TOP), STONE)
    column.update({z: CORNICE for band in CORNICES for z in range(*band)})
    _, across = bay(x, y)
    if within(across, (0.3, 0.7)):
        for story, (base, _) in enumerate(ARCADES):
            sill = 0 if story == 0 else base + 2
            for z in range(sill, base - 3 + arch_top(across, 0.4)):
                column.pop(z, None)
    return column


def seating_height(depth: float) -> int:
    """The top of the seating at a depth, in plates.

    The seating rises from the podium to the second ring.
    """
    share = (CAVEA[1] - depth) / (CAVEA[1] - CAVEA[0])
    return 2 * round((PODIUM_TOP + share * (SECOND_RING_TOP - PODIUM_TOP)) / 2)


def cavea(x: int, y: int, depth: float) -> dict[int, str]:
    """The seating's remains: radial walls, ring walls and one rebuilt sector.

    Passages cross the ring walls.
    """
    column: dict[int, str] = {}
    bay_index, across = bay(x, y)
    top = seating_height(depth)
    if not surviving(x, y):
        top -= 2 * round(6 * noise(bay_index, 2))
    if from_pier(x, y) < 0.5:
        column.update(dict.fromkeys(range(top), BRICKWORK))
    for band in ANNULAR_WALLS:
        if within(depth, band):
            column.update(dict.fromkeys(range(top), CORNICE))
            if within(across, (0.4, 0.6)):
                for z in range(8):  # the passages under the seats
                    column.pop(z, None)
    if (
        bay_index in SEATS
    ):  # steps of 2 plates on a shell of 4, so each step overlaps the next
        column.update(dict.fromkeys(range(top - 4, top), MARBLE))
    return column


def arena(x: int, y: int, depth: float) -> dict[int, str]:
    """The podium wall, the open hypogeum's walls, and the stage at the east end."""
    if within(depth, PODIUM):
        return dict.fromkeys(range(PODIUM_TOP), MARBLE)
    column: dict[int, str] = {}
    east, north = x + 0.5 - CENTER_X, y + 0.5 - CENTER_Y
    corridor = abs(north) < 1.5
    wall = (y % 3 == 0 or x % 6 == 0) and not corridor
    if wall:
        column.update(dict.fromkeys(range(HYPOGEUM_TOP), CORNICE))
    if east > STAGE_FROM:
        column[HYPOGEUM_TOP] = WOOD
    return column


def buttress(x: int, y: int, depth: float) -> dict[int, str]:
    """The stepped brick wedges that buttress the ends of the surviving outer ring."""
    if not within(depth, (-1.0, SECOND_RING[0])):
        return {}
    position = angle(x, y)
    for end, direction in ((SURVIVING[0], -1), (SURVIVING[1], 1)):
        past = (position - end) * direction % 360
        studs = past / 360 * bay_width(max(depth, 0.0)) * BAYS
        if studs < BUTTRESS_LENGTH:
            height = round(TOP * (1 - studs / BUTTRESS_LENGTH) ** 0.7)
            return dict.fromkeys(range(height), BUTTRESS)
    return {}


def monument() -> dict[Voxel, str]:
    """Every voxel of the monument, ring by ring."""
    voxels: dict[Voxel, str] = {}
    for x in range(SIZE):
        for y in range(SIZE):
            depth = depth_at(x, y)
            column: dict[int, str] = {}
            if depth < OUTER_WALL[0]:
                column = outer_skin(x, y, depth)
            elif within(depth, OUTER_WALL):
                column = outer_ring(x, y)
            elif within(depth, AMBULATORY):
                column = ambulatory(x, y)
            elif within(depth, SECOND_RING):
                column = second_ring(x, y)
            elif within(depth, CAVEA):
                column = cavea(x, y, depth)
            else:
                column = arena(x, y, depth)
            if not surviving(x, y):
                column = {**column, **buttress(x, y, depth)}
            voxels.update({(x, y, z): color for z, color in column.items()})
    return voxels


def half_columns() -> list[tuple[int, int, int]]:
    """Where the round bricks of the half-columns stand: at each pier, on each story."""
    piers: dict[int, tuple[float, int, int]] = {}
    for x in range(SIZE):
        for y in range(SIZE):
            depth = depth_at(x, y)
            if not within(depth, (-1.0, 0.0)):
                continue
            position = angle(x, y) / 360 * BAYS
            pier = round(position) % BAYS
            distance = abs(position - round(position))
            if pier not in piers or distance < piers[pier][0]:
                piers[pier] = (distance, x, y)
    spots: list[tuple[int, int, int]] = []
    for pier, (_, x, y) in piers.items():
        standing = (
            TOP if surviving(x, y) else min(ruin_top((pier - 1) % BAYS), ruin_top(pier))
        )
        for base, top in ARCADES:
            spots.extend(
                (x, y, z)
                for z in range(base, min(top, standing), 3)
                if z + 3 <= standing
            )
    return spots


def plaza(builder: ModelBuilder) -> None:
    """Lay the baseplates the monument stands on."""
    for i in range(SIZE // 32):
        for j in range(SIZE // 32):
            builder.place(
                "3811", at=(32 * i, 32 * j, 0), color=STEPS, id=f"plaza.{i}.{j}"
            )


def build() -> ModelBuilder:
    """Fill the monument's voxels, add the half-columns, and stand it on the plaza.

    The monument is a component, so the fill counts plates from zero, and its one
    instance stands on the baseplates, half a plate up.
    """
    builder = ModelBuilder("colosseum")
    plaza(builder)
    stone = builder.component("monument")
    voxels = monument()
    print(f"{len(voxels):,} voxels")
    stone.fill(voxels, id="stone")
    spots = [
        (x, y, z)
        for x, y, z in half_columns()
        if all((x, y, z + k) not in voxels for k in range(3))
    ]
    for x, y, z in spots:
        stone.place("3062", at=(x, y, z), color=STONE, id=f"column.{x}.{y}.{z}")
    print(f"{len(spots):,} round bricks in the half-columns")
    low_x = min(x for x, _, _ in voxels)
    low_y = min(y for _, y, _ in voxels)
    builder.instance("monument", at=(low_x, low_y, 0.5), id="colosseum")
    return builder
