# Copyright 2026 Maxence Faldor
"""Write a standalone 3D viewer of every example the docs' gallery shows.

Run from the repository root: ``uv run python docs/gallery.py``, or name examples, such
as ``cottage``, to write only those. The gallery page's links to ``gallery/<name>.html``
choose the examples, and each script in ``examples`` runs in its own process. Its viewer
goes to ``docs/gallery/<name>.html``, named after the script with hyphens, such as
``elizabeth-tower.html``. The viewers mark what the checks find, as
``bricky render --html`` does. Each viewer loads three.js from jsDelivr when opened.

Writing a viewer needs no browser, so the docs workflow runs this script on a plain
runner. The examples use the sample catalog, so every machine writes the same viewers.
The viewers are build output, left out of the repository.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import time
from pathlib import Path
from typing import Final

from bricky import Settings, check_model, default_catalog
from bricky.catalog import SAMPLE_CATALOG
from bricky.render import build_scene, write_html
from bricky.service import run_script

ROOT: Final = Path(__file__).resolve().parent.parent
EXAMPLES: Final = ROOT / "examples"
GALLERY: Final = ROOT / "docs" / "gallery"
GALLERY_PAGE: Final = ROOT / "docs" / "gallery.md"
VIEWER_LINK: Final = re.compile(r"\(gallery/([a-z0-9-]+)\.html\)")
"""A link from the gallery page to a viewer, such as ``(gallery/cottage.html)``."""


def gallery_scripts() -> list[Path]:
    """Return the example scripts whose viewers the gallery page links to, in order."""
    names = dict.fromkeys(VIEWER_LINK.findall(GALLERY_PAGE.read_text(encoding="utf-8")))
    return [EXAMPLES / (name.replace("-", "_") + ".py") for name in names]


def viewer_path(script: Path) -> Path:
    """Return where the viewer of an example script goes."""
    return GALLERY / (script.stem.replace("_", "-") + ".html")


async def write_viewer(script: Path, settings: Settings) -> Path:
    """Build an example in its own process, check it and write its viewer.

    The viewer keeps every face of the model, as ``bricky render --html`` does.
    Clipping the model in the browser can bring buried faces into view.
    """
    run = await run_script(script, settings)
    catalog = default_catalog()
    report = await asyncio.to_thread(
        check_model,
        run.model,
        provenance=run.provenance,
        catalog=catalog,
        settings=settings,
    )
    scene = await asyncio.to_thread(
        build_scene,
        run.model,
        catalog,
        provenance=run.provenance,
        report=report,
        cull=False,
    )
    return await asyncio.to_thread(write_html, scene, viewer_path(script))


async def main() -> None:
    """Write the viewer of every example, or of the examples the command line names."""
    # Example scripts use the sample catalog, as the docs' images do.
    os.environ["BRICKY_CATALOG"] = str(SAMPLE_CATALOG)
    settings = Settings()
    wanted = set(sys.argv[1:])
    scripts = [
        script
        for script in gallery_scripts()
        if not wanted or script.stem in wanted or viewer_path(script).stem in wanted
    ]
    started = time.perf_counter()
    for script in scripts:
        begun = time.perf_counter()
        path = await write_viewer(script, settings)
        print(
            f"wrote {path.relative_to(ROOT)}: {path.stat().st_size / 1000:,.0f} kB "
            f"in {time.perf_counter() - begun:.1f} s"
        )
    print(f"wrote {len(scripts)} viewers in {time.perf_counter() - started:.1f} s")


if __name__ == "__main__":
    asyncio.run(main())
