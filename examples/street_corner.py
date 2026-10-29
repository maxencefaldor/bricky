# Copyright 2026 Maxence Faldor
"""A European street corner: four townhouses, the corner one a café with a turret.

- A Baseplate 48 x 48 holds two roads of tiles with zebra crossings and two cars,
  sidewalks two plates high behind a curb, and a lawn behind the houses. The
  houses stand three and four floors tall, and the turret's spike 97 plates up.
- The walls, gables, turret, onion dome, chimneys and trees are voxels filled with
  bricks and plates (``builder.fill``): colored walls with white bands and quoins,
  a crow-stepped gable, a neck gable, and canopies in clumps of three greens.
- Windows, doors, shop windows, signs, awnings and dormers are components placed
  76 times; each one carves its opening out of the voxels. Tables, lamps, planters
  and shop counters are components too.
- Tiles held upright on bricks with side studs make shutters, signs and wheels.
  Inverted slopes carry the café's cornice, and arches top windows and the gate.
- Roofs are courses of Slope 45 over a core of bricks, stepping in one stud every
  brick; Slope 75 make the mansard, and curved slopes round off the neck gable.
- Jumpers center the lamp posts, and the dome's golden spike, half a stud off the
  grid.

Run: ``uv run bricky build examples/street_corner.py``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, degrees, hypot, pi, sin, sqrt

from bricky import ModelBuilder

BASE = 0.5  # the top of the baseplate, in plates
SIZE = 48  # the baseplate, in studs
ROAD, WALK = 7, 7  # the widths of the roads and the sidewalks
FRONT = ROAD + WALK  # the row of the south fronts' walls
EAST = SIZE - ROAD - WALK  # the east fronts' walls fill the column EAST - 1
CURB_X = EAST + WALK - 1  # the curb's column on the east sidewalk
STREET = 2  # the local z of the sidewalk's top and of the shop floors
SHOP_TOP = 14  # the ground floors end, and the upper floors start, at this z
STORY = 12  # plates per upper floor

GLASS = "Trans-Light Blue"
SHOP_GLASS = "Trans-Clear"
TRIM = "White"
SLATE = "Dark Bluish Gray"
TILES = "Reddish Brown"
PAVING = "Light Bluish Gray"
LAWN = "Green"
COPPER = "Sand Green"
CAFE_GREEN = "Dark Green"

type Voxel = tuple[int, int, int]
type Square = tuple[int, int]
type Point = tuple[float, float, float]

TILE_SIZES = {
    (2, 6): "69729",
    (2, 4): "87079",
    (1, 8): "4162",
    (1, 6): "6636",
    (2, 3): "26603",
    (2, 2): "3068",
    (1, 4): "2431",
    (1, 3): "63864",
    (1, 2): "3069",
    (1, 1): "3070",
}  # tiles by size, x by y unrotated
SLOPES = {4: "3037", 2: "3039", 1: "3040"}  # Slope 45 2 x N by width
FALLS = {"-y": "R0", "+y": "R180", "-x": "R270", "+x": "R90"}


@dataclass(slots=True)
class Site:
    """The model under construction, the voxels its fill covers, and the free studs.

    ``bare`` holds the squares of sidewalk and road that keep their studs, for the
    furniture and the cars to stand on; ``soil`` holds the tree pit's squares.
    """

    builder: ModelBuilder
    voxels: dict[Voxel, str] = field(default_factory=dict)
    bare: set[Square] = field(default_factory=set)
    soil: set[Square] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class Front:
    """A wall one stud thick, seen from outside, that faces south, east, north or west.

    A south or north front runs along x in the wall row y = ``plane``; an east or west
    front runs along y in the wall column x = ``plane``. Components face -y, and a
    front rotates them to face its way.
    """

    facing: str
    plane: int

    @property
    def rotation(self) -> str:
        """Return the rotation that points a component's -y face this front's way."""
        return {"south": "R0", "east": "R90", "north": "R180", "west": "R270"}[
            self.facing
        ]

    def square(self, along: int, out: int = 0) -> Square:
        """Return the square ``out`` studs in front of the wall at ``along``."""
        match self.facing:
            case "south":
                return (along, self.plane - out)
            case "north":
                return (along, self.plane + out)
            case "east":
                return (self.plane + out, along)
            case _:
                return (self.plane - out, along)


SOUTH_FRONT = Front("south", FRONT)
EAST_FRONT = Front("east", EAST - 1)


@dataclass(frozen=True, slots=True)
class Fitting:
    """A component made for a front: its size and how far it reaches either side.

    The component faces -y. It spans ``width`` squares along the wall row y = 0 and
    ``height`` plates up from z = 0, and reaches ``out`` studs in front of the wall and
    ``inner`` rows behind it.
    """

    name: str
    width: int
    height: int
    out: float
    inner: int


@dataclass(frozen=True, slots=True)
class House:
    """One townhouse: its footprint, its height, its colors and its windows."""

    x: range
    y: range
    top: int  # the local z of the top of the walls
    wall: str
    shop: str  # the color of the shopfront on the ground floor
    window: Fitting  # the window of the upper floors on the street
    bays: tuple[tuple[Front, int], ...]  # each window's front and first square


@dataclass(frozen=True, slots=True)
class Roof:
    """A pitched roof of Slope 45 courses: its slopes' footprint, base and ridge.

    The ridge runs along x when ``along_x`` holds, else along y. Each course rises
    three plates and steps in one stud from both eaves. A chimney two studs long
    rises from the ridge at each position in ``stacks``.
    """

    x: range
    y: range
    z: int
    color: str
    along_x: bool = False
    stacks: tuple[int, ...] = ()


def put(site: Site, part: str, at: Point, color: str, rotation: str = "R0") -> str:
    """Place a part at a local z, measured from the top of the baseplate."""
    x, y, z = at
    return site.builder.place(part, at=(x, y, BASE + z), color=color, rotation=rotation)


def carve(site: Site, squares: list[Square], zs: range) -> None:
    """Remove the voxels over some squares, where placed parts take their place."""
    for x, y in squares:
        for z in zs:
            site.voxels.pop((x, y, z), None)


def block(site: Site, xs: range, ys: range, zs: range, color: str) -> None:
    """Add a box of voxels of one color."""
    for x in xs:
        for y in ys:
            for z in zs:
                site.voxels[x, y, z] = color


def fit(site: Site, fitting: Fitting, front: Front, spot: tuple[int, int]) -> None:
    """Place a fitting in a front at (along, z), carving its squares of the wall."""
    along, z = spot
    squares = [
        front.square(along + i, -row)
        for i in range(fitting.width)
        for row in range(fitting.inner + 1)
    ]
    carve(site, squares, range(z, z + fitting.height))
    match front.facing:
        case "south":
            corner = (along, front.plane - fitting.out)
        case "north":
            corner = (along, front.plane - fitting.inner)
        case "east":
            corner = (front.plane - fitting.inner, along)
        case _:
            corner = (front.plane - fitting.out, along)
    site.builder.instance(fitting.name, at=(*corner, BASE + z), rotation=front.rotation)


def tile(site: Site, squares: set[Square], z: float, color: str) -> None:
    """Cover a set of squares with tiles, largest first, row by row."""
    covered: set[Square] = set()
    for x, y in sorted(squares, key=lambda square: (square[1], square[0])):
        if (x, y) in covered:
            continue
        for (width, depth), part in TILE_SIZES.items():
            placed = False
            for size_x, size_y, rotation in (
                (width, depth, "R0"),
                (depth, width, "R90"),
            ):
                cells = {(x + i, y + j) for i in range(size_x) for j in range(size_y)}
                if cells <= squares and not cells & covered:
                    put(site, part, (x, y, z), color, rotation)
                    covered |= cells
                    placed = True
                    break
            if placed:
                break


# Components: windows, shopfronts and street furniture.


GERANIUMS = Fitting("window-geraniums", 4, 8, 1, 0)
MARIGOLDS = Fitting("window-marigolds", 4, 8, 1, 0)
SHUTTER_WINDOW = Fitting("window-shutters", 4, 8, 0.4, 1)
ARCHED_WINDOW = Fitting("window-arched", 4, 10, 0, 1)
FRAMED_WINDOW = Fitting("window-framed", 4, 8, 0, 1)
ATTIC_WINDOW = Fitting("window-attic", 4, 10, 0, 0)
DOOR = Fitting("door", 2, 9, 0, 0)
AWNING = Fitting("awning", 4, 1, 3, 0)
DORMER = Fitting("dormer", 2, 10, 0, 1)


def display(shop: str) -> Fitting:
    """Return the shop window of a shopfront color."""
    return Fitting(f"display-{shop}", 4, 9, 0, 0)


def sign(shop: str) -> Fitting:
    """Return the sign of a shopfront color."""
    return Fitting(f"sign-{shop}", 4, 3, 0.4, 0)


def box_window(builder: ModelBuilder, name: str, flowers: tuple[str, ...]) -> None:
    """Define a window with a sill that stands out and holds a box of flowers."""
    window = builder.component(name)
    window.place("3020", at=(0, -1, 0), rotation="R90", color=TRIM)
    for x in (0, 3):
        for z in (1, 4):
            window.place("3005", at=(x, 0, z), color=TRIM)
    for z in (1, 4):
        window.place("3004", at=(1, 0, z), rotation="R90", color=GLASS)
    window.place("3710", at=(0, 0, 7), rotation="R90", color=TRIM)
    window.place("3710", at=(0, -1, 1), rotation="R90", color=CAFE_GREEN)
    for x, color in enumerate(flowers):
        window.place("4073", at=(x, -1, 2), color=color)


def shutter_window(builder: ModelBuilder, frame: str, shutter: str) -> None:
    """Define a window set back one stud, between shutters held on side studs."""
    window = builder.component(SHUTTER_WINDOW.name)
    window.place("3020", at=(0, 0, 0), rotation="R90", color=TRIM)
    window.place("3069", at=(1, 0, 1), rotation="R90", color=TRIM)
    for x in (0, 3):
        window.place("87087", at=(x, 0, 1), color=frame)
        window.place("3005", at=(x, 0, 4), color=frame)
        window.place("3069", at=(x, -0.4, 1.5), rotation="+x+z", color=shutter)
    for z in (1, 4):
        window.place("3004", at=(1, 1, z), rotation="R90", color=GLASS)
    window.place("3020", at=(0, 0, 7), rotation="R90", color=TRIM)


def arched_window(builder: ModelBuilder, frame: str) -> None:
    """Define a window set back one stud under an arch."""
    window = builder.component(ARCHED_WINDOW.name)
    window.place("3020", at=(0, 0, 0), rotation="R90", color=TRIM)
    window.place("3069", at=(1, 0, 1), rotation="R90", color=TRIM)
    for x in (0, 3):
        for z in (1, 4):
            window.place("3005", at=(x, 0, z), color=frame)
    for z in (1, 4, 7):
        window.place("3004", at=(1, 1, z), rotation="R90", color=GLASS)
    window.place("3659", at=(0, 0, 7), rotation="R90", color=frame)


def attic_window(builder: ModelBuilder, frame: str) -> None:
    """Define a window under an arch, flush with the wall, for a gable."""
    window = builder.component(ATTIC_WINDOW.name)
    window.place("3710", at=(0, 0, 0), rotation="R90", color=TRIM)
    for x in (0, 3):
        for z in (1, 4):
            window.place("3005", at=(x, 0, z), color=frame)
    for z in (1, 4):
        window.place("3004", at=(1, 0, z), rotation="R90", color=GLASS)
    window.place("3659", at=(0, 0, 7), rotation="R90", color=frame)


def framed_window(builder: ModelBuilder, frame: str) -> None:
    """Define a window set back one stud in a plain frame."""
    window = builder.component(FRAMED_WINDOW.name)
    window.place("3020", at=(0, 0, 0), rotation="R90", color=TRIM)
    window.place("3069", at=(1, 0, 1), rotation="R90", color=TRIM)
    for x in (0, 3):
        for z in (1, 4):
            window.place("3005", at=(x, 0, z), color=frame)
    for z in (1, 4):
        window.place("3004", at=(1, 1, z), rotation="R90", color=GLASS)
    window.place("3020", at=(0, 0, 7), rotation="R90", color=TRIM)


def dormer(builder: ModelBuilder) -> None:
    """Define a dormer window two studs wide, under a little gable of slopes."""
    window = builder.component(DORMER.name)
    window.place("3022", at=(0, 0, 0), color=TRIM)
    for z in (1, 4):
        window.place("3004", at=(0, 0, z), rotation="R90", color=GLASS)
        window.place("3004", at=(0, 1, z), rotation="R90", color=SLATE)
    window.place("3022", at=(0, 0, 7), color=TRIM)
    window.place("85984", at=(0, 0, 8), rotation="R270", color=SLATE)
    window.place("85984", at=(1, 0, 8), rotation="R90", color=SLATE)


def shop_parts(builder: ModelBuilder, shops: dict[str, str]) -> None:
    """Define the door and the awning, and a shop window and sign per shopfront.

    ``shops`` maps each shopfront color to the color of its sign.
    """
    door = builder.component(DOOR.name)
    door.place("3004", at=(0, 0, 0), rotation="R90", color=TILES)
    door.place("3004", at=(0, 0, 3), rotation="R90", color=SHOP_GLASS)
    door.place("3004", at=(0, 0, 6), rotation="R90", color=TILES)
    awning = builder.component(AWNING.name)
    awning.place("3031", at=(0, -3, 0), color=CAFE_GREEN)
    for x in range(4):
        awning.place("4286", at=(x, -3, 1), color="Red" if x % 2 == 0 else TRIM)
    for shop, board in shops.items():
        window = builder.component(display(shop).name)
        window.place("3010", at=(0, 0, 0), rotation="R90", color=shop)
        for z in (3, 6):
            window.place("3010", at=(0, 0, z), rotation="R90", color=SHOP_GLASS)
        holder = "Black" if shop == "Dark Blue" else shop
        plate = builder.component(sign(shop).name)
        plate.place("30414", at=(0, 0, 0), color=holder)
        plate.place("2431", at=(0, -0.4, 0.5), rotation="-z+x", color=board)


def shelf(builder: ModelBuilder, name: str, part: str, goods: tuple[str, ...]) -> None:
    """Define a counter four studs long that shows a row of goods behind a shop window.

    The counter stands on the baseplate inside the shop, one stud behind the glass.
    """
    counter = builder.component(name)
    for z in (0, 3):
        counter.place("3010", at=(0, 0, z), rotation="R90", color=TILES)
    counter.place("3710", at=(0, 0, 6), rotation="R90", color="Tan")
    for x, color in enumerate(goods):
        counter.place(part, at=(x, 0, 7), color=color)


def furniture(builder: ModelBuilder) -> None:
    """Define the café table, the stool, the bench, the lamp post and the flower pot."""
    table = builder.component("table")
    table.place("3062", at=(0, 0, 0), color="Black")
    table.place("14769", at=(0, 0, 3), color=TRIM)
    stool = builder.component("stool")
    stool.place("4073", at=(0, 0, 0), color="Black")
    stool.place("3024", at=(0, 0, 1), color="Red")
    bench = builder.component("bench")
    for x in (0, 3):
        for z in (0, 1):
            bench.place("3023", at=(x, 0, z), color="Black")
    bench.place("3020", at=(0, 0, 2), rotation="R90", color=TILES)
    bench.place("3010", at=(0, 1, 3), rotation="R90", color=TILES)
    lamp = builder.component("lamp")
    lamp.place("15573", at=(0, 0, 0), color="Black")
    for z in range(1, 16, 3):
        lamp.place("3062", at=(0, 0.5, z), color="Black")
    lamp.place("3623", at=(0, -0.5, 16), color="Black")
    lamp.place("63864", at=(0, -0.5, 17), color="Black")
    for y in (-0.5, 1.5):
        lamp.place("3062", at=(0, y, 13), color="Trans-Yellow")
    planter = builder.component("planter")
    planter.place("3010", at=(0, 0, 0), color=CAFE_GREEN)
    planter.place("3710", at=(0, 0, 3), color="Green")
    for y, color in enumerate(("Red", TRIM, "Red", TRIM)):
        planter.place("4073", at=(0, y, 4), color=color)
    postbox = builder.component("postbox")
    postbox.place("3004", at=(0, 0, 0), color="Yellow")
    postbox.place("3040", at=(0, 0, 3), color="Yellow")
    for name, color in (("pot-red", "Red"), ("pot-pink", "Dark Pink")):
        pot = builder.component(name)
        pot.place("3941", at=(0, 0, 0), color=TILES)
        pot.place("4032", at=(0, 0, 3), color="Green")
        for x, y in ((0, 0), (1, 1)):
            pot.place("4073", at=(x, y, 4), color=color)
        pot.place("4073", at=(1, 0, 4), color="Yellow")


def car(builder: ModelBuilder, name: str, paint: str) -> None:
    """Define a small car, eight studs long, facing +x.

    Bricks with a stud on the side hang under the chassis and hold round tiles
    upright as wheels; a hidden brick under the middle stands on the baseplate.
    """
    body = builder.component(name)
    body.place("3003", at=(3, 1, 0), color="Black")
    body.place("3022", at=(3, 1, 3), color="Black")
    body.place("3035", at=(0, 0, 4), rotation="R90", color="Black")
    for x in (1, 5):
        body.place("87087", at=(x, 0, 1), color="Black")
        body.place("87087", at=(x, 3, 1), rotation="R180", color="Black")
        body.place("14769", at=(x, -0.4, 1.5), rotation="+x+z", color=SLATE)
        body.place("14769", at=(x, 4, 1.5), rotation="-x+z", color=SLATE)
    for y in (0, 2):
        for x in (0, 4):
            body.place("3001", at=(x, y, 5), rotation="R90", color=paint)
        body.place("15068", at=(6, y, 8), rotation="R90", color=paint)
    body.place("3037", at=(4, 0, 8), rotation="R90", color="Trans-Clear")
    body.place("3037", at=(0, 0, 8), rotation="R270", color="Trans-Clear")
    for y in (0, 3):
        body.place("3004", at=(2, y, 8), rotation="R90", color="Trans-Clear")
    body.place("3003", at=(2, 1, 8), color=paint)
    body.place("3031", at=(1, 0, 11), color=paint)
    body.place("87079", at=(1, 0, 12), rotation="R90", color=paint)
    body.place("87079", at=(1, 2, 12), rotation="R90", color=paint)


# The ground: roads, a crossing and sidewalks.


SOUTH_CAR = (3, 2)  # the corner of the car that drives east on the south road
EAST_CAR = (SIZE - 5, 20)  # the corner of the car that drives north on the east road
MANHOLES = ((22, 4), (44, 2))  # round covers, set on the baseplate between tiles


def road(site: Site) -> None:
    """Lay the roads in tiles on the baseplate, with crossings, lane marks and cars.

    The squares under each car's middle keep their studs: a hidden brick stands
    there and holds the car.
    """
    south_crossing = {(x, y) for x in range(EAST + 1, EAST + 6, 2) for y in range(ROAD)}
    east_crossing = {
        (x, y) for x in range(SIZE - ROAD, SIZE, 2) for y in range(ROAD + 1, ROAD + 5)
    }
    dashes = {(x, 3) for x in range(EAST - 2) if x % 6 < 3} | {
        (SIZE - 4, y) for y in range(ROAD + 7, SIZE) if y % 6 < 3
    }
    (south_x, south_y), (east_x, east_y) = SOUTH_CAR, EAST_CAR
    under_cars = {
        (x, y) for x in range(south_x, south_x + 8) for y in range(south_y, south_y + 4)
    } | {(x, y) for x in range(east_x, east_x + 4) for y in range(east_y, east_y + 8)}
    site.bare |= {(south_x + i, south_y + j) for i in (3, 4) for j in (1, 2)}
    site.bare |= {(east_x + i, east_y + j) for i in (1, 2) for j in (3, 4)}
    for x, y in MANHOLES:
        put(site, "14769", (x, y, 0), "Flat Silver")
        site.bare |= {(x + i, y + j) for i in (0, 1) for j in (0, 1)}
    white = south_crossing | east_crossing | dashes - under_cars
    asphalt = {(x, y) for x in range(SIZE) for y in range(ROAD)} | {
        (x, y) for x in range(SIZE - ROAD, SIZE) for y in range(ROAD, SIZE)
    }
    tile(site, asphalt - white - site.bare, 0, SLATE)
    tile(site, white, 0, TRIM)
    # The wheels stand 0.4 studs out from the body, so each car's corner moves out.
    site.builder.instance("car-teal", at=(south_x, south_y - 0.4, BASE), id="teal-car")
    site.builder.instance(
        "car-orange", at=(east_x - 0.4, east_y, BASE), rotation="R90", id="orange-car"
    )


def sidewalk(site: Site) -> None:
    """Lay the sidewalks: plates on the baseplate, then tiles with a curb row."""
    walk = {(x, y) for x in range(EAST + WALK) for y in range(ROAD, FRONT)} | {
        (x, y) for x in range(EAST, EAST + WALK) for y in range(FRONT, SIZE)
    }
    for x, y in walk:
        site.voxels[x, y, 0] = PAVING
    walk -= site.bare
    tile(site, walk & site.soil, 1, "Dark Brown")
    walk -= site.soil
    curb = {(x, y) for x, y in walk if y == ROAD or x == CURB_X}
    tile(site, curb, 1, SLATE)
    tile(site, walk - curb, 1, PAVING)


# The houses.


def wall_color(house: House, x: int, y: int, z: int) -> str:
    """Return the color of a wall voxel: plinth, shopfront, bands, quoins or wall."""
    south = y == FRONT
    east = x == EAST - 1
    street = south or east
    if z < STREET:
        return SLATE
    if street and z < SHOP_TOP:
        return house.shop
    if street and (z - SHOP_TOP) % STORY == 0:
        return TRIM
    corner = (south and x in {house.x.start, house.x.stop - 1}) or (
        east and y in {house.y.start, house.y.stop - 1}
    )
    if corner and (z // 3) % 2 == 0:
        return TRIM
    return house.wall


def shell(site: Site, house: House) -> None:
    """Add the house's four walls and its ceiling to the voxels."""
    for z in range(house.top):
        for x in house.x:
            for y in house.y:
                ring = x in {house.x.start, house.x.stop - 1} or y in {
                    house.y.start,
                    house.y.stop - 1,
                }
                if ring:
                    site.voxels[x, y, z] = wall_color(house, x, y, z)
                elif z == house.top - 1:
                    site.voxels[x, y, z] = house.wall


