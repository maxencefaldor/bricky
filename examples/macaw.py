# Copyright 2026 Maxence Faldor
"""A scarlet macaw perched on a branch: a brick-built sculpture on a display base.

- The bird, the tree and the ground are voxels, filled in staggered courses
  (``builder.fill``). Smooth unions of tilted ellipsoids shape the body and the head.
- The folded wings show the bird's bands: red coverts at the shoulder, then yellow
  ones with green tips, then blue flight feathers. The tail hangs in red feathers of
  graded length with blue tips.
- The hooked beak is plates laid along its length, rooted inside the head. Crossed
  plates build the tail and the leaves, so each layer bridges the joints of the next.
- Each eye is a round tile on a brick with a stud on its side. Cheese slopes ease the
  steps of the surface, and tiles cover the bird and the leaves.
- Round bricks and plates make flowers, palm fruit and two bromeliads' flower spikes.
- The base has two tiers of black bricks with tiled tops, a feather and a leaf inlaid
  in the tiles, and a gold plaque on a brick with studs on its side.
- The bird faces west, its body rotated 20 degrees south and its head rotated south.
  The south-east view thus shows the face, the left wing and the tail.
- The model is 20 by 20 studs and 97 plates tall.

Run: ``uv run bricky build examples/macaw.py``
"""

from functools import cache
from itertools import pairwise
from math import cos, sin, sqrt

from bricky import ModelBuilder

type Vector = tuple[float, float, float]
type Voxel = tuple[int, int, int]
type Voxels = dict[Voxel, str]
type Square = tuple[int, int]
type Color = str | None
type Spike = tuple[tuple[str, str, int], ...]  # parts bottom up: id, color, plates

PLATES_PER_STUD = 2.5  # a stud is 8 mm and a plate 3.2 mm

RED, YELLOW, GREEN = "Red", "Yellow", "Green"
BLUE, DARK_BLUE, SKY = "Blue", "Dark Blue", "Medium Blue"
FACE, BILL, TIP = "White", "Light Bluish Gray", "Black"
FEET = "Dark Bluish Gray"
BARK, GRAIN = "Reddish Brown", "Dark Brown"
MOSS, DARK_MOSS = "Olive Green", "Dark Green"
STONE, DARK_STONE = "Light Bluish Gray", "Dark Bluish Gray"
BASE, LEDGE, PLAQUE = "Black", "Dark Bluish Gray", "Pearl Gold"

WEST, EAST, SOUTH, NORTH = 3, 23, 5, 25  # the base's lower tier, in studs
TIER = 3  # plates: the lower tier fills z 0 to 2, the upper tier z 3 to 5
TOP = 6  # the plate layer of the top tiles; the scenery stands on it too
HEIGHT = 100  # plates
TILES = {
    (2, 4): "87079",
    (2, 2): "3068",
    (1, 4): "2431",
    (1, 3): "63864",
    (1, 2): "3069",
    (1, 1): "3070",
}  # tiles by footprint, the shorter side along x when unrotated
STRIPS = {8: "3460", 6: "3666", 4: "3710", 3: "3623", 2: "3023", 1: "3024"}  # 1 x N
CAPS = {8: "4162", 6: "6636", 4: "2431", 3: "63864", 2: "3069", 1: "3070"}  # 1 x N
CHEESE = "54200"  # Slope 30 1 x 1 x 2/3: two plates tall, falling toward -y
FALLS = {(0, -1): "R0", (1, 0): "R90", (0, 1): "R180", (-1, 0): "R270"}

# The bird's frames: forward, left and up, in studs. The bird's frame starts at the top
# of the branch under it and faces west. The body's frame rotates from it toward the
# bird's left. The head's frame faces south, toward the viewer, from a column's center,
# so the beak lines up with the studs.
PERCH: Vector = (13.5, 17.5, 20.0)
HEADING = (-1.0, 0.0)  # west
HEAD_ORIGIN: Vector = (10.5, 20.5, 20.0)
HEAD_HEADING = (0.0, -1.0)  # south
BODY_YAW = 0.35  # radians toward the bird's left, the side the camera sees
BODY_CENTER: Vector = (0.8, 0.0, 7.0)
BODY_RADII: Vector = (4.6, 4.0, 6.4)  # across, side, along the tilted axis
BODY_TILT = 0.4  # radians: the top of the body leans forward
HEAD_CENTER: Vector = (2.6, 0.0, 15.2)
HEAD_RADII: Vector = (3.4, 3.2, 3.4)
EYE = (2.4, 15.9)  # forward and up

