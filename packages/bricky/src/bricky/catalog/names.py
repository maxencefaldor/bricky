"""Read a part's shape from its BrickLink name.

BrickLink names ordinary building parts by a strict pattern: the kind of part, its size in studs,
its height when it differs from the usual one, then any details. "Brick 1 x 2 x 2" is a brick one
stud wide, two long and two bricks tall; "Slope 45 2 x 4" is a slope two studs deep and four wide;
"Plate, Round 2 x 2 with Axle Hole" is a round plate.

:func:`shape_from_name` returns the shape of every name that follows a pattern bricky has a family
for, and ``None`` for every other name, rather than guess. Some details leave the outer shape and
the connectors as bricky models them, such as a groove along the bottom edge or the tubes
underneath. Any other detail, such as "Double", "with Cutout" or "with Handle", marks a part that
differs from the plain shape, and the name gets no shape.
"""

import math
import re
from collections.abc import Callable
from typing import Final, Literal

from bricky.catalog.families import LIP
from bricky.catalog.models import (
    ArchShape,
    BaseplateShape,
    BlockShape,
    CurvedSlopeShape,
    Family,
    InvertedSlopeShape,
    JumperShape,
    RoundShape,
    Shape,
    Side,
    SideStudsShape,
    SlopeShape,
)
from bricky.units import PLATE, STUD

_NEUTRAL: Final = frozenset(
    {
        "Groove",
        "Bottom Groove",
        "Bottom Tube",
        "Bottom Tubes",
        "Solid Bottom Tube",
        "Hollow Bottom Tube",
        "Cross Support",
        "Cross Supports",
        "Underside Cross Supports",
        "Inside Stud Holder",
        "Bottom Stud Holder",
        "Bottom Pin",
        "Flat Bottom Pin",
        "Connections between Studs",
        "Thick Top",
        "Reinforced Underside",
    }
)
"""Details that leave a part's outer shape and connectors as bricky models them."""

_STUD_KINDS: Final = frozenset(
    {"Open Stud", "Open Studs", "Hollow Stud", "Hollow Studs", "Solid Stud", "Solid Studs"}
)
"""Details that say how a part's studs are made: neutral for a part with studs on top, and the
mark of a different part on a tile or a curved slope."""

_ROUND_DETAILS: Final = frozenset({"Axle Hole", "Straight Side"})
"""Details neutral for round parts only: an axle hole through the middle, or a straight side."""

_SIZE: Final = r"(?P<a>\d+) x (?P<b>\d+)"
_HEIGHT: Final = r"(?: x (?P<height>\d+ \d/3|\d/3|\d+))?"
_DETAIL: Final = r"(?: (?P<detail>.+))?"


def _pattern(head: str) -> re.Pattern[str]:
    return re.compile(f"^{head}$")


_BLOCK: Final = _pattern(rf"(?P<kind>Brick|Plate|Tile) {_SIZE}{_HEIGHT}{_DETAIL}")
_BASEPLATE: Final = _pattern(rf"Baseplate {_SIZE}")
_SLOPE: Final = _pattern(rf"Slope (?P<angle>\d+) {_SIZE}{_HEIGHT}{_DETAIL}")
_INVERTED: Final = _pattern(rf"Slope, Inverted (?P<angle>\d+) {_SIZE}{_HEIGHT}{_DETAIL}")
_CURVED: Final = _pattern(rf"Slope, Curved {_SIZE}{_HEIGHT}{_DETAIL}")
_ROUND: Final = _pattern(rf"(?P<kind>Brick|Plate|Tile), Round {_SIZE}{_HEIGHT}{_DETAIL}")
_SIDE_STUDS: Final = _pattern(
    r"Brick, Modified 1 x (?P<length>\d+) with (?:(?P<count>\d+) )?Studs? on (?:(?P<sides>\d) )?"
    r"Sides?(?:, (?P<arrangement>Adjacent|Opposite))?"
)
_JUMPER: Final = _pattern(rf"Plate, Modified {_SIZE} with (?P<detail>.*\b1 Stud\b.*) \(Jumper\)")
_ARCH: Final = _pattern(rf"(?:Brick, )?Arch 1 x (?P<b>\d+){_HEIGHT}{_DETAIL}")

