# Copyright 2026 Maxence Faldor

from __future__ import annotations

import pytest

from bricky import (
    BrickyError,
    Element,
    Level,
    Model,
    ModelBuilder,
    Settings,
    check_model,
    default_catalog,
)
from bricky.passes import BUILT_IN, installed_passes, installed_rules
from bricky.passes.schema import SchemaPass

SCHEMA: dict[str, Level] = {"all": Level.IGNORE} | {
    rule.name: rule.default_level for rule in SchemaPass.rules
}
"""Levels that check the schema rules alone, each at its default level."""


def rules(model: Model, levels: dict[str, Level] | None = None) -> list[str]:
    report = check_model(model, rules=levels, settings=Settings())
    return [d.rule for d in report.diagnostics]


def stack(*placements: tuple[str, tuple[float, float, float], str]) -> Model:
    builder = ModelBuilder()
    for part, at, rotation in placements:
        builder.place(part, at=at, rotation=rotation, color="Red")
    return builder.build()


def test_the_core_passes_are_installed_through_entry_points_and_run_first() -> None:
    assert tuple(installed_passes())[: len(BUILT_IN)] == BUILT_IN


def test_geometry_rules_are_errors_and_stability_rules_warnings_by_default() -> None:
    levels = {name: rule.default_level for name, (_, rule) in installed_rules().items()}
    assert levels == {
        "unknown-part": Level.ERROR,
        "unknown-color": Level.ERROR,
        "below-ground": Level.ERROR,
        "color-never-made": Level.WARN,
        "overlap": Level.ERROR,
        "blocked-stud": Level.ERROR,
        "floating-group": Level.ERROR,
        "unbalanced-group": Level.WARN,
        "overloaded-studs": Level.WARN,
        "strained-studs": Level.WARN,
    }


def test_interlocking_bricks_pass() -> None:
    model = stack(
        ("3001", (0, 0, 0), "R0"),
        ("3001", (2, 0, 0), "R0"),
        ("3001", (0, 0, 3), "R90"),
        ("3001", (0, 2, 3), "R90"),
        ("3068b", (0, 0, 6), "R0"),
    )
    assert rules(model) == []


def test_parts_resting_on_the_ground_need_no_connection() -> None:
    assert rules(stack(("3001", (0, 0, 0), "R0"), ("3001", (10, 0, 0), "R0"))) == []


def test_overlapping_parts_collide() -> None:
    assert rules(stack(("3001", (0, 0, 0), "R0"), ("3001", (1, 0, 0), "R0"))) == [
        "overlap"
    ]


def test_half_stud_offsets_are_blocked_and_float() -> None:
    model = stack(("3001", (0, 0, 0), "R0"), ("3003", (0.5, 0, 3), "R0"))
    assert rules(model) == ["blocked-stud", "floating-group"]


def test_an_upside_down_tile_cannot_sit_on_studs() -> None:
    model = stack(("3003", (0, 0, 0), "R0"), ("3068b", (0, 0, 3), "+x-y"))
    assert rules(model) == ["blocked-stud", "floating-group"]


def test_floating_groups_are_reported_once_each() -> None:
    model = stack(
        ("3001", (0, 0, 6), "R0"),
        ("3022", (0, 0, 9), "R0"),
        ("3022", (10, 10, 3), "R0"),
    )
    report = check_model(model, settings=Settings())
    assert [d.rule for d in report.diagnostics] == ["floating-group"] * 2
    assert sorted(len(d.elements) for d in report.diagnostics) == [1, 2]


def test_schema_errors() -> None:
    model = Model(
        elements=(
            Element(id="ghost", part="99999", color=5),
            Element(id="odd", part="3001", color=4242),
            Element(id="deep", part="3001", color=5, position=(100, 0, -8)),
        )
    )
    assert rules(model, SCHEMA) == ["unknown-part", "unknown-color", "below-ground"]


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
    report = check_model(builder.build(), rules=SCHEMA)
    assert [(d.rule, d.elements) for d in report.diagnostics] == [
        ("color-never-made", ("never", "again"))
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


def test_reports_give_the_level_of_every_rule() -> None:
    report = check_model(Model(), rules={"overlap": Level.WARN}, settings=Settings())
    assert list(report.rules) == list(installed_rules())
    assert report.rules["overlap"] is Level.WARN
    assert report.rules["floating-group"] is Level.ERROR


def overlap(levels: dict[str, Level]) -> tuple[int, int]:
    """Check two overlapping bricks at the levels given; return errors and warnings."""
    model = stack(("3001", (0, 0, 0), "R0"), ("3001", (1, 0, 0), "R0"))
    report = check_model(model, rules=levels, settings=Settings())
    return report.errors, report.warnings


def test_a_rule_entry_overrides_all() -> None:
    assert overlap({"all": Level.WARN}) == (0, 1)
    assert overlap({"all": Level.IGNORE, "overlap": Level.ERROR}) == (1, 0)


def test_options_apply_over_the_settings() -> None:
    settings = Settings(rules={"all": Level.IGNORE, "overlap": Level.WARN})
    model = stack(("3001", (0, 0, 0), "R0"), ("3001", (1, 0, 0), "R0"))
    assert check_model(model, settings=settings).warnings == 1
    report = check_model(model, rules={"all": Level.ERROR}, settings=settings)
    assert (report.errors, report.warnings) == (1, 0)
    report = check_model(model, rules={"overlap": Level.IGNORE}, settings=settings)
    assert report.diagnostics == ()


def test_unknown_rules_are_rejected() -> None:
    with pytest.raises(BrickyError, match="no installed pass checks a rule named"):
        check_model(Model(), rules={"colision": Level.IGNORE}, settings=Settings())
    settings = Settings(rules={"floating": Level.WARN})
    with pytest.raises(BrickyError, match="'floating'; known rules: unknown-part"):
        check_model(Model(), settings=settings)
