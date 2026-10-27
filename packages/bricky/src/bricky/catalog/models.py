"""Catalog data types: part specifications, parts, connectors and colours."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from bricky.geometry import Pose, Solid, Vec3
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
    pos: Vec3
    """Centre of the interface, on the part's face."""

    normal: Vec3
    """Outward unit axis."""

    def transformed(self, pose: Pose) -> Connector:
        """Return this connector placed by a pose."""
        return Connector(self.kind, pose.apply(self.pos), pose.apply_direction(self.normal))


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


type Side = Literal["-x", "+x", "-y", "+y"]
"""A vertical face of a part, by the axis it faces in the part's own frame."""


class _Spec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[0-9a-z]+$", description="BrickLink item number, such as '3001'.")
    name: str = Field(description="BrickLink item name, such as 'Brick 2 x 4'.")
    size: tuple[
        Annotated[int, Field(ge=1, le=64)],
        Annotated[int, Field(ge=1, le=64)],
    ] = Field(description="Studs along the part's local x and y axes.")


class BlockSpec(_Spec):
    """A brick, plate or tile: a box with a stud on top (but not tiles) at every position."""

    family: Literal[Family.BRICK, Family.PLATE, Family.TILE]
    height: int | None = Field(
        default=None, ge=1, description="Plates tall; 3 for a brick and 1 for a plate or tile."
    )


class BaseplateSpec(_Spec):
    """A thin, flat-bottomed plate with studs on top, to build on."""

    family: Literal[Family.BASEPLATE]


class SlopeSpec(_Spec):
    """A slope falling toward the front (local -y), studs on its flat top at the back."""

    family: Literal[Family.SLOPE]
    height: int = Field(default=3, ge=1, description="Plates tall.")
    run: int = Field(ge=1, description="Studs the slope covers, from the front edge back.")
    studs: bool = Field(default=True, description="Whether the flat top carries studs.")


class InvertedSlopeSpec(_Spec):
    """A slope underneath, rising toward the front (local -y), studs all over its flat top."""

    family: Literal[Family.INVERTED_SLOPE]
    height: int = Field(default=3, ge=1, description="Plates tall.")
    run: int = Field(ge=1, description="Studs the slope covers, from the front edge back.")


class CurvedSlopeSpec(_Spec):
    """A smooth slope curving down toward the front (local -y), with no studs."""

    family: Literal[Family.CURVED_SLOPE]
    height: int = Field(default=2, ge=1, description="Plates tall.")


class RoundSpec(_Spec):
    """A round brick, plate or tile: a cylinder filling a square footprint."""

    family: Literal[Family.ROUND]
    height: int = Field(ge=1, description="Plates tall.")
    studs: bool = Field(default=True, description="Whether the top carries studs.")


class SideStudsSpec(_Spec):
    """A brick with studs on some of its vertical faces as well as on top."""

    family: Literal[Family.SIDE_STUDS]
    height: int = Field(default=3, ge=1, description="Plates tall.")
    sides: tuple[Side, ...] = Field(min_length=1, description="Faces carrying studs.")


class JumperSpec(_Spec):
    """A plate with a single stud in the middle of its top."""

    family: Literal[Family.JUMPER]
    centre_receptor: bool = Field(
        default=False, description="Whether its underside also grips a stud in the middle."
    )


class ArchSpec(_Spec):
    """A one-stud-wide arch along local y: two legs and a curved opening between them."""

    family: Literal[Family.ARCH]
    height: int = Field(ge=2, description="Plates tall.")
    span: int = Field(ge=1, description="Studs the opening spans, centred between the legs.")


type PartSpec = Annotated[
    BlockSpec
    | BaseplateSpec
    | SlopeSpec
    | InvertedSlopeSpec
    | CurvedSlopeSpec
    | RoundSpec
    | SideStudsSpec
    | JumperSpec
    | ArchSpec,
    Field(discriminator="family"),
]
"""A part as stored in the catalog data files, by family."""


class ColorType(StrEnum):
    """BrickLink colour types that change how a colour looks."""

    SOLID = "solid"
    TRANSPARENT = "transparent"
    PEARL = "pearl"


class Color(BaseModel):
    """A colour, identified by its BrickLink colour id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int = Field(ge=0, description="BrickLink colour id.")
    name: str = Field(description="BrickLink colour name.")
    type: ColorType = Field(default=ColorType.SOLID, description="BrickLink colour type.")
    rgb: str = Field(
        pattern=r"^#[0-9A-F]{6}$", description="Display colour for renders, as #RRGGBB."
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
    size: Vec3
    solids: tuple[Solid, ...]
    connectors: tuple[Connector, ...]
    note: str = ""
    """How the part sits when placed unturned, for parts where it matters."""

    @property
    def stud_count(self) -> int:
        """Number of studs on the part."""
        return sum(1 for c in self.connectors if c.kind is ConnectorKind.STUD)

    @property
    def footprint(self) -> tuple[int, int]:
        """Width and length in studs, along the local x and y axes."""
        return (-(-self.size.x // STUD), -(-self.size.y // STUD))