CULMEN = (4.6, 12.6, 4.0)  # the beak's outer curve: forward, up and radius
HOOK = (4.4, 10.4, 3.0)  # the inner curve of the hook
JAW = (5.2, 11.6, 1.6)  # the lower mandible

WING_SHOULDER: Vector = (0.8, 2.9, 12.0)
WING_TIP: Vector = (-4.4, 2.2, -8.0)
WING_WIDTH = 2.9  # the half-width across the wing at its broadest
WING_BANDS = ((0.22, RED), (0.42, YELLOW), (0.48, GREEN))  # the coverts, by band

TAIL_TOP: Vector = (-2.6, -1.0, 1.6)
TAIL_TIP: Vector = (-7.2, -1.0, -14.8)
FEATHERS = ((1.0, 0.82), (0.86, 0.72), (0.62, 0.5))  # length and red share by column

FOOT_SIDE = 2  # studs from the bird's middle to each foot
BRANCH_RADIUS = 1.5
BRANCH_END = 23.0  # the y where the branch ends, north of the bird

# The tree and the ground, in world studs.
TRUNK: tuple[tuple[float, float, float, float], ...] = (
    (12.5, 10.5, 2.4, 1.9),
    (11.5, 11.0, 8.0, 1.7),
    (12.5, 11.5, 14.0, 1.6),
    (13.3, 11.9, 17.2, 1.55),
    (13.5, 13.0, 18.5, 1.5),
)  # the trunk's path: x, y, height and radius; it bends into the branch at the top
ROOTS: tuple[Vector, ...] = ((16.0, 8.5, 2.8), (8.5, 12.0, 2.8), (11.5, 7.0, 2.8))
TWIGS: tuple[tuple[Vector, Vector, float], ...] = (
    ((12.0, 11.5, 9.0), (7.5, 12.5, 9.0), 1.15),
    ((13.5, 22.5, 18.5), (13.5, 22.5, 21.0), 0.8),
)  # each twig's start, end and radius
SPRIGS: tuple[tuple[Square, str, tuple[tuple[float, float, float], ...]], ...] = (
    ((7, 12), "Green", ((-1.0, 1.0, 5.0), (-1.0, 0.0, 4.0), (0.0, -1.0, 5.5))),
    ((13, 22), "Dark Green", ((1.0, 0.0, 5.5), (-1.0, 0.0, 5.0), (1.0, 1.0, 3.0))),
)  # each sprig's stalk on the wood, its color, and its leaves: direction and length
FRUIT: tuple[tuple[Square, int], ...] = (
    ((9, 12), 4),
    ((9, 11), 3),
    ((8, 12), 3),
    ((8, 11), 2),
    ((13, 21), 4),
    ((14, 21), 2),
    ((13, 20), 3),
)  # palm fruit under the twig and the branch: each bunch's square and length in plates
FRUIT_COLORS = ("Orange", "Dark Orange")
STONES: tuple[tuple[Vector, Vector], ...] = (
    ((7.0, 8.5, 2.4), (1.8, 1.5, 1.2)),
    ((20.0, 15.5, 2.4), (1.4, 1.2, 0.9)),
)  # each stone's center and radii
FLOWERS: tuple[tuple[Square, int, str], ...] = (
    ((10, 8), 2, "Dark Pink"),
    ((15, 9), 1, "Yellow"),
    ((9, 11), 1, "Magenta"),
    ((14, 7), 1, "Orange"),
)  # each flower's square, the round bricks of its stem, and its blossom
ROSETTE_LEAVES = ((1, 0), (0, 1), (-1, 0), (0, -1))
ROSETTES: tuple[tuple[Square, int, str, Spike], ...] = (
    (
        (17, 12),
        3,
        "Lime",
        (("3062", "Red", 3), ("3062", "Red", 3), ("4073", YELLOW, 1)),
    ),
    ((8, 19), 2, GREEN, (("3062", "Orange", 3), ("4073", YELLOW, 1))),
)  # bromeliads on the base: center, leaf length, color, and the flower spike
INLAYS: tuple[tuple[Square, int, str], ...] = (
    ((16, 7), 3, RED),  # a fallen feather, red with a blue tip
    ((19, 7), 2, BLUE),
    ((17, 8), 2, RED),
    ((19, 8), 1, BLUE),
    ((15, 19), 2, MOSS),  # a fallen leaf
    ((13, 20), 4, MOSS),
    ((14, 21), 3, MOSS),
    ((16, 22), 1, MOSS),
)  # tiles inlaid among the top tiles: start, length along x and color


