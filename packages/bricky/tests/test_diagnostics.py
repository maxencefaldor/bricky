# Copyright 2026 Maxence Faldor

from __future__ import annotations

import ast
import inspect

from bricky import (
    Level,
    ModelBuilder,
    Settings,
    check_model,
    default_catalog,
    format_report,
)
from bricky.diagnostics import Diagnostic
from bricky.passes import installed_passes, installed_rules


def wall(builder: ModelBuilder, x: int, z: int) -> None:
    builder.place("3001", at=(x, 0, z), color="Red")


def test_every_pass_documents_its_rules_with_a_level_and_a_condition() -> None:
    rules = installed_rules()
    assert {"unknown-part", "overlap", "blocked-stud", "floating-group"} <= set(rules)
    for name, rule in rules.values():
        assert name in installed_passes()
        assert len(rule.condition) > 40


def test_passes_only_emit_rules_they_document() -> None:
    for pass_type in installed_passes().values():
        documented = {rule.name for rule in pass_type.rules}
        tree = ast.parse(inspect.getsource(pass_type))
        emitted = {
            keyword.value.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            for keyword in node.keywords
            if keyword.arg == "rule" and isinstance(keyword.value, ast.Constant)
        }
        assert emitted <= documented, pass_type.name


def test_diagnostics_carry_facts_and_no_advice() -> None:
    assert "help" not in Diagnostic.model_fields


def test_reports_describe_each_element_and_count_script_lines() -> None:
    builder = ModelBuilder("m")
    wall(builder, 0, 0)
    wall(builder, 1, 0)
    wall(builder, 20, 9)
    report = check_model(
        builder.build(), provenance=builder.provenance(), settings=Settings()
    )
    assert [d.rule for d in report.diagnostics] == ["overlap", "floating-group"]
    info = report.elements["e1"]
    assert (info.part_name, info.color_name) == ("Brick 2 x 4", "Red")
    assert info.source is not None
    assert info.source.site.function == "wall"
    text = format_report(report)
    assert "= e1: Brick 2 x 4 (3001), Red, " in text
    assert "in wall()" in text
    assert "by source line:" in text
    assert "3 diagnostics" not in text
    assert ": 2 diagnostics" in text
    assert text.endswith(
        "checked 3 elements against 8 rules (overloaded-studs, strained-studs ignored):"
        " 2 errors, 0 warnings"
    )


def test_reports_without_provenance_still_name_parts_and_colors() -> None:
    builder = ModelBuilder("m")
    builder.place("3022", at=(0, 0, 5), color="Tan", id="floating")
    report = check_model(builder.build(), settings=Settings())
    assert report.elements["floating"].source is None
    text = format_report(report)
    assert "= floating: Plate 2 x 2 (3022), Tan" in text
    assert "by source line" not in text


def test_long_element_lists_are_shortened_in_text_but_complete_in_data() -> None:
    builder = ModelBuilder("m")
    for z in range(5, 30, 3):
        builder.place("3003", at=(0, 0, z), color="Red")
    report = check_model(builder.build(), settings=Settings())
    (diagnostic,) = report.diagnostics
    assert len(diagnostic.elements) == 9
    assert "and 3 more elements" in format_report(report)


def test_script_lines_that_tie_list_in_the_order_diagnostics_name_them() -> None:
    builder = ModelBuilder("m")
    builder.place("3001", at=(0, 0, 0), color="Red", id="first")
    builder.place("3001", at=(1, 0, 0), color="Blue", id="second")
    report = check_model(
        builder.build(), provenance=builder.provenance(), settings=Settings()
    )
    sites = []
    for uid in ("first", "second"):
        source = report.elements[uid].source
        assert source is not None
        sites.append(f"  {source.site}: 1 diagnostic")
    text = format_report(report)
    assert text.index(sites[0]) < text.index(sites[1])


def test_the_summary_names_ignored_rules_or_counts_many() -> None:
    builder = ModelBuilder("m")
    wall(builder, 0, 0)
    model = builder.build()
    one = check_model(model, rules={"overloaded-studs": Level.WARN})
    assert format_report(one).endswith(
        "against 9 rules (strained-studs ignored): 0 errors, 0 warnings"
    )
    most = check_model(model, rules={"all": Level.IGNORE, "overlap": Level.ERROR})
    assert format_report(most).endswith(
        "against 1 rule (9 ignored): 0 errors, 0 warnings"
    )


def test_reports_count_every_diagnostic_by_rule_beyond_the_cap() -> None:
    builder = ModelBuilder("m")
    for i in range(5):
        builder.place("3024", at=(3 * i, 0, 2), color="Red")
    report = check_model(builder.build(), max_diagnostics=2, settings=Settings())
    assert len(report.diagnostics) == 2
    assert report.counts == {"floating-group": 5}


def test_errors_come_first_under_the_cap() -> None:
    catalog = default_catalog()
    brick = catalog.entry("3001")
    assert brick is not None
    never = next(color for color in catalog.colors if color.id not in brick.colors)
    builder = ModelBuilder("m")
    builder.place("3001", at=(0, 0, 0), color=never.id, id="odd")
    wall(builder, 10, 0)
    wall(builder, 11, 0)
    report = check_model(builder.build(), max_diagnostics=1, settings=Settings())
    assert [d.rule for d in report.diagnostics] == ["overlap"]
    assert report.counts == {"color-never-made": 1, "overlap": 1}
