# Copyright 2026 Maxence Faldor
"""The analysis context: shared analyses, each computed once, on first use."""

from __future__ import annotations

from functools import cached_property

from bricky.analysis.connections import (
    AntiStudIndex,
    Connection,
    anti_stud_index,
    find_connections,
)
from bricky.analysis.spatial import SpatialHash
from bricky.analysis.voxels import Voxel, VoxelKey, world_voxels
from bricky.analysis.world import World, build_world
from bricky.catalog import Catalog
from bricky.model import Model


class Context:
    """One model under check, with analyses all passes share, computed on first use."""

    def __init__(self, model: Model, catalog: Catalog) -> None:
        """Hold a model and its catalog; derived data comes on first use."""
        self.model = model
        self.catalog = catalog

    @cached_property
    def world(self) -> World:
        """Every element placed in world space."""
        return build_world(self.model, self.catalog)

    @cached_property
    def voxels(self) -> dict[VoxelKey, Voxel]:
        """Which element fills each voxel."""
        return world_voxels(self.world)

    @cached_property
    def solid_index(self) -> SpatialHash[int]:
        """Spatial index of every solid, keyed by the index of its element."""
        index: SpatialHash[int] = SpatialHash()
        for i, element in enumerate(self.world.elements):
            for solid in element.solids:
                index.insert(i, solid.bounds)
        return index

    @cached_property
    def anti_studs(self) -> AntiStudIndex:
        """The elements with an anti-stud at each world position and normal."""
        return anti_stud_index(self.world)

    @cached_property
    def connections(self) -> tuple[Connection, ...]:
        """Every pair of elements joined by studs."""
        return find_connections(self.world, self.anti_studs)
