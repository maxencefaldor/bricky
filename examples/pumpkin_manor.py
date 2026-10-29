# Copyright 2026 Maxence Faldor
"""A haunted hill for Halloween: a crooked manor whose tower is a giant jack-o'-lantern.

- A Baseplate 48 x 48 holds a hill that twists up in brick-high terraces, a graveyard,
  a pumpkin patch and a witch's clearing. The ground, the hill, the walls, the tower,
  the moon, the tree, the ghosts and the cauldron are voxels that ``plan_fill``, the
  planner behind ``builder.fill``, covers in one plan; the script then drops any part
  that no chain of studs would ground.
- The manor's wing leans a stud forward each story, and the hall's upper floor juts
  over the door. Windows glow in Trans-Orange and Trans-Yellow under Arch 1 x 4.
- Roofs are rows of Slope 65 over a gable core, crested with cheese slopes. Twisted
  chimneys rise through them, and a dormer wears a small gable of Slope 45.
- The leaning stone tower carries a jack-o'-lantern 16 studs wide, ribbed and carved
  toward the camera, under a witch's hat whose tip bends east. The full moon stands on
  a pole hidden behind the manor, and bats fly across it in silhouette.
- Tiles held upright on side studs give eyes to the black cat, the scarecrow, a skull
  and the carved pumpkins. Jumpers center stems and the broom's handle, round plates
  chain lanterns under the tree's limbs, and Slope 45 banks soften the terraces.
- Headstones, lamp posts, pumpkins, crows, toadstools and candles are components.

Run: ``uv run bricky build examples/pumpkin_manor.py``
"""

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import partial
from itertools import pairwise
from math import atan2, cos, floor, hypot, radians, sin

from bricky import ModelBuilder
from bricky.fill import BRICKS as FILL_BRICKS
from bricky.fill import PLATES as FILL_PLATES
from bricky.fill import Placement, plan_fill

type Square = tuple[int, int]
type Voxel = tuple[int, int, int]
type Voxels = dict[Voxel, str]
type Point = tuple[float, float, float]

SIZE = 48  # The Baseplate 48 x 48, in studs
BASE = 0.5  # The top of the baseplate, in plates
GROUND = 2  # Layers of ground over the baseplate
TOP = 17  # The first free layer over the hill's plateau

GRASS, DRY, MUD = "Dark Green", "Olive Green", "Dark Brown"
ROCK, CRACK, PEBBLE, LICHEN = (
    "Dark Bluish Gray",
    "Black",
    "Light Bluish Gray",
    "Sand Green",
)
WALL, TIMBER, ROOF, TRIM = "Sand Green", "Dark Brown", "Magenta", "Black"
GLOW, LAMP, BACKING, BREW = (
    "Trans-Orange",
    "Trans-Yellow",
    "Bright Light Orange",
    "Trans-Green",
)
PUMPKIN, RIB, PITH, FACE, STEM = (
    "Orange",
    "Dark Orange",
    "Yellow",
    "Black",
    "Olive Green",
)
MOON, MARE = "Bright Light Yellow", "Tan"
BARK, WOOD, STRAW, SHEET = "Dark Brown", "Reddish Brown", "Tan", "White"
ROD = "Trans-Clear"

STORY = 12  # Layers of wall in each story

# The camera looks from 35 degrees east of south, and the faces look back at it.
VIEW = radians(-55)

# The hill: a plateau under the buildings, falling away in twisted ridges.
PLATEAU = (1.0, 27.0, 24.0, 45.0)  # West, south, east, north edges, in studs
HILL_X, HILL_Y = 14.0, 36.0
REACH = 8.5  # Studs from the plateau's edge to the foot of the hill

# Flat grounds at the foot of the hill: west, south, east, north squares.
GRAVEYARD = (0, 0, 16, 14)
PATCH = (28, 0, 47, 12)
CLEARING = (29, 14, 40, 23)

# The pumpkin tower: a leaning shaft, the jack-o'-lantern, and its hat.
TOWER_X, TOWER_Y = 26.0, 34.0
SHAFT_RADIUS = 3.6
SHAFT_TOP = TOP + 30
LEAN = 1.5  # Studs the shaft leans east over its height
PUMPKIN_RADIUS = 8.0
PUMPKIN_HALF = 13  # Layers from the pumpkin's center to its top
RIBS = 12
HAT = 34  # Layers of the hat's cone

# The moon: a disc two studs thick, on a pole hidden behind the manor.
MOON_X, MOON_Y, MOON_Z = 10.0, 44, 78
MOON_RADIUS = 9.5
CRATERS = ((4.5, 88, 1.6), (15.5, 72, 2.0), (6.0, 66, 1.4), (16.0, 88, 1.0))

# The dead tree: a trunk of three twisted strands, then limbs that fork twice.
TREE_X, TREE_Y = 44.0, 33.0
FORK = 31  # The layer where the trunk forks into limbs
LIMBS = (
    (200, 28, 10.0, 1.25),
    (240, 46, 7.5, 1.1),
    (140, 50, 6.5, 1.05),
    (95, 55, 6.5, 1.05),
    (-70, 50, 6.0, 1.0),
    (30, 64, 5.5, 1.0),
)  # Azimuth and elevation in degrees, length and radius in studs

# The path: from the manor's door down the stairs to the south edge.
PATH = (
    (13.0, 31.0),
    (13.0, 27.0),
    (13.0, 20.0),
    (16.0, 17.0),
    (21.0, 14.5),
    (24.0, 9.0),
    (24.5, 4.0),
    (23.5, -1.0),
)
STAIRS_FROM = 28  # The stairs fall two plates a stud south of this row


@dataclass(frozen=True, slots=True)
class Story:
    """One story of the manor: its footprint, first layer, door and windows."""

    x: int
    y: int
    width: int
    depth: int
    z: int
    windows: tuple[tuple[str, int, str], ...] = ()
    door: int | None = None


@dataclass(frozen=True, slots=True)
class Roof:
    """A gable roof: footprint, eave layer, ridge direction, slopes and colors."""

    x: int
    y: int
    width: int
    depth: int
    z: int
    along_x: bool
    steep: bool = True  # Slope 65, or Slope 45
    gable: str = WALL
    color: str = ROOF
    chimney: int | None = None  # Where a twisted chimney rises, along the ridge
    dormer: int | None = None  # Where a dormer four studs wide sits on the front


WING = (
    Story(3, 29, 6, 12, TOP, (("south", 5, GLOW), ("east", 30, LAMP))),
    Story(
        3,
        28,
        6,
        12,
        TOP + 13,
        (("south", 5, LAMP), ("west", 33, GLOW), ("north", 5, GLOW)),
    ),
    Story(2, 27, 6, 12, TOP + 26, (("south", 4, GLOW),)),
)
HALL = (
    Story(
        9,
        32,
        9,
        10,
        TOP,
        (("south", 15, GLOW), ("east", 35, LAMP), ("north", 11, GLOW)),
        door=11,
    ),
    Story(
        9,
        31,
        9,
        10,
        TOP + 13,
        (("south", 10, LAMP), ("south", 14, GLOW), ("north", 13, LAMP)),
    ),
)
CRYPT = Story(2, 9, 8, 6, GROUND, door=5)
ROOFS = (
    Roof(1, 26, 8, 14, TOP + 38, along_x=False, chimney=12),
    Roof(9, 30, 10, 12, TOP + 25, along_x=True, chimney=6, dormer=2),
    Roof(1, 8, 10, 8, GROUND + 15, along_x=False, steep=False, gable=ROCK, color=ROCK),
)
CHIMNEY = ((0, 0), (0, 0), (0, 0), (1, 0), (1, 1), (0, 1), (0, 0))  # Course offsets

FACADES = {
    "south": ((1, 0), (0, -1)),
    "north": ((1, 0), (0, 1)),
    "west": ((0, 1), (-1, 0)),
    "east": ((0, 1), (1, 0)),
}  # Each facade's direction along the wall, and its outward direction

BAT = (
    "XX.......XX",
    "XXX.X.X.XXX",
    "XXXXXXXXXXX",
    ".XXXXXXXXX.",
    "..XX.X.XX..",
    "...X...X...",
)  # A bat's silhouette, top row first, one stud by one plate per character
SMALL_BAT = (
    "X.......X",
    "XX.X.X.XX",
    ".XXXXXXX.",
    "..X.X.X..",
)

