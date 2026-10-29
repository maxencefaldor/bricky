# Copyright 2026 Maxence Faldor
"""The Elizabeth Tower (Big Ben) in London, beside the palace on Bridge Street.

- The tower stands 300 plates (96 m) tall on a plan of 16 studs, at about 1 stud to
  0.8 m. Its hollow shaft is voxels filled with bricks and plates (``builder.fill``):
  six tiers of recessed panels between ribs and string courses, lancet windows under
  Arch 1 x 4 heads, and round bricks as corner shafts.
- Each dial is built sideways: bricks with side studs hold a dark blue backing, then
  plates and tiles for the white dial, its blue rim, the gilded surround, the
  inscription and a row of shields. Jumpers center the hub, the hands and four
  numerals half a stud off the grid.
- Inverted slopes make the corbel table under the clock stage. The belfry has three
  louvered lights under gilded gablets of cheese slopes.
- The spire's roof is five courses of Slope 75 with lucarnes and crocketed hips. The
  Ayrton Light shines from a lantern of arches, under the orb and cross.
- The palace wing, the buses, the cab and the plane trees are voxels too. Lamps and
  Belisha beacons are components, and round tiles on side studs make the wheels.

Run: ``uv run bricky build examples/elizabeth_tower.py``
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from math import hypot
from typing import NamedTuple

from bricky import ModelBuilder
from bricky.fill import BRICKS, PLATES, Placement, plan_fill

BASE = 0.5  # the top of the baseplates, in plates
TOWER_X, TOWER_Y = 40, 22  # the south-west corner of the shaft, in studs
SHAFT = 16  # the shaft is 16 studs square

# Heights above the street, in plates.
PLINTH = 18
TIER = 22
TIERS = 6
SHAFT_TOP = PLINTH + TIER * TIERS  # the string course under the clock stage
CORBEL = SHAFT_TOP + 1
FLOOR = CORBEL + 3
PANEL = FLOOR + 1  # the bottom of the dial panels
ROWS = 14  # the dial panels are 14 studs tall
CORNICE = PANEL + ROWS * 5 // 2
BELFRY = CORNICE + 1
LIGHTS = BELFRY + 3
SIDE_ARCH = LIGHTS + 19
CENTER_ARCH = SIDE_ARCH + 3
EAVES = LIGHTS + 28  # the belfry's cornice
ROOF = EAVES + 1
COURSE = 9  # a Slope 75 is nine plates tall
LANTERN = ROOF + 5 * COURSE
SPIRE = LANTERN + 13

STONE, SHADE, GOLD = "Tan", "Dark Tan", "Pearl Gold"
BLUE, DIAL, INK, SLATE = "Dark Blue", "White", "Black", "Dark Bluish Gray"
RED, LIGHT = "Red", "Trans-Yellow"
RESERVED = "Magenta"  # marks voxels that placed parts take; the fill skips them

BAYS = ((1, 4), (4, 7), (8, 11), (11, 14))  # the ribs either side of each bay
INNER = frozenset({1, 2})  # the inner bays hold the windows and the taller heads
TRANSOM = 11  # the height in a tier of the bar that splits each panel in two

type Voxel = tuple[int, int, int]
type Cell = tuple[int, int]
type Point = tuple[float, float, float]

AXES = {
    "+x": (1, 0, 0),
    "-x": (-1, 0, 0),
    "+y": (0, 1, 0),
    "-y": (0, -1, 0),
    "+z": (0, 0, 1),
    "-z": (0, 0, -1),
}
NAMES = {vector: name for name, vector in AXES.items()}
QUARTERS = {"R0": "+x+y", "R90": "+y-x", "R180": "-x-y", "R270": "-y+x"}


def rotate(rotation: str, quarters: int) -> str:
    """Compose a rotation with quarters of a full rotation about the vertical axis."""
    name = QUARTERS.get(rotation, rotation)
    axes = [AXES[name[:2]], AXES[name[2:]]]
    for _ in range(quarters % 4):
        axes = [(-y, x, z) for x, y, z in axes]
    return NAMES[axes[0]] + NAMES[axes[1]]


class Piece(NamedTuple):
    """A part to place on a face, with its footprint (along, deep) and its color."""

    part: str
    size: tuple[float, float]
    color: str
    rotation: str = "R0"  # as placed on the south face


@dataclass(frozen=True)
class Face:
    """One face of the tower, seen from outside.

    ``a`` runs along the face from its left end, and ``d`` runs inward from the shaft's
    outer plane; both are in studs, and the shaft itself spans ``a`` from 0 to 16.
    """

    quarter: int  # quarters of a rotation from the south face, counterclockwise

    def corner(
        self, a: float, d: float, size: tuple[float, float] = (1, 1)
    ) -> tuple[float, float]:
        """Return the world corner of a box ``size`` (along, deep) at (a, d)."""
        along, deep = size
        match self.quarter:
            case 0:
                return TOWER_X + a, TOWER_Y + d
            case 1:
                return TOWER_X + SHAFT - d - deep, TOWER_Y + a
            case 2:
                return TOWER_X + SHAFT - a - along, TOWER_Y + SHAFT - d - deep
            case _:
                return TOWER_X + d, TOWER_Y + SHAFT - a - along

    def cell(self, a: int, d: int) -> Cell:
        """Return the world stud square at (a, d)."""
        x, y = self.corner(a, d)
        return int(x), int(y)


FACES = tuple(Face(quarter) for quarter in range(4))


def owned(d: int) -> range:
    """Return the squares along a face that it owns at depth ``d``.

    Each face owns its row from its left corner up to the next face's corner, so the
    four faces share out every square of each ring once.
    """
    return range(d, SHAFT - 1 - d)


@dataclass
class Scene:
    """The builder, the voxels still to fill, and the voxels placed parts take."""

    builder: ModelBuilder
    voxels: dict[Voxel, str] = field(default_factory=dict)
    reserved: set[Voxel] = field(default_factory=set)

    def put(self, part: str, at: Point, color: str, rotation: str = "R0") -> None:
        """Place a part at a height measured from the top of the baseplates."""
        x, y, z = at
        self.builder.place(part, at=(x, y, BASE + z), color=color, rotation=rotation)

    def put_on(self, face: Face, piece: Piece, at: Point) -> None:
        """Place a piece on a face, its minimum corner at (a, d, z)."""
        a, d, z = at
        x, y = face.corner(a, d, piece.size)
        self.put(
            piece.part, (x, y, z), piece.color, rotate(piece.rotation, face.quarter)
        )

    def reserve(self, cells: Iterable[Cell], heights: range) -> None:
        """Keep voxels for placed parts, so the fill leaves them free."""
        for x, y in cells:
            for z in heights:
                self.reserved.add((x, y, z))

    def lay(
        self,
        depths: Iterable[int],
        heights: range,
        color: Callable[[int, int, int], str | None],
    ) -> None:
        """Set the voxels of the tower's rings from a color for each (a, d, z)."""
        for face in FACES:
            for d in depths:
                for a in owned(d):
                    for z in heights:
                        if (value := color(a, d, z)) is not None:
                            self.voxels[(*face.cell(a, d), z)] = value

    def made(self, part: str, color: int | str) -> bool:
        """Return whether the catalog lists a part in a color."""
        if color == RESERVED:
            return True
        entry = self.builder.catalog.entry(part)
        if entry is None or not entry.colors:
            return True
        return self.builder.catalog.resolve_color(color).id in entry.colors

    def fill(self) -> None:
        """Fill the voxels with bricks and plates, leaving the reserved ones free."""
        voxels = {
            voxel: color
            for voxel, color in self.voxels.items()
            if voxel not in self.reserved
        }
        voxels |= dict.fromkeys(self.reserved, RESERVED)
        print(f"{len(voxels):,} voxels")
        for placement in plan_fill(voxels, made_in=self.made):
            if placement.color != RESERVED and not loose(placement, voxels):
                self.put(
                    placement.part,
                    placement.at,
                    str(placement.color),
                    placement.rotation,
                )


