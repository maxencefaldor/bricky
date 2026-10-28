# Copyright 2026 Maxence Faldor
"""Hokusai's "The Great Wave off Kanagawa" (about 1831): a framed relief on a stand.

- The picture is 60 studs wide and 102 plates tall. Each pixel is one stud wide and one
  plate tall, so the print keeps its proportions, about 1.47 to 1.
- The script paints the print on those pixels from curves, each pixel with a color and a
  depth, then fills the voxels behind every pixel with bricks and plates
  (``builder.fill``).
- The relief: the sky sits deepest, Mount Fuji and the far sea stand a stud forward, and
  the great wave rises toward its crest, whose claws of foam stand before the frame.
- Curved slopes and cheese slopes round every ledge of the relief. White round tiles on
  bricks with a stud on their side are drops of spray.
- The black frame steps back to a Pearl Gold liner under a top beaded with curved
  slopes. The stand is a blind arcade of arches under a tiled tray, braced from behind
  by stepped buttresses capped with slopes.

Run: ``uv run bricky build examples/great_wave.py``
"""

from collections.abc import Iterator
from dataclasses import dataclass
from itertools import pairwise
from math import atan2, cos, floor, hypot, inf, sin

from bricky import ModelBuilder

type Point = tuple[float, float]
"""A point of the print: x runs from 0 to SPAN, left to right, and y from 0 to 1, up."""

type Pixel = tuple[int, int]
"""A column and a row of the picture."""

type Canvas = dict[Pixel, tuple[str, int]]
"""Each pixel's color and depth, in studs behind the crest's front."""

type Voxels = dict[tuple[int, int, int], str]
"""The color of each voxel to fill, keyed by its corner in studs, studs and plates."""

WIDTH, HEIGHT = 60, 102  # the picture, in studs and plates
SPAN = WIDTH * 2.5 / HEIGHT  # the print's width over its height: a stud is 2.5 plates
BACK = 8  # each pixel fills the voxels from its depth back to BACK - 1, the board
SKY_DEPTH, FAR_DEPTH = 6, 5

SKY, CLOUD, PAPER, INK = "Tan", "Dark Tan", "Bright Light Yellow", "Dark Brown"
DEEP, WATER, SHALLOW, FOAM = "Dark Blue", "Blue", "Medium Blue", "White"
MOUNTAIN, SNOW = "Light Bluish Gray", "White"
HULL, KEEL, ROWER = "Tan", "Dark Tan", "Dark Blue"
FRAME_COLOR, LINER_COLOR, BOARD_COLOR = "Black", "Pearl Gold", "Dark Brown"
STAND_COLOR = "Reddish Brown"

BORDER, RAIL = 2, 5  # the frame's sides, in studs, and its rails, in plates
FRAME_FRONT = 3  # the frame's front, as a depth: the crest stands 3 studs before it
FRONT, STAND = 5, 4  # the y of depth 0, and the z of the tray the frame stands on
STAND_WEST, STAND_EAST = -2, WIDTH + 2 * BORDER + 2  # the stand spans x, west to east
STAND_NORTH = 20  # and y, from 0 to STAND_NORTH - 1
BUTTRESSES = (6, 31, 56)  # the x of each buttress behind the frame, 2 studs wide
TILES = {8: "4162", 6: "6636", 4: "2431", 2: "3069", 1: "3070"}  # Tiles 1 x N

HORIZON = 0.215

# The great wave's outline. Its back rises from the left edge to the crest, the crest
# curls over to the lip's tip, and the lip's underside returns into the face, which
# falls into the trough before Mount Fuji.
BACK_EDGE = [
    (-0.05, 0.47),
    (0.08, 0.58),
    (0.20, 0.71),
    (0.33, 0.83),
    (0.46, 0.905),
    (0.58, 0.935),
]
CREST = [(0.70, 0.93), (0.80, 0.89), (0.88, 0.825), (0.93, 0.755), (0.955, 0.69)]
LIP = [(0.955, 0.69), (0.92, 0.675), (0.87, 0.685), (0.81, 0.70), (0.75, 0.68)]
FACE = [
    (0.68, 0.65),
    (0.63, 0.59),
    (0.61, 0.52),
    (0.62, 0.46),
    (0.67, 0.40),
    (0.74, 0.35),
    (0.82, 0.29),
    (0.90, 0.245),
    (0.98, 0.22),
    (1.06, 0.21),
]
TROUGH = (0.62, 0.46)  # the trough's water lies right of and below this point

