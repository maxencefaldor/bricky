"""The service layer: every command, defined once.

Each command is a request model plus an async function. The CLI runs them, the MCP server awaits
them, and Python callers can do either, so every front-end shares one set of argument names,
defaults and descriptions. A :class:`Session` carries the settings and a warm renderer between
commands.

:func:`run_script` runs each build script in a child process (see :mod:`bricky.runner`), within a
timeout, and captures what the script prints.
"""

import asyncio
import sys
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final, Self

from platformdirs import user_cache_path
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import CliPositionalArg

from bricky.analysis import build_world, diff_worlds
from bricky.catalog import (
    IMPORTED_CATALOG,
    SAMPLE_CATALOG,
    Catalog,
    CatalogPart,
    Color,
    ColorType,
    ConnectorKind,
    Family,
    Part,
    catalog_path,
    load_catalog,
)
from bricky.catalog.bricklink import DOWNLOAD_PAGE, read_downloads
from bricky.catalog.importing import Coverage, Progress, import_catalog
from bricky.catalog.ldraw import Library
from bricky.check import check_model
from bricky.diagnostics import Code, Report, render_report
from bricky.errors import BrickyError
from bricky.files import (
    SUFFIX,
    load_model,
    load_source_map,
    model_stem,
    save_model,
    save_source_map,
    write_file,
)
from bricky.geometry import AXES, DOWN, ORIGIN, UP, Box, Vector
from bricky.model import Element, Model
from bricky.passes import installed_codes, installed_passes
from bricky.provenance import Provenance
from bricky.render import Clip, Renderer, View, build_scene, write_html
from bricky.runner import RunResult
from bricky.settings import Settings
from bricky.units import STUD, to_plates, to_studs

_PROFILE_HELP: Final = (
    "Profile to run, such as 'digital' or 'physical'; defaults to the configured one."
)
_PASSES_HELP: Final = "Pass names to run instead of a profile."
_MAX_DIAGNOSTICS_HELP: Final = "Maximum diagnostics to return; defaults to the configured cap."
_VIEWS_HELP: Final = (
    "Views to draw: sheet (perspective, front, right and top on one image), perspective (from the "
    "south-east), perspective-south-west, perspective-north-west, perspective-north-east, front, "
    "back, left, right or top."
)
_WIDTH: Final = 1600
_HEIGHT: Final = 1200
_LISTED_LINES: Final = 10
_LISTED_CATEGORIES: Final = 25
_LISTED_DISAGREEMENTS: Final = 40
_FALLBACK_COLOR: Final = 86
"""Light Bluish Gray: the color `catalog show` draws a part in when the catalog lists none."""
PART_PICTURES: Final = user_cache_path("bricky", appauthor=False) / "parts"
"""Where `catalog show --render` draws parts unless told otherwise: out of every workspace."""


class Session:
    """Settings and a warm renderer, shared by the commands of one process.

    The browser launch is the slow part of a render, so a session launches the browser on the
    first render and keeps it until :meth:`close`. A session is an async context manager.
    """

    def __init__(self, settings: Settings | None = None, catalog: Catalog | None = None) -> None:
        self.settings = settings or Settings()
        self.catalog = catalog or load_catalog(catalog_path(self.settings))
        self._renderer: Renderer | None = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def renderer(self) -> Renderer:
        """Return the session's renderer, starting the browser on first use."""
        async with self._lock:
            if self._renderer is None:
                renderer = Renderer(self.settings.render_browser)
                await renderer.start()
                self._renderer = renderer
            return self._renderer

    async def close(self) -> None:
        """Close the renderer's browser, if it was started."""
        if self._renderer is not None:
            await self._renderer.close()
            self._renderer = None


# ---------------------------------------------------------------------------------------------
# Results shared by several commands


class Image(BaseModel):
    """A rendered picture of a model."""

    view: View
    path: Path = Field(description="The PNG file.")
    width: int
    height: int


class ScriptOutput(BaseModel):
    """What a build script printed."""

    stdout: str = Field(default="", description="Standard output, up to the configured limit.")
    stderr: str = Field(default="", description="Standard error, up to the configured limit.")
    truncated: bool = Field(default=False, description="Whether either stream was truncated.")

    def describe(self) -> str:
        """Return the output as text, or an empty string when the script printed nothing."""
        parts = []
        if self.stdout.strip():
            parts.append("script output:\n" + _indent(self.stdout.rstrip()))
        if self.stderr.strip():
            parts.append("script errors:\n" + _indent(self.stderr.rstrip()))
        if self.truncated:
            parts.append("(output truncated at the configured limit)")
        return "\n\n".join(parts)


class Timings(BaseModel):
    """Seconds spent in each stage of a command."""

    script: float = 0.0
    changes: float = 0.0
    check: float = 0.0
    render: float = 0.0


# ---------------------------------------------------------------------------------------------
# check


class CheckRequest(BaseModel):
    """Check a model file and report diagnostics."""

    model: CliPositionalArg[Path] = Field(description="Path to a .bricky.json model file.")
    profile: str | None = Field(default=None, description=_PROFILE_HELP)
    passes: list[str] | None = Field(default=None, description=_PASSES_HELP)
    max_diagnostics: int | None = Field(default=None, ge=1, description=_MAX_DIAGNOSTICS_HELP)


async def check(request: CheckRequest, session: Session) -> Report:
    """Check a model file, naming script lines when its source map is current.

    Raises:
        BrickyError: If the file is missing or invalid, or the profile is unknown.
    """
    model, provenance = await asyncio.to_thread(_load, request.model)
    return await asyncio.to_thread(
        _check,
        model,
        provenance=provenance,
        profile=request.profile,
        passes=request.passes,
        max_diagnostics=request.max_diagnostics,
        session=session,
    )