def loose(placement: Placement, voxels: dict[Voxel, str]) -> bool:
    """Return whether a part of a fill has no voxel above or below it to join.

    The fill leaves such a part out: a stray leaf under a tree's crown, say.
    """
    x, y, z = placement.at
    short, long = next(
        size
        for table in (BRICKS, PLATES)
        for size, part in table.items()
        if part == placement.part
    )
    width, depth = (short, long) if placement.rotation == "R0" else (long, short)
    height = 3 if placement.part in BRICKS.values() else 1
    return z > 0 and not any(
        (x + i, y + j, level) in voxels
        for i in range(width)
        for j in range(depth)
        for level in (z - 1, z + height)
    )


# The shaft.


def bay_of(a: int) -> int | None:
    """Return the bay a panel square lies in, or None for a rib or a corner."""
    for index, (left, right) in enumerate(BAYS):
        if left < a < right:
            return index
    return None


def head(bay: int) -> int:
    """Return the height in a tier where a bay's arch starts."""
    return TIER - 3 if bay in INNER else TIER - 6


def panel_back(bay: int, tier: int, rise: int) -> str:
    """Return the color at the back of a panel: a window, shaded stone or stone."""
    if bay in INNER and tier >= 1 and TRANSOM < rise <= head(bay) + 2:
        return INK
    if 1 <= rise <= 3 or 5 <= rise <= head(bay) + 2:
        return SHADE
    return STONE


def shaft_color(a: int, d: int, z: int) -> str | None:
    """Return the color of a shaft voxel, or None where a panel recedes."""
    tier, rise = divmod(z - PLINTH, TIER)
    bay = bay_of(a)
    if rise == 0 or bay is None:
        return SHADE if rise == 0 else STONE
    if d == 1:
        return panel_back(bay, tier, rise)
    recessed = 1 <= rise <= 3 or (5 <= rise < head(bay) + 3 and rise != TRANSOM)
    return None if recessed else STONE


def plinth_color(a: int, d: int, z: int) -> str | None:
    """Return the color of a plinth voxel: a base course, panels and a chamfer."""
    panel = 5 <= z < 13 and bay_of(a) is not None
    if z < 3:
        return SHADE
    if d == -1 and (z >= 15 or panel):
        return None  # a recessed panel, or the chamfer's slopes
    return SHADE if d == 0 and panel else STONE


def sill(scene: Scene, face: Face, at: Voxel, color: str, width: int = 2) -> None:
    """Tile the floor of a recess, one or two studs wide along a face."""
    a, d, z = at
    piece = (
        Piece("3069", (2, 1), color, "R90")
        if width == 2
        else Piece("3070", (1, 1), color)
    )
    scene.put_on(face, piece, at)
    scene.reserve([face.cell(a + i, d) for i in range(width)], range(z, z + 1))


def shaft(scene: Scene) -> None:
    """Lay the plinth and the paneled shaft, with arches and round corner shafts."""
    scene.lay((-1, 0, 1), range(PLINTH), plinth_color)
    scene.lay((0, 1), range(PLINTH, SHAFT_TOP + 1), shaft_color)
    for face in FACES:
        for a in range(-1, 16):  # cheese slopes chamfer the plinth
            scene.put_on(face, Piece("54200", (1, 1), SHADE), (a, -1, 15))
        scene.reserve([face.cell(a, -1) for a in range(-1, 16)], range(15, 17))
        for tier in range(TIERS):
            bottom = PLINTH + tier * TIER
            scene.reserve([face.cell(0, 0)], range(bottom + 1, bottom + TIER))
            for course in range(7):
                at = (0, 0, bottom + 1 + 3 * course)
                scene.put_on(face, Piece("3062", (1, 1), STONE), at)
            for bay, (left, _) in enumerate(BAYS):
                z = bottom + head(bay)
                scene.put_on(face, Piece("3659", (4, 1), STONE, "R90"), (left, 0, z))
                cells = [face.cell(left + i, 0) for i in range(4)]
                scene.reserve(cells, range(z, z + 3))
                for rise, color in ((1, SHADE), (5, STONE), (TRANSOM + 1, STONE)):
                    sill(scene, face, (left + 1, 0, bottom + rise), color)
        for left, _ in BAYS:
            sill(scene, face, (left + 1, -1, 5), STONE)


# The clock stage.

TILE_SIZES = {
    (1, 1): "3070",
    (1, 2): "3069",
    (1, 3): "63864",
    (1, 4): "2431",
    (1, 6): "6636",
    (1, 8): "4162",
    (2, 2): "3068",
    (2, 4): "87079",
}
PLATE_SIZES = {
    (1, 1): "3024",
    (1, 2): "3023",
    (1, 3): "3623",
    (1, 4): "3710",
    (1, 6): "3666",
    (1, 8): "3460",
    (2, 2): "3022",
    (2, 4): "3020",
}
KINDS = {"tile": TILE_SIZES, "plate": PLATE_SIZES, "round": {(1, 1): "98138"}}

