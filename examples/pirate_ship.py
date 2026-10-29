# Copyright 2026 Maxence Faldor
"""A pirate galleon under full sail on a choppy sea.

- The hull, its castles and the sea are voxels filled with bricks and plates: a hull 45
  studs long rounds into its bow and rises at the stern in two decks, on 66 x 38 studs
  of sea.
- Each gun port is a brick with a stud on its side, holding a cannon built sideways
  from round parts. An anchor built flat hangs sideways on the bow.
- The sails are walls one stud thick, pushed forward by the wind and laid as staggered
  plates under slim yards. Jumpers center the round topmasts on the crow's nests.
- The Jolly Roger and the pennants are walls of plates; the bowsprit climbs in steps
  smoothed by cheese slopes.
- Inverted slopes carry the quarter galleries, arches open the castles' front rails and
  tiles cover the decks. The sea mixes tiles, plates and cheese slopes for whitecaps.

Run: ``uv run bricky build examples/pirate_ship.py``
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import ceil, cos, floor, pi, sin

from bricky import Catalog, ComponentBuilder, ModelBuilder

type Scope = ModelBuilder | ComponentBuilder
type Square = tuple[int, int]
type Voxel = tuple[int, int, int]
type Voxels = dict[Voxel, str]

PLANKING, WALES, GOLD = "Reddish Brown", "Dark Brown", "Pearl Gold"
GLASS, DECK, CANVAS = "Trans-Yellow", "Tan", "White"
SPAR, YARD = PLANKING, WALES
DEEP, SHALLOW, SURF, FOAM = "Blue", "Dark Turquoise", "Medium Azure", "White"
IRON, CASK = "Dark Bluish Gray", "Medium Nougat"

SEA_LENGTH, SEA_WIDTH = 66, 38  # the sea's footprint, in studs
KEEL = 19  # the hull is symmetric about the line y = 19
STERN, BOW = 8, 45  # where the hull meets the water, along x
BEAM = 6.3  # half the widest beam, in studs
WAIST, CASTLE, POOP = 18, 24, 30  # the heights of the decks, in plates
POOP_END, QUARTER_END, FORECASTLE = 13, 21, 40  # where the decks change, along x
BULWARK = 4  # layers of bulwark around each deck
STRIPES = (9, 14)  # the gold stripes, below and above the gun ports
GUN_DECK = 10  # the lowest layer of the gun ports
PORTS = range(14, 37, 3)  # the gun ports along x
STAIRS = {21: 6, 22: 4, 23: 2}  # each step's x and height above the waist, in plates
STAIR_ROWS = (14, 15, 22, 23)
SIDE = KEEL - 6  # the y of the hull's south side amidships
GALLERY = range(10, 13)  # the quarter galleries along x, a stud out from each side
GALLERY_ROWS = range(20, 27)
GALLERY_FACE = {20: GOLD, 21: GLASS, 22: GLASS, 23: GLASS, 24: GOLD}  # by layer
SIDE_WINDOWS = (
    (range(6, 8), range(19, 22)),
    (range(14, 16), range(19, 22)),
    (range(17, 19), range(19, 22)),
    (range(6, 9), range(27, 30)),
)  # the windows along each side of the stern castle: their x and their layers
STERN_WINDOWS = ({20, 21, 22, 26, 27, 28}, {15, 16, 18, 19, 21, 22})  # rows, panes
ARCHES = ((QUARTER_END - 1, CASTLE), (POOP_END - 1, POOP), (FORECASTLE, CASTLE))
ARCH_SPAN = range(KEEL - 3, KEEL + 3)  # each castle's front rail opens in an Arch 1 x 6
ANCHOR = (43, 18)  # the x and layer of the side stud that holds the anchor
BOWSPRIT = range(45, 53)  # the bowsprit's steps along x, each 2 plates higher
JIB = ((45, 34), (52, 41), (42, 84))  # the jib's corners (x, z): clew, tack and head
FIN = (51, 6)  # where a shark's fin cuts the water, a Slope 65 2 x 1 x 2

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
}  # plates by footprint, the shorter side first, along x when unrotated
TILES = {
    (1, 1): "3070",
    (1, 2): "3069",
    (1, 3): "63864",
    (1, 4): "2431",
    (1, 6): "6636",
    (1, 8): "4162",
}  # tiles by footprint, the shorter side first, along x when unrotated
ROUND_TILE = "98138"  # Tile, Round 1 x 1: the tile for colors without a Tile 1 x 1
LENGTHS = (8, 6, 4, 3, 2, 1)
# The longest first part of a run, layer by layer or row by row, so joints stagger.
STAGGER = (8, 4, 6, 2)
FACES = {"south": (0, -1), "north": (0, 1), "west": (-1, 0), "east": (1, 0)}

JOLLY_ROGER = (
    ".........",
    "...###...",
    "..#####..",
    "..#####..",
    "..#.#.#..",
    "..#.#.#..",
    "..#####..",
    "..##.##..",
    "...###...",
    "...#.#...",
    ".........",
    ".#.....#.",
    "..#...#..",
    "...#.#...",
    "....#....",
    "...#.#...",
    "..#...#..",
)  # the flag, top row first: a white skull over crossed bones, on black
PENNANT = (3, 5, 7, 8, 8, 7, 5, 3)  # the length of each row of a pennant, bottom first
RIPPLE = (0, 0, 1, 1, 0, 0, -1, -1)  # how far each column of a pennant ripples north


@dataclass(frozen=True, slots=True)
class Sail:
    """A square sail: its width in studs, its height in plates, its bulge in studs."""

    width: int
    height: int
    bulge: int


@dataclass(frozen=True, slots=True)
class Mast:
    """One mast: where it stands, its two sails, and its sections of round bricks.

    The foot, head, pole and top count the round bricks below the course, between the
    course and the crow's nest, below the topsail, and above it.
    """

    name: str
    x: int
    deck: int
    foot: int
    course: Sail
    head: int
    pole: int
    topsail: Sail
    top: int
    flag: str
    striped: bool = False


MASTS = (
    Mast("fore", 37, WAIST, 4, Sail(18, 24, 3), 1, 1, Sail(13, 18, 2), 1, "pennant"),
    Mast(
        "main",
        27,
        WAIST,
        2,
        Sail(20, 27, 3),
        1,
        1,
        Sail(15, 21, 3),
        2,
        "jolly-roger",
        striped=True,
    ),
    Mast("mizzen", 16, CASTLE, 2, Sail(16, 18, 2), 1, 1, Sail(11, 12, 2), 1, "pennant"),
)


@dataclass(slots=True)
class Stock:
    """Which parts the catalog lists in which colors."""

    catalog: Catalog
    known: dict[tuple[str, str], bool] = field(default_factory=dict)

    def has(self, part: str, color: str) -> bool:
        """Whether the part comes in the color."""
        if (part, color) not in self.known:
            entry = self.catalog.entry(part)
            color_id = self.catalog.resolve_color(color).id
            self.known[part, color] = entry is not None and (
                not entry.colors or color_id in entry.colors
            )
        return self.known[part, color]


@dataclass(frozen=True, slots=True)
class Run:
    """A straight run of parts: its first corner, length, direction, color and width.

    The first part is at most ``first`` long, so that joints stagger between runs.
    """

    at: Voxel
    length: int
    along_x: bool
    color: str
    width: int = 1
    first: int = 8


def mirror(y: int) -> int:
    """Return the row that mirrors a row across the keel, from south to north."""
    return 2 * KEEL - 1 - y


def lay_run(
    scope: Scope, stock: Stock, run: Run, parts: dict[Square, str] = PLATES
) -> None:
    """Cover a straight run with plates or tiles, longest first.

    No part leaves a single stud at the run's end where a shorter part avoids it, so
    the end of a run always shares a part with its neighbor. A run of tiles takes a
    round tile where no Tile 1 x 1 comes in its color.
    """
    x, y, z = run.at
    done, limit = 0, run.first
    while done < run.length:
        left = run.length - done
        sizes = [
            length
            for length in LENGTHS
            if length <= min(left, limit)
            and (part := parts.get((min(length, run.width), max(length, run.width))))
            is not None
            and stock.has(part, run.color)
        ]
        size = next((n for n in sizes if left - n != 1), sizes[0]) if sizes else 1
        key = (min(size, run.width), max(size, run.width))
        footprint = (size, run.width) if run.along_x else (run.width, size)
        scope.place(
            parts[key] if sizes else ROUND_TILE,
            at=(x + done, y, z) if run.along_x else (x, y + done, z),
            rotation="R0" if footprint[0] <= footprint[1] else "R90",
            color=run.color,
        )
        done, limit = done + size, LENGTHS[0]


def runs_along(group: dict[Square, str]) -> list[tuple[Square, int, str]]:
    """Return the runs of one color along the first coordinate: start, length, color."""
    found: list[tuple[Square, int, str]] = []
    for along, across in sorted(group, key=lambda cell: (cell[1], cell[0])):
        color = group[along, across]
        if group.get((along - 1, across)) == color:
            continue
        length = 1
        while group.get((along + length, across)) == color:
            length += 1
        found.append(((along, across), length, color))
    return found


def lay_tiles(
    scope: Scope,
    stock: Stock,
    squares: dict[Square, str],
    z: int,
    *,
    along_x: bool | None = None,
) -> None:
    """Cover squares with tiles, in runs along x, along y, or whichever is longer."""
    left = dict(squares)
    for x, y in sorted(squares, key=lambda square: (square[1], square[0])):
        if (x, y) not in left:
            continue
        color = left[x, y]
        lengths: dict[bool, int] = {}
        for horizontal in (True, False):
            length = 0
            while left.get((x + length, y) if horizontal else (x, y + length)) == color:
                length += 1
            lengths[horizontal] = length
        horizontal = lengths[True] >= lengths[False] if along_x is None else along_x
        length = lengths[horizontal]
        first = STAGGER[(y if horizontal else x) % len(STAGGER)]
        run = Run((x, y, z), length, along_x=horizontal, color=color, first=first)
        lay_run(scope, stock, run, TILES)
        for k in range(length):
            del left[(x + k, y) if horizontal else (x, y + k)]


def pack_wall(
    scope: Scope, stock: Stock, cells: Voxels, *, along_x: bool, rippled: bool = False
) -> None:
    """Lay a thin wall as plates, staggering the joints from layer to layer.

    The wall runs along x or y. Two cells side by side across the wall share a plate 2
    studs wide, which ties them together; every other cell takes a plate 1 stud wide,
    in runs along the wall. A rippled wall ties its cells only in every other layer,
    so that the runs between can bridge its steps.
    """
    for z in sorted({voxel[2] for voxel in cells}):
        tie = not rippled or z % 2 == 0
        layer = {
            ((x, y) if along_x else (y, x)): color
            for (x, y, height), color in cells.items()
            if height == z
        }
        used: set[Square] = set()
        pairs: dict[Square, str] = {}
        for along, across in sorted(layer, key=lambda cell: (cell[1], cell[0])):
            if not tie or {(along, across), (along, across + 1)} & used:
                continue
            if layer.get((along, across + 1)) == layer[along, across]:
                pairs[along, across] = layer[along, across]
                used |= {(along, across), (along, across + 1)}
        singles = {cell: color for cell, color in layer.items() if cell not in used}
        first = STAGGER[z % len(STAGGER)]
        for width, group in ((2, pairs), (1, singles)):
            for (along, across), length, color in runs_along(group):
                at = (along, across, z) if along_x else (across, along, z)
                run = Run(
                    at, length, along_x=along_x, color=color, width=width, first=first
                )
                lay_run(scope, stock, run)


def stern_at(z: int) -> float:
    """Return the x of the stern at a layer: the stern castle leans aft as it rises."""
    return STERN - max(0, z - 6) / 8


def bow_at(z: int) -> float:
    """Return the x of the bow at a layer: the stem rakes forward as it rises."""
    return BOW + max(0, z - 2) / 5


def half_beam(x: int, z: int) -> float:
    """Return half the hull's width at a square's center, in studs; 0 off the hull.

    The plan is full amidships, rounds into the bow and squares off at the stern. The
    sides curve in below the waterline and lean in above the main deck.
    """
    stern, bow = stern_at(z), bow_at(z)
    along = (x + 0.5 - stern) / (bow - stern)
    if not 0 <= along <= 1:
        return 0.0
    if along < 0.1:
        plan = 0.86 + 1.4 * along
    elif along <= 0.58:
        plan = 1.0
    else:
        plan = float((1 - ((along - 0.58) / 0.42) ** 2.2) ** 0.6)
    side = 0.78 + 0.22 * z / 6 if z < 6 else 1 - max(0, z - 16) * 0.012
    return BEAM * plan * side


def in_plan(x: int, y: int, z: int) -> bool:
    """Whether the hull's outline at a layer covers a square."""
    return abs(y + 0.5 - KEEL) < half_beam(x, z)