# ---------------------------------------------------------------------------------------------
# build


class BuildRequest(BaseModel):
    """Run a build script, save its model, check it and render it."""

    script: CliPositionalArg[Path] = Field(
        description="Python file defining build(), which returns a ModelBuilder or a Model."
    )
    output: Path | None = Field(
        default=None, description="Where to save the model; defaults to <script>.bricky.json."
    )
    check: bool = Field(default=True, description="Check the model after building it.")
    render: bool = Field(default=True, description="Render the model after checking it.")
    views: list[View] = Field(default=[View.SHEET], description=_VIEWS_HELP)
    profile: str | None = Field(default=None, description=_PROFILE_HELP)
    passes: list[str] | None = Field(default=None, description=_PASSES_HELP)
    max_diagnostics: int | None = Field(default=None, ge=1, description=_MAX_DIAGNOSTICS_HELP)


class LineCount(BaseModel):
    """Elements counted by the build-script line that placed them."""

    line: str = Field(description="Script file, line and enclosing function.")
    elements: int


class Changes(BaseModel):
    """What changed since the last build saved a model at the same path.

    The counts unfold every instance. Elements match by part, color and the space they take,
    whatever their ids, so renumbered elements count as unchanged. An element with the same id and
    part in another position, rotation or color counts as changed.
    """

    added: int = Field(description="Elements new since the earlier model.")
    removed: int = Field(description="Elements of the earlier model that are gone.")
    changed: int = Field(
        description="Elements with the same id and part, now in another position, rotation or "
        "color."
    )
    unchanged: int = Field(description="Elements of the same part and color in the same space.")
    voxels_filled: int = Field(
        description="Voxels, each one stud square and one plate tall, empty before and filled now."
    )
    voxels_emptied: int = Field(description="Voxels filled before and empty now.")
    voxels_recolored: int = Field(description="Voxels filled in both models, in another color.")
    added_at: tuple[LineCount, ...] = Field(
        description="Added elements by the script line that placed them, most first."
    )
    changed_at: tuple[LineCount, ...] = Field(
        description="Changed elements by the script line that placed them, most first."
    )
    removed_at: tuple[LineCount, ...] = Field(
        description="Removed elements by the line of the earlier script that placed them; that "
        "line may have moved since."
    )

    def describe(self) -> str:
        """Return the changes as text for people and agents."""
        if not (self.added or self.removed or self.changed):
            return f"since the last build: no changes ({_count(self.unchanged, 'element')})"
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
                    f"    {count.line}: {_count(count.elements, 'element')}"
                    for count in counts[:_LISTED_LINES]
                )
                if len(counts) > _LISTED_LINES:
                    lines.append(f"    ... and {len(counts) - _LISTED_LINES} more lines")
        return "\n".join(lines)


class BuildResult(BaseModel):
    """What a build produced."""

    model: Path = Field(description="The saved model file.")
    source_map: Path | None = Field(
        description="The saved source map, linking elements to script lines."
    )
    elements: int = Field(description="Elements in the model, with every instance unfolded.")
    size: tuple[float, float, float] | None = Field(
        default=None,
        description="Size of the model's bodies: x and y in studs, z in plates; null when the "
        "catalog can place none of its elements.",
    )
    output: ScriptOutput = Field(description="What the build script printed.")
    changes: Changes | None = Field(
        description="What changed since the last build saved a model at the same path; null on "
        "the first build."
    )
    report: Report | None = Field(description="The check report; null when checking is off.")
    images: tuple[Image, ...] = Field(description="Rendered pictures; empty when rendering is off.")
    seconds: Timings

    def describe(self) -> str:
        """Return the result as text for people and agents."""
        saved = f"saved {self.model}: {_count(self.elements, 'element')}"
        if self.size is not None:
            x, y, z = self.size
            saved += f", {x:g} x {y:g} studs, {_count(z, 'plate')} tall"
        blocks = [saved]
        if self.changes is not None:
            blocks.append(self.changes.describe())
        if text := self.output.describe():
            blocks.append(text)
        if self.report is not None:
            blocks.append(render_report(self.report))
        blocks.extend(_describe_images(self.images))
        blocks.append(_describe_timings(self.seconds))
        return "\n\n".join(blocks)


async def build(request: BuildRequest, session: Session) -> BuildResult:
    """Run a build script in its own process, save its model and source map, check and render.

    When an earlier build saved a model at the same path, the result says what changed since,
    and the pictures mark the new and changed elements.

    Raises:
        BrickyError: If the script is missing, fails, times out or returns no model, or if the
            render fails.
    """
    settings = session.settings
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
        changes, changed = await asyncio.to_thread(_compare, earlier, run, session.catalog)
        seconds.changes = time.perf_counter() - started

    report = None
    if request.check:
        started = time.perf_counter()
        report = await asyncio.to_thread(
            _check,
            run.model,
            provenance=run.provenance,
            profile=request.profile,
            passes=request.passes,
            max_diagnostics=request.max_diagnostics,
            session=session,
        )
        seconds.check = time.perf_counter() - started

    images: tuple[Image, ...] = ()
    if request.render:
        started = time.perf_counter()
        images = await _render(
            session,
            run.model,
            provenance=run.provenance,
            report=report,
            views=request.views,
            paths=_view_paths(path.with_name(model_stem(path) + ".png"), request.views),
            changed=changed,
        )
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
        seconds=seconds,
    )


class ScriptRun(BaseModel):
    """A build script's model, its provenance and what the script printed."""

    model: Model
    provenance: Provenance | None
    output: ScriptOutput