def windows(site: Site, house: House) -> None:
    """Fit the house's window in every bay of every upper floor."""
    for floor in range(SHOP_TOP, house.top - house.window.height, STORY):
        for front, along in house.bays:
            fit(site, house.window, front, (along, floor + 2))


def rear(site: Site) -> None:
    """Fit plain windows and back doors in the walls that face the courtyard."""
    backs = Front("north", FRONT + 15)
    for front, alongs, floors in (
        (backs, (1, 5), 2),
        (backs, (11, 15), 3),
        (Front("west", 0), (17, 23), 2),
        (Front("north", FRONT + 27), (22, 28), 2),
        (Front("west", 20), (31, 37), 2),
    ):
        for along in alongs:
            for floor in range(floors):
                z = SHOP_TOP + 2 + STORY * floor
                fit(site, FRAMED_WINDOW, front, (along, z))
    for front, along in ((backs, 4), (backs, 14), (Front("west", 20), 35)):
        fit(site, DOOR, front, (along, STREET))


def pitched(site: Site, roof: Roof, house: House) -> None:
    """Lay a pitched roof's courses of slopes over a core of wall-colored voxels."""
    span = roof.x if roof.along_x else roof.y
    low, high = (
        (roof.y.start, roof.y.stop) if roof.along_x else (roof.x.start, roof.x.stop)
    )
    falls = ("-y", "+y") if roof.along_x else ("-x", "+x")
    walls = house.x if roof.along_x else house.y
    core = range(max(span.start, walls.start), min(span.stop, walls.stop))
    z, course = roof.z, 0
    while high - low >= 4:
        for row, fall in ((low, falls[0]), (high - 2, falls[1])):
            slope_row(site, span, (row, z, course), fall, roof.color)
        for a in core:
            for b in range(low + 2, high - 2):
                x, y = (a, b) if roof.along_x else (b, a)
                site.voxels.update(
                    {(x, y, z + layer): house.wall for layer in range(3)}
                )
        low, high, z, course = low + 1, high - 1, z + 3, course + 1
    ridge(site, roof, (low, z))