def noise(*key: int) -> float:
    """Return a fixed pseudo-random number in [0, 1) for a key."""
    value = 0
    for part in key:
        value = (value * 1_000_003 + part * 7_919 + 104_729) % 2_147_483_647
    return (value * 48_271 % 2_147_483_647) / 2_147_483_647


def center_of(voxel: Voxel) -> Vector:
    """Return the center of a voxel in studs, its height converted from plates."""
    x, y, z = voxel
    return x + 0.5, y + 0.5, (z + 0.5) / PLATES_PER_STUD


def subtract(point: Vector, origin: Vector) -> Vector:
    """Return the vector from an origin to a point."""
    return point[0] - origin[0], point[1] - origin[1], point[2] - origin[2]


def dot(first: Vector, second: Vector) -> float:
    """Return the dot product of two vectors."""
    return first[0] * second[0] + first[1] * second[1] + first[2] * second[2]


def length(vector: Vector) -> float:
    """Return the length of a vector."""
    return sqrt(dot(vector, vector))


def unit(vector: Vector) -> Vector:
    """Return a vector scaled to length one."""
    size = length(vector)
    return vector[0] / size, vector[1] / size, vector[2] / size


def ellipsoid(offset: Vector, radii: Vector) -> float:
    """Return the approximate signed distance from an ellipsoid's center offset.

    The distance is negative inside the ellipsoid.
    """
    pairs = list(zip(offset, radii, strict=True))
    scaled = sqrt(sum((part / radius) ** 2 for part, radius in pairs))
    gradient = sqrt(sum((part / radius**2) ** 2 for part, radius in pairs))
    if gradient == 0:
        return -min(radii)
    return scaled * (scaled - 1) / gradient


def smooth_union(first: float, second: float, blend: float) -> float:
    """Return the union of two signed distances, rounded over a blend distance."""
    weight = max(blend - abs(first - second), 0.0) / blend
    return min(first, second) - weight * weight * blend / 4


def segment(point: Vector, start: Vector, end: Vector) -> tuple[float, float]:
    """Return the distance from a point to a segment, and where along it, 0 to 1."""
    axis = subtract(end, start)
    along = max(0.0, min(1.0, dot(subtract(point, start), axis) / dot(axis, axis)))
    closest = (
        start[0] + along * axis[0],
        start[1] + along * axis[1],
        start[2] + along * axis[2],
    )
    return length(subtract(point, closest)), along


def cylinder(point: Vector, start: Vector, end: Vector, radius: float) -> bool:
    """Whether a point lies inside a cylinder with flat ends."""
    axis = subtract(end, start)
    along = dot(subtract(point, start), axis) / dot(axis, axis)
    return 0 <= along <= 1 and segment(point, start, end)[0] <= radius


def inside(forward: float, up: float, circle: tuple[float, float, float]) -> bool:
    """Whether a point of the bird's side view lies inside a circle."""
    return (forward - circle[0]) ** 2 + (up - circle[1]) ** 2 <= circle[2] ** 2


def triangle(value: float) -> float:
    """Return a triangle wave of period 2 that rises from 0 to 1 and falls back."""
    return 1 - abs(value % 2 - 1)


# The bird.


def frame(point: Vector, origin: Vector, heading: tuple[float, float]) -> Vector:
    """Return a world point in a frame: forward along the heading, left and up."""
    east, north, up = subtract(point, origin)
    ahead_x, ahead_y = heading
    return east * ahead_x + north * ahead_y, north * ahead_x - east * ahead_y, up


def head_frame(point: Vector) -> Vector:
    """Return a world point in the head's frame."""
    return frame(point, HEAD_ORIGIN, HEAD_HEADING)


def bird_frame(point: Vector) -> Vector:
    """Return a world point in the bird's frame."""
    return frame(point, PERCH, HEADING)


def body_frame(bird_point: Vector) -> Vector:
    """Return a point of the bird's frame in the body's frame."""
    forward, side, up = bird_point
    cosine, sine = cos(BODY_YAW), sin(BODY_YAW)
    return forward * cosine + side * sine, side * cosine - forward * sine, up


def body_and_head(head: Vector, body: Vector) -> float:
    """Return the signed distance to the body and the head, blended at the neck."""
    across, along = body[0] - BODY_CENTER[0], body[2] - BODY_CENTER[2]
    cosine, sine = cos(BODY_TILT), sin(BODY_TILT)
    tilted = (across * cosine - along * sine, body[1], across * sine + along * cosine)
    body_distance = ellipsoid(tilted, BODY_RADII)
    head_distance = ellipsoid(subtract(head, HEAD_CENTER), HEAD_RADII)
    return smooth_union(body_distance, head_distance, 3.0)