async def run_script(script: Path, settings: Settings) -> ScriptRun:
    """Run a build script in a child process, within the configured time and output limits.

    Raises:
        BrickyError: If the script is missing, fails, runs out of time or returns no model.
    """
    if not await asyncio.to_thread(script.is_file):
        message = f"no such build script: {script}"
        raise BrickyError(message)
    try:
        async with asyncio.timeout(settings.build_timeout):
            result, output, code = await _run_child(script, settings.output_limit)
    except TimeoutError:
        message = f"{script} did not finish within {settings.build_timeout:g} s and was stopped"
        raise BrickyError(message) from None
    if result is None:
        message = f"{script}: the build process exited with code {code} before reporting a result"
        raise BrickyError(_with_output(message, output))
    if result.failure is not None or result.model is None:
        raise BrickyError(_with_output(f"{script} failed: {result.failure}", output))
    return ScriptRun(model=result.model, provenance=result.provenance, output=output)


async def _run_child(script: Path, limit: int) -> tuple[RunResult | None, ScriptOutput, int]:
    """Run the child process to its end and return its result, its output and its exit code.

    When the caller stops waiting, through a timeout or a cancelled request, the function kills
    the child before the cancellation goes on, so no build script outlives its command.
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
        if process.stdout is None or process.stderr is None:  # pragma: no cover - pipes requested
            message = "could not capture the build script's output"
            raise BrickyError(message)
        try:
            (stdout, stdout_truncated), (stderr, stderr_truncated) = await asyncio.gather(
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
    """Return the child's result, or ``None`` when the child exited before writing all of it."""
    try:
        return RunResult.model_validate_json(path.read_bytes())
    except FileNotFoundError, ValidationError:
        return None


def _earlier(path: Path) -> tuple[Model, Provenance | None] | None:
    """Return the model an earlier build saved at ``path`` and its source map, if readable."""
    if not path.is_file():
        return None
    try:
        return _load(path)
    except BrickyError:
        return None


def _compare(
    earlier: tuple[Model, Provenance | None], run: ScriptRun, catalog: Catalog
) -> tuple[Changes, tuple[str, ...]]:
    """Return what changed since the earlier model, and the uids of the elements to mark.

    The marked elements are the new and changed ones, and only when some elements are unchanged:
    when nothing carried over, every element is new, and marking them all would say nothing.
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
    """Count elements by the script line that placed each: most first, ties in placing order."""
    if provenance is None:
        return ()
    counts = Counter(
        str(source.site) for uid in uids if (source := provenance.trace(model, uid).source)
    )
    return tuple(LineCount(line=line, elements=count) for line, count in counts.most_common())


def _save(run: ScriptRun, script: Path, path: Path) -> Path | None:
    """Save a built model, and its source map when its provenance is known; return the map."""
    save_model(run.model, path)
    if run.provenance is None:
        return None
    return save_source_map(run.provenance, script=script, model_path=path)


async def _read_capped(stream: asyncio.StreamReader, limit: int) -> tuple[str, bool]:
    """Read a stream to its end, keep its first ``limit`` bytes, and say whether it had more."""
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


# ---------------------------------------------------------------------------------------------
# render


class RenderRequest(BaseModel):
    """Render pictures of a model file."""

    model: CliPositionalArg[Path] = Field(description="Path to a .bricky.json model file.")
    views: list[View] = Field(default=[View.SHEET], description=_VIEWS_HELP)
    highlight: list[str] = Field(
        default_factory=list,
        description=(
            "Elements to highlight, drawing the rest faintly: uid patterns such as 'lintel*', or "
            "'@' and a function, file or file:line of the build script, such as '@horseshoe'."
        ),
    )
    clip: list[str] = Field(
        default_factory=list,
        description="Clip the model to look inside: 'z<130' keeps what lies below 130 plates; x "
        "and y are in studs.",
    )
    check: bool = Field(default=True, description="Mark the elements that diagnostics name.")
    width: int = Field(default=_WIDTH, ge=200, le=4096, description="Image width in pixels.")
    height: int = Field(default=_HEIGHT, ge=200, le=4096, description="Image height in pixels.")
    output: Path | None = Field(
        default=None,
        description="Image file to write; with several views, each file name gets the view's "
        "name added. Defaults to <model>.<view>.png beside the model, so renders keep the "
        "picture a build drew.",
    )
    html: bool = Field(
        default=False,
        description="Also write a standalone HTML viewer people can orbit and clip, highlighted "
        "like the pictures.",
    )


class RenderResult(BaseModel):
    """Pictures of a model."""

    images: tuple[Image, ...]
    html: Path | None = Field(description="The standalone viewer, when requested.")
    report: Report | None = Field(
        description="The check report whose diagnostics the pictures mark; null when checking is "
        "off."
    )
    seconds: Timings

    def describe(self) -> str:
        """Return the result as text for people and agents."""
        blocks = list(_describe_images(self.images))
        if self.html is not None:
            blocks.append(f"viewer: {self.html}")
        if self.report is not None:
            blocks.append(
                f"marked {self.report.errors} errors and {self.report.warnings} warnings "
                f"from profile {self.report.profile or 'explicit passes'}"
            )
        blocks.append(_describe_timings(self.seconds))
        return "\n\n".join(blocks)


async def render(request: RenderRequest, session: Session) -> RenderResult:
    """Render pictures of a model file.

    Raises:
        BrickyError: If the file is missing or invalid, a selector or clip is invalid, or the
            render fails.
    """
    model, provenance = await asyncio.to_thread(_load, request.model)
    clips = [Clip.parse(text) for text in request.clip]
    seconds = Timings()
    report = None
    if request.check:
        started = time.perf_counter()
        report = await asyncio.to_thread(
            _check,
            model,
            provenance=provenance,
            profile=None,
            passes=None,
            max_diagnostics=None,
            session=session,
        )
        seconds.check = time.perf_counter() - started
    started = time.perf_counter()
    if request.output is None:
        stem = model_stem(request.model)
        paths = [request.model.with_name(f"{stem}.{view.value}.png") for view in request.views]
        viewer = request.model.with_name(stem + ".html")
    else:
        paths = _view_paths(request.output, request.views)
        viewer = request.output.with_suffix(".html")
    images = await _render(
        session,
        model,
        provenance=provenance,
        report=report,
        views=request.views,
        paths=paths,
        highlight=request.highlight,
        clips=clips,
        size=(request.width, request.height),
    )
    html = None
    if request.html:
        scene = await asyncio.to_thread(
            build_scene,
            model,
            session.catalog,
            provenance=provenance,
            report=report,
            highlight=request.highlight,
            clips=clips,
            cull=False,
        )
        html = await asyncio.to_thread(write_html, scene, viewer)
    seconds.render = time.perf_counter() - started
    return RenderResult(images=images, html=html, report=report, seconds=seconds)


async def _render(  # noqa: PLR0913 - keyword-only options, one per concern
    session: Session,
    model: Model,
    *,
    provenance: Provenance | None,
    report: Report | None,
    views: Sequence[View],
    paths: Sequence[Path],
    highlight: Sequence[str] = (),
    clips: Sequence[Clip] = (),
    changed: Sequence[str] = (),
    size: tuple[int, int] = (_WIDTH, _HEIGHT),
) -> tuple[Image, ...]:
    """Draw ``views`` of a model and write each to the path at the same position in ``paths``."""
    scene = await asyncio.to_thread(
        build_scene,
        model,
        session.catalog,
        provenance=provenance,
        report=report,
        highlight=highlight,
        clips=clips,
        changed=changed,
    )
    renderer = await session.renderer()
    width, height = size
    pictures = await renderer.render(scene, views, width=width, height=height)
    await asyncio.to_thread(_write_images, paths, pictures)
    return tuple(
        Image(view=view, path=path, width=width, height=height)
        for view, path in zip(views, paths, strict=True)
    )


def _view_paths(base: Path, views: Sequence[View]) -> list[Path]:
    """One image path per view: ``base`` for a single view, else ``base`` plus each view's name."""
    if len(views) == 1:
        return [base]
    return [base.with_name(f"{base.stem}.{view.value}{base.suffix}") for view in views]


