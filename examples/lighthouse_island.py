# Copyright 2026 Maxence Faldor
"""A lighthouse on a small rocky island, with a keeper's cottage, a beach and a pier.

- The Baseplate 48 x 48 holds a sea of tiles and plates in three blues, lighter toward
  the shore, with round plates and tiles of white foam where the water meets the land.
- The island is voxels filled in one plan (``builder.fill``'s planner), so the tower
  and the cottage rest on the rock: strata of two grays, terraces of grass, a beach
  that rises a plate a stud, and a natural arch over a channel of sea.
- Slopes 45 and 65 and cheese slopes soften the foot of each step of rock and grass.
- The lighthouse is a round tower of five red and white bands that tapers from 8 to 6
  studs. Inverted slopes carry its gallery, and its lantern of round bricks holds a
  yellow lamp under a dome of cheese slopes. A jumper centers the finial.
- The cottage has a roof of Slope 45 rows over gable bricks, a chimney through it, and
  window sills with flowers.
- The pier stands on round bricks, under beams of plates and planks of tiles. The
  rowboat and the sailboat have hulls of inverted slopes, and a lifebuoy hangs
  sideways from a stud.
- Each palm leans half a stud on every jumper of its trunk. The palms' crowns, the
  gulls and the bushes are components.

Run: ``uv run bricky build examples/lighthouse_island.py``
"""

from collections import defaultdict, deque
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from functools import cache, partial
from math import cos, floor, hypot, radians, sin

from bricky import ModelBuilder
from bricky.fill import plan_fill

type Square = tuple[int, int]
type Voxel = tuple[int, int, int]

SIZE = 48  # the Baseplate 48 x 48
BASE = 0.5  # the top of the baseplate, in plates

DEEP, SEA, SHALLOW, FOAM = "Blue", "Dark Turquoise", "Medium Azure", "White"
DARK_ROCK, LIGHT_ROCK = "Dark Bluish Gray", "Light Bluish Gray"
GRASS, MEADOW, LEAF = "Green", "Lime", "Dark Green"
SAND, WET_SAND = "Tan", "Dark Tan"
WOOD, PLANK, BEAM = "Reddish Brown", "Dark Tan", "Dark Brown"
WALL, ROOF, DOOR, GLASS = "White", "Red", "Dark Turquoise", "Trans-Light Blue"
FLOWERS = ("Yellow", "White", "Dark Pink", "Magenta", "Bright Light Orange", "Red")

TILES = {
    (2, 4): "87079",
    (2, 3): "26603",
    (2, 2): "3068",
    (1, 4): "2431",
    (1, 3): "63864",
    (1, 2): "3069",
    (1, 1): "3070",
}  # tiles by footprint: the shorter side first, along x when unrotated
PLATES = {
    (2, 4): "3020",
    (2, 3): "3021",
    (2, 2): "3022",
    (1, 4): "3710",
    (1, 3): "3623",
    (1, 2): "3023",
    (1, 1): "3024",
}

FALLS = {(0, -1): "R0", (1, 0): "R90", (0, 1): "R180", (-1, 0): "R270"}
"""The rotation that makes a slope fall toward each direction."""

# The tower stands on a corner between studs, so its rings are symmetric.
TOWER_X, TOWER_Y = 18.0, 32.0
SUMMIT = 24  # the top of the rock under the tower, in plates
PLINTH = 3
FOOT = SUMMIT + PLINTH  # the foot of the tower's wall
BAND = 12  # the height of each red or white band
GALLERY = FOOT + 5 * BAND  # the gallery's floor, two plates thick

# The cottage's walls fill x from WEST to EAST - 1 and y from SOUTH to NORTH - 1.
WEST, EAST, SOUTH, NORTH = 25, 33, 27, 33
TERRACE = 18  # the top of the rock under the cottage
EAVES = TERRACE + 9  # three courses of wall
DOORWAY = (28, 29)  # the x of the cottage's door, and of the stairs below it
WINDOWS = (26, 31)  # the x of the windows in the front wall
CHIMNEY = (30, 28)

PIER_X = 32  # the deck spans x from PIER_X to PIER_X + 2
PIER_POSTS = (2, 6, 10, 14)  # the y of each pair of posts
DECK = BASE + 7  # the underside of the pier's beams
BOAT = (36, 4)  # the rowboat's minimum corner: 3 studs wide and 6 long
SAILBOAT = (7, 3)  # the sailboat's minimum corner: 6 studs long and 3 wide
PALMS = (
    (18, 19, ((-1, 0), (-1, 0), (0, -1), (-1, 0), (0, -1), (-1, 0))),
    (26, 12, ((0, -1), (1, 0), (0, -1), (0, -1), (1, 0), (0, -1))),
)  # where each palm stands, and the way each jumper leans its trunk
LAMP = (30, 25)  # a lamp post beside the cottage's door
BARREL, CRATE = (35, 12), (30, 12)
PARASOL, TOWEL = (24, 22), (23, 20)  # the towel is two tiles 1 x 4, along x
BUOYS = ((43, 8, "Red", "Trans-Red"), (24, 3, "Green", "Trans-Green"))
GULLS = (
    (42, 22, (1, 0)),
    (8, 13, (0, 1)),
)  # gulls on rocks, and where their tails point
ARCH = range(38, 41)  # the x of the arch's opening, between the island and a stack
ARCH_Y = range(21, 23)


@dataclass(frozen=True, slots=True)
class Mesa:
    """A mass of rock: a flat top inside an ellipse, and flanks that fall away."""

    x: float
    y: float
    radius_x: float
    radius_y: float
    top: int  # plates
    fall: float  # plates per stud beyond the ellipse

    def height(self, x: int, y: int) -> float:
        """Return the rock's height over a square, before rounding to whole courses."""
        reach = hypot(
            (x + 0.5 - self.x) / self.radius_x, (y + 0.5 - self.y) / self.radius_y
        )
        beyond = (reach - 1) * (self.radius_x + self.radius_y) / 2
        rugged = 2.0 * (smooth(x, y, 3.0, 1) - 0.5)
        return self.top - self.fall * max(0.0, beyond + rugged)


