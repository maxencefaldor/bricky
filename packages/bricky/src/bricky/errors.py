# Copyright 2026 Maxence Faldor
"""The error that front ends show to users as a message instead of a traceback."""

from __future__ import annotations


class BrickyError(Exception):
    """A problem the caller can fix: a missing file, invalid model, unknown profile."""