# ---------------------------------------------------------------------------------------------
# parts and colors


class PartsRequest(BaseModel):
    """Search the parts catalog."""

    query: CliPositionalArg[str] = Field(
        default="",
        description="Words to match against ids, names, categories and sizes, such as "
        "'plate 2x4' (quoted).",
    )
    limit: int = Field(default=20, ge=1, le=500, description="Maximum number of parts to return.")
    shapeless: bool = Field(
        default=False,
        description="Also list the parts without a shape, which cannot be placed.",
    )


class PartInfo(BaseModel):
    """A catalog part, summarized for choosing parts."""

    id: str = Field(description="BrickLink item number.")
    name: str = Field(description="BrickLink item name.")
    category: str | None = Field(default=None, description="BrickLink category.")
    family: Family | None = Field(
        default=None,
        description="The family that turns the part's shape into geometry; null without a shape.",
    )
    footprint: tuple[int, int] | None = Field(
        default=None, description="Studs along x, then along y, when the part is unrotated."
    )
    height: float | None = Field(default=None, description="Body height in plates.")
    studs: int | None = Field(default=None, description="Number of studs, on top and on sides.")
    note: str = Field(
        default="", description="How the part sits when placed unrotated, where that matters."
    )
    base: str | None = Field(
        default=None, description="For a printed part, the part it is printed on."
    )


class PartsResult(BaseModel):
    """Parts matching a search."""

    parts: tuple[PartInfo, ...]
    total: int = Field(description="Matching parts before the limit applied.")

    def describe(self) -> str:
        """Return the result as a table, with each part's note under it."""
        table: list[tuple[list[str], str]] = []
        for part in self.parts:
            if part.family is None:
                table.append(([part.id, part.name, "no shape: cannot be placed"], ""))
                continue
            x, y = part.footprint or (0, 0)
            cells = [
                part.id,
                part.name,
                part.family,
                f"{x} x {y}",
                _count(part.height or 0, "plate"),
                _count(part.studs or 0, "stud"),
            ]
            table.append((cells, part.note))
        header = ["id", "name", "family", "x by y", "height", "studs"]
        widths = [
            max([len(title), *(len(cells[i]) for cells, _ in table if len(cells) > i)])
            for i, title in enumerate(header)
        ]
        rows = [_row(header, widths)] if table else []
        for cells, note in table:
            rows.append(_row(cells, widths))
            if note:
                rows.append(" " * (widths[0] + 2) + note)
        shown = f"{len(self.parts)} of {self.total:,} matching parts"
        rows.append(shown + ("; --limit shows more" if len(self.parts) < self.total else ""))
        return "\n".join(rows)


async def parts(request: PartsRequest, session: Session) -> PartsResult:
    """Search the parts catalog."""
    catalog = session.catalog
    hits = await asyncio.to_thread(catalog.search_parts, request.query, shapeless=request.shapeless)
    shown = hits[: request.limit]
    infos = await asyncio.to_thread(lambda: tuple(_part_info(catalog, entry) for entry in shown))
    return PartsResult(parts=infos, total=len(hits))


