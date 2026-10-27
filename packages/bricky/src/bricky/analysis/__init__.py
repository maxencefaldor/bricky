"""Analyses derived from a model: world geometry, spatial indices and connections."""

from bricky.analysis.cells import Cell, CellKey, model_cells, world_cells
from bricky.analysis.context import Context
from bricky.analysis.diff import WorldDiff, diff_worlds
from bricky.analysis.links import Link, ReceptorIndex
from bricky.analysis.spatial import SpatialHash
from bricky.analysis.world import Placed, Unresolved, World, build_world

__all__ = [
    "Cell",
    "CellKey",
    "Context",
    "Link",
    "Placed",
    "ReceptorIndex",
    "SpatialHash",
    "Unresolved",
    "World",
    "WorldDiff",
    "build_world",
    "diff_worlds",
    "model_cells",
    "world_cells",
]
