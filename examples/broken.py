"""A deliberately broken model, to show what bricky reports.

Run: ``uv run bricky build examples/broken.py``
"""

from bricky import ModelBuilder


def build() -> ModelBuilder:
    """Make one mistake of each kind the digital profile catches."""
    builder = ModelBuilder("broken")
    builder.place("3001", at=(0, 0, 0), color="Red", name="base")
    builder.place("3001", at=(1, 0, 0), color="Blue", name="overlap")  # shares space with base
    builder.place("3003", at=(0.5, 0, 3), color="White", name="offset")  # half a stud off the grid
    builder.place("3022", at=(10, 10, 6), color="Tan", name="floating")  # touches nothing
    return builder
