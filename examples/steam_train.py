# Copyright 2026 Maxence Faldor
"""A steam train at a small country station.

- The ground spans 100 x 32 studs. The train on it is 78 studs long: a red and black
  locomotive, its tender and two green and cream carriages.
- The boiler is voxels of a circular section, filled with bricks and plates. Cheese
  slopes round off its top corners, and gold bands ring it.
- Round plates held sideways on bricks with side studs make the wheels. Tiles held the
  same way make the coupling rods, the number plates and the nameboard.
- The steam, the trees and the bushes are balls of voxels. The script drops any part
  the fill cannot hold, so each stays in one piece.
- Jumpers center the lamp posts, the whistle, the headlamp, the clock and the gables'
  round windows half a stud off the grid.
- Inverted slopes carry the station's canopy as brackets, and arches open the base of
  the water tower.
- The carriage, the lamp, the bench and the flower tub are components, each placed two
  to four times.

Run: ``uv run bricky build examples/steam_train.py``
"""

from collections.abc import Callable
from itertools import groupby
from math import hypot

from bricky import ComponentBuilder, ModelBuilder, default_catalog
from bricky import voxels as model_voxels
from bricky.fill import BRICKS as FILL_BRICKS
from bricky.fill import PLATES as FILL_PLATES
from bricky.fill import Placement, plan_fill

type Placer = ModelBuilder | ComponentBuilder
type Point = tuple[float, float, float]
type Square = tuple[int, int]
type Voxels = dict[tuple[int, int, int], str]
type Cell = Callable[[int, int, int], str | None]
"""The color of a wall cell at x and y in a course, or None to leave it to others."""

LENGTH, DEPTH = 100, 32  # The ground, in studs
SOUTH_RAIL, NORTH_RAIL = 5, 10  # The y of each rail; vehicles span y 5 to 10
WHEEL_BOTTOM = 5  # The top of the rail heads, in plates
FLOOR = 10  # Vehicle floors lie from z 10 to 11
DECK = 10  # The top of the platform's brickwork, under its paving

CARRIAGE_XS = (10, 32)
CARRIAGE_LENGTH = 20
TENDER_X = 54
LOCOMOTIVE_X = 65  # The cab's back; the cowcatcher ends 23 studs east of it
BOILER = range(LOCOMOTIVE_X + 5, LOCOMOTIVE_X + 19)
PLATFORM = (4, 56)  # The platform spans x 4 to 55 and y 12 to 19
STATION = (22, 42, 20, 30)  # The west, east, south and north of the station's walls
TOWER = (89, 16)  # The water tower's base spans 6 x 6 studs from here

GRASS, BALLAST, SLEEPER = "Green", "Dark Bluish Gray", "Reddish Brown"
RAIL, RAIL_HEAD = "Dark Bluish Gray", "Light Bluish Gray"
FRAME, LIVERY, GOLD = "Black", "Red", "Pearl Gold"
COACH, CREAM, GLASS = "Dark Green", "Tan", "Trans-Clear"
WALL, ROOF, STONE, PAVING = "Tan", "Dark Red", "Dark Tan", "Light Bluish Gray"
FLOWERS = ("Red", "Yellow", "White", "Magenta", "Bright Light Orange", "Dark Pink")

BRICKS = {
    16: "2465",
    12: "6112",
    10: "6111",
    8: "3008",
    6: "3009",
    4: "3010",
    3: "3622",
    2: "3004",
    1: "3005",
}
PLATES = {
    12: "60479",
    10: "4477",
    8: "3460",
    6: "3666",
    4: "3710",
    3: "3623",
    2: "3023",
    1: "3024",
}
TILES = {8: "4162", 6: "6636", 4: "2431", 3: "63864", 2: "3069", 1: "3070"}
WIDE_PLATES = {
    16: "4282",
    14: "91988",
    12: "2445",
    10: "3832",
    8: "3034",
    6: "3795",
    4: "3020",
    3: "3021",
    2: "3022",
}
WIDE_TILES = {6: "69729", 4: "87079", 3: "26603", 2: "3068"}
SLOPES = {4: "3037", 3: "3038", 2: "3039", 1: "3040"}  # Slope 45 2 x N, N along x


def made_in(part: str, color: int | str) -> bool:
    """Return whether the catalog lists the part in the color."""
    catalog = default_catalog()
    entry = catalog.entry(part)
    return entry is not None and catalog.resolve_color(color).id in entry.colors


def split(sizes: list[int], length: int) -> list[int]:
    """Split a length into the fewest of the given sizes, longest first."""
    best: dict[int, list[int]] = {0: []}
    for total in range(1, length + 1):
        options = [
            [size, *best[total - size]]
            for size in sizes
            if size <= total and total - size in best
        ]
        if options:
            best[total] = min(options, key=len)
    return sorted(best[length], reverse=True)


def line(
    placer: Placer,
    parts: dict[int, str],
    color: str,
    start: Point,
    end: tuple[float, float],
) -> None:
    """Lay a straight run of parts from start to end, along x or along y.

    The end gives the x and y where the run stops; one of them equals the start's.
    """
    x, y, z = start
    along_x = end[0] != x
    length = round(end[0] - x if along_x else end[1] - y)
    sizes = [size for size, part in parts.items() if made_in(part, color)]
    done = 0
    for size in split(sizes, length):
        if along_x:
            rotation = "R0" if size == 1 and parts is not WIDE_PLATES else "R90"
            placer.place(
                parts[size], at=(x + done, y, z), color=color, rotation=rotation
            )
        else:
            placer.place(parts[size], at=(x, y + done, z), color=color)
        done += size


def squares(placement: Placement) -> set[Square]:
    """Return the stud squares a part of a fill covers."""
    sizes = {
        part: size
        for parts in (FILL_BRICKS, FILL_PLATES)
        for size, part in parts.items()
    }
    short, long = sizes[placement.part]
    width, depth = (short, long) if placement.rotation == "R0" else (long, short)
    x, y, _ = placement.at
    return {(x + i, y + j) for i in range(width) for j in range(depth)}