class ColorsRequest(BaseModel):
    """Search the catalog's colors."""

    query: CliPositionalArg[str] = Field(
        default="",
        description="Words to match against ids, names and types, such as 'gray', or an RGB "
        "value, such as '#F2CD37', to list the nearest colors.",
    )


class ColorInfo(BaseModel):
    """A catalog color."""

    id: int = Field(description="BrickLink color id.")
    name: str = Field(description="BrickLink color name.")
    type: ColorType
    rgb: str = Field(description="Display color used by renders.")


class ColorsResult(BaseModel):
    """Colors matching a search."""

    colors: tuple[ColorInfo, ...]

    def describe(self) -> str:
        """Return the result as a table."""
        rows = [
            f"{color.id:>4}  {color.name:<22} {color.type:<12} {color.rgb}" for color in self.colors
        ]
        rows.append(_count(len(self.colors), "color"))
        return "\n".join(rows)


async def colors(request: ColorsRequest, session: Session) -> ColorsResult:
    """Search the catalog's colors."""
    found = await asyncio.to_thread(session.catalog.search_colors, request.query)
    return ColorsResult(colors=tuple(_color_info(color) for color in found))


# ---------------------------------------------------------------------------------------------
# catalog


class CatalogImportRequest(BaseModel):
    """Import the catalog: parts and colors from BrickLink, shapes from names and LDraw."""

    bricklink: Path | None = Field(
        default=None,
        description="Folder holding BrickLink's catalog downloads as XML, from "
        f"{DOWNLOAD_PAGE}: Catalog Items (Parts), Colors, Categories and Codes, under any file "
        "names. Without it, parts come from LDraw and colors from bricky's sample.",
    )
    ldraw: Path | None = Field(
        default=None,
        description="LDraw parts library folder, holding parts and p, such as an unzipped "
        "complete.zip from library.ldraw.org; LDraw shapes the parts that no name describes.",
    )
    output: Path | None = Field(
        default=None,
        description="Catalog file to write; defaults to bricky's data folder, where bricky "
        "looks for it.",
    )


class CatalogImportResult(BaseModel):
    """What an import wrote, where each part's shape came from, and what the checks found."""

    catalog: Path = Field(description="The catalog file written.")
    coverage: Coverage
    in_use: bool = Field(description="Whether bricky uses this catalog from now on.")

    def describe(self) -> str:
        """Return the result as text."""
        coverage = self.coverage
        unshaped = coverage.parts - coverage.shaped
        lines = [
            f"imported {coverage.parts:,} parts and {coverage.colors:,} colors from:",
            *(f"  {source}" for source in coverage.sources),
            "",
            f"{coverage.shaped:,} parts have a shape and can be placed; {unshaped:,} have none",
            "shapes by source: " + _pairs(coverage.by_source),
            "shapes by family: " + _pairs(coverage.by_family),
        ]
        _section(
            lines,
            "parts without a shape, by category (most first)",
            coverage.unshaped_by_category,
        )
        _section(
            lines, "LDraw files that could not be converted, by reason", coverage.ldraw_failures
        )
        if coverage.compared:
            disagreements = coverage.disagreements
            lines += [
                "",
                f"compared {coverage.compared:,} named shapes with LDraw: "
                + _count(len(disagreements), "disagreement"),
                *(f"  {disagreement}" for disagreement in disagreements[:_LISTED_DISAGREEMENTS]),
            ]
            hidden = len(disagreements) - _LISTED_DISAGREEMENTS
            if hidden > 0:
                lines.append(f"  ... and {hidden} more, in the JSON output")
        if coverage.skipped_colors:
            lines += ["", "colors left out:", *(f"  {color}" for color in coverage.skipped_colors)]
        lines += ["", f"wrote {self.catalog}"]
        if not self.in_use:
            lines.append(
                "bricky does not use it yet: set catalog to this file in [tool.bricky] or "
                "BRICKY_CATALOG"
            )
        return "\n".join(lines)


async def catalog_import(
    request: CatalogImportRequest, session: Session, progress: Progress | None = None
) -> CatalogImportResult:
    """Import the catalog from BrickLink's downloads, an LDraw library, or both.

    Args:
        request: The sources and where to write.
        session: The session, whose settings say which catalog bricky uses.
        progress: Receives how many parts the import has looked at, out of how many.

    Raises:
        BrickyError: If no source is given, a source is missing or invalid, or the file cannot be
            written.
    """
    bricklink = None
    if request.bricklink is not None:
        bricklink = await asyncio.to_thread(read_downloads, request.bricklink)
    ldraw = None if request.ldraw is None else await asyncio.to_thread(Library, request.ldraw)
    catalog, coverage = await asyncio.to_thread(import_catalog, bricklink, ldraw, progress)
    output = request.output or IMPORTED_CATALOG
    await asyncio.to_thread(write_file, output, catalog.dump())
    in_use = catalog_path(session.settings).resolve() == output.resolve()
    return CatalogImportResult(catalog=output, coverage=coverage, in_use=in_use)


class CatalogStatusRequest(BaseModel):
    """Show which catalog bricky uses and what it holds."""


class CatalogStatusResult(BaseModel):
    """The catalog bricky uses."""

    catalog: Path = Field(description="The catalog file.")
    source: str
    sample: bool = Field(description="Whether the catalog is the small sample shipped with bricky.")
    parts: int
    shaped: int = Field(description="Parts with a shape, which can be placed.")
    printed: int = Field(description="Printed parts shaped like the part they are printed on.")
    colors: int
    by_family: dict[str, int] = Field(description="Shaped parts by family.")

    def describe(self) -> str:
        """Return the result as text."""
        counts = (
            f"{self.parts:,} parts, {self.shaped:,} with a shape ({self.printed:,} printed), "
            f"{self.colors:,} colors"
        )
        lines = [
            f"catalog: {self.catalog}",
            f"source: {self.source}",
            counts,
            *(f"  {family}: {count:,}" for family, count in self.by_family.items()),
        ]
        if self.sample:
            lines.append(
                "the sample shipped with bricky holds a small set of parts; "
                "`bricky catalog import <folder of BrickLink downloads>` imports every part"
            )
        return "\n".join(lines)


