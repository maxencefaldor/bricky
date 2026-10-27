"""Reference for project 03: the footbridge that inputs/bridge.py means to build."""

from bricky import ModelBuilder


def pier(builder: ModelBuilder, x: int) -> None:
    """Three courses of Dark Bluish Gray 2 x 4 bricks, x to x + 2, y 0 to 4."""
    for course in range(3):
        builder.place("3001", at=(x, 0, 3 * course), color="Dark Bluish Gray")


def railing(builder: ModelBuilder, y: int) -> None:
    """White 1 x 1 posts on the deck, capped by two White 1 x 6 plates."""
    for x in (0, 2, 4, 6, 8, 10, 11):
        builder.place("3005", at=(x, y, 10), color="White")
    for x in (0, 6):
        builder.place("3666", at=(x, y, 13), rot="R90", color="White")


def build() -> ModelBuilder:
    builder = ModelBuilder("footbridge")
    pier(builder, 0)
    pier(builder, 10)
    # Deck: Reddish Brown plates on the piers, each row a 2 x 8 and a 2 x 4 end to end.
    builder.place("3034", at=(0, 0, 9), rot="R90", color="Reddish Brown")
    builder.place("3020", at=(8, 0, 9), rot="R90", color="Reddish Brown")
    builder.place("3020", at=(0, 2, 9), rot="R90", color="Reddish Brown")
    builder.place("3034", at=(4, 2, 9), rot="R90", color="Reddish Brown")
    railing(builder, 0)
    railing(builder, 3)
    return builder
