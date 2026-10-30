# Copyright 2026 Maxence Faldor
"""The service layer: every command, defined once.

Each command is a request model plus an async function. The command line runs them,
the MCP server awaits them, and Python callers can do either, so every front end shares
one set of argument names, defaults and descriptions. A :class:`Session` carries the
settings and a warm renderer between commands.

Each module holds one group of commands: :mod:`~bricky.service.builds` runs build
scripts, :mod:`~bricky.service.checks` checks models and explains rules,
:mod:`~bricky.service.outputs` writes what a saved model makes, and
:mod:`~bricky.service.catalog` searches and imports the catalog. The module
:mod:`~bricky.service.session` holds what they share.
"""

from __future__ import annotations

from bricky.service.builds import (
    BuildRequest,
    BuildResult,
    Changes,
    LineCount,
    ScriptOutput,
    ScriptRun,
    build,
    run_script,
)
from bricky.service.catalog import (
    CatalogImportRequest,
    CatalogImportResult,
    CatalogShowRequest,
    CatalogShowResult,
    CatalogStatusRequest,
    CatalogStatusResult,
    CatalogVerifyRequest,
    CatalogVerifyResult,
    ColorInfo,
    ColorsRequest,
    ColorsResult,
    PartInfo,
    PartsRequest,
    PartsResult,
    catalog_import,
    catalog_show,
    catalog_status,
    catalog_verify,
    colors,
    parts,
)
from bricky.service.checks import (
    CheckRequest,
    ExplainRequest,
    ExplainResult,
    RuleInfo,
    check,
    explain,
)
from bricky.service.outputs import (
    ExportRequest,
    ExportResult,
    InstructionsRequest,
    InstructionsResult,
    RenderRequest,
    RenderResult,
    StepNote,
    export,
    instructions,
    render,
)
from bricky.service.session import Image, Session, Timings

__all__ = [
    "BuildRequest",
    "BuildResult",
    "CatalogImportRequest",
    "CatalogImportResult",
    "CatalogShowRequest",
    "CatalogShowResult",
    "CatalogStatusRequest",
    "CatalogStatusResult",
    "CatalogVerifyRequest",
    "CatalogVerifyResult",
    "Changes",
    "CheckRequest",
    "ColorInfo",
    "ColorsRequest",
    "ColorsResult",
    "ExplainRequest",
    "ExplainResult",
    "ExportRequest",
    "ExportResult",
    "Image",
    "InstructionsRequest",
    "InstructionsResult",
    "LineCount",
    "PartInfo",
    "PartsRequest",
    "PartsResult",
    "RenderRequest",
    "RenderResult",
    "RuleInfo",
    "ScriptOutput",
    "ScriptRun",
    "Session",
    "StepNote",
    "Timings",
    "build",
    "catalog_import",
    "catalog_show",
    "catalog_status",
    "catalog_verify",
    "check",
    "colors",
    "explain",
    "export",
    "instructions",
    "parts",
    "render",
    "run_script",
]
