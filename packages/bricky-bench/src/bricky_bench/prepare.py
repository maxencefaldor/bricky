"""Write a project's generated inputs from its reference: pictures and voxel plans.

Generated inputs are committed with the project, so every run of the benchmark gives the agent the
same files. ``bricky-bench prepare`` writes them again after a reference changes.
"""

import asyncio
import string
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Final

from bricky import voxels
from bricky.analysis import Voxel, VoxelKey
from bricky.catalog import Catalog
from bricky.errors import BrickyError
from bricky.files import write_file
from bricky.model import Model
from bricky.render import build_scene
from bricky.service import Session, run_script
from bricky_bench.projects import REFERENCE_FILE, Layers, Project, Render

EMPTY: Final = "."
"""The character that marks an empty voxel in a plan."""


async def prepare(project: Project, session: Session) -> list[Path]:
    """Build a project's reference and write every input its project file generates.

    Raises:
        BrickyError: If the project generates inputs but has no reference, the reference does not
            build, or a picture cannot be drawn.
    """
    if not project.spec.generate:
        return []
    model = await reference_model(project, session)
    written = []
    for item in project.spec.generate:
        match item:
            case Render():
                data = await _render(model, item, session)
            case Layers():
                data = layers_text(model, session.catalog, item.levels).encode()
        written.append(await asyncio.to_thread(write_file, project.path / item.file, data))
    return written


async def reference_model(project: Project, session: Session) -> Model:
    """Build a project's reference model.

    Raises:
        BrickyError: If the project has no reference, or it does not build.
    """
    if project.reference is None:
        message = f"{project.id} has no {REFERENCE_FILE}"
        raise BrickyError(message)
    run = await run_script(project.reference, session.settings)
    return run.model


async def _render(model: Model, item: Render, session: Session) -> bytes:
    scene = await asyncio.to_thread(build_scene, model, session.catalog)
    if item.caption is not None:
        scene = scene.model_copy(update={"title": item.caption})
    renderer = await session.renderer()
    (png,) = await renderer.render(scene, [item.view], width=item.width, height=item.height)
    return png


def layers_text(model: Model, catalog: Catalog, levels: Sequence[int] | None = None) -> str:
    """Describe a model's voxels as text: a color legend, then one plan per plate level.

    Every plan covers the same x and y range, the model's own, so plans line up when read one
    after another. Rows run from north (top) to south, columns from west (left) to east.

    Raises:
        BrickyError: If the model fills no voxel.
    """
    filled = voxels(model, catalog)
    if not filled:
        message = f"{model.name} fills no voxel"
        raise BrickyError(message)
    xs = [x for x, _, _ in filled]
    ys = [y for _, y, _ in filled]
    zs = sorted({z for _, _, z in filled})
    shown = zs if levels is None else [z for z in levels if z in zs]
    colors = _first_seen(filled, (min(xs), max(xs)), (min(ys), max(ys)), zs)
    names = [_color_name(catalog, color) for color in colors]
    symbols = dict(zip(colors, _symbols(names), strict=True))

    lines = [
        f"{model.name}: the voxels it fills, one plate level at a time from the ground up.",
        "",
        "A voxel is 1 x 1 stud and 1 plate tall; z counts plates, so a brick fills three levels.",
        "Each level is a plan seen from above, north up: x grows to the right (east) and y grows",
        "upward (north), both in studs. '.' is an empty voxel; every other character is a color:",
        "",
        *(f"  {symbols[color]}  {name}" for color, name in zip(colors, names, strict=True)),
        "",
        (
            f"x runs from {min(xs)} to {max(xs)}, y from {min(ys)} to {max(ys)}, "
            f"and z from {zs[0]} to {zs[-1]}."
        ),
    ]
    for z in shown:
        lines.extend(("", f"z = {z}", *_plan(filled, symbols, z, xs, ys)))
    return "\n".join(lines) + "\n"


def _plan(
    filled: dict[VoxelKey, Voxel],
    symbols: dict[int, str],
    z: int,
    xs: Sequence[int],
    ys: Sequence[int],
) -> list[str]:
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    width = max(len(str(y0)), len(str(y1)), 3)
    columns = range(x0, x1 + 1)
    tens = "".join(str(abs(x) // 10 % 10) if x % 10 == 0 else " " for x in columns)
    units = "".join(str(abs(x) % 10) for x in columns)
    rows = [f"{'y\\x':>{width}}  {tens}".rstrip(), f"{'':>{width}}  {units}"]
    for y in range(y1, y0 - 1, -1):
        row = "".join(
            symbols[voxel.color] if (voxel := filled.get((x, y, z))) is not None else EMPTY
            for x in columns
        )
        rows.append(f"{y:>{width}}  {row}")
    return rows


def _first_seen(
    filled: dict[VoxelKey, Voxel], xs: tuple[int, int], ys: tuple[int, int], zs: Iterable[int]
) -> list[int]:
    """Color ids in reading order: level by level, rows north to south, columns west to east."""
    seen: dict[int, None] = {}
    for z in zs:
        for y in range(ys[1], ys[0] - 1, -1):
            for x in range(xs[0], xs[1] + 1):
                if (voxel := filled.get((x, y, z))) is not None:
                    seen.setdefault(voxel.color)
    return list(seen)


def _color_name(catalog: Catalog, color_id: int) -> str:
    color = catalog.color(color_id)
    return f"{color.name} ({color_id})" if color is not None else f"color {color_id}"


def _symbols(names: Sequence[str]) -> list[str]:
    """One character per color: an initial when free, else another letter of the name."""
    pool = string.ascii_uppercase + string.ascii_lowercase + string.digits
    used: set[str] = set()
    symbols = []
    for name in names:
        words = name.split(" (")[0].replace("-", " ").split()
        preferred = [word[0].upper() for word in words] + [
            letter.upper() for word in words for letter in word[1:] if letter.isalpha()
        ]
        symbol = next(c for c in (*preferred, *pool) if c not in used and c != EMPTY)
        used.add(symbol)
        symbols.append(symbol)
    return symbols
