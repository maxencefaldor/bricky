"""Read a part's shape from its BrickLink name.

BrickLink names the ordinary building parts by a strict pattern: the kind of part, its size in
studs, its height when that is not the usual one, then any details. "Brick 1 x 2 x 2" is a brick
one stud wide, two long and two bricks tall; "Slope 45 2 x 4" a slope two studs deep and four wide;
"Plate, Round 2 x 2 with Axle Hole" a round plate.

:func:`shape_from_name` returns the shape of every name that follows a pattern bricky has a family
for, and ``None`` for every other name rather than guess. A name may carry details that leave the
outer shape and the connectors as bricky models them, such as a groove along the bottom edge or
the tubes underneath; any other detail, such as "Double", "with Cutout" or "with Handle", means the
part is not the plain shape, and the name gets no shape.
"""

import re
from collections.abc import Callable
from typing import Final, Literal

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
        "Open Stud",
        "Open Studs",
        "Hollow Stud",
        "Hollow Studs",
        "Solid Stud",
        "Solid Studs",
    }
)
"""Details that leave a part's outer shape and connectors as bricky models them."""

_ROUND_NEUTRAL: Final = _NEUTRAL | {"Axle Hole", "Straight Side"}
"""Details of round parts: an axle hole through the middle, or a straight-sided plate."""

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
    r"Brick, Modified 1 x (?P<length>\d+) with (?:(?P<count>\d+) )?Studs? on (?P<sides>\d) "
    r"Sides?(?P<adjacent>, Adjacent)?"
)
_JUMPER: Final = _pattern(rf"Plate, Modified {_SIZE} with (?P<detail>.*\b1 Stud\b.*) \(Jumper\)")
_ARCH: Final = _pattern(rf"(?:Brick, )?Arch 1 x (?P<b>\d+){_HEIGHT}")

_SIDES_OF_ONE: Final[dict[tuple[int, bool], tuple[Side, ...]]] = {
    (1, False): ("-y",),
    (2, False): ("-y", "+y"),
    (2, True): ("-y", "+x"),
    (3, False): ("-y", "+x", "+y"),
    (4, False): ("-y", "+x", "+y", "-x"),
}
"""The faces of a 1 x 1 brick with studs on n sides: the first faces front, -y."""

_SIDES_OF_LONG: Final[dict[int, tuple[Side, ...]]] = {1: ("-y",), 2: ("-y", "+y")}
"""The faces of a longer brick with studs on n sides: its long sides."""

_BLOCKS: Final[dict[str, Literal[Family.BRICK, Family.PLATE, Family.TILE]]] = {
    "Brick": Family.BRICK,
    "Plate": Family.PLATE,
    "Tile": Family.TILE,
}


def shape_from_name(name: str) -> Shape | None:
    """Return the shape a BrickLink part name describes, or ``None`` when it describes none.

    Example:
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


def plates(height: str | None, default: int) -> int | None:
    """Convert a BrickLink height in bricks, such as ``"2"``, ``"2/3"`` or ``"1 1/3"``, to plates.

    Returns ``default`` when there is no height, and ``None`` for heights off the plate grid.
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


def _neutral(detail: str | None, allowed: frozenset[str] = _NEUTRAL) -> bool:
    """Whether every fragment of a detail is allowed, splitting it at "with", "and" and commas."""
    if detail is None:
        return True
    fragments = re.split(r"\s*(?:\bwith(?:out)?\b|\band\b|,)\s*", detail)
    return all(fragment in allowed for fragment in fragments if fragment)


def _block(name: str) -> Shape | None:
    match = _BLOCK.match(name)
    if match is None or not _neutral(match["detail"]):
        return None
    kind = _BLOCKS[match["kind"]]
    if kind is not Family.BRICK and match["height"] is not None:
        return None
    height = plates(match["height"], 3)
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
    """Slopes are named by angle, then depth (front to back) and width, then height in bricks.

    The slope covers every row but the last, whose flat top carries the studs; a slope one row
    deep, such as a cheese slope, is all slope and has no studs.
    """
    match = _SLOPE.match(name)
    if match is None or not _neutral(match["detail"]):
        return None
    depth, width = int(match["a"]), int(match["b"])
    height = plates(match["height"], 3)
    if height is None:
        return None
    run = max(depth - 1, 1)
    return SlopeShape(
        family=Family.SLOPE, size=(width, depth), height=height, run=run, studs=depth > 1
    )


def _inverted_slope(name: str) -> Shape | None:
    match = _INVERTED.match(name)
    if match is None or not _neutral(match["detail"]):
        return None
    depth, width = int(match["a"]), int(match["b"])
    height = plates(match["height"], 3)
    if height is None or depth < 2:  # noqa: PLR2004 - the flat back row grips the studs below
        return None
    return InvertedSlopeShape(
        family=Family.INVERTED_SLOPE, size=(width, depth), height=height, run=depth - 1
    )


def _curved_slope(name: str) -> Shape | None:
    """Curved slopes come in several heights, so only names that give the height have a shape."""
    match = _CURVED.match(name)
    if match is None or match["height"] is None or not _neutral(match["detail"]):
        return None
    height = plates(match["height"], 0)
    if not height:
        return None
    depth, width = int(match["a"]), int(match["b"])
    return CurvedSlopeShape(family=Family.CURVED_SLOPE, size=(width, depth), height=height)


def _round(name: str) -> Shape | None:
    """Round bricks, plates and tiles, one or two studs across: bigger ones have studs set in."""
    match = _ROUND.match(name)
    if match is None or not _neutral(match["detail"], _ROUND_NEUTRAL):
        return None
    width, length = int(match["a"]), int(match["b"])
    if width != length or width > 2:  # noqa: PLR2004 - see the docstring
        return None
    kind = match["kind"]
    if kind != "Brick" and match["height"] is not None:
        return None
    height = plates(match["height"], 3) if kind == "Brick" else 1
    if height is None:
        return None
    return RoundShape(
        family=Family.ROUND, size=(width, length), height=height, studs=kind != "Tile"
    )


def _side_studs(name: str) -> Shape | None:
    """Bricks one stud wide with studs on their sides: one stud per position along each face.

    Unrotated, the brick runs along x and its first studded side faces front, -y.
    """
    match = _SIDE_STUDS.match(name)
    if match is None:
        return None
    length, sides, adjacent = int(match["length"]), int(match["sides"]), bool(match["adjacent"])
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
    """Plain arches: one stud wide, a one-stud leg at each end, the opening between them."""
    match = _ARCH.match(name)
    if match is None:
        return None
    length = int(match["b"])
    height = plates(match["height"], 3)
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