def held(plan: list[Placement]) -> list[Placement]:
    """Return the parts of a fill that a chain of studs joins to its lowest layer."""
    bricks = set(FILL_BRICKS.values())
    spans = [
        (
            placement.at[2],
            placement.at[2] + (3 if placement.part in bricks else 1),
            squares(placement),
        )
        for placement in plan
    ]
    reached = {index for index, (bottom, _, _) in enumerate(spans) if bottom == 0}
    queue = list(reached)
    while queue:
        bottom, top, area = spans[queue.pop()]
        for index, (other_bottom, other_top, other_area) in enumerate(spans):
            touching = other_bottom == top or other_top == bottom
            if index not in reached and touching and area & other_area:
                reached.add(index)
                queue.append(index)
    return [plan[index] for index in sorted(reached)]


def fill_above(
    placer: Placer, voxels: Voxels, prefix: str, *, prune: bool = False
) -> None:
    """Fill voxels whose lowest layer rests on parts placed before them.

    With prune, the fill drops the voxels of parts that nothing holds and plans again,
    so a loose shape such as a cloud or a crown of leaves stays in one piece.
    """
    base = min(z for _, _, z in voxels)
    lowered = {(x, y, z - base): color for (x, y, z), color in voxels.items()}
    plan = plan_fill(lowered, made_in=made_in)
    while prune and len(kept := held(plan)) < len(plan):
        for placement in plan:
            if placement in kept:
                continue
            height = 3 if placement.part in FILL_BRICKS.values() else 1
            for x, y in squares(placement):
                for layer in range(height):
                    lowered.pop((x, y, placement.at[2] + layer), None)
        plan = plan_fill(lowered, made_in=made_in)
    for placement in plan:
        x, y, z = placement.at
        placer.place(
            placement.part,
            at=(x, y, z + base),
            color=placement.color,
            rotation=placement.rotation,
            id=f"{prefix}.{x}.{y}.{z + base}",
        )


def noise(*key: int) -> float:
    """Return a fixed pseudo-random number in [0, 1) for a key, alike every build."""
    value = 2_166_136_261
    for part in key:
        value = ((value ^ (part & 0xFFFFFFFF)) * 16_777_619) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 2_246_822_519) & 0xFFFFFFFF
    value ^= value >> 13
    return value / 2**32


type Sphere = tuple[float, float, float, float, str]
"""A sphere's center, x and y in studs and z in plates, its radius in studs, a color."""


def ball(spheres: list[Sphere], floor: int) -> Voxels:
    """Return the voxels inside the spheres from the floor up, in the last color."""
    reach = max(sphere[3] for sphere in spheres)
    xs = [sphere[0] for sphere in spheres]
    ys = [sphere[1] for sphere in spheres]
    top = max(sphere[2] for sphere in spheres) + 2.5 * reach
    voxels: Voxels = {}
    for x in range(int(min(xs) - reach) - 1, int(max(xs) + reach) + 2):
        for y in range(int(min(ys) - reach) - 1, int(max(ys) + reach) + 2):
            for z in range(floor, int(top) + 2):
                for center_x, center_y, center_z, radius, color in spheres:
                    east, north = x + 0.5 - center_x, y + 0.5 - center_y
                    if hypot(east, north, (z + 0.5 - center_z) / 2.5) <= radius:
                        voxels[x, y, z] = color
    return voxels


def tile(
    builder: ModelBuilder,
    area: set[Square],
    z: int,
    color_of: Callable[[int, int], str],
    corner: Callable[[int, int], bool],
) -> None:
    """Cover an area with tiles 2 x 2 from the corners that allow one, then smaller."""
    free = set(area)
    for x, y in sorted(free, key=lambda square: (square[1], square[0])):
        if (x, y) not in free:
            continue
        color = color_of(x, y)
        block = {(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)}
        pair = {(x, y), (x + 1, y)}
        if corner(x, y) and block <= free:
            builder.place("3068", at=(x, y, z), color=color)
            free -= block
        elif pair <= free and color_of(x + 1, y) == color:
            builder.place("3069", at=(x, y, z), rotation="R90", color=color)
            free -= pair
        else:
            builder.place("3070", at=(x, y, z), color=color)
            free.discard((x, y))


def runs(placer: Placer, cells: list[Square], z: int, course: int, cell: Cell) -> None:
    """Lay a straight wall of cells, one run of bricks per color; skip cells of None."""
    along_x = len(cells) > 1 and cells[1][0] != cells[0][0]
    for color, group in groupby(cells, key=lambda square: cell(*square, course)):
        members = list(group)
        if color is None:
            continue
        (x, y), (last_x, last_y) = members[0], members[-1]
        stop = (last_x + 1, y) if along_x else (x, last_y + 1)
        line(placer, BRICKS, color, (x, y, z), stop)


def walls(
    placer: Placer, box: tuple[int, int, int, int], z: int, course: int, cell: Cell
) -> None:
    """Lay one course of walls one stud thick, their corners bonded alternately.

    The box gives the walls' west, east, south and north, ends excluded.
    """
    west, east, south, north = box
    full_x = course % 2 == 0
    xs = range(west, east) if full_x else range(west + 1, east - 1)
    ys = range(south + 1, north - 1) if full_x else range(south, north)
    for y in (south, north - 1):
        runs(placer, [(x, y) for x in xs], z, course, cell)
    for x in (west, east - 1):
        runs(placer, [(x, y) for y in ys], z, course, cell)


def ring(placer: Placer, box: tuple[int, int, int, int], z: int, color: str) -> None:
    """Lay a ring of plates on top of walls one stud thick."""
    west, east, south, north = box
    for y in (south, north - 1):
        line(placer, PLATES, color, (west, y, z), (east, y))
    for x in (west, east - 1):
        line(placer, PLATES, color, (x, south + 1, z), (x, north - 1))


