"""The service layer: every command, defined once.

Each command is a request model plus an async function. The CLI runs them, the MCP server awaits
them, and Python callers can do either, so argument names, defaults and descriptions never drift
between front-ends. A :class:`Session` carries the settings and a warm renderer between commands.

Build scripts never run in this process: :func:`run_script` starts each one in a child process
(see :mod:`bricky.runner`), with a timeout, and captures what it prints.
"""

import asyncio
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final, Self

from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import CliPositionalArg

from bricky.catalog import Catalog, Color, ColorType, Family, Part, default_catalog
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
from bricky.model import Model
from bricky.passes import installed_codes, installed_passes
from bricky.provenance import Provenance
from bricky.render import Clip, Renderer, View, build_scene, write_html
from bricky.runner import RunResult
from bricky.settings import Settings
from bricky.units import to_plates

_PROFILE_HELP: Final = (
    "Profile to run, such as 'digital' or 'physical'; defaults to the configured one."
)
_PASSES_HELP: Final = "Pass names to run instead of a profile."
_MAX_HELP: Final = "Maximum diagnostics to return; defaults to the configured cap."
_VIEWS_HELP: Final = (
    "Views to draw: sheet (iso, front, right and top on one image), iso, front, back, left, right "
    "or top."
)
_WIDTH: Final = 1600
_HEIGHT: Final = 1200


class Session:
    """Settings and a warm renderer, shared by the commands of one process.

    Launching the browser is the slow part of a render, so a session starts it on the first render
    and keeps it until :meth:`close`. Use a session as an async context manager.
    """

    def __init__(self, settings: Settings | None = None, catalog: Catalog | None = None) -> None:
        self.settings = settings or Settings()
        self.catalog = catalog or default_catalog()
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
    path: Path = Field(description="PNG file.")
    width: int
    height: int


class ScriptOutput(BaseModel):
    """What a build script printed."""

    stdout: str = Field(default="", description="Standard output, cut to the configured limit.")
    stderr: str = Field(default="", description="Standard error, cut to the configured limit.")
    truncated: bool = Field(default=False, description="Whether either stream was cut.")

    def describe(self) -> str:
        """Render the output for reading, or an empty string when the script printed nothing."""
        parts = []
        if self.stdout.strip():
            parts.append("script output:\n" + _indent(self.stdout.rstrip()))
        if self.stderr.strip():
            parts.append("script errors:\n" + _indent(self.stderr.rstrip()))
        if self.truncated:
            parts.append("(output cut to the configured limit)")
        return "\n\n".join(parts)


class Timings(BaseModel):
    """Seconds spent in each stage of a command."""

    script: float = 0.0
    check: float = 0.0
    render: float = 0.0


# ---------------------------------------------------------------------------------------------
# check


class CheckRequest(BaseModel):
    """Check a model file and report diagnostics."""

    model: CliPositionalArg[Path] = Field(description="Path to a .bricky.json model file.")
    profile: str | None = Field(default=None, description=_PROFILE_HELP)
    passes: list[str] | None = Field(default=None, description=_PASSES_HELP)
    max_diagnostics: int | None = Field(default=None, ge=1, description=_MAX_HELP)


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
    views: list[View] = Field(default_factory=lambda: [View.SHEET], description=_VIEWS_HELP)
    profile: str | None = Field(default=None, description=_PROFILE_HELP)
    passes: list[str] | None = Field(default=None, description=_PASSES_HELP)
    max_diagnostics: int | None = Field(default=None, ge=1, description=_MAX_HELP)