def beak(point: Vector) -> Color:
    """Return the beak's color: a gray hook with a black tip.

    The black lower mandible sits under the hook. The upper mandible's root reaches
    back into the head, out of sight, so that plates tie the beak to the head.
    """
    forward, side, up = head_frame(point)
    if 2.8 <= forward < 4.6:  # the root, hidden inside the head
        return BILL if abs(side) <= 1 and 13.6 <= up <= 15.0 else None
    ridge = CULMEN[1] + sqrt(max(0.0, CULMEN[2] ** 2 - (forward - CULMEN[0]) ** 2))
    width = 1 if forward < 6.5 and up < ridge - 0.8 else 0
    upper = inside(forward, up, CULMEN) and not inside(forward, up, HOOK)
    if upper and forward > 4.6 and abs(side) <= width:
        return TIP if up < 11.2 else BILL
    jaw = inside(forward, up, JAW) and abs(side) <= (1 if forward < 6.5 else 0)
    return TIP if jaw and forward > 3.6 else None


def wing_color(band: float, across: float) -> str:
    """Return the color of a band of the wing, with stripes between flight feathers."""
    zigzag = 0.03 * triangle(across)
    for end, color in WING_BANDS:
        if band < end + (zigzag if color != RED else 0):
            return color
    if band > 0.84 or (band > 0.6 and across % 1.6 < 0.5):
        return DARK_BLUE
    return BLUE


def wing(forward: float, side: float, up: float) -> Color:
    """Return the folded wing's color, in bands from the shoulder to the tip."""
    reach = subtract(WING_TIP, WING_SHOULDER)
    axis = unit(reach)
    offset = subtract((forward, abs(side), up), WING_SHOULDER)
    along = dot(offset, axis) / length(reach)
    if along < 0.25:
        half_width = WING_WIDTH * sqrt(max(0.0, 1 - ((along - 0.25) / 0.3) ** 2))
    else:
        half_width = WING_WIDTH - (WING_WIDTH - 0.4) * (along - 0.25) / 0.75
    across = dot(offset, unit((-axis[2], 0.0, axis[0])))
    if not (-0.05 <= along <= 0.97 and abs(across) < half_width):
        return None
    outer = 4.9 - 1.6 * along - 0.6 * (across / half_width) ** 2
    if not 1.6 + 1.6 * max(0.0, along - 0.55) <= abs(side) <= outer:
        return None
    return wing_color(along + 0.06 * across / half_width, across)


def tail(point: Vector) -> Color:
    """Return the tail's color: feathers of graded length, red with blue tips."""
    forward, side, up = bird_frame(point)
    along = (TAIL_TOP[2] - up) / (TAIL_TOP[2] - TAIL_TIP[2])
    column = round(abs(side - TAIL_TOP[1]))
    if column >= len(FEATHERS) or not -0.25 <= along <= FEATHERS[column][0]:
        return None
    middle = TAIL_TOP[0] + along * (TAIL_TIP[0] - TAIL_TOP[0])
    if abs(forward - middle) > 1.15 - 0.55 * along:
        return None
    return RED if along < FEATHERS[column][1] else BLUE


def plumage(head: Vector, body: Vector) -> Color:
    """Return the color of the body and the head: red, the white face, the blue rump."""
    forward, side, up = head
    face_back = 1.4 + 0.5 * max(0.0, 15.6 - up)
    if forward > face_back and 12.2 < up < 16.6 and (abs(side) >= 1 or forward > 4.6):
        return FACE
    if body[0] < -1.5 and up < 3.0:
        return SKY
    return RED


def foot(forward: float, side: float, up: float) -> Color:
    """Return the color of the legs and the toes that grip the branch."""
    if round(abs(side)) != FOOT_SIDE or abs(forward) > 2.4:
        return None
    if forward**2 + (up + BRANCH_RADIUS) ** 2 < BRANCH_RADIUS**2:
        return None
    if -1.2 <= up <= 0.8:
        return TIP if up < -0.6 else FEET
    if 0 <= forward <= 1 and 0 < up < 2.6:
        return FEET
    return None


def bird(point: Vector) -> Color:
    """Return the color of the bird's body, head, wings and feet, or None."""
    own = bird_frame(point)
    if not (-9 < own[0] < 10 and abs(own[1]) < 9 and -17 < own[2] < 19):
        return None
    body = body_frame(own)
    color = wing(*body)
    if color is not None:
        return color
    head = head_frame(point)
    if body_and_head(head, body) <= 0:
        return plumage(head, body)
    return foot(*own)


