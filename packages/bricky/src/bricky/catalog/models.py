"""Catalog data types: parts, connectors and colours."""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from bricky.geometry import Box, Pose, Vec3
from bricky.units import STUD


class ConnectorKind(StrEnum):
    """The kinds of connection point bricky understands."""

    STUD = "stud"
    """A stud on top of a part."""

    ANTI_STUD = "anti_stud"
    """A receptor under a part that a stud clicks into."""

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


class PartSpec(BaseModel):
    """A part as stored in the catalog data files."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[0-9a-z]+$", description="BrickLink item number, such as '3001'.")
    name: str = Field(description="BrickLink item name, such as 'Brick 2 x 4'.")
    family: Family = Field(description="Family whose generator builds the geometry.")
    width: int = Field(ge=1, le=16, description="Studs along the local x axis.")
    length: int = Field(ge=1, le=16, description="Studs along the local y axis.")


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
    width, y along its length and z up. Studs are connectors, not solids.
    """

    id: str
    name: str
    family: Family
    size: Vec3
    solids: tuple[Box, ...]
    connectors: tuple[Connector, ...]

    @property
    def stud_count(self) -> int:
        """Number of studs on the part."""
        return sum(1 for c in self.connectors if c.kind is ConnectorKind.STUD)

    @property
    def footprint(self) -> tuple[int, int]:
        """Width and length in studs, along the local x and y axes."""
        return (self.size.x // STUD, self.size.y // STUD)
