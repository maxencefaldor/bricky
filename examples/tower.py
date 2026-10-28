"""A 4 x 4 tower of interlocking 2 x 4 bricks, capped with tiles.

Each level turns the bricks a quarter turn, so every brick bridges the two below it.

Run: ``uv run bricky build examples/tower.py``
"""

from bricky import ModelBuilder

LEVELS = 8


def build() -> ModelBuilder:
    """Stack crossed pairs of 2 x 4 bricks, then tile the top."""
    builder = ModelBuilder("tower")
    for level in range(LEVELS):
        z = 3 * level  # a brick is three plates tall
        if level % 2 == 0:
            builder.place("3001", at=(0, 0, z), color="Red")
            builder.place("3001", at=(2, 0, z), color="Red")
        else:
            builder.place("3001", at=(0, 0, z), rotation="R90", color="White")
            builder.place("3001", at=(0, 2, z), rotation="R90", color="White")
    for x in (0, 2):
        for y in (0, 2):
            builder.place("3068b", at=(x, y, 3 * LEVELS), color="Dark Bluish Gray")
    return builder
