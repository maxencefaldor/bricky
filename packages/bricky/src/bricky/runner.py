# Copyright 2026 Maxence Faldor
"""Run one build script in a process of its own.

The service starts ``python -P -m bricky.runner SCRIPT RESULT`` for every build. The
script's prints, crashes, exits and endless loops therefore stay out of the command line
and the MCP server, whose standard output may be a protocol channel. The runner writes a
:class:`RunResult` as JSON to ``RESULT``. The script prints to the runner's own standard
streams, which the service captures and returns.
"""

from __future__ import annotations

import runpy
import sys
import traceback
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import override

from pydantic import BaseModel, ConfigDict, Field

from bricky.builder import ModelBuilder
from bricky.model import Model
from bricky.provenance import Frame, Provenance, is_script_file, relative_path


class Failure(BaseModel):
    """Why a build script produced no model."""

    model_config = ConfigDict(frozen=True)

    error: str = Field(description="Exception type, such as 'ValueError'.")
    message: str = Field(description="Exception message.")
    frames: tuple[Frame, ...] = Field(
        default=(), description="Script frames of the traceback, innermost first."
    )

    @override
    def __str__(self) -> str:
        """The error and its message, then the script frames that raised it."""
        head = f"{self.error}: {self.message}" if self.message else self.error
        if not self.frames:
            return head
        callers = "".join(f"\n  called from {frame}" for frame in self.frames[1:])
        return f"{self.frames[0]}: {head}{callers}"


class RunResult(BaseModel):
    """What a build script produced: a model and its provenance, or a failure."""

    model: Model | None = None
    provenance: Provenance | None = None
    failure: Failure | None = None


def run(script: Path) -> RunResult:
    """Run a build script in this process and return its model, provenance or failure.

    The script's directory comes first on the import path while the script runs, so the
    script can import helper modules beside it, as under ``python script.py``.
    """
    root = Path.cwd()
    try:
        with _importable(script.parent):
            return _run(script, root)
    except SystemExit as error:
        return RunResult(
            failure=_failure(error, root, f"the script exited with {error.code!r}")
        )
    except BaseException as error:  # noqa: BLE001 - a build script may raise anything
        return RunResult(failure=_failure(error, root, str(error)))


def _run(script: Path, root: Path) -> RunResult:
    namespace = runpy.run_path(str(script), run_name="__bricky__")
    entry = namespace.get("build")
    if not callable(entry):
        message = f"{script} must define build(), returning a ModelBuilder or a Model"
        return RunResult(failure=Failure(error="BuildScriptError", message=message))
    result = entry()
    provenance = None
    if isinstance(result, ModelBuilder):
        provenance = result.provenance().relative_to(root)
        result = result.build()
    if not isinstance(result, Model):
        message = (
            f"build() returned {type(result).__name__}, not a ModelBuilder or a Model"
        )
        return RunResult(failure=Failure(error="BuildScriptError", message=message))
    return RunResult(model=result, provenance=provenance)


@contextmanager
def _importable(directory: Path) -> Generator[None]:
    entry = str(directory.resolve())
    sys.path.insert(0, entry)
    try:
        yield
    finally:
        sys.path.remove(entry)


def _failure(error: BaseException, root: Path, message: str) -> Failure:
    """Describe an exception by the script lines it passed through, innermost first."""
    frames = [
        Frame(
            file=frame.f_code.co_filename, line=line or 1, function=frame.f_code.co_name
        )
        for frame, line in traceback.walk_tb(error.__traceback__)
        if is_script_file(frame.f_code.co_filename)
    ]
    frames.reverse()
    relative = tuple(
        frame.model_copy(update={"file": relative_path(frame.file, root)})
        for frame in frames
    )
    return Failure(error=type(error).__name__, message=message, frames=relative)


def main(argv: list[str] | None = None) -> None:
    """Run the script named by the first argument and write the result to the second."""
    script, result = (
        Path(argument) for argument in (argv if argv is not None else sys.argv[1:])
    )
    outcome = run(script)
    result.write_text(outcome.model_dump_json(), encoding="utf-8")


if __name__ == "__main__":
    main()
