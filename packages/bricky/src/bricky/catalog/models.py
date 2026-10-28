"""Catalog data types: catalog parts and their shapes, generated parts, connectors and colors.

A catalog part pairs what BrickLink says about a part (its id, name, category and the colors it
comes in) with the shape bricky generates its geometry from, when bricky has one for it.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bricky.geometry import Pose, Solid, Vector
from bricky.units import STUD


class ConnectorKind(StrEnum):
    """The kinds of connection point bricky understands."""

    STUD = "stud"
    """A stud, on top of a part or on one of its sides."""

    ANTI_STUD = "anti_stud"
    """A receptor, under a part, that a stud clicks into."""

    @property
    def mate(self) -> ConnectorKind:
        """The kind this one connects to."""
        return ConnectorKind.ANTI_STUD if self is ConnectorKind.STUD else ConnectorKind.STUD


@dataclass(frozen=True, slots=True)
class Connector:
    """A connection point, in its part's local frame or in world space."""

    kind: ConnectorKind
    position: Vector
    """Center of the interface, on the part's face."""

    normal: Vector
    """Outward unit axis."""

    def transformed(self, pose: Pose) -> Connector:
        """Return this connector placed by a pose."""
        return Connector(self.kind, pose.apply(self.position), pose.apply_direction(self.normal))


class Family(StrEnum):
    """Part families whose geometry bricky generates."""

    BRICK = "brick"
    PLATE = "plate"
    TILE = "tile"
    BASEPLATE = "baseplate"
    SLOPE = "slope"
    INVERTED_SLOPE = "inverted_slope"
    CURVED_SLOPE = "curved_slope"
    ROUND = "round"
    SIDE_STUDS = "side_studs"
    JUMPER = "jumper"
    ARCH = "arch"
    BOXES = "boxes"
    """Any part, its body given as boxes and its connectors one by one, as converted from LDraw."""


type Side = Literal["-x", "+x", "-y", "+y"]
"""A vertical face of a part, by the axis it faces in the part's own frame."""

type Studs = Annotated[int, Field(ge=1, le=64)]