async def catalog_status(request: CatalogStatusRequest, session: Session) -> CatalogStatusResult:  # noqa: ARG001 - every command takes its request
    """Describe the catalog bricky uses."""
    catalog = session.catalog
    path = catalog_path(session.settings)
    families: Counter[str] = Counter()
    printed = 0
    for entry in await asyncio.to_thread(lambda: catalog.entries):
        shape = catalog.shape(entry.id)
        if shape is not None:
            families[shape.family.value] += 1
            printed += entry.base is not None
    return CatalogStatusResult(
        catalog=path,
        source=catalog.source,
        sample=path == SAMPLE_CATALOG,
        parts=len(catalog),
        shaped=families.total(),
        printed=printed,
        colors=len(catalog.colors),
        by_family=dict(families.most_common()),
    )


class CatalogShowRequest(BaseModel):
    """Show everything the catalog knows about one part."""

    part: CliPositionalArg[str] = Field(description="BrickLink item number, such as '3001'.")
    render: bool = Field(
        default=False, description="Also draw the part, in the first color it comes in."
    )
    output: Path | None = Field(
        default=None,
        description="Image file for the drawing; defaults to <part>.png in bricky's cache folder, "
        "outside the workspace.",
    )


class CatalogShowResult(BaseModel):
    """One catalog part: BrickLink's facts, and the geometry bricky generates for it."""

    part: CatalogPart
    info: PartInfo
    colors: tuple[str, ...] = Field(description="Names of the colors the part comes in.")
    anti_studs: int | None = Field(description="Number of anti-studs; null without a shape.")
    connectors: tuple[str, ...] = Field(
        default=(),
        description="Where the part's studs and anti-studs are, as text: maps of its top and its "
        "underside, north up, then the connectors off those maps.",
    )
    heights: tuple[str, ...] = Field(
        default=(),
        description="How tall the part stands over the center of each stud square, in plates, as "
        "a map north up; empty when the top is flat.",
    )
    images: tuple[Image, ...] = ()

    def describe(self) -> str:
        """Return the result as text."""
        part, info = self.part, self.info
        lines = [f"{part.id}: {part.name}", f"category: {part.category or 'none'}"]
        if part.alternates:
            lines.append(f"other numbers: {', '.join(part.alternates)}")
        if part.base:
            lines.append(f"printed on: {part.base}, whose shape it has")
        if info.family is None:
            lines.append("shape: none, so it cannot be placed")
        else:
            x, y = info.footprint or (0, 0)
            lines.append(
                f"shape: {info.family}, {x} x {y} studs (x by y, unrotated), "
                f"{_count(info.height or 0, 'plate')} tall, {_count(info.studs or 0, 'stud')}, "
                f"{_count(self.anti_studs or 0, 'anti-stud')}"
            )
            if info.note:
                lines.append(f"  {info.note}")
            lines.extend(self.connectors)
            lines.extend(self.heights)
        if self.colors:
            lines.append(f"colors ({len(self.colors)}): {', '.join(self.colors)}")
        lines.extend(_describe_images(self.images))
        return "\n".join(lines)


async def catalog_show(request: CatalogShowRequest, session: Session) -> CatalogShowResult:
    """Describe one catalog part, and draw it when asked.

    Raises:
        BrickyError: If the catalog does not list the part, or it has no shape to draw.
    """
    catalog = session.catalog
    entry = catalog.entry(request.part)
    if entry is None:
        message = f"the catalog has no part {request.part!r}; search it with `bricky parts <words>`"
        raise BrickyError(message)
    part = catalog.part(entry.id)
    names = tuple(
        color.name for color_id in entry.colors if (color := catalog.color(color_id)) is not None
    )
    images: tuple[Image, ...] = ()
    if request.render:
        if part is None:
            message = f"part {entry.id} has no shape to draw"
            raise BrickyError(message)
        color = next(iter(entry.colors), _FALLBACK_COLOR)
        model = Model(name=entry.id, elements=(Element(id=entry.id, part=entry.id, color=color),))
        path = request.output or PART_PICTURES / f"{entry.id}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        images = await _render(
            session, model, provenance=None, report=None, views=[View.SHEET], paths=[path]
        )
    return CatalogShowResult(
        part=entry,
        info=_part_info(catalog, entry),
        colors=names,
        anti_studs=None
        if part is None
        else sum(connector.kind is ConnectorKind.ANTI_STUD for connector in part.connectors),
        connectors=() if part is None else _connector_maps(part),
        heights=() if part is None else _heights(part),
        images=images,
    )