def deck_at(x: int) -> int:
    """Return the height of the deck over a column of the hull, in plates."""
    if x < POOP_END:
        return POOP
    if x < QUARTER_END or x >= FORECASTLE:
        return CASTLE
    return WAIST


def outside(x: int, y: int, z: int) -> set[str]:
    """Return the faces of a hull square that look out of the hull's outline."""
    return {
        face
        for face, (east, north) in FACES.items()
        if not in_plan(x + east, y + north, z)
    }


def on_rim(x: int, y: int, z: int) -> bool:
    """Whether a hull square touches the outline, by a side or a corner.

    Corners count, so that the bulwark's squares always share sides with each other.
    """
    return any(
        not in_plan(x + east, y + north, z)
        for east in (-1, 0, 1)
        for north in (-1, 0, 1)
    )


def channels() -> list[Square]:
    """Return the squares of the channels on the south side, a stud out from the hull.

    Each channel is a ledge beside a mast on the waist, carrying the deadeyes of its
    shrouds; the north side mirrors it.
    """
    return [
        (x, min(y for y in range(SEA_WIDTH) if in_plan(x, y, WAIST)) - 1)
        for mast in MASTS
        if mast.deck == WAIST
        for x in range(mast.x - 1, mast.x + 3)
    ]


def body() -> set[Voxel]:
    """Return the hull's body: solid up to each deck, then a bulwark round its rim.

    A deck raised above its neighbor also takes a rail along its front edge.
    """
    cells: set[Voxel] = set()
    for x in range(SEA_LENGTH):
        deck = deck_at(x)
        raised = deck_at(x - 1) < deck or deck_at(x + 1) < deck
        cells |= {
            (x, y, z)
            for z in range(deck + BULWARK)
            for y in range(SEA_WIDTH)
            if in_plan(x, y, z) and (z < deck or raised or on_rim(x, y, z))
        }
    return cells


