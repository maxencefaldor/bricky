# Copyright 2026 Maxence Faldor
"""Passes, and the registry that discovers and runs them."""

from bricky.passes.registry import (
    ENTRY_POINT_GROUP,
    Pass,
    installed_codes,
    installed_passes,
    run_passes,
)

__all__ = [
    "ENTRY_POINT_GROUP",
    "Pass",
    "installed_codes",
    "installed_passes",
    "run_passes",
]
