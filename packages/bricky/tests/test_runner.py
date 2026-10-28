# Copyright 2026 Maxence Faldor

import asyncio
from pathlib import Path

import pytest

from bricky import BrickyError, Settings
from bricky.runner import run
from bricky.service import run_script

MODEL = """
from bricky import ModelBuilder


def build():
    builder = ModelBuilder("m")
    builder.place("3001", at=(0, 0, 0), color="Red")
    return builder
"""


def write(tmp_path: Path, text: str, name: str = "script.py") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def run_child(script: Path, timeout: float = 30, limit: int = 1000):
    settings = Settings(build_timeout=timeout, output_limit=limit)
    return asyncio.run(run_script(script, settings))


def test_run_returns_the_model_and_its_provenance(tmp_path):
    result = run(write(tmp_path, MODEL))
    assert result.failure is None
    assert result.model is not None
    assert result.model.element_count() == 1
    assert result.provenance is not None
    (source,) = result.provenance.model.elements.values()
    assert source.site.line == 7


def test_failures_name_the_script_lines_innermost_first(tmp_path):
    text = "def helper():\n    return 1 / 0\n\n\ndef build():\n    return helper()\n"
    failure = run(write(tmp_path, text)).failure
    assert failure is not None
    assert failure.error == "ZeroDivisionError"
    assert [frame.line for frame in failure.frames] == [2, 6]
    assert str(failure).endswith("called from " + str(failure.frames[1]))


def test_errors_inside_bricky_point_at_the_calling_line(tmp_path):
    text = MODEL.replace('color="Red"', 'color="Mauve"')
    failure = run(write(tmp_path, text)).failure
    assert failure is not None
    assert failure.error == "ValueError"
    assert failure.frames[0].line == 7
    assert "unknown color 'Mauve'" in failure.message


def test_exits_and_missing_entry_points_are_failures(tmp_path):
    exited = run(write(tmp_path, "import sys\nsys.exit(3)\n")).failure
    assert exited is not None
    assert exited.error == "SystemExit"
    assert "exited with 3" in exited.message
    missing = run(write(tmp_path, "x = 1\n", "other.py")).failure
    assert missing is not None
    assert "must define build()" in missing.message


def test_scripts_import_helpers_that_sit_beside_them(tmp_path):
    write(tmp_path, "COLOR = 'Blue'\n", "palette.py")
    text = "from palette import COLOR\n" + MODEL.replace('"Red"', "COLOR")
    result = run(write(tmp_path, text))
    assert result.failure is None


def test_child_processes_capture_what_scripts_print(tmp_path):
    noisy = "    print('to stdout')\n    import sys\n    print('to stderr', file=sys.stderr)\n"
    text = MODEL.replace("    return builder", noisy + "    return builder")
    output = run_child(write(tmp_path, text)).output
    assert output.stdout == "to stdout\n"
    assert output.stderr == "to stderr\n"
    assert not output.truncated


def test_child_output_is_cut_at_the_limit(tmp_path):
    text = MODEL.replace(
        "    return builder", "    print('x' * 5000)\n    return builder"
    )
    output = run_child(write(tmp_path, text), limit=100).output
    assert len(output.stdout) == 100
    assert output.truncated


def test_endless_scripts_are_stopped(tmp_path):
    script = write(tmp_path, "def build():\n    while True:\n        pass\n")
    with pytest.raises(BrickyError, match="did not finish within 1 s"):
        run_child(script, timeout=1)


def test_failures_come_back_with_what_the_script_printed(tmp_path):
    script = write(
        tmp_path, "def build():\n    print('working')\n    raise RuntimeError('boom')\n"
    )
    with pytest.raises(BrickyError) as caught:
        run_child(script)
    message = str(caught.value)
    assert "script.py:3 in build(): RuntimeError: boom" in message
    assert "script output:\n  working" in message


def test_hard_crashes_are_reported(tmp_path):
    script = write(tmp_path, "import os\n\n\ndef build():\n    os._exit(7)\n")
    with pytest.raises(
        BrickyError, match="exited with code 7 before reporting a result"
    ):
        run_child(script)


def test_results_cut_short_are_reported(tmp_path):
    text = (
        "import os\nimport sys\nfrom pathlib import Path\n\n\n"
        "def build():\n    Path(sys.argv[2]).write_text('{\"model\": {')\n    os._exit(0)\n"
    )
    with pytest.raises(
        BrickyError, match="exited with code 0 before reporting a result"
    ):
        run_child(write(tmp_path, text))


def test_missing_scripts_are_reported(tmp_path):
    with pytest.raises(BrickyError, match="no such build script"):
        run_child(tmp_path / "nope.py")