# The line between the wave's dark back and its lighter, hollow face.
SHADE = [
    (0.82, 0.71),
    (0.62, 0.63),
    (0.48, 0.50),
    (0.37, 0.32),
    (0.28, 0.12),
    (0.22, -0.1),
]

# The small wave in the foreground, a peak that echoes Mount Fuji.
SMALL_WAVE = [
    (0.26, -0.02),
    (0.34, 0.12),
    (0.41, 0.25),
    (0.46, 0.35),
    (0.50, 0.42),
    (0.54, 0.40),
    (0.58, 0.34),
    (0.63, 0.25),
    (0.69, 0.15),
    (0.76, 0.05),
    (0.80, -0.02),
]

# The swell on the right, which lifts the third boat.
SWELL = [
    (1.04, 0.205),
    (1.10, 0.25),
    (1.18, 0.30),
    (1.28, 0.345),
    (1.38, 0.37),
    (1.50, 0.385),
]

FUJI = (1.02, 0.40)  # the summit
FUJI_HALF_BASE = 0.15

# Each boat: its bow, its stern, and the hull's thickness.
BOATS = (
    ((0.03, 0.12), (0.42, 0.20), 0.065),
    ((0.58, 0.335), (0.84, 0.26), 0.06),
    ((1.12, 0.25), (1.44, 0.33), 0.06),
)

# Drops of spray falling from the claws toward Mount Fuji.
SPRAY = [
    (0.80, 0.56),
    (0.85, 0.61),
    (0.88, 0.52),
    (0.92, 0.585),
    (0.95, 0.50),
    (0.99, 0.56),
    (1.02, 0.63),
    (1.04, 0.49),
    (1.08, 0.57),
    (1.12, 0.66),
    (1.13, 0.51),
    (1.18, 0.60),
    (0.84, 0.45),
    (0.91, 0.43),
    (1.22, 0.53),
    (0.98, 0.69),
]


@dataclass(frozen=True, slots=True)
class Talon:
    """A finger of foam that curls as it reaches out, tapering to its tip."""

    start: Point
    heading: float
    """The direction it sets out in, in radians counterclockwise from the right."""

    bend: float
    """How fast it curls, in radians per unit of length; negative curls clockwise."""

    length: float
    width: float


def catmull(
    before: float, start: float, end: float, after: float, fraction: float
) -> float:
    """Interpolate from start to end, bending toward their neighbors (Catmull-Rom)."""
    return 0.5 * (
        2 * start
        + (end - before) * fraction
        + (2 * before - 5 * start + 4 * end - after) * fraction**2
        + (3 * start - before - 3 * end + after) * fraction**3
    )


def spline(points: list[Point], steps: int = 8) -> list[Point]:
    """Return a smooth curve through the points, as a polyline."""
    padded = [points[0], *points, points[-1]]
    curve: list[Point] = []
    for index in range(1, len(padded) - 2):
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = padded[index - 1 : index + 3]
        for step in range(steps):
            fraction = step / steps
            curve.append(
                (catmull(x0, x1, x2, x3, fraction), catmull(y0, y1, y2, y3, fraction))
            )
    curve.append(points[-1])
    return curve


def inside(polygon: list[Point], point: Point) -> bool:
    """Whether the point lies inside the polygon, by the even-odd rule."""
    x, y = point
    result = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            result = not result
    return result


