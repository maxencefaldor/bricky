# Copyright 2026 Maxence Faldor
"""The session, and what several commands share.

A :class:`Session` carries the settings, the catalog and a warm renderer between
commands. The rest serves several commands: the results they share, the descriptions of
their common options, reading model files, rendering views, and text.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Final, Self

from pydantic import BaseModel, Field

from bricky.catalog import Catalog, catalog_path, load_catalog
from bricky.diagnostics import Report
from bricky.files import load_model, load_source_map, write_file
from bricky.model import Model
from bricky.provenance import Provenance
from bricky.render import Clip, Renderer, View, build_scene
from bricky.settings import Settings

ERROR_HELP: Final = (
    "Rules to report as errors, such as 'overloaded-studs', or 'all' for every rule; "
    "overrides the configured levels."
)
WARN_HELP: Final = (
    "Rules to report as warnings, or 'all' for every rule; overrides the configured "
    "levels."
)
IGNORE_HELP: Final = (
    "Rules to leave out, such as 'strained-studs', or 'all' for every rule; overrides "
    "the configured levels."
)
MAX_DIAGNOSTICS_HELP: Final = (
    "Maximum diagnostics to return; defaults to the configured cap."
)
VIEWS_HELP: Final = (
    "Views to render: sheet (perspective, front, right and top on one image), "
    "perspective (from the south-east), perspective-south-west, "
    "perspective-north-west, perspective-north-east, front, back, left, right or top."
)
WIDTH: Final = 1600
HEIGHT: Final = 1200


class Session:
    """Settings and a warm renderer, shared by the commands of one process.

    The browser launch is the slow part of a render, so a session launches the browser
    on the first render and keeps it until :meth:`close`. A session is an async context
    manager.
    """

    def __init__(
        self, settings: Settings | None = None, catalog: Catalog | None = None
    ) -> None:
        """Use the given settings and catalog, or the configured ones."""
        self.settings = settings or Settings()
        self.catalog = catalog or load_catalog(catalog_path(self.settings))
        self._renderer: Renderer | None = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        """Return the session; its renderer starts when a command first renders."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close the renderer, if one started."""
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


class Image(BaseModel):
    """A rendered image of a model."""

    view: View
    path: Path = Field(description="The PNG file.")
    width: int
    height: int


class Timings(BaseModel):
    """Seconds spent in each stage of a command."""

    script: float = 0.0
    changes: float = 0.0
    check: float = 0.0
    render: float = 0.0


def read_model(path: Path) -> tuple[Model, Provenance | None]:
    """Read a model file and its source map, when the map is current."""
    return load_model(path), load_source_map(path)


async def render_views(  # noqa: PLR0913 - keyword-only options, one per concern
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
    size: tuple[int, int] = (WIDTH, HEIGHT),
) -> tuple[Image, ...]:
    """Render ``views`` of a model, each to the path at the same index in ``paths``."""
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
    images = await renderer.render(scene, views, width=width, height=height)
    await asyncio.to_thread(_write_images, paths, images)
    return tuple(
        Image(view=view, path=path, width=width, height=height)
        for view, path in zip(views, paths, strict=True)
    )


def view_paths(base: Path, views: Sequence[View]) -> list[Path]:
    """One path per view: ``base`` for one view, else ``base`` plus each view's name."""
    if len(views) == 1:
        return [base]
    return [base.with_name(f"{base.stem}.{view.value}{base.suffix}") for view in views]


def _write_images(paths: Sequence[Path], images: Sequence[bytes]) -> None:
    for path, image in zip(paths, images, strict=True):
        write_file(path, image)


def describe_images(images: Sequence[Image]) -> list[str]:
    """Return the lines that list rendered images, or none when there are none."""
    if not images:
        return []
    lines = [f"  {image.view.value}: {image.path}" for image in images]
    return ["rendered (open the images to see the model):\n" + "\n".join(lines)]


def describe_timings(seconds: Timings) -> str:
    """Return the line that says how long each stage took."""
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


def plural(value: float, noun: str) -> str:
    """Return a count and its noun, such as ``1 element`` or ``3 elements``."""
    return f"{value:g} {noun}{'' if value == 1 else 's'}"


def indent(text: str) -> str:
    """Return text with each line indented by two spaces."""
    return "\n".join(f"  {line}" for line in text.splitlines())
