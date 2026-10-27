"""Check passes and the machinery that discovers and runs them."""

from bricky.passes.registry import ENTRY_POINT_GROUP, Pass, installed_passes, run_passes

__all__ = ["ENTRY_POINT_GROUP", "Pass", "installed_passes", "run_passes"]