# The graveyard: headstones (west square, row, kind, color), ghosts on rods.
HEADSTONES = (
    (2, 5, "cross", PEBBLE),
    (6, 5, "peak", ROCK),
    (9, 5, "rounded", PEBBLE),
    (12, 5, "slab", LICHEN),
    (11, 11, "peak", PEBBLE),
    (13, 13, "rounded", ROCK),
)
GHOSTS = ((8, 2, 9), (41, 19, 15), (6, 23, 10))  # The center square, the rod's length
GHOST = (2.6, 2.6, 2.5, 2.4, 2.3, 2.2, 2.1, 2.05, 2.0, 2.0, 1.9, 1.75, 1.45, 0.9)
GATE_Y = (4, 9)  # The first rows of the gate's two pillars, each three studs deep

# The pumpkin patch and the clearing with the witch's cauldron.
BIG_PUMPKINS = (
    (33.0, 5.0, 2.7, True),
    (44.0, 3.0, 2.2, False),
    (42.5, 9.5, 1.8, False),
)
ROUND_PUMPKINS = ((30, 9), (35, 9), (36, 1), (40, 1), (45, 6), (29, 0))
SQUASHES = ((29, 6), (38, 10), (41, 5), (46, 1), (34, 1), (39, 3))
SCARECROW = (38, 6)
CAULDRON = (35, 20)  # The center of the cauldron, at a corner of four studs
BOWL = (1.7, 2.5, 2.95, 3.1, 3.1, 3.0, 2.8, 2.6, 3.0)  # Radius of each layer
LEGS = ((-2, -1), (1, 0), (-1, 1), (0, -2))  # Squares of the legs, from the center
TOADSTOOLS = ((30, 15), (39, 16), (30, 21), (38, 23), (36, 15))
LAMPS = ((10, 20, "R0"), (20, 11, "R0"), (27, 6, "R180"))  # Posts, and their rotations


@dataclass(slots=True)
class Scene:
    """The builder, the ground's height and the squares details already use."""

    builder: ModelBuilder
    height: dict[Square, int]
    taken: set[Square] = field(default_factory=set)

    def put(self, part: str, at: Point, color: str, rotation: str = "R0") -> None:
        """Place a part, its corner given in studs and layers over the baseplate."""
        x, y, z = at
        self.builder.place(part, at=(x, y, BASE + z), color=color, rotation=rotation)

    def copy(self, component: str, at: Point, rotation: str = "R0") -> None:
        """Place an instance of a component, its corner given like ``put``'s."""
        x, y, z = at
        self.builder.instance(component, at=(x, y, BASE + z), rotation=rotation)


