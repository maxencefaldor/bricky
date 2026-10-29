# Copyright 2026 Maxence Faldor
"""Analyses derived from a model: world geometry, spatial index, connections, voxels.

Diffs compare the worlds of two builds.
"""

from __future__ import annotations

from bricky.analysis.connections import AntiStudIndex, Connection
from bricky.analysis.context import Context
from bricky.analysis.diff import WorldDiff, diff_worlds
from bricky.analysis.spatial import SpatialHash
from bricky.analysis.voxels import Voxel, VoxelKey, model_voxels, world_voxels
from bricky.analysis.world import PlacedElement, UnknownElement, World, build_world

__all__ = [
    "AntiStudIndex",
    "Connection",
    "Context",
    "PlacedElement",
    "SpatialHash",
    "UnknownElement",
    "Voxel",
    "VoxelKey",
    "World",
    "WorldDiff",
    "build_world",
    "diff_worlds",
    "model_voxels",
    "world_voxels",
]