def deck_height(x: int, y: int) -> int:
    """Return how many plates of brickwork stand under the platform at x and y."""
    west, east, south, north = STATION
    if PLATFORM[0] <= x < PLATFORM[1] and 12 <= y < 20:
        return DECK
    if west <= x < east and south <= y < north:
        return DECK
    if PLATFORM[1] <= x < PLATFORM[1] + DECK - 1 and 12 <= y < 20:
        return DECK - 1 - (x - PLATFORM[1])  # The ramp falls a plate per stud.
    return 0


def ground(builder: ModelBuilder) -> None:
    """Fill the grass, a bed of ballast under the track and the platform's brickwork."""
    voxels: Voxels = {}
    for x in range(LENGTH):
        for y in range(DEPTH):
            if height := deck_height(x, y):
                for z in range(height):
                    voxels[x, y, z] = STONE
                continue
            voxels[x, y, 0] = BALLAST if 2 <= y < 14 else GRASS
            if 3 <= y < 13:
                voxels[x, y, 1] = BALLAST
    fill_above(builder, voxels, "ground")


def track(builder: ModelBuilder) -> None:
    """Lay sleepers every two studs, then rails of plates under staggered tiles."""
    for x in range(0, LENGTH, 2):
        builder.place("3460", at=(x, 4, 2), color=SLEEPER)  # Plate 1 x 8
    for y in (SOUTH_RAIL, NORTH_RAIL):
        line(builder, PLATES, RAIL, (0, y, 3), (LENGTH, y))
        for start, end in ((0, 4), (4, LENGTH - 4), (LENGTH - 4, LENGTH)):
            line(builder, TILES, RAIL_HEAD, (start, y, 4), (end, y))


def axle(placer: Placer, x: float, color: str) -> None:
    """Hold a pair of wheels, round plates 2 x 2, sideways on bricks with side studs."""
    placer.place("11211", at=(x, 6, 7), color=FRAME)
    placer.place("11211", at=(x, 9, 7), rotation="R180", color=FRAME)
    placer.place("4032", at=(x, 5.6, WHEEL_BOTTOM), rotation="+x+z", color=color)
    placer.place("4032", at=(x, 10, WHEEL_BOTTOM), rotation="-x+z", color=color)


def rods(placer: Placer, x: float, length: int, color: str) -> None:
    """Hold tiles sideways across the upper studs of a row of wheels, on both sides."""
    part, z = TILES[length], WHEEL_BOTTOM + 2.5
    placer.place(part, at=(x, 5.2, z), rotation="-z+x", color=color)
    placer.place(part, at=(x, 10.4, z), rotation="+z+x", color=color)


def underframe(
    placer: Placer,
    span: range,
    axles: list[int],
    supports: list[int],
    extra: Voxels | None = None,
) -> None:
    """Fill the supports on the sleepers, the chassis and the frame around the axles."""
    voxels: Voxels = dict(extra or {})
    for x in span:
        for y in range(6, 10):
            for z in (6, 7, 8, 9):
                voxels[x, y, z] = FRAME
            if x in supports:  # A brick 1 x 4 on a sleeper, between the rails
                for z in (3, 4, 5):
                    voxels[x, y, z] = FRAME
    for start in axles:  # Room for the bricks with side studs that hold the wheels
        for x in (start, start + 1):
            for y in (6, 9):
                for z in (7, 8, 9):
                    voxels.pop((x, y, z), None)
    fill_above(placer, voxels, f"frame{span.start}")


def footplate(placer: Placer, start: int, length: int, edge: str) -> None:
    """Lay the floor: plates two studs wide, colored at the edges and black between."""
    for y, color in ((5, edge), (7, FRAME), (9, edge)):
        line(placer, WIDE_PLATES, color, (start, y, FLOOR), (start + length, y))


def boiler_color(x: int) -> str:
    """Return the boiler's livery at x: red, with gold bands and a black smokebox."""
    if x >= LOCOMOTIVE_X + 16:
        return FRAME
    if x - LOCOMOTIVE_X in {8, 12, 15}:
        return GOLD
    return LIVERY


def boiler(builder: ModelBuilder) -> None:
    """Fill a round boiler from voxels of a circular section; add a smokebox door."""
    voxels: Voxels = {}
    for x in BOILER:
        for y in range(6, 10):
            for z in range(11, 20) if y in {7, 8} else range(13, 19):
                voxels[x, y, z] = boiler_color(x)
    front = BOILER.stop
    for y in (7, 8):  # Room for the brick with side studs that holds the door
        for z in (13, 14, 15):
            del voxels[front - 1, y, z]
    fill_above(builder, voxels, "boiler")
    builder.place("11211", at=(front - 1, 7, 13), rotation="R90", color=FRAME)
    builder.place("4032", at=(front, 7, 13.5), rotation="+y+z", color=FRAME)
    builder.place(
        "14769", at=(front + 0.4, 7, 13.5), rotation="+y+z", color=GOLD, id="door"
    )


def boiler_top(builder: ModelBuilder) -> None:
    """Round off the boiler's top corners with cheese slopes, and tile its crown."""
    x = BOILER.start
    while x < BOILER.stop:
        color = boiler_color(x)
        pair = x + 1 < BOILER.stop and boiler_color(x + 1) == color
        part = "85984" if pair else "54200"  # Slope 30 1 x 2 or 1 x 1
        builder.place(part, at=(x, 6, 19), color=color)
        builder.place(part, at=(x, 9, 19), rotation="R180", color=color)
        x += 2 if pair else 1
    fittings = {6, 9, 10, 16, 17, 18}  # The whistle, the dome, the chimney, the lamp
    free = [x for x in BOILER if x - LOCOMOTIVE_X not in fittings]
    for (color, _), group in groupby(
        enumerate(free), key=lambda item: (boiler_color(item[1]), item[1] - item[0])
    ):
        xs = [x for _, x in group]
        if len(xs) == 1:
            builder.place("3069", at=(xs[0], 7, 20), color=color)
        else:
            line(builder, WIDE_TILES, color, (xs[0], 7, 20), (xs[-1] + 1, 7))