# The tree and the ground.


def in_trunk(point: Vector) -> bool:
    """Whether a point lies inside the trunk."""
    for start, end in pairwise(TRUNK):
        distance, along = segment(point, start[:3], end[:3])
        if distance <= start[3] + along * (end[3] - start[3]):
            return True
    return False


def in_offshoot(point: Vector) -> bool:
    """Whether a point lies inside a root or a twig."""
    foot_of_trunk = (TRUNK[0][0], TRUNK[0][1], 3.2)
    for root in ROOTS:
        distance, along = segment(point, foot_of_trunk, root)
        if distance <= 1.2 - 0.5 * along:
            return True
    return any(cylinder(point, start, end, radius) for start, end, radius in TWIGS)


def in_branch(point: Vector) -> bool:
    """Whether a point lies inside the branch, from the trunk to its northern tip."""
    x, y, height = point
    bend = TRUNK[-1]
    if not bend[1] <= y <= BRANCH_END:
        return False
    radius = BRANCH_RADIUS - 0.3 * max(0.0, (y - BRANCH_END + 2) / 2)
    return (x - PERCH[0]) ** 2 + (height - bend[2]) ** 2 <= radius**2


def in_tree(point: Vector) -> bool:
    """Whether a point lies inside the trunk or the branch."""
    return in_branch(point) or in_trunk(point)


def in_wood(point: Vector) -> bool:
    """Whether a point lies inside any wood: trunk, branch, roots or twigs."""
    return in_tree(point) or in_offshoot(point)


def tree(point: Vector) -> Color:
    """Return the color of the wood: bark, with grain and moss on trunk and branch.

    Grain only colors voxels that stand on wood among neighbors that do too. Every
    overhang and the voxels beside it then share one color, so the fill's plates
    reach back from the overhang to what holds it.
    """
    if not in_tree(point):
        return BARK if in_offshoot(point) else None
    x, y, height = point
    above = (x, y, height + 1 / PLATES_PER_STUD)
    if not in_wood(above) and noise(int(x), int(y)) > 0.7:
        return MOSS  # moss on the upper face of the wood
    if noise(int(x), int(y), int(height * PLATES_PER_STUD) // 4) < 0.8:
        return BARK
    low = height - 1 / PLATES_PER_STUD
    supported = all(
        in_wood((x + step_x, y + step_y, low))
        for step_x, step_y in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))
    )
    return GRAIN if supported else BARK


@cache
def stalk_layer(x: int, y: int) -> int:
    """Return the layer just above the highest wood in a column."""
    return 1 + max(z for z in range(HEIGHT) if tree(center_of((x, y, z))) is not None)


def leaf(voxel: Voxel) -> Color:
    """Return a leaf's color: pointed blades two plates thick, spread from a stalk.

    The stalk sits on the wood, and each blade spreads flat from it.
    """
    x, y, z = voxel
    for (stalk_x, stalk_y), color, blades in SPRIGS:
        stalk_z = stalk_layer(stalk_x, stalk_y)
        offset_x, offset_y = x - stalk_x, y - stalk_y
        for direction_x, direction_y, size in blades:
            norm = sqrt(direction_x**2 + direction_y**2)
            along = (offset_x * direction_x + offset_y * direction_y) / norm
            across = (offset_y * direction_x - offset_x * direction_y) / norm
            share = max(0.0, along) / size
            width = max(0.6, 5.2 * sqrt(share) * (1 - share))
            if -0.5 < along < size and abs(across) <= width and 0 <= z - stalk_z <= 1:
                return color
    return None


def rosette(voxel: Voxel) -> Color:
    """Return the color of a bromeliad's leaves, or None.

    Each leaf rises two plates per stud from the center and is four plates thick.
    Each step thus shares a layer of each direction with the step before it.
    """
    x, y, z = voxel
    for (center_x, center_y), size, color, _ in ROSETTES:
        offset_x, offset_y = x - center_x, y - center_y
        for step_x, step_y in ROSETTE_LEAVES:
            along = offset_x * step_x + offset_y * step_y
            across = offset_x * step_y - offset_y * step_x
            rise = z - TOP - 2 * along
            if across == 0 and 0 <= along <= size and 0 <= rise <= 3:
                return color
    return None


