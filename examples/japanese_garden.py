# Copyright 2026 Maxence Faldor
"""A Japanese garden in spring: a pagoda, a torii, cherry trees and a koi pond.

- The garden stands on a Baseplate 48 x 48. Its lawn, stone rims, plinth, rocks,
  hedges, shrubs and cherry trees are voxels that ``builder.fill`` covers with bricks
  and plates. The lawn is one brick deep, and the pond lies a plate below it.
- Before the fill, ``plan_fill`` plans the parts, and the script drops the voxels of
  any part that no chain of studs would join to the ground.
- Each cherry tree forks from a leaning trunk into limbs and twigs, and every twig ends
  in a puff of blossom: white where the sun falls, magenta in the shade.
- The five-story pagoda tapers from walls 10 studs square to 6. Inverted slopes flare
  the eaves out from the walls and Slope 33 parts fall from them. At each corner, a
  plate 2 x 2 and a curved slope turn the eaves up over a gold bell.
- Round plates in Pearl Gold stack into the finial, and a jumper centers its spike.
- The torii stands on round bricks 2 x 2. Its lintel's ends step up a plate and finish
  in curved slopes; a tile on side studs makes its plaque.
- Two Arch 1 x 8 x 2 carry the bridge over the pond, and curved slopes make its ramps.
- Koi, lily pads and fallen petals are round tiles 1 x 1 among the water tiles.
- Tiles rake the gravel bed in white and gray stripes that ring each mossy rock.

Run: ``uv run bricky build examples/japanese_garden.py``
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from itertools import pairwise
from math import ceil, cos, floor, hypot, pi, sin

from bricky import ModelBuilder
from bricky.fill import BRICKS as FILL_BRICKS
from bricky.fill import PLATES as FILL_PLATES
from bricky.fill import Placement, plan_fill

type Cell = tuple[int, int]
type Voxel = tuple[int, int, int]
type Voxels = dict[Voxel, str]
type Size = tuple[int, int]

BASE = 0.5  # The top of the baseplate, in plates
SIZE = 48  # The baseplate's side, in studs
GROUND = 3  # The top of the lawn, in plates above the baseplate

LAWN, MOSS, STONE, DARK_STONE = (
    "Green",
    "Sand Green",
    "Light Bluish Gray",
    "Dark Bluish Gray",
)
SHALLOW, DEEP = "Medium Azure", "Dark Turquoise"
VERMILION, LACQUER, ROOF, EDGE, GOLD = (
    "Red",
    "Dark Red",
    "Dark Bluish Gray",
    "Black",
    "Pearl Gold",
)
BARK, SHADE = "Reddish Brown", "Dark Green"

TILES = {
    (1, 1): "3070",
    (1, 2): "3069",
    (1, 3): "63864",
    (1, 4): "2431",
    (1, 6): "6636",
    (1, 8): "4162",
    (2, 2): "3068",
    (2, 3): "26603",
    (2, 4): "87079",
    (2, 6): "69729",
}  # Tiles by footprint: along x, then along y, unrotated
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
    (2, 10): "3832",
    (4, 4): "3031",
    (4, 6): "3032",
    (4, 8): "3035",
    (6, 6): "3958",
    (6, 8): "3036",
    (8, 8): "41539",
    (16, 16): "91405",
}  # Plates by footprint
BRICKS = {
    (1, 1): "3005",
    (1, 2): "3004",
    (1, 3): "3622",
    (1, 4): "3010",
    (2, 2): "3003",
    (2, 3): "3002",
    (2, 4): "3001",
    (2, 6): "2456",
}  # Bricks by footprint
SLOPES_33 = {4: "3297", 2: "3298", 1: "4286"}  # Slope 33 3 x N by width

# The pagoda: its center, the half-width of each story's walls, and their heights.
PAGODA_X, PAGODA_Y = 12, 36
HALVES = (5, 4, 4, 3, 3)
WALL_HEIGHTS = (9, 6, 6, 6, 6)
EAVE = 3  # Studs the roof reaches beyond the walls
PLINTH_TOP = GROUND + 3

# The torii: its posts' west corners, along the row it stands on.
TORII_Y = 21
TORII_POSTS = (7, 15)

# The bridge spans the pond's waist: rows 15 to 18, arch legs at x 24 and x 31.
BRIDGE_ROWS = range(15, 19)
ARCH_WEST, ARCH_EAST = 24, 31
UNDER_ARCHES = {
    (x, y)
    for x in (ARCH_WEST, ARCH_WEST + 1, ARCH_EAST - 1, ARCH_EAST)
    for y in (BRIDGE_ROWS[0], BRIDGE_ROWS[-1])
}  # The arches' legs stand on the baseplate and flare at their feet.
POND_LOBES = ((27.5, 9.0, 9.5, 6.0), (28.5, 23.0, 6.5, 5.0))  # Centers, radii

GRAVEL = (range(24, 41), range(31, 44))  # The raked gravel bed's squares

# Stepping stones follow this line, from the pagoda's steps to the east edge.
PATH = ((12.0, 24.0), (12.0, 17.0), (15.0, 16.5), (19.0, 16.5))
PATH_EAST = ((36.5, 16.5), (41.0, 17.5), (46.5, 19.0))

LANTERNS = ((18, 19), (39, 19), (21, 30))  # The south-west corner of each lantern
BENCH, PARASOL, BASIN = (9, 2), (13, 5), (42, 5)
IRISES = ((36, 21), (36, 22), (37, 21), (36, 24), (19, 4), (20, 4), (19, 5))

# Koi as two round tiles each: head cell, tail cell, head color, tail color.
KOI = (
    ((25, 9), (26, 8), "White", "Red"),
    ((30, 11), (31, 11), "Orange", "Orange"),
    ((22, 10), (22, 11), "Red", "White"),
    ((29, 6), (28, 6), "White", "Orange"),
    ((33, 8), (33, 9), "Orange", "Orange"),
    ((27, 23), (26, 24), "Orange", "White"),
    ((31, 22), (31, 21), "White", "Red"),
    ((29, 25), (30, 25), "Red", "Orange"),
)
LILIES = ((24, 6), (34, 11), (32, 24), (25, 21), (27, 26), (20, 9))


@dataclass(frozen=True, slots=True)
class Tree:
    """A cherry tree: its trunk's center, height and lean, its reach and its limbs."""

    x: int
    y: int
    height: int
    lean: Cell
    reach: float
    limbs: int
    seed: int