_SIDES_OF_ONE: Final[dict[tuple[int, bool], tuple[Side, ...]]] = {
    (1, False): ("-y",),
    (2, False): ("-y", "+y"),
    (2, True): ("-y", "+x"),
    (3, False): ("-y", "+x", "+y"),
    (4, False): ("-y", "+x", "+y", "-x"),
}
"""The studded faces of a 1 x 1 brick, by the number of sides and whether they are adjacent.

The first face is the front, -y."""

_SIDES_OF_LONG: Final[dict[int, tuple[Side, ...]]] = {1: ("-y",), 2: ("-y", "+y")}
"""The studded faces of a longer brick, by the number of sides: its long sides."""

_BLOCKS: Final[dict[str, Literal[Family.BRICK, Family.PLATE, Family.TILE]]] = {
    "Brick": Family.BRICK,
    "Plate": Family.PLATE,
    "Tile": Family.TILE,
}


def shape_from_name(name: str) -> Shape | None:
    """Return the shape a BrickLink part name describes, or ``None`` when it describes none.

    Examples:
        >>> shape_from_name("Slope 45 2 x 4")
        SlopeShape(size=(4, 2), family=<Family.SLOPE: 'slope'>, height=3, run=1, studs=True)
        >>> shape_from_name("Slope 45 2 x 2 Double") is None
        True
    """
    text = " ".join(name.split())
    for read in _READERS:
        shape = read(text)
        if shape is not None:
            return shape
    return None


def height_in_plates(height: str | None, default: int) -> int | None:
    """Convert a BrickLink height in bricks, such as ``"2"``, ``"2/3"`` or ``"1 1/3"``, to plates.

    Returns:
        The height in plates; ``default`` when ``height`` is ``None``; ``None`` for a height off
        the plate grid.
    """
    if height is None:
        return default
    whole, _, fraction = height.rpartition(" ") if " " in height else ("", "", height)
    if "/" in fraction:
        numerator, denominator = fraction.split("/")
        if denominator != "3":
            return None
        return int(whole or 0) * 3 + int(numerator)
    return int(fraction) * 3


def _neutral(detail: str | None, *, studs: bool, allowed: frozenset[str] = frozenset()) -> bool:
    """Whether every fragment of a detail is neutral, splitting at "with", "and", commas and dashes.

    Details about studs are neutral only for a part with studs on top. ``allowed`` adds the details
    neutral for one kind of part.
    """
    if detail is None:
        return True
    neutral = _NEUTRAL | allowed | (_STUD_KINDS if studs else frozenset())
    fragments = re.split(r"\s*(?:\bwith(?:out)?\b|\band\b|,|(?:^|\s)-\s)\s*", detail)
    return all(fragment in neutral for fragment in fragments if fragment)


def _block(name: str) -> Shape | None:
    match = _BLOCK.match(name)
    if match is None:
        return None
    kind = _BLOCKS[match["kind"]]
    if not _neutral(match["detail"], studs=kind is not Family.TILE):
        return None
    if kind is not Family.BRICK and match["height"] is not None:
        return None
    height = height_in_plates(match["height"], 3)
    if height is None:
        return None
    size = (int(match["a"]), int(match["b"]))
    return BlockShape(family=kind, size=size, height=height if match["height"] else None)


def _baseplate(name: str) -> Shape | None:
    match = _BASEPLATE.match(name)
    if match is None:
        return None
    return BaseplateShape(family=Family.BASEPLATE, size=(int(match["a"]), int(match["b"])))


def _slope(name: str) -> Shape | None:
    """Read a slope's name: its angle, its depth (front to back) and width, then its height.

    The slope rises from the lip at the front to the full height at the angle in the name, and
    covers the rows that rise needs. The rows behind it are flat on top and carry studs. A slope
    that covers its whole depth, such as a cheese slope, has no studs.
    """
    match = _SLOPE.match(name)
    if match is None:
        return None
    depth, width = int(match["a"]), int(match["b"])
    height = height_in_plates(match["height"], 3)
    if height is None:
        return None
    run = _run(int(match["angle"]), height, depth)
    if not _neutral(match["detail"], studs=run < depth):
        return None
    return SlopeShape(
        family=Family.SLOPE, size=(width, depth), height=height, run=run, studs=run < depth
    )