def ground(point: Vector) -> Color:
    """Return the color of the moss and the stones around the roots."""
    x, y, height = point
    if (x - 12.5) ** 2 / 20 + (y - 10.0) ** 2 / 12 + (height - 2.4) ** 2 / 0.6 <= 1:
        return DARK_MOSS if noise(int(x), int(y)) > 0.6 else MOSS
    for center, radii in STONES:
        if ellipsoid(subtract(point, center), radii) <= 0:
            return DARK_STONE if noise(int(x), int(y)) > 0.5 else STONE
    return None


# The voxels, split by how they are built.


def rounded(x: int, y: int, inset: int, corner: float) -> bool:
    """Whether a square lies inside the base's footprint, inset, with round corners."""
    west, east, south, north = WEST + inset, EAST - inset, SOUTH + inset, NORTH - inset
    if not (west <= x < east and south <= y < north):
        return False
    near_x = min(x + 0.5 - west, east - x - 0.5)
    near_y = min(y + 0.5 - south, north - y - 0.5)
    if near_x >= corner or near_y >= corner:
        return True
    return (corner - near_x) ** 2 + (corner - near_y) ** 2 <= corner**2


def upper_tier(x: int, y: int) -> bool:
    """Whether a square lies inside the base's upper tier."""
    return rounded(x, y, 1, 2.5)


def filled_color(voxel: Voxel) -> tuple[str, bool] | None:
    """Return the color of a voxel the fill covers and whether the bird holds it."""
    x, y, z = voxel
    if z < TOP:
        lower = z < TIER and rounded(x, y, 0, 3.0)
        return (BASE, False) if lower or upper_tier(x, y) else None
    point = center_of(voxel)
    color = bird(point)
    if color is not None:
        return color, True
    if z < TOP + 3 and not upper_tier(x, y):
        return None  # the roots and the stones stay on the upper tier
    color = tree(point)
    if color is None:
        color = ground(point)
    return None if color is None else (color, False)


def laid_color(voxel: Voxel) -> Color:
    """Return the color of a voxel laid in crossed plates: tail, leaf or bromeliad."""
    x, y, z = voxel
    if z < TOP + 3 and not upper_tier(x, y):
        return None
    color = tail(center_of(voxel))
    if color is None:
        color = leaf(voxel)
    if color is None:
        color = rosette(voxel)
    return color


def sculpture() -> tuple[Voxels, Voxels, Voxels, set[Voxel]]:
    """Return the voxels to fill, to lay lengthwise and to lay crosswise, with colors.

    Plates laid lengthwise build the beak, and crossed plates build the thin, slanted
    tail and leaves. The last set holds the bird's and the leaves' voxels, whose tops
    take tiles.
    """
    filled: Voxels = {}
    lengthwise: Voxels = {}
    crosswise: Voxels = {}
    skin: set[Voxel] = set()
    for x in range(WEST, EAST):
        for y in range(SOUTH, NORTH):
            for z in range(HEIGHT):
                voxel = (x, y, z)
                if (color := beak(center_of(voxel))) is not None:
                    lengthwise[voxel] = color
                    skin.add(voxel)
                elif (found := filled_color(voxel)) is not None:
                    filled[voxel], in_bird = found
                    if in_bird:
                        skin.add(voxel)
                elif (color := laid_color(voxel)) is not None:
                    crosswise[voxel] = color
                    skin.add(voxel)
    return filled, lengthwise, crosswise, skin


# Parts placed one by one: plates laid in runs, eyes, flowers, slopes and the base.


def made_in(builder: ModelBuilder, part: str, color: str) -> bool:
    """Whether the catalog lists a part in a color."""
    entry = builder.catalog.entry(part)
    return entry is not None and builder.catalog.resolve_color(color).id in entry.colors


def lay(
    builder: ModelBuilder,
    voxels: Voxels,
    prefix: str,
    steps: tuple[Square, ...],
    parts: dict[int, str] = STRIPS,
) -> None:
    """Lay plates or tiles 1 x N over voxels, one run of a color at a time.

    Each layer's runs follow the step for its layer. One step lays every layer the
    same way, and two steps cross each layer's plates over the joints of the next.
    No run leaves a single stud at its end, and every part comes in its color.
    """
    for (x, y, z), color in sorted(voxels.items()):
        step = steps[z % len(steps)]
        if voxels.get((x - step[0], y - step[1], z)) == color:
            continue  # not the start of a run
        run = 1
        while voxels.get((x + run * step[0], y + run * step[1], z)) == color:
            run += 1
        start = 0
        while start < run:
            left = run - start
            size = next(
                size
                for size, part in parts.items()
                if size <= left and left - size != 1 and made_in(builder, part, color)
            )
            builder.place(
                parts[size],
                at=(x + start * step[0], y + start * step[1], z),
                rotation="R90" if step == (1, 0) else "R0",
                color=color,
                id=f"{prefix}.{x + start * step[0]}.{y + start * step[1]}.{z}",
            )
            start += size


