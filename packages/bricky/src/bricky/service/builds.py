# Copyright 2026 Maxence Faldor
"""Builds: run a build script, then save, check and render its model.

:func:`run_script` runs each build script in a child process (see :mod:`bricky.runner`),
within a timeout, and captures what the script prints.
"""

from __future__ import annotations

import asyncio
import sys
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import CliPositionalArg

from bricky.analysis import build_world, diff_worlds
from bricky.catalog import Catalog
from bricky.diagnostics import Report, format_report
from bricky.errors import BrickyError
from bricky.files import SUFFIX, model_stem, save_model, save_source_map
from bricky.geometry import Box
from bricky.model import Model
from bricky.provenance import Provenance
from bricky.render import View
from bricky.runner import RunResult
from bricky.service.checks import rule_levels, run_check
from bricky.service.session import (
    ERROR_HELP,
    IGNORE_HELP,
    MAX_DIAGNOSTICS_HELP,
    VIEWS_HELP,
    WARN_HELP,
    Image,
    Session,
    Timings,
    describe_images,
    describe_timings,
    indent,
    plural,
    read_model,
    render_views,
    view_paths,
)
from bricky.settings import Settings
from bricky.units import to_plates, to_studs

_LISTED_LINES: Final = 10


class ScriptOutput(BaseModel):
    """What a build script printed."""

    stdout: str = Field(
        default="", description="Standard output, up to the configured limit."
    )
    stderr: str = Field(
        default="", description="Standard error, up to the configured limit."
    )
    truncated: bool = Field(
        default=False, description="Whether either stream was truncated."
    )

    def describe(self) -> str:
        """Return the output as text, empty when the script printed nothing."""
        parts = []
        if self.stdout.strip():
            parts.append("script output:\n" + indent(self.stdout.rstrip()))
        if self.stderr.strip():
            parts.append("script errors:\n" + indent(self.stderr.rstrip()))
        if self.truncated:
            parts.append("(output truncated at the configured limit)")
        return "\n\n".join(parts)


class BuildRequest(BaseModel):
    """Run a build script, save its model, check it and render it.

    The script runs as ordinary Python with the user's permissions, in its own process
    with a time limit; that process is not a sandbox.
    """

    script: CliPositionalArg[Path] = Field(
        description=(
            "Python file defining build(), which returns a ModelBuilder or a Model."
        )
    )
    output: Path | None = Field(
        default=None,
        description="Where to save the model; defaults to <script>.bricky.json.",
    )
    check: bool = Field(default=True, description="Check the model after building it.")
    render: bool = Field(
        default=True, description="Render the model after checking it."
    )
    views: list[View] = Field(default=[View.SHEET], description=VIEWS_HELP)
    error: list[str] = Field(default_factory=list, description=ERROR_HELP)
    warn: list[str] = Field(default_factory=list, description=WARN_HELP)
    ignore: list[str] = Field(default_factory=list, description=IGNORE_HELP)
    max_diagnostics: int | None = Field(
        default=None, ge=1, description=MAX_DIAGNOSTICS_HELP
    )


class LineCount(BaseModel):
    """Elements counted by the build-script line that placed them."""

    line: str = Field(description="Script file, line and enclosing function.")
    elements: int


class Changes(BaseModel):
    """What changed since the last build saved a model at the same path.

    The counts unfold every instance. Elements match by part, color and the space they
    take, whatever their ids, so renumbered elements count as unchanged. An element with
    the same id and part in another position, rotation or color counts as changed.
    """

    added: int = Field(description="Elements new since the earlier model.")
    removed: int = Field(description="Elements of the earlier model that are gone.")
    changed: int = Field(
        description=(
            "Elements with the same id and part, now in another position, "
            "rotation or color."
        )
    )
    unchanged: int = Field(
        description="Elements of the same part and color in the same space."
    )
    voxels_filled: int = Field(
        description=(
            "Voxels, each one stud square and one plate tall, "
            "empty before and filled now."
        )
    )
    voxels_emptied: int = Field(description="Voxels filled before and empty now.")
    voxels_recolored: int = Field(
        description="Voxels filled in both models, in another color."
    )
    added_at: tuple[LineCount, ...] = Field(
        description="Added elements by the script line that placed them, most first."
    )
    changed_at: tuple[LineCount, ...] = Field(
        description="Changed elements by the script line that placed them, most first."
    )
    removed_at: tuple[LineCount, ...] = Field(
        description=(
            "Removed elements by the line of the earlier script that placed them; "
            "that line may have moved since."
        )
    )

    def describe(self) -> str:
        """Return the changes as text for people and agents."""
        if not (self.added or self.removed or self.changed):
            return (
                "since the last build: no changes "
                f"({plural(self.unchanged, 'element')})"
            )
        elements = (
            f"since the last build: {self.added} added, {self.removed} removed, "
            f"{self.changed} changed, {self.unchanged} unchanged"
        )
        voxels = (
            f"  voxels: {self.voxels_filled} filled, {self.voxels_emptied} emptied, "
            f"{self.voxels_recolored} recolored"
        )
        lines = [elements, voxels]
        for title, counts in (
            ("added at", self.added_at),
            ("changed at", self.changed_at),
            ("removed from the earlier script at", self.removed_at),
        ):
            if counts:
                lines.append(f"  {title}:")
                lines.extend(
                    f"    {count.line}: {plural(count.elements, 'element')}"
                    for count in counts[:_LISTED_LINES]
                )
                if len(counts) > _LISTED_LINES:
                    more = plural(len(counts) - _LISTED_LINES, "more line")
                    lines.append(f"    ... and {more}")
        return "\n".join(lines)