def hashed(*values: int) -> float:
    """Return a repeatable number in [0, 1) for a tuple of integers."""
    state = 2166136261
    for value in values:
        state = ((state ^ (value & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
        state ^= state >> 15
        state = (state * 2246822519) & 0xFFFFFFFF
        state ^= state >> 13
    return state / 2**32


def noise(x: float, y: float, seed: int) -> float:
    """Return smooth value noise in [0, 1) that varies over about one unit."""
    corner_x, corner_y = floor(x), floor(y)
    ease_x, ease_y = (
        (value - corner) ** 2 * (3 - 2 * (value - corner))
        for value, corner in ((x, corner_x), (y, corner_y))
    )
    south, north = (
        hashed(corner_x, corner_y + row, seed) * (1 - ease_x)
        + hashed(corner_x + 1, corner_y + row, seed) * ease_x
        for row in (0, 1)
    )
    return south * (1 - ease_y) + north * ease_y


def inside(square: Square, zone: tuple[int, int, int, int]) -> bool:
    """Return whether a square lies in a zone, its edges included."""
    west, south, east, north = zone
    return west <= square[0] <= east and south <= square[1] <= north


def segment_distance(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    """Return the distance from a point to a segment in the plane."""
    run_x, run_y = end[0] - start[0], end[1] - start[1]
    away_x, away_y = point[0] - start[0], point[1] - start[1]
    share = (away_x * run_x + away_y * run_y) / (run_x * run_x + run_y * run_y)
    share = max(0.0, min(1.0, share))
    return hypot(away_x - share * run_x, away_y - share * run_y)


def on_path(x: int, y: int) -> bool:
    """Return whether the square lies on the path."""
    point = (x + 0.5, y + 0.5)
    return any(
        segment_distance(point, start, end) < 1.1 for start, end in pairwise(PATH)
    )


def plateau_distance(x: float, y: float) -> float:
    """Return the distance from a point to the plateau, 0 inside it."""
    west, south, east, north = PLATEAU
    offset_x = max(west - x, 0.0, x - east)
    offset_y = max(south - y, 0.0, y - north)
    tower = hypot(x - TOWER_X - 1, y - TOWER_Y) - 6.0
    return max(0.0, min(hypot(offset_x, offset_y), tower))


def hill_height(x: int, y: int) -> int:
    """Return the first free layer over a square of the hill or the ground."""
    if any(inside((x, y), zone) for zone in (GRAVEYARD, PATCH, CLEARING)):
        return GROUND
    center_x, center_y = x + 0.5, y + 0.5
    distance = plateau_distance(center_x, center_y)
    if distance == 0:
        return TOP
    angle = atan2(center_y - HILL_Y, center_x - HILL_X)
    distance += 1.4 * sin(3 * angle + 0.9 * distance)
    distance += 2.0 * (noise(center_x / 3, center_y / 3, 7) - 0.5)
    drop = TOP * min(1.0, (max(0.0, distance) / REACH) ** 0.8)
    return max(GROUND, GROUND + 3 * round((TOP - drop - GROUND) / 3))  # Brick steps


def heights() -> dict[Square, int]:
    """Return the first free layer over every square of the baseplate."""
    height: dict[Square, int] = {}
    for x in range(SIZE):
        for y in range(SIZE):
            if on_path(x, y) and y >= STAIRS_FROM - 10:
                height[x, y] = max(GROUND, min(TOP, TOP - 2 * (STAIRS_FROM - y)))
            elif on_path(x, y):
                height[x, y] = GROUND
            else:
                height[x, y] = hill_height(x, y)
    return height


def surface_color(x: int, y: int) -> str:
    """Return the color of the top layer of the ground or the hill."""
    patchy = noise(x / 4, y / 4, 3)
    if inside((x, y), PATCH):
        return GRASS if hashed(x, y, 4) < 0.06 else MUD
    if inside((x, y), GRAVEYARD) or inside((x, y), CLEARING):
        return MUD if patchy < 0.35 else DRY if patchy < 0.75 else GRASS
    if noise(x / 3, y / 3, 5) < 0.16:
        return MUD
    return DRY if patchy < 0.33 else GRASS


def rock_color(x: int, y: int, z: int) -> str:
    """Return the color of an exposed side of the hill: strata and lichen."""
    value = noise(x / 2 + z / 7, y / 2 - z / 9, 11)
    if (z + round(3 * noise(x / 3, y / 3, 13))) % 6 == 0:
        return CRACK
    if value > 0.72:
        return LICHEN
    if value < 0.2:
        return PEBBLE
    return ROCK


def terrain(height: dict[Square, int]) -> Voxels:
    """Return the ground and the hill as voxels; the path's top layer is left open."""
    voxels: Voxels = {}
    for (x, y), top in height.items():
        below = min(
            height.get((x + offset_x, y + offset_y), GROUND)
            for offset_x, offset_y in ((1, 0), (-1, 0), (0, 1), (0, -1))
        )
        path = on_path(x, y)
        for z in range(top):
            if path and z == top - 1:
                continue  # A tile covers the path
            if z == top - 1:
                voxels[x, y, z] = surface_color(x, y)
            elif z < GROUND - 1:
                voxels[x, y, z] = MUD
            elif z >= below:
                voxels[x, y, z] = rock_color(x, y, z)
            else:
                voxels[x, y, z] = ROCK
    return voxels


def wall_cells(story: Story) -> Iterable[Square]:
    """Yield the squares of a story's outer wall."""
    for x in range(story.x, story.x + story.width):
        for y in range(story.y, story.y + story.depth):
            edge_x = x in {story.x, story.x + story.width - 1}
            edge_y = y in {story.y, story.y + story.depth - 1}
            if edge_x or edge_y:
                yield x, y


def facade_cells(story: Story, facade: str, offset: int) -> tuple[Square, Square]:
    """Return the two wall squares of a window or a door, west or south one first."""
    rows = {
        "south": story.y,
        "north": story.y + story.depth - 1,
        "west": story.x,
        "east": story.x + story.width - 1,
    }
    row = rows[facade]
    if facade in {"south", "north"}:
        return (offset, row), (offset + 1, row)
    return (row, offset), (row, offset + 1)


def story_voxels(story: Story, voxels: Voxels, arches: list[tuple[Voxel, str]]) -> None:
    """Add a story's walls, windows and door to the voxels, and note their arches."""
    corners = {
        (story.x, story.y),
        (story.x + story.width - 1, story.y),
        (story.x, story.y + story.depth - 1),
        (story.x + story.width - 1, story.y + story.depth - 1),
    }
    for x, y in wall_cells(story):
        for z in range(story.z, story.z + STORY):
            if (x, y) in corners:
                voxels[x, y, z] = TIMBER
            elif story.z == TOP and z < TOP + 3:
                voxels[x, y, z] = ROCK
            else:
                voxels[x, y, z] = WALL
    openings = list(story.windows)
    if story.door is not None:
        openings.append(("south", story.door, "door"))
    for spec in openings:
        opening(story, spec, voxels, arches)


def opening(
    story: Story,
    spec: tuple[str, int, str],
    voxels: Voxels,
    arches: list[tuple[Voxel, str]],
) -> None:
    """Open a window or a door under an Arch 1 x 4, with glass and a glowing backing."""
    facade, offset, glass = spec
    (along_x, along_y), (out_x, out_y) = FACADES[facade]
    first, second = facade_cells(story, facade, offset)
    door = glass == "door"
    bottom = story.z if door else story.z + 3
    for x, y in (first, second):
        for z in range(bottom, story.z + 9):
            voxels[x, y, z] = TIMBER if door else glass
        for z in range(story.z, story.z + STORY):
            voxels[x - out_x, y - out_y, z] = TIMBER if door else BACKING
    ends = [
        (first[0] - along_x, first[1] - along_y),
        (second[0] + along_x, second[1] + along_y),
    ]
    if not door:
        for x, y in (ends[0], first, second, ends[1]):
            voxels[x, y, story.z + 2] = TRIM
        for x, y in (first, second):
            voxels[x + out_x, y + out_y, story.z + 2] = TRIM
    for x, y in (ends[0], first, second, ends[1]):
        for z in range(story.z + 9, story.z + 12):
            voxels.pop((x, y, z), None)
    low_x, low_y = min(ends)
    rotation = "R90" if facade in {"south", "north"} else "R0"
    arches.append(((low_x, low_y, story.z + 9), rotation))


def floor_voxels(lower: Story, upper: Story, voxels: Voxels) -> None:
    """Add the timber floor between two stories, under both footprints."""
    for story in (lower, upper):
        for x in range(story.x, story.x + story.width):
            for y in range(story.y, story.y + story.depth):
                voxels[x, y, lower.z + STORY] = TIMBER


def roof_frame(roof: Roof) -> tuple[int, int, int, int]:
    """Return a roof's span across the ridge, length along it, rows and row height."""
    span = roof.depth if roof.along_x else roof.width
    length = roof.width if roof.along_x else roof.depth
    return span, length, (span - 4) // 2 + 1, 6 if roof.steep else 3


def roof_square(roof: Roof, across: int, along: int) -> Square:
    """Return the square at a position across and along a roof's ridge."""
    if roof.along_x:
        return roof.x + along, roof.y + across
    return roof.x + across, roof.y + along


def roof_voxels(roof: Roof, voxels: Voxels) -> None:
    """Add a roof's eave plates, the gable core its slopes rest on, and its extras."""
    for x in range(roof.x, roof.x + roof.width):
        for y in range(roof.y, roof.y + roof.depth):
            voxels[x, y, roof.z] = TRIM
    span, length, rows, rise = roof_frame(roof)
    for level in range(rows - 1):
        bottom = roof.z + 1 + rise * level
        for across in range(level + 2, span - level - 2):
            for along in range(1, length - 1):
                x, y = roof_square(roof, across, along)
                for z in range(bottom, bottom + rise):
                    voxels[x, y, z] = roof.gable
    if roof.gable == WALL:
        attic_windows(roof, voxels)
    if roof.dormer is not None:
        dormer_voxels(roof, voxels)
    if roof.chimney is not None:
        chimney_voxels(roof, voxels)


def attic_windows(roof: Roof, voxels: Voxels) -> None:
    """Light a window two studs wide in each gable of a roof."""
    span, length, _, rise = roof_frame(roof)
    for along in (1, length - 2):
        for across in (span // 2 - 1, span // 2):
            x, y = roof_square(roof, across, along)
            for z in range(roof.z + 2 + rise, roof.z + 5 + rise):
                voxels[x, y, z] = LAMP


def chimney_voxels(roof: Roof, voxels: Voxels) -> None:
    """Add a chimney that rises through a roof's ridge, then twists course by course."""
    _, _, rows, rise = roof_frame(roof)
    along = roof.chimney if roof.chimney is not None else 0
    base = roof.z + 1 + rise * (rows - 1)
    for course, (shift_along, shift_across) in enumerate(CHIMNEY):
        color = TRIM if course == len(CHIMNEY) - 1 else ROCK
        for step in (0, 1):
            for across in (rows, rows + 1):
                x, y = roof_square(
                    roof, across + shift_across, along + step + shift_along
                )
                for z in range(base + 3 * course, base + 3 * course + 3):
                    voxels[x, y, z] = color


def dormer_voxels(roof: Roof, voxels: Voxels) -> None:
    """Add a dormer on a roof's front: walls, a glowing window and its sill."""
    along = roof.dormer if roof.dormer is not None else 0
    base = roof.z + 1 + 6
    for step in range(4):
        for across in range(1, 5):
            x, y = roof_square(roof, across, along + step)
            for z in range(base, base + 12):
                corner = step in {0, 3} and across == 1
                voxels[x, y, z] = TIMBER if corner else WALL
    for step in (1, 2):
        x, y = roof_square(roof, 1, along + step)
        for z in range(base + 3, base + 9):
            voxels[x, y, z] = LAMP
        for z in range(base + 3, base + 12):
            voxels[x, y + 1, z] = BACKING
        voxels[x, y, base + 2] = TRIM
    for step in range(4):
        x, y = roof_square(roof, 1, along + step)
        for z in range(base + 9, base + 12):
            voxels.pop((x, y, z), None)


def place_roof(scene: Scene, roof: Roof) -> None:
    """Place a roof's rows of slopes and its ridge of cheese slopes."""
    span, length, rows, rise = roof_frame(roof)
    front, back = ("R0", "R180") if roof.along_x else ("R270", "R90")
    wide, narrow = ("3678b", "60481") if roof.steep else ("3039", "3040")
    chimney = set() if roof.chimney is None else {roof.chimney, roof.chimney + 1}
    for level in range(rows):
        along = 0
        while along < length:
            size = 2 if length - along >= 2 else 1
            part = wide if size == 2 else narrow
            skip = level == rows - 1 and along in chimney
            dormer = roof.dormer is not None and level in {1, 2}
            dormer = dormer and along in {roof.dormer, (roof.dormer or 0) + 2}
            for across, rotation in ((level, front), (span - 2 - level, back)):
                if not skip and not (dormer and rotation == front):
                    x, y = roof_square(roof, across, along)
                    at = (x, y, roof.z + 1 + rise * level)
                    scene.put(part, at, roof.color, rotation)
            along += size
    if roof.dormer is not None:
        dormer_roof(scene, roof)
    for along in range(length):
        crest = along not in chimney
        for across, rotation in ((rows, front), (rows + 1, back)):
            level = rows if crest else rows - 1
            step = across if crest else across - 1 if rotation == front else across + 1
            x, y = roof_square(roof, step, along)
            scene.put("54200", (x, y, roof.z + 1 + rise * level), TRIM, rotation)


def dormer_roof(scene: Scene, roof: Roof) -> None:
    """Top a dormer with an arch over its window and a small gable of slopes."""
    along = roof.dormer if roof.dormer is not None else 0
    x, y = roof_square(roof, 1, along)
    top = roof.z + 1 + 6 + 12
    scene.put("3659", (x, y, top - 3), TRIM, "R90")
    scene.put("3039", (x, y, top), ROOF, "R270")
    scene.put("3039", (x + 2, y, top), ROOF, "R90")
    for offset_y in (0, 1):
        scene.put("54200", (x + 1, y + offset_y, top + 3), TRIM, "R270")
        scene.put("54200", (x + 2, y + offset_y, top + 3), TRIM, "R90")


def manor(voxels: Voxels) -> list[tuple[Voxel, str]]:
    """Add the manor's and the crypt's walls, floors and roof cores; return arches."""
    arches: list[tuple[Voxel, str]] = []
    for stories in (WING, HALL):
        for story in stories:
            story_voxels(story, voxels, arches)
        for lower, upper in pairwise(stories):
            floor_voxels(lower, upper, voxels)
    crypt(voxels, arches)
    for roof in ROOFS:
        roof_voxels(roof, voxels)
    return arches


def crypt(voxels: Voxels, arches: list[tuple[Voxel, str]]) -> None:
    """Add the crypt: stone walls, pale corners, and a doorway glowing green."""
    for x in range(CRYPT.x, CRYPT.x + CRYPT.width):
        for y in range(CRYPT.y, CRYPT.y + CRYPT.depth):
            for z in range(CRYPT.z, CRYPT.z + 15):
                corner = x in {CRYPT.x, CRYPT.x + CRYPT.width - 1}
                low = z < CRYPT.z + 2 or z == CRYPT.z + 14
                moss = hashed(x, y, z, 51) < 0.25 and z < CRYPT.z + 6
                voxels[x, y, z] = PEBBLE if corner or low else LICHEN if moss else ROCK
    door = CRYPT.door if CRYPT.door is not None else 0
    for x in (door, door + 1):
        for z in range(CRYPT.z, CRYPT.z + 9):
            voxels.pop((x, CRYPT.y, z), None)
            voxels[x, CRYPT.y + 1, z] = BREW
    for x in range(door - 1, door + 3):
        for z in range(CRYPT.z + 9, CRYPT.z + 12):
            voxels.pop((x, CRYPT.y, z), None)
    arches.append(((door - 1, CRYPT.y, CRYPT.z + 9), "R90"))
    for x in (door, door + 1):  # A glowing slot in the pediment
        voxels[x, CRYPT.y, CRYPT.z + 18] = BREW


def shaft_center(z: int) -> tuple[float, float]:
    """Return the center of the leaning shaft at a layer."""
    rise = max(0, z - TOP) / (SHAFT_TOP - TOP)
    return TOWER_X + LEAN * rise * rise, TOWER_Y


def facing(offset_x: float, offset_y: float) -> tuple[float, float]:
    """Return how far an offset reaches toward the camera, and to its right."""
    return offset_x * cos(VIEW) + offset_y * sin(VIEW), -offset_x * sin(
        VIEW
    ) + offset_y * cos(VIEW)


def tower(voxels: Voxels) -> None:
    """Add the leaning stone shaft, its door, and slit windows that climb around it."""
    for z in range(GROUND, SHAFT_TOP):
        center_x, center_y = shaft_center(z)
        for x in range(
            floor(center_x - SHAFT_RADIUS), floor(center_x + SHAFT_RADIUS) + 1
        ):
            for y in range(
                floor(center_y - SHAFT_RADIUS), floor(center_y + SHAFT_RADIUS) + 1
            ):
                offset_x, offset_y = x + 0.5 - center_x, y + 0.5 - center_y
                radius = hypot(offset_x, offset_y)
                if radius >= SHAFT_RADIUS:
                    continue
                ahead, aside = facing(offset_x, offset_y)
                spiral = atan2(offset_y, offset_x) - VIEW - 0.9 * ((z - TOP) // 10)
                slit = (
                    z >= TOP
                    and radius > SHAFT_RADIUS - 1.2
                    and (z - TOP) % 10 in range(2, 7)
                    and abs((spiral + 3.1416) % 6.2832 - 3.1416) < 0.3
                )
                vine = atan2(offset_y, offset_x) - VIEW - 1.2 - 0.5 * sin(z / 3)
                ivy = z < TOP + 24 and abs((vine + 3.1416) % 6.2832 - 3.1416) < 0.22
                if TOP <= z < TOP + 9 and ahead > SHAFT_RADIUS - 1.3 and abs(aside) < 1:
                    voxels[x, y, z] = TIMBER
                elif ivy and radius > SHAFT_RADIUS - 1.2:
                    voxels[x, y, z] = GRASS
                elif slit:
                    voxels[x, y, z] = GLOW
                elif hashed(x, y, z // 3, 17) < 0.18:
                    voxels[x, y, z] = PEBBLE
                else:
                    voxels[x, y, z] = ROCK


def face_feature(right: float, up: float) -> bool:
    """Return whether a point of the face, in studs from its center, is carved."""
    for side in (-1, 1):  # Triangle eyes, apex up
        if 0.9 <= up <= 3.9 and abs(right - side * 3.0) <= 2.0 * (3.9 - up) / 3.0:
            return True
    if -0.2 <= up <= 0.8 and abs(right) <= 0.3 + 0.7 * (0.8 - up):
        return True  # The nose
    upper = -0.7 + 0.07 * right * right
    lower = -3.0 + 0.1 * right * right
    if abs(right) <= 5.2 and lower <= up <= upper:
        teeth = (1.5 <= abs(right) <= 2.6 and up >= upper - 0.7) or (
            abs(right) <= 0.6 and up <= lower + 0.8
        )
        return not teeth
    return False


@dataclass(frozen=True, slots=True)
class Gourd:
    """A ribbed pumpkin of voxels: center, radius, half height, carved face or not."""

    x: float
    y: float
    z: int
    radius: float
    half: int
    carved: bool


def gourd(voxels: Voxels, shape: Gourd) -> None:
    """Add a ribbed pumpkin: its face, if carved, looks toward the camera."""
    center = shape.z + shape.half
    for z in range(shape.z, center + shape.half):
        height = (z + 0.5 - center) / shape.half
        reach = shape.radius * (1 - abs(height) ** 3.0) ** (1 / 2.4)
        below = min(1.0, abs((z - 0.5 - center) / shape.half))
        held = shape.radius * (1 - below**3.0) ** (1 / 2.4)
        scale = shape.radius / PUMPKIN_RADIUS
        for x in range(floor(shape.x - reach), floor(shape.x + reach) + 1):
            for y in range(floor(shape.y - reach), floor(shape.y + reach) + 1):
                offset_x, offset_y = x + 0.5 - shape.x, y + 0.5 - shape.y
                radius = hypot(offset_x, offset_y)
                ahead, aside = facing(offset_x, offset_y)
                face = shape.carved and ahead > 0.45 * radius
                groove = (
                    0.0 if face else (1 + cos(RIBS * atan2(offset_y, offset_x))) / 2
                )
                limit = reach * (1 - 0.07 * groove**4)
                if radius >= limit:
                    continue
                up = ((z + 0.5 - center) / 2.5 - 0.3 * scale) / scale
                carved = face and face_feature(aside / scale, up)
                if carved and limit - radius < 1.0:
                    voxels[x, y, z] = FACE
                elif carved and limit - radius < 2.0:
                    voxels[x, y, z] = PITH
                else:  # A rib only where the layer below holds it
                    rib = groove > 0.85 and radius < held - 0.6
                    voxels[x, y, z] = RIB if rib else PUMPKIN


def hat(voxels: Voxels) -> None:
    """Add the witch's hat: a wide brim, a band, and a cone whose tip bends east."""
    center_x, center_y = shaft_center(SHAFT_TOP)
    bottom = SHAFT_TOP + 2 * PUMPKIN_HALF
    for z in range(bottom - 1, bottom + 1):
        for x in range(floor(center_x - 7), floor(center_x + 7) + 1):
            for y in range(floor(center_y - 7), floor(center_y + 7) + 1):
                if hypot(x + 0.5 - center_x, y + 0.5 - center_y) < 6.6:
                    voxels[x, y, z] = TRIM
    for step in range(HAT):
        rise = step / HAT
        radius = 4.1 * (1 - rise) + 0.55
        tip_x = center_x + 5.0 * rise**2.5
        tip_y = center_y - 0.5 * rise**2.5
        color = ROOF if step < 3 else TRIM
        for x in range(floor(tip_x - radius), floor(tip_x + radius) + 1):
            for y in range(floor(tip_y - radius), floor(tip_y + radius) + 1):
                if hypot(x + 0.5 - tip_x, y + 0.5 - tip_y) < radius:
                    voxels[x, y, bottom + 1 + step] = color


def silhouette(voxels: Voxels, art: tuple[str, ...], corner: Voxel) -> None:
    """Add a shape drawn in characters, upright and facing south, top row first."""
    x, y, top = corner
    for row, line in enumerate(art):
        for column, mark in enumerate(line):
            if mark == "X":
                voxels[x + column, y, top - row] = TRIM


def moon(voxels: Voxels, height: dict[Square, int]) -> None:
    """Add the full moon, its craters, two bats across its face, and its pole."""
    for x in range(floor(MOON_X - MOON_RADIUS), floor(MOON_X + MOON_RADIUS) + 1):
        for z in range(MOON_Z - 24, MOON_Z + 25):
            offset_x = x + 0.5 - MOON_X
            dz = (z + 0.5 - MOON_Z) / 2.5
            if hypot(offset_x, dz) >= MOON_RADIUS:
                continue
            crater = any(
                hypot(x + 0.5 - crater_x, (z + 0.5 - crater_z) / 2.5) < size
                for crater_x, crater_z, size in CRATERS
            )
            for y in (MOON_Y, MOON_Y + 1):
                voxels[x, y, z] = MARE if crater else MOON
    for y in (MOON_Y, MOON_Y + 1):  # The bats show on both faces of the disc
        silhouette(voxels, BAT, (round(MOON_X) - 7, y, MOON_Z + 15))
        silhouette(voxels, SMALL_BAT, (round(MOON_X) + 1, y, MOON_Z + 6))
    for x in (round(MOON_X) - 1, round(MOON_X)):
        for z in range(height[x, MOON_Y + 1], MOON_Z - 22):
            voxels[x, MOON_Y + 1, z] = TRIM


def capsule(
    voxels: Voxels, start: Point, end: Point, radii: tuple[float, float], color: str
) -> None:
    """Add the voxels within a tapering radius of a segment, measured in studs."""
    first = (start[0], start[1], start[2] / 2.5)
    last = (end[0], end[1], end[2] / 2.5)
    run = [b - a for a, b in zip(first, last, strict=True)]
    length = sum(part * part for part in run)
    reach = max(radii)
    low = [floor(min(a, b) - reach) for a, b in zip(first, last, strict=True)]
    high = [floor(max(a, b) + reach) + 1 for a, b in zip(first, last, strict=True)]
    for x in range(low[0], high[0]):
        for y in range(low[1], high[1]):
            for z in range(floor(low[2] * 2.5), floor(high[2] * 2.5) + 1):
                away = (
                    x + 0.5 - first[0],
                    y + 0.5 - first[1],
                    (z + 0.5) / 2.5 - first[2],
                )
                share = sum(a * b for a, b in zip(away, run, strict=True)) / length
                share = max(0.0, min(1.0, share))
                gap = hypot(*(a - share * b for a, b in zip(away, run, strict=True)))
                if gap < radii[0] + (radii[1] - radii[0]) * share:
                    voxels.setdefault((x, y, z), color)


def grow(
    voxels: Voxels, start: Point, limb: tuple[float, float, float, float], depth: int
) -> None:
    """Add a crooked limb of three bending pieces, a side twig, then two forks."""
    azimuth, elevation, length, radius = limb
    bend = 26 if hashed(round(azimuth), depth, 41) < 0.5 else -26
    end = start
    for piece in range(3):
        heading = radians(azimuth + bend * piece / 2)
        curl = 30 if depth == 0 and piece == 2 else 0  # Twigs curl up like fingers
        rise = radians(max(16.0, elevation - 8 * piece) + curl)
        step = length / 3
        tip = (
            end[0] + step * cos(rise) * cos(heading),
            end[1] + step * cos(rise) * sin(heading),
            end[2] + 2.5 * step * sin(rise),
        )
        radii = (radius * (1 - 0.12 * piece), radius * (0.88 - 0.12 * piece))
        capsule(voxels, end, tip, radii, BARK)
        end = tip
        if piece == 1 and depth > 0:
            twig = (azimuth - bend * 1.5, elevation + 20, length * 0.45, 0.72)
            grow(voxels, end, twig, 0)
    if depth == 0:
        return
    for side in (-1, 1):
        child = (
            azimuth + bend + side * 34,
            max(20.0, elevation + 4),
            length * 0.6,
            max(0.74, radius * 0.7),
        )
        grow(voxels, end, child, depth - 1)


def dead_tree(voxels: Voxels) -> None:
    """Add a gnarled dead tree: roots, a trunk of twisted strands, crooked limbs."""
    for angle in (25, 100, 165, 245, 315):
        heading = radians(angle)
        tip = (TREE_X + 4.5 * cos(heading), TREE_Y + 4.0 * sin(heading), GROUND)
        capsule(voxels, (TREE_X, TREE_Y, GROUND + 5), tip, (1.4, 0.6), BARK)
    for strand in range(3):
        points: list[Point] = []
        for z in range(GROUND, FORK + 1, 2):
            rise = (z - GROUND) / (FORK - GROUND)
            twist = radians(120 * strand) + 0.16 * (z - GROUND)
            points.append(
                (
                    TREE_X - 1.2 * rise + 1.1 * cos(twist),
                    TREE_Y + 0.6 * rise + 1.1 * sin(twist),
                    z,
                )
            )
        for start, end in pairwise(points):
            capsule(voxels, start, end, (1.35, 1.35), BARK)
    fork = (TREE_X - 1.2, TREE_Y + 0.6, FORK)
    for limb in LIMBS:
        grow(voxels, fork, limb, 2)
    hollow(voxels)


def hollow(voxels: Voxels) -> None:
    """Darken a hollow in the trunk's front, with two glowing eyes peering out."""
    for z in range(10, 16):
        bark = [
            (*facing(x + 0.5 - TREE_X, y + 0.5 - TREE_Y), (x, y, z))
            for x in range(floor(TREE_X) - 4, floor(TREE_X) + 4)
            for y in range(floor(TREE_Y) - 4, floor(TREE_Y) + 4)
            if voxels.get((x, y, z)) == BARK
        ]
        front = max(ahead for ahead, _, _ in bark)
        dark = sorted(
            (aside, voxel)
            for ahead, aside, voxel in bark
            if ahead > front - 1.0 and abs(aside) < 1.6
        )
        for _, voxel in dark:
            voxels[voxel] = TRIM
        if z in {12, 13} and len(dark) > 1:
            voxels[dark[0][1]] = LAMP
            voxels[dark[-1][1]] = LAMP


def limb(voxels: Voxels, voxel: Voxel) -> bool:
    """Return whether a voxel belongs to the dead tree's crown."""
    x, y, z = voxel
    near = hypot(x - TREE_X, y - TREE_Y) < 13
    return near and z > FORK and voxels.get(voxel) == BARK


def column_top(voxels: Voxels, x: int, y: int, low: int, high: int) -> int | None:
    """Return the highest filled layer of a column between two layers, if any."""
    filled = [z for z in range(low, high) if (x, y, z) in voxels]
    return max(filled) if filled else None


def ghosts(voxels: Voxels, height: dict[Square, int]) -> None:
    """Add ghosts on clear rods: a wavy hem, raised arms, and a startled face."""
    for ghost_x, ghost_y, rod in GHOSTS:
        ghost_z = height[ghost_x, ghost_y] + rod
        for z in range(height[ghost_x, ghost_y], ghost_z):
            voxels[ghost_x, ghost_y, z] = ROD
        for level, radius in enumerate(GHOST):
            for x in range(ghost_x - 3, ghost_x + 4):
                for y in range(ghost_y - 3, ghost_y + 4):
                    gap = hypot(x - ghost_x, y - ghost_y)
                    wavy = level < 2 and gap > 1.5 and (x + y + level) % 2 == 0
                    if gap < radius and not wavy:
                        voxels[x, y, ghost_z + level] = SHEET
        for side in (-1, 1):  # Arms raised to frighten
            for reach, level in ((3, 7), (2, 8), (3, 8), (3, 9), (3, 10)):
                voxels[ghost_x + reach * side, ghost_y, ghost_z + level] = SHEET
        ghost_face(voxels, (ghost_x, ghost_y, ghost_z))


def ghost_face(voxels: Voxels, hem: Voxel) -> None:
    """Darken a ghost's eyes and its open mouth on the front of its sheet."""
    ghost_x, ghost_y, ghost_z = hem
    for offset_x, levels in ((-1, (9, 10, 11)), (1, (9, 10, 11)), (0, (4, 5, 6))):
        for level in levels:
            front = min(
                y
                for y in range(ghost_y - 3, ghost_y + 1)
                if (ghost_x + offset_x, y, ghost_z + level) in voxels
            )
            voxels[ghost_x + offset_x, front, ghost_z + level] = TRIM


def made_in(builder: ModelBuilder, part: str, color: int | str) -> bool:
    """Return whether the catalog lists the part in the color."""
    entry = builder.catalog.entry(part)
    return entry is not None and builder.catalog.resolve_color(color).id in entry.colors


def footprint(placement: Placement) -> tuple[list[Square], int]:
    """Return the squares a planned part covers, and its height in plates."""
    sizes = {part: size for size, part in FILL_PLATES.items()}
    tall = 1
    if placement.part not in sizes:
        sizes = {part: size for size, part in FILL_BRICKS.items()}
        tall = 3
    short, long = sizes[placement.part]
    along_x, along_y = (short, long) if placement.rotation == "R0" else (long, short)
    x, y, _ = placement.at
    return [(x + i, y + j) for i in range(along_x) for j in range(along_y)], tall


def stranded(placements: list[Placement]) -> list[Placement]:
    """Return the planned parts that no chain of studs joins to the ground."""
    bottoms: dict[Voxel, int] = {}
    tops: dict[Voxel, int] = {}
    shapes = [footprint(placement) for placement in placements]
    for index, (placement, (cells, tall)) in enumerate(
        zip(placements, shapes, strict=True)
    ):
        z = placement.at[2]
        for x, y in cells:
            bottoms[x, y, z] = index
            tops[x, y, z + tall - 1] = index
    grounded = {i for i, placement in enumerate(placements) if placement.at[2] == 0}
    queue = deque(grounded)
    while queue:
        index = queue.popleft()
        cells, tall = shapes[index]
        z = placements[index].at[2]
        for x, y in cells:
            for near in (tops.get((x, y, z - 1)), bottoms.get((x, y, z + tall))):
                if near is not None and near not in grounded:
                    grounded.add(near)
                    queue.append(near)
    return [
        placement for index, placement in enumerate(placements) if index not in grounded
    ]


def fill(builder: ModelBuilder, voxels: Voxels) -> Voxels:
    """Fill the voxels in one plan, dropping parts that no stud chain would ground."""
    voxels = {
        voxel: color
        for voxel, color in voxels.items()
        if 0 <= voxel[0] < SIZE and 0 <= voxel[1] < SIZE and voxel[2] >= 0
    }
    check = partial(made_in, builder)
    dropped = 0
    while True:
        plan = plan_fill(voxels, made_in=check)
        floating = stranded(plan)
        if not floating:
            break
        for placement in floating:
            cells, tall = footprint(placement)
            for x, y in cells:
                for z in range(placement.at[2], placement.at[2] + tall):
                    dropped += voxels.pop((x, y, z), None) is not None
    print(f"{len(voxels):,} voxels, {dropped} dropped as floating")
    scene = builder.component("scene")
    for placement in plan:
        scene.place(
            placement.part,
            at=placement.at,
            color=placement.color,
            rotation=placement.rotation,
        )
    builder.instance("scene", at=(0, 0, BASE), id="scene")
    return voxels


def components(builder: ModelBuilder) -> None:
    """Define the small features placed many times: lamps, pumpkins, crows and more."""
    skull = builder.component("skull")  # Faces south
    skull.place("11211", at=(0, 0.4, 0), color=SHEET)
    for x in (0, 1):
        skull.place("98138", at=(x, 0, 0.5), rotation="+x+z", color=TRIM)
    skull.place("85984", at=(0, 0.4, 3), color=SHEET)

    jack = builder.component("jack")  # A carved pumpkin, its eyes glowing south
    jack.place("4032", at=(0, 0.4, 0), color=PUMPKIN)
    jack.place("11211", at=(0, 0.4, 1), color=PUMPKIN)
    jack.place("3004", at=(0, 1.4, 1), rotation="R90", color=PUMPKIN)
    for x in (0, 1):
        jack.place("98138", at=(x, 0, 1.5), rotation="+x+z", color=LAMP)
    jack.place("87580", at=(0, 0.4, 4), color=PUMPKIN)
    jack.place("4073", at=(0.5, 0.9, 5), color=STEM)

    pumpkin = builder.component("pumpkin")
    pumpkin.place("4032", at=(0, 0, 0), color=PUMPKIN)
    pumpkin.place("3941", at=(0, 0, 1), color=PUMPKIN)
    pumpkin.place("87580", at=(0, 0, 4), color=PUMPKIN)
    pumpkin.place("4073", at=(0.5, 0.5, 5), color=STEM)

    squash = builder.component("squash")
    squash.place("4032", at=(0, 0, 0), color=RIB)
    squash.place("4032", at=(0, 0, 1), color=PUMPKIN)
    squash.place("4073", at=(1, 1, 2), color=STEM)

    candle = builder.component("candle")
    candle.place("3062", at=(0, 0, 0), color="White")
    candle.place("98138", at=(0, 0, 3), color=GLOW)

    lamp = builder.component("lamp")  # A post, a pumpkin on top, a lantern hanging
    for z in (0, 3, 6):
        lamp.place("3062", at=(0, 0, z), color=TRIM)
    lamp.place("3623", at=(0, 0, 9), rotation="R90", color=TRIM)
    lamp.place("3062", at=(0, 0, 10), color=PUMPKIN)
    lamp.place("4073", at=(0, 0, 13), color=STEM)
    lamp.place("4073", at=(2, 0, 8), color=TRIM)
    lamp.place("3062", at=(2, 0, 5), color=LAMP)
    lamp.place("4073", at=(2, 0, 4), color=TRIM)

    crow = builder.component("crow")  # Faces east
    crow.place("3023", at=(0, 0, 0), rotation="R90", color=TRIM)
    crow.place("54200", at=(0, 0, 1), rotation="R270", color=TRIM)
    crow.place("4073", at=(1, 0, 1), color=TRIM)
    crow.place("4073", at=(1, 0, 2), color=TRIM)

    toadstool = builder.component("toadstool")
    toadstool.place("3062", at=(0, 0, 0), color="White")
    toadstool.place("4032", at=(0, 0, 3), color="Lime")
    toadstool.place("98138", at=(1, 1, 4), color="White")
    toadstool.place("98138", at=(0, 1, 4), color="White")

    tombstones(builder)


def tombstones(builder: ModelBuilder) -> None:
    """Define four headstones in each stone color: a cross and three slabs."""
    for color in (PEBBLE, ROCK, LICHEN):
        name = color.lower().replace(" ", "-")
        cross = builder.component(f"cross-{name}")
        cross.place("3005", at=(1, 0, 0), color=color)
        cross.place("3005", at=(1, 0, 3), color=color)
        cross.place("3622", at=(0, 0, 6), rotation="R90", color=color)
        cross.place("3005", at=(1, 0, 9), color=color)
        peak = builder.component(f"peak-{name}")
        rounded = builder.component(f"rounded-{name}")
        slab = builder.component(f"slab-{name}")
        for stone in (peak, rounded, slab):
            stone.place("3004", at=(0, 0, 0), rotation="R90", color=color)
        for stone in (peak, rounded):
            stone.place("3004", at=(0, 0, 3), rotation="R90", color=color)
        peak.place("54200", at=(0, 0, 6), rotation="R270", color=color)
        peak.place("54200", at=(1, 0, 6), rotation="R90", color=color)
        rounded.place("11477", at=(0, 0, 6), rotation="R90", color=color)
        slab.place("3023", at=(0, 0, 3), rotation="R90", color=color)
        slab.place("85984", at=(0, 0, 4), color=color)


def path_tiles(scene: Scene) -> None:
    """Cover the path and the stairs with flagstones in two grays."""
    squares = {square for square in scene.height if on_path(*square)}
    scene.taken |= squares
    done: set[Square] = set()
    for x, y in sorted(squares):
        if (x, y) in done:
            continue
        z = scene.height[x, y] - 1
        color = PEBBLE if hashed(x, y, 31) < 0.6 else ROCK
        pair = (x + 1, y)
        if (
            pair in squares
            and pair not in done
            and scene.height[pair] == scene.height[x, y]
            and hashed(x, y, 32) < 0.6
        ):
            scene.put("3069", (x, y, z), color, "R90")
            done |= {(x, y), pair}
        else:
            scene.put("3070", (x, y, z), color)
            done.add((x, y))


def iron_fence(scene: Scene, cells: list[Square]) -> None:
    """Stand a wrought-iron fence: posts, round bars, a top rail and spear tips."""
    for index, (x, y) in enumerate(cells):
        if index % 2 == 1:
            continue  # A gap between bars
        post = index % 6 == 0
        for z in (GROUND, GROUND + 3):
            scene.put("3005" if post else "3062", (x, y, z), TRIM)
        scene.put("4073", (x, y, GROUND + 7), "Pearl Gold" if post else TRIM)
    scene.taken |= set(cells)
    runs: list[list[Square]] = [[]]
    for cell in cells:
        last = runs[-1][-1] if runs[-1] else None
        joined = (
            last is not None and abs(cell[0] - last[0]) + abs(cell[1] - last[1]) == 1
        )
        if runs[-1] and (not joined or len(runs[-1]) == 8):
            runs.append([])
        runs[-1].append(cell)
    plates = {1: "3024", 2: "3023", 3: "3623", 4: "3710", 6: "3666", 8: "3460"}
    for run in runs:
        start = 0
        while start < len(run):
            size = max(size for size in plates if size <= len(run) - start)
            x, y = min(run[start : start + size])
            along_x = run[0][1] == run[-1][1] and len(run) > 1
            rotation = "R90" if along_x else "R0"
            scene.put(plates[size], (x, y, GROUND + 6), TRIM, rotation)
            start += size


def graveyard(scene: Scene) -> None:
    """Fence the graveyard, raise its gate, and lay out its graves and its crypt."""
    west, south, east, north = GRAVEYARD
    gate = range(GATE_Y[0], GATE_Y[1] + 3)
    iron_fence(scene, [(x, south) for x in range(west, east + 1)])
    iron_fence(scene, [(west, y) for y in range(south + 1, north + 1)])
    iron_fence(scene, [(east, y) for y in range(south + 1, north + 1) if y not in gate])
    for y in GATE_Y:  # The pillars, each topped with a cap
        for course in range(4):
            scene.put("3002", (east - 1, y, GROUND + 3 * course), ROCK)
        scene.put("3021", (east - 1, y, GROUND + 12), PEBBLE)
        scene.taken |= {(east - 1 + i, y + j) for i in (0, 1) for j in range(3)}
    opening = GATE_Y[0] + 3
    scene.put("3659", (east, opening - 1, GROUND + 13), TRIM)  # The iron arch
    scene.copy("skull", (east, opening, GROUND + 16), "R90")
    scene.put("4073", (east, opening - 1, GROUND + 16), "Pearl Gold")
    for z in (GROUND, GROUND + 3):  # A closed leaf, and an open one swung out
        scene.put("3062", (east, opening, z), TRIM)
        for x in (east + 1, east + 2):
            scene.put("3062", (x, opening + 1, z), TRIM)
    scene.put("4073", (east, opening, GROUND + 6), TRIM)
    scene.put("3023", (east + 1, opening + 1, GROUND + 6), TRIM, "R90")
    scene.taken |= {(east, opening), (east, opening + 1), (east + 1, opening + 1)}
    scene.taken.add((east + 2, opening + 1))
    black_cat(scene, (east - 1, GATE_Y[1] + 1, GROUND + 13))
    scene.copy("jack", (east - 1, GATE_Y[0] - 0.4, GROUND + 13))
    headstones(scene)
    crypt_details(scene)


def headstones(scene: Scene) -> None:
    """Place the headstones, a grave mound before each, and flowers and candles."""
    for index, (x, y, kind, color) in enumerate(HEADSTONES):
        name = f"{kind}-{color.lower().replace(' ', '-')}"
        width = 3 if kind == "cross" else 2
        scene.copy(name, (x, y, GROUND))
        mound = x + (1 if kind == "cross" else 0)
        scene.put("3021", (mound, y - 3, GROUND), MUD)
        scene.taken |= {(x + i, y) for i in range(width)}
        scene.taken |= {(mound + i, y - j) for i in range(2) for j in range(1, 4)}
        if index % 2 == 0:
            scene.copy("candle", (mound + 1, y - 1, GROUND + 1))
        else:
            for bloom, row in ((ROOF, y - 3), ("Bright Light Orange", y - 1)):
                scene.put("4073", (mound, row, GROUND + 1), bloom)


def crypt_details(scene: Scene) -> None:
    """Place the crypt's two steps, and a candle at each end of the lower one."""
    door = CRYPT.door if CRYPT.door is not None else 0
    scene.put("3020", (door - 1, CRYPT.y - 2, GROUND), PEBBLE, "R90")
    scene.put("3710", (door - 1, CRYPT.y - 1, GROUND + 1), PEBBLE, "R90")
    for x in (door - 1, door + 2):
        scene.copy("candle", (x, CRYPT.y - 2, GROUND + 1))
    scene.taken |= {(door - 1 + i, CRYPT.y - j) for i in range(4) for j in (1, 2)}


def black_cat(scene: Scene, at: Point) -> None:
    """Seat a black cat with glowing eyes, its tail curled up behind it."""
    x, y, z = at
    scene.put("3003", (x, y, z), TRIM)
    scene.put("11211", (x, y, z + 3), TRIM)
    for offset_x in (0, 1):
        scene.put("98138", (x + offset_x, y - 0.4, z + 3.5), "Lime", "+x+z")
        scene.put("54200", (x + offset_x, y, z + 6), TRIM)
    scene.put("3005", (x, y + 1, z + 3), TRIM)
    scene.put("3062", (x + 1, y + 1, z + 3), TRIM)
    scene.put("4073", (x + 1, y + 1, z + 6), TRIM)
    scene.put("4073", (x + 1, y + 1, z + 7), TRIM)


def rail_fence(scene: Scene, cells: list[Square]) -> None:
    """Stand a crooked wooden fence: posts every three studs, rails that zigzag."""
    posts = cells[::3]
    for x, y in posts:
        for z in (GROUND, GROUND + 3):
            scene.put("3005", (x, y, z), WOOD)
    for index in range(len(posts) - 1):
        first, second = posts[index], posts[index + 1]
        x, y = min(first, second)
        rotation = "R90" if first[1] == second[1] else "R0"
        scene.put("3710", (x, y, GROUND + 6 + index % 2), WOOD, rotation)
    scene.taken |= set(cells)


def scarecrow(scene: Scene) -> None:
    """Stand a scarecrow: a pole, a magenta shirt, a jack-o'-lantern head, a hat."""
    x, y = SCARECROW
    z = GROUND
    for course in range(3):
        scene.put("3062", (x, y, z + 3 * course), BARK)
    scene.put("3004", (x, y, z + 9), ROOF, "R90")
    scene.put("3666", (x - 2, y, z + 12), ROOF, "R90")
    scene.put("54200", (x - 2, y, z + 13), STRAW, "R270")
    scene.put("54200", (x + 3, y, z + 13), STRAW, "R90")
    scene.put("3022", (x, y, z + 13), STRAW)
    scene.put("11211", (x, y, z + 14), PUMPKIN)
    scene.put("3004", (x, y + 1, z + 14), PUMPKIN, "R90")
    for offset_x in (0, 1):
        scene.put("98138", (x + offset_x, y - 0.4, z + 14.5), TRIM, "+x+z")
    scene.put("4032", (x, y, z + 17), PUMPKIN)
    scene.put("11212", (x, y, z + 18), STRAW)  # A crooked brim, pushed back
    scene.put("3941", (x, y, z + 19), STRAW)
    scene.put("14769", (x, y, z + 22), STRAW)
    scene.copy("crow", (x + 2, y, z + 19), "R90")
    scene.taken.add((x, y))


def pumpkin_patch(scene: Scene) -> None:
    """Fence the patch, then grow pumpkins, squashes, vines and leaves in its soil."""
    west, south, east, north = PATCH
    corner = [(west, y) for y in range(south, north + 1)]
    rail_fence(scene, corner + [(x, north) for x in range(west + 1, east)])
    scene.copy("crow", (west + 7, north, GROUND + 7))
    for shape in BIG_PUMPKINS:
        x, y, radius, _ = shape
        scene.taken |= {
            (floor(x + i), floor(y + j))
            for i in range(-floor(radius) - 1, floor(radius) + 2)
            for j in range(-floor(radius) - 1, floor(radius) + 2)
        }
    for x, y in ROUND_PUMPKINS:
        scene.copy("pumpkin", (x, y, GROUND))
        scene.taken |= {(x + i, y + j) for i in (0, 1) for j in (0, 1)}
    for x, y in SQUASHES:
        scene.copy("squash", (x, y, GROUND))
        scene.taken |= {(x + i, y + j) for i in (0, 1) for j in (0, 1)}
    scarecrow(scene)
    for x in range(west + 1, east + 1):
        for y in range(south, north):
            if (x, y) in scene.taken:
                continue
            vine = noise(x / 2.5, y / 1.5, 61)
            if vine > 0.62:
                scene.put("3024", (x, y, GROUND), GRASS)
            elif vine > 0.5 and hashed(x, y, 62) < 0.5:
                scene.put(
                    "98138",
                    (x, y, GROUND),
                    "Lime" if hashed(x, y, 63) < 0.4 else "Green",
                )
            else:
                continue
            scene.taken.add((x, y))


def cauldron_voxels(voxels: Voxels) -> None:
    """Add the cauldron's iron belly on three legs, and its brew below the rim."""
    center_x, center_y = CAULDRON
    for offset_x, offset_y in LEGS:
        for z in range(GROUND, GROUND + 4):
            voxels[center_x + offset_x, center_y + offset_y, z] = TRIM
    for level, radius in enumerate(BOWL):
        z = GROUND + 3 + level
        for x in range(center_x - 4, center_x + 4):
            for y in range(center_y - 4, center_y + 4):
                gap = hypot(x + 0.5 - center_x, y + 0.5 - center_y)
                if gap >= radius:
                    continue
                if gap >= 1.8 or level < 7:
                    voxels[x, y, z] = TRIM
                elif level == 7:
                    voxels[x, y, z] = BREW


def cauldron(scene: Scene) -> None:
    """Light a fire under the cauldron, bubble its brew, and lay out the clearing."""
    center_x, center_y = CAULDRON
    z = GROUND
    for offset_x in (-1, 0):  # Two logs, and flames licking the cauldron's belly
        scene.put("3023", (center_x + offset_x, center_y - 1, z), WOOD)
    scene.put("54200", (center_x - 1, center_y - 1, z + 1), GLOW)
    scene.put("4073", (center_x - 1, center_y, z + 1), LAMP)
    scene.put("54200", (center_x, center_y - 1, z + 1), "Trans-Red", "R180")
    scene.put("4073", (center_x, center_y, z + 1), GLOW)
    scene.put("98138", (center_x - 2, center_y, z), LAMP)
    scene.put("98138", (center_x + 1, center_y - 1, z), GLOW)
    brew = z + 3 + 8
    scene.put("4073", (center_x - 1, center_y - 1, brew), "Lime")
    scene.put("98138", (center_x, center_y, brew), "Lime")
    scene.put("3062", (center_x, center_y - 1, brew), BREW)
    scene.put("4073", (center_x, center_y - 1, brew + 3), "Lime")
    scene.put("98138", (center_x, center_y - 1, brew + 4), BREW)
    scene.put("3062", (center_x - 1, center_y, brew), BARK)  # The stirring stick
    scene.put("3062", (center_x - 1, center_y, brew + 3), BARK)
    scene.taken |= {
        (center_x + offset_x, center_y + offset_y)
        for offset_x in range(-3, 3)
        for offset_y in range(-3, 3)
    }
    broom = (center_x + 3, center_y)
    scene.put("3941", (*broom, z), STRAW)
    scene.put("87580", (*broom, z + 3), STRAW)
    for course in range(3):
        scene.put("3062", (broom[0] + 0.5, broom[1] + 0.5, z + 4 + 3 * course), BARK)
    scene.taken |= {(broom[0] + i, broom[1] + j) for i in (0, 1) for j in (0, 1)}
    for x, y in TOADSTOOLS:
        scene.copy("toadstool", (x, y, GROUND))
        scene.taken |= {(x + i, y + j) for i in (0, 1) for j in (0, 1)}


def lamps(scene: Scene) -> None:
    """Stand lamp posts beside the path, each with a lantern and a pumpkin."""
    for x, y, rotation in LAMPS:
        west = x if rotation == "R0" else x - 2
        scene.copy("lamp", (west, y, scene.height[x, y]), rotation)
        scene.taken |= {(west, y), (west + 1, y), (west + 2, y)}


def manor_details(scene: Scene, arches: list[tuple[Voxel, str]]) -> None:
    """Place the arches over windows and doors, the roofs, and a lantern by the door."""
    for (x, y, z), rotation in arches:
        color = PEBBLE if z < TOP else TRIM
        scene.put("3659", (x, y, z), color, rotation)
    for roof in ROOFS:
        place_roof(scene, roof)
    door = HALL[0].door if HALL[0].door is not None else 0
    lantern = (door + 3, HALL[1].y)
    scene.put("4073", (*lantern, TOP + 11), TRIM)
    scene.put("3062", (*lantern, TOP + 8), LAMP)
    scene.put("4073", (*lantern, TOP + 7), TRIM)
    for x, y in ((10, 28), (15, 28)):  # Carved pumpkins at the head of the stairs
        scene.copy("jack", (x, y - 0.4, scene.height[x, y]))
        scene.taken |= {(x + i, y + j) for i in (0, 1) for j in (0, 1)}


def tree_lanterns(scene: Scene, voxels: Voxels) -> None:
    """Hang three lanterns on chains of round plates under the tree's limbs."""
    candidates = [
        (x, y, z)
        for x, y, z in voxels
        if limb(voxels, (x, y, z))
        and z > FORK + 4
        and hypot(x - TREE_X, y - TREE_Y) > 4
        and not any((x, y, low) in voxels for low in range(z - 14, z))
    ]
    chosen: list[Voxel] = []
    for candidate in sorted(candidates, key=lambda voxel: hashed(*voxel, 91)):
        if all(hypot(candidate[0] - x, candidate[1] - y) >= 5 for x, y, _ in chosen):
            chosen.append(candidate)
    for x, y, z in chosen[:3]:
        scene.put("4073", (x, y, z - 1), TRIM)
        scene.put("4073", (x, y, z - 2), TRIM)
        scene.put("3062", (x, y, z - 5), LAMP)
        scene.put("4073", (x, y, z - 6), TRIM)


def crows(scene: Scene, voxels: Voxels) -> None:
    """Perch crows on the tree's limbs, wherever two studs lie bare side by side."""
    perches = [
        (x, y, z)
        for x, y, z in voxels
        if limb(voxels, (x, y, z))
        and limb(voxels, (x + 1, y, z))
        and not any(
            (x + offset_x, y, z + up) in voxels
            for offset_x in (0, 1)
            for up in range(1, 6)
        )
    ]
    chosen: list[Voxel] = []
    for x, y, z in sorted(perches, key=lambda voxel: hashed(*voxel, 93)):
        if all(hypot(x - other_x, y - other_y) > 6 for other_x, other_y, _ in chosen):
            chosen.append((x, y, z))
    for x, y, z in chosen[:3]:
        scene.copy("crow", (x, y, z + 1))


def banks(scene: Scene, voxels: Voxels) -> None:
    """Soften the foot of the hill's brick-high steps with grassy Slope 45 banks."""
    rotations = {(0, -1): "R0", (0, 1): "R180", (1, 0): "R90", (-1, 0): "R270"}
    for (x, y), top in sorted(scene.height.items()):
        for (offset_x, offset_y), rotation in rotations.items():
            low = top - 3
            pair = ((x + offset_x, y + offset_y), (x + 2 * offset_x, y + 2 * offset_y))
            if any(
                scene.height.get(square) != low
                or square in scene.taken
                or column_top(voxels, *square, low, low + 40) is not None
                for square in pair
            ):
                continue
            if hashed(x, y, offset_x + 2 * offset_y, 81) < 0.1:
                continue
            corner = (min(pair)[0], min(pair)[1], low)
            color = surface_color(x, y)
            scene.put("3040", corner, GRASS if color == MUD else color, rotation)
            scene.taken |= set(pair)


def leaves(scene: Scene, voxels: Voxels) -> None:
    """Scatter autumn leaves on the bare ground, thickest under the tree."""
    colors = ("Orange", RIB, "Dark Red", "Bright Light Orange", WOOD, "Yellow")
    for (x, y), top in scene.height.items():
        if (x, y) in scene.taken or column_top(voxels, x, y, top, top + 40) is not None:
            continue
        near = hypot(x - TREE_X, y - TREE_Y)
        chance = 0.5 * max(0.0, 1 - near / 12) + 0.05
        if hashed(x, y, 71) < chance:
            color = colors[floor(hashed(x, y, 72) * len(colors))]
            scene.put("98138", (x, y, top), color)


def build() -> ModelBuilder:
    """Build the haunted hill on its baseplate."""
    builder = ModelBuilder("pumpkin-manor")
    builder.place("4186", at=(0, 0, 0), color="Green", id="baseplate")
    height = heights()
    voxels = terrain(height)
    arches = manor(voxels)
    tower(voxels)
    center_x, center_y = shaft_center(SHAFT_TOP)
    gourd(
        voxels,
        Gourd(center_x, center_y, SHAFT_TOP, PUMPKIN_RADIUS, PUMPKIN_HALF, carved=True),
    )
    for x, y, radius, carved in BIG_PUMPKINS:
        gourd(voxels, Gourd(x, y, GROUND, radius, round(radius * 1.9), carved))
        voxels[floor(x), floor(y), GROUND + round(radius * 3.8)] = STEM
    hat(voxels)
    moon(voxels, height)
    dead_tree(voxels)
    cauldron_voxels(voxels)
    ghosts(voxels, height)
    voxels = fill(builder, voxels)
    components(builder)
    scene = Scene(builder, height)
    path_tiles(scene)
    manor_details(scene, arches)
    graveyard(scene)
    pumpkin_patch(scene)
    cauldron(scene)
    lamps(scene)
    tree_lanterns(scene, voxels)
    crows(scene, voxels)
    for x, y in ((14, 2), (30, 18)):  # Skulls lying in the grass
        scene.copy("skull", (x, y - 0.4, GROUND))
        scene.taken |= {(x, y), (x + 1, y)}
    banks(scene, voxels)
    leaves(scene, voxels)
    return builder
