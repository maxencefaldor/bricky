# Copyright 2026 Maxence Faldor
"""The error that front-ends show to users as a message instead of a traceback."""


class BrickyError(Exception):
    """A problem the caller can fix: a missing file, an invalid model, an unknown profile."""