type Layer = dict[Cell, tuple[str, str]]  # (u, v) to (kind, color)

CENTER = 7.0  # the dial's center, in studs along the panel and up it
NUMERALS = {(5, 10), (8, 10), (5, 3), (8, 3), (10, 8), (10, 5), (3, 8), (3, 5)}
HANDS = {(u, v) for u in (6, 7) for v in (3, 6, 7, 8, 9, 10)} | {
    (u, v) for u in (3, 8, 9, 10) for v in (6, 7)
}  # the squares under the hub, the hands and the numerals on jumpers
LOOKS = {  # the kind and color of each role in layers 2, 3 and 4
    "stone": (("tile", STONE),),
    "letters": (("tile", BLUE),),
    "gilt": (("tile", GOLD),),
    "shield": (("plate", DIAL), ("tile", DIAL)),
    "cross": (("plate", DIAL), ("round", RED)),
    "frame": (("plate", GOLD), ("tile", GOLD)),
    "spandrel": (("round", GOLD),),
    "rim": (("plate", BLUE), ("plate", BLUE), ("tile", BLUE)),
    "glass": (("plate", DIAL), ("tile", DIAL)),
}


def cover(scene: Scene, face: Face, layer: Layer, depth: int) -> None:
    """Cover a layer of a dial panel with parts held sideways, largest first.

    The panel's squares (u, v) are one stud wide and one stud tall; ``depth`` counts
    the layers out from the wall, each one plate thick.
    """
    free = dict(layer)
    for u, v in sorted(layer, key=lambda cell: (cell[1], cell[0])):
        if (u, v) not in free:
            continue
        kind, color = free[u, v]
        for (short, long), part in sorted(
            KINDS[kind].items(), key=lambda item: -item[0][0] * item[0][1]
        ):
            for width, height, rotation in (
                (short, long, "+x+z"),
                (long, short, "-z+x"),
            ):
                cells = [(u + i, v + j) for i in range(width) for j in range(height)]
                if scene.made(part, color) and all(
                    free.get(cell) == (kind, color) for cell in cells
                ):
                    piece = Piece(part, (width, 0.4), color, rotation)
                    scene.put_on(face, piece, (1 + u, -0.4 * depth, PANEL + 2.5 * v))
                    for cell in cells:
                        del free[cell]
                    break
            else:
                continue
            break


def square_role(across: float, up: float) -> str:
    """Return what a square of the dial's surround shows, from the dial's center."""
    if max(abs(across), abs(up)) == 5.5:
        return "frame"
    radius = hypot(across, up)
    if radius <= 4:
        return "glass"
    return "rim" if radius <= 5 else "spandrel"


def dial_role(u: int, v: int) -> str:
    """Return what a square of the dial panel shows."""
    if u in {0, ROWS - 1}:
        return "stone"
    if v == 0:  # the inscription: gilt letters on blue
        return "gilt" if u in {2, 3, 5, 6, 7, 8, 10, 11} else "letters"
    if v == ROWS - 1:  # shields of St George
        return "cross" if u % 3 == 2 else "shield"
    return square_role(u + 0.5 - CENTER, v + 0.5 - CENTER)


def hands(scene: Scene, face: Face) -> None:
    """Place the hub, the hands at three o'clock and the numerals III, VI and IX.

    Jumpers center the hands and those numerals on the dial, half a stud off the grid.
    """
    across = Piece("15573", (2, 0.4), DIAL, "-z+x")  # a jumper along the panel
    upright = Piece("15573", (1, 0.4), DIAL, "+x+z")  # a jumper up the panel
    for v in (3, 8, 9, 10):  # VI, then the minute hand
        scene.put_on(face, across, (7, -1.2, PANEL + 2.5 * v))
    for u in (3, 8, 9, 10):  # IX, the hour hand, and III
        scene.put_on(face, upright, (1 + u, -1.2, PANEL + 15))
    scene.put_on(face, Piece("3022", (2, 0.4), DIAL, "+x+z"), (7, -1.2, PANEL + 15))
    scene.put_on(face, Piece("14769", (2, 0.4), GOLD, "+x+z"), (7, -1.6, PANEL + 15))
    scene.put_on(face, Piece("63864", (1, 0.4), INK, "+x+z"), (7.5, -1.6, PANEL + 20))
    scene.put_on(face, Piece("3069", (2, 0.4), INK, "-z+x"), (9, -1.6, PANEL + 16.25))
    numeral = Piece("98138", (1, 0.4), INK, "+x+z")
    for a, z in ((4, PANEL + 16.25), (11, PANEL + 16.25), (7.5, PANEL + 7.5)):
        scene.put_on(face, numeral, (a, -1.6, z))


def dial(scene: Scene, face: Face) -> None:
    """Build one dial panel on the side studs of its wall, layer by layer."""
    backing = Piece("91988", (14, 0.4), BLUE, "-z+x")  # Plate 2 x 14
    for v in range(0, ROWS, 2):
        scene.put_on(face, backing, (1, -0.4, PANEL + 2.5 * v))
    layers: list[Layer] = [{}, {}, {}]
    for u in range(ROWS):
        for v in range(ROWS):
            for depth, look in enumerate(LOOKS[dial_role(u, v)]):
                if depth != 1 or (u, v) not in HANDS:
                    numeral = depth == 1 and (u, v) in NUMERALS
                    layers[depth][u, v] = ("round", INK) if numeral else look
    for depth, layer in enumerate(layers, start=2):
        cover(scene, face, layer, depth)
    hands(scene, face)


