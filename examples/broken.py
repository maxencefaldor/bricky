# Copyright 2026 Maxence Faldor
"""A deliberately broken model, to show what bricky reports.

Run: ``uv run bricky build examples/broken.py``
"""

from bricky import ModelBuilder


def build() -> ModelBuilder:
    """Make three mistakes: an overlap, a brick half a stud off and a floating plate."""
    builder = ModelBuilder("broken")
    builder.place("3001", at=(0, 0, 0), color="Red", id="base")  # Brick 2 x 4
    builder.place("3001", at=(1, 0, 0), color="Blue", id="overlap")  # shares space
    builder.place("3003", at=(0.5, 0, 3), color="White", id="offset")  # half a stud off
    builder.place("3022", at=(4, 2, 6), color="Tan", id="floating")  # touches nothing
    return builder