class BuildResult(BaseModel):
    """What a build produced."""

    model: Path = Field(description="The saved model file.")
    source_map: Path | None = Field(
        description="The saved source map, linking elements to script lines."
    )
    elements: int = Field(description="Elements in the model, with every instance unfolded.")
    output: ScriptOutput = Field(description="What the build script printed.")
    report: Report | None = Field(description="The check report, unless checking was off.")
    images: tuple[Image, ...] = Field(description="Rendered pictures, unless rendering was off.")
    seconds: Timings

    def describe(self) -> str:
        """Render the result as text for people and agents."""
        blocks = [f"saved {self.model} ({self.elements} elements)"]
        if text := self.output.describe():
            blocks.append(text)
        if self.report is not None:
            blocks.append(render_report(self.report))
        blocks.extend(_describe_images(self.images))
        blocks.append(_describe_timings(self.seconds))
        return "\n\n".join(blocks)


async def build(request: BuildRequest, session: Session) -> BuildResult:
    """Run a build script in its own process, save its model and source map, check and render.

    Raises:
        BrickyError: If the script is missing, fails, times out or returns no model, or if the
            render cannot be made.
    """
    settings = session.settings
    started = time.perf_counter()
    run = await run_script(request.script, settings)
    path = request.output or request.script.with_name(request.script.stem + SUFFIX)
    source_map = await asyncio.to_thread(_save, run, request.script, path)
    seconds = Timings(script=time.perf_counter() - started)

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
        )
        seconds.render = time.perf_counter() - started
    return BuildResult(
        model=path,
        source_map=source_map,
        elements=run.model.element_count(),
        output=run.output,
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
        msg = f"no such build script: {script}"
        raise BrickyError(msg)
    try:
        async with asyncio.timeout(settings.build_timeout):
            result, output, code = await _run_child(script, settings.output_limit)
    except TimeoutError:
        msg = f"{script} did not finish within {settings.build_timeout:g} s and was stopped"
        raise BrickyError(msg) from None
    if result is None:
        msg = f"{script}: the build process exited with code {code} before reporting a result"
        raise BrickyError(_with_output(msg, output))
    if result.failure is not None or result.model is None:
        raise BrickyError(_with_output(f"{script} failed: {result.failure}", output))
    return ScriptRun(model=result.model, provenance=result.provenance, output=output)


async def _run_child(script: Path, limit: int) -> tuple[RunResult | None, ScriptOutput, int]:
    """Run the child process to its end and return its result, its output and its exit code.

    If the caller stops waiting, through a timeout or a cancelled request, the child is killed
    before the cancellation goes on: no build script outlives the command that started it.
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
            msg = "could not capture the build script's output"
            raise BrickyError(msg)
        try:
            (stdout, cut_out), (stderr, cut_err) = await asyncio.gather(
                _read_capped(process.stdout, limit), _read_capped(process.stderr, limit)
            )
            code = await process.wait()
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        output = ScriptOutput(stdout=stdout, stderr=stderr, truncated=cut_out or cut_err)
        result = await asyncio.to_thread(_read_result, result_path)
    return result, output, code


def _read_result(path: Path) -> RunResult | None:
    """Return the child's result, or ``None`` if it exited before writing a whole one."""
    try:
        return RunResult.model_validate_json(path.read_bytes())
    except FileNotFoundError, ValidationError:
        return None


def _save(run: ScriptRun, script: Path, path: Path) -> Path | None:
    """Save a built model and, when its provenance is known, its source map."""
    save_model(run.model, path)
    if run.provenance is None:
        return None
    return save_source_map(run.provenance, script=script, model_path=path)


async def _read_capped(stream: asyncio.StreamReader, limit: int) -> tuple[str, bool]:
    """Read a stream to its end, keeping at most ``limit`` characters' worth of bytes."""
    kept = bytearray()
    cut = False
    while chunk := await stream.read(65536):
        room = max(limit - len(kept), 0)
        kept += chunk[:room]
        cut = cut or len(chunk) > room
    return kept.decode(errors="replace"), cut


def _with_output(message: str, output: ScriptOutput) -> str:
    text = output.describe()
    return f"{message}\n\n{text}" if text else message


# ---------------------------------------------------------------------------------------------
# render


class RenderRequest(BaseModel):
    """Render pictures of a model file."""

    model: CliPositionalArg[Path] = Field(description="Path to a .bricky.json model file.")
    views: list[View] = Field(default_factory=lambda: [View.SHEET], description=_VIEWS_HELP)
    highlight: list[str] = Field(
        default_factory=list,
        description=(
            "Parts to highlight, drawing the rest faintly: uid patterns such as 'lintel*', or '@' "
            "and a function, file or file:line of the build script, such as '@horseshoe'."
        ),
    )
    clip: list[str] = Field(
        default_factory=list,
        description="Cut the model to look inside: 'z<130' keeps parts below 130 plates; x and y "
        "are in studs.",
    )
    check: bool = Field(default=True, description="Mark the parts that diagnostics name.")
    width: int = Field(default=_WIDTH, ge=200, le=4096, description="Image width in pixels.")
    height: int = Field(default=_HEIGHT, ge=200, le=4096, description="Image height in pixels.")
    out: Path | None = Field(
        default=None,
        description="Image file to write; with several views, each gets the view's name added. "
        "Defaults to <model>.<view>.png beside the model, so renders never replace the picture "
        "a build drew.",
    )
    html: bool = Field(
        default=False,
        description="Also write a standalone HTML viewer people can orbit, cut and highlighted "
        "like the pictures.",
    )


class RenderResult(BaseModel):
    """Pictures of a model."""

    images: tuple[Image, ...]
    html: Path | None = Field(description="The standalone viewer, when one was asked for.")
    report: Report | None = Field(description="The check whose findings were marked, if any.")
    seconds: Timings

    def describe(self) -> str:
        """Render the result as text for people and agents."""
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
            render cannot be made.
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
    if request.out is None:
        stem = model_stem(request.model)
        paths = [request.model.with_name(f"{stem}.{view.value}.png") for view in request.views]
        viewer = request.model.with_name(stem + ".html")
    else:
        paths = _view_paths(request.out, request.views)
        viewer = request.out.with_suffix(".html")
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
    )
    renderer = await session.renderer()
    width, height = size
    pngs = await renderer.render(scene, views, width=width, height=height)
    await asyncio.to_thread(_write_images, paths, pngs)
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
        description="Words to match against ids, names and sizes, such as 'plate 2x4' (quoted).",
    )
    limit: int = Field(default=20, ge=1, le=500, description="Maximum number of parts to return.")


