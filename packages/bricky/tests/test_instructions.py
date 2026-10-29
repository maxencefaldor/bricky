# Copyright 2026 Maxence Faldor

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from bricky import Model, ModelBuilder, default_catalog
from bricky.analysis import build_world
from bricky.analysis.connections import anti_stud_index, find_connections
from bricky.cli import main
from bricky.files import save_model
from bricky.geometry import AXES, DOWN, UP, Box, Vector
from bricky.instructions import (
    Instructions,
    Reason,
    _Leg,
    _Solids,
    _Sweep,
    build_instructions,
)


def order(instructions: Instructions) -> list[int]:
    return [i for step in instructions.steps for i in step.elements]


def floating_after(model: Model, instructions: Instructions) -> list[int]:
    """The steps, from 1, after which some placed element has no path to the ground."""
    world = build_world(model, default_catalog())
    links: dict[int, set[int]] = {i: set() for i in range(len(world.elements))}
    for connection in find_connections(world, anti_stud_index(world)):
        links[connection.a].add(connection.b)
        links[connection.b].add(connection.a)
    placed: set[int] = set()
    floating: list[int] = []
    for k, step in enumerate(instructions.steps, start=1):
        placed.update(step.elements)
        reached = {i for i in placed if world.elements[i].bounds.min.z == 0}
        stack = list(reached)
        while stack:
            for j in links[stack.pop()] & placed - reached:
                reached.add(j)
                stack.append(j)
        if placed - reached:
            floating.append(k)
    return floating


def test_steps_place_every_element_once_after_the_bricks_below_it() -> None:
    builder = ModelBuilder("wall")
    for course in range(3):
        for k in range(3):
            at = (4 * k + 2 * (course % 2), 0, 3 * course)
            builder.place("3001", at=at, color="Red")
    model = builder.build()
    world = build_world(model, default_catalog())
    instructions = build_instructions(model, default_catalog())
    placed = order(instructions)
    assert sorted(placed) == list(range(9))
    assert not instructions.forced
    position = {i: k for k, i in enumerate(placed)}
    for i, upper in enumerate(world.elements):
        for j, lower in enumerate(world.elements):
            below = lower.bounds.max.z == upper.bounds.min.z
            across = lower.bounds.min.x < upper.bounds.max.x
            if below and across and upper.bounds.min.x < lower.bounds.max.x:
                assert position[j] < position[i]


def overhang(*, below: bool) -> ModelBuilder:
    """A beam on a post, a plate hanging under its free end, and maybe a plate below."""
    builder = ModelBuilder("overhang")
    builder.place("3003", at=(0, 0, 0), color="Red", id="post")
    builder.place("3020", at=(0, 0, 3), color="Blue", rotation="R90", id="beam")
    builder.place("3022", at=(2, 0, 2), color="Yellow", id="hanging")
    if below:
        builder.place("3022", at=(2, 0, 0), color="Green", id="below")
    return builder


def approaches_of(model: Model, instructions: Instructions) -> dict[str, Vector]:
    world = build_world(model, default_catalog())
    return {
        world.elements[i].uid: approach
        for step in instructions.steps
        for i, approach in zip(step.elements, step.approaches, strict=True)
    }


def test_an_element_held_from_above_goes_on_after_it_pushed_up() -> None:
    model = overhang(below=False).build()
    instructions = build_instructions(model, default_catalog())
    world = build_world(model, default_catalog())
    uids = [world.elements[i].uid for i in order(instructions)]
    assert uids == ["post", "beam", "hanging"]
    assert approaches_of(model, instructions)["hanging"] == UP
    assert floating_after(model, instructions) == []


def test_an_element_held_from_above_with_no_room_below_goes_on_under_its_holder() -> (
    None
):
    model = overhang(below=True).build()
    instructions = build_instructions(model, default_catalog())
    world = build_world(model, default_catalog())
    index = {element.uid: i for i, element in enumerate(world.elements)}
    (step,) = [s for s in instructions.steps if index["hanging"] in s.elements]
    assert index["beam"] in step.elements
    assert approaches_of(model, instructions)["hanging"] == DOWN
    assert not instructions.forced
    assert floating_after(model, instructions) == []


def test_a_column_that_hangs_from_a_beam_never_floats() -> None:
    # A sail: plates hanging one under another from a beam, as on the pirate ship.
    builder = ModelBuilder("sail")
    builder.place("3003", at=(0, 0, 0), color="Dark Brown")
    for level in range(1, 7):
        builder.place("3003", at=(0, 0, 3 * level), color="Dark Brown")
    builder.place("3020", at=(0, 0, 21), color="Dark Brown", rotation="R90")
    for level in range(6):
        builder.place("3023", at=(2, 0, 20 - level), color="White", rotation="R90")
    model = builder.build()
    instructions = build_instructions(model, default_catalog())
    assert not instructions.forced
    assert floating_after(model, instructions) == []


def test_an_element_on_side_studs_goes_on_sideways_after_its_brick() -> None:
    builder = ModelBuilder("side")
    builder.place("87087", at=(0, 1, 0), color="Red", id="brick")
    builder.place("3024", at=(0, 0.6, 0.5), color="Blue", rotation="+x+z", id="plate")
    instructions = build_instructions(builder.build(), default_catalog())
    (step,) = instructions.steps
    assert step.elements == (0, 1)
    assert step.approaches == (DOWN, Vector(0, 1, 0))