def eyes(builder: ModelBuilder, voxels: Voxels) -> set[Voxel]:
    """Set an eye into each side of the face: a round tile on a brick's side stud.

    The head faces south, so the eyes look west and east. Each brick replaces three
    voxels at the surface of the face, and any voxel beside it gives way to the tile.
    Return the voxels the bricks and the tiles take.
    """
    taken: set[Voxel] = set()
    y = int(HEAD_ORIGIN[1] - EYE[0])
    z = round((HEAD_ORIGIN[2] + EYE[1]) * PLATES_PER_STUD - 1.5)
    row = [
        x for x in range(WEST, EAST) if all((x, y, z + k) in voxels for k in range(3))
    ]
    for x, outward, rotation, tile_rotation in (
        (min(row), -1, "R270", "-y+z"),
        (max(row), 1, "R90", "+y+z"),
    ):
        for k in range(3):
            del voxels[x, y, z + k]
            voxels.pop((x + outward, y, z + k), None)
            taken |= {(x, y, z + k), (x + outward, y, z + k)}
        builder.place(
            "87087", at=(x, y, z), rotation=rotation, color=FACE, id=f"eye-holder.{x}"
        )
        builder.place(
            "98138",
            at=(x - 0.4 if outward < 0 else x + 1, y, z + 0.5),
            rotation=tile_rotation,
            color=TIP,
            id=f"eye.{x}",
        )
    return taken


def flowers(builder: ModelBuilder, voxels: Voxels) -> set[Voxel]:
    """Stand flowers in the moss: round bricks for stems, a round plate for a blossom.

    Return the voxels the flowers take.
    """
    taken: set[Voxel] = set()
    for (x, y), stems, blossom in FLOWERS:
        z = next(z for z in range(TOP, HEIGHT) if (x, y, z) not in voxels)
        for stem in range(stems):
            builder.place(
                "3062", at=(x, y, z + 3 * stem), color=GREEN, id=f"stem.{x}.{y}.{stem}"
            )
        builder.place(
            "4073", at=(x, y, z + 3 * stems), color=blossom, id=f"flower.{x}.{y}"
        )
        taken |= {(x, y, z + k) for k in range(3 * stems + 1)}
    return taken


def spikes(builder: ModelBuilder, voxels: Voxels) -> set[Voxel]:
    """Stand each bromeliad's flower spike on the center of its rosette.

    Return the voxels the spikes take.
    """
    taken: set[Voxel] = set()
    for (x, y), _, _, spike in ROSETTES:
        z = next(z for z in range(TOP, HEIGHT) if (x, y, z) not in voxels)
        for part, color, height in spike:
            builder.place(part, at=(x, y, z), color=color, id=f"spike.{x}.{y}.{z}")
            taken |= {(x, y, z + k) for k in range(height)}
            z += height
    return taken


def fruit(builder: ModelBuilder, voxels: Voxels) -> set[Voxel]:
    """Hang bunches of palm fruit under the wood, each round plate on the one below.

    The topmost plate's stud holds it to the wood's underside. Return the voxels the
    fruit takes.
    """
    taken: set[Voxel] = set()
    for (x, y), size in FRUIT:
        z = stalk_layer(x, y) - 1  # the top of the wood, then down to its underside
        while (x, y, z - 1) in voxels:
            z -= 1
        z -= size
        for k in range(size):
            builder.place(
                "4073",
                at=(x, y, z + k),
                color=FRUIT_COLORS[(x + y + k) % 2],
                id=f"fruit.{x}.{y}.{z + k}",
            )
            taken.add((x, y, z + k))
    return taken


def smooth(
    builder: ModelBuilder, voxels: Voxels, taken: set[Voxel], low: int
) -> set[Voxel]:
    """Ease the steps of the surface with cheese slopes, from layer ``low`` up.

    A slope stands on a column whose top lies at least two plates below a neighbor's.
    The slope falls away from that neighbor, toward a side no higher than the column.
    Voxels in ``taken`` hold other parts, so no slope goes there. Return the slopes'
    voxels.
    """
    slopes: set[Voxel] = set()
    solid = taken | set(voxels)
    tops = [
        (x, y, z)
        for (x, y, z) in voxels
        if z >= low and (x, y, z + 1) not in solid and (x, y, z + 2) not in solid
    ]
    for x, y, z in sorted(tops):
        for (step_x, step_y), rotation in FALLS.items():
            higher = (x - step_x, y - step_y)
            lower = (x + step_x, y + step_y, z + 1)
            if all((*higher, z + k) in solid for k in (1, 2)) and lower not in solid:
                builder.place(
                    CHEESE,
                    at=(x, y, z + 1),
                    rotation=rotation,
                    color=voxels[x, y, z],
                    id=f"slope.{x}.{y}.{z + 1}",
                )
                slopes |= {(x, y, z + 1), (x, y, z + 2)}
                break
    return slopes


