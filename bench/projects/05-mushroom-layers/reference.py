# Copyright 2026 Maxence Faldor
"""Reference for project 05: a toadstool on a lawn, from plate-by-plate layers.

The stem is four courses of interlocking White 2 x 4 bricks. The cap is seven layers of plates whose
rows rotate by 90 degrees from one layer to the next, so every row crosses the rows above and below
it and the overhang holds together.
"""

from bricky import ModelBuilder

SIZE = 10
STEM = (3, 7)  # x and y range of the stem, in studs
CAP = (
    (2, 8),
    (1, 9),
    (0, 10),
    (0, 10),
    (1, 9),
    (2, 8),
    (3, 7),
)  # square extent of each layer
CAP_Z = 13
# White spots on the cap, by layer index: cells (x, y), each over a cell of the layer below.
SPOTS = {
    3: {(0, 4), (0, 5), (9, 2), (9, 3), (4, 0), (5, 0), (2, 9), (7, 9)},
    4: {(1, 7), (8, 1), (8, 7), (2, 2), (6, 3), (3, 6)},
    5: {(4, 4), (5, 5), (3, 6), (6, 3)},
}
PLATES = {
    8: "3460",
    6: "3666",
    4: "3710",
    3: "3623",
    2: "3023",
    1: "3024",
}  # Plates 1 x N


def row(
    builder: ModelBuilder,
    cells: list[tuple[int, int]],
    colors: list[str],
    z: int,
    along_x: bool,
) -> None:
    """Fill a straight row of cells with 1 x N plates, one color at a time, longest first."""
    i = 0
    while i < len(cells):
        j = i
        while j < len(cells) and colors[j] == colors[i]:
            j += 1
        start = i
        while start < j:
            length = next(size for size in PLATES if size <= j - start)
            x, y = cells[start]
            builder.place(
                PLATES[length],
                at=(x, y, z),
                rotation="R90" if along_x else "R0",
                color=colors[i],
            )
            start += length
        i = j


def build() -> ModelBuilder:
    """Build the toadstool on its lawn."""
    builder = ModelBuilder("toadstool")
    # Lawn: Green 2 x 8 and 2 x 2 plates, 10 x 10 studs.
    for y in range(0, SIZE, 2):
        builder.place("3034", at=(0, y, 0), rotation="R90", color="Green")
        builder.place("3022", at=(8, y, 0), color="Green")
    # Stem: crossed pairs of White 2 x 4 bricks.
    for course in range(4):
        z = 1 + 3 * course
        for offset in (0, 2):
            if course % 2 == 0:
                builder.place("3001", at=(STEM[0] + offset, STEM[0], z), color="White")
            else:
                builder.place(
                    "3001",
                    at=(STEM[0], STEM[0] + offset, z),
                    rotation="R90",
                    color="White",
                )
    # Cap: Red plate layers, rows alternating between x and y.
    for layer, (start, stop) in enumerate(CAP):
        z = CAP_Z + layer
        spots = SPOTS.get(layer, set())
        along_x = layer % 2 == 0
        for across in range(start, stop):
            cells = [
                (along, across) if along_x else (across, along)
                for along in range(start, stop)
            ]
            colors = ["White" if cell in spots else "Red" for cell in cells]
            row(builder, cells, colors, z, along_x)
    return builder