class _Shape(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    size: tuple[Studs, Studs] = Field(description="Studs along the part's local x and y axes.")


class BlockShape(_Shape):
    """A brick, plate or tile: a box with a stud on top (but not tiles) at every position."""

    family: Literal[Family.BRICK, Family.PLATE, Family.TILE]
    height: int | None = Field(
        default=None, ge=1, description="Plates tall; 3 for a brick and 1 for a plate or tile."
    )


class BaseplateShape(_Shape):
    """A thin, flat-bottomed plate with studs on top, to build on."""

    family: Literal[Family.BASEPLATE]


class SlopeShape(_Shape):
    """A slope falling toward the front (local -y), studs on its flat top at the back."""

    family: Literal[Family.SLOPE]
    height: int = Field(default=3, ge=1, description="Plates tall.")
    run: int = Field(ge=1, description="Studs the slope covers, from the front edge back.")
    studs: bool = Field(default=True, description="Whether the flat top carries studs.")


class InvertedSlopeShape(_Shape):
    """A slope underneath, rising toward the front (local -y), studs all over its flat top."""

    family: Literal[Family.INVERTED_SLOPE]
    height: int = Field(default=3, ge=1, description="Plates tall.")
    run: int = Field(ge=1, description="Studs the slope covers, from the front edge back.")


class CurvedSlopeShape(_Shape):
    """A smooth slope curving down toward the front (local -y), with no studs."""

    family: Literal[Family.CURVED_SLOPE]
    height: int = Field(default=2, ge=1, description="Plates tall.")


class RoundShape(_Shape):
    """A round brick, plate or tile: a cylinder filling a square footprint."""

    family: Literal[Family.ROUND]
    height: int = Field(ge=1, description="Plates tall.")
    studs: bool = Field(default=True, description="Whether the top carries studs.")

    @model_validator(mode="after")
    def _square(self) -> Self:
        width, length = self.size
        if width != length:
            msg = f"a round part needs a square footprint, not {width} x {length}"
            raise ValueError(msg)
        return self


class SideStudsShape(_Shape):
    """A brick with studs on some of its vertical faces as well as on top."""

    family: Literal[Family.SIDE_STUDS]
    height: int = Field(default=3, ge=1, description="Plates tall.")
    sides: tuple[Side, ...] = Field(min_length=1, description="Faces carrying studs.")


class JumperShape(_Shape):
    """A plate with a single stud in the middle of its top."""

    family: Literal[Family.JUMPER]
    center_anti_stud: bool = Field(
        default=False, description="Whether its underside also grips a stud in the middle."
    )


class ArchShape(_Shape):
    """A one-stud-wide arch along local y: two legs and a curved opening between them."""

    family: Literal[Family.ARCH]
    height: int = Field(ge=2, description="Plates tall.")
    span: int = Field(ge=1, description="Studs the opening spans, centered between the legs.")

    @model_validator(mode="after")
    def _legs(self) -> Self:
        legs = self.size[1] - self.span
        if legs < 2 or legs % 2:  # noqa: PLR2004 - one whole-stud leg at each end
            msg = (
                f"an arch {self.size[1]} studs long cannot span {self.span}: the legs must be equal"
            )
            raise ValueError(msg)
        return self


type Axis = Literal["+x", "-x", "+y", "-y", "+z", "-z"]
type Corners = tuple[int, int, int, int, int, int]


class BoxesShape(BaseModel):
    """Any part, given explicitly: its body as boxes, its studs and its anti-studs.

    Coordinates are base units in the part's frame, the minimum corner of its body at the origin.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    family: Literal[Family.BOXES]
    size: tuple[int, int, int] = Field(
        description="The part's bounding box, from the origin, which the body lies within."
    )
    boxes: tuple[Corners, ...] = Field(
        min_length=1, description="The body: boxes as x0, y0, z0, x1, y1, z1."
    )
    studs: tuple[tuple[int, int, int, Axis], ...] = Field(
        default=(), description="Each stud: where its base sits, x, y, z, and the axis it points."
    )
    anti_studs: tuple[tuple[int, int], ...] = Field(
        default=(), description="Each anti-stud on the bottom face, z = 0: x, y."
    )
    source: str = Field(description="Where the shape was converted from, such as 'LDraw 3001.dat'.")

    @model_validator(mode="after")
    def _within(self) -> Self:
        for box in self.boxes:
            if any(not 0 <= box[a] < box[a + 3] <= self.size[a] for a in range(3)):
                msg = f"box {box} has no volume or reaches outside the size {self.size}"
                raise ValueError(msg)
        return self


type Shape = Annotated[
    BlockShape
    | BaseplateShape
    | SlopeShape
    | InvertedSlopeShape
    | CurvedSlopeShape
    | RoundShape
    | SideStudsShape
    | JumperShape
    | ArchShape
    | BoxesShape,
    Field(discriminator="family"),
]
"""How bricky generates a part's geometry: its family and the numbers the family needs."""


class CatalogPart(BaseModel):
    """A part as the catalog lists it: BrickLink's facts about it, and bricky's shape for it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^\S+$", description="BrickLink item number, such as '3001'.")
    name: str = Field(description="BrickLink item name, such as 'Brick 2 x 4'.")
    category: str | None = Field(
        default=None, description="BrickLink category, such as 'Brick, Round'."
    )
    alternates: tuple[str, ...] = Field(
        default=(), description="Other item numbers BrickLink lists for the part."
    )
    colors: tuple[int, ...] = Field(
        default=(), description="BrickLink color ids the part is known in, when the source says."
    )
    shape: Shape | None = Field(
        default=None,
        description="The shape bricky generates the part's geometry from; null when bricky has "
        "none for it, or when the part takes its shape from its base.",
    )
    base: str | None = Field(
        default=None,
        description="For a printed part, the item number of the part it is printed on, whose "
        "shape it has.",
    )


class ColorType(StrEnum):
    """BrickLink color types, which change how a color looks."""

    SOLID = "solid"
    TRANSPARENT = "transparent"
    CHROME = "chrome"
    PEARL = "pearl"
    METALLIC = "metallic"
    SATIN = "satin"
    MILKY = "milky"
    GLITTER = "glitter"
    SPECKLE = "speckle"
    MODULEX = "modulex"


class Color(BaseModel):
    """A color, identified by its BrickLink color id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int = Field(ge=1, description="BrickLink color id.")
    name: str = Field(description="BrickLink color name.")
    type: ColorType = Field(default=ColorType.SOLID, description="BrickLink color type.")
    rgb: str = Field(
        pattern=r"^#[0-9A-F]{6}$", description="Display color for renders, as #RRGGBB."
    )


@dataclass(frozen=True, slots=True)
class Part:
    """A catalog part with its geometry in its local frame.

    The local frame puts the bounding box's minimum corner at the origin, with x along the part's
    width, y along its length and z up. The body is a union of solids. Studs are connectors, not
    solids, and stand outside the bounding box.
    """

    id: str
    name: str
    family: Family
    size: Vector
    solids: tuple[Solid, ...]
    connectors: tuple[Connector, ...]
    note: str = ""
    """How the part sits when placed unrotated, for parts where it matters."""

    category: str | None = None
    """BrickLink category, such as ``"Brick, Round"``."""

    @property
    def stud_count(self) -> int:
        """Number of studs on the part."""
        return sum(1 for c in self.connectors if c.kind is ConnectorKind.STUD)

    @property
    def footprint(self) -> tuple[int, int]:
        """Width and length in studs, along the local x and y axes."""
        return (-(-self.size.x // STUD), -(-self.size.y // STUD))
