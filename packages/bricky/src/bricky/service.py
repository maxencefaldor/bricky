"""The service layer: every command, defined once.

Each command is a request model plus a function. The CLI, the MCP server and Python callers all go
through these, so argument names, defaults and descriptions never drift between front-ends.
"""

import runpy
import sys
import traceback
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import CliPositionalArg

from bricky.builder import ModelBuilder
from bricky.catalog import Family, Part, default_catalog
from bricky.check import check_model
from bricky.diagnostics import Report
from bricky.errors import BrickyError
from bricky.files import SUFFIX, load_model, save_model
from bricky.model import Model
from bricky.passes import installed_passes
from bricky.settings import Settings
from bricky.units import STUD, to_plates

_PROFILE_HELP = "Profile to run, such as 'digital' or 'physical'; defaults to the configured one."
_PASSES_HELP = "Pass names to run instead of a profile."
_MAX_HELP = "Maximum diagnostics to return; defaults to the configured cap."


class CheckRequest(BaseModel):
    """Check a model file and report diagnostics."""

    model: CliPositionalArg[Path] = Field(description="Path to a .bricky.json model file.")
    profile: str | None = Field(default=None, description=_PROFILE_HELP)
    passes: list[str] | None = Field(default=None, description=_PASSES_HELP)
    max_diagnostics: int | None = Field(default=None, ge=1, description=_MAX_HELP)


def check(request: CheckRequest, settings: Settings | None = None) -> Report:
    """Check a model file.

    Raises:
        BrickyError: If the file is missing or invalid, or the profile is unknown.
    """
    settings = settings or Settings()
    model = load_model(request.model)
    return _check(model, request.profile, request.passes, request.max_diagnostics, settings)


class BuildRequest(BaseModel):
    """Run a build script, save the model it returns, then check it."""

    script: CliPositionalArg[Path] = Field(
        description="Python file defining build(), which returns a ModelBuilder or a Model."
    )
    output: Path | None = Field(
        default=None, description="Where to save the model; defaults to <script>.bricky.json."
    )
    check: bool = Field(default=True, description="Check the model after building it.")
    profile: str | None = Field(default=None, description=_PROFILE_HELP)
    passes: list[str] | None = Field(default=None, description=_PASSES_HELP)
    max_diagnostics: int | None = Field(default=None, ge=1, description=_MAX_HELP)


class BuildResult(BaseModel):
    """What a build produced."""

    output: Path = Field(description="The saved model file.")
    elements: int = Field(description="Elements in the model, with every instance unfolded.")
    report: Report | None = Field(description="The check report, unless checking was turned off.")


def build(request: BuildRequest, settings: Settings | None = None) -> BuildResult:
    """Run a build script, save its model and check it.

    Raises:
        BrickyError: If the script is missing, fails, or does not return a model.
    """
    settings = settings or Settings()
    model = run_script(request.script)
    output = request.output or request.script.with_name(request.script.stem + SUFFIX)
    save_model(model, output)
    report = (
        _check(model, request.profile, request.passes, request.max_diagnostics, settings)
        if request.check
        else None
    )
    return BuildResult(output=output, elements=model.element_count(), report=report)


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
    studs: int = Field(description="Number of studs on top.")


class PartsResult(BaseModel):
    """Parts matching a search."""

    parts: tuple[PartInfo, ...]
    total: int = Field(description="Matching parts before the limit was applied.")


def parts(request: PartsRequest) -> PartsResult:
    """Search the parts catalog."""
    hits = default_catalog().search(request.query)
    return PartsResult(
        parts=tuple(_part_info(part) for part in hits[: request.limit]), total=len(hits)
    )


class PassesRequest(BaseModel):
    """List the installed check passes and the profiles that run them."""


class PassInfo(BaseModel):
    """An installed pass."""

    name: str
    summary: str


class PassesResult(BaseModel):
    """Installed passes and configured profiles."""

    installed: tuple[PassInfo, ...]
    profiles: dict[str, tuple[str, ...]] = Field(description="Pass names run by each profile.")
    default_profile: str


def passes(_request: PassesRequest, settings: Settings | None = None) -> PassesResult:
    """List the installed passes and the configured profiles."""
    settings = settings or Settings()
    return PassesResult(
        installed=tuple(
            PassInfo(name=name, summary=pass_type.summary)
            for name, pass_type in installed_passes().items()
        ),
        profiles=settings.profiles,
        default_profile=settings.profile,
    )


def run_script(script: Path) -> Model:
    """Run a build script and return the model its ``build()`` function produces.

    Raises:
        BrickyError: If the script is missing, fails, or does not return a model.
    """
    if not script.is_file():
        msg = f"no such build script: {script}"
        raise BrickyError(msg)
    with _importable(script.parent):
        namespace = _guarded(script, lambda: runpy.run_path(str(script), run_name="__bricky__"))
        entry = namespace.get("build")
        if not callable(entry):
            msg = f"{script} must define build(), returning a ModelBuilder or a Model"
            raise BrickyError(msg)
        result = _guarded(script, entry)
    if isinstance(result, ModelBuilder):
        result = _guarded(script, result.build)
    if not isinstance(result, Model):
        msg = f"build() in {script} returned {type(result).__name__}, not a ModelBuilder or Model"
        raise BrickyError(msg)
    return result


def _check(
    model: Model,
    profile: str | None,
    passes: list[str] | None,
    max_diagnostics: int | None,
    settings: Settings,
) -> Report:
    return check_model(
        model,
        profile=profile,
        passes=passes,
        max_diagnostics=max_diagnostics or settings.max_diagnostics,
        settings=settings,
    )


def _part_info(part: Part) -> PartInfo:
    return PartInfo(
        id=part.id,
        name=part.name,
        family=part.family,
        width=part.size.x // STUD,
        length=part.size.y // STUD,
        height=to_plates(part.size.z),
        studs=part.stud_count,
    )


@contextmanager
def _importable(directory: Path) -> Generator[None]:
    """Let a build script import helper modules that sit next to it."""
    entry = str(directory.resolve())
    sys.path.insert(0, entry)
    try:
        yield
    finally:
        sys.path.remove(entry)


def _guarded[T](script: Path, call: Callable[[], T]) -> T:
    try:
        return call()
    except Exception as error:
        raise BrickyError(_describe_failure(script, error)) from error


def _describe_failure(script: Path, error: Exception) -> str:
    # Walk the frames directly: line numbers are all we need, and reading source lines through
    # linecache warns about the module globals that runpy creates.
    target = script.resolve()
    lines = [
        line
        for frame, line in traceback.walk_tb(error.__traceback__)
        if Path(frame.f_code.co_filename).resolve() == target
    ]
    where = f", line {lines[-1]}" if lines else ""
    return f"{script}{where}: {type(error).__name__}: {error}"