def chimney(builder: ModelBuilder) -> None:
    """Build the chimney with its gold rim, and a column of steam billowing back."""
    stack = LOCOMOTIVE_X + 16
    for z in (20, 23, 26):
        builder.place("3941", at=(stack, 7, z), color=FRAME)
    builder.place("4032", at=(stack, 7, 29), color=GOLD, id="chimney-rim")
    puffs = (
        (1.0, 8.0, 31.5, 1.15),
        (1.0, 8.0, 34.5, 1.7),
        (0.2, 7.4, 38.0, 2.3),
        (-1.8, 8.8, 40.5, 2.4),
        (-4.2, 7.6, 41.5, 2.1),
        (-6.4, 8.5, 42.5, 1.6),
        (-8.4, 7.9, 42.0, 1.1),
    )
    steam = ball(
        [(stack + offset, y, z, radius, "White") for offset, y, z, radius in puffs], 30
    )
    for x, y, z in list(steam):  # The steam leaves through the chimney's top.
        if z < 32 and not (stack <= x < stack + 2 and 7 <= y < 9):
            del steam[x, y, z]
    fill_above(builder, steam, "steam", prune=True)


def fittings(builder: ModelBuilder) -> None:
    """Add a gold dome, a gold whistle and a headlamp, the last two on jumpers."""
    dome = LOCOMOTIVE_X + 9
    builder.place("4032", at=(dome, 7, 20), color=GOLD)
    builder.place("4032", at=(dome, 7, 21), color=GOLD)
    builder.place("14769", at=(dome, 7, 22), color=GOLD, id="dome")
    whistle = LOCOMOTIVE_X + 6
    builder.place("15573", at=(whistle, 7, 20), color=LIVERY)  # Jumper 1 x 2
    builder.place("3062", at=(whistle, 7.5, 21), color=GOLD, id="whistle")
    builder.place("4073", at=(whistle, 7.5, 24), color=GOLD)
    lamp = LOCOMOTIVE_X + 18
    builder.place("15573", at=(lamp, 7, 20), color=FRAME)
    builder.place("87087", at=(lamp, 7.5, 21), rotation="R90", color=FRAME)
    builder.place(
        "98138",
        at=(lamp + 1, 7.5, 21.5),
        rotation="+y+z",
        color="Trans-Yellow",
        id="headlamp",
    )
    builder.place("54200", at=(lamp, 7.5, 24), rotation="R90", color=FRAME)


def cab(builder: ModelBuilder) -> None:
    """Build the cab: red walls with wide side windows, under a black curved roof."""
    x = LOCOMOTIVE_X
    for y in (5, 10):
        builder.place("3004", at=(x, y, 11), rotation="R90", color=LIVERY)
        builder.place("3622", at=(x + 2, y, 11), rotation="R90", color=LIVERY)
        builder.place("3005", at=(x, y, 14), color=LIVERY)
        rotation = "R0" if y == SOUTH_RAIL else "R180"
        builder.place("11211", at=(x + 1, y, 14), rotation=rotation, color=LIVERY)
        builder.place("3004", at=(x + 3, y, 14), rotation="R90", color=LIVERY)
        for z in (17, 20):  # The window's pillars
            builder.place("3005", at=(x, y, z), color=LIVERY)
            builder.place("3005", at=(x + 4, y, z), color=LIVERY)
    # Brass number plates: tiles held sideways on the studs of the bricks below them.
    builder.place("3069", at=(x + 1, 4.6, 14.5), rotation="-z+x", color=GOLD)
    builder.place("3069", at=(x + 1, 11, 14.5), rotation="+z+x", color=GOLD)
    front = x + 4  # The front wall, with the firebox glowing inside
    builder.place("3010", at=(front, 6, 11), color=LIVERY)
    builder.place("3005", at=(front, 6, 14), color=LIVERY)
    builder.place("3005", at=(front, 7, 14), color="Trans-Orange", id="firebox")
    builder.place("3005", at=(front, 8, 14), color="Trans-Orange")
    builder.place("3005", at=(front, 9, 14), color=LIVERY)
    builder.place("3010", at=(front, 6, 17), color=LIVERY)
    builder.place("3005", at=(front, 6, 20), color=GLASS)
    builder.place("3004", at=(front, 7, 20), color=LIVERY)
    builder.place("3005", at=(front, 9, 20), color=GLASS)
    builder.place("3036", at=(x, 4, 23), color=FRAME)  # Plate 6 x 8
    for offset in (0, 2, 4):
        builder.place("15068", at=(x + offset, 4, 24), color=FRAME)
        builder.place("15068", at=(x + offset, 10, 24), rotation="R180", color=FRAME)
    builder.place("3032", at=(x, 6, 24), rotation="R90", color=FRAME)
    builder.place("69729", at=(x, 6, 25), rotation="R90", color=FRAME)
    builder.place("69729", at=(x, 8, 25), rotation="R90", color=FRAME)


