# Copyright 2026 Maxence Faldor
"""The analysis context: shared analyses, each computed once, on first use."""

from __future__ import annotations

from collections.abc import Mapping
from functools import cached_property
from types import MappingProxyType

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
from bricky.settings import Level, Settings


class Context:
    """One model under check, with analyses all passes share, computed on first use."""

    def __init__(
        self,
        model: Model,
        catalog: Catalog,
        settings: Settings | None = None,
        levels: Mapping[str, Level] | None = None,
    ) -> None:
        """Hold a model, its catalog, settings and rule levels; the rest comes on use.

        Settings are read from the environment and the configuration file by default.
        The levels are those of the check that runs the passes, by rule name; a pass
        can skip the work of rules a check ignores, as ty's lints can.
        """
        self.model = model
        self.catalog = catalog
        self.settings = settings or Settings()
        self.levels: Mapping[str, Level] = MappingProxyType(dict(levels or {}))

    def checks(self, rule: str, default: Level) -> bool:
        """Whether the check reports ``rule``, at the ``default`` level when unset."""
        return self.levels.get(rule, default) is not Level.IGNORE

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
