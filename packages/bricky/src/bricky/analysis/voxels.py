# Copyright 2026 Maxence Faldor
"""The model as voxels: which element fills each voxel.

A voxel is one stud wide, one stud deep and one plate tall: the grid that parts are
placed on. An element fills a voxel when the voxel's center lies inside its body. Every
voxel of a model free of overlaps therefore belongs to at most one element, and a
comparison with a target made of voxels is exact. Studs belong to no body and fill no
voxel.
"""

from dataclasses import dataclass
from typing import Final

from bricky.analysis.world import World, build_world
from bricky.catalog import Catalog, default_catalog
from bricky.geometry import Solid, Vector
from bricky.model import Model
from bricky.units import PLATE, STUD

type VoxelKey = tuple[int, int, int]
"""A voxel by its minimum corner: x and y in studs, z in plates."""


@dataclass(frozen=True, slots=True)
class Voxel:
    """A filled voxel: the element whose body fills it, and that element's color."""

    uid: str
    """The element's uid, such as ``"bay2/e3"``."""

    color: int
    """The element's color id."""


_HALF_STUD: Final = STUD // 2
_HALF_PLATE: Final = PLATE // 2


def world_voxels(world: World) -> dict[VoxelKey, Voxel]:
    """Return every filled voxel of a placed model, keyed by its minimum corner.

    A voxel that overlapping elements both fill belongs to the one placed first.
    """
    voxels: dict[VoxelKey, Voxel] = {}
    for element in world.elements:
        voxel = Voxel(element.uid, element.color)
        for solid in element.solids:
            for key in _candidates(solid):
                if key not in voxels and solid.contains(_center(key)):
                    voxels[key] = voxel
    return voxels


def model_voxels(model: Model, catalog: Catalog | None = None) -> dict[VoxelKey, Voxel]:
    """Return each voxel a model fills, keyed by its minimum corner in studs and plates.

    Examples:
        >>> from bricky import ModelBuilder, voxels
        >>> builder = ModelBuilder("wall")
        >>> builder.place("3004", at=(0, 0, 0), color="Red")  # Brick 1 x 2
        'e1'
        >>> sorted(voxels(builder.build()))
        [(0, 0, 0), (0, 0, 1), (0, 0, 2), (0, 1, 0), (0, 1, 1), (0, 1, 2)]
    """
    return world_voxels(build_world(model, catalog or default_catalog()))


def _candidates(solid: Solid) -> list[VoxelKey]:
    low, high = solid.bounds.min, solid.bounds.max
    return [
        (x, y, z)
        for x in range(low.x // STUD, -(-high.x // STUD))
        for y in range(low.y // STUD, -(-high.y // STUD))
        for z in range(low.z // PLATE, -(-high.z // PLATE))
    ]


def _center(key: VoxelKey) -> Vector:
    x, y, z = key
    return Vector(x * STUD + _HALF_STUD, y * STUD + _HALF_STUD, z * PLATE + _HALF_PLATE)
