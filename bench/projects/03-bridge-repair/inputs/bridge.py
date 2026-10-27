"""A footbridge over a stream: two stone piers, a wooden deck and white railings.

The bridge runs 12 studs along x and is 4 studs wide (y 0 to 4).
"""

from bricky import ModelBuilder


def pier(builder: ModelBuilder, x: int, courses: tuple[int, ...]) -> None:
    """A pier: Dark Bluish Gray 2 x 4 bricks stacked three high, x to x + 2, y 0 to 4."""
    for z in courses:
        builder.place("3001", at=(x, 0, z), color="Dark Grey")


def railing(builder: ModelBuilder, y: int, post_heights: dict[int, int]) -> None:
    """A railing: White 1 x 1 posts standing on the deck, capped by two White 1 x 6 plates."""
    for x, z in post_heights.items():
        builder.place("3005", at=(x, y, z), color="White")
    for x in (0, 6):
        builder.place("3666", at=(x, y, 13), rot="R90", color="White")


def build() -> ModelBuilder:
    builder = ModelBuilder("footbridge")
    # Piers: three courses each, at z = 0, 3 and 6, so their tops are at z = 9.
    pier(builder, 0, (0, 3, 6))
    pier(builder, 10, (0, 4, 6))
    # Deck: Reddish Brown plates on the piers at z = 9. Each row is a 2 x 8 and a 2 x 4 plate end
    # to end from x = 0 to 12; the south row starts with the 2 x 8, the north row with the 2 x 4.
    builder.place("3034", at=(0, 0, 9), rot="R90", color="Reddish Brown")
    builder.place("3020", at=(8, 0, 9), rot="R90", color="Reddish Brown")
    builder.place("3020", at=(0, 2, 9), rot="R90", color="Reddish Brown")
    builder.place("3034", at=(5, 2, 9), rot="R90", color="Reddish Brown")
    # Railings along both edges: posts on the deck (z = 10) at x = 0, 2, 4, 6, 8, 10 and 11.
    posts = {0: 10, 2: 10, 4: 10, 6: 10, 8: 10, 10: 10, 11: 10}
    railing(builder, 0, posts)
    railing(builder, 3, {**posts, 6: 9})
    return builder
