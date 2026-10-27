from hypothesis import given
from hypothesis import strategies as st

from bricky import ModelBuilder, default_catalog
from bricky.analysis import WorldDiff, build_world, diff_worlds

PARTS = ["3001", "3004", "3024", "3022", "3020", "3070b", "3040", "3062b"]


def diff(before: ModelBuilder, after: ModelBuilder) -> WorldDiff:
    catalog = default_catalog()
    return diff_worlds(build_world(before.build(), catalog), build_world(after.build(), catalog))


def row(*, first: str | None = None) -> ModelBuilder:
    builder = ModelBuilder("row")
    if first is not None:
        builder.place(first, at=(0, 0, 0), color="Blue")
    for x in range(2, 10, 2):
        builder.place("3003", at=(x, 0, 0), color="Red")  # Brick 2 x 2
    return builder


def test_renumbered_elements_are_unchanged():
    result = diff(row(), row(first="3005"))  # one brick placed first renumbers the rest
    assert result.added == ("e1",)
    assert result.removed == ()
    assert result.changed == ()
    assert result.unchanged == 4
    assert (result.filled, result.emptied, result.recoloured) == (3, 0, 0)


def test_an_element_moved_or_recoloured_under_its_id_has_changed():
    before, after = ModelBuilder("m"), ModelBuilder("m")
    before.place("3001", at=(0, 0, 0), color="Red", name="base")
    before.place("3022", at=(0, 0, 3), color="Tan", name="cap")
    after.place("3001", at=(0, 0, 0), color="Blue", name="base")  # recoloured
    after.place("3022", at=(0, 2, 3), color="Tan", name="cap")  # moved two studs north
    result = diff(before, after)
    assert result.changed == ("base", "cap")
    assert (result.added, result.removed, result.unchanged) == ((), (), 0)
    assert result.recoloured == 2 * 4 * 3
    assert (result.filled, result.emptied) == (4, 4)


def test_another_part_under_the_same_id_is_added_and_removed():
    before, after = ModelBuilder("m"), ModelBuilder("m")
    before.place("3001", at=(0, 0, 0), color="Red", name="base")
    after.place("3020", at=(0, 0, 0), color="Red", name="base")  # a plate instead of a brick
    result = diff(before, after)
    assert (result.added, result.removed, result.changed) == (("base",), ("base",), ())
    assert (result.filled, result.emptied, result.recoloured) == (0, 2 * 4 * 2, 0)


def test_a_part_turned_onto_itself_is_unchanged_and_one_turned_round_is_not():
    before, after = ModelBuilder("m"), ModelBuilder("m")
    before.place("3003", at=(0, 0, 0), color="Red", name="square")  # Brick 2 x 2
    before.place("3040", at=(4, 0, 0), color="Red", name="slope")  # Slope 45 2 x 1
    after.place("3003", at=(0, 0, 0), rot="R180", color="Red", name="square")
    after.place("3040", at=(4, 0, 0), rot="R180", color="Red", name="slope")
    result = diff(before, after)
    assert result.unchanged == 1
    assert result.changed == ("slope",)


placements = st.tuples(
    st.sampled_from(PARTS),
    st.integers(0, 6),
    st.integers(0, 6),
    st.integers(0, 9),
    st.sampled_from(["R0", "R90", "R180", "R270"]),
    st.sampled_from(["Red", "Blue"]),
)


def build(name: str, parts: list[tuple[str, int, int, int, str, str]]) -> ModelBuilder:
    builder = ModelBuilder(name)
    for part, x, y, z, rot, color in parts:
        builder.place(part, at=(x, y, z), rot=rot, color=color)
    return builder


@given(st.lists(placements, max_size=8))
def test_a_model_has_not_changed_since_itself(parts):
    result = diff(build("a", parts), build("b", parts))
    assert result.unchanged == len(parts)
    assert result == WorldDiff((), (), (), len(parts), 0, 0, 0)


@given(st.lists(placements, max_size=8), st.lists(placements, max_size=8))
def test_comparing_the_other_way_swaps_what_came_and_went(first, second):
    forward = diff(build("a", first), build("b", second))
    backward = diff(build("b", second), build("a", first))
    assert forward.unchanged == backward.unchanged
    assert len(forward.added) + len(forward.changed) == len(second) - forward.unchanged
    assert len(forward.removed) + len(forward.changed) == len(first) - forward.unchanged
    assert len(forward.added) + len(forward.changed) == len(backward.removed) + len(
        backward.changed
    )
    assert (forward.filled, forward.emptied) == (backward.emptied, backward.filled)
    assert forward.recoloured == backward.recoloured
