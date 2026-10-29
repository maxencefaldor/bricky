# Copyright 2026 Maxence Faldor

from __future__ import annotations

import ast
import inspect

from bricky import ModelBuilder, Settings, check_model, format_report
from bricky.diagnostics import Diagnostic
from bricky.passes import installed_codes, installed_passes


def wall(builder: ModelBuilder, x: int, z: int) -> None:
    builder.place("3001", at=(x, 0, z), color="Red")


def test_every_pass_documents_its_codes_with_a_title_and_a_rule() -> None:
    codes = installed_codes()
    assert {"E101", "E102", "E103", "E201", "E202", "E301"} <= set(codes)
    for name, code in codes.values():
        assert name in installed_passes()
        assert code.title
        assert len(code.rule) > 40


def test_passes_only_emit_codes_they_document() -> None:
    for pass_type in installed_passes().values():
        documented = {code.code for code in pass_type.codes}
        tree = ast.parse(inspect.getsource(pass_type))
        emitted = {
            keyword.value.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            for keyword in node.keywords
            if keyword.arg == "code" and isinstance(keyword.value, ast.Constant)
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
    assert [d.code for d in report.diagnostics] == ["E201", "E301"]
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