def nearest(polyline: list[Point], point: Point) -> tuple[float, float]:
    """Return the distance from the point to the polyline, and the arc length there."""
    x, y = point
    best, position, walked = inf, 0.0, 0.0
    for (x1, y1), (x2, y2) in pairwise(polyline):
        run, rise = x2 - x1, y2 - y1
        length = hypot(run, rise)
        fraction = 0.0
        if length > 0:
            fraction = ((x - x1) * run + (y - y1) * rise) / length**2
            fraction = min(1.0, max(0.0, fraction))
        gap = hypot(x - x1 - fraction * run, y - y1 - fraction * rise)
        if gap < best:
            best, position = gap, walked + fraction * length
        walked += length
    return best, position


def walk(polyline: list[Point], position: float) -> tuple[Point, float]:
    """Return the point at an arc length along the polyline, and the heading there."""
    for (x1, y1), (x2, y2) in pairwise(polyline):
        length = hypot(x2 - x1, y2 - y1)
        if position <= length or (x2, y2) == polyline[-1]:
            fraction = position / length if length > 0 else 0.0
            point = x1 + fraction * (x2 - x1), y1 + fraction * (y2 - y1)
            return point, atan2(y2 - y1, x2 - x1)
        position -= length
    return polyline[-1], 0.0


def arc_length(polyline: list[Point]) -> float:
    """Return the length of the polyline."""
    return sum(hypot(x2 - x1, y2 - y1) for (x1, y1), (x2, y2) in pairwise(polyline))


def smooth(value: float) -> float:
    """Ease a value from 0 to 1, clamped (smoothstep)."""
    value = min(1.0, max(0.0, value))
    return value * value * (3 - 2 * value)


def pixels() -> Iterator[tuple[Pixel, Point]]:
    """Yield every pixel of the picture with the point of the print at its center."""
    for column in range(WIDTH):
        for row in range(HEIGHT):
            yield (column, row), ((column + 0.5) * SPAN / WIDTH, (row + 0.5) / HEIGHT)


def contours(values: dict[Pixel, float], period: float) -> set[Pixel]:
    """Return the pixels that contour lines cross, one line every period of the value.

    Where a line passes between two neighboring pixels, the one with the larger value
    takes it, so each line is one pixel thick whichever way it runs.
    """
    lines: set[Pixel] = set()
    for (column, row), value in values.items():
        for neighbor in ((column + 1, row), (column, row + 1)):
            other = values.get(neighbor)
            if other is not None and floor(value / period) != floor(other / period):
                lines.add((column, row) if value > other else neighbor)
    return lines


def paint_talon(canvas: Canvas, talon: Talon, depth: int) -> None:
    """Paint a finger of foam, edged in blue where it crosses foam painted before."""
    spine: list[tuple[Point, float]] = []
    (x, y), heading = talon.start, talon.heading
    count = 16
    step = talon.length / count
    for index in range(count + 1):
        spine.append(((x, y), talon.width * (1 - 0.7 * index / count)))
        x, y = x + step * cos(heading), y + step * sin(heading)
        heading += talon.bend * step
    for pixel, (x, y) in pixels():
        # Vertical distances count 1.3 times, so a finger reads a little slimmer.
        gap = min(
            hypot(x - spine_x, (y - spine_y) * 1.3) - half
            for (spine_x, spine_y), half in spine
        )
        if gap < 0:
            canvas[pixel] = FOAM, depth
        elif gap < 0.012 and canvas[pixel][0] == FOAM:
            canvas[pixel] = SHALLOW, canvas[pixel][1]


def paint_sky(canvas: Canvas) -> None:
    """Paint the sky, darker in bands at the top and in a haze above the horizon."""
    for (column, row), (_, y) in pixels():
        band = y > 0.955 or (y > 0.915 and row % 2 == 0) or y < HORIZON + 0.03
        canvas[column, row] = (CLOUD if band else SKY), SKY_DEPTH