def wall(scene: Scene, face: Face) -> None:
    """Lay the wall behind a dial: plates, and bricks whose side studs hold the dial.

    Side studs sit 1.75 plates above their brick's base, so a row every five plates
    meets every other row of anti-studs under the dial's upright plates.
    """
    for row in range(ROWS // 2):
        z = PANEL + 5 * row
        for rise, first in ((0, 8), (1, 6)):  # two plates, their joints staggered
            other = 14 - first
            scene.put_on(
                face,
                Piece(PLATE_SIZES[1, first], (first, 1), STONE, "R90"),
                (1, 0, z + rise),
            )
            scene.put_on(
                face,
                Piece(PLATE_SIZES[1, other], (other, 1), STONE, "R90"),
                (1 + first, 0, z + rise),
            )
        for a in (1, 5, 9):
            scene.put_on(face, Piece("30414", (4, 1), STONE), (a, 0, z + 2))
        scene.put_on(face, Piece("11211", (2, 1), STONE), (13, 0, z + 2))
    scene.reserve([face.cell(a, 0) for a in range(1, 15)], range(PANEL, CORNICE))


def corbels(scene: Scene, face: Face) -> None:
    """Carry the clock stage on a corbel table of inverted slopes, capped with tiles."""
    for a in (*range(1, 8, 2), *range(8, 15, 2)):
        scene.put_on(face, Piece("3665", (1, 2), STONE), (a, -1, CORBEL))
        scene.reserve([face.cell(a, 0)], range(CORBEL, FLOOR))
    for a in range(1, 15, 2):
        scene.put_on(face, Piece("3069", (2, 1), SHADE, "R90"), (a, -1, FLOOR))
    scene.reserve([face.cell(a, -1) for a in range(1, 15)], range(FLOOR, PANEL))


def parapet(scene: Scene, face: Face) -> None:
    """Crown the clock stage with a pierced parapet, a gilded coping and a cresting."""
    for a in range(1, 15):
        for z in range(CORNICE + 1, CORNICE + 4):
            if a % 2 == 1 or z == CORNICE + 1:
                scene.voxels[(*face.cell(a, -1), z)] = STONE
        scene.voxels[(*face.cell(a, -1), CORNICE + 4)] = GOLD
        crest = Piece("54200" if a % 2 else "4073", (1, 1), GOLD)
        scene.put_on(face, crest, (a, -1, CORNICE + 5))
        scene.voxels[(*face.cell(a, -2), CORNICE)] = SHADE  # a lip over the dial


def pinnacle(scene: Scene, face: Face) -> None:
    """Give a corner pier a round shaft, and top it with a turret and a gilded needle.

    The shaft carries on the round corners of the shaft below; a jumper centers the
    needle on the turret.
    """
    scene.reserve([face.cell(-1, -1)], range(PANEL, CORNICE))
    for z in range(PANEL, CORNICE - 2, 3):
        scene.put_on(face, Piece("3062", (1, 1), STONE), (-1, -1, z))
    for z in (CORNICE - 2, CORNICE - 1):
        scene.put_on(face, Piece("4073", (1, 1), STONE), (-1, -1, z))
    x, y = face.corner(-1, -1, (2, 2))
    z = CORNICE + 7
    scene.put("3941", (x, y, z), STONE)
    scene.put("4032", (x, y, z + 3), GOLD)
    scene.put("87580", (x, y, z + 4), GOLD)
    for rise, part in ((5, "3062"), (8, "4073"), (9, "3062"), (12, "98138")):
        scene.put(part, (x + 0.5, y + 0.5, z + rise), GOLD)


def stage_color(a: int, d: int, z: int) -> str | None:
    """Return the color of a voxel of the clock stage's rings and corner piers.

    Each face lays the pier at its left corner, and one square of the pier at its
    right corner, which the next face does not own.
    """
    pier = (a in {-1, 0} and d in {-1, 0}) or (a == SHAFT - 1 and d == -1)
    if z == CORNICE or (z == FLOOR and d <= 1):
        return SHADE
    if z < FLOOR:
        return STONE if d in {0, 1} else None
    return STONE if pier and z < CORNICE + 7 else None


def stage(scene: Scene) -> None:
    """Build the clock stage: corbels, piers, dials, cornice, parapet and pinnacles."""
    scene.lay((-1, 0, 1, 2), range(SHAFT_TOP + 1, CORNICE + 7), stage_color)
    for face in FACES:
        corbels(scene, face)
        wall(scene, face)
        dial(scene, face)
        parapet(scene, face)
        pinnacle(scene, face)


# The belfry, the roof and the spire.


def belfry_color(a: int, d: int, z: int) -> str | None:
    """Return the color of a belfry voxel: three lights with louvers behind."""
    side, center = a in {4, 5, 10, 11}, a in {7, 8}
    if z == EAVES or d == 0:
        return SHADE if z == EAVES else None
    if a in {2, 13} and LIGHTS <= z < SIDE_ARCH + 3:  # a narrow blind panel each side
        return None if d == 1 else SHADE
    if not (side or center) or z < LIGHTS:
        jamb = a in {3, 12} and LIGHTS <= z < SIDE_ARCH  # frames the three lights
        return SHADE if z == LIGHTS - 1 or jamb else STONE
    top = SIDE_ARCH if side else CENTER_ARCH
    if d == 1:
        return None if z < top + 3 else STONE
    return (SLATE if z % 2 else INK) if z < top + 2 else STONE


def belfry(scene: Scene) -> None:
    """Build the belfry: three lights on each face under gilded gablets."""
    scene.lay((0, 1, 2), range(BELFRY, EAVES + 1), belfry_color)
    for face in FACES:
        scene.reserve([face.cell(1, 1)], range(BELFRY, EAVES))
        for course in range(10):  # a round shaft on each corner
            scene.put_on(
                face, Piece("3062", (1, 1), STONE), (1, 1, BELFRY + 3 * course)
            )
        scene.put_on(face, Piece("4073", (1, 1), STONE), (1, 1, EAVES - 1))
        for left, z in ((3, SIDE_ARCH), (6, CENTER_ARCH), (9, SIDE_ARCH)):
            scene.put_on(face, Piece("3659", (4, 1), STONE, "R90"), (left, 1, z))
            scene.reserve([face.cell(left + i, 1) for i in range(4)], range(z, z + 3))
            scene.put_on(
                face, Piece("54200", (1, 1), GOLD, "R270"), (left + 1, 1, z + 3)
            )
            scene.put_on(
                face, Piece("54200", (1, 1), GOLD, "R90"), (left + 2, 1, z + 3)
            )
            gablet = [face.cell(left + 1, 1), face.cell(left + 2, 1)]
            scene.reserve(gablet, range(z + 3, z + 5))
            sill(scene, face, (left + 1, 1, LIGHTS), SHADE)
        for a in (2, 13):
            sill(scene, face, (a, 1, LIGHTS), SHADE, width=1)
        eaves(scene, face)


def eaves(scene: Scene, face: Face) -> None:
    """Gild the belfry's eaves and raise a pinnacle on each corner."""
    for a in range(1, 15, 2):
        scene.put_on(face, Piece("4073", (1, 1), GOLD), (a, 0, ROOF))
        scene.put_on(face, Piece("54200", (1, 1), GOLD), (a + 1, 0, ROOF))
    for rise, part, color in (
        (0, "3062", STONE),
        (3, "3062", STONE),
        (6, "4073", GOLD),
        (7, "3062", GOLD),
        (10, "98138", GOLD),
    ):
        scene.put_on(face, Piece(part, (1, 1), color), (0, 0, ROOF + rise))


def slopes(scene: Scene, face: Face, cells: list[int], at: Cell) -> None:
    """Cover a row of roof squares with Slope 75, two studs wide where they fit.

    ``at`` holds the row's inset and its height.
    """
    inset, z = at
    index = 0
    while index < len(cells):
        a = cells[index]
        if index + 1 < len(cells) and cells[index + 1] == a + 1:
            scene.put_on(face, Piece("3684a", (2, 2), SLATE), (a, inset, z))
            index += 2
        else:
            scene.put_on(face, Piece("4460b", (1, 2), SLATE), (a, inset, z))
            index += 1


def hip(scene: Scene, face: Face, inset: int, z: int) -> None:
    """Build one course of a hip: a column of round bricks under a gilded crocket.

    The east and west rows stop a stud short of the hips, where a second column of
    bricks closes each course.
    """
    for rise, color in ((0, SLATE), (3, SLATE), (6, GOLD)):
        scene.put_on(face, Piece("3062", (1, 1), color), (inset, inset, z + rise))
    scene.put_on(face, Piece("54200", (1, 1), GOLD), (inset, inset, z + COURSE))
    if face.quarter % 2:
        for a in (inset + 1, SHAFT - inset - 2):
            for rise in range(0, COURSE, 3):
                scene.put_on(face, Piece("3005", (1, 1), SLATE), (a, inset, z + rise))
            scene.put_on(face, Piece("54200", (1, 1), GOLD), (a, inset, z + COURSE))


def roof(scene: Scene) -> None:
    """Build the spire's roof: five courses of Slope 75 between crocketed hips."""
    for face in FACES:
        for course in range(5):
            inset, z = course + 1, ROOF + COURSE * course
            hip(scene, face, inset, z)
            first = inset + 1 + face.quarter % 2
            cells = list(range(first, SHAFT - first))
            if course in {1, 3}:
                lucarne(scene, face, inset, z)
                cells = [a for a in cells if a not in {7, 8}]
            slopes(scene, face, cells, (inset, z))


def lucarne(scene: Scene, face: Face, inset: int, z: int) -> None:
    """Build a small gabled lucarne in the middle of a roof course."""
    scene.put_on(face, Piece("3022", (2, 2), SLATE), (7, inset, z))
    scene.put_on(face, Piece("3004", (2, 1), INK, "R90"), (7, inset, z + 1))
    scene.put_on(face, Piece("3023", (2, 1), GOLD, "R90"), (7, inset, z + 4))
    scene.put_on(face, Piece("54200", (1, 1), GOLD, "R270"), (7, inset, z + 5))
    scene.put_on(face, Piece("54200", (1, 1), GOLD, "R90"), (8, inset, z + 5))
    for rise, part in ((1, "3004"), (4, "3023"), (5, "3023"), (6, "3004")):
        scene.put_on(face, Piece(part, (2, 1), SLATE, "R90"), (7, inset + 1, z + rise))


def lantern(scene: Scene) -> None:
    """Build the Ayrton Light's lantern: gilded posts under staggered blue arches."""
    low = TOWER_X + 6, TOWER_Y + 6
    scene.put("3031", (*low, LANTERN), SLATE)
    arch = Piece("3659", (4, 1), BLUE, "R90")
    for face in FACES:
        for rise in (1, 4):
            scene.put_on(face, Piece("3062", (1, 1), GOLD), (6, 6, LANTERN + rise))
        if face.quarter % 2:  # the east and west arches sit under the others
            scene.put_on(face, arch, (6, 6, LANTERN + 7))
            scene.put_on(face, Piece("3004", (2, 1), BLUE, "R90"), (7, 6, LANTERN + 10))
        else:
            scene.put_on(face, arch, (6, 6, LANTERN + 10))
        scene.put_on(face, Piece("3062", (1, 1), GOLD), (6, 6, SPIRE + 1))
        scene.put_on(face, Piece("98138", (1, 1), GOLD), (6, 6, SPIRE + 4))
    middle = TOWER_X + 7, TOWER_Y + 7
    for rise in (1, 4, 7):
        scene.builder.place(
            "3941",
            at=(*middle, BASE + LANTERN + rise),
            color=LIGHT,
            id=f"ayrton-light-{rise}",
        )
    scene.put("3003", (*middle, LANTERN + 10), LIGHT)
    scene.put("3031", (*low, SPIRE), BLUE)


def spire(scene: Scene) -> None:
    """Taper the spire from round bricks to a needle, an orb and a cross."""
    middle = TOWER_X + 7, TOWER_Y + 7
    for rise, part, color in (
        (1, "3941", SLATE),
        (4, "3941", SLATE),
        (7, "4032", GOLD),
        (8, "87580", SLATE),  # a jumper centers the needle
    ):
        scene.put(part, (*middle, SPIRE + rise), color)
    x, y = TOWER_X + 7.5, TOWER_Y + 7.5
    scene.put("3062", (x, y, SPIRE + 9), SLATE)
    scene.put("4073", (x, y, SPIRE + 12), GOLD)
    scene.builder.place("3062", at=(x, y, BASE + SPIRE + 13), color=GOLD, id="orb")
    scene.builder.place("47905", at=(x, y, BASE + SPIRE + 16), color=GOLD, id="cross")
    scene.put("4073", (x, y, SPIRE + 19), GOLD)
    scene.put("98138", (x, y - 0.4, SPIRE + 16.5), GOLD, "+x+z")  # the cross's arms
    scene.put("98138", (x, y + 1, SPIRE + 16.5), GOLD, "-x+z")


# The palace.

PALACE_X = range(3, 39)
PALACE_Y = range(25, 38)
FLOORS = ((8, 17), (23, 35), (41, 50))  # the bottom of each window and of its arch
PARAPET = 55


@dataclass(frozen=True)
class Side:
    """One side of the palace: squares along it, and ``d`` studs in from its front."""

    along: range
    front: int
    inward: int  # 1 or -1: the way in from the front
    across: bool  # whether the side runs along x
    first: int  # the left leg of the first window's arch

    def cell(self, along: int, d: int) -> Cell:
        """Return the world square ``along`` the side and ``d`` studs in."""
        if self.across:
            return along, self.front + self.inward * d
        return self.front + self.inward * d, along

    def bay(self, along: int) -> int:
        """Return where a square lies in its bay: 0 and 3 are legs, 4 a buttress."""
        return (along - self.first) % 5


SIDES = (
    Side(PALACE_X, PALACE_Y.start, 1, across=True, first=4),
    Side(PALACE_X, PALACE_Y.stop - 1, -1, across=True, first=4),
    Side(PALACE_Y, PALACE_X.start, 1, across=False, first=27),
)


def palace_color(bay: int, d: int, z: int) -> str | None:
    """Return the color of a voxel of the palace's walls, ``d`` studs deep."""
    if z < 6 or z in {21, 39, PARAPET - 1}:
        return SHADE
    for bottom, arch in FLOORS:
        if bay in {1, 2} and bottom <= z < arch + 3:
            if d == 0:
                return STONE if z == (bottom + arch) // 2 else None
            return INK if z < arch + 2 else STONE
    return STONE


def walls(scene: Scene, side: Side) -> None:
    """Lay one side of the palace, with Arch 1 x 4 over two-tier windows."""
    for along in side.along:
        for d in (0, 1):
            for z in range(PARAPET):
                if (color := palace_color(side.bay(along), d, z)) is not None:
                    scene.voxels[(*side.cell(along, d), z)] = color
    rotation = "R90" if side.across else "R0"
    for left in range(side.first, side.along.stop - 3, 5):
        for bottom, arch in FLOORS:
            cells = [side.cell(left + i, 0) for i in range(4)]
            scene.put("3659", (*min(cells), arch), STONE, rotation)
            scene.reserve(cells, range(arch, arch + 3))
            for z in (bottom, (bottom + arch) // 2 + 1):  # tiled sills
                scene.put("3069", (*min(cells[1:3]), z), STONE, rotation)
                scene.reserve(cells[1:3], range(z, z + 1))


def battlements(scene: Scene, side: Side) -> None:
    """Crown a long side with a crenellated parapet, and buttresses with pinnacles."""
    for along in side.along:
        for z in range(PARAPET, PARAPET + 3):
            if along % 2 == 0 or z == PARAPET:
                scene.voxels[(*side.cell(along, 0), z)] = STONE
        scene.voxels[(*side.cell(along, 0), PARAPET + 3)] = SHADE
        if side.bay(along) != 4:
            continue
        x, y = side.cell(along, -1)
        for z in range(PARAPET + 6):
            scene.voxels[x, y, z] = STONE if z % 18 else SHADE
        for rise, part, color in (
            (6, "3062", STONE),
            (9, "3062", STONE),
            (12, "4073", SHADE),
            (13, "98138", GOLD),
        ):
            scene.put(part, (x, y, PARAPET + rise), color)


def palace(scene: Scene) -> None:
    """Build a slice of the palace's wing: arched windows, buttresses and pinnacles."""
    for side in SIDES:
        walls(scene, side)
        if side.across:
            battlements(scene, side)
    for y in PALACE_Y:
        for z in range(PARAPET):
            scene.voxels[PALACE_X.stop - 1, y, z] = STONE
    for course in range(4):  # the west gable
        for y in range(PALACE_Y.start + 3 + course, PALACE_Y.stop - 3 - course):
            for z in range(PARAPET + 3 * course, PARAPET + 3 * course + 3):
                scene.voxels[PALACE_X.start, y, z] = STONE
    palace_roof(scene)


def palace_roof(scene: Scene) -> None:
    """Lay the palace's pitched roof, with dormers and a gilded ridge cresting."""
    dormers = range(5, PALACE_X.stop, 10)
    for course in range(4):
        z = PARAPET + 3 * course
        south, north = PALACE_Y.start + 1 + course, PALACE_Y.stop - 3 - course
        for x in range(PALACE_X.start, PALACE_X.stop, 2):
            scene.put("3039", (x, north, z), SLATE, "R180")
            if course == 1 and x in dormers:
                dormer(scene, x, south, z)
            else:
                scene.put("3039", (x, south, z), SLATE)
    ridge = PARAPET + 12
    for x in PALACE_X:
        scene.put("3623", (x, PALACE_Y.start + 5, ridge), SLATE)
        if x % 3 == 0:
            scene.put("4073", (x, PALACE_Y.start + 6, ridge + 1), GOLD)


def dormer(scene: Scene, x: int, y: int, z: int) -> None:
    """Build a gabled dormer window in place of one roof slope."""
    scene.put("3022", (x, y, z), SLATE)
    scene.put("3004", (x, y, z + 1), INK, "R90")
    scene.put("3023", (x, y + 1, z + 1), SLATE, "R90")
    scene.put("3023", (x, y + 1, z + 2), SLATE, "R90")
    scene.put("54200", (x, y, z + 4), STONE, "R270")
    scene.put("54200", (x + 1, y, z + 4), STONE, "R90")


# The street.

ROAD = 12  # the road fills y from 0 up to ROAD
ASPHALT, PAVING = "Dark Bluish Gray", "Light Bluish Gray"
ZEBRA = range(26, 30)
FLAT = {  # tiles by footprint, the shorter side first
    (2, 6): "69729",
    (2, 4): "87079",
    (1, 8): "4162",
    (1, 6): "6636",
    (2, 2): "3068",
    (1, 4): "2431",
    (1, 3): "63864",
    (1, 2): "3069",
    (1, 1): "3070",
}


def pave(scene: Scene, squares: dict[Cell, str]) -> None:
    """Cover squares of the baseplates with tiles of their colors, largest first."""
    free = dict(squares)
    for x, y in sorted(squares, key=lambda square: (square[1], square[0])):
        if (x, y) not in free:
            continue
        color = free[x, y]
        for (short, long), part in FLAT.items():
            for width, depth, rotation in ((short, long, "R0"), (long, short, "R90")):
                cells = [(x + i, y + j) for i in range(width) for j in range(depth)]
                if scene.made(part, color) and all(
                    free.get(cell) == color for cell in cells
                ):
                    scene.put(part, (x, y, 0), color, rotation)
                    for cell in cells:
                        del free[cell]
                    break
            else:
                continue
            break


def road_color(x: int, y: int) -> str:
    """Return the color of a road square: asphalt, a lane line or a zebra stripe."""
    if x in ZEBRA:
        return DIAL if y % 2 == 0 else ASPHALT
    if y == ROAD - 1:
        return "Yellow"
    if y == ROAD // 2 and x % 8 < 3:
        return DIAL
    return ASPHALT


def ground(scene: Scene) -> None:
    """Lay the baseplates, then tile the road and the pavement around what stands."""
    scene.builder.place("3857", at=(0, 0, 0), color=PAVING, id="baseplate-west")
    scene.builder.place("3867", at=(0, 32, 0), color=PAVING, id="baseplate-north")
    scene.builder.place("4186", at=(16, 0, 0), color=PAVING, id="baseplate")
    taken = {(x, y) for x, y, z in scene.voxels.keys() | scene.reserved if z == 0}
    pave(
        scene,
        {
            (x, y): road_color(x, y) if y < ROAD else PAVING
            for x in range(64)
            for y in range(48)
            if (x, y) not in taken
        },
    )


def wheels(scene: Scene, corner: Cell, width: int, axles: tuple[int, ...]) -> None:
    """Place bricks with side studs on a vehicle's axles, and round tiles as wheels."""
    x, y = corner
    for u in axles:
        scene.put("87087", (x + u, y, 1), INK)
        scene.put("87087", (x + u, y + width - 1, 1), INK, "R180")
        scene.put("98138", (x + u, y - 0.4, 1.5), INK, "+x+z")
        scene.put("98138", (x + u, y + width, 1.5), INK, "-x+z")
        scene.reserve([(x + u, y), (x + u, y + width - 1)], range(1, 4))


PALETTE = {
    "r": RED,
    "k": INK,
    "w": DIAL,
    "b": "Trans-Light Blue",
    "c": "Trans-Clear",
    "o": "Bright Light Orange",
}


def vehicle(scene: Scene, corner: Cell, size: Cell, looks: str) -> None:
    """Add a vehicle's voxels, standing on a road plate, from rows of colors.

    ``looks`` holds one row per plate, bottom first: each letter colors a square along
    the vehicle, across its whole width, and a dot leaves it empty.
    """
    x, y = corner
    length, width = size
    for u in range(length):
        for w in range(width):
            scene.voxels[x + u, y + w, 0] = ASPHALT
    for z, row in enumerate(looks.split(), start=1):
        for u, key in enumerate(row):
            for w in range(width):
                if key != ".":
                    scene.voxels[x + u, y + w, z] = PALETTE[key]


BUS = """
rrrrrrrrrrrrrr rrrrrrrrrrrrrw rrrrrrrrrrrrrr rrrrrrrrrrrrrr rkkkrkkkrkkkkk
rkkkrkkkrkkkkk rkkkrkkkrkkkkk rrrrrrrrrrrrrr rrrrrrrrrrrrrr kkkkkkkkkkkkkk
kkkkkkkkkkkkkk kkkkkkkkkkkkko rrrrrrrrrrrrrr
"""
CAB = "kkkkkk wkkkkk kkkkkk .cbbk. .kkkk."


def bus(scene: Scene, corner: Cell, *, east: bool) -> None:
    """Add a double-decker bus heading east or west, its roof rounded at both ends."""
    x, y = corner
    rows = BUS if east else " ".join(row[::-1] for row in BUS.split())
    vehicle(scene, corner, (14, 3), rows)
    wheels(scene, corner, 3, (2, 3, 11) if east else (2, 10, 11))
    for w in range(3):
        scene.put("11477", (x, y + w, 14), RED, "R270")
        scene.put("4162", (x + 2, y + w, 14), RED, "R90")
        scene.put("3069", (x + 10, y + w, 14), RED, "R90")
        scene.put("11477", (x + 12, y + w, 14), RED, "R90")


def traffic(scene: Scene) -> None:
    """Add two red double-decker buses and a black cab, driving on the left."""
    bus(scene, (9, 7), east=True)
    bus(scene, (48, 1), east=False)
    vehicle(scene, (38, 2), (6, 2), CAB)
    wheels(scene, (38, 2), 2, (1, 4))
    scene.put("15573", (40, 2, 6), INK)  # a jumper centers the taxi sign
    scene.put("4073", (40, 2.5, 7), LIGHT)


PEOPLE = (  # where people stand, and the colors of their coats and legs
    (11, 15, "Lime", BLUE),
    (15, 18, "Magenta", INK),
    (16, 18, "Medium Azure", SLATE),
    (23, 14, "Yellow", BLUE),
    (27, 4, RED, INK),
    (28, 7, "Blue", SLATE),
    (32, 16, "Orange", BLUE),
    (37, 15, DIAL, BLUE),
    (41, 17, "Dark Pink", INK),
    (45, 14, "Dark Turquoise", SLATE),
    (50, 19, RED, INK),
    (53, 15, "Sand Blue", BLUE),
    (58, 18, "Yellow", INK),
    (62, 25, "Dark Green", SLATE),
    (61, 33, "Medium Azure", BLUE),
)
SKIN = ("Nougat", "Medium Nougat", "Reddish Brown", "Nougat", "Dark Orange")


def people(scene: Scene) -> None:
    """Add people on the pavement and on the zebra crossing."""
    for index, (x, y, coat, legs) in enumerate(PEOPLE):
        scene.put("3024", (x, y, 0), road_color(x, y) if y < ROAD else PAVING)
        scene.put("4073", (x, y, 1), legs)
        scene.put("4073", (x, y, 2), legs)
        scene.put("3062", (x, y, 3), coat)
        scene.put("98138", (x, y, 6), SKIN[index % len(SKIN)])
        scene.reserve([(x, y)], range(1))


def lamp(builder: ModelBuilder) -> None:
    """Define an ornate lamp standard with two lanterns on a crossbar."""
    lamp = builder.component("lamp")
    lamp.place("4073", at=(1, 0, 0), color=INK)
    for z in (1, 4, 7):
        lamp.place("3062", at=(1, 0, z), color=INK)
    lamp.place("4073", at=(1, 0, 10), color=GOLD)
    lamp.place("3062", at=(1, 0, 11), color=INK)
    lamp.place("3623", at=(0, 0, 14), color=INK, rotation="R90")
    for x in (0, 2):
        lamp.place("3062", at=(x, 0, 15), color=LIGHT)
        lamp.place("4073", at=(x, 0, 18), color=INK)
        lamp.place("98138", at=(x, 0, 19), color=GOLD)
    lamp.place("4073", at=(1, 0, 15), color=INK)
    lamp.place("98138", at=(1, 0, 16), color=GOLD)


def beacon(builder: ModelBuilder) -> None:
    """Define a Belisha beacon: a striped pole under an amber globe."""
    pole = builder.component("beacon")
    for z in range(9):
        pole.place("4073", at=(0, 0, z), color=INK if z % 2 == 0 else DIAL)
    pole.place("4073", at=(0, 0, 9), color="Trans-Orange")
    pole.place("4073", at=(0, 0, 10), color="Trans-Orange")
    pole.place("98138", at=(0, 0, 11), color="Trans-Orange")


def kiosk(scene: Scene, corner: Cell) -> None:
    """Build a red telephone box under a roof of four cheese slopes."""
    x, y = corner
    for z, part, color in (
        (0, "3022", RED),
        (1, "3003", RED),
        (4, "3003", "Trans-Clear"),
        (7, "3022", DIAL),
        (8, "3022", RED),
    ):
        scene.put(part, (x, y, z), color)
    for (i, j), rotation in zip(
        ((0, 0), (1, 0), (1, 1), (0, 1)), QUARTERS, strict=True
    ):
        scene.put("54200", (x + i, y + j, 9), RED, rotation)
    scene.reserve([(x + i, y + j) for i in range(2) for j in range(2)], range(1))


def furniture(scene: Scene) -> None:
    """Add lamps, Belisha beacons, a telephone box and gilded railings."""
    lamp(scene.builder)
    beacon(scene.builder)
    for x in (6, 20, 34, 48, 60):
        scene.builder.instance("lamp", at=(x - 1, ROAD + 1, BASE))
        scene.reserve([(x, ROAD + 1)], range(1))
    for x in (ZEBRA.start - 1, ZEBRA.stop):
        scene.builder.instance("beacon", at=(x, ROAD + 1, BASE))
        scene.reserve([(x, ROAD + 1)], range(1))
    kiosk(scene, (34, 17))
    railing = TOWER_Y - 2  # the railings run past the palace and the tower
    posts = range(PALACE_X.start, TOWER_X + SHAFT + 1)
    for x in posts:
        scene.put("3062", (x, railing, 0), INK)
        scene.put("4073", (x, railing, 4), GOLD)
    for x in range(posts.start, posts.stop, 6):
        scene.put("3666", (x, railing, 3), INK, "R90")
    scene.reserve([(x, railing) for x in posts], range(1))


# Plane trees.

LEAVES = ("Dark Green", "Green", "Green", "Lime")
CROWN = (  # the crown's lumps: offsets from its center and radii, in studs
    (0.0, 0.0, 0.0, 5.5),
    (3.5, 1.5, -1.0, 4.0),
    (-3.5, 1.0, 0.5, 4.0),
    (1.0, -3.5, 1.0, 4.0),
    (-1.5, 3.5, 2.0, 4.0),
    (0.5, 0.0, 5.0, 4.0),
)
NEIGHBORS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def noise(x: int, y: int, z: int) -> float:
    """Return a repeatable pseudo-random number from 0 to 1 for a voxel."""
    value = (x * 73_856_093) ^ (y * 19_349_663) ^ (z * 83_492_791)
    return (value % 1_000) / 1_000


def crown(center: Point, low: int) -> set[Voxel]:
    """Return the voxels of a lumpy crown that narrows down to its trunk."""
    cx, cy, cz = center
    voxels: set[Voxel] = set()
    for x in range(int(cx) - 10, int(cx) + 10):
        for y in range(int(cy) - 10, int(cy) + 10):
            for z in range(low, low + 45):
                px, py, pz = x + 0.5 - cx, y + 0.5 - cy, (z + 0.5) / 2.5 - cz
                rough = 0.8 * noise(x // 2, y // 2, z // 3) - 0.4
                if hypot(px, py) <= 1.5 + 0.9 * (z - low) and any(
                    (px - dx) ** 2 + (py - dy) ** 2 + (pz - dz) ** 2 <= (r + rough) ** 2
                    for dx, dy, dz, r in CROWN
                ):
                    voxels.add((x, y, z))
    return voxels


def prune(leaves: set[Voxel], trunk: set[Voxel]) -> None:
    """Drop, layer by layer, the leaves that nothing below or beside could hold."""
    for z in sorted({z for _, _, z in leaves}):
        held = leaves | trunk
        for x, y, _ in [voxel for voxel in leaves if voxel[2] == z]:
            if (x, y, z - 1) not in held and not any(
                (x + i, y + j, z) in leaves and (x + i, y + j, z - 1) in held
                for i, j in NEIGHBORS
            ):
                leaves.discard((x, y, z))


def tree(scene: Scene, corner: Cell, top: int) -> None:
    """Grow a plane tree: a round trunk under a lumpy crown in mixed greens.

    The crown's underside, and the squares beside it, stay dark green, so the fill
    reaches back over each overhang in parts of one color.
    """
    x0, y0 = corner
    for z in range(0, top, 3):
        scene.put("3941", (x0, y0, z), SHADE)
    scene.reserve([(x0 + i, y0 + j) for i in range(2) for j in range(2)], range(top))
    trunk = {
        (x0 + i, y0 + j, z) for i in range(2) for j in range(2) for z in range(top + 8)
    }
    for x, y, z in trunk:  # the trunk rises on into the crown
        if z >= top:
            scene.voxels[x, y, z] = SHADE
    leaves = crown((x0 + 1, y0 + 1, top / 2.5 + 5), top) - trunk
    prune(leaves, trunk)
    hanging = {(x, y, z) for x, y, z in leaves if (x, y, z - 1) not in leaves | trunk}
    for x, y, z in leaves:
        if any((x + i, y + j, z) in hanging for i, j in ((0, 0), *NEIGHBORS)):
            scene.voxels[x, y, z] = LEAVES[0]
        else:
            shade = int((z - top) / 35 * 2.4 + noise(x, y, z) * 1.5)
            scene.voxels[x, y, z] = LEAVES[min(3, shade)]


def build() -> ModelBuilder:
    """Build the tower, the palace's wing and the street on three baseplates."""
    builder = ModelBuilder("elizabeth-tower")
    scene = Scene(builder)
    shaft(scene)
    stage(scene)
    belfry(scene)
    roof(scene)
    lantern(scene)
    spire(scene)
    palace(scene)
    traffic(scene)
    furniture(scene)
    people(scene)
    tree(scene, (6, 16), 21)
    tree(scene, (59, 43), 24)
    ground(scene)
    scene.fill()
    return builder