class PartInfo(BaseModel):
    """A catalog part, summarised for choosing parts."""

    id: str = Field(description="BrickLink item number.")
    name: str = Field(description="BrickLink item name.")
    family: Family
    width: int = Field(description="Studs along the part's local x axis.")
    length: int = Field(description="Studs along the part's local y axis.")
    height: float = Field(description="Body height in plates.")
    studs: int = Field(description="Number of studs, on top and on its sides.")
    note: str = Field(
        default="", description="How the part sits when placed unturned, where that matters."
    )


class PartsResult(BaseModel):
    """Parts matching a search."""

    parts: tuple[PartInfo, ...]
    total: int = Field(description="Matching parts before the limit was applied.")

    def describe(self) -> str:
        """Render the result as a table, with each part's note under it."""
        name = max((len(p.name) for p in self.parts), default=0)
        family = max((len(p.family) for p in self.parts), default=0)
        rows = []
        for p in self.parts:
            rows.append(
                f"{p.id:<7} {p.name:<{name}}  {p.family:<{family}}  {p.width}x{p.length}  "
                f"{_count(p.height, 'plate')}  {_count(p.studs, 'stud')}"
            )
            if p.note:
                rows.append(f"{'':<8}{p.note}")
        rows.append(f"{len(self.parts)} of {self.total} matching parts")
        return "\n".join(rows)


async def parts(request: PartsRequest, session: Session) -> PartsResult:
    """Search the parts catalog."""
    hits = await asyncio.to_thread(session.catalog.search, request.query)
    return PartsResult(
        parts=tuple(_part_info(part) for part in hits[: request.limit]), total=len(hits)
    )


