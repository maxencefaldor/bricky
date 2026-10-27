"""Geometry generators for part families.

A family turns a few numbers from the catalog data files into a part's solids and connectors, so
dozens of parts share one tested definition.
"""

from typing import Final

from bricky.catalog.models import Connector, ConnectorKind, Family, Part, PartSpec
from bricky.geometry import DOWN, ORIGIN, UP, Box, Vec3
from bricky.units import BRICK, PLATE, STUD

HEIGHTS: Final[dict[Family, int]] = {Family.BRICK: BRICK, Family.PLATE: PLATE, Family.TILE: PLATE}
"""Body height of each family, in base units."""


def build_part(spec: PartSpec) -> Part:
    """Generate a part's solids and connectors from its catalog entry.

    Bricks and plates carry a stud on top and a receptor underneath at every stud position. Tiles
    have the receptors but a smooth top.
    """
    height = HEIGHTS[spec.family]
    size = Vec3(spec.width * STUD, spec.length * STUD, height)
    connectors: list[Connector] = []
    for i in range(spec.width):
        for j in range(spec.length):
            x = i * STUD + STUD // 2
            y = j * STUD + STUD // 2
            connectors.append(Connector(ConnectorKind.ANTI_STUD, Vec3(x, y, 0), DOWN))
            if spec.family is not Family.TILE:
                connectors.append(Connector(ConnectorKind.STUD, Vec3(x, y, height), UP))
    return Part(
        id=spec.id,
        name=spec.name,
        family=spec.family,
        size=size,
        solids=(Box(ORIGIN, size),),
        connectors=tuple(connectors),
    )
