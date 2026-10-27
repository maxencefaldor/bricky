import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from bricky import Component, Element, Instance, Model, ModelBuilder, load_model, save_model
from bricky.analysis import build_world
from bricky.catalog import default_catalog
from bricky.geometry import ROTATIONS, Box, Vec3
from bricky.units import PLATE, STUD


def world_bounds(model: Model) -> list[Box]:
    return [p.bounds for p in build_world(model, default_catalog()).placed]


def test_place_puts_the_rotated_corner_at_the_given_point():
    builder = ModelBuilder()
    builder.place("3001", at=(0, 0, 0), color="Red")
    builder.place("3001", at=(5, 1, 3), rot="R90", color="Red")
    builder.place("3001", at=(0, 6, 0), rot="R180", color="Red")
    upright, turned, reversed_ = world_bounds(builder.build())
    assert upright == Box(Vec3(0, 0, 0), Vec3(40, 80, 24))
    assert turned == Box(Vec3(100, 20, 24), Vec3(180, 60, 48))  # 4 studs east, 2 north
    assert reversed_ == Box(Vec3(0, 120, 0), Vec3(40, 200, 24))


def test_builder_rejects_unknown_parts_and_colours():
    builder = ModelBuilder()
    with pytest.raises(ValueError, match="unknown part"):
        builder.place("99999", at=(0, 0, 0), color="Red")
    with pytest.raises(ValueError, match="unknown colour"):
        builder.place("3001", at=(0, 0, 0), color="Mauve")
    with pytest.raises(ValueError, match="not a whole number"):
        builder.place("3001", at=(0.01, 0, 0), color="Red")


def test_builder_generates_and_checks_ids():
    builder = ModelBuilder()
    assert builder.place("3001", at=(0, 0, 0), color="Red") == "e1"
    assert builder.place("3001", at=(0, 0, 3), color="Red", name="top") == "top"
    assert builder.place("3001", at=(0, 0, 6), color="Red") == "e3"
    with pytest.raises(ValueError, match="already used"):
        builder.place("3001", at=(0, 0, 9), color="Red", name="top")


def test_instances_unfold_with_hierarchical_ids():
    builder = ModelBuilder()
    column = builder.component("column")
    column.place("3003", at=(0, 0, 0), color="Tan")
    column.place("3003", at=(0, 0, 3), color="Tan")
    builder.instance("column", at=(4, 0, 0), name="west")
    builder.instance("column", at=(10, 0, 0), rot="R90")
    model = builder.build()
    assert model.element_count() == 4
    world = build_world(model, default_catalog())
    assert [p.uid for p in world.placed] == ["west/e1", "west/e2", "i2/e1", "i2/e2"]
    assert world.placed[0].bounds.lo == Vec3(4 * STUD, 0, 0)


def test_rotation_names_are_canonicalised():
    element = Element(id="a", part="3001", color=5, rot="R90")
    assert element.rot == "+y-x"


def test_models_reject_duplicate_ids_and_unknown_components():
    with pytest.raises(ValidationError, match="duplicate id"):
        Model(
            elements=(Element(id="a", part="3001", color=5), Element(id="a", part="3001", color=5))
        )
    with pytest.raises(ValidationError, match="unknown component"):
        Model(instances=(Instance(id="i", component="nope"),))


def test_models_reject_component_cycles():
    loop = {
        "a": Component(instances=(Instance(id="x", component="b"),)),
        "b": Component(instances=(Instance(id="y", component="a"),)),
    }
    with pytest.raises(ValidationError, match="cycle"):
        Model(components=loop)


def test_files_round_trip(tmp_path):
    builder = ModelBuilder("roundtrip")
    builder.component("c").place("3001", at=(0, 0, 0), color="Red")
    builder.instance("c", at=(0, 0, 0))
    model = builder.build()
    path = tmp_path / "m.bricky.json"
    save_model(model, path)
    assert load_model(path) == model


@settings(max_examples=60)
@given(
    rot=st.sampled_from([rotation.name for rotation in ROTATIONS]),
    x=st.integers(-8, 30),
    y=st.integers(-8, 30),
    z=st.integers(0, 30),
)
def test_instances_put_the_rotated_corner_at_the_given_point(rot, x, y, z):
    builder = ModelBuilder()
    column = builder.component("column")
    column.place("3001", at=(0, 0, 0), color="Red")
    column.place("3003", at=(0, 4, 3), color="Red")
    builder.instance("column", at=(x, y, z), rot=rot)
    bounds = Box.bounding(world_bounds(builder.build()))
    assert bounds.lo == Vec3(x * STUD, y * STUD, z * PLATE)


def test_parts_and_components_turn_the_same_way():
    one = ModelBuilder()
    one.place("3001", at=(3, 5, 0), rot="R90", color="Red")
    two = ModelBuilder()
    two.component("brick").place("3001", at=(0, 0, 0), color="Red")
    two.instance("brick", at=(3, 5, 0), rot="R90")
    assert world_bounds(one.build()) == world_bounds(two.build())


def test_components_may_be_filled_after_their_instances_are_placed():
    builder = ModelBuilder()
    builder.instance("late", at=(2, 0, 0), rot="R180")
    builder.component("late").place("3010", at=(0, 0, 0), color="Tan")
    (bounds,) = world_bounds(builder.build())
    assert bounds.lo == Vec3(2 * STUD, 0, 0)


def test_nested_components_follow_the_same_corner_rule():
    builder = ModelBuilder()
    builder.component("brick").place("3001", at=(0, 0, 0), color="Red")
    pair = builder.component("pair")
    pair.instance("brick", at=(0, 0, 0))
    pair.instance("brick", at=(0, 4, 0))
    builder.instance("pair", at=(10, 10, 0), rot="R90")
    bounds = Box.bounding(world_bounds(builder.build()))
    assert bounds == Box(Vec3(10 * STUD, 10 * STUD, 0), Vec3(18 * STUD, 12 * STUD, 3 * PLATE))


def test_unknown_empty_and_cyclic_components_fail_when_built():
    unknown = ModelBuilder()
    unknown.instance("nope", at=(0, 0, 0))
    with pytest.raises(ValueError, match="unknown component 'nope'"):
        unknown.build()
    empty = ModelBuilder()
    empty.component("void")
    empty.instance("void", at=(0, 0, 0))
    with pytest.raises(ValueError, match="'void' is empty"):
        empty.build()
    cyclic = ModelBuilder()
    cyclic.component("a").instance("b", at=(0, 0, 0))
    cyclic.component("b").instance("a", at=(0, 0, 0))
    with pytest.raises(ValueError, match="cycle: a -> b -> a"):
        cyclic.build()


def test_invalid_names_are_rejected_without_using_up_the_id():
    builder = ModelBuilder()
    with pytest.raises(ValueError, match="pattern"):
        builder.place("3001", at=(0, 0, 0), color="Red", name="two words")
    with pytest.raises(ValueError, match="unknown colour"):
        builder.place("3001", at=(0, 0, 0), color="Mauve", name="first")
    assert builder.place("3001", at=(0, 0, 0), color="Red", name="first") == "first"
