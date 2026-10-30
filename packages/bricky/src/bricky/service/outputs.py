# Copyright 2026 Maxence Faldor
"""What a saved model makes: images and a viewer, building instructions, and exports."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import CliPositionalArg

from bricky.diagnostics import Report
from bricky.exports import FORMATS, Format, model_lots
from bricky.files import model_stem, write_file
from bricky.instructions import ELEMENTS_PER_STEP, build_instructions
from bricky.render import Clip, View, build_scene, downloads, write_html
from bricky.service.checks import rule_levels, run_check
from bricky.service.session import (
    ERROR_HELP,
    HEIGHT,
    IGNORE_HELP,
    VIEWS_HELP,
    WARN_HELP,
    WIDTH,
    Image,
    Session,
    Timings,
    describe_images,
    describe_timings,
    plural,
    read_model,
    render_views,
    view_paths,
)


class RenderRequest(BaseModel):
    """Render images of a model file."""

    model: CliPositionalArg[Path] = Field(
        description="Path to a .bricky.json model file."
    )
    views: list[View] = Field(default=[View.SHEET], description=VIEWS_HELP)
    highlight: list[str] = Field(
        default_factory=list,
        description=(
            "Elements to highlight, rendering the rest faintly: uid patterns such as "
            "'sign*', or '@' and a function, file or file:line of the build script, "
            "such as '@roof'."
        ),
    )
    clip: list[str] = Field(
        default_factory=list,
        description=(
            "Clip the model to look inside: 'z<130' keeps what lies below 130 plates; "
            "x and y are in studs."
        ),
    )
    check: bool = Field(
        default=True, description="Mark the elements that diagnostics name."
    )
    error: list[str] = Field(default_factory=list, description=ERROR_HELP)
    warn: list[str] = Field(default_factory=list, description=WARN_HELP)
    ignore: list[str] = Field(default_factory=list, description=IGNORE_HELP)
    width: int = Field(
        default=WIDTH, ge=200, le=4096, description="Image width in pixels."
    )
    height: int = Field(
        default=HEIGHT, ge=200, le=4096, description="Image height in pixels."
    )
    output: Path | None = Field(
        default=None,
        description=(
            "Image file to write; with several views, each file name gets the view's "
            "name added. Defaults to <model>.<view>.png beside the model, so renders "
            "keep the sheet a build rendered."
        ),
    )
    html: bool = Field(
        default=False,
        description=(
            "Also write a standalone HTML viewer to orbit, inspect and build step "
            "by step, highlighted like the images, with the model's exports."
        ),
    )


class RenderResult(BaseModel):
    """Images of a model."""

    images: tuple[Image, ...]
    html: Path | None = Field(description="The standalone viewer, when requested.")
    report: Report | None = Field(
        description=(
            "The check report whose diagnostics the images mark; "
            "null when checking is off."
        )
    )
    seconds: Timings

    def describe(self) -> str:
        """Return the result as text for people and agents."""
        blocks = list(describe_images(self.images))
        if self.html is not None:
            blocks.append(f"viewer: {self.html}")
        if self.report is not None:
            blocks.append(
                f"marked {self.report.errors} errors and "
                f"{self.report.warnings} warnings"
            )
        blocks.append(describe_timings(self.seconds))
        return "\n\n".join(blocks)


async def render(request: RenderRequest, session: Session) -> RenderResult:
    """Render images of a model file.

    Raises:
        BrickyError: If the file is missing or invalid, a selector or clip is invalid,
            a rule is unknown or given two levels, or the render fails.
    """
    rules = await asyncio.to_thread(
        rule_levels, request.error, request.warn, request.ignore, session.settings
    )
    model, provenance = await asyncio.to_thread(read_model, request.model)
    clips = [Clip.parse(text) for text in request.clip]
    seconds = Timings()
    report = None
    if request.check:
        started = time.perf_counter()
        report = await asyncio.to_thread(
            run_check,
            model,
            provenance=provenance,
            rules=rules,
            max_diagnostics=None,
            session=session,
        )
        seconds.check = time.perf_counter() - started
    started = time.perf_counter()
    if request.output is None:
        stem = model_stem(request.model)
        paths = [
            request.model.with_name(f"{stem}.{view.value}.png")
            for view in request.views
        ]
        viewer = request.model.with_name(stem + ".html")
    else:
        paths = view_paths(request.output, request.views)
        viewer = request.output.with_suffix(".html")
    images = await render_views(
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
        steps = await asyncio.to_thread(
            build_instructions, model, session.catalog, provenance=provenance
        )
        scene = await asyncio.to_thread(
            build_scene,
            model,
            session.catalog,
            provenance=provenance,
            report=report,
            highlight=request.highlight,
            clips=clips,
            cull=False,
            instructions=steps,
        )
        files = await asyncio.to_thread(downloads, model, session.catalog)
        html = await asyncio.to_thread(write_html, scene, viewer, files)
    seconds.render = time.perf_counter() - started
    return RenderResult(images=images, html=html, report=report, seconds=seconds)


class InstructionsRequest(BaseModel):
    """Write building instructions: a page that shows a model's steps in 3D."""

    model: CliPositionalArg[Path] = Field(
        description="Path to a .bricky.json model file."
    )
    elements_per_step: int = Field(
        default=ELEMENTS_PER_STEP,
        ge=1,
        le=100,
        description="How many elements a step adds at most.",
    )
    output: Path | None = Field(
        default=None,
        description=(
            "HTML file to write; defaults to <model>.instructions.html beside the "
            "model."
        ),
    )


