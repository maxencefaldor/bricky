"""Errors that front-ends show to users as messages rather than tracebacks."""


class BrickyError(Exception):
    """A problem the caller can fix: a missing file, an invalid model, an unknown profile."""