def _inverted_slope(name: str) -> Shape | None:
    """Read an inverted slope's name: the underside rises toward the front, as a slope falls."""
    match = _INVERTED.match(name)
    if match is None or not _neutral(match["detail"], studs=True):
        return None
    depth, width = int(match["a"]), int(match["b"])
    height = height_in_plates(match["height"], 3)
    if height is None or depth < 2:  # noqa: PLR2004 - the flat back row holds the anti-studs
        return None
    run = min(_run(int(match["angle"]), height, depth), depth - 1)
    return InvertedSlopeShape(
        family=Family.INVERTED_SLOPE, size=(width, depth), height=height, run=run
    )


def _run(angle: int, height: int, depth: int) -> int:
    """Return the rows a slope covers, from its angle in degrees and its height in plates.

    The slope rises ``height * PLATE - LIP``, from the lip to the full height. The rows it covers
    are that rise divided by the angle's tangent, rounded to whole rows and kept between one row
    and the part's depth.

    Examples:
        >>> _run(45, 3, 2), _run(33, 3, 3), _run(18, 3, 4), _run(30, 2, 1)
        (1, 2, 3, 1)
    """
    across = (height * PLATE - LIP) / math.tan(math.radians(angle))
    return min(max(round(across / STUD), 1), depth)


def _curved_slope(name: str) -> Shape | None:
    """Read a curved slope's name, which gets a shape only when it gives the slope's height.

    Curved slopes come in several heights, so a name without one describes no single shape.
    """
    match = _CURVED.match(name)
    if match is None or match["height"] is None or not _neutral(match["detail"], studs=False):
        return None
    height = height_in_plates(match["height"], 0)
    if not height:
        return None
    depth, width = int(match["a"]), int(match["b"])
    return CurvedSlopeShape(family=Family.CURVED_SLOPE, size=(width, depth), height=height)


def _round(name: str) -> Shape | None:
    """Read the name of a round brick, plate or tile one or two studs across.

    Bigger round parts have their studs set in, so their names get no shape.
    """
    match = _ROUND.match(name)
    if match is None:
        return None
    kind = match["kind"]
    if not _neutral(match["detail"], studs=kind != "Tile", allowed=_ROUND_DETAILS):
        return None
    width, length = int(match["a"]), int(match["b"])
    if width != length or width > 2:  # noqa: PLR2004 - see the docstring
        return None
    if kind != "Brick" and match["height"] is not None:
        return None
    height = height_in_plates(match["height"], 3) if kind == "Brick" else 1
    if height is None:
        return None
    return RoundShape(
        family=Family.ROUND, size=(width, length), height=height, studs=kind != "Tile"
    )


def _side_studs(name: str) -> Shape | None:
    """Read the name of a brick one stud wide with studs on its sides, one per position along each.

    The brick runs along x when unrotated, and its first studded side faces the front, -y.
    """
    match = _SIDE_STUDS.match(name)
    if match is None:
        return None
    length, sides = int(match["length"]), int(match["sides"] or 1)
    adjacent = match["arrangement"] == "Adjacent"
    if match["arrangement"] == "Opposite" and sides != 2:  # noqa: PLR2004 - opposite means two
        return None
    count = match["count"]
    if count is not None and int(count) != length:
        return None
    if length == 1:
        faces = _SIDES_OF_ONE.get((sides, adjacent))
    else:
        faces = None if adjacent else _SIDES_OF_LONG.get(sides)
    if faces is None:
        return None
    return SideStudsShape(family=Family.SIDE_STUDS, size=(length, 1), sides=faces)


def _jumper(name: str) -> Shape | None:
    match = _JUMPER.match(name)
    if match is None:
        return None
    return JumperShape(
        family=Family.JUMPER,
        size=(int(match["a"]), int(match["b"])),
        center_anti_stud="Bottom Stud Holder" in match["detail"],
    )


def _arch(name: str) -> Shape | None:
    """Read a plain arch's name: one stud wide, with a one-stud leg at each end of the opening."""
    match = _ARCH.match(name)
    if match is None or not _neutral(match["detail"], studs=True):
        return None
    length = int(match["b"])
    height = height_in_plates(match["height"], 3)
    if height is None or length < 3 or height < 2:  # noqa: PLR2004 - two legs and an opening
        return None
    return ArchShape(family=Family.ARCH, size=(1, length), height=height, span=length - 2)


_READERS: Final[tuple[Callable[[str], Shape | None], ...]] = (
    _block,
    _baseplate,
    _slope,
    _inverted_slope,
    _curved_slope,
    _round,
    _side_studs,
    _jumper,
    _arch,
)