def _connector_maps(part: Part) -> tuple[str, ...]:
    """Maps of a part's top studs and underside anti-studs, north up, and its other connectors.

    Each map has one character per stud square of the footprint: ``o`` where a stud stands, or an
    anti-stud opens, at the square's center, and ``.`` elsewhere.
    """
    width, length = part.footprint
    top: set[tuple[int, int]] = set()
    underside: set[tuple[int, int]] = set()
    others: list[str] = []
    for connector in part.connectors:
        position = connector.position
        square = ((position.x - STUD // 2) // STUD, (position.y - STUD // 2) // STUD)
        on_grid = position.x % STUD == STUD // 2 and position.y % STUD == STUD // 2
        if on_grid and connector.normal == UP and position.z == part.size.z:
            top.add(square)
        elif on_grid and connector.normal == DOWN and position.z == 0:
            underside.add(square)
        else:
            kind = "stud" if connector.kind is ConnectorKind.STUD else "anti-stud"
            facing = next(name for name, axis in AXES.items() if axis == connector.normal)
            others.append(
                f"  {kind} facing {facing} at x {to_studs(position.x):g}, "
                f"y {to_studs(position.y):g}, z {to_plates(position.z):g}"
            )

    def drawn(squares: set[tuple[int, int]]) -> list[str]:
        return [
            "    " + " ".join("o" if (x, y) in squares else "." for x in range(width))
            for y in reversed(range(length))
        ]

    lines = ["top studs, north up:", *drawn(top), "underside anti-studs, north up:"]
    lines += drawn(underside)
    if others:
        lines += ["other connectors:", *others]
    return tuple(lines)


def _heights(part: Part) -> tuple[str, ...]:
    """A map of how tall a part stands over each stud square's center, north up; empty if flat."""
    width, length = part.footprint

    def top(x: int, y: int) -> int:
        center = Vector(x * STUD + STUD // 2, y * STUD + STUD // 2, 0)
        return next(
            (
                z + 1
                for z in reversed(range(part.size.z))
                if any(solid.contains(Vector(center.x, center.y, z)) for solid in part.solids)
            ),
            0,
        )

    tops = [[f"{to_plates(top(x, y)):.3g}" for x in range(width)] for y in reversed(range(length))]
    if all(cell == tops[0][0] for row in tops for cell in row):
        return ()
    span = max(len(cell) for row in tops for cell in row)
    return (
        "height over each square in plates, north up:",
        *("    " + " ".join(cell.rjust(span) for cell in row) for row in tops),
    )


class CatalogVerifyRequest(BaseModel):
    """Generate the geometry of every part with a shape and check it."""


class CatalogVerifyResult(BaseModel):
    """Parts whose geometry breaks a promise every family makes."""

    checked: int = Field(description="Parts whose geometry the command generated and checked.")
    problems: tuple[str, ...] = Field(description="Each problem, naming its part.")

    def describe(self) -> str:
        """Return the result as text."""
        lines = [
            *self.problems,
            f"checked {self.checked:,} parts: {_count(len(self.problems), 'problem')}",
        ]
        return "\n".join(lines)


async def catalog_verify(request: CatalogVerifyRequest, session: Session) -> CatalogVerifyResult:  # noqa: ARG001 - every command takes its request
    """Generate the geometry of every part with a shape and check what every family promises.

    A part's body fills its bounding box from the origin; anti-studs sit on its bottom face,
    pointing down and inside its footprint; studs stand on its top face or on a side face; and no
    two connectors of one kind share a position and a direction.
    """
    return await asyncio.to_thread(_verify, session.catalog)


# ---------------------------------------------------------------------------------------------
# passes and explain


class PassesRequest(BaseModel):
    """List the installed check passes and the profiles that run them."""


class PassInfo(BaseModel):
    """An installed pass."""

    name: str
    summary: str
    codes: tuple[str, ...] = Field(description="Codes the pass can report.")


class PassesResult(BaseModel):
    """Installed passes and configured profiles."""

    installed: tuple[PassInfo, ...]
    profiles: dict[str, tuple[str, ...]] = Field(description="Pass names run by each profile.")
    default_profile: str

    def describe(self) -> str:
        """Return the result as text."""
        installed = {info.name for info in self.installed}
        table = [[info.name, ", ".join(info.codes), info.summary] for info in self.installed]
        widths = [max((len(cells[i]) for cells in table), default=0) for i in range(2)]
        rows = [_row(cells, widths) for cells in table]
        rows.append("")
        for profile, names in self.profiles.items():
            marked = ", ".join(
                name if name in installed else f"{name} (not installed)" for name in names
            )
            default = " (default)" if profile == self.default_profile else ""
            rows.append(f"{profile}{default}: {marked}")
        return "\n".join(rows)


async def passes(request: PassesRequest, session: Session) -> PassesResult:  # noqa: ARG001 - every command takes its request
    """List the installed passes and the configured profiles."""
    settings = session.settings
    installed = await asyncio.to_thread(installed_passes)
    return PassesResult(
        installed=tuple(
            PassInfo(
                name=name,
                summary=pass_type.summary,
                codes=tuple(code.code for code in pass_type.codes),
            )
            for name, pass_type in installed.items()
        ),
        profiles=settings.profiles,
        default_profile=settings.profile,
    )


class ExplainRequest(BaseModel):
    """Explain diagnostic codes: what each means and the exact rule its pass checks."""

    code: CliPositionalArg[str] = Field(
        default="", description="A code such as 'E301'; every code when omitted."
    )


class CodeInfo(Code):
    """A diagnostic code and the pass that reports it."""

    pass_name: str = Field(description="Name of the pass that reports the code.")


class ExplainResult(BaseModel):
    """Explanations of diagnostic codes."""

    codes: tuple[CodeInfo, ...]

    def describe(self) -> str:
        """Return the explanations as text."""
        return "\n\n".join(
            f"{info.code} {info.title} ({info.severity}, pass {info.pass_name})\n"
            + _indent(info.rule)
            for info in self.codes
        )


async def explain(request: ExplainRequest, session: Session) -> ExplainResult:  # noqa: ARG001 - every command takes the session
    """Explain one diagnostic code, or all of them.

    Raises:
        BrickyError: If no installed pass documents the code.
    """
    codes = await asyncio.to_thread(installed_codes)
    wanted = request.code.strip().upper()
    if wanted and wanted not in codes:
        message = f"no installed pass reports {wanted}; known codes: {', '.join(codes)}"
        raise BrickyError(message)
    chosen = [wanted] if wanted else list(codes)
    return ExplainResult(
        codes=tuple(
            CodeInfo(pass_name=codes[code][0], **codes[code][1].model_dump(exclude={"severity"}))
            for code in chosen
        )
    )


# ---------------------------------------------------------------------------------------------
# helpers


def _check(  # noqa: PLR0913 - one argument per check option
    model: Model,
    *,
    provenance: Provenance | None,
    profile: str | None,
    passes: list[str] | None,
    max_diagnostics: int | None,
    session: Session,
) -> Report:
    return check_model(
        model,
        profile=profile,
        passes=passes,
        max_diagnostics=max_diagnostics or session.settings.max_diagnostics,
        provenance=provenance,
        catalog=session.catalog,
        settings=session.settings,
    )


def _load(path: Path) -> tuple[Model, Provenance | None]:
    """Read a model file and its source map, when the map is current."""
    return load_model(path), load_source_map(path)


def _write_images(paths: Sequence[Path], pictures: Sequence[bytes]) -> None:
    for path, picture in zip(paths, pictures, strict=True):
        write_file(path, picture)


def _part_info(catalog: Catalog, entry: CatalogPart) -> PartInfo:
    info = PartInfo(id=entry.id, name=entry.name, category=entry.category, base=entry.base)
    part = catalog.part(entry.id)
    if part is None:
        return info
    return info.model_copy(
        update={
            "family": part.family,
            "footprint": part.footprint,
            "height": to_plates(part.size.z),
            "studs": part.stud_count,
            "note": part.note,
        }
    )


def _verify(catalog: Catalog) -> CatalogVerifyResult:
    problems: list[str] = []
    checked = 0
    for entry in catalog.entries:
        try:
            part = catalog.part(entry.id)
        except ValueError as error:
            problems.append(f"{entry.id} {entry.name}: its shape cannot be generated: {error}")
            continue
        if part is not None:
            checked += 1
            problems += [f"{entry.id} {entry.name}: {problem}" for problem in _part_problems(part)]
    return CatalogVerifyResult(checked=checked, problems=tuple(problems))


def _part_problems(part: Part) -> list[str]:
    """List the promises every family makes that a part's geometry breaks."""
    size = part.size
    problems = []
    if Box.bounding(solid.bounds for solid in part.solids) != Box(ORIGIN, size):
        problems.append("its body does not fill its bounding box from the origin")
    sides = {AXES["-x"]: 0, AXES["+x"]: size.x, AXES["-y"]: 0, AXES["+y"]: size.y}
    places = Counter(
        (connector.kind, connector.position, connector.normal) for connector in part.connectors
    )
    problems += [
        f"two {kind}s at {position}" for (kind, position, _), count in places.items() if count > 1
    ]
    for connector in part.connectors:
        position, normal = connector.position, connector.normal
        inside = 0 < position.x < size.x and 0 < position.y < size.y
        if connector.kind is ConnectorKind.ANTI_STUD:
            if normal != DOWN or position.z != 0 or not inside:
                problems.append(f"the anti-stud at {position} is not on the bottom face")
        elif normal == UP:
            if position.z != size.z or not inside:
                problems.append(f"the stud at {position} is not on the top face")
        elif normal not in sides or (position.x if normal.x else position.y) != sides[normal]:
            problems.append(f"the stud at {position} facing {normal} is not on a side face")
    return problems


def _color_info(color: Color) -> ColorInfo:
    return ColorInfo(id=color.id, name=color.name, type=color.type, rgb=color.rgb)


def _describe_images(images: Sequence[Image]) -> list[str]:
    if not images:
        return []
    lines = [f"  {image.view.value}: {image.path}" for image in images]
    return ["rendered (open the images to see the model):\n" + "\n".join(lines)]


def _row(cells: Sequence[str], widths: Sequence[int]) -> str:
    """A table row: each cell padded to its column's width, the last left as it is."""
    padded = [cell.ljust(width) for cell, width in zip(cells[:-1], widths, strict=False)]
    return "  ".join([*padded, cells[-1]])


def _size(model: Model, catalog: Catalog) -> tuple[float, float, float] | None:
    """The size of a model's bodies, in studs, studs and plates."""
    elements = build_world(model, catalog).elements
    if not elements:
        return None
    size = Box.bounding(element.bounds for element in elements).size
    return to_studs(size.x), to_studs(size.y), to_plates(size.z)


def _describe_timings(seconds: Timings) -> str:
    stages = [
        f"{name} {value:.2f} s"
        for name, value in (
            ("script", seconds.script),
            ("changes", seconds.changes),
            ("check", seconds.check),
            ("render", seconds.render),
        )
        if value
    ]
    return "time: " + ", ".join(stages) if stages else "time: 0 s"


def _pairs(counts: dict[str, int]) -> str:
    return ", ".join(f"{name} {count:,}" for name, count in counts.items()) or "none"


def _section(lines: list[str], title: str, counts: dict[str, int]) -> None:
    if not counts:
        return
    lines += ["", f"{title}:"]
    lines += [f"  {name}: {count:,}" for name, count in list(counts.items())[:_LISTED_CATEGORIES]]
    hidden = len(counts) - _LISTED_CATEGORIES
    if hidden > 0:
        lines.append(f"  ... and {hidden} more")


def _count(value: float, noun: str) -> str:
    return f"{value:g} {noun}{'' if value == 1 else 's'}"


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" for line in text.splitlines())