MESAS = (
    Mesa(18.0, 31.5, 6.5, 5.5, SUMMIT, 6.0),  # under the lighthouse
    Mesa(29.5, 30.0, 6.5, 5.0, TERRACE, 5.0),  # under the cottage
    Mesa(11.0, 26.0, 3.5, 5.0, 12, 5.0),  # the western shoulder
    Mesa(30.0, 37.0, 4.5, 2.5, 12, 5.0),  # the northern ledge
    Mesa(12.5, 18.5, 3.0, 2.5, 9, 4.5),  # the rocks west of the beach
    Mesa(35.5, 21.5, 2.5, 2.5, 15, 4.0),  # the spur that springs the arch
    Mesa(42.5, 22.0, 1.6, 1.8, 15, 5.0),  # the stack across the arch
    Mesa(8.0, 13.0, 1.4, 1.4, 6, 4.0),  # rocks out at sea
    Mesa(37.0, 41.0, 1.2, 1.2, 6, 4.0),
    Mesa(16.5, 6.5, 0.8, 0.8, 3, 4.0),
    Mesa(44.5, 31.5, 0.9, 1.2, 6, 4.0),
    Mesa(4.5, 35.5, 0.9, 0.9, 3, 4.0),
)
BEACH = (25.0, 17.5, 12.5, 7.0)  # the ellipse of sand: center x, y and radii


def noise(*key: int) -> float:
    """Return a fixed pseudo-random number in [0, 1) for a key of integers."""
    value = 0x9E3779B9
    for part in key:
        value = ((value ^ (part & 0xFFFFFFFF)) * 0x85EBCA6B) & 0xFFFFFFFF
        value ^= value >> 13
        value = (value * 0xC2B2AE35) & 0xFFFFFFFF
        value ^= value >> 16
    return value / 2**32


def smooth(x: float, y: float, scale: float, seed: int) -> float:
    """Return noise in [0, 1) that varies smoothly over ``scale`` studs."""
    column, row = floor(x / scale), floor(y / scale)
    east, north = x / scale - column, y / scale - row
    east, north = east * east * (3 - 2 * east), north * north * (3 - 2 * north)
    corners = [noise(seed, column + i, row + j) for j in (0, 1) for i in (0, 1)]
    south_edge = corners[0] + (corners[1] - corners[0]) * east
    north_edge = corners[2] + (corners[3] - corners[2]) * east
    return south_edge + (north_edge - south_edge) * north


def neighbors(x: int, y: int) -> tuple[Square, ...]:
    """Return the four squares that share a side with a square."""
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))


@cache
def disc(radius: float) -> frozenset[Square]:
    """Return the squares whose centers lie within ``radius`` of the tower's axis."""
    reach = range(-6, 6)
    return frozenset(
        (int(TOWER_X) + i, int(TOWER_Y) + j)
        for i in reach
        for j in reach
        if hypot(i + 0.5, j + 0.5) < radius
    )


@dataclass(slots=True)
class Land:
    """The island's surface: the top of every square of land, and what covers it."""

    height: dict[Square, int] = field(default_factory=dict)
    """The top of each column, in plates."""

    sand: set[Square] = field(default_factory=set)
    grass: set[Square] = field(default_factory=set)
    tiles: dict[Square, str] = field(default_factory=dict)
    """Squares whose top layer is a tile instead of a plate, by color."""

    taken: set[Square] = field(default_factory=set)
    """Squares where a part stands, which flowers and tiles leave free."""

    banks: list[tuple[str, Square, str, str]] = field(default_factory=list)
    """Slopes at the foot of steps: part, corner, rotation and color."""

    def top(self, x: float, y: float) -> float:
        """Return the height of the land's surface over a square, in world plates."""
        return BASE + self.height.get((floor(x), floor(y)), 0)


