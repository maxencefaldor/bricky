# Copyright 2026 Maxence Faldor
"""Provenance: the build-script lines that placed each element and instance.

A build script places parts by calling :meth:`ModelBuilder.place` and
:meth:`ModelBuilder.instance`. The builder records the script's call stack at each call,
so diagnostics and renders can point back at the line that placed a part.

Provenance is build metadata and stays out of the model. A build result carries it, and
bricky saves it beside the model file as a source map, tied to that file by its hash.
"""

from __future__ import annotations

import hashlib
import inspect
import sysconfig
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from types import FrameType
from typing import Final, Literal, override

from pydantic import BaseModel, ConfigDict, Field

from bricky.model import Model

SOURCE_MAP_FORMAT: Final = "bricky.sourcemap/1"
"""Format tag written into every source map."""

MAX_FRAMES: Final = 4
"""Script frames kept per placement, innermost first."""

_PACKAGE: Final = Path(__file__).resolve().parent


class Frame(BaseModel):
    """One line of a build script."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    file: str = Field(
        description="Script path, relative to the working directory when inside it."
    )
    line: int = Field(ge=1, description="Line number.")
    function: str = Field(
        description="Enclosing function, or '<module>' at the top level."
    )

    @override
    def __str__(self) -> str:
        """The frame as text, such as ``cottage.py:151 in garden()``."""
        where = (
            "at module level"
            if self.function == "<module>"
            else f"in {self.function}()"
        )
        return f"{self.file}:{self.line} {where}"


class Source(BaseModel):
    """The script's call stack at one placement, innermost frame first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    frames: tuple[Frame, ...] = Field(
        min_length=1, description="Script frames, innermost first."
    )

    @property
    def site(self) -> Frame:
        """The innermost frame: the line that made the call."""
        return self.frames[0]

    @override
    def __str__(self) -> str:
        """The innermost frame, then the frames that called it."""
        callers = "".join(f", called from {frame}" for frame in self.frames[1:])
        return f"{self.site}{callers}"

    def relative_to(self, root: Path) -> Source:
        """Return this source with file paths relative to ``root`` where possible."""
        return Source(
            frames=tuple(
                frame.model_copy(update={"file": relative_path(frame.file, root)})
                for frame in self.frames
            )
        )


class ScopeSources(BaseModel):
    """Sources for the elements and instances of one scope: the model or a component."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    elements: dict[str, Source] = Field(
        default_factory=dict, description="By element id."
    )
    instances: dict[str, Source] = Field(
        default_factory=dict, description="By instance id."
    )

    def relative_to(self, root: Path) -> ScopeSources:
        """Return these sources with file paths relative to ``root`` where possible."""
        return ScopeSources(
            elements={
                key: source.relative_to(root) for key, source in self.elements.items()
            },
            instances={
                key: source.relative_to(root) for key, source in self.instances.items()
            },
        )


class Provenance(BaseModel):
    """Where a build script placed every element and instance of a model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: ScopeSources = Field(
        default_factory=ScopeSources, description="Top-level scope."
    )
    components: dict[str, ScopeSources] = Field(
        default_factory=dict, description="Each component's scope, by component name."
    )

    def relative_to(self, root: Path) -> Provenance:
        """Return the provenance with file paths relative to ``root`` where possible."""
        return Provenance(
            model=self.model.relative_to(root),
            components={
                name: sources.relative_to(root)
                for name, sources in self.components.items()
            },
        )

    def trace(self, model: Model, uid: str) -> Trace:
        """Trace a world uid such as ``"west/e2"`` through its instances to its element.

        An unknown id yields an empty trace, never an error, since provenance only adds
        detail.
        """
        *instance_ids, element_id = uid.split("/")
        scope_name: str | None = None
        scope = self.model
        instances = model.instances
        steps: list[InstanceStep] = []
        for instance_id in instance_ids:
            instance = next(
                (item for item in instances if item.id == instance_id), None
            )
            if instance is None or instance.component not in model.components:
                return Trace()
            steps.append(
                InstanceStep(
                    id=instance_id,
                    component=instance.component,
                    source=scope.instances.get(instance_id),
                )
            )
            scope_name = instance.component
            scope = self.components.get(scope_name, ScopeSources())
            instances = model.components[scope_name].instances
        return Trace(
            component=scope_name,
            source=scope.elements.get(element_id),
            via=tuple(steps),
        )


class InstanceStep(BaseModel):
    """One instance on the way from the model to an element."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(description="Instance id within its scope.")
    component: str = Field(description="Component the instance places.")
    source: Source | None = Field(
        default=None, description="Where the instance was placed."
    )


class Trace(BaseModel):
    """Where an element came from: its placement and the instances that copied it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    component: str | None = Field(
        default=None, description="Component defining the element."
    )
    source: Source | None = Field(
        default=None, description="Where the element was placed."
    )
    via: tuple[InstanceStep, ...] = Field(
        default=(), description="Instances, outermost first."
    )

    def sources(self) -> Iterator[Source]:
        """Every source on the trace: the element's own, then each instance's."""
        if self.source is not None:
            yield self.source
        yield from (step.source for step in self.via if step.source is not None)


class SourceMap(BaseModel):
    """A model file's provenance, saved beside it and tied to its exact bytes."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["bricky.sourcemap/1"] = SOURCE_MAP_FORMAT
    script: str = Field(description="The build script that produced the model.")
    model_sha256: str = Field(
        description="SHA-256 of the model file this map describes."
    )
    provenance: Provenance


def model_digest(data: bytes) -> str:
    """Return the digest a source map records for model-file bytes."""
    return hashlib.sha256(data).hexdigest()


def capture() -> Source | None:
    """Return the build script's call stack at the current point, innermost frame first.

    The walk skips frames in bricky, the standard library and installed packages up to
    the first script frame, then stops at the next frame outside the script, such as
    bricky's runner or the interpreter's own machinery.

    Returns:
        The script frames, or ``None`` when no script frame is on the stack.
    """
    frame: FrameType | None = inspect.currentframe()
    frames: list[Frame] = []
    try:
        while frame is not None and not is_script_file(frame.f_code.co_filename):
            frame = frame.f_back
        while (
            frame is not None
            and len(frames) < MAX_FRAMES
            and is_script_file(frame.f_code.co_filename)
        ):
            frames.append(
                Frame(
                    file=frame.f_code.co_filename,
                    line=frame.f_lineno or 1,
                    function=frame.f_code.co_name,
                )
            )
            frame = frame.f_back
    finally:
        del frame  # break the reference cycle through the frame's locals
    return Source(frames=tuple(frames)) if frames else None


@cache
def is_script_file(filename: str) -> bool:
    """Return whether the code in a file belongs to a build script.

    Generated code, such as ``<string>`` and ``<frozen runpy>``, and code in bricky, the
    standard library or an installed package belong to no script.
    """
    if filename.startswith("<"):
        return False
    path = Path(filename).resolve()
    return not any(path.is_relative_to(root) for root in _library_roots())


@cache
def _library_roots() -> tuple[Path, ...]:
    paths = sysconfig.get_paths()
    roots = {_PACKAGE}
    roots.update(
        Path(paths[key]).resolve()
        for key in ("stdlib", "platstdlib", "purelib", "platlib")
    )
    return tuple(sorted(roots))


def relative_path(file: str, root: Path) -> str:
    """Return ``file`` relative to ``root`` when it lies inside it, else unchanged."""
    try:
        return Path(file).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return file