class BuildResult(BaseModel):
    """What a build produced."""

    model: Path = Field(description="The saved model file.")
    source_map: Path | None = Field(
        description="The saved source map, linking elements to script lines."
    )
    elements: int = Field(
        description="Elements in the model, with every instance unfolded."
    )
    size: tuple[float, float, float] | None = Field(
        default=None,
        description=(
            "Size of the model's bodies: x and y in studs, z in plates; "
            "null when the catalog can place none of its elements."
        ),
    )
    output: ScriptOutput = Field(description="What the build script printed.")
    changes: Changes | None = Field(
        description=(
            "What changed since the last build saved a model at the same path; "
            "null on the first build."
        )
    )
    report: Report | None = Field(
        description="The check report; null when checking is off."
    )
    images: tuple[Image, ...] = Field(
        description="Rendered images; empty when rendering is off or failed."
    )
    render_error: str | None = Field(
        default=None,
        description=(
            "Why the images failed to render; null when they rendered or rendering "
            "is off. The model, its source map and its report are saved regardless."
        ),
    )
    seconds: Timings

    def describe(self) -> str:
        """Return the result as text for people and agents."""
        saved = f"saved {self.model}: {plural(self.elements, 'element')}"
        if self.size is not None:
            x, y, z = self.size
            saved += f", {x:g} x {y:g} studs, {plural(z, 'plate')} tall"
        blocks = [saved]
        if self.changes is not None:
            blocks.append(self.changes.describe())
        if text := self.output.describe():
            blocks.append(text)
        if self.report is not None:
            blocks.append(format_report(self.report))
        blocks.extend(describe_images(self.images))
        if self.render_error is not None:
            blocks.append(f"not rendered: {self.render_error}")
        blocks.append(describe_timings(self.seconds))
        return "\n\n".join(blocks)


async def build(request: BuildRequest, session: Session) -> BuildResult:
    """Run a script in its own process, save its model and source map, check and render.

    When an earlier build saved a model at the same path, the result says what changed
    since, and the images mark the new and changed elements.

    A render that fails, for example for want of a browser, leaves the saved model and
    the report intact, and the result says why in ``render_error``.

    Raises:
        BrickyError: If the script is missing, fails, times out or returns no model, or
            a rule is unknown or given two levels.
    """
    settings = session.settings
    rules = await asyncio.to_thread(
        rule_levels, request.error, request.warn, request.ignore, settings
    )
    started = time.perf_counter()
    run = await run_script(request.script, settings)
    path = request.output or request.script.with_name(request.script.stem + SUFFIX)
    earlier = await asyncio.to_thread(_earlier, path)
    source_map = await asyncio.to_thread(_save, run, request.script, path)
    seconds = Timings(script=time.perf_counter() - started)
    size = await asyncio.to_thread(_size, run.model, session.catalog)

    changes = None
    changed: tuple[str, ...] = ()
    if earlier is not None:
        started = time.perf_counter()
        changes, changed = await asyncio.to_thread(
            _compare, earlier, run, session.catalog
        )
        seconds.changes = time.perf_counter() - started

    report = None
    if request.check:
        started = time.perf_counter()
        report = await asyncio.to_thread(
            run_check,
            run.model,
            provenance=run.provenance,
            rules=rules,
            max_diagnostics=request.max_diagnostics,
            session=session,
        )
        seconds.check = time.perf_counter() - started

    images: tuple[Image, ...] = ()
    render_error = None
    if request.render:
        started = time.perf_counter()
        try:
            images = await render_views(
                session,
                run.model,
                provenance=run.provenance,
                report=report,
                views=request.views,
                paths=view_paths(
                    path.with_name(model_stem(path) + ".png"), request.views
                ),
                changed=changed,
            )
        except BrickyError as error:
            render_error = str(error)
        seconds.render = time.perf_counter() - started
    return BuildResult(
        model=path,
        source_map=source_map,
        elements=run.model.element_count(),
        size=size,
        output=run.output,
        changes=changes,
        report=report,
        images=images,
        render_error=render_error,
        seconds=seconds,
    )


class ScriptRun(BaseModel):
    """A build script's model, its provenance and what the script printed."""

    model: Model
    provenance: Provenance | None
    output: ScriptOutput


