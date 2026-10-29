# Copyright 2026 Maxence Faldor

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from bricky import ModelBuilder, __version__, save_model, service
from bricky.cli import main

TOWER = """
from bricky import ModelBuilder


def build():
    builder = ModelBuilder("tower")
    builder.place("3001", at=(0, 0, 0), color="Red")
    builder.place("3001", at=(0, 0, 3), rotation="R90", color="White")
    return builder
"""


def run(*args: str) -> int:
    """Run the CLI and return its exit code."""
    try:
        main([*args])
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else 0
    return 0


@pytest.fixture
def floating(tmp_path: Path) -> Path:
    builder = ModelBuilder("floating")
    builder.place("3001", at=(0, 0, 3), color="Red", id="lonely")
    path = tmp_path / "floating.bricky.json"
    save_model(builder.build(), path)
    return path


def test_version_prints_the_installed_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("--version") == 0
    assert capsys.readouterr().out == f"bricky {__version__}\n"


def test_check_states_facts_and_exits_1(
    floating: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("check", str(floating)) == 1
    out = capsys.readouterr().out
    assert "error[floating-group]: 1 element floats" in out
    assert "= lonely: Brick 2 x 4 (3001), Red" in out
    assert "help" not in out


def test_check_writes_json(floating: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("check", str(floating), "--output-format", "json") == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert report["diagnostics"][0]["rule"] == "floating-group"
    assert report["rules"]["floating-group"] == "error"
    assert report["elements"]["lonely"]["part_name"] == "Brick 2 x 4"


def test_build_saves_checks_and_names_script_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = tmp_path / "tower.py"
    script.write_text(
        TOWER.replace('at=(0, 0, 3), rotation="R90"', 'at=(9, 9, 3), rotation="R90"')
    )
    assert run("build", str(script), "--no-render") == 1
    assert (tmp_path / "tower.bricky.json").is_file()
    assert (tmp_path / "tower.bricky.map.json").is_file()
    out = capsys.readouterr().out
    assert "error[floating-group]" in out
    assert "tower.py:8 in build()" in out
    assert "by source line:" in out


def test_a_failed_render_keeps_the_report_and_says_why(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BRICKY_RENDER_BROWSER", str(tmp_path / "no-such-browser"))
    script = tmp_path / "tower.py"
    script.write_text(TOWER)
    assert run("build", str(script)) == 2
    out = capsys.readouterr().out
    assert "checked 2 elements" in out
    assert "not rendered: cannot start Chromium" in out
    assert (tmp_path / "tower.bricky.json").is_file()


def test_invalid_arguments_fail_in_one_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("build", "--views", "sideways", str(tmp_path / "x.py")) == 2
    assert capsys.readouterr().err.startswith("error: invalid arguments: --views:")


def test_a_command_without_its_subcommand_fails() -> None:
    assert run("catalog") == 2


def test_unknown_parts_point_past_the_sample(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = tmp_path / "panel.py"
    script.write_text(TOWER.replace('"3001", at=(0, 0, 0)', '"60581", at=(0, 0, 0)'))
    assert run("build", str(script), "--no-render") == 2
    assert "the sample catalog in use holds 112 common parts" in capsys.readouterr().err
    assert run("parts", "wall panel") == 0
    assert "`bricky catalog import` imports every" in capsys.readouterr().out


def test_build_shows_what_the_script_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = tmp_path / "chatty.py"
    script.write_text(
        TOWER.replace(
            "    return builder",
            '    print("hello from the script")\n    return builder',
        )
    )
    assert run("build", str(script), "--no-render") == 0
    assert "script output:\n  hello from the script" in capsys.readouterr().out


def test_building_again_says_what_changed_and_where(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = tmp_path / "tower.py"
    script.write_text(TOWER)
    assert run("build", str(script), "--no-render") == 0
    assert "since the last build" not in capsys.readouterr().out
    assert run("build", str(script), "--no-render") == 0
    assert "since the last build: no changes (2 elements)" in capsys.readouterr().out
    script.write_text(
        TOWER.replace('color="White"', 'color="Blue"').replace(
            "    return builder",
            '    builder.place("3001", at=(0, 0, 6), color="Red")\n    return builder',
        )
    )
    assert run("build", str(script), "--no-render", "--output-format", "json") == 0
    changes = json.loads(capsys.readouterr().out)["changes"]
    assert (changes["added"], changes["removed"], changes["changed"]) == (1, 0, 1)
    assert changes["voxels_filled"] == changes["voxels_recolored"] == 2 * 4 * 3
    assert changes["added_at"] == [{"line": f"{script}:9 in build()", "elements": 1}]
    # Taking out the first brick renumbers the others, which are still unchanged.
    edited = script.read_text().replace(
        '    builder.place("3001", at=(0, 0, 0), color="Red")\n', ""
    )
    script.write_text(edited)
    assert run("build", str(script), "--no-render") == 1  # the rest now floats
    out = capsys.readouterr().out
    assert "since the last build: 0 added, 1 removed, 0 changed, 2 unchanged" in out
    assert (
        f"removed from the earlier script at:\n    {script}:7 in build(): 1 element"
        in out
    )


def test_build_reports_script_failures_with_line_numbers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = tmp_path / "bad.py"
    script.write_text("def build():\n    return 1 / 0\n")
    assert run("build", str(script)) == 2
    err = capsys.readouterr().err
    assert "bad.py:2 in build(): ZeroDivisionError: division by zero" in err


def test_build_requires_a_build_function(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = tmp_path / "empty.py"
    script.write_text("x = 1\n")
    assert run("build", str(script)) == 2
    assert "must define build()" in capsys.readouterr().err


def test_missing_files_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("check", str(tmp_path / "nope.json")) == 2
    assert "no such model file" in capsys.readouterr().err


def test_build_renders_a_sheet_and_render_looks_closer_beside_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = tmp_path / "tower.py"
    script.write_text(TOWER)
    assert run("build", str(script)) == 0
    image = tmp_path / "tower.png"
    assert f"sheet: {image}" in capsys.readouterr().out
    sheet = image.read_bytes()
    assert sheet.startswith(b"\x89PNG")
    model = str(tmp_path / "tower.bricky.json")
    look = ("--views", "front", "--highlight", "@build", "--clip", "z<3", "--html")
    assert run("render", model, *look) == 0
    out = capsys.readouterr().out
    front = tmp_path / "tower.front.png"
    assert front.read_bytes().startswith(b"\x89PNG")
    assert f"front: {front}" in out
    assert image.read_bytes() == sheet
    viewer = tmp_path / "tower.html"
    assert f"viewer: {viewer}" in out
    assert '"clips":[{"axis":"z","keep":"below","value":24}]' in viewer.read_text()


def test_outputs_go_where_they_are_asked_creating_folders(tmp_path: Path) -> None:
    script = tmp_path / "tower.py"
    script.write_text(TOWER)
    model = tmp_path / "out" / "models" / "tower.bricky.json"
    assert run("build", str(script), "--output", str(model), "--no-render") == 0
    assert model.is_file()
    assert (model.parent / "tower.bricky.map.json").is_file()
    shots = tmp_path / "shots" / "look.png"
    assert (
        run(
            "render",
            str(model),
            "--views",
            "perspective",
            "--views",
            "top",
            "--output",
            str(shots),
        )
        == 0
    )
    assert (shots.parent / "look.perspective.png").is_file()
    assert (shots.parent / "look.top.png").is_file()


def test_files_that_cannot_be_written_or_read_are_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = tmp_path / "tower.py"
    script.write_text(TOWER)
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where a folder would go")
    assert (
        run("build", str(script), "--output", str(blocker / "tower.bricky.json")) == 2
    )
    assert f"cannot write {blocker / 'tower.bricky.json'}" in capsys.readouterr().err
    assert run("check", str(tmp_path)) == 2
    assert f"cannot read {tmp_path}" in capsys.readouterr().err


DOWNLOADS = Path(__file__).parent / "data" / "bricklink"


def test_the_catalog_is_imported_and_looked_into(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "catalog.json"
    assert (
        run("catalog", "import", "--bricklink", str(DOWNLOADS), "--output", str(output))
        == 0
    )
    out = capsys.readouterr().out
    assert (
        "imported 9 parts and 6 colors from:\n  BrickLink catalog downloads of " in out
    )
    assert "5 parts have a shape and can be placed; 4 have none" in out
    assert "shapes by source: name 3, printed 2" in out
    assert "  Technic, Brick: 1" in out
    assert "Mystery Color (240): no RGB value" in out
    assert "bricky does not use it yet" in out
    monkeypatch.setenv("BRICKY_CATALOG", str(output))
    assert run("catalog", "status") == 0
    assert "9 parts, 5 with a shape (2 printed), 6 colors" in capsys.readouterr().out
    assert run("catalog", "show", "3068bpb0001") == 0
    out = capsys.readouterr().out
    assert "printed on: 3068b, whose shape it has" in out
    assert (
        "shape: tile, 2 x 2 studs (x by y, unrotated), 1 plate tall, "
        "0 studs, 4 anti-studs" in out
    )
    image = tmp_path / "brick.png"
    assert run("catalog", "show", "3001", "--render", "--output", str(image)) == 0
    assert "colors (2): White, Red" in capsys.readouterr().out
    assert image.read_bytes().startswith(b"\x89PNG")
    assert run("catalog", "verify") == 0
    assert "checked 5 parts: 0 problems" in capsys.readouterr().out
    assert run("parts", "brick", "--shapeless") == 0
    shapeless = r"\n3700 +Technic, Brick 1 x 2 with Hole +no shape: cannot be placed\n"
    assert re.search(shapeless, capsys.readouterr().out)
    assert run("catalog", "show", "3700", "--render") == 2
    assert "part 3700 has no shape to render" in capsys.readouterr().err


def test_shapes_come_from_ldraw_for_parts_no_name_describes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "catalog.json"
    ldraw = str(DOWNLOADS.parent / "ldraw")
    assert run("catalog", "import", "--ldraw", ldraw, "--output", str(output)) == 0
    captured = capsys.readouterr()
    assert "looked at 9 of 9 parts" in captured.err
    assert "shapes by source: LDraw 6, printed 1" in captured.out
    assert "encloses no volume: 1" in captured.out
    monkeypatch.setenv("BRICKY_CATALOG", str(output))
    assert run("catalog", "show", "4490") == 0
    out = capsys.readouterr().out
    assert (
        "shape: boxes, 3 x 1 studs (x by y, unrotated), 3 plates tall, "
        "3 studs, 2 anti-studs" in out
    )
    assert "converted from LDraw 4490.dat, as it is oriented there" in out
    assert run("catalog", "verify") == 0
    assert run("catalog", "import") == 2
    assert (
        "needs BrickLink's downloads, an LDraw library, or both"
        in capsys.readouterr().err
    )


def test_show_maps_a_sloped_top_and_renders_the_part_outside_the_workspace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "PART_IMAGES", tmp_path / "parts")
    monkeypatch.chdir(tmp_path)
    assert run("catalog", "show", "3039", "--render") == 0  # Slope 45 2 x 2
    out = capsys.readouterr().out
    assert (
        "height over each square in plates, north up:\n       3    3\n    1.75 1.75\n"
        in out
    )
    assert (tmp_path / "parts" / "3039.png").is_file()
    assert not (tmp_path / "3039.png").exists()
    assert run("catalog", "show", "3001") == 0
    assert "height over" not in capsys.readouterr().out


def test_help_writes_choices_as_the_values_the_command_line_accepts(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "PYTHON_COLORS", "0"
    )  # argparse colors help where CI forces color
    monkeypatch.setenv("COLUMNS", "200")  # one line per option, whatever the terminal
    assert run("render", "--help") == 0
    out = capsys.readouterr().out
    assert "--views {sheet,perspective,perspective-south-west," in out
    assert "--width N" in out
    assert "--output PATH" in out
    assert "(default: sheet)" in out
    assert "(default: --check)" in out
    assert "(default: --no-html)" in out
    for python in ("View.", "list[", " int", "None", "factory", "True", "False"):
        assert python not in out


def test_errors_are_json_when_the_output_is(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = str(tmp_path / "nope.json")
    assert run("check", missing, "--output-format", "json") == 2
    assert "no such model file" in json.loads(capsys.readouterr().out)["error"]
    assert run("check", missing, "--output-format=json", "--max-diagnostics", "x") == 2
    assert json.loads(capsys.readouterr().out)["error"].startswith("invalid arguments")


def test_parts_search(capsys: pytest.CaptureFixture[str]) -> None:
    assert run("parts", "plate 1x1") == 0
    out = capsys.readouterr().out
    assert "3024" in out
    assert "1 plate  1 stud" in out


def test_colors_search(capsys: pytest.CaptureFixture[str]) -> None:
    assert run("colors", "bluish") == 0
    out = capsys.readouterr().out
    assert "Light Bluish Gray" in out
    assert "Dark Bluish Gray" in out
    assert "2 colors" in out


def test_check_options_set_rule_levels(
    floating: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("check", str(floating), "--warn", "floating-group") == 0
    assert "warning[floating-group]: 1 element floats" in capsys.readouterr().out
    assert run("check", str(floating), "--ignore", "all") == 0
    out = capsys.readouterr().out
    assert "against 0 rules" in out
    assert "0 errors, 0 warnings" in out


def test_check_options_take_a_rule_once(
    floating: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = ("--error", "overlap", "--ignore", "overlap")
    assert run("check", str(floating), *arguments) == 2
    assert "give 'overlap' two levels" in capsys.readouterr().err


def test_build_and_render_reject_unknown_rules_before_any_work(
    tmp_path: Path, floating: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = tmp_path / "tower.py"
    script.write_text(TOWER)
    assert run("build", str(script), "--ignore", "colision", "--no-check") == 2
    assert "which the options name" in capsys.readouterr().err
    assert not (tmp_path / "tower.bricky.json").exists()
    assert run("render", str(floating), "--warn", "colision") == 2
    assert "which the options name" in capsys.readouterr().err


def test_check_rejects_unknown_rules(
    floating: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("check", str(floating), "--ignore", "colision") == 2
    assert "no installed pass checks a rule named 'colision'" in (
        capsys.readouterr().err
    )


def test_explain_gives_the_exact_condition(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("explain", "floating-group") == 0
    out = capsys.readouterr().out
    assert out.startswith("floating-group (error, pass connectivity)")
    assert "held only from above" in out


def test_explain_lists_every_rule_at_its_level(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BRICKY_RULES", '{"strained-studs": "ignore"}')
    assert run("explain") == 0
    out = capsys.readouterr().out
    assert "unknown-part (error, pass schema)" in out
    assert "strained-studs (ignore, by default warn, pass stability)" in out


def test_explain_rejects_unknown_rules(capsys: pytest.CaptureFixture[str]) -> None:
    assert run("explain", "lunar") == 2
    assert "no installed pass checks a rule named 'lunar'" in capsys.readouterr().err


def test_json_schema(capsys: pytest.CaptureFixture[str]) -> None:
    assert run("json-schema") == 0
    assert json.loads(capsys.readouterr().out)["title"] == "Model"
