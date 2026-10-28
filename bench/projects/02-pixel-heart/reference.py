"""Reference for project 02: a 12 x 12 pixel heart, as tiles on a Black base."""

from bricky import ModelBuilder

# Rows from north (top) to south; '.' White, 'R' Red, 'D' Dark Red.
PICTURE = """
............
..RR....RR..
.R.RR..RRRR.
R.RRRRRRRRRD
RRRRRRRRRRRD
RRRRRRRRRRRD
.RRRRRRRRRD.
..RRRRRRRD..
...RRRRRD...
....RRRD....
.....RD.....
............
"""

COLORS = {".": "White", "R": "Red", "D": "Dark Red"}


def build() -> ModelBuilder:
    builder = ModelBuilder("pixel-heart")
    rows = PICTURE.split()
    size = len(rows)
    # The base: Black 2 x 8 and 2 x 4 plates, two studs deep, 12 studs long.
    for y in range(0, size, 2):
        builder.place("3034", at=(0, y, 0), rotation="R90", color="Black")  # Plate 2 x 8
        builder.place("3020", at=(8, y, 0), rotation="R90", color="Black")  # Plate 2 x 4
    # The picture: one 1 x 1 tile per pixel.
    for row, line in enumerate(rows):
        y = size - 1 - row
        for x, pixel in enumerate(line):
            builder.place("3070", at=(x, y, 1), color=COLORS[pixel])  # Tile 1 x 1
    return builder