TREES = (
    Tree(7, 8, 16, (1, 1), 8.5, 4, 11),
    Tree(43, 38, 16, (-1, 0), 8.5, 4, 23),
    Tree(46, 13, 14, (-1, 0), 6.0, 3, 37),
)


@dataclass(frozen=True, slots=True)
class Mound:
    """A rounded mass of voxels: a rock or a clipped shrub."""

    x: float
    y: float
    radius_x: float
    radius_y: float
    height: int
    kind: str
    seed: int


MOUNDS = (
    Mound(29.0, 37.0, 2.6, 2.0, 7, "rock", 1),
    Mound(35.5, 40.0, 1.8, 1.5, 5, "rock", 2),
    Mound(36.5, 34.0, 1.4, 1.2, 4, "rock", 3),
    Mound(17.0, 9.5, 1.8, 1.6, 5, "rock", 4),
    Mound(38.5, 26.0, 1.7, 1.5, 4, "rock", 5),
    Mound(37.0, 12.5, 1.6, 1.4, 4, "rock", 6),
    Mound(21.0, 25.0, 1.8, 1.5, 5, "rock", 7),
    Mound(3.5, 24.0, 2.0, 2.4, 6, "azalea", 8),
    Mound(22.0, 40.0, 2.0, 2.0, 6, "azalea", 9),
    Mound(38.5, 2.5, 2.4, 2.0, 6, "shrub", 10),
    Mound(17.0, 3.0, 2.2, 1.8, 5, "azalea", 11),
    Mound(23.5, 1.5, 1.6, 1.3, 4, "azalea", 12),
    Mound(33.0, 1.5, 1.5, 1.3, 4, "azalea", 13),
)


