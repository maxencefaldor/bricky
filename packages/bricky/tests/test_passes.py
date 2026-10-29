# Copyright 2026 Maxence Faldor

from __future__ import annotations

import pytest

from bricky import (
    BrickyError,
    Element,
    Model,
    ModelBuilder,
    Settings,
    check_model,
    default_catalog,
)
from bricky.passes import installed_passes
from bricky.settings import DIGITAL


def codes(model: Model, passes: list[str] | None = None) -> list[str]:
    report = check_model(model, passes=passes, settings=Settings())
    return [d.code for d in report.diagnostics]


def stack(*placements: tuple[str, tuple[float, float, float], str]) -> Model:
    builder = ModelBuilder()
    for part, at, rotation in placements:
        builder.place(part, at=at, rotation=rotation, color="Red")
    return builder.build()


def test_the_core_passes_are_installed_through_entry_points() -> None:
    assert set(DIGITAL) <= set(installed_passes())


def test_interlocking_bricks_pass() -> None:
    model = stack(
        ("3001", (0, 0, 0), "R0"),
        ("3001", (2, 0, 0), "R0"),
        ("3001", (0, 0, 3), "R90"),
        ("3001", (0, 2, 3), "R90"),
        ("3068b", (0, 0, 6), "R0"),
    )
    assert codes(model) == []


def test_parts_resting_on_the_ground_need_no_connection() -> None:
    assert codes(stack(("3001", (0, 0, 0), "R0"), ("3001", (10, 0, 0), "R0"))) == []


def test_overlapping_parts_collide() -> None:
    assert codes(stack(("3001", (0, 0, 0), "R0"), ("3001", (1, 0, 0), "R0"))) == [
        "E201"
    ]


def test_half_stud_offsets_are_blocked_and_float() -> None:
    model = stack(("3001", (0, 0, 0), "R0"), ("3003", (0.5, 0, 3), "R0"))
    assert codes(model) == ["E202", "E301"]


def test_an_upside_down_tile_cannot_sit_on_studs() -> None:
    model = stack(("3003", (0, 0, 0), "R0"), ("3068b", (0, 0, 3), "+x-y"))
    assert codes(model) == ["E202", "E301"]


def test_floating_groups_are_reported_once_each() -> None:
    model = stack(
        ("3001", (0, 0, 6), "R0"),
        ("3022", (0, 0, 9), "R0"),
        ("3022", (10, 10, 3), "R0"),
    )
    report = check_model(model, settings=Settings())
    assert [d.code for d in report.diagnostics] == ["E301", "E301"]
    assert sorted(len(d.elements) for d in report.diagnostics) == [1, 2]


def test_schema_errors() -> None:
    model = Model(
        elements=(
            Element(id="ghost", part="99999", color=5),
            Element(id="odd", part="3001", color=4242),
            Element(id="deep", part="3001", color=5, position=(100, 0, -8)),
        )
    )
    assert codes(model, passes=["schema"]) == ["E101", "E102", "E103"]


def test_colors_a_part_never_came_in_are_reported_once_per_part_and_color() -> None:
    catalog = default_catalog()
    brick = catalog.entry("3001")
    assert brick is not None
    made = catalog.resolve_color(brick.colors[0])
    never = next(color for color in catalog.colors if color.id not in brick.colors)
    builder = ModelBuilder("colors")
    builder.place("3001", at=(0, 0, 0), color=made.id, id="made")
    builder.place("3001", at=(4, 0, 0), color=never.id, id="never")
    builder.place("3001", at=(8, 0, 0), color=never.id, id="again")
    report = check_model(builder.build(), passes=["schema"])
    assert [(d.code, d.elements) for d in report.diagnostics] == [
        ("W104", ("never", "again"))
    ]
    assert report.ok


def test_reports_cap_diagnostics_but_count_everything() -> None:
    builder = ModelBuilder()
    for i in range(5):
        builder.place("3024", at=(3 * i, 0, 2), color="Red")
    report = check_model(builder.build(), max_diagnostics=2, settings=Settings())
    assert report.errors == 5
    assert len(report.diagnostics) == 2
    assert report.omitted == 3
    assert not report.ok


def test_profiles_report_passes_that_are_not_installed() -> None:
    settings = Settings(profiles={"stable": (*DIGITAL, "stability")})
    report = check_model(
        stack(("3001", (0, 0, 0), "R0")), profile="stable", settings=settings
    )
    assert report.passes == DIGITAL
    assert report.missing == ("stability",)


def test_passes_named_explicitly_must_be_installed() -> None:
    with pytest.raises(BrickyError, match="no installed pass is named 'colision'"):
        check_model(Model(), passes=("colision",), settings=Settings())


def test_unknown_profiles_are_rejected() -> None:
    with pytest.raises(BrickyError, match="unknown profile"):
        check_model(Model(), profile="lunar", settings=Settings())


def test_configured_profiles_extend_the_defaults() -> None:
    settings = Settings(profiles={"quick": ("schema",)})
    assert set(settings.profiles) == {"digital", "quick"}
    report = check_model(
        stack(("3001", (0, 0, 0), "R0")), profile="quick", settings=settings
    )
    assert report.passes == ("schema",)
