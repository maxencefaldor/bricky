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
from bricky.analysis import Context
from bricky.diagnostics import Diagnostic, Rule
from bricky.passes import BUILT_IN, installed_passes, installed_rules, registry
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


def test_sure_rules_are_errors_and_slow_uncertain_ones_off_by_default() -> None:
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
        "overloaded-studs": Level.IGNORE,
        "strained-studs": Level.IGNORE,
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
    with pytest.raises(BrickyError, match="'colision', which the options name"):
        check_model(Model(), rules={"colision": Level.IGNORE}, settings=Settings())
    settings = Settings(rules={"floating": Level.WARN})
    with pytest.raises(BrickyError, match="'floating', which the settings name"):
        check_model(Model(), settings=settings)


class Odd:
    """A pass that reports a rule it does not list."""

    name = "odd"
    summary = "Reports what it never lists."
    rules = (Rule(name="listed", default_level=Level.ERROR, condition="Listed."),)

    def run(self, context: Context) -> list[Diagnostic]:
        """Report a fact under a rule the pass does not list."""
        del context
        return [Diagnostic(rule="unlisted", message="a fact under no listed rule")]


def test_passes_cannot_report_rules_they_do_not_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "installed_passes", lambda: {"odd": Odd})
    context = Context(Model(), default_catalog(), Settings())
    with pytest.raises(BrickyError, match="pass 'odd' reports rule 'unlisted'"):
        registry.run_passes(context, {"listed": Level.ERROR})


def test_rules_belong_to_one_pass_and_never_take_the_name_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rules = installed_rules.__wrapped__
    monkeypatch.setattr(registry, "installed_passes", lambda: {"a": Odd, "b": Odd})
    with pytest.raises(BrickyError, match="passes 'a' and 'b' both check rule listed"):
        rules()

    class All(Odd):
        rules = (Rule(name="all", default_level=Level.WARN, condition="Every."),)

    monkeypatch.setattr(registry, "installed_passes", lambda: {"all": All})
    with pytest.raises(BrickyError, match="names a rule 'all'"):
        rules()


def test_other_passes_run_after_the_built_in_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Point:
        def __init__(self, name: str) -> None:
            self.name = name

        def load(self) -> type[Odd]:
            return Odd

    names = ["acoustics", "stability", "schema", "collision", "beauty", "connectivity"]

    def points(group: str) -> list[Point]:
        assert group == registry.ENTRY_POINT_GROUP
        return [Point(name) for name in names]

    monkeypatch.setattr(registry, "entry_points", points)
    assert list(installed_passes.__wrapped__()) == [
        *BUILT_IN,
        "acoustics",
        "beauty",
    ]
