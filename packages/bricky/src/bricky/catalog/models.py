"""Catalog data types: catalog parts and their shapes, generated parts, connectors and colors.

A catalog part pairs BrickLink's facts about a part (its id, name, category and the colors it comes
in) with the shape bricky generates its geometry from, when bricky has one.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bricky.geometry import Pose, Solid, Vector
from bricky.units import STUD


class ConnectorKind(StrEnum):
    """The kinds of connector: studs and anti-studs."""

    STUD = "stud"
    """A stud, on a part's top or on one of its sides."""

    ANTI_STUD = "anti_stud"
    """The socket under a part that a stud fits."""

    @property
    def mate(self) -> ConnectorKind:
        """The kind that fits this one."""
        return ConnectorKind.ANTI_STUD if self is ConnectorKind.STUD else ConnectorKind.STUD


@dataclass(frozen=True, slots=True)
class Connector:
    """A stud or an anti-stud, in its part's local frame or in world space."""

    kind: ConnectorKind
    position: Vector
    """The connector's center, on the part's face."""

    normal: Vector
    """The outward unit axis."""

    def transformed(self, pose: Pose) -> Connector:
        """Return this connector placed by a pose."""
        return Connector(self.kind, pose.apply(self.position), pose.apply_direction(self.normal))


class Family(StrEnum):
    """The families: generators that convert a part's shape into its geometry."""

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
    """Any part, with its body as boxes and its connectors one by one, as converted from LDraw."""


type Side = Literal["-x", "+x", "-y", "+y"]
"""A vertical face of a part, by the axis it faces in the part's own frame."""

type Studs = Annotated[int, Field(ge=1, le=64)]


class _Shape(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    size: tuple[Studs, Studs] = Field(description="Studs along the part's local x and y axes.")


class BlockShape(_Shape):
    """A brick, plate or tile: a box with a stud at every position on top, except on a tile."""

    family: Literal[Family.BRICK, Family.PLATE, Family.TILE]
    height: int | None = Field(
        default=None,
        ge=1,
        description="Plates tall; by default 3 for a brick, 1 for a plate or tile.",
    )


class BaseplateShape(_Shape):
    """A thin, flat-bottomed plate with studs on top, to build on."""

    family: Literal[Family.BASEPLATE]


class SlopeShape(_Shape):
    """A slope falling toward the front (local -y), with studs on its flat top at the back."""

    family: Literal[Family.SLOPE]
    height: int = Field(default=3, ge=1, description="Plates tall.")
    run: int = Field(ge=1, description="Studs the slope covers, from the front edge back.")
    studs: bool = Field(default=True, description="Whether the flat top carries studs.")


class InvertedSlopeShape(_Shape):
    """A slope underneath, rising toward the front (local -y), with studs all over its top."""

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
            message = f"a round part needs a square footprint, not {width} x {length}"
            raise ValueError(message)
        return self


class SideStudsShape(_Shape):
    """A brick with studs on some of its vertical faces as well as on top."""

    family: Literal[Family.SIDE_STUDS]
    height: int = Field(default=3, ge=1, description="Plates tall.")
    sides: tuple[Side, ...] = Field(min_length=1, description="The faces that carry studs.")


class JumperShape(_Shape):
    """A plate with a single stud in the middle of its top."""

    family: Literal[Family.JUMPER]
    center_anti_stud: bool = Field(
        default=False, description="Whether the underside also has an anti-stud in the middle."
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
            message = (
                f"an arch {self.size[1]} studs long cannot span {self.span}: the legs must be equal"
            )
            raise ValueError(message)
        return self


type Axis = Literal["+x", "-x", "+y", "-y", "+z", "-z"]
type Corners = tuple[int, int, int, int, int, int]


class BoxesShape(BaseModel):
    """Any part, given explicitly: its body as boxes, its studs and its anti-studs.

    Coordinates are base units in the part's frame, with the part's minimum corner at the origin.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    family: Literal[Family.BOXES]
    size: tuple[int, int, int] = Field(
        description="The part's bounding box, from the origin; the body lies within it."
    )
    boxes: tuple[Corners, ...] = Field(
        min_length=1, description="The body: boxes as x0, y0, z0, x1, y1, z1."
    )
    studs: tuple[tuple[int, int, int, Axis], ...] = Field(
        default=(), description="Each stud: the x, y, z of its base, and the axis it points along."
    )
    anti_studs: tuple[tuple[int, int], ...] = Field(
        default=(), description="Each anti-stud: its x, y on the bottom face, z = 0."
    )
    source: str = Field(description="Where the shape was converted from, such as 'LDraw 3001.dat'.")
    rotation: Literal["R0", "R90", "R180", "R270"] = Field(
        default="R0",
        description="A rotation about the vertical axis that turns the source's orientation into "
        "the one the part's name describes, where the import found one.",
    )

    @model_validator(mode="after")
    def _within(self) -> Self:
        for box in self.boxes:
            if any(not 0 <= box[a] < box[a + 3] <= self.size[a] for a in range(3)):
                message = f"box {box} has no volume or reaches outside the size {self.size}"
                raise ValueError(message)
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

    id: str = Field(pattern=r"^\S+$", description="BrickLink id, such as '3001'.")
    name: str = Field(description="BrickLink name, such as 'Brick 2 x 4'.")
    category: str | None = Field(
        default=None, description="BrickLink category, such as 'Brick, Round'."
    )
    alternates: tuple[str, ...] = Field(
        default=(), description="Other ids BrickLink lists for the part."
    )
    colors: tuple[int, ...] = Field(
        default=(),
        description="BrickLink ids of the colors the part comes in, when the source lists them.",
    )
    shape: Shape | None = Field(
        default=None,
        description="The shape bricky generates the part's geometry from; null when bricky has "
        "none, or when the part takes its base's shape.",
    )
    base: str | None = Field(
        default=None,
        description="For a printed part, the id of the part it is printed on, its base.",
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
    width, y along its length and z up. The body is a union of solids. Studs are connectors and
    stand outside the bounding box.
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
        """The number of studs on the part."""
        return sum(1 for c in self.connectors if c.kind is ConnectorKind.STUD)

    @property
    def footprint(self) -> tuple[int, int]:
        """Width and length in studs, along the local x and y axes."""
        return (-(-self.size.x // STUD), -(-self.size.y // STUD))