def ridge(site: Site, roof: Roof, at: tuple[int, int]) -> None:
    """Close a roof's ridge with cheese slopes, and raise its chimneys from it.

    ``at`` gives the first of the ridge's two rows, and its z.
    """
    low, z = at
    falls = ("-y", "+y") if roof.along_x else ("-x", "+x")
    chimneys = {a + i for a in roof.stacks for i in (0, 1)}
    for a in roof.x if roof.along_x else roof.y:
        for row, fall in ((low, falls[0]), (low + 1, falls[1])):
            x, y = (a, row) if roof.along_x else (row, a)
            if a in chimneys:
                site.voxels.update(
                    {(x, y, z + layer): "Dark Red" for layer in range(8)}
                )
                site.voxels[x, y, z + 8] = SLATE
            else:
                put(site, "54200", (x, y, z), roof.color, FALLS[fall])
    for a in roof.stacks:
        corner = (a, low, z + 9) if roof.along_x else (low, a, z + 9)
        put(site, "3062", corner, "Dark Orange")


def slope_row(
    site: Site, span: range, at: tuple[int, int, int], fall: str, color: str
) -> None:
    """Lay Slope 45 2 x N along ``span``, falling toward ``fall``.

    ``at`` gives the row's first square across the span, its z and the course number.
    A single-stud slope goes first, where the walls hold it, and odd courses then
    start with a shorter slope, so joints stagger.
    """
    row, z, course = at
    along_x = fall in {"-y", "+y"}
    widths, room = [], len(span)
    if room % 2 == 1:
        widths.append(1)
        room -= 1
    if course % 2 == 1 and room > 2:
        widths.append(2)
        room -= 2
    widths += [4] * (room // 4) + [2] * (room % 4 // 2)
    start = span.start
    for width in widths:
        corner = (start, row, z) if along_x else (row, start, z)
        put(site, SLOPES[width], corner, color, FALLS[fall])
        start += width


def crow_gables(site: Site, house: House) -> None:
    """Raise crow-stepped gables at both ends of the house, capped with white."""
    west, east, z = house.x.start, house.x.stop, house.top
    while east - west >= 2:
        for y in (house.y.start, house.y.stop - 1):
            block(site, range(west, east), range(y, y + 1), range(z, z + 3), house.wall)
            for x in {west, east - 1}:
                site.voxels[x, y, z + 3] = TRIM
        west, east, z = west + 1, east - 1, z + 3
    fit(site, GERANIUMS, SOUTH_FRONT, (house.x.start + 3, house.top + 1))


def neck_gable(site: Site, house: House) -> None:
    """Raise a neck gable on the front: shoulders, a tall neck and a round top."""
    center = (house.x.start + house.x.stop) // 2
    y, z = FRONT, house.top
    row = range(y, y + 1)
    block(site, house.x, row, range(z, z + 6), house.wall)
    block(site, house.x, row, range(z + 6, z + 7), TRIM)
    neck = range(center - 3, center + 3)
    block(site, neck, row, range(z + 7, z + 19), house.wall)
    for x in (neck.start, neck.stop - 1):
        block(site, range(x, x + 1), row, range(z + 7, z + 19), TRIM)
    block(site, neck, row, range(z + 19, z + 20), TRIM)
    put(site, "11477", (house.x.start, y, z + 7), TRIM, "R270")
    put(site, "11477", (neck.stop, y, z + 7), TRIM, "R90")
    put(site, "11477", (neck.start, y, z + 20), TRIM, "R270")
    put(site, "11477", (neck.stop - 2, y, z + 20), TRIM, "R90")
    block(site, range(center - 1, center + 1), row, range(z + 20, z + 23), TRIM)
    put(site, "54200", (center - 1, y, z + 23), TRIM, "R270")
    put(site, "54200", (center, y, z + 23), TRIM, "R90")
    fit(site, ATTIC_WINDOW, SOUTH_FRONT, (neck.start + 1, z + 8))


# The corner café: cornice, mansard and turret.


TURRET_X, TURRET_Y = EAST - 1, FRONT + 1  # the axis of the turret, in studs
TURRET_OUTER, TURRET_INNER = 4.0, 3.0
CAFE_TOP = SHOP_TOP + 3 * STORY + 2  # the café's walls end under a cornice
MANSARD = CAFE_TOP + 1  # the mansard's base
ROOF_TOP = MANSARD + 9  # the mansard's flat top, and the turret's eaves
SPIRE = 30  # the height of the turret's onion dome, in plates
NECK, BULB = 0.08, 0.38  # where the dome's neck ends, and where its bulb is widest


def from_turret(x: int, y: int) -> float:
    """Return how far the center of a square lies from the turret's axis, in studs."""
    return hypot(x + 0.5 - TURRET_X, y + 0.5 - TURRET_Y)


def turret(site: Site, wall: str) -> None:
    """Add the round corner turret: corbel, ring with windows, eaves and onion dome."""
    for x in range(EAST - 6, EAST + 5):
        for y in range(FRONT - 5, FRONT + 6):
            distance = from_turret(x, y)
            for z in range(SHOP_TOP - 3, ROOF_TOP):
                if z < SHOP_TOP:
                    if distance < 2.2 + 0.8 * (z - SHOP_TOP + 3):
                        site.voxels[x, y, z] = TRIM
                elif distance < TURRET_INNER:
                    site.voxels.pop((x, y, z), None)
                elif distance < TURRET_OUTER:
                    site.voxels[x, y, z] = turret_color(x, y, z, wall)
            if distance < TURRET_OUTER + 0.6:
                site.voxels[x, y, ROOF_TOP] = TRIM
    top = dome(site)
    # A jumper centers the golden spike on the axis, which runs between four studs.
    put(site, "87580", (TURRET_X - 1, TURRET_Y - 1, top), "Pearl Gold")
    for z, part in ((1, "3062"), (4, "4073"), (5, "3062"), (8, "98138")):
        put(site, part, (TURRET_X - 0.5, TURRET_Y - 0.5, top + z), "Pearl Gold")


def dome(site: Site) -> int:
    """Fill the turret's onion dome in copper and return the local z of its top."""
    z = ROOF_TOP + 1
    while True:
        radius = onion((z - ROOF_TOP) / SPIRE)
        for x in range(EAST - 6, EAST + 5):
            for y in range(FRONT - 5, FRONT + 6):
                if from_turret(x, y) < max(radius, 0.8):
                    site.voxels[x, y, z] = COPPER
        z += 1
        if radius < 0.8:
            return z


def onion(rise: float) -> float:
    """Return the radius of the onion dome at a fraction of its height, in studs.

    A neck rises from the turret's eaves and the bulb swells, then the dome narrows
    in a concave curve to a needle.
    """
    if rise < NECK:
        return 3.1
    if rise < BULB:
        return 3.1 + 1.3 * sin((rise - NECK) / (BULB - NECK) * pi / 2)
    left = max(0.0, 1 - (rise - BULB) / (1 - BULB))
    return 4.4 * left * sqrt(left)


def turret_color(x: int, y: int, z: int, wall: str) -> str:
    """Return the color of a voxel in the turret's ring: glass, band or wall."""
    level = (z - SHOP_TOP) % STORY
    if level == 0 or z == CAFE_TOP:
        return TRIM
    angle = degrees(atan2(y + 0.5 - TURRET_Y, x + 0.5 - TURRET_X))
    window = any(abs(angle - facing) < 16 for facing in (-90, -45, 0))
    floor = z < CAFE_TOP and 3 <= level < 10
    attic = MANSARD + 2 <= z < MANSARD + 7
    return GLASS if window and (floor or attic) else wall


def cornice(site: Site, house: House) -> None:
    """Crown the café with a white cornice on inverted-slope brackets."""
    for x in range(house.x.start + 1, EAST - 5, 2):
        carve(site, [(x, FRONT)], range(CAFE_TOP - 3, CAFE_TOP))
        put(site, "3665", (x, FRONT - 1, CAFE_TOP - 3), TRIM)
    for y in range(FRONT + 5, house.y.stop, 2):
        carve(site, [(EAST - 1, y)], range(CAFE_TOP - 3, CAFE_TOP))
        put(site, "3665", (EAST - 1, y, CAFE_TOP - 3), TRIM, "R90")
    for x in range(house.x.start, EAST + 1):
        for y in range(FRONT - 1, house.y.stop):
            if from_turret(x, y) >= TURRET_OUTER and (x < EAST or y >= FRONT):
                site.voxels[x, y, CAFE_TOP] = TRIM


def mansard(site: Site, house: House) -> set[Square]:
    """Lay a mansard of Slope 75 with dormers, and return the squares it leaves flat.

    The slopes run along the two fronts with dormers between them, and along the
    walls the café shares with its neighbors, whose roofs stay lower.
    """
    flat: set[Square] = set()
    for front, alongs, dormers in (
        (SOUTH_FRONT, range(house.x.start, EAST - 5), (22, 26)),
        (EAST_FRONT, range(FRONT + 5, house.y.stop), (20, 26)),
    ):
        for along in alongs:
            if along in dormers:
                fit(site, DORMER, front, (along, MANSARD))
            elif along - 1 not in dormers:
                # A slope's corner is the lower of its two squares, outer and inner.
                x, y = min(front.square(along), front.square(along, -1))
                put(site, "4460b", (x, y, MANSARD), SLATE, front.rotation)
                flat.add(front.square(along, -1))
    north = house.y.stop - 2
    for x in range(house.x.start, EAST - 2):
        put(site, "4460b", (x, north, MANSARD), SLATE, "R180")
        flat.add((x, north))
    for y in range(FRONT + 2, north):
        put(site, "4460b", (house.x.start, y, MANSARD), SLATE, "R270")
        flat.add((house.x.start + 1, y))
    return flat


def zinc_roof(site: Site, house: House, flat: set[Square]) -> None:
    """Fill the mansard's core, raise two chimney stacks, and tile the flat top."""
    north = house.y.stop - 2
    for x in range(house.x.start + 2, EAST - 2):
        for y in range(FRONT + 2, north):
            if from_turret(x, y) >= TURRET_OUTER:
                site.voxels.update({(x, y, z): SLATE for z in range(MANSARD, ROOF_TOP)})
                flat.add((x, y))
    stacks = {(x, y) for x in range(23, 25) for y in range(21, 25)} | {
        (x, y) for x in range(26, 30) for y in range(25, 27)
    }
    for x, y in stacks:
        site.voxels.update(
            {(x, y, z): house.wall for z in range(ROOF_TOP, ROOF_TOP + 9)}
        )
        site.voxels[x, y, ROOF_TOP + 9] = TRIM
    for x, y in ((23, 21), (23, 23), (26, 25), (28, 25)):
        for i in (0, 1):
            put(site, "3062", (x + i, y + i, ROOF_TOP + 10), "Dark Orange")
    eaves = {square for square in flat if from_turret(*square) < TURRET_OUTER + 0.6}
    tile(site, flat - stacks - eaves, ROOF_TOP, PAVING)


# Shopfronts.


def shopfronts(site: Site, houses: tuple[House, ...]) -> None:
    """Fit the shop windows, doors, signs and the café's awnings."""
    flower, bakery, cafe, bookshop = houses
    for front, along, fitting in (
        (SOUTH_FRONT, 1, display(flower.shop)),
        (SOUTH_FRONT, 6, DOOR),
        (SOUTH_FRONT, 11, DOOR),
        (SOUTH_FRONT, 14, display(bakery.shop)),
        (SOUTH_FRONT, 21, display(cafe.shop)),
        (SOUTH_FRONT, 26, DOOR),
        (EAST_FRONT, 19, display(cafe.shop)),
        (EAST_FRONT, 25, display(cafe.shop)),
        (EAST_FRONT, 31, display(bookshop.shop)),
        (EAST_FRONT, 35, DOOR),
        (EAST_FRONT, 37, display(bookshop.shop)),
    ):
        fit(site, fitting, front, (along, STREET))
    for front, along, shop in (
        (SOUTH_FRONT, 1, flower.shop),
        (SOUTH_FRONT, 14, bakery.shop),
        (EAST_FRONT, 34, bookshop.shop),
    ):
        fit(site, sign(shop), front, (along, STREET + 9))
    for front, along in (
        (SOUTH_FRONT, 21),
        (SOUTH_FRONT, 25),
        (EAST_FRONT, 19),
        (EAST_FRONT, 25),
    ):
        fit(site, AWNING, front, (along, STREET + 9))
    for front, along, counter in (
        (SOUTH_FRONT, 1, "flowers"),
        (SOUTH_FRONT, 14, "bread"),
        (SOUTH_FRONT, 21, "cakes"),
        (EAST_FRONT, 19, "cakes"),
        (EAST_FRONT, 25, "cakes"),
        (EAST_FRONT, 31, "books"),
        (EAST_FRONT, 37, "books"),
    ):
        x, y = front.square(along, -1)
        site.builder.instance(counter, at=(x, y, BASE), rotation=front.rotation)
    # Street-name plates: blue tiles held upright on studs on the sides of bricks.
    carve(site, [(EAST - 3, FRONT), (EAST - 1, FRONT + 2)], range(8, 11))
    put(site, "87087", (EAST - 3, FRONT, 8), CAFE_GREEN)
    put(site, "3069", (EAST - 3, FRONT - 0.4, 8.5), "Dark Blue", "-z+x")
    put(site, "87087", (EAST - 1, FRONT + 2, 8), CAFE_GREEN, "R90")
    put(site, "3069", (EAST, FRONT + 2, 8.5), "Dark Blue", "-z+y")


# Street life and the garden.


def stand(site: Site, name: str, at: tuple[float, float], squares: set[Square]) -> None:
    """Stand an instance on the sidewalk, keeping the studs under it bare."""
    site.builder.instance(name, at=(*at, BASE + 1))
    site.bare |= squares


def street_life(site: Site) -> None:
    """Set café tables, lamps, a bench, flower pots and bollards on the sidewalks."""
    for x, y in ((22, 9), (27, 9), (36, 20), (36, 26)):
        stand(site, "table", (x, y), {(x, y)})
        for i, j in ((-1, 1), (2, 0)):
            stand(site, "stool", (x + i, y + j), {(x + i, y + j)})
    for x, y in ((CURB_X - 1, ROAD + 1), (12, ROAD + 1), (CURB_X - 1, 33)):
        stand(site, "lamp", (x, y - 0.5), {(x, y), (x, y + 1)})
    site.builder.instance("bench", at=(EAST + 1, 37, BASE + 1), rotation="R90")
    site.bare |= {(x, y) for x in (EAST + 1, EAST + 2) for y in (37, 40)}
    for x, name in ((1, "pot-red"), (3, "pot-pink"), (8, "pot-red"), (16, "pot-pink")):
        squares = {(x + i, FRONT - 2 + j) for i in (0, 1) for j in (0, 1)}
        stand(site, name, (x, FRONT - 2), squares)
    for x, y in ((EAST, ROAD + 1), (EAST + 2, ROAD + 1), (CURB_X - 1, ROAD + 3)):
        put(site, "3062", (x, y, 1), SLATE)
        put(site, "98138", (x, y, 4), SLATE)
        site.bare.add((x, y))
    for x, y, rotation in (
        (20, ROAD + 1, "R90"),
        (25, ROAD + 1, "R90"),
        (39, 22, "R0"),
    ):
        site.builder.instance("planter", at=(x, y, BASE + 1), rotation=rotation)
        cells = (
            [(x + i, y) for i in range(4)]
            if rotation == "R90"
            else [(x, y + j) for j in range(4)]
        )
        site.bare |= set(cells)
    stand(site, "postbox", (EAST, FRONT - 3), {(EAST, FRONT - 3), (EAST, FRONT - 2)})
    plant(site, Tree(EAST + 3, 44, 1, 3.3))
    site.bare |= {(x, y) for x in (EAST + 3, EAST + 4) for y in (44, 45)}
    site.soil |= {(x, y) for x in range(EAST + 2, EAST + 6) for y in range(43, 47)}


@dataclass(frozen=True, slots=True)
class Tree:
    """A tree: a trunk of round bricks two studs across, under a round canopy.

    The trunk's corner is (``x``, ``y``) and it stands at the local z ``base``.
    """

    x: int
    y: int
    base: int
    radius: float


def plant(site: Site, tree: Tree) -> None:
    """Stand a trunk of round bricks and fill a lumpy canopy of leaves above it."""
    for z in range(tree.base, tree.base + 15, 3):
        put(site, "3941", (tree.x, tree.y, z), TILES)
    low = tree.base + 15
    middle, rise = low + 10, 10
    reach = int(tree.radius + 2)
    for x in range(tree.x + 1 - reach, tree.x + 1 + reach):
        for y in range(tree.y + 1 - reach, tree.y + 1 + reach):
            east, north = x + 0.5 - tree.x - 1, y + 0.5 - tree.y - 1
            angle = atan2(north, east)
            wobble = 1 + 0.14 * sin(3 * angle) + 0.08 * sin(5 * angle + 1)
            spread = hypot(east, north) / (tree.radius * wobble)
            for z in range(low, low + 2 * rise):
                height = (z - middle) / rise
                trunk = z < low + 3 and abs(east) < 1 and abs(north) < 1
                if spread * spread + height * height <= 1 or trunk:
                    site.voxels[x, y, z] = leaf(x, y, z - rise - low)


def leaf(x: int, y: int, z: int) -> str:
    """Return a leaf color, ``z`` plates above the canopy's middle.

    The lower half widens upward, so each layer takes one color and plates reach
    back to hold its rim. The upper half narrows, so every leaf rests on one below,
    and it takes clumps of dark green and lime.
    """
    if z < 0:
        return "Dark Green" if z < -5 else "Green"
    clump = (x // 2 * 7 + y // 2 * 13 + z // 3 * 5) % 6
    if clump == 0:
        return "Dark Green"
    return "Lime" if clump in {1, 2} and z > 2 else "Green"


def garden(site: Site) -> None:
    """Lay the courtyard's lawn and path, a garden wall with a gate, and two trees."""
    for x in range(EAST - 1):
        for y in range(FRONT + 16, SIZE):
            if x < 20 or y >= FRONT + 28:
                site.voxels[x, y, 0] = LAWN
    path = {(x, y) for x in range(20) for y in (30, 31)} | {
        (x, y) for x in (18, 19) for y in range(32, 38)
    }
    tile(site, path, 1, "Tan")
    for y in range(FRONT + 28, SIZE):
        for z in range(12):
            gate = 44 <= y < 46 and z >= 1
            arch = 43 <= y < 47 and z >= 9
            if not gate and not arch:
                site.voxels[EAST - 1, y, z] = SLATE if z < STREET else "Dark Red"
        site.voxels[EAST - 1, y, 12] = TRIM
    put(site, "3659", (EAST - 1, 43, 9), "Dark Red")
    plant(site, Tree(27, 44, 1, 3.0))
    plant(site, Tree(6, 40, 1, 4.0))
    site.builder.instance("bench", at=(9, 34, BASE + 1))
    for x, y, name in ((2, 34, "pot-red"), (15, 42, "pot-pink"), (12, 44, "pot-red")):
        site.builder.instance(name, at=(x, y, BASE + 1))


HOUSES = (
    House(
        range(10),
        range(FRONT, FRONT + 16),
        SHOP_TOP + 2 * STORY,
        "Dark Red",
        CAFE_GREEN,
        GERANIUMS,
        ((SOUTH_FRONT, 1), (SOUTH_FRONT, 5)),
    ),
    House(
        range(10, 20),
        range(FRONT, FRONT + 16),
        SHOP_TOP + 3 * STORY,
        "Sand Green",
        TILES,
        ARCHED_WINDOW,
        ((SOUTH_FRONT, 11), (SOUTH_FRONT, 15)),
    ),
    House(
        range(20, EAST),
        range(FRONT, FRONT + 16),
        CAFE_TOP,
        "Bright Light Yellow",
        CAFE_GREEN,
        SHUTTER_WINDOW,
        (
            (SOUTH_FRONT, 21),
            (SOUTH_FRONT, 25),
            (EAST_FRONT, 19),
            (EAST_FRONT, 25),
        ),
    ),
    House(
        range(20, EAST),
        range(FRONT + 16, FRONT + 28),
        SHOP_TOP + 2 * STORY,
        "Medium Azure",
        "Dark Blue",
        MARIGOLDS,
        ((EAST_FRONT, 31), (EAST_FRONT, 37)),
    ),
)


def build() -> ModelBuilder:
    """Build the street corner on its baseplate."""
    builder = ModelBuilder("street-corner")
    site = Site(builder)
    builder.place("4186", at=(0, 0, 0), color="Light Bluish Gray", id="baseplate")
    flower, bakery, cafe, bookshop = HOUSES
    box_window(builder, GERANIUMS.name, ("Red", "Dark Pink", "Yellow", "Red"))
    box_window(builder, MARIGOLDS.name, ("Yellow", "Orange", TRIM, "Orange"))
    shutter_window(builder, CAFE_GREEN, CAFE_GREEN)
    arched_window(builder, TRIM)
    framed_window(builder, TRIM)
    attic_window(builder, TRIM)
    dormer(builder)
    shop_parts(
        builder, {CAFE_GREEN: "Bright Light Yellow", TILES: "Tan", "Dark Blue": TRIM}
    )
    furniture(builder)
    for name, part, goods in (
        ("flowers", "3062", ("Red", "Yellow", "Dark Pink", "Orange")),
        ("bread", "4073", ("Medium Nougat", "Dark Orange", "Tan", "Medium Nougat")),
        ("cakes", "4073", ("Dark Pink", TRIM, "Bright Light Yellow", "Dark Pink")),
        ("books", "3005", ("Red", "Blue", "Yellow", "Dark Green")),
    ):
        shelf(builder, name, part, goods)
    car(builder, "car-teal", "Dark Turquoise")
    car(builder, "car-orange", "Orange")
    for house in HOUSES:
        shell(site, house)
    turret(site, cafe.wall)
    for house in HOUSES:
        windows(site, house)
    rear(site)
    shopfronts(site, HOUSES)
    crow_gables(site, flower)
    pitched(
        site,
        Roof(flower.x, range(FRONT + 1, FRONT + 15), flower.top, SLATE, stacks=(25,)),
        flower,
    )
    neck_gable(site, bakery)
    pitched(
        site,
        Roof(bakery.x, range(FRONT + 1, FRONT + 16), bakery.top, TILES, stacks=(26,)),
        bakery,
    )
    pitched(
        site,
        Roof(
            range(20, EAST + 1),
            bookshop.y,
            bookshop.top,
            TILES,
            along_x=True,
            stacks=(23,),
        ),
        bookshop,
    )
    fit(site, MARIGOLDS, EAST_FRONT, (34, bookshop.top + 1))
    cornice(site, cafe)
    zinc_roof(site, cafe, mansard(site, cafe))
    garden(site)
    street_life(site)
    road(site)
    sidewalk(site)
    town = builder.component("town")
    town.fill(site.voxels, id="town")
    low_x = min(x for x, _, _ in site.voxels)
    low_y = min(y for _, y, _ in site.voxels)
    builder.instance("town", at=(low_x, low_y, BASE), id="town")
    print(f"{len(site.voxels):,} voxels")
    return builder