def paint_title(canvas: Canvas) -> None:
    """Paint the title's cartouche in the upper left, and the signature beside it."""
    for column in range(2, 7):
        for row in range(74, 99):
            border = column in {2, 6} or row in {74, 98}
            text = column in {3, 5} and 76 <= row <= 96 and row % 4 != 3
            color = CLOUD if border else INK if text else PAPER
            canvas[column, row] = color, FAR_DEPTH
    for row in range(80, 97):
        if row % 5 != 4:
            canvas[9, row] = INK, SKY_DEPTH


def paint_fuji(canvas: Canvas) -> None:
    """Paint Mount Fuji, snow streaking down its flanks, its middle a stud nearer."""
    summit_x, summit_y = FUJI
    for pixel, (x, y) in pixels():
        if not HORIZON - 0.02 <= y <= summit_y:
            continue
        fall = (summit_y - y) / (summit_y - HORIZON)
        half = 0.015 + (FUJI_HALF_BASE - 0.015) * fall**1.3
        if abs(x - summit_x) > half:
            continue
        snowline = 0.35 + 0.15 * cos((x - summit_x) * 60) ** 2
        ridge = abs(x - summit_x) < half * 0.45
        canvas[pixel] = (SNOW if fall < snowline else MOUNTAIN), FAR_DEPTH - ridge


def paint_sea(canvas: Canvas) -> None:
    """Paint the far sea below the horizon, streaked with lighter lines."""
    for (column, row), (_, y) in pixels():
        if y < HORIZON:
            canvas[column, row] = (SHALLOW if row % 4 == 1 else WATER), FAR_DEPTH


def paint_swell(canvas: Canvas) -> None:
    """Paint the swell on the right, its crest fringed with foam and small claws."""
    outline = spline(SWELL)
    polygon = [*outline, (SPAN + 0.1, -0.1), (SWELL[0][0], -0.1)]
    gaps = {
        pixel: nearest(outline, point)[0]
        for pixel, point in pixels()
        if inside(polygon, point)
    }
    lines = contours(gaps, 0.04)
    for pixel, gap in gaps.items():
        if gap < 0.015:
            canvas[pixel] = FOAM, 3
        else:
            color = SHALLOW if pixel in lines else DEEP if gap > 0.1 else WATER
            canvas[pixel] = color, 4
    for position in (0.12, 0.2, 0.28, 0.36):
        start, heading = walk(outline, position)
        paint_talon(canvas, Talon(start, heading + 1.3, -18.0, 0.045, 0.01), 2)


def wave_depth(point: Point, back_gap: float) -> int:
    """Return the great wave's depth: nearer toward its crest, rounded at its back."""
    x, y = point
    forward = 2 + 3 * smooth((y - 0.35) / 0.5) + smooth((x - 0.6) / 0.25)
    forward = min(forward, 1 + back_gap / 0.02)
    return max(0, SKY_DEPTH - round(forward))


def paint_great_wave(canvas: Canvas) -> None:
    """Paint the great wave: its dark back, its light face, its foam and the trough."""
    top = spline(BACK_EDGE + CREST)
    under = spline(LIP + FACE)
    polygon = [*top, *under, (FACE[-1][0], -0.1), (-0.1, -0.1)]
    face_zone = [*spline(SHADE), (SPAN + 0.1, -0.1), (SPAN + 0.1, SHADE[0][1])]
    region = {pixel: point for pixel, point in pixels() if inside(polygon, point)}
    tops = {pixel: nearest(top, point) for pixel, point in region.items()}
    faces = {pixel: nearest(under, point)[0] for pixel, point in region.items()}
    streaks = contours({pixel: gap for pixel, (gap, _) in tops.items()}, 0.065)
    ripples = contours(faces, 0.085)
    swells = contours(
        {pixel: y + 0.012 * sin(x * 22) for pixel, (x, y) in region.items()}, 0.04
    )
    for pixel, (x, y) in region.items():
        top_gap, along = tops[pixel]
        face_gap = faces[pixel]
        trough = x > TROUGH[0] and y < TROUGH[1]
        if top_gap < 0.012 + 0.012 * smooth((x - 0.35) / 0.3):
            color = FOAM
        elif face_gap < 0.012:
            color = FOAM if trough or y < 0.6 else SHALLOW
        elif trough:
            color = SHALLOW if pixel in swells else WATER
        elif inside(face_zone, (x, y)):
            vein = round(face_gap / 0.085) % 2 == 1 and along % 0.12 < 0.08
            color = (FOAM if vein else SHALLOW) if pixel in ripples else WATER
        elif pixel in streaks:
            lace = round(top_gap / 0.065) % 2 == 1 and along % 0.14 < 0.08
            color = FOAM if lace else WATER
        else:
            color = DEEP
        canvas[pixel] = color, 4 if trough else wave_depth((x, y), top_gap)
    paint_claws(canvas, top, spline(LIP))