def test_elements_that_lock_each_other_in_are_placed_and_noted() -> None:
    builder = ModelBuilder("locked")
    builder.place("3001", at=(0, 0, 0), color="Red", id="first")
    builder.place("3001", at=(1, 0, 0), color="Blue", id="second")
    instructions = build_instructions(builder.build(), default_catalog())
    assert order(instructions) == [0, 1]
    first, second = instructions.forced
    assert first.pending == ((1, Reason.WAY),)
    assert second.pending == ((0, Reason.BLOCKED),)
    uids = ["first", "second"]
    assert first.describe(uids) == "first goes on into the way of second"
    assert second.describe(uids) == "second goes on though first stands in its way"


def test_steps_keep_to_one_section_of_the_build_script() -> None:
    def walls(builder: ModelBuilder) -> None:
        for x in range(0, 8, 2):
            builder.place("3003", at=(x, 0, 0), color="Red")

    def garden(builder: ModelBuilder) -> None:
        for x in range(0, 8, 2):
            builder.place("3003", at=(x, 2, 0), color="Green")

    def build() -> ModelBuilder:
        builder = ModelBuilder("sections")
        walls(builder)
        garden(builder)
        return builder

    builder = build()
    instructions = build_instructions(
        builder.build(), default_catalog(), provenance=builder.provenance()
    )
    assert [step.section for step in instructions.steps] == ["walls", "garden"]
    assert [len(step.elements) for step in instructions.steps] == [4, 4]


def test_steps_add_at_most_the_elements_asked() -> None:
    builder = ModelBuilder("row")
    for x in range(0, 20, 2):
        builder.place("3003", at=(x, 0, 0), color="Red")
    instructions = build_instructions(
        builder.build(), default_catalog(), elements_per_step=3
    )
    assert [len(step.elements) for step in instructions.steps] == [3, 3, 3, 1]


def test_a_model_without_elements_has_no_steps() -> None:
    instructions = build_instructions(ModelBuilder("empty").build(), default_catalog())
    assert instructions == Instructions(steps=(), forced=())


@settings(max_examples=40, deadline=None)
@given(
    st.lists(
        st.tuples(st.integers(0, 3), st.integers(0, 3), st.integers(1, 4)),
        min_size=1,
        max_size=8,
    )
)
def test_every_element_goes_on_after_what_holds_it(
    columns: list[tuple[int, int, int]],
) -> None:
    # Columns of 2 x 2 bricks, each standing on the ground or on the brick below it.
    builder = ModelBuilder("columns")
    seen: set[tuple[int, int]] = set()
    for x, y, height in columns:
        if (x, y) in seen:
            continue
        seen.add((x, y))
        for level in range(height):
            builder.place("3003", at=(2 * x, 2 * y, 3 * level), color="Red")
    model = builder.build()
    world = build_world(model, default_catalog())
    instructions = build_instructions(model, default_catalog())
    placed = order(instructions)
    position = {i: k for k, i in enumerate(placed)}
    assert sorted(placed) == list(range(len(world.elements)))
    assert not instructions.forced
    assert floating_after(model, instructions) == []
    for i, element in enumerate(world.elements):
        for j, other in enumerate(world.elements):
            same_column = element.bounds.min.x == other.bounds.min.x and (
                element.bounds.min.y == other.bounds.min.y
            )
            if same_column and other.bounds.min.z < element.bounds.min.z:
                assert position[j] < position[i]


corners = st.tuples(st.integers(-6, 6), st.integers(-6, 6), st.integers(-6, 6))


@st.composite
def boxes(draw: st.DrawFn) -> Box:
    low = Vector(*draw(corners))
    size = Vector(*draw(st.tuples(*[st.integers(1, 5)] * 3)))
    return Box(low, low + size)


@settings(max_examples=300, deadline=None)
@given(
    boxes(),
    boxes(),
    st.sampled_from(list(AXES.values())),
    st.one_of(st.none(), st.integers(1, 8)),
    st.tuples(st.integers(-3, 3), st.integers(-3, 3), st.integers(-3, 3)),
)
def test_convex_sweeps_agree_with_box_sweeps(
    moving: Box,
    fixed: Box,
    direction: Vector,
    length: int | None,
    offset: tuple[int, int, int],
) -> None:
    # A box sweeps a box, so the separating axes of convex solids must find the same.
    leg = _Leg(Vector(*offset), direction, length)
    reach = Box(Vector(-20, -20, -20), Vector(20, 20, 20))
    exact = _Sweep(moving, leg, reach, _Solids()).crosses(fixed)
    convex = _Sweep(moving.as_convex(), leg, reach, _Solids())
    assert convex.crosses(fixed) == exact
    assert convex.crosses(fixed.as_convex()) == exact


def test_the_instructions_command_writes_a_page_and_states_what_breaks_the_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    builder = ModelBuilder("locked")
    builder.place("3001", at=(0, 0, 0), color="Red", id="first")
    builder.place("3001", at=(1, 0, 0), color="Blue", id="second")
    model = tmp_path / "locked.bricky.json"
    save_model(builder.build(), model)
    main(["instructions", str(model)])
    page = tmp_path / "locked.instructions.html"
    assert capsys.readouterr().out == (
        f"wrote {page}: 2 steps for 2 elements, 1.0 a step on average\n"
        "2 steps break the build order, where elements lock one another in:\n"
        "  step 1: first goes on into the way of second\n"
        "  step 2: second goes on though first stands in its way\n"
    )
    assert '"mode": "instructions"' in page.read_text()
    output = tmp_path / "pages" / "locked.html"
    main(
        ["instructions", str(model), "--output", str(output), "--output-format", "json"]
    )
    result = json.loads(capsys.readouterr().out)
    assert result["steps"] == 2
    assert result["notes"] == [
        {"step": 1, "message": "first goes on into the way of second"},
        {"step": 2, "message": "second goes on though first stands in its way"},
    ]
    assert output.is_file()