def cap(
    builder: ModelBuilder, voxels: Voxels, taken: set[Voxel], skin: set[Voxel]
) -> None:
    """Cover the skin's exposed tops with tiles 1 x N, in runs along x.

    Each tile takes the color of the voxel it covers, and none goes where ``taken``
    holds another part.
    """
    caps = {
        (x, y, z + 1): voxels[x, y, z]
        for x, y, z in skin & voxels.keys()
        if (x, y, z + 1) not in voxels and (x, y, z + 1) not in taken
    }
    lay(builder, caps, "cap", ((1, 0),), CAPS)


def tile(
    builder: ModelBuilder, squares: set[Square], z: int, color: str, prefix: str
) -> None:
    """Cover squares with tiles, the largest that fit first, in rows from the south."""
    free = set(squares)
    for x, y in sorted(free, key=lambda square: (square[1], square[0])):
        if (x, y) not in free:
            continue
        for (short, long), part in TILES.items():
            shapes = ((short, long, "R0"), (long, short, "R90"))
            fits = [
                (width, depth, rotation)
                for width, depth, rotation in shapes
                if all(
                    (x + i, y + j) in free for i in range(width) for j in range(depth)
                )
            ]
            if fits:
                width, depth, rotation = fits[0]
                builder.place(
                    part,
                    at=(x, y, z),
                    rotation=rotation,
                    color=color,
                    id=f"{prefix}.{x}.{y}",
                )
                free -= {(x + i, y + j) for i in range(width) for j in range(depth)}
                break


def base(builder: ModelBuilder, voxels: Voxels, laid: Voxels) -> None:
    """Tile the ledge and the top of the base, and mount the plaque on the front.

    The top tiles leave free the squares that voxels stand on. A fallen feather and a
    leaf lie inlaid among the tiles, inside a dark border. The plaque is a tile held
    upright by a brick with studs on its side, set into the lower tier.
    """
    lower = {
        (x, y)
        for x in range(WEST, EAST)
        for y in range(SOUTH, NORTH)
        if rounded(x, y, 0, 3.0)
    }
    upper = {(x, y) for x, y in lower if upper_tier(x, y)}
    tile(builder, lower - upper, TIER, LEDGE, "ledge")
    inlaid: set[Square] = set()
    for (x, y), size, color in INLAYS:
        tile(builder, {(x + i, y) for i in range(size)}, TOP, color, "inlay")
        inlaid |= {(x + i, y) for i in range(size)}
    free = {
        (x, y)
        for x, y in upper - inlaid
        if (x, y, TOP) not in voxels and (x, y, TOP) not in laid
    }
    border = {(x, y) for x, y in free if not rounded(x, y, 2, 2.0)}
    tile(builder, border, TOP, LEDGE, "border")
    tile(builder, free - border, TOP, BASE, "top")
    middle = (WEST + EAST) // 2 - 2
    for x in range(middle, middle + 4):
        for z in range(TIER):
            del voxels[x, SOUTH, z]
    builder.place("30414", at=(middle, SOUTH, 0), color=BASE, id="plaque-holder")
    builder.place(
        "2431",
        at=(middle, SOUTH - 0.4, 0.5),
        rotation="-z+x",
        color=PLAQUE,
        id="plaque",
    )


def build() -> ModelBuilder:
    """Fill the sculpture's voxels, lay the beak, tail and leaves, and add details."""
    builder = ModelBuilder("macaw")
    voxels, lengthwise, crosswise, skin = sculpture()
    taken = eyes(builder, voxels)
    base(builder, voxels, crosswise)
    print(f"{len(voxels):,} voxels to fill")
    builder.fill(voxels, id="macaw")
    lay(builder, lengthwise, "beak", ((0, 1),))
    lay(builder, crosswise, "laid", ((1, 0), (0, 1)))
    everything = voxels | lengthwise | crosswise
    taken |= flowers(builder, everything) | fruit(builder, everything)
    taken |= spikes(builder, everything)
    taken |= smooth(builder, everything, taken, TOP)
    cap(builder, everything, taken, skin)
    return builder
