# Copyright 2026 Maxence Faldor

from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from bricky import Level, ModelBuilder, Settings, check_model, default_catalog
from bricky.analysis import Context
from bricky.analysis import stability as stability_module
from bricky.analysis.stability import (
    GRAVITY,
    Material,
    Stability,
    _mass,
    _overlap,
    analyze_stability,
)
from bricky.geometry import Box, Vector
from bricky.passes.stability import StabilityPass

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


@settings(max_examples=300, deadline=None)
@given(rectangles, rectangles, st.integers(0, 2), st.booleans())
def test_faces_that_are_not_rectangles_overlap_as_rectangles_do(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
    axis: int,
    split_first: bool,  # noqa: FBT001 - a value Hypothesis draws
) -> None:
    # A midpoint on one edge makes a face a pentagon, which the exact polygon clip
    # handles instead of the rectangle shortcut; the area they find is the same, in
    # each plane and whichever face has fewer corners.
    a, b = (axis + 1) % 3, (axis + 2) % 3

    def point(u: int, v: int) -> tuple[int, int, int]:
        coordinates = [0, 0, 0]
        coordinates[a], coordinates[b] = u, v
        return coordinates[0], coordinates[1], coordinates[2]

    def corners(u: int, v: int, width: int, depth: int) -> list[tuple[int, int, int]]:
        u, v, width, depth = 2 * u, 2 * v, 2 * width, 2 * depth
        square = [(u, v), (u + width, v), (u + width, v + depth), (u, v + depth)]
        return [point(*corner) for corner in square]

    def split(face: list[tuple[int, int, int]]) -> tuple[tuple[int, int, int], ...]:
        middle = tuple((p + q) // 2 for p, q in zip(face[0], face[1], strict=True))
        return (face[0], (middle[0], middle[1], middle[2]), *face[1:])

    normal = Vector(*(1 if k == axis else 0 for k in range(3)))
    face, other = corners(*first), list(reversed(corners(*second)))
    shortcut = _overlap(tuple(face), tuple(other), normal)
    if split_first:
        clipped = _overlap(split(face), tuple(other), normal)
    else:
        clipped = _overlap(tuple(face), split(other), normal)
    assert bool(shortcut) == bool(clipped)
    if shortcut:
        us, vs = {p[a] for p in shortcut}, {p[b] for p in shortcut}
        area = (max(us) - min(us)) * (max(vs) - min(vs))
        twice = sum(
            p[a] * q[b] - q[a] * p[b]
            for p, q in zip(clipped, [*clipped[1:], clipped[0]], strict=True)
        )
        assert twice == 2 * area
        assert (min(p[a] for p in clipped), max(p[a] for p in clipped)) == (
            min(us),
            max(us),
        )
        assert (min(p[b] for p in clipped), max(p[b] for p in clipped)) == (
            min(vs),
            max(vs),
        )


def test_an_element_that_reaches_the_ground_along_an_edge_can_tip() -> None:
    # A round brick on its side touches the ground along one edge of its facets.
    builder = ModelBuilder("edge")
    builder.place("3941", at=(0, 0, 0), color="Green", rotation="+x+z", id="round")
    builder.place("3460", at=(0, -0.4, 2.5), color="Red", rotation="-z+x", id="arm")
    assert falls(builder) == [["round", "arm"]]


def lying(x: float) -> ModelBuilder:
    """A 1 x 4 brick on its side, resting on a 2 x 2 tile at ``x`` studs."""
    builder = ModelBuilder("lying")
    builder.place("3068", at=(0, 0, 0), color="White", id="tile")
    builder.place("3010", at=(x, 0, 1), color="Red", rotation="-z+x", id="beam")
    return builder


def test_an_element_on_its_side_rests_on_what_lies_below_it() -> None:
    # Weight closes the gap under a side that faces down, though sides stand in.
    assert falls(lying(-1)) == []
    assert falls(lying(1)) == [["beam"]]


def test_studs_that_share_a_seat_resist_twist_together() -> None:
    # The arm of the twist test, on two side studs instead of one: the studs resist
    # the twist as a couple, so only the arm's tilt out of the wall loads them.
    builder = ModelBuilder("couple")
    builder.place("3031", at=(0, 0, 0), color="Green", id="base")
    builder.place("11211", at=(1, 2, 1), color="Red", id="brick")
    builder.place("3460", at=(1, 1.6, 1.5), color="Blue", rotation="-z+x", id="arm")
    stability, uids = analyze(builder, threshold=1e-5)
    loads = {
        tuple(uids[i] for i in site.elements): site.load for site in stability.sites
    }
    assert loads["brick", "arm"] < 0.001


def test_studs_of_groups_that_fall_need_no_clutch() -> None:
    builder = cantilever(1)
    builder.place("3005", at=(10, 0, 0), color="Red", id="leg")
    builder.place("3460", at=(10, 0, 3), color="Blue", rotation="R90", id="reach")
    material = Material(clutch=0.0075, friction=0.2, density=0.54)
    stability, uids = analyze(builder, material, threshold=0.5)
    assert [[uids[i] for i in group] for group in stability.falls] == [["leg", "reach"]]
    assert [[uids[i] for i in site.elements] for site in stability.sites] == [
        ["post0", "arm0.0"],
        ["ground", "post0"],
    ]


STABILITY: dict[str, Level] = {"all": Level.IGNORE} | {
    rule.name: rule.default_level for rule in StabilityPass.rules
}
"""Levels that check the stability rules alone, each at its default level."""


def found(builder: ModelBuilder, clutch: float = 2.94) -> list[tuple[str, str]]:
    report = check_model(
        builder.build(), rules=STABILITY, settings=Settings(clutch=clutch)
    )
    return [(d.rule, d.message) for d in report.diagnostics]


def test_the_stability_pass_reports_groups_that_fall() -> None:
    builder = ModelBuilder("tipping")
    builder.place("3005", at=(0, 0, 0), color="Red", id="post")
    builder.place("3460", at=(0, 0, 3), color="Blue", rotation="R90", id="arm")
    message = (
        "2 elements fall: no forces at their faces and studs balance their weight, "
        "however firmly the studs grip"
    )
    assert found(builder) == [("unbalanced-group", message)]


def test_the_stability_pass_reports_overloaded_and_strained_studs() -> None:
    message = "4 studs joining 2 elements need {}% of their clutch to hold the model"
    assert found(cantilever(1), clutch=0.0075) == [
        ("overloaded-studs", message.format(116) + " together"),
        ("strained-studs", message.format(73) + " together"),
    ]


def test_the_stability_pass_passes_interlocking_bricks() -> None:
    builder = ModelBuilder("wall")
    for course in range(3):
        for k in range(3):
            builder.place(
                "3001", at=(4 * k + 2 * (course % 2), 0, 3 * course), color="Red"
            )
    assert found(builder) == []


def test_checks_report_stability_as_warnings_by_default() -> None:
    report = check_model(cantilever(1).build(), settings=Settings(clutch=0.0075))
    assert [d.rule for d in report.diagnostics] == [
        "overloaded-studs",
        "strained-studs",
    ]
    assert (report.errors, report.warnings, report.ok) == (0, 2, True)


def test_settings_can_make_stability_rules_errors() -> None:
    settings = Settings(clutch=0.0075, rules={"overloaded-studs": Level.ERROR})
    report = check_model(cantilever(1).build(), settings=settings)
    assert (report.errors, report.warnings, report.ok) == (1, 1, False)
    assert report.is_error(report.diagnostics[0])


def test_checks_skip_the_stability_pass_when_its_rules_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_: object) -> None:
        raise AssertionError

    monkeypatch.setattr(StabilityPass, "run", fail)
    ignored = dict.fromkeys(STABILITY.keys() - {"all"}, Level.IGNORE)
    report = check_model(cantilever(1).build(), rules=ignored)
    assert report.diagnostics == ()


@pytest.mark.parametrize(
    ("ignored", "threshold"),
    [
        ((), 0.5),
        (("strained-studs",), 1.0),
        (("overloaded-studs",), 0.5),
        (("overloaded-studs", "strained-studs"), None),
    ],
)
def test_the_search_for_sites_goes_as_deep_as_the_rules_reported(
    monkeypatch: pytest.MonkeyPatch,
    ignored: tuple[str, ...],
    threshold: float | None,
) -> None:
    asked: list[float | None] = []

    def record(
        context: Context, material: Material, *, threshold: float | None = 1.0
    ) -> Stability:
        asked.append(threshold)
        return analyze_stability(context, material, threshold=threshold)

    monkeypatch.setattr(stability_module, "analyze_stability", record)
    check_model(cantilever(1).build(), rules=dict.fromkeys(ignored, Level.IGNORE))
    assert asked == [threshold]
