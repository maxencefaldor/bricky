# Copyright 2026 Maxence Faldor
"""bricky: a compiler-style toolkit that lets AI agents design buildable LEGO® models.

Write a model with :class:`ModelBuilder`, then check it with :func:`check_model` or the
``bricky`` command line. :func:`voxels` returns the voxels a model fills, for comparison
with a plan.

LEGO® is a trademark of the LEGO Group, which does not sponsor, authorize or endorse
this project.
"""

from bricky.analysis.voxels import Voxel
from bricky.analysis.voxels import model_voxels as voxels
from bricky.builder import ComponentBuilder, ModelBuilder
from bricky.catalog import Catalog, default_catalog
from bricky.check import check_model
from bricky.diagnostics import Diagnostic, Region, Report, Severity, render_report
from bricky.errors import BrickyError
from bricky.files import load_model, save_model
from bricky.model import Component, Element, Instance, Model
from bricky.settings import Settings

__all__ = [
    "BrickyError",
    "Catalog",
    "Component",
    "ComponentBuilder",
    "Diagnostic",
    "Element",
    "Instance",
    "Model",
    "ModelBuilder",
    "Region",
    "Report",
    "Settings",
    "Severity",
    "Voxel",
    "check_model",
    "default_catalog",
    "load_model",
    "render_report",
    "save_model",
    "voxels",
]
