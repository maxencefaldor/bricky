# Copyright 2026 Maxence Faldor

from __future__ import annotations

import sys
from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from bricky import BrickyError, ModelBuilder, Settings, check_model, default_catalog
from bricky.analysis import Context
from bricky.analysis.stability import (
    GRAVITY,
    Material,
    Stability,
    _mass,
    _overlap,
    analyze_stability,
)
from bricky.geometry import Box, Vector

MATERIAL = Material(clutch=2.94, friction=0.2, density=0.54)


def analyze(
    builder: ModelBuilder, material: Material = MATERIAL, threshold: float = 1e-6
) -> tuple[Stability, list[str]]:
    context = Context(builder.build(), default_catalog())
    uids = [element.uid for element in context.world.elements]
    return analyze_stability(context, material, threshold=threshold), uids


def falls(builder: ModelBuilder) -> list[list[str]]:
    stability, uids = analyze(builder)
    return [[uids[i] for i in group] for group in stability.falls]


def weight(volume: float, material: Material = MATERIAL) -> float:
    """Millinewtons that a body of ``volume`` cubic millimeters weighs."""
    return volume / 1000 * material.density * GRAVITY


def test_a_tower_of_bricks_stands_and_needs_no_clutch() -> None:
    builder = ModelBuilder("tower")
    for level in range(5):
        builder.place("3003", at=(0, 0, 3 * level), color="Red")
    assert analyze(builder)[0] == Stability(falls=(), sites=())


def test_an_arm_that_reaches_past_its_base_tips_over() -> None:
    builder = ModelBuilder("tipping")
    builder.place("3005", at=(0, 0, 0), color="Red", id="post")
    builder.place("3460", at=(0, 0, 3), color="Blue", rotation="R90", id="arm")
    builder.place("3005", at=(6, 6, 0), color="Red", id="apart")
    assert falls(builder) == [["post", "arm"]]


def test_an_arm_balanced_over_its_base_stands_and_needs_no_clutch() -> None:
    builder = ModelBuilder("balanced")
    builder.place("3003", at=(3, 0, 0), color="Red", id="post")
    builder.place("3460", at=(0, 0, 3), color="Blue", rotation="R90", id="arm")
    assert analyze(builder)[0] == Stability(falls=(), sites=())


def test_an_element_resting_without_studs_falls_off_what_it_overhangs() -> None:
    builder = ModelBuilder("resting")
    builder.place("3005", at=(0, 0, 0), color="Red", id="post")
    builder.place("3070", at=(0, 0, 3), color="White", id="tile")
    builder.place("3010", at=(0, 0, 4), color="Yellow", rotation="R90", id="beam")
    assert falls(builder) == [["beam"]]


def test_an_element_resting_without_studs_stands_over_its_support() -> None:
    builder = ModelBuilder("resting")
    builder.place("3003", at=(0, 0, 0), color="Red", id="post")
    builder.place("3068", at=(0, 0, 3), color="White", id="tile")
    builder.place("3010", at=(-1, 0, 4), color="Yellow", rotation="R90", id="beam")
    assert falls(builder) == []


def test_a_plate_on_a_side_stud_stands() -> None:
    builder = ModelBuilder("bracket")
    builder.place("87087", at=(0, 1, 0), color="Red", id="brick")
    builder.place("3024", at=(0, 0.6, 0.5), color="Blue", rotation="+x+z", id="plate")
    assert falls(builder) == []


def test_elements_in_the_air_are_left_to_the_connectivity_pass() -> None:
    builder = ModelBuilder("air")
    builder.place("3003", at=(0, 0, 0), color="Red")
    builder.place("3003", at=(6, 6, 6), color="Red")
    assert analyze(builder)[0] == Stability(falls=(), sites=())


def cantilever(*arms: int) -> ModelBuilder:
    """A plate on the ground, and a 2 x 8 plate on a 2 x 2 brick for each arm."""
    builder = ModelBuilder("cantilever")
    builder.place("3035", at=(0, 0, 0), color="Green", id="ground")
    for k, length in enumerate(arms):
        y = 6 * k
        builder.place("3003", at=(0, y, 1), color="Red", id=f"post{k}")
        for layer in range(length):
            at = (0, y, 4 + layer)
            builder.place(
                "3034", at=at, color="Blue", rotation="R90", id=f"arm{k}.{layer}"
            )
    return builder


