"""bricky: a compiler-style toolkit that lets AI agents design buildable LEGO® models.

Write a model with :class:`ModelBuilder`, then check it with :func:`check_model` or the
``bricky`` command line. :func:`cells` gives the cells a model fills, to compare with a target.

LEGO® is a trademark of the LEGO Group, which does not sponsor, authorize or endorse this project.
"""

from bricky.analysis.cells import Cell
from bricky.analysis.cells import model_cells as cells
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
    "Cell",
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
    "cells",
    "check_model",
    "default_catalog",
    "load_model",
    "render_report",
    "save_model",
]