def hashed(*values: int) -> float:
    """Return a repeatable number in [0, 1) for a tuple of integers."""
    state = 2166136261
    for value in values:
        state = ((state ^ (value & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
        state ^= state >> 15
        state = (state * 2246822519) & 0xFFFFFFFF
        state ^= state >> 13
    return state / 2**32


def noise(x: float, y: float, z: float, seed: int) -> float:
    """Return smooth value noise in [0, 1) that varies over about one unit."""
    corner_x, corner_y, corner_z = floor(x), floor(y), floor(z)
    weights = [
        (t * t * (3 - 2 * t), 1 - t * t * (3 - 2 * t))
        for t in (x - corner_x, y - corner_y, z - corner_z)
    ]
    total = 0.0
    for i in (0, 1):
        for j in (0, 1):
            for k in (0, 1):
                weight = weights[0][1 - i] * weights[1][1 - j] * weights[2][1 - k]
                total += weight * hashed(corner_x + i, corner_y + j, corner_z + k, seed)
    return total


def made_in(builder: ModelBuilder, part: str, color: int | str) -> bool:
    """Return whether the catalog lists the part in the color."""
    entry = builder.catalog.entry(part)
    return entry is not None and builder.catalog.resolve_color(color).id in entry.colors


def footprint(placement: Placement) -> tuple[list[Cell], int]:
    """Return the stud squares a filled part covers, and its height in plates."""
    sizes = {part: size for size, part in FILL_PLATES.items()}
    height = 1
    if placement.part not in sizes:
        sizes = {part: size for size, part in FILL_BRICKS.items()}
        height = 3
    short, long = sizes[placement.part]
    along_x, along_y = (short, long) if placement.rotation == "R0" else (long, short)
    x, y, _ = placement.at
    cells = [(x + i, y + j) for i in range(along_x) for j in range(along_y)]
    return cells, height


def stranded(placements: list[Placement]) -> list[Placement]:
    """Return the planned parts that no chain of studs joins to the ground."""
    bottoms: dict[Voxel, int] = {}
    tops: dict[Voxel, int] = {}
    shapes = [footprint(placement) for placement in placements]
    for index, (placement, (cells, height)) in enumerate(
        zip(placements, shapes, strict=True)
    ):
        z = placement.at[2]
        for x, y in cells:
            bottoms[x, y, z] = index
            tops[x, y, z + height - 1] = index
    grounded = {
        index for index, placement in enumerate(placements) if placement.at[2] == 0
    }
    queue = deque(grounded)
    while queue:
        index = queue.popleft()
        cells, height = shapes[index]
        z = placements[index].at[2]
        for x, y in cells:
            for near in (tops.get((x, y, z - 1)), bottoms.get((x, y, z + height))):
                if near is not None and near not in grounded:
                    grounded.add(near)
                    queue.append(near)
    return [
        placement for index, placement in enumerate(placements) if index not in grounded
    ]


def prune(builder: ModelBuilder, voxels: Voxels) -> Voxels:
    """Drop the voxels of parts the fill would leave floating, until none remain."""
    voxels = dict(voxels)
    while True:
        plan = plan_fill(
            voxels, made_in=lambda part, color: made_in(builder, part, color)
        )
        floating = stranded(plan)
        if not floating:
            return voxels
        for placement in floating:
            cells, height = footprint(placement)
            for x, y in cells:
                for z in range(placement.at[2], placement.at[2] + height):
                    voxels.pop((x, y, z), None)


def lay(
    builder: ModelBuilder,
    cells: Mapping[Cell, str],
    z: float,
    sizes: Mapping[Size, str],
) -> None:
    """Cover cells with the largest parts that fit, one layer at height z."""
    free = dict(cells)
    by_area = sorted(sizes.items(), key=lambda item: -item[0][0] * item[0][1])
    for x, y in sorted(cells, key=lambda cell: (cell[1], cell[0])):
        if (x, y) not in free:
            continue
        color = free[x, y]
        for (width, depth), part in by_area:
            fitted = next(
                (
                    (along_x, along_y, rotation)
                    for along_x, along_y, rotation in (
                        (width, depth, "R0"),
                        (depth, width, "R90"),
                    )
                    if all(
                        free.get((x + i, y + j)) == color
                        for i in range(along_x)
                        for j in range(along_y)
                    )
                ),
                None,
            )
            if fitted is None or not made_in(builder, part, color):
                continue
            along_x, along_y, rotation = fitted
            builder.place(part, at=(x, y, BASE + z), rotation=rotation, color=color)
            for i in range(along_x):
                for j in range(along_y):
                    del free[x + i, y + j]
            break


def square(center_x: int, center_y: int, half: int) -> list[Cell]:
    """Return the cells of a square of side 2 * half around a grid point."""
    return [
        (x, y)
        for x in range(center_x - half, center_x + half)
        for y in range(center_y - half, center_y + half)
    ]


def settle(voxels: Voxels, reach: int = 2) -> Voxels:
    """Keep the voxels that rest on the layer below or reach back to it.

    A voxel stays when its stud square is filled one layer down, or when it lies
    within ``reach`` studs, through its own layer, of such a voxel. An overhanging
    voxel takes the color of the voxel it reaches back through, so one plate can
    cover both.
    """
    layers: defaultdict[int, dict[Cell, str]] = defaultdict(dict)
    for (x, y, z), color in voxels.items():
        layers[z][x, y] = color
    kept: Voxels = {}
    below: set[Cell] = set()
    for z in range(max(layers) + 1):
        layer = layers.get(z, {})
        held = {cell: color for cell, color in layer.items() if z == 0 or cell in below}
        queue = deque((cell, 0) for cell in held)
        while queue:
            (x, y), distance = queue.popleft()
            if distance == reach:
                continue
            for near in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if near in layer and near not in held:
                    held[near] = held[x, y]
                    queue.append((near, distance + 1))
        kept.update(((x, y, z), color) for (x, y), color in held.items())
        below = set(held)
    return kept


# The ground.


def in_pond(x: int, y: int) -> bool:
    """Return whether the stud square (x, y) lies in the pond."""
    if y in BRIDGE_ROWS:
        return ARCH_WEST <= x <= ARCH_EAST
    wobble = 0.3 * (noise(x / 3, y / 3, 0.5, 5) - 0.5)
    return any(
        ((x + 0.5 - center_x) / radius_x) ** 2 + ((y + 0.5 - center_y) / radius_y) ** 2
        <= 1 + wobble
        for center_x, center_y, radius_x, radius_y in POND_LOBES
    )


def pond_depths(pond: set[Cell]) -> dict[Cell, int]:
    """Return each pond square's distance in studs from the nearest bank."""
    depths = {
        cell: 1 for cell in pond if any(near not in pond for near in around(cell))
    }
    queue = deque(depths)
    while queue:
        x, y = queue.popleft()
        for near in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if near in pond and near not in depths:
                depths[near] = depths[x, y] + 1
                queue.append(near)
    return depths


def around(cell: Cell) -> list[Cell]:
    """Return the eight squares around a stud square."""
    x, y = cell
    return [(x + i, y + j) for i in (-1, 0, 1) for j in (-1, 0, 1) if i or j]


def in_gravel(x: int, y: int) -> bool:
    """Return whether the stud square (x, y) lies in the gravel bed."""
    return x in GRAVEL[0] and y in GRAVEL[1]


def ground(pond: set[Cell]) -> Voxels:
    """Return the lawn, the pond's stone rim and floor, and the gravel bed's base."""
    voxels: Voxels = {}
    for x in range(SIZE):
        for y in range(SIZE):
            if (x, y) in pond:
                if (x, y) not in UNDER_ARCHES:
                    voxels[x, y, 0] = DEEP
                continue
            rim = any(near in pond for near in around((x, y)))
            edge = any(in_gravel(*near) for near in around((x, y)))
            if in_gravel(x, y):
                voxels.update(((x, y, z), STONE) for z in range(2))
            elif rim or edge:
                color = DARK_STONE if hashed(x, y, 1) < 0.5 or edge else STONE
                voxels.update(((x, y, z), color) for z in range(GROUND))
            else:
                voxels.update(((x, y, z), LAWN) for z in range(GROUND))
                if noise(x / 3, y / 3, 0.5, 21) > 0.63:
                    voxels[x, y, GROUND - 1] = SHADE  # A patch of moss
    return voxels


def plinth() -> Voxels:
    """Return the pagoda's stone plinth, edged in darker stone, and its two steps."""
    voxels: Voxels = {}
    half = HALVES[0] + EAVE  # The plinth spans the widest eaves.
    for x, y in square(PAGODA_X, PAGODA_Y, half):
        edge = max(abs(x + 0.5 - PAGODA_X), abs(y + 0.5 - PAGODA_Y)) > half - 1
        for z in range(GROUND, PLINTH_TOP):
            voxels[x, y, z] = DARK_STONE if edge and z == PLINTH_TOP - 1 else STONE
    south = PAGODA_Y - half
    for x in range(PAGODA_X - 2, PAGODA_X + 2):
        voxels.update(((x, south - 1, z), STONE) for z in range(GROUND, GROUND + 2))
        voxels[x, south - 2, GROUND] = STONE
    return voxels


def hedges() -> Voxels:
    """Return clipped hedges along three edges, darker in the shade at their feet."""
    cells = [(x, y) for x in range(SIZE) for y in range(45, SIZE)]
    cells += [(x, y) for x in range(2) for y in range(18, 45)]
    cells += [(x, y) for x in range(SIZE - 2, SIZE) for y in range(23, 45)]
    return {
        (x, y, z): SHADE if z < GROUND + 3 else LAWN
        for x, y in cells
        for z in range(GROUND, GROUND + 6)
    }


def mound(shape: Mound) -> Voxels:
    """Return a rock with moss on top, or a clipped shrub, as a rounded dome."""
    voxels: Voxels = {}
    bottom = 2 if in_gravel(floor(shape.x), floor(shape.y)) else GROUND
    for x in range(floor(shape.x - shape.radius_x), ceil(shape.x + shape.radius_x)):
        for y in range(floor(shape.y - shape.radius_y), ceil(shape.y + shape.radius_y)):
            spread = hypot(
                (x + 0.5 - shape.x) / shape.radius_x,
                (y + 0.5 - shape.y) / shape.radius_y,
            )
            lumpy = 1 + 0.4 * (noise(x / 2, y / 2, 0.5, shape.seed) - 0.5)
            if spread > lumpy:
                continue
            top = bottom + round(shape.height * (1 - (spread / lumpy) ** 2) ** 0.5)
            for z in range(bottom, max(top, bottom + 1)):
                voxels[x, y, z] = mound_color(shape, x, y, z, top=z == top - 1)
    return voxels


def mound_color(shape: Mound, x: int, y: int, z: int, *, top: bool) -> str:
    """Return the color of one voxel of a rock or a shrub."""
    value = hashed(x, y, z, shape.seed)
    if shape.kind == "rock":
        if top and value < 0.7:
            return MOSS
        return STONE if value > 0.85 else DARK_STONE
    if shape.kind == "azalea" and top and value < 0.6:
        return "Magenta"
    return SHADE if value < 0.3 else LAWN


# The cherry trees.


def walk(start: Cell, end: Cell, z: int) -> Iterator[Voxel]:
    """Yield the squares from start to end, one step at a time along x, then y."""
    x, y = start
    yield x, y, z
    while (x, y) != end:
        if x != end[0]:
            x += 1 if end[0] > x else -1
        else:
            y += 1 if end[1] > y else -1
        yield x, y, z


def branch(start: tuple[float, float, int], tip: tuple[float, float, int]) -> Voxels:
    """Return a branch as a stair of plates, each layer reaching back to the last."""
    voxels: Voxels = {}
    start_x, start_y, bottom = start
    tip_x, tip_y, top = tip
    previous = (floor(start_x), floor(start_y))
    for z in range(bottom, top + 1):
        fraction = (z - bottom) / max(1, top - bottom)
        cell = (
            floor(start_x + (tip_x - start_x) * fraction),
            floor(start_y + (tip_y - start_y) * fraction),
        )
        voxels.update((voxel, BARK) for voxel in walk(previous, cell, z))
        previous = cell
    return voxels


def puff(center: tuple[float, float, float], radius: float, seed: int) -> set[Voxel]:
    """Return a lumpy, slightly flattened ball of blossom around a center."""
    center_x, center_y, center_z = center
    depth = radius * 2.0  # In plates: a ball squashed to 80 percent of its width
    voxels: set[Voxel] = set()
    for x in range(floor(center_x - radius), ceil(center_x + radius)):
        for y in range(floor(center_y - radius), ceil(center_y + radius)):
            for z in range(floor(center_z - depth), ceil(center_z + depth)):
                distance = (
                    ((x + 0.5 - center_x) / radius) ** 2
                    + ((y + 0.5 - center_y) / radius) ** 2
                    + ((z + 0.5 - center_z) / depth) ** 2
                )
                if distance <= 1 - 0.6 * (noise(x / 2, y / 2, z / 4, seed) - 0.5):
                    voxels.add((x, y, z))
    return voxels


def blossom(canopy: set[Voxel], seed: int) -> Voxels:
    """Color a canopy: white in the sun on top, magenta in the shade beneath."""
    colors: Voxels = {}
    for x, y, z in canopy:
        value = noise(x / 2, y / 2, z / 3, seed)
        if (x, y, z + 1) not in canopy:
            color = "White" if value < 0.42 else "Dark Pink"
        elif (x, y, z - 1) not in canopy:
            color = "Magenta" if value < 0.6 else "Dark Pink"
        else:
            color = (
                "White" if value < 0.3 else "Magenta" if value > 0.75 else "Dark Pink"
            )
        colors[x, y, z] = color
    return colors


def inside(value: float, margin: float) -> float:
    """Clamp a coordinate so that a puff of this radius stays on the baseplate."""
    return min(max(value, margin), SIZE - margin)


def trunk(shape: Tree) -> Voxels:
    """Return a tree's trunk: 2 x 2, leaning as it rises, flared into roots."""
    voxels: Voxels = {}
    for z in range(GROUND, GROUND + shape.height):
        shift_x = round(shape.lean[0] * (z - GROUND) / shape.height)
        shift_y = round(shape.lean[1] * (z - GROUND) / shape.height)
        half = 2 if z == GROUND else 1
        for x, y in square(shape.x + shift_x, shape.y + shift_y, half):
            if half == 1 or hashed(x, y, shape.seed) < 0.6:
                voxels[x, y, z] = BARK
    return voxels


def clear(x: int, y: int, z: int) -> bool:
    """Return whether blossom at (x, y, z) keeps clear of the torii and the pagoda.

    Blossom also keeps clear of the parasol beside the bench.
    """
    torii = 1 <= x <= 22 and 19 <= y <= 24 and z >= GROUND + 18
    pagoda = 2 <= x <= 21 and y >= 26
    parasol = 9 <= x <= 17 and 1 <= y <= 9 and z <= GROUND + 18
    return not (torii or pagoda or parasol)


def tree(shape: Tree) -> Voxels:
    """Return a cherry tree: a trunk, limbs that fork into twigs, and blossom."""
    voxels = trunk(shape)
    top = GROUND + shape.height
    crown = (shape.x + shape.lean[0], shape.y + shape.lean[1], top - 3)
    canopy: set[Voxel] = set()
    for limb in range(shape.limbs):
        angle = 2 * pi * (limb + 0.4 * hashed(limb, shape.seed)) / shape.limbs
        elbow = (
            crown[0] + 0.5 * shape.reach * cos(angle),
            crown[1] + 0.5 * shape.reach * sin(angle),
            top + 3,
        )
        voxels.update(branch(crown, elbow))
        twigs = 3 - limb % 2
        for twig in range(twigs):
            turn = (twig - (twigs - 1) / 2) * 0.8 + 0.3 * (
                hashed(limb, twig, shape.seed) - 0.5
            )
            length = shape.reach * (0.4 + 0.25 * hashed(limb, twig, shape.seed, 1))
            radius = 2.8 + 0.9 * hashed(limb, twig, shape.seed, 2)
            tip = (
                inside(elbow[0] + length * cos(angle + turn), radius),
                inside(elbow[1] + length * sin(angle + turn), radius),
                elbow[2] + 2 + round(6 * hashed(limb, twig, shape.seed, 3)),
            )
            voxels.update(branch(elbow, tip))
            seed = shape.seed + 10 * limb + twig
            canopy |= puff((tip[0], tip[1], tip[2] + 2), radius, seed)
    canopy |= puff((crown[0], crown[1], top + 11), 3.8, shape.seed + 99)
    voxels.update(blossom({voxel for voxel in canopy if clear(*voxel)}, shape.seed))
    return voxels


# The pagoda.


def pagoda(builder: ModelBuilder) -> None:
    """Build the pagoda story by story: walls, brackets, eaves, roof and railing."""
    z = PLINTH_TOP
    for course in range(4):  # The central pillar rises to the first eaves.
        builder.place(
            "3003", at=(PAGODA_X - 1, PAGODA_Y - 1, BASE + z + 3 * course), color=BARK
        )
    for story, (half, height) in enumerate(zip(HALVES, WALL_HEIGHTS, strict=True)):
        walls(builder, story, half, z, height)
        top = z + height
        brackets(builder, half, top)
        eave = half + EAVE
        lay(
            builder,
            dict.fromkeys(square(PAGODA_X, PAGODA_Y, eave), EDGE),
            top + 3,
            PLATES,
        )
        roof(builder, eave, top + 4)
        lay(
            builder,
            dict.fromkeys(square(PAGODA_X, PAGODA_Y, half), ROOF),
            top + 4,
            BRICKS,
        )
        if story < len(HALVES) - 1:
            railing(builder, half + 1, top + 7)
        z = top + 7
    cap(builder, z)
    finial(builder, z + 3)


def walls(
    builder: ModelBuilder, story: int, half: int, bottom: int, height: int
) -> None:
    """Build one story's walls: round posts, lacquered panels, windows and doors."""
    size = 2 * half
    west, south = PAGODA_X - half, PAGODA_Y - half
    faces = (
        [(west + i, south) for i in range(size)],
        [(west + i, south + size - 1) for i in range(size)],
        [(west, south + i) for i in range(1, size - 1)],
        [(west + size - 1, south + i) for i in range(1, size - 1)],
    )
    for face_index, cells in enumerate(faces):
        offset = 0 if face_index < 2 else 1
        for course in range(height // 3):
            z = BASE + bottom + 3 * course
            run: list[Cell] = []
            for i, (x, y) in enumerate(cells, start=offset):
                kind = wall_kind(story, i, half, course)
                if kind == "panel":
                    run.append((x, y))
                    continue
                panel(builder, run, z)
                run = []
                if kind == "post":
                    builder.place("3062", at=(x, y, z), color=VERMILION)
                elif kind == "window":
                    builder.place("3062", at=(x, y, z), color=MOSS)
            panel(builder, run, z)


def wall_kind(story: int, i: int, half: int, course: int) -> str:
    """Return what fills square i of a wall's face in one course."""
    if i in {0, 2 * half - 1, half - 2, half + 1}:
        return "post"
    center = i in {half - 1, half}
    if story == 0:
        if center:
            return "door" if course < 2 else "panel"
        return "window" if course == 1 else "panel"
    return "window" if center and course == 1 else "panel"


def panel(builder: ModelBuilder, run: list[Cell], z: float) -> None:
    """Lay a run of wall squares with bricks 1 x N in lacquer red."""
    start = 0
    while start < len(run):
        length = next(n for n in (4, 3, 2, 1) if n <= len(run) - start)
        cells = run[start : start + length]
        along_x = cells[0][1] == cells[-1][1] and length > 1
        x, y = min(cells)
        part = BRICKS[1, length]
        builder.place(
            part, at=(x, y, z), rotation="R90" if along_x else "R0", color=LACQUER
        )
        start += length


def brackets(builder: ModelBuilder, half: int, z: int) -> None:
    """Flare the eaves out from the walls with inverted slopes 3 x 2 on every face."""
    size = 2 * half
    west, south = PAGODA_X - half, PAGODA_Y - half
    east, north = west + size - 1, south + size - 1
    at_z = BASE + z
    for x in range(west, west + size, 2):
        builder.place("3747b", at=(x, south - 2, at_z), color=VERMILION)
        builder.place("3747b", at=(x, north, at_z), rotation="R180", color=VERMILION)
    for y in range(south + 1, north, 2):
        builder.place("3747b", at=(east, y, at_z), rotation="R90", color=VERMILION)
        builder.place("3747b", at=(west - 2, y, at_z), rotation="R270", color=VERMILION)


def slope_run(
    builder: ModelBuilder, start: Cell, length: int, z: int, facing: str
) -> None:
    """Lay Slope 33 parts in a row, all falling toward one side."""
    x, y = start
    rotation = {"south": "R0", "east": "R90", "north": "R180", "west": "R270"}[facing]
    along_x = facing in {"south", "north"}
    placed = 0
    while placed < length:
        width = next(n for n in SLOPES_33 if n <= length - placed)
        at = (x + placed, y, BASE + z) if along_x else (x, y + placed, BASE + z)
        builder.place(SLOPES_33[width], at=at, rotation=rotation, color=ROOF)
        placed += width


def roof(builder: ModelBuilder, eave: int, z: int) -> None:
    """Lay a ring of slopes 3 studs deep around the eaves, with upturned corners."""
    west, south = PAGODA_X - eave, PAGODA_Y - eave
    east, north = PAGODA_X + eave - 1, PAGODA_Y + eave - 1
    size = 2 * eave
    slope_run(builder, (west + 1, south), size - 2, z, "south")
    slope_run(builder, (west + 1, north - 2), size - 2, z, "north")
    slope_run(builder, (east - 2, south + 3), size - 6, z, "east")
    slope_run(builder, (west, south + 3), size - 6, z, "west")
    for x, rotation in ((west, "R90"), (east, "R270")):
        # Slopes 45 2 x 1 finish each corner's column, falling toward its tip.
        builder.place("3040", at=(x, south + 1, BASE + z), color=ROOF)
        builder.place("3040", at=(x, north - 2, BASE + z), rotation="R180", color=ROOF)
        for y in (south, north):
            corner_x = x - 1 if x == west else x
            corner_y = y - 1 if y == south else y
            tip(builder, (corner_x, corner_y), z, rotation)


def tip(builder: ModelBuilder, corner: Cell, z: int, rotation: str) -> None:
    """Turn up one corner of the eaves, with a gold bell hung beneath it.

    A plate 2 x 2 reaches one stud out from the corner on both sides. On its outer
    row, a curved slope rises toward the corner; a tile covers its inner row. A round
    plate hangs from the stud under the very tip.
    """
    x, y = corner
    outer_y = y if y < PAGODA_Y else y + 1
    inner_y = y + 1 if y < PAGODA_Y else y
    outer_x = x if rotation == "R90" else x + 1
    builder.place("3022", at=(x, y, BASE + z), color=EDGE)
    builder.place("11477", at=(x, outer_y, BASE + z + 1), rotation=rotation, color=ROOF)
    builder.place("3069", at=(x, inner_y, BASE + z + 1), rotation="R90", color=ROOF)
    builder.place("4073", at=(outer_x, outer_y, BASE + z - 1), color=GOLD)


def railing(builder: ModelBuilder, half: int, z: int) -> None:
    """Run a railing of posts and tiles around a balcony."""
    west, south = PAGODA_X - half, PAGODA_Y - half
    size = 2 * half
    sides = (
        [(west + i, south) for i in range(size)],
        [(west + i, south + size - 1) for i in range(size)],
        [(west, south + i) for i in range(1, size - 1)],
        [(west + size - 1, south + i) for i in range(1, size - 1)],
    )
    for cells in sides:
        start = 0
        for length in rail_lengths(len(cells)):
            segment = cells[start : start + length]
            for x, y in (segment[0], segment[-1]):
                builder.place("4073", at=(x, y, BASE + z), color=VERMILION)
            x, y = segment[0]
            along_x = segment[0][1] == segment[-1][1]
            tile = TILES[1, length]
            rotation = "R90" if along_x else "R0"
            builder.place(
                tile, at=(x, y, BASE + z + 1), rotation=rotation, color=VERMILION
            )
            start += length


def rail_lengths(total: int) -> list[int]:
    """Split a side into rails of 3 studs, with one of 2 or 4 in the middle."""
    middle = {0: 0, 1: 4, 2: 2}[total % 3]
    rails = [3] * ((total - middle) // 3)
    if middle:
        rails.insert(len(rails) // 2, middle)
    return rails


def cap(builder: ModelBuilder, z: int) -> None:
    """Close the top roof with four slopes 3 x 3 laid in a pinwheel."""
    x, y, at_z = PAGODA_X, PAGODA_Y, BASE + z
    builder.place("3298", at=(x - 3, y - 3, at_z), color=ROOF)
    builder.place("4286", at=(x - 1, y - 3, at_z), color=ROOF)
    builder.place("3298", at=(x, y - 3, at_z), rotation="R90", color=ROOF)
    builder.place("4286", at=(x, y - 1, at_z), rotation="R90", color=ROOF)
    builder.place("3298", at=(x + 1, y, at_z), rotation="R180", color=ROOF)
    builder.place("4286", at=(x, y, at_z), rotation="R180", color=ROOF)
    builder.place("3298", at=(x - 3, y + 1, at_z), rotation="R270", color=ROOF)
    builder.place("4286", at=(x - 3, y, at_z), rotation="R270", color=ROOF)


def finial(builder: ModelBuilder, z: int) -> None:
    """Stack the finial: a dark base, nine gold rings, and a gold spike on a jumper.

    Between the rings, four round plates 1 x 1 pinch the column in.
    """
    x, y = PAGODA_X - 1, PAGODA_Y - 1
    builder.place("4032", at=(x, y, BASE + z), color=EDGE)
    builder.place("3941", at=(x, y, BASE + z + 1), color=EDGE)
    z += 4
    for ring in range(9):
        builder.place("4032", at=(x, y, BASE + z), color=GOLD, id=f"ring{ring}")
        z += 1
        if ring < 8:
            for corner_x, corner_y in square(PAGODA_X, PAGODA_Y, 1):
                builder.place("4073", at=(corner_x, corner_y, BASE + z), color=GOLD)
            z += 1
    builder.place("87580", at=(x, y, BASE + z), color=GOLD)
    center_x, center_y = PAGODA_X - 0.5, PAGODA_Y - 0.5
    for course in range(2):
        builder.place(
            "3062", at=(center_x, center_y, BASE + z + 1 + 3 * course), color=GOLD
        )
    builder.place("4073", at=(center_x, center_y, BASE + z + 7), color=GOLD)
    builder.place(
        "98138", at=(center_x, center_y, BASE + z + 8), color=GOLD, id="jewel"
    )


# The torii and the bridge.


def torii(builder: ModelBuilder) -> set[Cell]:
    """Build the torii: two posts, a tie beam, a plaque and a lintel swept up."""
    y = TORII_Y
    z = BASE + GROUND
    for x in TORII_POSTS:
        builder.place("3941", at=(x, y, z), color=EDGE)
        for course in range(1, 6):
            builder.place("3941", at=(x, y, z + 3 * course), color=VERMILION)
        for course in range(2):
            builder.place("3941", at=(x, y, z + 20 + 3 * course), color=VERMILION)
    west = TORII_POSTS[0] - 2
    for layer in range(2):
        builder.place(
            "91988", at=(west, y, z + 18 + layer), rotation="R90", color=VERMILION
        )
    middle = (TORII_POSTS[0] + TORII_POSTS[1]) // 2 + 1
    builder.place("11211", at=(middle - 1, y, z + 20), color=VERMILION)
    builder.place(
        "3004", at=(middle - 1, y + 1, z + 20), rotation="R90", color=VERMILION
    )
    builder.place("3004", at=(middle - 1, y, z + 23), rotation="R90", color=VERMILION)
    builder.place(
        "3004", at=(middle - 1, y + 1, z + 23), rotation="R90", color=VERMILION
    )
    builder.place(
        "3068",
        at=(middle - 1, y - 0.4, z + 20.5),
        rotation="+x+z",
        color=EDGE,
        id="plaque",
    )
    # The lintel: a red beam under a black one, whose ends step up a plate and
    # finish in curved slopes that rise toward the tips.
    builder.place("4282", at=(west - 1, y, z + 26), rotation="R90", color=VERMILION)
    builder.place("4282", at=(west - 1, y, z + 27), rotation="R90", color=EDGE)
    for x in (west + 1, west + 7):
        builder.place("69729", at=(x, y, z + 28), rotation="R90", color=EDGE)
    for x, tip_x, rotation in (
        (west - 3, west - 3, "R90"),
        (west + 13, west + 15, "R270"),
    ):
        builder.place("3020", at=(x, y, z + 28), rotation="R90", color=EDGE)
        tile_x = x + 2 if rotation == "R90" else x
        builder.place("3068", at=(tile_x, y, z + 29), color=EDGE)
        builder.place("15068", at=(tip_x, y, z + 29), rotation=rotation, color=EDGE)
    return {(x + i, y + j) for x in TORII_POSTS for i in range(2) for j in range(2)}


def bridge(builder: ModelBuilder) -> set[Cell]:
    """Build the arched bridge: two arches, a deck, railings and curved ramps."""
    south, north = BRIDGE_ROWS[0], BRIDGE_ROWS[-1]
    for y in (south, north):
        builder.place("3308", at=(ARCH_WEST, y, BASE), rotation="R90", color=VERMILION)
    builder.place(
        "3035", at=(ARCH_WEST, south, BASE + 6), rotation="R90", color=VERMILION
    )
    for x in (ARCH_WEST, ARCH_WEST + 4):
        builder.place("87079", at=(x, south + 1, BASE + 7), rotation="R90", color=BARK)
    for y in (south, north):
        for x in (ARCH_WEST, ARCH_WEST + 2, ARCH_EAST - 2, ARCH_EAST):
            builder.place("3062", at=(x, y, BASE + 7), color=VERMILION)
        for x, length in ((ARCH_WEST + 1, 1), (ARCH_WEST + 3, 2), (ARCH_EAST - 1, 1)):
            builder.place(
                TILES[1, length], at=(x, y, BASE + 7), rotation="R90", color=VERMILION
            )
        builder.place(
            "2431", at=(ARCH_WEST + 2, y, BASE + 10), rotation="R90", color=VERMILION
        )
        for x in (ARCH_WEST, ARCH_EAST):
            builder.place("4073", at=(x, y, BASE + 10), color=GOLD)
            builder.place("98138", at=(x, y, BASE + 11), color=GOLD)
    for side, rotation in ((-1, "R270"), (1, "R90")):
        foot = ARCH_WEST - 4 if side < 0 else ARCH_EAST + 4
        ramp = ARCH_WEST - 3 if side < 0 else ARCH_EAST + 1
        support = {
            (x, y): DARK_STONE for x in range(ramp, ramp + 3) for y in BRIDGE_ROWS
        }
        for layer in range(2):
            lay(builder, support, GROUND + layer, PLATES)
        for y in BRIDGE_ROWS:
            color = VERMILION if y in {south, north} else BARK
            builder.place(
                "50950", at=(ramp, y, BASE + GROUND + 2), rotation=rotation, color=color
            )
            builder.place(
                "54200", at=(foot, y, BASE + GROUND), rotation=rotation, color=color
            )
    return {
        (x, y)
        for x in [
            *range(ARCH_WEST - 4, ARCH_WEST),
            *range(ARCH_EAST + 1, ARCH_EAST + 5),
        ]
        for y in BRIDGE_ROWS
    }


def water(builder: ModelBuilder, pond: set[Cell]) -> None:
    """Tile the pond: shallow by the banks, deep in the middle, with koi and lilies."""
    depths = pond_depths(pond)
    special: set[Cell] = set()
    for head, tail, head_color, tail_color in KOI:
        builder.place("98138", at=(*head, BASE + 1), color=head_color)
        builder.place("98138", at=(*tail, BASE + 1), color=tail_color)
        special.update((head, tail))
    for index, (x, y) in enumerate(LILIES):
        if index % 2:
            builder.place("98138", at=(x, y, BASE + 1), color=LAWN)
        else:
            builder.place("4073", at=(x, y, BASE + 1), color=LAWN)
            builder.place(
                "98138",
                at=(x, y, BASE + 2),
                color="White" if index % 4 else "Dark Pink",
            )
        special.add((x, y))
    for x, y in sorted(pond - special - UNDER_ARCHES):
        if hashed(x, y, 7) < 0.04:  # A petal afloat
            color = "Dark Pink" if hashed(x, y, 8) < 0.6 else "White"
            builder.place("98138", at=(x, y, BASE + 1), color=color)
            special.add((x, y))
    cells = {
        cell: SHALLOW if depths[cell] <= 2 else DEEP
        for cell in pond
        if cell not in special and cell not in UNDER_ARCHES
    }
    lay(builder, cells, 1, TILES)


def gravel(builder: ModelBuilder, voxels: Voxels) -> None:
    """Tile the gravel bed in raked stripes along x, with two rings around each rock."""
    bed = [(x, y) for x in GRAVEL[0] for y in GRAVEL[1]]
    rocks = [(x, y) for x, y in bed if (x, y, 2) in voxels]
    cells: dict[Cell, str] = {}
    for x, y in bed:
        if (x, y) in rocks:
            continue
        nearest = min(hypot(x - rock_x, y - rock_y) for rock_x, rock_y in rocks)
        if nearest < 1.5:
            cells[x, y] = "White"
        elif nearest < 2.5:
            cells[x, y] = STONE
        else:
            cells[x, y] = "White" if y % 2 else STONE
    lay(builder, cells, 2, TILES)


def lantern(builder: ModelBuilder, x: int, y: int) -> set[Cell]:
    """Build a stone lantern: base, pillar, light box, roof and jewel."""
    z = BASE + GROUND
    builder.place("11212", at=(x, y, z), color=STONE)
    builder.place("3062", at=(x + 1, y + 1, z + 1), color=STONE)
    builder.place("3062", at=(x + 1, y + 1, z + 4), color=STONE)
    builder.place("11212", at=(x, y, z + 7), color=STONE)
    for corner_x in (x, x + 2):
        for corner_y in (y, y + 2):
            builder.place("3062", at=(corner_x, corner_y, z + 8), color=STONE)
    builder.place("3062", at=(x + 1, y + 1, z + 8), color="Trans-Yellow")
    builder.place("11212", at=(x, y, z + 11), color=STONE)
    for (i, j), rotation in (
        ((1, 0), "R0"),
        ((0, 0), "R0"),
        ((2, 0), "R0"),
        ((1, 2), "R180"),
        ((0, 2), "R180"),
        ((2, 2), "R180"),
        ((0, 1), "R270"),
        ((2, 1), "R90"),
    ):
        builder.place(
            "54200", at=(x + i, y + j, z + 12), rotation=rotation, color=STONE
        )
    builder.place("3062", at=(x + 1, y + 1, z + 12), color=STONE)
    builder.place("98138", at=(x + 1, y + 1, z + 15), color=STONE)
    return {(x + i, y + j) for i in range(3) for j in range(3)}


def path_stones(
    builder: ModelBuilder, line: Iterable[tuple[float, float]]
) -> set[Cell]:
    """Lay stepping stones every three studs along a line, and return their squares."""
    points = list(line)
    spots = [points[-1]]
    for (start_x, start_y), (end_x, end_y) in pairwise(points):
        steps = max(1, round(hypot(end_x - start_x, end_y - start_y) / 3))
        spots += [
            (
                start_x + (end_x - start_x) * step / steps,
                start_y + (end_y - start_y) * step / steps,
            )
            for step in range(steps)
        ]
    taken: set[Cell] = set()
    for count, (spot_x, spot_y) in enumerate(spots):
        x, y = floor(spot_x + 0.5) - 1, floor(spot_y + 0.5) - 1
        color = (STONE, DARK_STONE, "Dark Tan")[count % 3]
        part = "14769" if count % 2 == 0 else "3068"
        builder.place(part, at=(x, y, BASE + GROUND), color=color)
        taken.update({(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)})
    return taken


# Small touches.


def hanami(builder: ModelBuilder) -> set[Cell]:
    """Build a bench draped in red felt, and a red parasol beside it."""
    x, y = BENCH
    z = BASE + GROUND
    for leg_x in (x, x + 5):
        builder.place("3004", at=(leg_x, y, z), color=BARK)
    builder.place("3795", at=(x, y, z + 3), rotation="R90", color=BARK)
    builder.place("69729", at=(x, y, z + 4), rotation="R90", color=VERMILION, id="felt")
    pole_x, pole_y = PARASOL
    for course in range(4):
        builder.place("3062", at=(pole_x, pole_y, z + 3 * course), color=BARK)
    top = z + 12
    builder.place("11212", at=(pole_x - 1, pole_y - 1, top), color=VERMILION)
    for i in (-1, 0, 1):  # Slopes 45 2 x 1 fall away on all four sides.
        builder.place("3040", at=(pole_x + i, pole_y - 2, top + 1), color=VERMILION)
        builder.place(
            "3040",
            at=(pole_x + i, pole_y + 1, top + 1),
            rotation="R180",
            color=VERMILION,
        )
    builder.place(
        "3040", at=(pole_x + 1, pole_y, top + 1), rotation="R90", color=VERMILION
    )
    builder.place(
        "3040", at=(pole_x - 2, pole_y, top + 1), rotation="R270", color=VERMILION
    )
    builder.place("3062", at=(pole_x, pole_y, top + 1), color=VERMILION)
    builder.place("4073", at=(pole_x, pole_y, top + 4), color=EDGE, id="parasol")
    return {(x + i, y + j) for i in range(6) for j in range(2)} | {PARASOL}


def basin(builder: ModelBuilder) -> set[Cell]:
    """Build a stone water basin: a round stone, its water, and a ladle stone."""
    x, y = BASIN
    z = BASE + GROUND
    builder.place("3941", at=(x, y, z), color=DARK_STONE)
    builder.place("14769", at=(x, y, z + 3), color=SHALLOW, id="basin")
    builder.place("4073", at=(x + 2, y, z), color=STONE)
    builder.place("4073", at=(x - 1, y + 1, z), color=DARK_STONE)
    return {(x + i, y + j) for i in range(2) for j in range(2)} | {
        (x + 2, y),
        (x - 1, y + 1),
    }


def irises(builder: ModelBuilder) -> set[Cell]:
    """Plant irises by the pond: green leaves under blue flowers."""
    for x, y in IRISES:
        builder.place("3062", at=(x, y, BASE + GROUND), color=SHADE)
        builder.place("98138", at=(x, y, BASE + GROUND + 3), color="Medium Blue")
    return set(IRISES)


def petals(builder: ModelBuilder, voxels: Voxels, taken: set[Cell]) -> None:
    """Scatter fallen petals on the lawn, thickest under the cherry trees."""
    for x in range(SIZE):
        for y in range(SIZE):
            if (x, y) in taken or (x, y, GROUND) in voxels:
                continue
            if voxels.get((x, y, GROUND - 1)) not in {LAWN, SHADE}:
                continue
            nearest = min(
                hypot(x + 0.5 - shape.x, y + 0.5 - shape.y) for shape in TREES
            )
            if hashed(x, y, 9) < 0.3 * max(0.0, 1 - nearest / 10):
                color = "Dark Pink" if hashed(x, y, 10) < 0.65 else "White"
                builder.place("98138", at=(x, y, BASE + GROUND), color=color)


def build() -> ModelBuilder:
    """Build the garden on its baseplate."""
    builder = ModelBuilder("japanese-garden")
    builder.place("4186", at=(0, 0, 0), color=LAWN, id="baseplate")
    pond = {(x, y) for x in range(SIZE) for y in range(SIZE) if in_pond(x, y)}
    voxels = ground(pond) | plinth() | hedges()
    for shape in MOUNDS:
        voxels |= mound(shape)
    for shape in TREES:
        voxels |= tree(shape)
    voxels = settle(
        {
            voxel: color
            for voxel, color in voxels.items()
            if 0 <= voxel[0] < SIZE and 0 <= voxel[1] < SIZE
        }
    )
    voxels = prune(builder, voxels)
    print(f"{len(voxels):,} voxels")
    garden = builder.component("garden")
    garden.fill(voxels, id="ground")
    low_x = min(x for x, _, _ in voxels)
    low_y = min(y for _, y, _ in voxels)
    builder.instance("garden", at=(low_x, low_y, BASE), id="garden")
    water(builder, pond)
    gravel(builder, voxels)
    pagoda(builder)
    taken = torii(builder) | bridge(builder) | hanami(builder) | basin(builder)
    taken |= irises(builder)
    for x, y in LANTERNS:
        taken |= lantern(builder, x, y)
    taken |= path_stones(builder, PATH) | path_stones(builder, PATH_EAST)
    petals(builder, voxels, taken)
    return builder