def hull_shape() -> set[Voxel]:
    """Return the hull's voxels: its body, steps, channels and quarter galleries.

    Each gallery stands a stud out from the side; inverted slopes in the side carry it.
    """
    cells = body()
    cells |= {
        (x, y, z)
        for x, rise in STAIRS.items()
        for y in STAIR_ROWS
        for z in range(WAIST, WAIST + rise)
    }
    cells |= {(x, row, WAIST) for x, y in channels() for row in (y, mirror(y))}
    corbels = range(GALLERY_ROWS.start - 3, GALLERY_ROWS.start)
    for wall in (SIDE, mirror(SIDE)):
        bay = wall - 1 if wall == SIDE else wall + 1
        cells |= {(x, bay, z) for x in GALLERY for z in GALLERY_ROWS}
        cells -= {(x, wall, z) for x in GALLERY for z in corbels}
    gap = range(CASTLE, CASTLE + BULWARK)  # the stairs climb through the rail
    cells -= {(QUARTER_END - 1, y, z) for y in STAIR_ROWS for z in gap}
    rails = range(BULWARK)
    return cells - {(x, y, z + k) for x, z in ARCHES for y in ARCH_SPAN for k in rails}


def gun_ports(cells: set[Voxel]) -> list[tuple[int, int, bool]]:
    """Clear the gun ports from the hull's sides.

    Returns each port's x, the y of its wall and whether it faces south.
    """
    ports: list[tuple[int, int, bool]] = []
    rows = range(GUN_DECK, GUN_DECK + 3)
    for x in PORTS:
        for south in (True, False):
            pick = min if south else max
            walls = {
                pick(y for y in range(SEA_WIDTH) if in_plan(x, y, z)) for z in rows
            }
            if len(walls) == 1:
                y = walls.pop()
                cells -= {(x, y, z) for z in rows}
                ports.append((x, y, south))
    return ports


def door(x: int, y: int, z: int, shown: set[str]) -> str | None:
    """Return the color of a door, lintel or window in a castle's front wall, if any."""
    deck = deck_at(x)
    front = "west" if x >= FORECASTLE else "east"
    if deck == WAIST or z >= deck or front not in shown - outside(x, y, z):
        return None
    bottom = CASTLE if x < POOP_END else WAIST
    if y in {KEEL - 1, KEEL} and z < bottom + 5:
        return WALES
    if KEEL - 2 <= y <= KEEL + 1 and z == bottom + 5:
        return GOLD
    if y in {KEEL - 3, KEEL + 2} and bottom < z <= bottom + 3:
        return GLASS
    return None