def paint_claws(canvas: Canvas, top: list[Point], lip: list[Point]) -> None:
    """Paint the claws of foam along the crest, and the talons hanging from the lip."""
    length = arc_length(top)
    position = length * 0.25
    while position < length - 0.03:
        start, heading = walk(top, position)
        progress = smooth((start[0] - 0.25) / 0.7)
        talon = Talon(
            start,
            heading + 1.1,
            -12.0,
            0.035 + 0.05 * progress,
            0.009 + 0.006 * progress,
        )
        paint_talon(canvas, talon, wave_depth(start, 1.0) - 1)
        position += 0.05
    for offset, heading, reach in (
        (0.18, -1.4, 0.08),
        (0.12, -1.1, 0.11),
        (0.06, -0.7, 0.14),
        (0.0, -0.2, 0.16),
    ):
        start, _ = walk(lip, offset)
        paint_talon(canvas, Talon(start, heading, -17.0, reach, 0.018), -1)


def paint_boat(canvas: Canvas, bow: Point, stern: Point, thickness: float) -> None:
    """Paint a long boat a stud before the sea, its rowers a stud before the boat."""
    (x1, y1), (x2, y2) = bow, stern
    run, rise = x2 - x1, y2 - y1
    length = hypot(run, rise)
    hull: dict[Pixel, str] = {}
    for pixel, (x, y) in pixels():
        along = ((x - x1) * run + (y - y1) * rise) / length**2  # 0 at the bow
        if not 0 <= along <= 1:
            continue
        offset = ((y - y1) * run - (x - x1) * rise) / length
        half = thickness / 2 * min(1.0, along / 0.15, (1 - along) / 0.06)
        if abs(offset) < half:
            seat = 0.12 < along < 0.94 and pixel[0] % 2 == 0
            rower = seat and offset > 0.15 * half
            hull[pixel] = ROWER if rower else KEEL if offset < -half * 0.5 else HULL
    depth = min(canvas[pixel][1] for pixel in hull) - 1
    for pixel, color in hull.items():
        canvas[pixel] = color, depth - (color == ROWER)


