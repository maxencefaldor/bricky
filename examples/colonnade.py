"""A colonnade: one column component, placed four times, under a two-layer beam.

The model stores the column once and places four instances of it, so a change to the column
changes every copy.

Run: ``uv run bricky build examples/colonnade.py``
"""

from bricky import ModelBuilder

HEIGHT = 5  # bricks per column
SPACING = 4  # studs between column origins


def build() -> ModelBuilder:
    """Build the colonnade."""
    builder = ModelBuilder("colonnade")

    column = builder.component("column")
    for level in range(HEIGHT):
        column.place("3003", at=(0, 0, 3 * level), color="Tan")

    for index in range(4):
        builder.instance("column", at=(index * SPACING, 0, 0))

    top = 3 * HEIGHT
    builder.place("3034", at=(0, 0, top), rotation="R90", color="Dark Tan")
    builder.place("3034", at=(8, 0, top), rotation="R90", color="Dark Tan")
    builder.place("3034", at=(4, 0, top + 1), rotation="R90", color="Dark Tan")
    return builder