def window(x: int, y: int, z: int, out: set[str]) -> str | None:
    """Return the color of a gallery, a side window or a stern window, if any."""
    if x in GALLERY and y in {SIDE - 1, mirror(SIDE - 1)}:
        return GALLERY_FACE.get(z, PLANKING)
    side = bool(out & {"south", "north"}) and any(
        x in columns and z in rows for columns, rows in SIDE_WINDOWS
    )
    rows, panes = STERN_WINDOWS
    stern = "west" in out and x < POOP_END and z in rows and y in panes
    return GLASS if side or stern else None


def trim(x: int, z: int, shown: set[str], out: set[str]) -> str | None:
    """Return gold where the stem, a stripe or a castle's band runs, if any."""
    if "east" in out and x >= BOW and STRIPES[0] <= z < CASTLE:
        return GOLD  # the gilded stem
    castle = x < QUARTER_END or x >= FORECASTLE
    band = z in STRIPES or (z == CASTLE and castle) or (z == POOP and x < POOP_END)
    return GOLD if shown and band else None


def hull_color(x: int, y: int, z: int, cells: set[Voxel]) -> str:
    """Return the color of a hull voxel: planking, wales, gold trim or glass."""
    shown = {
        face
        for face, (east, north) in FACES.items()
        if (x + east, y + north, z) not in cells
    }
    out = outside(x, y, z)
    for color in (door(x, y, z, shown), window(x, y, z, out), trim(x, z, shown, out)):
        if color is not None:
            return color
    return WALES if z <= 8 else PLANKING


def bowsprit() -> Voxels:
    """Return the bowsprit's voxels: steps 2 studs wide and 3 plates thick.

    Each step stands 2 plates above the one behind it.
    """
    return {
        (x, y, z): SPAR
        for step, x in enumerate(BOWSPRIT)
        for y in (KEEL - 1, KEEL)
        for z in range(CASTLE + 2 * step, CASTLE + 2 * step + 3)
    }


def jib() -> Voxels:
    """Return the jib's voxels: a triangle of canvas from the bowsprit to the foremast.

    The rows stop where a row would no longer overlap the one below.
    """
    (clew_x, clew_z), (tack_x, tack_z), (head_x, head_z) = JIB
    cells: Voxels = {}
    for z in range(clew_z, head_z + 1):
        back = clew_x + (head_x - clew_x) * (z - clew_z) / (head_z - clew_z)
        if z < tack_z:
            front = clew_x + (tack_x - clew_x) * (z - clew_z) / (tack_z - clew_z)
        else:
            front = tack_x + (head_x - tack_x) * (z - tack_z) / (head_z - tack_z)
        row = range(ceil(back), floor(front) + 1)
        below = {x for x, _, height in cells if height == z - 1}
        if z > clew_z and not below.intersection(row):
            break
        cells |= dict.fromkeys(((x, KEEL - 1, z) for x in row), CANVAS)
    return cells


def in_sea(x: int, y: int) -> bool:
    """Whether a square lies on the sea, a rounded rectangle."""
    east = (x + 0.5 - SEA_LENGTH / 2) / (SEA_LENGTH / 2)
    north = (y + 0.5 - SEA_WIDTH / 2) / (SEA_WIDTH / 2)
    return east**4 + north**4 <= 1


def swell(x: int, y: int) -> float:
    """Return the swell's height at a square, from 0 in a trough to 1 on a crest.

    The swells run roughly along x and roll south, toward the camera.
    """
    shift = 2.5 * sin(x / 5.5) + 1.2 * sin((x + y) / 3.7)
    return 0.5 + 0.5 * cos(2 * pi * (y + shift) / 9)


def near_kind(x: int, y: int, distance: int | None) -> str | None:
    """Return what the sea does near the hull or the shark: fin, foam, spray or wake.

    The distance is how far the square lies from the hull at the waterline, if near.
    """
    fin_x, fin_y = FIN
    if y == fin_y and x in {fin_x, fin_x + 1}:
        return "fin"
    if abs(x - fin_x - 0.5) <= 2.5 and abs(y - fin_y) <= 1:
        return "foam"
    if distance is not None and 0 < distance <= 2 and x >= BOW - 5:
        return "spray"
    if distance == 1 and (x + y) % 3 != 0:
        return "foam"
    if STERN - 14 < x <= STERN and abs(y + 0.5 - KEEL) < 1 + (STERN - x) * 0.3:
        return "wake"
    return None


def wave_kind(x: int, y: int) -> str:
    """Return what the open sea does at a square: crest, foam, swell, flank or trough.

    A crest runs along each swell's peak, broken here and there; foam spills on its
    southern side.
    """
    height = swell(x, y)
    peak = swell(x, y + 1) <= height > swell(x, y - 1)
    if peak and sin(x * 0.7 + y * 0.4) > -0.5:
        return "crest"
    if peak or swell(x, y + 1) > height > 0.85:
        return "foam"
    if height > 0.7:
        return "swell"
    return "flank" if height > 0.4 else "trough"


def sea_kind(x: int, y: int, distance: int | None) -> str:
    """Return what the sea does at a square, near the hull or on the open sea."""
    near = near_kind(x, y, distance)
    return wave_kind(x, y) if near is None else near


def waterline(solid: Voxels) -> dict[Square, int]:
    """Return how far each square near the hull lies from it at the waterline.

    Squares farther than 3 studs are left out.
    """
    footprint = {(x, y) for x, y, z in solid if z == 3}
    distance = dict.fromkeys(footprint, 0)
    queue = deque(footprint)
    while queue:
        x, y = queue.popleft()
        for east, north in FACES.values():
            near = (x + east, y + north)
            if near not in distance and distance[x, y] < 3:
                distance[near] = distance[x, y] + 1
                queue.append(near)
    return distance


@dataclass(slots=True)
class Sea:
    """The sea: voxels to fill, then tiles, and slopes for the crests."""

    voxels: Voxels = field(default_factory=dict)
    tiles: dict[Square, str] = field(default_factory=dict)
    crests: dict[Square, str] = field(default_factory=dict)