def locomotive(builder: ModelBuilder) -> None:
    """Build the locomotive: wheels, cylinders, cowcatcher, boiler, chimney and cab."""
    x = LOCOMOTIVE_X
    drivers = [x + 6, x + 9, x + 12]
    chassis = {  # Six studs wide under the cylinders, narrowing under the cowcatcher
        (column, y, 6): FRAME
        for column in range(x + 14, x + 23)
        for y in range(5, 11)
        if column < x + 22 or y in {7, 8}
    }
    supports = [x + 3, x + 7, x + 11, x + 15]
    underframe(builder, range(x, x + 19), [x + 1, *drivers], supports, chassis)
    axle(builder, x + 1, FRAME)
    for driver in drivers:
        axle(builder, driver, LIVERY)
        for y, rotation in ((5.2, "+x+z"), (10.4, "-x+z")):  # Crank pins
            builder.place(
                "98138", at=(driver, y, WHEEL_BOTTOM), rotation=rotation, color=PAVING
            )
    rods(builder, x + 6, 8, PAVING)
    for y in (5, 10):  # The cylinders: round bricks held sideways, with gold covers
        builder.place("87087", at=(x + 14, y, 7), rotation="R90", color=FRAME)
        for offset in (15, 16.2, 17.4):
            builder.place("3062", at=(x + offset, y, 7.5), rotation="+y+z", color=FRAME)
        builder.place("98138", at=(x + 18.6, y, 7.5), rotation="+y+z", color=GOLD)
    builder.place("3009", at=(x + 19, 5, 7), color=LIVERY, id="buffer-beam")
    # The cowcatcher: slopes that fall toward the front, the middle one longest.
    builder.place("3039", at=(x + 20, 5, 7), rotation="R90", color=FRAME)
    builder.place("3298", at=(x + 20, 7, 7), rotation="R90", color=FRAME)
    builder.place("3039", at=(x + 20, 9, 7), rotation="R90", color=FRAME)
    footplate(builder, x, 21, LIVERY)
    for y in (5, 10):  # Smooth running boards beside the boiler
        line(builder, TILES, LIVERY, (x + 5, y, 11), (x + 19, y))
    builder.place("69729", at=(x + 19, 5, 11), color=LIVERY)  # Tile 2 x 6
    boiler(builder)
    boiler_top(builder)
    chimney(builder)
    fittings(builder)
    cab(builder)


def tender(builder: ModelBuilder) -> None:
    """Build the tender: red sides with a gold band and crest, heaped with coal."""
    x = TENDER_X
    wheels = [x + 1, x + 4, x + 7]
    underframe(builder, range(x, x + 10), wheels, [x + 2, x + 6])
    for wheel in wheels:
        axle(builder, wheel, FRAME)
    footplate(builder, x, 10, LIVERY)
    box = (x, x + 10, 5, 11)
    crest = {x + 4, x + 5}  # A gold disc on each side, on bricks with side studs
    for course in range(2):
        walls(
            builder,
            box,
            11 + 3 * course,
            course,
            lambda cell_x, _, course: None if course and cell_x in crest else LIVERY,
        )
    builder.place("11211", at=(x + 4, 5, 14), color=LIVERY)
    builder.place("11211", at=(x + 4, 10, 14), rotation="R180", color=LIVERY)
    builder.place("14769", at=(x + 4, 4.6, 12), rotation="+x+z", color=GOLD)
    builder.place("14769", at=(x + 4, 11, 12), rotation="-x+z", color=GOLD)
    ring(builder, box, 17, GOLD)
    walls(builder, box, 18, 0, lambda *_: LIVERY)
    ring(builder, box, 21, FRAME)
    coal: Voxels = {}
    for column in range(x + 1, x + 9):
        for row in range(6, 10):
            east, north = (column + 0.5 - (x + 5)) / 4.8, (row + 0.5 - 8) / 2.8
            heap = max(1, round(3.6 * (1 - east * east - north * north)))
            for z in range(11, 21 + heap):
                coal[column, row, z] = FRAME
    fill_above(builder, coal, "coal")


COACH_WINDOWS = {4, 5, 7, 8, 11, 12, 14, 15}
COACH_DOORS = {1, 2, 17, 18}
HANDLES = (2, 17)


def coach_cell(x: int, y: int, course: int) -> str | None:
    """Return a carriage wall cell's color: green below, cream windows, green doors."""
    side = y in {SOUTH_RAIL, NORTH_RAIL}
    if course < 2:
        return None if side and course == 1 and x in HANDLES else COACH
    if not side:
        return GLASS if y in {7, 8} else CREAM
    if x in COACH_DOORS:
        return GLASS if course == 2 else COACH
    return GLASS if x in COACH_WINDOWS else CREAM


def carriage(part: ComponentBuilder) -> None:
    """Build a carriage on two bogies: green and cream, with doors, windows, seats."""
    length = CARRIAGE_LENGTH
    wheels = [2, 6, 12, 16]
    underframe(part, range(length), wheels, [2, 10, 18])
    for wheel in wheels:
        axle(part, wheel, FRAME)
    for x in (2, 12):  # The bogies' side frames
        rods(part, x, 6, BALLAST)
    footplate(part, 0, length, FRAME)
    for x in (4, 8, 11, 15):  # Seats, seen through the windows
        part.place("3010", at=(x, 6, 11), color="Dark Red")
    box = (0, length, 5, 11)
    for course in range(4):
        walls(part, box, 11 + 3 * course, course, coach_cell)
    for x in HANDLES:  # Door handles: round tiles on studs on the sides of bricks
        part.place("87087", at=(x, 5, 14), color=COACH)
        part.place("98138", at=(x, 4.6, 14.5), rotation="+x+z", color=GOLD)
        part.place("87087", at=(x, 10, 14), rotation="R180", color=COACH)
        part.place("98138", at=(x, 11, 14.5), rotation="-x+z", color=GOLD)
    ring(part, box, 23, COACH)
    for x in (0, 10):
        part.place("3033", at=(x, 5, 24), rotation="R90", color=BALLAST)  # 6 x 10
    for x in range(length):  # A barrel roof of curved slopes, back to back
        part.place("50950", at=(x, 5, 25), color=BALLAST)
        part.place("50950", at=(x, 8, 25), rotation="R180", color=BALLAST)


