"""The analysis context: shared analyses, each computed once, on first use."""

from functools import cached_property

from bricky.analysis.cells import Cell, CellKey, world_cells
from bricky.analysis.links import Link, ReceptorIndex, find_links, receptor_index
from bricky.analysis.spatial import SpatialHash
from bricky.analysis.world import World, build_world
from bricky.catalog import Catalog
from bricky.model import Model


class Context:
    """One model under check, with lazily computed analyses that every pass can share."""

    def __init__(self, model: Model, catalog: Catalog) -> None:
        self.model = model
        self.catalog = catalog

    @cached_property
    def world(self) -> World:
        """Every element placed in world space."""
        return build_world(self.model, self.catalog)

    @cached_property
    def cells(self) -> dict[CellKey, Cell]:
        """Which element fills each stud x stud x plate cell."""
        return world_cells(self.world)

    @cached_property
    def solid_index(self) -> SpatialHash[int]:
        """Spatial index of every solid, keyed by element index."""
        index: SpatialHash[int] = SpatialHash()
        for i, placed in enumerate(self.world.placed):
            for solid in placed.solids:
                index.insert(i, solid.bounds)
        return index

    @cached_property
    def receptors(self) -> ReceptorIndex:
        """Receptors by world position and normal."""
        return receptor_index(self.world)

    @cached_property
    def links(self) -> tuple[Link, ...]:
        """Every stud connection between two elements."""
        return find_links(self.world, self.receptors)