class StepNote(BaseModel):
    """A build-order rule a step breaks, because elements lock one another in."""

    step: int = Field(description="The step's number, from 1.")
    message: str = Field(
        description=(
            "What goes on early, such as 'e7 goes on before e3, which holds it'."
        )
    )


class InstructionsResult(BaseModel):
    """Building instructions, written as a page."""

    path: Path = Field(description="The page written.")
    steps: int = Field(description="How many steps the instructions take.")
    elements: int = Field(description="How many elements the steps place.")
    notes: list[StepNote] = Field(
        description=(
            "Every build-order rule a step breaks; empty when each element goes on "
            "with nothing in its way and something to hold it."
        )
    )

    def describe(self) -> str:
        """Return the result as text for people and agents."""
        average = self.elements / max(self.steps, 1)
        lines = [
            (
                f"wrote {self.path}: {plural(self.steps, 'step')} for "
                f"{plural(self.elements, 'element')}, {average:.1f} a step on average"
            )
        ]
        if self.notes:
            steps = len({note.step for note in self.notes})
            verb = "breaks" if steps == 1 else "break"
            lines.append(
                f"{plural(steps, 'step')} {verb} the build order, where elements "
                "lock one another in:"
            )
            lines.extend(f"  step {note.step}: {note.message}" for note in self.notes)
        return "\n".join(lines)


async def instructions(
    request: InstructionsRequest, session: Session
) -> InstructionsResult:
    """Write building instructions for a model file.

    Raises:
        BrickyError: If the file is missing or invalid, the model has no element to
            place, or the page cannot be written.
    """
    model, provenance = await asyncio.to_thread(read_model, request.model)
    steps = await asyncio.to_thread(
        build_instructions,
        model,
        session.catalog,
        provenance=provenance,
        elements_per_step=request.elements_per_step,
    )
    scene = await asyncio.to_thread(
        build_scene,
        model,
        session.catalog,
        provenance=provenance,
        cull=False,
        instructions=steps,
    )
    files = await asyncio.to_thread(downloads, model, session.catalog)
    path = request.output or request.model.with_name(
        model_stem(request.model) + ".instructions.html"
    )
    await asyncio.to_thread(write_html, scene, path, files, mode="instructions")
    return InstructionsResult(
        path=path,
        steps=len(scene.steps),
        elements=sum(len(step.elements) for step in scene.steps),
        notes=[
            StepNote(step=k + 1, message=message)
            for k, step in enumerate(scene.steps)
            for message in step.notes
        ],
    )


class ExportRequest(BaseModel):
    """Export a model file for another tool, such as a BrickLink Wanted List."""

    model: CliPositionalArg[Path] = Field(
        description="Path to a .bricky.json model file."
    )
    format: Format = Field(
        default=Format.WANTED_LIST,
        description=(
            "File format: wanted-list (a BrickLink Wanted List, to buy the parts on "
            "BrickLink)."
        ),
    )
    output: Path | None = Field(
        default=None,
        description=(
            "File to write; defaults to the model's name and the format's suffix, "
            "such as <model>.wanted.xml, beside the model."
        ),
    )


class ExportResult(BaseModel):
    """An exported file, with what it lists."""

    path: Path = Field(description="The file written.")
    format: Format
    lots: int = Field(description="Parts in one color each: one line of the list each.")
    elements: int = Field(description="Elements the lots add up to.")
    usage: str = Field(description="How to use the file in its tool.")

    def describe(self) -> str:
        """Return the result as text for people and agents."""
        title = FORMATS[self.format].title
        return (
            f"wrote {self.path}: {self.lots:,} lots, {self.elements:,} elements, "
            f"as a {title}\n{self.usage}"
        )


async def export(request: ExportRequest, session: Session) -> ExportResult:
    """Export a model file for another tool.

    Raises:
        BrickyError: If the file is missing or invalid, the catalog lacks a part or
            color the model uses, or the file cannot be written.
    """
    model, _ = await asyncio.to_thread(read_model, request.model)
    exporter = FORMATS[request.format]
    lots = model_lots(model, session.catalog)
    path = request.output or request.model.with_name(
        model_stem(request.model) + exporter.suffix
    )
    await asyncio.to_thread(write_file, path, exporter.write(lots))
    return ExportResult(
        path=path,
        format=request.format,
        lots=len(lots),
        elements=sum(lot.quantity for lot in lots),
        usage=exporter.usage,
    )