def lamp(part: ComponentBuilder) -> None:
    """Build a lamp post on a jumper, half a stud off the grid, with a lantern."""
    part.place("15573", at=(0, 0, 0), color=COACH)  # Jumper 1 x 2, along y
    for z in (1, 4, 7, 10):
        part.place("3062", at=(0, 0.5, z), color=COACH)
    part.place("4073", at=(0, 0.5, 13), color=FRAME)
    part.place("3062", at=(0, 0.5, 14), color="Trans-Yellow", id="lantern")
    part.place("4073", at=(0, 0.5, 17), color=FRAME)
    part.place("98138", at=(0, 0.5, 18), color=GOLD)


def bench(part: ComponentBuilder) -> None:
    """Build a bench: a seat and a backrest of reddish brown on black legs."""
    for x in (0, 3):
        part.place("3023", at=(x, 0, 0), color=FRAME)
        part.place("3023", at=(x, 0, 1), color=FRAME)
    part.place("3020", at=(0, 0, 2), rotation="R90", color=SLEEPER)
    part.place("2431", at=(0, 0, 3), rotation="R90", color=SLEEPER)
    part.place("3010", at=(0, 1, 3), rotation="R90", color=SLEEPER)
    part.place("2431", at=(0, 1, 6), rotation="R90", color=SLEEPER)


def tub(part: ComponentBuilder, flowers: tuple[str, ...]) -> None:
    """Build a flower tub: a round brick of earth, leaves and four flowers."""
    part.place("3941", at=(0, 0, 0), color=SLEEPER)
    part.place("4032", at=(0, 0, 3), color=GRASS)
    for (x, y), color in zip(((0, 0), (1, 0), (1, 1), (0, 1)), flowers, strict=True):
        part.place("4073", at=(x, y, 4), color=color)


def nameboard(builder: ModelBuilder, x: int, y: int) -> None:
    """Hold the nameboard, a tile, sideways on a brick with side studs on two posts."""
    for post in (x, x + 3):
        for z in range(DECK, DECK + 12, 3):
            builder.place("3062", at=(post, y, z), color=COACH)
    builder.place("30414", at=(x, y, DECK + 12), color="White")
    builder.place(
        "2431",
        at=(x, y - 0.4, DECK + 12.5),
        rotation="-z+x",
        color="Dark Blue",
        id="nameboard",
    )
    builder.place("3710", at=(x, y, DECK + 15), rotation="R90", color="White")


def furniture(builder: ModelBuilder) -> set[Square]:
    """Place lamps, benches, tubs, churns and the nameboard; return their squares."""
    lamp(builder.component("lamp"))
    bench(builder.component("bench"))
    tub(builder.component("tub"), ("Magenta", "Yellow", "Dark Pink", "White"))
    taken: set[Square] = set()
    for x in (7, 17, 46, 53):
        builder.instance("lamp", at=(x, 13, DECK))
        taken |= {(x, 13), (x, 14)}
    for x in (9, 43):
        builder.instance("bench", at=(x, 18, DECK))
        taken |= {(x + i, y) for i in range(4) for y in (18, 19)}
    for x in (5, 14, 48):
        builder.instance("tub", at=(x, 18, DECK))
        taken |= {(x + i, y) for i in range(2) for y in (18, 19)}
    nameboard(builder, 50, 18)
    taken |= {(50, 18), (53, 18)}
    for x, y in ((54, 18), (55, 18), (55, 17)):  # Milk churns waiting for the train
        builder.place("3062", at=(x, y, DECK), color=PAVING)
        builder.place("98138", at=(x, y, DECK + 3), color=PAVING)
        taken.add((x, y))
    return taken