async def run_script(script: Path, settings: Settings) -> ScriptRun:
    """Run a build script in a child process with the configured time and output limits.

    Raises:
        BrickyError: If the script is missing, fails, runs out of time or returns no
            model.
    """
    if not await asyncio.to_thread(script.is_file):
        message = f"no such build script: {script}"
        raise BrickyError(message)
    try:
        async with asyncio.timeout(settings.build_timeout):
            result, output, code = await _run_child(script, settings.output_limit)
    except TimeoutError:
        message = (
            f"{script} did not finish within {settings.build_timeout:g} s "
            "and was stopped"
        )
        raise BrickyError(message) from None
    if result is None:
        message = (
            f"{script}: the build process exited with code {code} "
            "before reporting a result"
        )
        raise BrickyError(_with_output(message, output))
    if result.failure is not None or result.model is None:
        raise BrickyError(_with_output(f"{script} failed: {result.failure}", output))
    return ScriptRun(model=result.model, provenance=result.provenance, output=output)


async def _run_child(
    script: Path, limit: int
) -> tuple[RunResult | None, ScriptOutput, int]:
    """Run the child process to its end and return its result, output and exit code.

    When the caller stops waiting, through a timeout or a cancelled request, the
    function kills the child before the cancellation goes on, so no build script
    outlives its command.
    """
    with TemporaryDirectory(prefix="bricky-") as scratch:
        result_path = Path(scratch) / "result.json"
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-P",
            "-m",
            "bricky.runner",
            str(script),
            str(result_path),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if (
            process.stdout is None or process.stderr is None
        ):  # pragma: no cover - pipes requested
            message = "could not capture the build script's output"
            raise BrickyError(message)
        try:
            (
                (stdout, stdout_truncated),
                (stderr, stderr_truncated),
            ) = await asyncio.gather(
                _read_capped(process.stdout, limit), _read_capped(process.stderr, limit)
            )
            code = await process.wait()
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        output = ScriptOutput(
            stdout=stdout, stderr=stderr, truncated=stdout_truncated or stderr_truncated
        )
        result = await asyncio.to_thread(_read_result, result_path)
    return result, output, code


def _read_result(path: Path) -> RunResult | None:
    """Return the child's result, or ``None`` if it exited before writing all of it."""
    try:
        return RunResult.model_validate_json(path.read_bytes())
    except (FileNotFoundError, ValidationError):
        return None


def _earlier(path: Path) -> tuple[Model, Provenance | None] | None:
    """Return the earlier build's model at ``path`` and its source map, if readable."""
    if not path.is_file():
        return None
    try:
        return read_model(path)
    except BrickyError:
        return None


def _compare(
    earlier: tuple[Model, Provenance | None], run: ScriptRun, catalog: Catalog
) -> tuple[Changes, tuple[str, ...]]:
    """Return what changed since the earlier model, and the uids of elements to mark.

    The marked elements are the new and changed ones, and only when some elements are
    unchanged: when nothing carried over, every element is new, and marking them all
    would say nothing.
    """
    before, before_provenance = earlier
    diff = diff_worlds(build_world(before, catalog), build_world(run.model, catalog))
    changes = Changes(
        added=len(diff.added),
        removed=len(diff.removed),
        changed=len(diff.changed),
        unchanged=diff.unchanged,
        voxels_filled=diff.filled,
        voxels_emptied=diff.emptied,
        voxels_recolored=diff.recolored,
        added_at=_by_line(run.model, run.provenance, diff.added),
        changed_at=_by_line(run.model, run.provenance, diff.changed),
        removed_at=_by_line(before, before_provenance, diff.removed),
    )
    marked = diff.added + diff.changed if diff.unchanged else ()
    return changes, marked


def _by_line(
    model: Model, provenance: Provenance | None, uids: Sequence[str]
) -> tuple[LineCount, ...]:
    """Count elements by the script line that placed each, most first.

    Lines with equal counts keep their placing order.
    """
    if provenance is None:
        return ()
    counts = Counter(
        str(source.site)
        for uid in uids
        if (source := provenance.trace(model, uid).source)
    )
    return tuple(
        LineCount(line=line, elements=count) for line, count in counts.most_common()
    )


def _save(run: ScriptRun, script: Path, path: Path) -> Path | None:
    """Save a model, and its source map when its provenance is known; return the map."""
    save_model(run.model, path)
    if run.provenance is None:
        return None
    return save_source_map(run.provenance, script=script, model_path=path)


async def _read_capped(stream: asyncio.StreamReader, limit: int) -> tuple[str, bool]:
    """Read a whole stream; return its first ``limit`` bytes and whether it had more."""
    kept = bytearray()
    truncated = False
    while chunk := await stream.read(65536):
        room = max(limit - len(kept), 0)
        kept += chunk[:room]
        truncated = truncated or len(chunk) > room
    return kept.decode(errors="replace"), truncated


def _with_output(message: str, output: ScriptOutput) -> str:
    text = output.describe()
    return f"{message}\n\n{text}" if text else message


def _size(model: Model, catalog: Catalog) -> tuple[float, float, float] | None:
    """The size of a model's bodies, in studs, studs and plates."""
    elements = build_world(model, catalog).elements
    if not elements:
        return None
    size = Box.bounding(element.bounds for element in elements).size
    return to_studs(size.x), to_studs(size.y), to_plates(size.z)