def test_a_cantilever_needs_the_clutch_that_its_statics_gives() -> None:
    # The arm rotates about the post's far edge, 2 studs from the arm's center, and
    # four studs hold it, 1.5, 1.5, 0.5 and 0.5 studs behind that edge.
    material = Material(clutch=0.0075, friction=0.2, density=0.54)
    stability, uids = analyze(cantilever(1), material, threshold=0.5)
    arm = weight(2 * 8 * 64 * 3.2)
    post = weight(2 * 2 * 64 * 9.6)
    clutch = material.clutch * 1000
    first, second = stability.sites
    assert [uids[i] for i in first.elements] == ["post0", "arm0.0"]
    assert first.load == pytest.approx(arm * 2 / 4 / clutch, rel=1e-4)
    # Held rigidly to the post, the arm then tips the post about the same edge.
    assert [uids[i] for i in second.elements] == ["ground", "post0"]
    assert second.load == pytest.approx((arm * 2 - post) / 4 / clutch, rel=1e-4)
    assert stability.falls == ()


def test_sites_come_most_loaded_first() -> None:
    stability, uids = analyze(cantilever(2, 1), threshold=0.0025)
    assert [[uids[i] for i in site.elements] for site in stability.sites] == [
        ["post0", "arm0.0"],
        ["ground", "post0"],
        ["post1", "arm1.0"],
    ]
    double, _, single = (site.load for site in stability.sites)
    assert double == pytest.approx(2 * single, rel=1e-4)
    assert [site.load for site in stability.sites] == sorted(
        (site.load for site in stability.sites), reverse=True
    )


def test_a_stud_alone_in_its_seat_twists_with_its_clutch() -> None:
    # A 1 x 8 plate on its edge hangs from one side stud: its weight twists the stud,
    # 3.5 studs out, and tips it out of the wall, 0.2 studs out over 0.5 studs.
    builder = ModelBuilder("twist")
    builder.place("3031", at=(0, 0, 0), color="Green", id="base")
    builder.place("87087", at=(1, 2, 1), color="Red", id="brick")
    builder.place("3460", at=(1, 1.6, 1.5), color="Blue", rotation="-z+x", id="arm")
    stability, uids = analyze(builder, threshold=0.03)
    (site,) = stability.sites
    assert [uids[i] for i in site.elements] == ["brick", "arm"]
    radius = 2.4 / 8
    expected = weight(8 * 64 * 3.2) * (0.2 / 0.5 + 3.5 / radius) / 2940
    assert site.load == pytest.approx(expected, rel=1e-4)


@settings(max_examples=25, deadline=None)
@given(
    st.lists(
        st.tuples(st.integers(0, 3), st.integers(0, 3), st.integers(1, 5)),
        min_size=1,
        max_size=6,
    )
)
def test_columns_of_bricks_stand_and_need_no_clutch(
    columns: list[tuple[int, int, int]],
) -> None:
    builder = ModelBuilder("columns")
    seen: set[tuple[int, int]] = set()
    for x, y, height in columns:
        if (x, y) not in seen:
            seen.add((x, y))
            for level in range(height):
                builder.place("3003", at=(2 * x, 2 * y, 3 * level), color="Red")
    assert analyze(builder)[0] == Stability(falls=(), sites=())


corners = st.tuples(st.integers(-40, 40), st.integers(-40, 40), st.integers(-40, 40))


@settings(max_examples=100, deadline=None)
@given(corners, st.tuples(*[st.integers(1, 30)] * 3))
def test_the_mass_of_a_convex_solid_matches_its_box(
    low: tuple[int, int, int], size: tuple[int, int, int]
) -> None:
    builder = ModelBuilder("one")
    builder.place("3003", at=(0, 0, 0), color="Red")
    (element,) = Context(builder.build(), default_catalog()).world.elements
    box = Box(Vector(*low), Vector(*low) + Vector(*size))
    volume, center = _mass(replace(element, solids=(box,)))
    convex_volume, convex_center = _mass(replace(element, solids=(box.as_convex(),)))
    assert volume == convex_volume == size[0] * size[1] * size[2]
    assert center == pytest.approx(convex_center)
    assert center == pytest.approx([a + b / 2 for a, b in zip(low, size, strict=True)])


