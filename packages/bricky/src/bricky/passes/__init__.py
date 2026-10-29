# Copyright 2026 Maxence Faldor
"""Passes, and the registry that discovers and runs them."""

from __future__ import annotations

from bricky.passes.registry import (
    BUILT_IN,
    ENTRY_POINT_GROUP,
    Pass,
    installed_passes,
    installed_rules,
    resolve_levels,
    run_passes,
)

__all__ = [
    "BUILT_IN",
    "ENTRY_POINT_GROUP",
    "Pass",
    "installed_passes",
    "installed_rules",
    "resolve_levels",
    "run_passes",
]
