# Copyright 2026 Maxence Faldor
"""A standalone viewer: one HTML file people open in a browser to inspect a model.

The page holds the scene, the viewer's modules and its styles, and loads three.js from
jsDelivr, so it stays small and needs a network connection when opened. Renders for
agents run offline in headless Chromium instead (see :mod:`bricky.render.browser`).

The viewer is a core, in ``assets/app``, plus components, in ``assets/components``: the
title card, the view bar, the parts panel and others. :data:`COMPONENTS` lists the
components a page loads, so removing one is removing its name there and its file.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Sequence
from functools import cache
from html import escape
from importlib.resources import files
from pathlib import Path
from string import Template
from typing import Final, Literal

from pydantic import BaseModel, Field

from bricky.catalog import Catalog
from bricky.errors import BrickyError
from bricky.exports import FORMATS, model_lots
from bricky.files import write_file
from bricky.model import Model
from bricky.render.scene import Scene

THREE_VERSION: Final = "0.186.1"
"""The three.js version vendored for renders and loaded by the standalone viewer."""

_THREE_PACKAGE: Final = f"https://cdn.jsdelivr.net/npm/three@{THREE_VERSION}/"
"""The three.js package on jsDelivr, which the standalone viewer loads."""

CORE: Final = ("app/app.js", "app/engine.js", "app/shell.js", "app/icons.js")
"""The viewer's core modules, under ``assets``."""

COMPONENTS: Final = (
    "title",
    "views",
    "compass",
    "inspector",
    "parts",
    "checks",
    "clip",
    "instructions",
    "fit",
    "screenshot",
    "fullscreen",
    "help",
)
"""The components a viewer loads, in order, from ``assets/components/<name>.js``."""


class Download(BaseModel):
    """A file the viewer offers to download, such as a BrickLink Wanted List."""

    title: str = Field(description="The format's name.")
    file: str = Field(description="The file name to save as.")
    media_type: str
    usage: str = Field(description="How to use the file in its tool.")
    text: str = Field(description="The file's contents.")


def downloads(model: Model, catalog: Catalog) -> list[Download]:
    """Return every export of a model, for a viewer to offer.

    A model with a part or color the catalog lacks gets none: an export lists only
    what it states exactly.
    """
    try:
        lots = model_lots(model, catalog)
    except BrickyError:
        return []
    return [
        Download(
            title=exporter.title,
            file=model.name + exporter.suffix,
            media_type=exporter.media_type,
            usage=exporter.usage,
            text=exporter.write(lots).decode(),
        )
        for exporter in FORMATS.values()
    ]


_PAGE: Final = Template("""\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>$title</title>
<style>
$style
</style>
<script type="importmap">$imports</script>
</head>
<body>
<div class="app" id="app" data-state="loading">
  <div class="splash" role="status">
    <div class="spinner" aria-hidden="true"></div>
    <p>Loading the 3D view</p>
  </div>
</div>
<script type="application/json" id="scene">$scene</script>
<script type="application/json" id="viewer">$options</script>
<script type="module">
const root = document.getElementById("app");
const read = (id) => JSON.parse(document.getElementById(id).textContent);
try {
  const options = read("viewer");
  const { start } = await import("bricky/app/app.js");
  const components = await Promise.all(
    options.components.map((name) => import("bricky/components/" + name + ".js")),
  );
  window.bricky = await start(root, read("scene"), {
    ...options,
    components: components.map((module) => module.default),
  });
} catch (error) {
  console.error(error);
  root.dataset.state = "failed";
  const offline = /import|fetch|module/i.test(String(error && error.message));
  root.querySelector(".splash p").textContent = offline
    ? "The 3D view needs three.js from cdn.jsdelivr.net, which did not load. "
      + "Check the network connection, then reload the page."
    : "The 3D view could not start: " + error.message;
}
</script>
</body>
</html>
""")


@cache
def _asset(name: str) -> str:
    return (
        files("bricky.render")
        .joinpath("assets", *name.split("/"))
        .read_text(encoding="utf-8")
    )


def _module(name: str) -> str:
    """A module as a data URL, so the page holds every module and fetches only three."""
    encoded = base64.b64encode(_asset(name).encode()).decode("ascii")
    return f"data:text/javascript;base64,{encoded}"


_SLUG_SEPARATOR: Final = re.compile(r"[-_\s]+")


def heading_of(name: str) -> str:
    """A model's name as a heading: ``japanese-garden`` becomes ``Japanese garden``."""
    words = _SLUG_SEPARATOR.sub(" ", name).strip()
    return words[:1].upper() + words[1:] if words else "Model"


def write_html(
    scene: Scene,
    path: Path,
    downloads: Sequence[Download] = (),
    *,
    heading: str | None = None,
    mode: Literal["explore", "instructions"] = "explore",
) -> Path:
    """Write a standalone HTML viewer for a scene and return its path.

    Args:
        scene: The scene to view.
        path: The file to write.
        downloads: Files the viewer offers to download, such as the model's exports.
        heading: The model's name as people read it; by default, the model's name with
            spaces for hyphens and a capital first letter.
        mode: What the page opens on: the model to explore, or its first building
            step, which needs a scene with steps.

    Raises:
        BrickyError: If the file cannot be written.
    """
    imports = {
        "three": _THREE_PACKAGE + "build/three.module.js",
        "three/addons/": _THREE_PACKAGE + "examples/jsm/",
        "bricky/viewer.js": _module("viewer.js"),
        **{f"bricky/{name}": _module(name) for name in CORE},
        **{
            f"bricky/components/{name}.js": _module(f"components/{name}.js")
            for name in COMPONENTS
        },
    }
    title = heading or heading_of(scene.name)
    options = {
        "heading": title,
        "components": list(COMPONENTS),
        "downloads": [download.model_dump() for download in downloads],
        "mode": mode,
    }
    page = _PAGE.substitute(
        title=escape(f"{title} · bricky"),
        style=_asset("app/style.css"),
        imports=json.dumps({"imports": imports}),
        scene=scene.model_dump_json().replace("</", "<\\/"),
        options=json.dumps(options).replace("</", "<\\/"),
    )
    return write_file(path, page.encode())