rectangles = st.tuples(
    st.integers(-10, 10), st.integers(-10, 10), st.integers(1, 10), st.integers(1, 10)
)


@settings(max_examples=200, deadline=None)
@given(rectangles, rectangles)
def test_faces_that_are_not_rectangles_overlap_as_rectangles_do(
    first: tuple[int, int, int, int], second: tuple[int, int, int, int]
) -> None:
    # A midpoint on one edge makes the first face a pentagon, which the exact polygon
    # clip handles instead of the rectangle shortcut; the area they find is the same.
    def corners(x: int, y: int, width: int, depth: int) -> list[tuple[int, int, int]]:
        x, y, width, depth = 2 * x, 2 * y, 2 * width, 2 * depth
        return [
            (x, y, 0),
            (x + width, y, 0),
            (x + width, y + depth, 0),
            (x, y + depth, 0),
        ]

    up = Vector(0, 0, 1)
    face = corners(*first)
    other = tuple(reversed(corners(*second)))
    pentagon = (face[0], ((face[0][0] + face[1][0]) // 2, face[0][1], 0), *face[1:])
    shortcut = _overlap(tuple(face), other, up)
    clipped = _overlap(pentagon, other, up)
    assert bool(shortcut) == bool(clipped)
    if shortcut:
        xs, ys = {p[0] for p in shortcut}, {p[1] for p in shortcut}
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        twice = sum(
            a[0] * b[1] - b[0] * a[1]
            for a, b in zip(clipped, [*clipped[1:], clipped[0]], strict=True)
        )
        assert twice == 2 * area
        assert {p[0] for p in clipped} >= xs
        assert min(p[0] for p in clipped) == min(xs)
        assert max(p[1] for p in clipped) == max(ys)


def codes(builder: ModelBuilder, clutch: float = 2.94) -> list[tuple[str, str]]:
    report = check_model(
        builder.build(), passes=["stability"], settings=Settings(clutch=clutch)
    )
    return [(d.code, d.message) for d in report.diagnostics]


def test_the_stability_pass_reports_groups_that_fall() -> None:
    builder = ModelBuilder("tipping")
    builder.place("3005", at=(0, 0, 0), color="Red", id="post")
    builder.place("3460", at=(0, 0, 3), color="Blue", rotation="R90", id="arm")
    message = (
        "2 elements fall: no forces at their faces and studs balance their weight, "
        "however firmly the studs grip"
    )
    assert codes(builder) == [("E401", message)]


def test_the_stability_pass_reports_overloaded_and_strained_studs() -> None:
    message = "4 studs joining 2 elements need {}% of their clutch to hold the model"
    assert codes(cantilever(1), clutch=0.0075) == [
        ("E402", message.format(116) + " together"),
        ("W403", message.format(72) + " together"),
    ]


def test_the_stability_pass_passes_interlocking_bricks() -> None:
    builder = ModelBuilder("wall")
    for course in range(3):
        for k in range(3):
            builder.place(
                "3001", at=(4 * k + 2 * (course % 2), 0, 3 * course), color="Red"
            )
    assert codes(builder) == []


def test_the_physical_profile_checks_stability() -> None:
    report = check_model(
        cantilever(1).build(), profile="physical", settings=Settings(clutch=0.0075)
    )
    assert report.passes == ("schema", "collision", "connectivity", "stability")
    assert [d.code for d in report.diagnostics] == ["E402", "W403"]


def test_the_stability_pass_names_the_extra_its_solvers_come_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "bricky.analysis.stability")
    monkeypatch.setitem(sys.modules, "highspy", None)
    with pytest.raises(BrickyError, match=r"needs highspy: .* bricky\[stability\]"):
        codes(cantilever(1))