def rock_height(x: int, y: int) -> int:
    """Return the rock's height over a square, in whole courses.

    The summit is level within 6.5 studs of a point half a stud south of the tower's
    axis, and the terrace is level around the cottage.
    """
    height = max(mesa.height(x, y) for mesa in MESAS)
    if hypot(x + 0.5 - TOWER_X, y + 0.5 - (TOWER_Y - 0.5)) < 6.5:
        height = SUMMIT
    elif WEST - 1 <= x <= EAST + 2 and SOUTH - 2 <= y <= NORTH + 1:
        height = TERRACE
    return 3 * int(max(0.0, height) // 3)


def path(land: Land) -> None:
    """Lay a path of tiles from the beach up the stairs to the cottage and the tower."""
    front = SOUTH - 1  # the row along the cottage's front
    steps = {(x, front): TERRACE for x in range(WEST, DOORWAY[1] + 1)}
    steps |= {(x, front - 1): TERRACE for x in DOORWAY}
    steps |= {(WEST - 1, front): 21, (WEST - 1, SOUTH): 21}  # a step up to the summit
    steps |= {(x, SOUTH): SUMMIT for x in range(19, WEST - 1)}  # to the tower's door
    for y in range(front - 2, 10, -1):  # the stairs fall two plates a stud
        rise = TERRACE - 2 * (front - 1 - y)
        if rise <= land.height.get((DOORWAY[0], y), 0):
            break
        for x in DOORWAY:
            steps[x, y] = rise
        for x in (DOORWAY[0] - 1, DOORWAY[1] + 1):  # rock either side of the stairs
            land.height[x, y] = max(land.height.get((x, y), 0), 3 * (rise // 3 + 1))
            land.sand.discard((x, y))
    for square, rise in steps.items():
        land.height[square] = rise
        land.sand.discard(square)
        land.grass.discard(square)
        land.tiles[square] = SAND


def beach(land: Land) -> None:
    """Spread sand inside an ellipse, rising one plate a stud from the sea."""
    center_x, center_y, radius_x, radius_y = BEACH
    squares = {
        (x, y)
        for x in range(SIZE)
        for y in range(SIZE)
        if hypot((x + 0.5 - center_x) / radius_x, (y + 0.5 - center_y) / radius_y)
        + 0.3 * (smooth(x, y, 3.0, 2) - 0.5)
        < 1
    }
    inland = distances(squares | set(land.height), outward=False)
    for square in squares:
        rise = min(6, 1 + int(0.8 * (inland[square] - 1)))
        if rise > land.height.get(square, 0):
            land.height[square] = rise
            land.sand.add(square)


def meadows(land: Land) -> None:
    """Grow grass on the rock, except where a square stands out over two sides."""
    for (x, y), rise in land.height.items():
        lower = [near for near in neighbors(x, y) if land.height.get(near, 0) < rise]
        if (x, y) not in land.sand and rise >= 6 and len(lower) <= 1:
            land.grass.add((x, y))


def reserve(land: Land) -> None:
    """Reserve the squares where buildings and props stand, then tile the beach."""
    land.taken |= {(PIER_X + i, y) for i in (0, 2) for y in PIER_POSTS}
    land.taken |= {(x, y) for x, y, _ in PALMS + GULLS} | {LAMP, PARASOL} | disc(4.7)
    land.taken |= {
        (x + i, y + j) for x, y in (BARREL, CRATE) for i in (0, 1) for j in (0, 1)
    }
    land.taken |= {(TOWEL[0] + i, TOWEL[1] + j) for i in range(4) for j in (0, 1)}
    land.taken |= {
        (x, y) for x in range(WEST - 1, EAST + 1) for y in range(SOUTH - 1, NORTH + 1)
    }
    for x, y in land.sand - land.taken:
        if noise(x, y, 8) < 0.75:
            land.tiles[x, y] = WET_SAND if land.height[x, y] == 1 else SAND


def survey() -> Land:
    """Shape the island: rock, a beach that rises from the sea, grass and paths."""
    land = Land()
    for x in range(SIZE):
        for y in range(SIZE):
            if (rock := rock_height(x, y)) > 0:
                land.height[x, y] = rock
    beach(land)
    for x in ARCH:  # a channel of sea under the arch
        for y in range(ARCH_Y.start - 4, ARCH_Y.stop + 4):
            land.height.pop((x, y), None)
            land.sand.discard((x, y))
    meadows(land)
    path(land)
    reserve(land)
    soften(land)
    return land


def soften(land: Land) -> None:
    """Choose slopes for the foot of steps, so the rock and grass fall in banks.

    A step of one course takes a Slope 45 2 x 1 over two level squares, or a cheese
    slope over one; a step of two courses takes a Slope 65 2 x 1 x 2.
    """
    level_ground = set(land.tiles) | land.sand  # squares without studs, or with sand
    for (x, y), rise in sorted(land.height.items()):
        if (x, y) in level_ground or rise < 6:
            continue
        for (i, j), rotation in FALLS.items():
            near, far = (x + i, y + j), (x + 2 * i, y + 2 * j)
            low = land.height.get(near, 0)
            level = land.height.get(far) == low
            blocked = land.taken | level_ground
            color = GRASS if (x, y) in land.grass else rock_color(x, y, rise - 1)
            if noise(x, y, i, j, 14) > 0.85 or low < 3 or near in blocked:
                continue
            if rise - low in {3, 6} and level and far not in blocked:
                part = "3040" if rise - low == 3 else "60481"
                corner = (min(near[0], far[0]), min(near[1], far[1]))
                land.banks.append((part, corner, rotation, color))
                land.taken |= {near, far}
            elif rise - low == 3:
                land.banks.append(("54200", near, rotation, color))
                land.taken.add(near)


def distances(squares: set[Square], *, outward: bool) -> dict[Square, int]:
    """Return how many steps each square lies from the edge of a set of squares.

    Outward, the distances run over the squares outside the set, from 1 beside it;
    inward, over the squares inside, from 1 at its edge. Steps go to all eight
    neighbors, and the baseplate's edge is no edge.
    """
    grid = {(x, y) for x in range(SIZE) for y in range(SIZE)}
    region = {square for square in grid if (square in squares) != outward}
    found: dict[Square, int] = {}
    queue: deque[Square] = deque()
    for x, y in region:
        around = {(x + i, y + j) for i in (-1, 0, 1) for j in (-1, 0, 1)}
        if (around & grid) - region:
            found[x, y] = 1
            queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                square = (x + i, y + j)
                if square in region and square not in found:
                    found[square] = found[x, y] + 1
                    queue.append(square)
    return found


def rock_color(x: int, y: int, z: int) -> str:
    """Return the gray of a rock voxel: strata a course thick that rise and fall."""
    stratum = z // 3 + round(2 * smooth(x, y, 5.0, 20))
    light = stratum % 2 == 0
    if noise(x, y, z // 3, 21) < 0.1:
        light = not light
    return LIGHT_ROCK if light else DARK_ROCK


def island_voxels(land: Land) -> dict[Voxel, str]:
    """Return the voxels of rock, sand and grass, under the tiles of the paths."""
    voxels: dict[Voxel, str] = {}
    for (x, y), rise in land.height.items():
        for z in range(rise):
            if (x, y) in land.sand:
                color = WET_SAND if rise == 1 else SAND
            elif z == rise - 1 and (x, y) in land.grass:
                color = MEADOW if smooth(x, y, 3.0, 3) > 0.66 else GRASS
            else:
                color = rock_color(x, y, z)
            voxels[x, y, z] = color
        if (x, y) in land.tiles:
            del voxels[x, y, rise - 1]
    for x, y, z in list(voxels):  # hidden voxels take one color, for larger parts
        around = [(*near, z) for near in neighbors(x, y)] + [(x, y, z + 1)]
        if all(voxel in voxels for voxel in around):
            voxels[x, y, z] = DARK_ROCK if (x, y) not in land.sand else SAND
    return voxels


def arch_voxels() -> dict[Voxel, str]:
    """Return the rock that bridges the spur and the stack over an arched opening."""
    voxels: dict[Voxel, str] = {}
    for x in ARCH:
        bottom = 9 if x == ARCH[1] else 6
        for y in ARCH_Y:
            for z in range(bottom, 15):
                voxels[x, y, z] = rock_color(x, y, z)
    return voxels


def stripe(z: int) -> str:
    """Return the color of the tower's band at a height: red, then white, upward."""
    return "Red" if (z - FOOT) // BAND % 2 == 0 else "White"


def corbels() -> dict[Square, tuple[Square, str]]:
    """Return the inverted slopes under the gallery: overhang square, back, rotation."""
    top, gallery = disc(3.05), disc(4.0)
    found: dict[Square, tuple[Square, str]] = {}
    rotations = {(0, 1): "R0", (-1, 0): "R90", (0, -1): "R180", (1, 0): "R270"}
    for x, y in gallery - top:
        inward = [(i, j) for i, j in rotations if (x + i, y + j) in top]
        if len(inward) == 1:
            i, j = inward[0]
            found[x, y] = ((x + i, y + j), rotations[i, j])
    return found


def tower_voxels() -> dict[Voxel, str]:
    """Return the tower's voxels: plinth, banded wall, door, windows and gallery."""
    voxels: dict[Voxel, str] = {}
    for z in range(SUMMIT, FOOT):
        for x, y in disc(4.7):
            voxels[x, y, z] = DARK_ROCK
    for z in range(FOOT, GALLERY):
        course = z - (z - FOOT) % 3
        radius = 4.0 - (course - FOOT) / (GALLERY - FOOT)
        for x, y in disc(radius) - disc(radius - 1.3):
            voxels[x, y, z] = stripe(z)
    openings(voxels)
    for x, y in disc(4.0):  # two plates, so the floor's corners reach back
        voxels[x, y, GALLERY] = "White"
        voxels[x, y, GALLERY + 1] = DARK_ROCK
    return voxels


def openings(voxels: dict[Voxel, str]) -> None:
    """Open the tower's door and windows, and the seats of the corbels."""
    wall = int(TOWER_Y) - 4  # the south row of the wall at its foot
    for z in range(FOOT, FOOT + 6):  # the door faces south, set back a stud
        for x in (int(TOWER_X) - 1, int(TOWER_X)):
            del voxels[x, wall, z]
            voxels[x, wall + 1, z] = DOOR
    # Windows in the white bands, by the angle they face, from east counterclockwise.
    for angle, bottom in ((-50, FOOT + 15), (-75, FOOT + 39), (35, FOOT + 18)):
        radius = 4.0 - (bottom - FOOT) / (GALLERY - FOOT)
        x = floor(TOWER_X + (radius - 0.5) * cos(radians(angle)))
        y = floor(TOWER_Y + (radius - 0.5) * sin(radians(angle)))
        for z in range(bottom, bottom + 3):
            voxels[x, y, z] = "Black"
    for back, _ in corbels().values():
        for z in range(GALLERY - 3, GALLERY):
            voxels.pop((*back, z), None)


def cottage_color(x: int, y: int, course: int) -> str:
    """Return the color of a cottage wall cell: wall, door or window."""
    if y == SOUTH and x in DOORWAY and course < 2:
        return DOOR
    front = y == SOUTH and x in WINDOWS
    side = x in {WEST, EAST - 1} and y in {29, 30}
    return GLASS if course == 1 and (front or side) else WALL


SILLS = ((WINDOWS[0], SOUTH - 1), (WINDOWS[1], SOUTH - 1), (EAST, 29), (EAST, 30))


def cottage_voxels() -> dict[Voxel, str]:
    """Return the cottage's walls, with a sill under each window at the front."""
    voxels: dict[Voxel, str] = {}
    for x in range(WEST, EAST):
        for y in range(SOUTH, NORTH):
            if x in {WEST, EAST - 1} or y in {SOUTH, NORTH - 1}:
                for z in range(TERRACE, EAVES):
                    voxels[x, y, z] = cottage_color(x, y, (z - TERRACE) // 3)
    for square in SILLS:
        voxels[*square, TERRACE + 2] = WALL
    return voxels


def made_in(builder: ModelBuilder, part: str, color: int | str) -> bool:
    """Return whether the catalog lists a part in a color."""
    entry = builder.catalog.entry(part)
    if entry is None or not entry.colors:
        return True
    return builder.catalog.resolve_color(color).id in entry.colors


def footprints(
    parts: Mapping[tuple[int, int], str], x: int, y: int, largest: int
) -> Iterator[tuple[int, int]]:
    """Yield footprints, along x by along y, largest first, in a varied order."""
    sizes = [
        size
        for short, long in parts
        for size in {(short, long), (long, short)}
        if short * long <= largest
    ]
    sizes.sort(key=lambda size: (-size[0] * size[1], noise(x, y, *size)))
    yield from sizes


def cover(
    builder: ModelBuilder,
    squares: Mapping[Square, str],
    z: float,
    parts: Mapping[tuple[int, int], str] = TILES,
) -> None:
    """Cover squares with parts of their colors, one layer, each as large as fits."""
    free = dict(squares)
    for x, y in sorted(squares, key=lambda square: (square[1], square[0])):
        if (x, y) not in free:
            continue
        color = free[x, y]
        largest = 8 if noise(x, y, 7) < 0.8 else 2
        for width, depth in footprints(parts, x, y, largest):
            part = parts[min(width, depth), max(width, depth)]
            span = [(x + i, y + j) for i in range(width) for j in range(depth)]
            if all(free.get(square) == color for square in span) and made_in(
                builder, part, color
            ):
                rotation = "R0" if width <= depth else "R90"
                builder.place(part, at=(x, y, z), color=color, rotation=rotation)
                for square in span:
                    del free[square]
                break


def fill(builder: ModelBuilder, features: Mapping[str, dict[Voxel, str]]) -> None:
    """Fill the voxels of every feature in one plan, in a component on the baseplate.

    One plan lets the tower and the cottage rest on the rock. Each part takes its id
    from the feature its corner lies in, such as ``tower.17.29.27``.
    """
    voxels: dict[Voxel, str] = {}
    owners: dict[Voxel, str] = {}
    for name, feature in features.items():
        voxels |= feature
        owners |= dict.fromkeys(feature, name)
    print(f"{len(voxels):,} voxels")
    island = builder.component("island")
    for placement in plan_fill(voxels, made_in=partial(made_in, builder)):
        island.place(
            placement.part,
            at=placement.at,
            color=placement.color,
            rotation=placement.rotation,
            id=".".join(map(str, (owners[placement.at], *placement.at))),
        )
    low_x = min(x for x, _, _ in voxels)
    low_y = min(y for _, y, _ in voxels)
    builder.instance("island", at=(low_x, low_y, BASE), id="island")


def surface(builder: ModelBuilder, land: Land) -> None:
    """Top the paths, the stairs and most of the beach with tiles."""
    layers: defaultdict[int, dict[Square, str]] = defaultdict(dict)
    for square, color in land.tiles.items():
        layers[land.height[square]][square] = color
    for rise, squares in layers.items():
        cover(builder, squares, BASE + rise - 1)


def sea(builder: ModelBuilder, land: Land, kept: set[Square]) -> None:
    """Cover the baseplate around the island with water: foam, shallows and deeps."""
    shore = distances(set(land.height), outward=True)
    water: dict[Square, str] = {}
    ripples: dict[Square, str] = {}  # plates among the tiles, whose studs catch light
    for (x, y), distance in shore.items():
        if (x, y) in kept:
            continue
        depth = distance + 3 * (smooth(x, y, 4.0, 4) - 0.5)
        if distance == 1 and noise(x, y, 5) < 0.75:
            part = "4073" if noise(x, y, 6) < 0.5 else "98138"
            builder.place(part, at=(x, y, BASE), color=FOAM)
        elif depth < 3:
            (ripples if noise(x, y, 18) < 0.3 else water)[x, y] = SHALLOW
        elif depth < 6.5:
            water[x, y] = SEA
        else:
            water[x, y] = DEEP
    cover(builder, water, BASE)
    cover(builder, ripples, BASE, PLATES)


def gallery(builder: ModelBuilder) -> None:
    """Place the corbels under the gallery and the railing around its edge."""
    for (x, y), (back, rotation) in corbels().items():
        corner = (min(x, back[0]), min(y, back[1]), BASE + GALLERY - 3)
        builder.place("3665", at=corner, color="White", rotation=rotation)
    ring = disc(4.0) - disc(3.05)
    deck = BASE + GALLERY + 2
    runs: list[list[Square]] = []
    left = set(ring)
    for step in ((1, 0), (0, 1)):
        for square in sorted(left, key=lambda square: (square[step[0]], square)):
            if square not in left:
                continue
            run = [square]
            while (run[-1][0] + step[0], run[-1][1] + step[1]) in left:
                run.append((run[-1][0] + step[0], run[-1][1] + step[1]))
            if len(run) > 1:
                runs.append(run)
                left -= set(run)
    runs += [[square] for square in sorted(left)]
    for run in runs:
        for x, y in {run[0], run[-1]}:  # posts at both ends of each run
            builder.place("4073", at=(x, y, deck), color="Black")
            builder.place("4073", at=(x, y, deck + 1), color="Black")
        x, y = run[0]
        if len(run) == 1:
            builder.place("98138", at=(x, y, deck + 2), color="Black")
        else:
            rotation = "R90" if run[1][0] > x else "R0"
            part = TILES[1, len(run)]
            builder.place(part, at=(x, y, deck + 2), color="Black", rotation=rotation)


def lantern(builder: ModelBuilder) -> None:
    """Build the lantern: a lamp behind glass, under a roof of slopes and a finial."""
    x, y, z = int(TOWER_X) - 2, int(TOWER_Y) - 2, BASE + GALLERY + 2
    builder.place("3031", at=(x, y, z), color="Black", id="lantern-floor")
    for course in range(3):
        level = z + 1 + 3 * course
        builder.place("3003", at=(x + 1, y + 1, level), color="Trans-Yellow")
        for i in range(4):
            for j in range(4):
                if i in {1, 2} and j in {1, 2}:
                    continue
                corner = i in {0, 3} and j in {0, 3}
                color = "Black" if corner else "Trans-Clear"
                builder.place("3062", at=(x + i, y + j, level), color=color)
    z += 10
    builder.place("3031", at=(x, y, z), color="Black", id="lantern-roof")
    # The dome: a round brick ringed by cheese slopes that fall outward, then a
    # jumper that centers the vent and its finial on the tower's axis.
    builder.place("3941", at=(x + 1, y + 1, z + 1), color=ROOF, id="dome")
    sides = ((x + 1, y, "R0"), (x + 3, y + 1, "R90"), (x + 1, y + 3, "R180"))
    for i, j, rotation in (*sides, (x, y + 1, "R270")):
        builder.place("85984", at=(i, j, z + 1), color=ROOF, rotation=rotation)
    corners = ((x, y, "R0"), (x + 3, y, "R90"), (x + 3, y + 3, "R180"))
    for i, j, rotation in (*corners, (x, y + 3, "R270")):
        builder.place("54200", at=(i, j, z + 1), color=ROOF, rotation=rotation)
    builder.place("87580", at=(x + 1, y + 1, z + 4), color="Black")
    builder.place("3062", at=(x + 1.5, y + 1.5, z + 5), color="Black")
    builder.place("4073", at=(x + 1.5, y + 1.5, z + 8), color="Pearl Gold", id="finial")


def slope_row(
    builder: ModelBuilder, y: int, z: float, widths: tuple[int, ...], rotation: str
) -> None:
    """Lay a row of Slope 45 along x from the roof's west edge; a width 0 skips 2."""
    x = WEST - 1
    for width in widths:
        if width:
            part = {4: "3037", 2: "3039"}[width]  # Slope 45 2 x 4 and 2 x 2
            builder.place(part, at=(x, y, z), color=ROOF, rotation=rotation)
        x += width or 2


def roof(builder: ModelBuilder) -> None:
    """Roof the cottage: plates, two rows of slopes over gable bricks, and a ridge."""
    z = BASE + EAVES
    for y in range(SOUTH - 1, NORTH + 1, 2):  # 10 x 8 plates, a stud over each wall
        builder.place("3832", at=(WEST - 1, y, z), color=DARK_ROCK, rotation="R90")
    slope_row(builder, SOUTH - 1, z + 1, (4, 4, 2), "R0")
    slope_row(builder, NORTH - 1, z + 1, (4, 4, 2), "R180")
    slope_row(builder, SOUTH + 1, z + 4, (4, 2, 0, 2), "R0")  # around the chimney
    slope_row(builder, NORTH - 3, z + 4, (4, 4, 2), "R180")
    for x in range(WEST - 1, EAST + 1, 2):  # the gables, at both ends
        for y in (SOUTH + 1, SOUTH + 3):
            if (x, y) != CHIMNEY:
                builder.place("3003", at=(x, y, z + 1), color=WALL)
    for x in range(WEST - 1, EAST + 1):  # the ridge
        if x not in {CHIMNEY[0], CHIMNEY[0] + 1}:
            builder.place("54200", at=(x, SOUTH + 2, z + 7), color=ROOF)
        builder.place("54200", at=(x, SOUTH + 3, z + 7), color=ROOF, rotation="R180")
    chimney(builder)


def chimney(builder: ModelBuilder) -> None:
    """Raise the chimney through the roof, from the plates to two pots on a cap."""
    x, y = CHIMNEY
    z = BASE + EAVES + 1
    for course in range(4):
        builder.place("3003", at=(x, y, z + 3 * course), color=LIGHT_ROCK)
    builder.place("3022", at=(x, y, z + 12), color=DARK_ROCK)
    for i in (0, 1):
        builder.place("3062", at=(x + i, y + 1, z + 13), color="Dark Orange")
    gull(builder, x + 1, y, z + 13, (1, 0))


def post(builder: ModelBuilder, x: float, y: float, bottom: float, top: float) -> None:
    """Stack round bricks, then round plates, from ``bottom`` to ``top``."""
    z = bottom
    while top - z >= 3:
        builder.place("3062", at=(x, y, z), color=BEAM)
        z += 3
    while top - z >= 1:
        builder.place("4073", at=(x, y, z), color=BEAM)
        z += 1


def components(builder: ModelBuilder) -> None:
    """Define the features that repeat: a gull, a bush and a palm's crown."""
    gull = builder.component("gull")
    gull.place("4073", at=(0, 0, 0), color="White")
    gull.place("54200", at=(0, 0, 1), color=LIGHT_ROCK)  # wings, the tail toward -y
    bush = builder.component("bush")
    bush.place("3941", at=(0, 0, 0), color=LEAF)  # Brick, Round 2 x 2
    bush.place("4032", at=(0, 0, 3), color=GRASS)
    # The crown sits on the trunk's top stud, the square (3, 3). Two tiers of curved
    # slopes stand on Plates 3 x 3: the first on the edges and corners of its plate,
    # the second on the corners of another, so its fronds fall between the first.
    crown = builder.component("crown")
    crown.place("11212", at=(2, 2, 0), color=GRASS)
    for x, y, rotation in ((3, 0, "R0"), (4, 3, "R90"), (3, 4, "R180"), (0, 3, "R270")):
        crown.place("50950", at=(x, y, 1), color=GRASS, rotation=rotation)
    for x, y, rotation in ((2, 1, "R0"), (4, 2, "R90"), (4, 4, "R180"), (1, 4, "R270")):
        crown.place("11477", at=(x, y, 1), color=MEADOW, rotation=rotation)
    crown.place("3062", at=(3, 3, 1), color=WOOD)
    crown.place("11212", at=(2, 2, 4), color=GRASS)
    for x, y, rotation in ((4, 0, "R0"), (4, 4, "R90"), (2, 4, "R180"), (0, 2, "R270")):
        crown.place("50950", at=(x, y, 5), color=GRASS, rotation=rotation)
    crown.place("4073", at=(3, 3, 5), color=GRASS)


def gull(builder: ModelBuilder, x: float, y: float, z: float, tail: Square) -> None:
    """Perch a gull on a stud, its tail toward a direction."""
    builder.instance("gull", at=(x, y, z), rotation=FALLS[tail])


def pier(builder: ModelBuilder, land: Land) -> set[Square]:
    """Build the pier on posts, with bollards, gulls and a lifebuoy at its end.

    Returns the squares of the baseplate the posts stand on.
    """
    south, north = PIER_POSTS[0], PIER_POSTS[-1] + 1
    for x in (PIER_X, PIER_X + 2):
        for y in PIER_POSTS:
            post(builder, x, y, land.top(x, y), DECK)
    # Beams of plates along y, their joints staggered and each over two posts.
    for x, lengths in ((PIER_X, (8, 6)), (PIER_X + 2, (6, 8))):
        y = south
        for length in lengths:
            part = {8: "3460", 6: "3666"}[length]
            builder.place(part, at=(x, y, DECK), color=BEAM)
            y += length
    for y in range(south + 1, north):  # planks of tiles across the beams
        color = WOOD if noise(y, 9) < 0.5 else PLANK
        builder.place("63864", at=(PIER_X, y, DECK + 1), color=color, rotation="R90")
    # The end of the deck is a plate, whose studs hold two bollards and a round tile.
    end = DECK + 2
    builder.place("3623", at=(PIER_X, south, DECK + 1), color=PLANK, rotation="R90")
    builder.place("98138", at=(PIER_X + 1, south, end), color=PLANK)
    builder.place("3062", at=(PIER_X, south, end), color=BEAM, id="bollard")
    builder.place("87087", at=(PIER_X + 2, south, end), color=BEAM, id="hook")
    gull(builder, PIER_X, south, end + 3, (-1, 0))
    gull(builder, PIER_X + 2, south, end + 3, (0, 1))
    # A lifebuoy hangs from the hook's side stud: a round plate rotated upright, with
    # red round tiles on two of its studs.
    buoy = (PIER_X + 1, south - 0.4, end - 2)
    builder.place("4032", at=buoy, color="White", rotation="+x+z", id="lifebuoy")
    for x, z in ((PIER_X + 1, end + 0.5), (PIER_X + 2, end - 2)):
        builder.place("98138", at=(x, south - 0.8, z), color="Red", rotation="+x+z")
    return {
        (PIER_X + i, y)
        for i in (0, 2)
        for y in PIER_POSTS
        if (PIER_X + i, y) not in land.height
    }


def rowboat(builder: ModelBuilder) -> set[Square]:
    """Build the rowboat: a bottom of plates, a bow and stern of inverted slopes.

    Returns the squares of the baseplate it stands on.
    """
    x, y = BOAT
    builder.place("3020", at=(x, y + 1, BASE), color=ROOF)  # Plate 2 x 4
    builder.place("3710", at=(x + 2, y + 1, BASE), color=ROOF)  # Plate 1 x 4
    for i in range(3):
        builder.place("3665", at=(x + i, y, BASE + 1), color=ROOF)  # the bow
        builder.place("3665", at=(x + i, y + 4, BASE + 1), color=ROOF, rotation="R180")
    for i in (0, 2):
        builder.place("3004", at=(x + i, y + 2, BASE + 1), color=ROOF)
        builder.place("3666", at=(x + i, y, BASE + 4), color="White")  # the gunwales
    builder.place("3069", at=(x + 1, y + 2, BASE + 1), color=WOOD)  # the floor
    builder.place("3069", at=(x + 1, y, BASE + 4), color="White")
    builder.place("3069", at=(x + 1, y + 4, BASE + 4), color="White")
    builder.place("63864", at=(x, y + 3, BASE + 5), color=WOOD, rotation="R90")
    return {(x + i, y + j) for i in range(3) for j in range(1, 5)}


def sailboat(builder: ModelBuilder) -> set[Square]:
    """Build a sailboat along x: a hull like the rowboat's, a mast and a sail.

    Returns the squares of the baseplate it stands on.
    """
    x, y = SAILBOAT
    hull = "Yellow"
    builder.place("3020", at=(x + 1, y, BASE), color=hull, rotation="R90")
    builder.place("3710", at=(x + 1, y + 2, BASE), color=hull, rotation="R90")
    for j in range(3):
        builder.place("3665", at=(x, y + j, BASE + 1), color=hull, rotation="R270")
        builder.place("3665", at=(x + 4, y + j, BASE + 1), color=hull, rotation="R90")
    for j in (0, 2):
        builder.place("3004", at=(x + 2, y + j, BASE + 1), color=hull, rotation="R90")
        builder.place("3666", at=(x, y + j, BASE + 4), color="White", rotation="R90")
    builder.place("3023", at=(x + 2, y + 1, BASE + 1), color=WOOD, rotation="R90")
    builder.place("3623", at=(x, y + 1, BASE + 4), color="White", rotation="R90")
    builder.place("3069", at=(x + 4, y + 1, BASE + 4), color="White", rotation="R90")
    # The mast is round bricks on the floor, with a red round plate for a pennant.
    for course in range(6):
        level = BASE + 2 + 3 * course
        builder.place("3062", at=(x + 3, y + 1, level), color="White")
    builder.place("4073", at=(x + 3, y + 1, BASE + 20), color=ROOF, id="pennant")
    # The sail rises in steps beside the mast, and slopes finish each step.
    sail = BASE + 5
    builder.place("3622", at=(x, y + 1, sail), color="White", rotation="R90")
    builder.place("3040", at=(x, y + 1, sail + 3), color="White", rotation="R270")
    builder.place("3005", at=(x + 2, y + 1, sail + 3), color="White")
    builder.place("3040", at=(x + 1, y + 1, sail + 6), color="White", rotation="R270")
    builder.place("54200", at=(x + 2, y + 1, sail + 9), color="White", rotation="R270")
    return {(x + i, y + j) for i in range(1, 5) for j in range(3)}


def palm(
    builder: ModelBuilder, land: Land, x: float, y: float, leans: tuple[Square, ...]
) -> None:
    """Grow a palm: round bricks on jumpers that lean half a stud each, and fronds."""
    z = land.top(x, y)
    for i, j in leans:
        builder.place("3062", at=(x, y, z), color=WOOD)
        z += 3
        rotation = "R0" if i == 0 else "R90"
        builder.place(
            "15573",
            at=(x + min(i, 0), y + min(j, 0), z),
            color=PLANK,
            rotation=rotation,
        )
        x, y, z = x + i / 2, y + j / 2, z + 1
    builder.place("3062", at=(x, y, z), color=WOOD)
    builder.instance("crown", at=(x - 3, y - 3, z + 3))


def flowers(builder: ModelBuilder, land: Land) -> None:
    """Scatter flowers over the grass, and on the cottage's window sills."""
    near = {
        (x + i, y + j) for x, y in land.taken for i in (-1, 0, 1) for j in (-1, 0, 1)
    }
    for x, y in sorted(land.grass - near):
        if noise(x, y, 11) < 0.16:
            color = FLOWERS[int(noise(x, y, 12) * len(FLOWERS))]
            part = "4073" if noise(x, y, 13) < 0.6 else "98138"
            builder.place(part, at=(x, y, land.top(x, y)), color=color)
    for index, (x, y) in enumerate(SILLS):
        color = FLOWERS[(2 * index) % len(FLOWERS)]
        builder.place("4073", at=(x, y, BASE + TERRACE + 3), color=color)


def banks(builder: ModelBuilder, land: Land) -> None:
    """Place the slopes that soften the island's steps: grass banks and rock."""
    for part, corner, rotation, color in land.banks:
        at = (*corner, land.top(*corner))
        builder.place(part, at=at, color=color, rotation=rotation)


def bushes(builder: ModelBuilder, land: Land) -> None:
    """Plant round bushes on level grass, each with a flower on top."""
    planted = 0
    for x, y in sorted(land.grass, key=lambda square: noise(*square, 15)):
        span = {(x + i, y + j) for i in (0, 1) for j in (0, 1)}
        level = len({land.height[square] for square in span & land.grass}) == 1
        if planted < 7 and span <= land.grass and level and not span & land.taken:
            z = land.top(x, y)
            builder.instance("bush", at=(x, y, z))
            color = FLOWERS[planted % len(FLOWERS)]
            builder.place("4073", at=(x + planted % 2, y, z + 4), color=color)
            land.taken |= {(x + i, y + j) for i in range(-1, 3) for j in range(-1, 3)}
            planted += 1


def beach_finds(builder: ModelBuilder, land: Land) -> None:
    """Place a barrel and a crate by the pier, a lamp by the door, and shells."""
    x, y = BARREL
    z = max(land.top(x + i, y + j) for i in (0, 1) for j in (0, 1))
    builder.place("3941", at=(x, y, z), color=WOOD, id="barrel")
    builder.place("14769", at=(x, y, z + 3), color=PLANK)
    x, y = CRATE
    z = max(land.top(x + i, y + j) for i in (0, 1) for j in (0, 1))
    builder.place("3003", at=(x, y, z), color="Dark Orange", id="crate")
    builder.place("3068", at=(x, y, z + 3), color=WOOD)
    x, y = LAMP
    z = land.top(x, y)
    builder.place("3062", at=(x, y, z), color="Black", id="lamp-post")
    builder.place("3062", at=(x, y, z + 3), color="Black")
    builder.place("4073", at=(x, y, z + 6), color="Black")
    builder.place("4073", at=(x, y, z + 7), color="Trans-Yellow", id="lamp")
    builder.place("4073", at=(x, y, z + 8), color="Trans-Yellow")
    builder.place("98138", at=(x, y, z + 9), color="Black")
    shells = ("White", "Bright Light Orange", "Dark Pink", "Orange")
    for x, y in sorted(land.sand - land.taken - set(land.tiles)):
        if noise(x, y, 16) < 0.15:
            color = shells[int(noise(x, y, 17) * len(shells))]
            builder.place("98138", at=(x, y, land.top(x, y)), color=color)


def parasol(builder: ModelBuilder, land: Land) -> None:
    """Open a parasol over a striped towel: a Plate 3 x 3 under cheese slopes."""
    x, y = TOWEL
    for j, color in enumerate(("Dark Pink", "White")):
        at = (x, y + j, land.top(x, y + j))
        builder.place("2431", at=at, color=color, rotation="R90", id=f"towel-{j}")
    x, y = PARASOL
    z = land.top(x, y)
    builder.place("3062", at=(x, y, z), color="White", id="parasol-pole")
    builder.place("3062", at=(x, y, z + 3), color="White")
    builder.place("11212", at=(x - 1, y - 1, z + 6), color=ROOF, id="parasol")
    for (i, j), rotation in FALLS.items():
        at = (x + i, y + j, z + 7)
        builder.place("54200", at=at, color="White", rotation=rotation)
    builder.place("4073", at=(x, y, z + 7), color="White")


def buoys(builder: ModelBuilder) -> set[Square]:
    """Moor two channel buoys: a round brick, a white band, and a light on a jumper.

    Returns the squares of the baseplate they stand on.
    """
    for x, y, color, light in BUOYS:
        builder.place("3941", at=(x, y, BASE), color=color, id=f"buoy-{color.lower()}")
        builder.place("4032", at=(x, y, BASE + 3), color="White")
        builder.place("87580", at=(x, y, BASE + 4), color=color)
        builder.place("3062", at=(x + 0.5, y + 0.5, BASE + 5), color=color)
        builder.place("4073", at=(x + 0.5, y + 0.5, BASE + 8), color=light)
    return {(x + i, y + j) for x, y, _, _ in BUOYS for i in (0, 1) for j in (0, 1)}


def build() -> ModelBuilder:
    """Build the island, its lighthouse, cottage and pier, in a sea on a baseplate."""
    builder = ModelBuilder("lighthouse-island")
    builder.place("4186", at=(0, 0, 0), color=DEEP, id="baseplate")
    components(builder)
    land = survey()
    features = {
        "rock": island_voxels(land),
        "arch": arch_voxels(),
        "tower": tower_voxels(),
        "cottage": cottage_voxels(),
    }
    fill(builder, features)
    surface(builder, land)
    gallery(builder)
    lantern(builder)
    roof(builder)
    kept = pier(builder, land) | rowboat(builder) | sailboat(builder) | buoys(builder)
    sea(builder, land, kept)
    for x, y, leans in PALMS:
        palm(builder, land, x, y, leans)
    banks(builder, land)
    for x, y, tail in GULLS:
        gull(builder, x, y, land.top(x, y), tail)
    bushes(builder, land)
    beach_finds(builder, land)
    parasol(builder, land)
    flowers(builder, land)
    return builder
