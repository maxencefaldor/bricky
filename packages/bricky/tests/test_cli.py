import json
from pathlib import Path

import pytest

from bricky import ModelBuilder, save_model
from bricky.cli import main

TOWER = """
from bricky import ModelBuilder


def build():
    builder = ModelBuilder("tower")
    builder.place("3001", at=(0, 0, 0), color="Red")
    builder.place("3001", at=(0, 0, 3), rot="R90", color="White")
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
    builder.place("3001", at=(0, 0, 3), color="Red", name="lonely")
    path = tmp_path / "floating.bricky.json"
    save_model(builder.build(), path)
    return path


def test_check_reports_errors_and_exits_1(floating, capsys):
    assert run("check", str(floating)) == 1
    out = capsys.readouterr().out
    assert "error[E301]: 1 element floats" in out
    assert "= elements: lonely" in out


def test_check_writes_json(floating, capsys):
    assert run("check", str(floating), "--output-format", "json") == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert report["diagnostics"][0]["severity"] == "error"


def test_build_saves_and_checks(tmp_path, capsys):
    script = tmp_path / "tower.py"
    script.write_text(TOWER)
    assert run("build", str(script)) == 0
    assert (tmp_path / "tower.bricky.json").is_file()
    assert "0 errors" in capsys.readouterr().out


def test_build_reports_script_failures_with_line_numbers(tmp_path, capsys):
    script = tmp_path / "bad.py"
    script.write_text("def build():\n    return 1 / 0\n")
    assert run("build", str(script)) == 2
    assert f"{script}, line 2: ZeroDivisionError" in capsys.readouterr().err


def test_build_requires_a_build_function(tmp_path, capsys):
    script = tmp_path / "empty.py"
    script.write_text("x = 1\n")
    assert run("build", str(script)) == 2
    assert "must define build()" in capsys.readouterr().err


def test_missing_files_exit_2(tmp_path, capsys):
    assert run("check", str(tmp_path / "nope.json")) == 2
    assert "no such model file" in capsys.readouterr().err


def test_parts_search(capsys):
    assert run("parts", "brick 2x4") == 0
    assert "3001" in capsys.readouterr().out


def test_passes_lists_profiles(capsys):
    assert run("passes") == 0
    out = capsys.readouterr().out
    assert "digital (default): schema, collision, connectivity" in out
    assert "stability (not installed)" in out


def test_json_schema(capsys):
    assert run("json-schema") == 0
    assert json.loads(capsys.readouterr().out)["title"] == "Model"