def sea(solid: Voxels) -> Sea:
    """Lay the sea around the hull: two layers of plates, then the waves.

    Swells, crests and spray take a third layer of plates, with white slopes on the
    crests and the spray; troughs, flanks, foam and the wake take tiles.
    """
    distance = waterline(solid)
    water = Sea()
    for x in range(SEA_LENGTH):
        for y in range(SEA_WIDTH):
            if not in_sea(x, y):
                continue
            kind = sea_kind(x, y, distance.get((x, y)))
            raised = kind in {"crest", "swell", "spray", "fin"}
            for z in range(3 if raised else 2):
                if (x, y, z) not in solid:
                    water.voxels[x, y, z] = SURF if raised and z > 0 else DEEP
            if kind in {"trough", "flank"}:
                water.tiles[x, y] = DEEP if kind == "trough" else SHALLOW
            elif kind in {"foam", "wake"}:
                water.tiles[x, y] = FOAM if (x * 7 + y * 13) % 5 < 2 else SURF
            elif kind == "crest":
                water.crests[x, y] = "R0"  # falls south
            elif kind == "spray":
                ahead = x >= bow_at(3)
                water.crests[x, y] = "R90" if ahead else "R0" if y < KEEL else "R180"
    return water


def canvas(sail: Sail, edge: int, *, striped: bool, roach: int = 0) -> Voxels:
    """Return a sail's voxels: a wall along y, pushed forward (toward +x) by the wind.

    The sail bulges most at its middle. Where the bulge steps forward, a layer holds
    both positions, so each layer overlaps the one below. A sail with a roach hangs
    free, its foot curved up by that many plates at the middle; a sail without one
    stands on a yard at layer 0.
    """
    cells: Voxels = {}
    bottom = 0 if roach else 1
    for j in range(sail.width):
        across = (j + 0.5) / sail.width * 2 - 1
        color = "Red" if striped and j // 2 % 2 == 0 else CANVAS
        start = round(roach * (1 - across**2))
        previous = 0
        for i in range(start, sail.height):
            up = (i - start + 0.5) / (sail.height - start)
            offset = round(sail.bulge * sin(pi * up) ** 0.7 * (1 - 0.5 * across**2))
            if roach and i == start:
                previous = offset
            low = 0 if i == sail.height - 1 else min(previous, offset)
            for k in range(low, max(previous, offset) + 1):
                cells[edge + k, j + 1, bottom + i] = color
            previous = offset
    return cells


def yard(scope: ComponentBuilder, stock: Stock, band: Voxel, width: int) -> None:
    """Lay a yard one stud wide along y, on both sides of the band that grips the mast.

    The yard reaches a stud past the sail at each end: the yardarms.
    """
    x, middle, z = band
    first = STAGGER[z % len(STAGGER)]
    start = middle + (2 if width % 2 == 0 else 1)
    for corner, length in ((0, middle), (start, width + 2 - start)):
        run = Run((x, corner, z), length, along_x=False, color=YARD, first=first)
        lay_run(scope, stock, run)