def flagstone(x: int, y: int) -> str:
    """Return the color of a paving square: a white edge, then gray flagstones."""
    if y == 12:
        return "White"
    return BALLAST if noise(x // 2, y // 2) < 0.18 else PAVING


def pave(builder: ModelBuilder, taken: set[Square]) -> None:
    """Tile the platform in flagstones around what stands on it, then the ramp."""
    west, east = PLATFORM
    free = {(x, y) for x in range(west, east) for y in range(12, 20)} - taken
    tile(
        builder,
        free,
        DECK,
        flagstone,
        lambda x, y: y > 12 and (x - west) % 2 == 0 and (y - 13) % 2 == 0,
    )
    for x in range(east, east + DECK - 1):
        builder.place("4162", at=(x, 12, deck_height(x, 12)), color=PAVING)


STATION_WINDOWS = {24, 25, 27, 28, 35, 36, 38, 39}
STATION_DOOR = {31, 32}
BRACKETS = (23, 30, 33, 40)
POSTS = (22, 27, 36, 41)


def station_cell(x: int, y: int, course: int) -> str | None:
    """Return a station wall cell's color: a plinth, windows, lintels or quoins."""
    west, east, south, north = STATION
    front, back, side = y == south, y == north - 1, x in {west, east - 1}
    door = x in STATION_DOOR and course < 5
    if front and (door or (x in BRACKETS and course == 4)):
        return None  # The door and the canopy's brackets
    if course == 0:
        return STONE
    quoin = (
        (side and y in {south, north - 1})
        or (course % 2 == 0 and (front or back) and x in {west + 1, east - 2})
        or (course % 2 == 1 and side and y in {south + 1, north - 2})
    )
    window = (
        (front and x in STATION_WINDOWS)
        or (back and x in {26, 27, 36, 37})
        or (side and y in {24, 25})
    )
    if quoin or (window and course == 4):
        return "White"
    return GLASS if window and course <= 3 else WALL


def station_walls(builder: ModelBuilder) -> None:
    """Lay the station's walls on the platform, with a door and the brackets."""
    for course in range(5):
        walls(builder, STATION, DECK + 3 * course, course, station_cell)
    _, _, south, _ = STATION
    builder.place("2454", at=(31, south, DECK), rotation="R90", color=COACH)
    for x in BRACKETS:  # Inverted slopes, half in the wall, carry the canopy.
        builder.place("3665", at=(x, south - 1, DECK + 12), color=COACH)


def canopy(builder: ModelBuilder) -> None:
    """Build a canopy on posts, with a valance, a clock and a green roof."""
    west, east, _, north = STATION
    for x in POSTS:
        for z in range(DECK, DECK + 15, 3):
            builder.place("3062", at=(x, 16, z), color=COACH)
    deck = {(x, y, 25): COACH for x in range(west, east) for y in range(16, north)}
    fill_above(builder, deck, "canopy")
    for x in range(west, east):  # Round plates hang from the edge of the canopy.
        if x not in POSTS and x not in STATION_DOOR:
            builder.place("4073", at=(x, 16, 24), color="White")
    for x in STATION_DOOR:  # The clock: a jumper held sideways, a round tile on it
        builder.place("47905", at=(x, 16, 22), color="White")
    builder.place("87580", at=(31, 15.6, 20), rotation="+x+z", color=GOLD)
    builder.place(
        "98138", at=(31.5, 15.2, 21.25), rotation="+x+z", color="White", id="clock"
    )
    walls(builder, STATION, 26, 5, station_cell)
    for x in range(west, east, 4):
        builder.place("3297", at=(x, 17, 26), color=COACH)  # Slope 33 3 x 4
    for x in range(west, east, 2):
        builder.place("85984", at=(x, 16, 26), color="White")


def slopes(builder: ModelBuilder, start: Point, end: int, rotation: str) -> None:
    """Lay a row of Slope 45 2 x N along x, from start to the x of end."""
    x, y, z = start
    for size in split(list(SLOPES), round(end - x)):
        builder.place(SLOPES[size], at=(x, y, z), rotation=rotation, color=ROOF)
        x += size


def station_roof(builder: ModelBuilder) -> None:
    """Build a red roof: rows of slopes over a tan attic, which shows as the gables."""
    west, east, _, _ = STATION
    eaves = {(x, y, 29): ROOF for x in range(west - 1, east + 1) for y in range(19, 31)}
    fill_above(builder, eaves, "eaves")
    front, back, z = 19, 31, 30
    attic: Voxels = {}
    while True:
        slopes(builder, (west - 1, front, z), east + 1, "R0")
        slopes(builder, (west - 1, back - 2, z), east + 1, "R180")
        if back - front == 4:
            break
        for x in range(west, east):
            for y in range(front + 2, back - 2):
                for layer in range(z, z + 3):
                    attic[x, y, layer] = WALL
        front, back, z = front + 2, back - 2, z + 3
    windows = {
        (x, y, layer)
        for x in (west, east - 1)
        for y in (24, 25)
        for layer in (30, 31, 32)
    }
    fill_above(builder, {key: attic[key] for key in attic.keys() - windows}, "attic")
    gable_windows(builder)
    ridge(builder, front + 1, z + 3)


def gable_windows(builder: ModelBuilder) -> None:
    """Set round windows in the gables: jumpers held sideways, a round tile on each."""
    west, east, _, _ = STATION
    for x, out, rotation, facing in (
        (west, -0.4, "R270", "-y+z"),
        (east - 1, 1.0, "R90", "+y+z"),
    ):
        builder.place("11211", at=(x, 24, 30), rotation=rotation, color=WALL)
        builder.place("87580", at=(x + out, 24, 30.5), rotation=facing, color="White")
        glass = x + out + (0.4 if out > 0 else -0.4)
        builder.place("98138", at=(glass, 24.5, 31.75), rotation=facing, color=GLASS)


def ridge(builder: ModelBuilder, y: int, z: int) -> None:
    """Cap the ridge with cheese slopes back to back, around a brick chimney stack."""
    west, east, _, _ = STATION
    stack = east - 5
    for x in range(west - 1, east + 1):
        if x not in {stack, stack + 1}:
            builder.place("54200", at=(x, y, z), color=ROOF)
            builder.place("54200", at=(x, y + 1, z), rotation="R180", color=ROOF)
    for level in (z, z + 3):
        builder.place("3003", at=(stack, y, level), color="Dark Orange")
    builder.place("3022", at=(stack, y, z + 6), color=BALLAST)
    builder.place("3062", at=(stack, y, z + 7), color="Dark Orange")
    builder.place("3062", at=(stack + 1, y + 1, z + 7), color="Dark Orange")


def tree(builder: ModelBuilder, x: int, y: int, trunk: int, radius: float) -> None:
    """Grow a tree: a trunk of round bricks under a lumpy crown of leaves."""
    for z in range(1, 1 + 3 * trunk, 3):
        builder.place("3941", at=(x, y, z), color=SLEEPER)
    top = 1 + 3 * trunk
    center_x, center_y, center_z = x + 1, y + 1, top + 2.5 * radius
    lumps = (  # Offsets and radii, as fractions of the crown's radius
        (-0.5, 0.4, 1.0, 0.7, "Green"),
        (0.5, -0.3, 0.6, 0.7, "Green"),
        (0.1, -0.5, 1.6, 0.5, "Lime"),
    )
    crown: list[Sphere] = [(center_x, center_y, center_z, radius, "Dark Green")]
    crown += [
        (
            center_x + east * radius,
            center_y + north * radius,
            center_z + up * radius,
            size * radius,
            color,
        )
        for east, north, up, size, color in lumps
    ]
    fill_above(builder, ball(crown, top), f"tree{x}", prune=True)


def bush(builder: ModelBuilder, x: int, y: int, radius: float, color: str) -> None:
    """Grow a bush: a low ball of leaves on the grass, with a few flowers on top."""
    voxels = ball([(x + 0.5, y + 0.5, 1 + 1.2 * radius, radius, color)], 1)
    fill_above(builder, voxels, f"bush{x}.{y}", prune=True)
    top = max(z for _, _, z in voxels)
    crown = sorted((column, row) for column, row, z in voxels if z == top)
    for index, (column, row) in enumerate(crown[:: max(1, len(crown) // 3)]):
        flower = FLOWERS[(x + y + index) % len(FLOWERS)]
        builder.place("4073", at=(column, row, top + 1), color=flower)


def tower_cell(x: int, y: int, course: int) -> str | None:
    """Return a cell's color in the water tower's base: brick, an arch per face."""
    west, south = TOWER
    along = x - west if y in {south, south + 5} else y - south
    if (course < 2 and along in {2, 3}) or (course == 2 and 1 <= along <= 4):
        return None  # The opening, and the arch above it
    return "Dark Orange"


def tank(builder: ModelBuilder) -> None:
    """Fill a round wooden tank with iron hoops under a conical roof, and a spout."""
    west, south = TOWER
    center_x, center_y = west + 3, south + 3
    voxels: Voxels = {}
    for x in range(west - 1, west + 7):
        for y in range(south - 1, south + 7):
            distance = hypot(x + 0.5 - center_x, y + 0.5 - center_y)
            for z in range(14, 26):
                if distance <= 4:
                    voxels[x, y, z] = FRAME if z in {16, 22} else SLEEPER
            for z, radius in enumerate((4.6, 4.0, 3.4, 2.8, 2.2, 1.6, 1.0), start=26):
                if distance <= radius:
                    voxels[x, y, z] = BALLAST
    for y in range(south - 4, south):  # The spout reaches out over the track.
        voxels[center_x, y, 19] = BALLAST
    fill_above(builder, voxels, "tank")
    builder.place("3062", at=(center_x, south - 4, 16), color=FRAME, id="spout")
    builder.place("87580", at=(center_x - 1, center_y - 1, 33), color=BALLAST)
    builder.place("4073", at=(center_x - 0.5, center_y - 0.5, 34), color=GOLD)


def water_tower(builder: ModelBuilder) -> None:
    """Build a water tower: a base opened by arches, under a tank on a plate 8 x 8."""
    west, south = TOWER
    box = (west, west + 6, south, south + 6)
    for course in range(4):
        walls(builder, box, 1 + 3 * course, course, tower_cell)
    for y in (south, south + 5):
        builder.place("3659", at=(west + 1, y, 7), rotation="R90", color="Dark Orange")
    for x in (west, west + 5):
        builder.place("3659", at=(x, south + 1, 7), color="Dark Orange")
    builder.place("41539", at=(west - 1, south - 1, 13), color=BALLAST)
    tank(builder)


def signal(builder: ModelBuilder, x: int, y: int) -> None:
    """Build a semaphore signal: a white post, its red arm held on a side stud."""
    for z in range(1, 25, 3):
        builder.place("3062", at=(x, y, z), color="White")
    builder.place("87087", at=(x, y, 25), color="White")
    builder.place("3062", at=(x, y, 28), color="White")
    builder.place("4073", at=(x, y, 31), color=FRAME)
    builder.place("98138", at=(x, y, 32), color=FRAME)
    builder.place("3710", at=(x - 3, y - 0.4, 25.5), rotation="-z+x", color=LIVERY)
    builder.place(
        "3070", at=(x - 2, y - 0.8, 25.5), rotation="+x+z", color="White", id="arm"
    )


def path(builder: ModelBuilder) -> None:
    """Tile a path from the foot of the ramp to the back of the ground."""
    tile(
        builder,
        {(x, y) for x in range(65, 69) for y in range(14, DEPTH)},
        1,
        lambda x, y: CREAM if noise(x // 2, y // 2, 7) < 0.3 else STONE,
        lambda x, y: x % 2 == 0 and y % 2 == 0,
    )


def fence(builder: ModelBuilder, west: int, east: int) -> None:
    """Build a white fence along the back: posts every two studs under a rail."""
    for x in range(west, east, 2):
        builder.place("3005", at=(x, DEPTH - 1, 1), color="White")
    line(builder, TILES, "White", (west, DEPTH - 1, 4), (east - 1, DEPTH - 1))


def flowers(builder: ModelBuilder) -> None:
    """Scatter flowers, round plates 1 x 1, over the grass that nothing stands on."""
    filled = model_voxels(builder.build())
    west, south = TOWER
    for x in range(LENGTH):
        for y in range(DEPTH):
            grass = (y < 2 or y >= 14) and deck_height(x, y) == 0
            inside = west < x < west + 5 and south < y < south + 5
            free = grass and not inside and (x, y, 1) not in filled
            if free and noise(x, y, 3) < 0.07:
                color = FLOWERS[int(noise(x, y, 5) * len(FLOWERS))]
                builder.place("4073", at=(x, y, 1), color=color)


def scenery(builder: ModelBuilder) -> None:
    """Add the water tower, a signal, a path, a fence, trees, bushes and flowers."""
    water_tower(builder)
    signal(builder, 96, 1)
    path(builder)
    fence(builder, 0, 64)
    fence(builder, 70, LENGTH)
    tree(builder, 4, 25, 4, 3.6)
    tree(builder, 93, 27, 5, 3.5)
    for x, y, radius, color in (
        (10, 25, 2.2, "Green"),
        (16, 28, 1.8, "Dark Green"),
        (46, 24, 2.0, "Dark Green"),
        (52, 28, 2.4, "Green"),
        (84, 28, 2.0, "Green"),
    ):
        bush(builder, x, y, radius, color)
    flowers(builder)


def build() -> ModelBuilder:
    """Build the track, the train, the platform, the station and the scenery."""
    builder = ModelBuilder("steam-train")
    ground(builder)
    track(builder)
    carriage(builder.component("carriage"))
    for index, x in enumerate(CARRIAGE_XS):
        # The door handles stand 0.4 studs out from the carriage's south side.
        builder.instance("carriage", at=(x, 4.6, 3), id=f"carriage{index + 1}")
    tender(builder)
    locomotive(builder)
    pave(builder, furniture(builder) | {(x, 16) for x in POSTS})
    station_walls(builder)
    canopy(builder)
    station_roof(builder)
    scenery(builder)
    return builder
