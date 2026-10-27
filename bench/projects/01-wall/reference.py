"""Reference for project 01: a running-bond wall, 8 studs long and 6 bricks tall."""

from bricky import ModelBuilder

LENGTH = 8
COURSES = 6


def build() -> ModelBuilder:
    builder = ModelBuilder("wall")
    for course in range(COURSES):
        z = 3 * course
        color = "White" if course == COURSES - 1 else "Red"
        if course % 2 == 0:
            for x in range(0, LENGTH, 2):
                builder.place("3004", at=(x, 0, z), rot="R90", color=color)  # Brick 1 x 2
        else:
            builder.place("3005", at=(0, 0, z), color=color)  # Brick 1 x 1
            for x in range(1, LENGTH - 1, 2):
                builder.place("3004", at=(x, 0, z), rot="R90", color=color)
            builder.place("3005", at=(LENGTH - 1, 0, z), color=color)
    return builder