def course(builder: ModelBuilder, stock: Stock, mast: Mast) -> str:
    """Define a mast's lower sail, hung from its yard; return the component's name.

    The lower mast, round bricks 2 x 2, runs behind the sail; a plate 2 x 3 grips the
    mast where the yard crosses it.
    """
    sail = mast.course
    name = f"{mast.name}-course"
    scope = builder.component(name)
    middle = sail.width // 2
    for k in range(sail.height // 3):
        scope.place("3941", at=(0, middle, 3 * k), color=SPAR)
    scope.place("3021", at=(0, middle, sail.height), rotation="R90", color=YARD)
    yard(scope, stock, (2, middle, sail.height), sail.width)
    cells = canvas(sail, 2, striped=mast.striped, roach=3)
    pack_wall(scope, stock, cells, along_x=False)
    return name


def topsail(builder: ModelBuilder, stock: Stock, mast: Mast) -> str:
    """Define a mast's upper sail between two yards; return the component's name."""
    sail = mast.topsail
    name = f"{mast.name}-topsail"
    scope = builder.component(name)
    middle = (sail.width + 1) // 2
    for z in (0, sail.height + 1):
        scope.place("3023", at=(0, middle, z), rotation="R90", color=YARD)
        yard(scope, stock, (1, middle, z), sail.width)
    for k in range(sail.height // 3):
        scope.place("3062", at=(0, middle, 1 + 3 * k), color=SPAR)
    pack_wall(scope, stock, canvas(sail, 1, striped=False), along_x=False)
    return name


def flag_cells(kind: str, at: Voxel) -> tuple[Voxels, str]:
    """Return a flag's voxels east of the mast, and the color of its field."""
    x, y, z = at
    if kind == "jolly-roger":
        cells = {
            (x + 1 + i, y, z + row): "White" if pixel == "#" else "Black"
            for row, line in enumerate(reversed(JOLLY_ROGER))
            for i, pixel in enumerate(line)
        }
        return cells, "Black"
    # Where the ripple steps, a column holds both rows, so its plates span the step.
    cells = {
        (x + 1 + i, y + shift, z + row): "Red"
        for row, length in enumerate(PENNANT)
        for i in range(length)
        for shift in {RIPPLE[i], RIPPLE[i - 1] if i else 0}
    }
    return cells, "Red"


def flag(scope: ComponentBuilder, stock: Stock, kind: str, at: Voxel) -> None:
    """Fly a flag east of the mast; its bottom and top rows run through the mast.

    Round bricks carry the mast between the two rows, and a gold finial caps it.
    """
    x, y, z = at
    cells, color = flag_cells(kind, at)
    top = max(voxel[2] for voxel in cells)
    cells[x, y, z] = cells[x, y, top] = color
    for height in range(z + 1, top, 3):
        scope.place("3062", at=(x, y, height), color=SPAR)
    pack_wall(scope, stock, cells, along_x=True, rippled=kind == "pennant")
    scope.place("4073", at=(x, y, top + 1), color=GOLD)
    scope.place(ROUND_TILE, at=(x, y, top + 2), color=GOLD)


def topmast(builder: ModelBuilder, stock: Stock, mast: Mast) -> str:
    """Define a round topmast with its topsail and flag; return the component's name."""
    sail = mast.topsail
    name = f"{mast.name}-topmast"
    scope = builder.component(name)
    middle = (sail.width + 1) // 2
    z = 0
    for _ in range(mast.pole):
        scope.place("3062", at=(0, middle, z), color=SPAR)
        z += 3
    scope.instance(topsail(builder, stock, mast), at=(0, 0, z))
    z += sail.height + 2
    for _ in range(mast.top):
        scope.place("3062", at=(0, middle, z), color=SPAR)
        z += 3
    flag(scope, stock, mast.flag, (0, middle, z))
    return name


def crows_nest(builder: ModelBuilder) -> None:
    """Define a crow's nest: a platform round the mast, a wall, and a jumper inside.

    The jumper's single stud centers the round topmast on the lower mast, half a stud
    off the grid.
    """
    nest = builder.component("crows-nest")
    for y in (0, 3):
        nest.place("3710", at=(0, y, 0), rotation="R90", color=SPAR)
        nest.place("3004", at=(1, y, 2), rotation="R90", color=WALES)
        nest.place("3069", at=(1, y, 5), rotation="R90", color=GOLD)
    for x in (0, 3):
        nest.place("3023", at=(x, 1, 0), color=SPAR)
        nest.place("3004", at=(x, 0, 2), color=WALES)
        nest.place("3004", at=(x, 2, 2), color=WALES)
        nest.place("2431", at=(x, 0, 5), color=GOLD)
    nest.place("3031", at=(0, 0, 1), color=SPAR, id="platform")
    nest.place("87580", at=(1, 1, 2), color=SPAR, id="jumper")


def rig(builder: ModelBuilder, stock: Stock, mast: Mast) -> Voxel:
    """Step a mast on its deck with its sails, crow's nest and flag.

    Returns where the mast stands: its west-south corner on the deck.
    """
    foot = (mast.x, KEEL - 1, mast.deck)
    z = mast.deck
    for _ in range(mast.foot):
        builder.place("3941", at=(mast.x, KEEL - 1, z), color=SPAR)
        z += 3
    sail = mast.course
    builder.instance(
        course(builder, stock, mast),
        at=(mast.x, KEEL - 1 - sail.width // 2, z),
        id=f"{mast.name}-course",
    )
    z += sail.height + 1
    for _ in range(mast.head):
        builder.place("3941", at=(mast.x, KEEL - 1, z), color=SPAR)
        z += 3
    builder.instance(
        "crows-nest", at=(mast.x - 1, KEEL - 2, z - 1), id=f"{mast.name}-nest"
    )
    builder.instance(
        topmast(builder, stock, mast),
        at=(mast.x + 0.5, KEEL - 0.5 - (mast.topsail.width + 1) // 2, z + 2),
        id=f"{mast.name}-topmast",
    )
    return foot


def spars(builder: ModelBuilder, stock: Stock) -> set[Voxel]:
    """Rig the masts and the jib, and cap the bowsprit's steps with cheese slopes.

    Returns where the masts stand.
    """
    sail = jib()
    pack_wall(builder, stock, sail, along_x=True)
    for step, x in enumerate(BOWSPRIT):
        z = CASTLE + 2 * step + 3
        for y in (KEEL - 1, KEEL):
            if (x, y, z) in sail or (x, y, z + 1) in sail:
                continue  # the jib stands on this step
            if x == BOWSPRIT[-1]:
                builder.place("4073", at=(x, y, z), color=SPAR)
            else:
                builder.place("54200", at=(x, y, z), rotation="R270", color=SPAR)
    crows_nest(builder)
    feet = [rig(builder, stock, mast) for mast in MASTS]
    return {(x + i, y + j, z) for x, y, z in feet for i in (0, 1) for j in (0, 1)}


def guns(builder: ModelBuilder, ports: list[tuple[int, int, bool]]) -> set[Voxel]:
    """Run out a cannon in every gun port; return where the ports stand.

    A brick with a side stud fills the port and holds the barrel, built sideways.
    """
    gun = builder.component("cannon")
    gun.place("87087", at=(0, 1.6, 0), color="Black", id="port")
    gun.place("3062", at=(0, 0.4, 0.5), rotation="+x+z", color="Black", id="barrel")
    gun.place("4073", at=(0, 0, 0.5), rotation="+x+z", color="Black", id="muzzle")
    for x, y, south in ports:
        if south:
            builder.instance("cannon", at=(x, y - 1.6, GUN_DECK), id=f"gun-s{x}")
        else:
            builder.instance(
                "cannon", at=(x, y, GUN_DECK), rotation="R180", id=f"gun-n{x}"
            )
    return {(x, y, GUN_DECK) for x, y, _ in ports}


def anchor(builder: ModelBuilder, cells: set[Voxel]) -> Voxel:
    """Hang an anchor on the bow's south side, built flat and rotated upright.

    The anchor's shank plugs onto the side stud of a brick set into the hull. Returns
    where that brick stands.
    """
    x, z = ANCHOR
    y = min(y for y in range(SEA_WIDTH) if (x, y, z) in cells)
    cells -= {(x, y, z + k) for k in range(3)}
    builder.place("87087", at=(x, y, z), color=PLANKING, id="anchor-post")
    iron = builder.component("anchor")
    iron.place("3710", at=(1, 0, 0), color=IRON)  # the shank, a Plate 1 x 4
    iron.place("3623", at=(0, 0, 1), rotation="R90", color=IRON)  # the arms
    iron.place("3623", at=(0, 2, 1), rotation="R90", color=IRON)  # the stock
    iron.place(ROUND_TILE, at=(1, 1, 1), color=IRON)
    iron.place("4073", at=(1, 3, 1), color=IRON)  # the ring
    iron.place("54200", at=(0, 0, 2), rotation="R270", color=IRON)  # the flukes
    iron.place("54200", at=(2, 0, 2), rotation="R90", color=IRON)
    # Rotated +x+z, the anchor stands up facing south. The side stud, 1.75 plates up
    # its brick, meets the shank's third stud, 2.5 studs up the anchor.
    builder.instance(
        "anchor",
        at=(x - 1, y - 1.6, z + 1.75 - 2.5 * 2.5),
        rotation="+x+z",
        id="anchor",
    )
    return (x, y, z)


def galleries(builder: ModelBuilder) -> set[Voxel]:
    """Carry each quarter gallery on inverted slopes and roof it with slopes.

    Returns the squares the slopes take over the hull's tops.
    """
    taken: set[Voxel] = set()
    low, top = GALLERY_ROWS.start - 3, GALLERY_ROWS.stop
    sides = ((SIDE, SIDE - 1, "R0"), (mirror(SIDE), mirror(SIDE), "R180"))
    for x in GALLERY:
        for wall, corner, rotation in sides:
            # Slope, Inverted 45 2 x 1 under the gallery; Slope 45 2 x 1 over it.
            builder.place("3665", at=(x, corner, low), rotation=rotation, color=WALES)
            builder.place("3040", at=(x, corner, top), rotation=rotation, color=WALES)
            taken |= {(x, wall, low), (x, corner, top), (x, corner + 1, top)}
    return taken


def arcades(builder: ModelBuilder, stock: Stock) -> set[Voxel]:
    """Open each castle's front rail in an arch, capped by a plate and gold tiles.

    Returns the squares under the arches, which keep their studs.
    """
    taken: set[Voxel] = set()
    start = ARCH_SPAN.start
    for x, z in ARCHES:
        builder.place("3455", at=(x, start, z), color=PLANKING, id=f"arch-{x}")
        builder.place("3666", at=(x, start, z + 3), color=PLANKING)
        run = Run((x, start, z + 4), len(ARCH_SPAN), along_x=False, color=GOLD)
        lay_run(builder, stock, run, TILES)
        taken |= {(x, y, z) for y in ARCH_SPAN}
    return taken


def deck_fittings(builder: ModelBuilder, shape: set[Voxel]) -> set[Voxel]:
    """Fit out the decks: barrels, kegs, the hatch, the wheel, the chest and the bell.

    Returns where they stand, with the deadeyes on the channels and the stern lanterns.
    """
    taken: set[Voxel] = set()
    barrel(builder)
    for x, y in ((24, 14), (24, 22), (35, 21)):
        builder.instance("barrel", at=(x, y, WAIST))
        taken |= {(x + i, y + j, WAIST) for i in (0, 1) for j in (0, 1)}
    keg(builder)
    for x, y in ((26, 14), (26, 23), (36, 14), (36, 15)):
        builder.instance("keg", at=(x, y, WAIST))
        taken.add((x, y, WAIST))
    builder.place("3031", at=(31, 17, WAIST), color=PLANKING, id="hatch")
    for i in (0, 2):
        for j in (0, 2):
            builder.place("3022", at=(31 + i, 17 + j, WAIST + 1), color=WALES)
    taken |= {(31 + i, 17 + j, WAIST) for i in range(4) for j in range(4)}
    for x, y in channels():
        for row in (y, mirror(y)):
            builder.place("4073", at=(x, row, WAIST + 1), color="Black")
            taken.add((x, row, WAIST + 1))
    taken |= wheel(builder, (10, KEEL - 1, POOP))
    taken |= treasure(builder, (7, 15, POOP))
    taken |= bell(builder, (42, KEEL - 1, CASTLE))
    return taken | lanterns(builder, shape)


def barrel(builder: ModelBuilder) -> None:
    """Define a barrel: a round brick 2 x 2 between hoops of round plates."""
    cask = builder.component("barrel")
    cask.place("4032", at=(0, 0, 0), color=WALES)
    cask.place("3941", at=(0, 0, 1), color=CASK)
    cask.place("4032", at=(0, 0, 4), color=WALES)
    cask.place("14769", at=(0, 0, 5), color=DECK)


def keg(builder: ModelBuilder) -> None:
    """Define a keg: a round brick 1 x 1 on a round plate, with a round tile lid."""
    small = builder.component("keg")
    small.place("4073", at=(0, 0, 0), color=WALES)
    small.place("3062", at=(0, 0, 1), color=CASK)
    small.place(ROUND_TILE, at=(0, 0, 4), color=WALES)


def wheel(builder: ModelBuilder, at: Voxel) -> set[Voxel]:
    """Stand the ship's wheel on the poop deck, facing the bow; return where it stands.

    A brick with a side stud holds a round plate 2 x 2 upright, and round tiles on its
    studs make the handles.
    """
    x, y, z = at
    builder.place("3005", at=(x, y, z), color=WALES, id="wheel-post")
    builder.place("87087", at=(x, y, z + 3), rotation="R90", color=WALES)
    builder.place(
        "4032", at=(x + 1, y, z + 3.5), rotation="+y+z", color=PLANKING, id="wheel"
    )
    for j in (0, 1):
        for rise in (0, 2.5):
            builder.place(
                ROUND_TILE,
                at=(x + 1.4, y + j, z + 3.5 + rise),
                rotation="+y+z",
                color=GOLD,
            )
    return {at}


def treasure(builder: ModelBuilder, at: Voxel) -> set[Voxel]:
    """Set a treasure chest on the deck, with gold coins spilled beside it.

    Returns where the chest and the coins stand.
    """
    x, y, z = at
    builder.place("3003", at=(x, y, z), color=WALES, id="chest")
    builder.place("3022", at=(x, y, z + 3), color=GOLD)
    builder.place("15068", at=(x, y, z + 4), color=PLANKING, id="chest-lid")
    builder.place("4073", at=(x - 1, y, z), color=GOLD)
    builder.place(ROUND_TILE, at=(x - 1, y, z + 1), color=GOLD)
    builder.place(ROUND_TILE, at=(x - 1, y + 1, z), color=GOLD)
    builder.place(ROUND_TILE, at=(x + 2, y + 1, z), color=GOLD)
    chest = {(x + i, y + j, z) for i in (-1, 0, 1) for j in (0, 1)}
    return chest | {(x + 2, y + 1, z)}


def bell(builder: ModelBuilder, at: Voxel) -> set[Voxel]:
    """Hang the ship's bell from a beam on two posts; return where the posts stand.

    The bell, a round brick, hangs from the beam by its own stud.
    """
    x, y, z = at
    for post in (y, y + 2):
        for level in (z, z + 3):
            builder.place("3005", at=(x, post, level), color=WALES)
    builder.place("3623", at=(x, y, z + 6), color=WALES, id="belfry")
    builder.place("3062", at=(x, y + 1, z + 3), color=GOLD, id="bell")
    return {(x, y, z), (x, y + 2, z)}


def lanterns(builder: ModelBuilder, shape: set[Voxel]) -> set[Voxel]:
    """Light the stern: a lantern on each aft corner of the poop deck's rail.

    The great stern lantern, round bricks 2 x 2, stands over the middle of the
    taffrail. Returns where the lanterns stand.
    """
    lamp = builder.component("lantern")
    lamp.place("4073", at=(0, 0, 0), color="Black")
    lamp.place("3062", at=(0, 0, 1), color=GLASS)
    lamp.place("4073", at=(0, 0, 4), color="Black")
    lamp.place(ROUND_TILE, at=(0, 0, 5), color=GOLD)
    rail = POOP + BULWARK
    taffrail = [(x, y) for x, y, z in shape if z == rail - 1]
    taken: set[Voxel] = set()
    for pick in (min, max):
        y = pick(y for _, y in taffrail)
        x = min(x for x, other in taffrail if other == y)
        builder.instance("lantern", at=(x, y, rail))
        taken.add((x, y, rail))
    x = min(x for x, y in taffrail if y == KEEL)
    for z, part, color in (
        (rail, "4032", "Black"),
        (rail + 1, "3941", GLASS),
        (rail + 4, "4032", "Black"),
        (rail + 5, "4032", GOLD),
    ):
        builder.place(part, at=(x, KEEL - 1, z), color=color)
    builder.place("4073", at=(x, KEEL - 1, rail + 6), color=GOLD, id="stern-lantern")
    return taken | {(x, KEEL - 1, rail), (x, KEEL, rail)}


def lay_tops(
    builder: ModelBuilder,
    stock: Stock,
    solid: Voxels,
    filled: Voxels,
    taken: set[Voxel],
) -> None:
    """Tile every open top of the hull: plank the decks and cap the rails and ledges.

    Planks run fore and aft; the castles' rails and ledges take gold.
    """
    planks: dict[int, dict[Square, str]] = {}
    caps: dict[int, dict[Square, str]] = {}
    for (x, y, z), color in solid.items():
        top = (x, y, z + 1)
        if top in filled or top in taken:
            continue
        deck = deck_at(x)
        if z + 1 == deck or (x in STAIRS and y in STAIR_ROWS):
            planks.setdefault(z + 1, {})[x, y] = DECK
        elif z + 1 == deck + BULWARK:
            caps.setdefault(z + 1, {})[x, y] = GOLD if deck > WAIST else WALES
        else:
            caps.setdefault(z + 1, {})[x, y] = GOLD if z >= CASTLE else color
    for z, squares in planks.items():
        lay_tiles(builder, stock, squares, z, along_x=True)
    for z, squares in caps.items():
        lay_tiles(builder, stock, squares, z)


def lay_sea(builder: ModelBuilder, stock: Stock, water: Sea, filled: Voxels) -> None:
    """Tile the sea, break white slopes on its crests, and raise the shark's fin.

    Two squares side by side on one crest share a Slope 30 1 x 2.
    """
    tiles = {
        square: color
        for square, color in water.tiles.items()
        if (*square, 2) not in filled
    }
    lay_tiles(builder, stock, tiles, 2)
    builder.place("60481", at=(*FIN, 3), rotation="R90", color=IRON, id="shark-fin")
    crests = {
        square: rotation
        for square, rotation in water.crests.items()
        if (*square, 3) not in filled and (*square, 4) not in filled
    }
    for (x, y), rotation in sorted(crests.items()):
        if (x, y) not in crests:
            continue
        del crests[x, y]
        if rotation == "R0" and crests.get((x + 1, y)) == "R0":
            del crests[x + 1, y]
            builder.place("85984", at=(x, y, 3), rotation=rotation, color=FOAM)
        else:
            builder.place("54200", at=(x, y, 3), rotation=rotation, color=FOAM)


def build() -> ModelBuilder:
    """Build the galleon on its sea.

    The hull, the sea and the bowsprit fill their voxels together, so the hull stands
    on the sea's plates; every other part plugs onto them.
    """
    builder = ModelBuilder("pirate-ship")
    stock = Stock(builder.catalog)
    shape = hull_shape()
    ports = gun_ports(shape)
    taken = {anchor(builder, shape)}
    solid = {cell: hull_color(*cell, shape) for cell in shape}
    water = sea(solid)
    filled = {**water.voxels, **solid, **bowsprit()}
    builder.fill(filled, id="ship")
    print(f"{len(filled):,} voxels filled")
    taken |= guns(builder, ports)
    taken |= spars(builder, stock)
    taken |= galleries(builder)
    taken |= arcades(builder, stock)
    taken |= deck_fittings(builder, shape)
    lay_tops(builder, stock, solid, filled, taken)
    lay_sea(builder, stock, water, filled)
    return builder