def paint_small_wave(canvas: Canvas) -> None:
    """Paint the small wave in the foreground: a dark peak capped with foam, as Fuji."""
    outline = spline(SMALL_WAVE)
    peak = max(y for _, y in SMALL_WAVE)
    region = {pixel: point for pixel, point in pixels() if inside(outline, point)}
    gaps = {pixel: nearest(outline, point)[0] for pixel, point in region.items()}
    lines = contours(gaps, 0.07)
    for pixel, (x, y) in region.items():
        gap = gaps[pixel]
        if y > peak - 0.07 - 0.04 * cos(x * 70) ** 2:
            color = FOAM
        elif gap < 0.012:
            color = SHALLOW
        else:
            color = WATER if pixel in lines else DEEP
        canvas[pixel] = color, 3 if gap < 0.02 else 1 if color == FOAM else 2
    right = outline[len(outline) // 2 :]
    for position in (0.03, 0.08, 0.13):
        start, heading = walk(right, position)
        paint_talon(canvas, Talon(start, heading + 1.2, -16.0, 0.05, 0.011), 1)


def paint() -> Canvas:
    """Paint the print on the picture's pixels, from the sky forward."""
    canvas: Canvas = {}
    paint_sky(canvas)
    paint_title(canvas)
    paint_fuji(canvas)
    paint_sea(canvas)
    paint_swell(canvas)
    paint_boat(canvas, *BOATS[2])
    paint_great_wave(canvas)
    paint_boat(canvas, *BOATS[1])
    paint_small_wave(canvas)
    paint_boat(canvas, *BOATS[0])
    return canvas


def ledges(canvas: Canvas) -> Iterator[tuple[Pixel, str, int, int]]:
    """Yield each pixel whose top is a ledge, with its color, its depth and the reach.

    A ledge is the top of a pixel that stands before the two pixels above it; the reach
    is how far it stands before them, so a slope on it touches nothing above.
    """
    for (column, row), (color, depth) in canvas.items():
        if row + 2 < HEIGHT:
            reach = min(canvas[column, row + k][1] for k in (1, 2)) - depth
            if reach > 0:
                yield (column, row), color, depth, reach


def spray(canvas: Canvas) -> list[Pixel]:
    """Return the lowest pixel of each drop of spray that has three rows of open sky."""
    drops = [(round(x * WIDTH / SPAN - 0.5), round(y * HEIGHT - 0.5)) for x, y in SPRAY]
    return [
        (column, row)
        for column, row in drops
        if all(canvas[column, row + k][1] == SKY_DEPTH for k in range(3))
    ]


def picture_voxels(canvas: Canvas, drops: list[Pixel]) -> Voxels:
    """Return the relief's voxels, from each pixel's depth back to the board.

    The sky leaves a column of three voxels free behind each drop of spray, for the
    brick that holds it.
    """
    held = {(column, row + k) for column, row in drops for k in range(3)}
    return {
        (BORDER + column, FRONT + depth, STAND + RAIL + row): (
            color if depth < BACK - 1 else BOARD_COLOR
        )
        for (column, row), (color, front) in canvas.items()
        for depth in range(front, BACK)
        if depth != SKY_DEPTH or (column, row) not in held
    }


def frame_voxels() -> Voxels:
    """Return the frame's voxels: a molding that steps back to a liner."""
    voxels: Voxels = {}
    width, height = WIDTH + 2 * BORDER, HEIGHT + 2 * RAIL
    for x in range(width):
        for z in range(height):
            across, up = min(x, width - 1 - x), min(z, height - 1 - z)
            if across >= BORDER and up >= RAIL:
                continue
            outer = across < BORDER - 1 or up < RAIL - 2
            for depth in range(FRAME_FRONT + (not outer), BACK):
                liner = not outer and depth == FRAME_FRONT + 1
                color = LINER_COLOR if liner else FRAME_COLOR
                voxels[x, FRONT + depth, STAND + z] = color
    return voxels


def place_frame_top(builder: ModelBuilder) -> None:
    """Bead the frame's top with curved slopes, front and back, either side of tiles."""
    z = STAND + HEIGHT + 2 * RAIL
    for x in range(0, WIDTH + 2 * BORDER, 2):
        builder.place("15068", at=(x, FRONT + FRAME_FRONT, z), color=FRAME_COLOR)
        builder.place(
            "15068", at=(x, FRONT + BACK - 2, z), rotation="R180", color=FRAME_COLOR
        )
    for x in range(0, WIDTH + 2 * BORDER, 8):
        builder.place(
            "4162",
            at=(x, FRONT + FRAME_FRONT + 2, z),
            rotation="R90",
            color=FRAME_COLOR,
        )


def place_relief_details(builder: ModelBuilder, canvas: Canvas) -> None:
    """Hold each drop of spray on a side stud, and round each ledge with a slope."""
    for index, (column, row) in enumerate(spray(canvas)):
        x, z = BORDER + column, STAND + RAIL + row
        builder.place(
            "87087", at=(x, FRONT + SKY_DEPTH, z), color=canvas[column, row][0]
        )
        builder.place(
            "98138",
            at=(x, FRONT + SKY_DEPTH - 0.4, z + 0.5),
            rotation="+x+z",
            color=FOAM,
            id=f"spray{index + 1}",
        )
    for (column, row), color, depth, reach in ledges(canvas):
        # A curved slope rounds a ledge two studs deep or more, a cheese slope the rest.
        part = "11477" if reach >= 2 else "54200"
        builder.place(
            part,
            at=(BORDER + column, FRONT + depth, STAND + RAIL + row + 1),
            color=color,
        )


def place_stand(builder: ModelBuilder) -> None:
    """Build the stand: a blind arcade under a plate, then a tray with a sloped rim."""
    for x in range(STAND_WEST + 1, STAND_EAST - 6, 6):
        builder.place("3455", at=(x, 0, 0), rotation="R90", color=STAND_COLOR)
    body: Voxels = {
        (x, y, z): STAND_COLOR
        for x in range(STAND_WEST, STAND_EAST)
        for y in range(STAND_NORTH)
        for z in range(STAND)
        if z == STAND - 1 or y >= 2 or x in {STAND_WEST, STAND_EAST - 1}
    }
    builder.fill(body, id="stand")
    for x in range(STAND_WEST, STAND_EAST, 2):
        builder.place("85984", at=(x, 0, STAND), color=STAND_COLOR)
    builder.place(
        "2431", at=(30, 2, STAND), rotation="R90", color=LINER_COLOR, id="label"
    )
    taken = {(x, 2) for x in range(30, 34)}
    taken |= {
        (x, y)
        for x in range(WIDTH + 2 * BORDER)
        for y in range(FRONT + FRAME_FRONT, FRONT + BACK)
    }
    taken |= {
        (x + k, y)
        for x in BUTTRESSES
        for k in range(2)
        for y in range(FRONT + BACK, STAND_NORTH)
    }
    for y in range(1, STAND_NORTH):
        free = [x for x in range(STAND_WEST, STAND_EAST) if (x, y) not in taken]
        tile_row(builder, free, y)


def tile_row(builder: ModelBuilder, xs: list[int], y: int) -> None:
    """Cover the given squares of one row of the tray with tiles, longest first."""
    runs: list[list[int]] = []
    for x in xs:
        if runs and runs[-1][-1] == x - 1:
            runs[-1].append(x)
        else:
            runs.append([x])
    for run in runs:
        start, left = run[0], len(run)
        while left > 0:
            length = next(size for size in TILES if size <= left)
            builder.place(
                TILES[length], at=(start, y, STAND), rotation="R90", color=STAND_COLOR
            )
            start, left = start + length, left - length


def place_buttresses(builder: ModelBuilder) -> None:
    """Brace the frame from behind with stepped buttresses capped with slopes."""
    courses = 6
    back = FRONT + BACK
    voxels: Voxels = {}
    for x in BUTTRESSES:
        for course in range(courses):
            z = STAND + 3 * course
            end = back + courses - 1 - course  # where the course's slope begins
            for y in range(back, end):
                for k in range(3):
                    voxels[x, y, z + k] = voxels[x + 1, y, z + k] = STAND_COLOR
            builder.place("3039", at=(x, end, z), rotation="R180", color=STAND_COLOR)
    builder.fill(voxels, id="buttress")


def build() -> ModelBuilder:
    """Paint the print, then build its relief, its frame and its stand."""
    builder = ModelBuilder("great-wave")
    canvas = paint()
    place_stand(builder)
    place_buttresses(builder)
    builder.fill(frame_voxels(), id="frame")
    place_frame_top(builder)
    builder.fill(picture_voxels(canvas, spray(canvas)), id="picture")
    place_relief_details(builder, canvas)
    return builder