class ColorsRequest(BaseModel):
    """List the catalog's colours."""

    query: CliPositionalArg[str] = Field(
        default="", description="Words to match against ids, names and types, such as 'gray'."
    )


class ColorInfo(BaseModel):
    """A catalog colour."""

    id: int = Field(description="BrickLink colour id.")
    name: str = Field(description="BrickLink colour name.")
    type: ColorType
    rgb: str = Field(description="Display colour used by renders.")


class ColorsResult(BaseModel):
    """Colours matching a search."""

    colors: tuple[ColorInfo, ...]

    def describe(self) -> str:
        """Render the result as a table."""
        rows = [f"{c.id:>4}  {c.name:<22} {c.type:<12} {c.rgb}" for c in self.colors]
        rows.append(f"{_count(len(self.colors), 'colour')}")
        return "\n".join(rows)


async def colors(request: ColorsRequest, session: Session) -> ColorsResult:
    """List the catalog's colours."""
    found = await asyncio.to_thread(session.catalog.search_colors, request.query)
    return ColorsResult(colors=tuple(_color_info(c) for c in found))


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
        """Render the result as text."""
        installed = {p.name for p in self.installed}
        rows = [f"{p.name:<14} {', '.join(p.codes):<12} {p.summary}" for p in self.installed]
        rows.append("")
        for name, names in self.profiles.items():
            marked = ", ".join(n if n in installed else f"{n} (not installed)" for n in names)
            default = " (default)" if name == self.default_profile else ""
            rows.append(f"{name}{default}: {marked}")
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

    check: str = Field(description="Name of the pass that reports the code.")


class ExplainResult(BaseModel):
    """Explanations of diagnostic codes."""

    codes: tuple[CodeInfo, ...]

    def describe(self) -> str:
        """Render the explanations as text."""
        return "\n\n".join(
            f"{c.code} {c.title} ({c.severity}, pass {c.check})\n{_indent(c.rule)}"
            for c in self.codes
        )


async def explain(request: ExplainRequest, session: Session) -> ExplainResult:  # noqa: ARG001 - every command takes the session
    """Explain one diagnostic code, or all of them.

    Raises:
        BrickyError: If no installed pass documents the code.
    """
    codes = await asyncio.to_thread(installed_codes)
    wanted = request.code.strip().upper()
    if wanted and wanted not in codes:
        msg = f"no installed pass reports {wanted}; known codes: {', '.join(codes)}"
        raise BrickyError(msg)
    chosen = [wanted] if wanted else list(codes)
    return ExplainResult(
        codes=tuple(
            CodeInfo(check=codes[c][0], **codes[c][1].model_dump(exclude={"severity"}))
            for c in chosen
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


def _write_images(paths: Sequence[Path], pngs: Sequence[bytes]) -> None:
    for path, png in zip(paths, pngs, strict=True):
        write_file(path, png)


def _part_info(part: Part) -> PartInfo:
    width, length = part.footprint
    return PartInfo(
        id=part.id,
        name=part.name,
        family=part.family,
        width=width,
        length=length,
        height=to_plates(part.size.z),
        studs=part.stud_count,
        note=part.note,
    )


def _color_info(color: Color) -> ColorInfo:
    return ColorInfo(id=color.id, name=color.name, type=color.type, rgb=color.rgb)


def _describe_images(images: Sequence[Image]) -> list[str]:
    if not images:
        return []
    lines = [f"  {image.view.value}: {image.path}" for image in images]
    return ["rendered (open the images to see the model):\n" + "\n".join(lines)]


def _describe_timings(seconds: Timings) -> str:
    stages = [
        f"{name} {value:.2f} s"
        for name, value in (
            ("script", seconds.script),
            ("check", seconds.check),
            ("render", seconds.render),
        )
        if value
    ]
    return "time: " + ", ".join(stages) if stages else "time: 0 s"


def _count(value: float, noun: str) -> str:
    return f"{value:g} {noun}{'' if value == 1 else 's'}"


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" for line in text.splitlines())
