# Copyright 2026 Maxence Faldor
"""A standalone viewer: one HTML file people open in a browser to orbit a model.

The page embeds the scene and bricky's viewer module, and loads three.js from jsDelivr, so it stays
small and needs a network connection when opened. Renders for agents run offline in headless
Chromium instead (see :mod:`bricky.render.browser`).
"""

import json
from functools import cache
from html import escape
from importlib.resources import files
from pathlib import Path
from string import Template
from typing import Final

from bricky.files import write_file
from bricky.render.scene import Scene

THREE_VERSION: Final = "0.186.1"
"""The three.js version vendored for renders and loaded by the standalone viewer."""

_THREE_PACKAGE: Final = f"https://cdn.jsdelivr.net/npm/three@{THREE_VERSION}/"
"""The three.js package on jsDelivr, which the standalone viewer loads."""

_PAGE: Final = Template("""\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>
  :root {
    color-scheme: light; --ink: #1f2328; --quiet: #59636e; --line: #d0d7de; --paper: #f6f7f9;
  }
  html, body { height: 100%; margin: 0; }
  body {
    display: grid; grid-template-rows: auto 1fr; background: #ffffff; color: var(--ink);
    font: 14px system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }
  header {
    display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px;
    padding: 10px 16px; border-bottom: 1px solid var(--line);
  }
  h1 { margin: 0; font-size: 15px; font-weight: 600; flex: 1 1 320px; }
  nav { display: flex; gap: 4px; }
  button {
    font: inherit; padding: 4px 10px; border: 1px solid var(--line); border-radius: 6px;
    background: #ffffff; color: var(--ink); cursor: pointer;
  }
  button:focus-visible, input:focus-visible { outline: 2px solid #0969da; outline-offset: 2px; }
  label { display: flex; align-items: center; gap: 8px; color: var(--quiet); }
  output { min-width: 7ch; font-variant-numeric: tabular-nums; color: var(--ink); }
  #stage { position: relative; min-height: 0; background: var(--paper); }
  #stage canvas { display: block; width: 100%; height: 100%; touch-action: none; }
</style>
<script type="importmap">$imports</script>
</head>
<body>
<header>
  <h1>$heading</h1>
  <nav aria-label="Views">
    <button type="button" data-view="perspective">Perspective</button>
    <button type="button" data-view="front">Front</button>
    <button type="button" data-view="right">Right</button>
    <button type="button" data-view="top">Top</button>
  </nav>
  <label for="clip">Clip at
    <input id="clip" type="range" min="1" step="1"> <output id="clip-height"></output>
  </label>
</header>
<main id="stage" aria-label="3D view of the model"></main>
<script type="application/json" id="scene">$scene</script>
<script type="module">
$viewer
const scene = JSON.parse(document.getElementById("scene").textContent);
const viewer = await mount(document.getElementById("stage"), scene);
for (const button of document.querySelectorAll("[data-view]")) {
  button.addEventListener("click", () => viewer.look(button.dataset.view));
}
const clip = document.getElementById("clip");
const height = document.getElementById("clip-height");
clip.max = String(viewer.topPlates);
clip.value = clip.max;
const show = () => {
  height.textContent = clip.value + " plates";
  viewer.clip(Number(clip.value));
};
clip.addEventListener("input", show);
show();
</script>
</body>
</html>
""")


@cache
def _viewer_source() -> str:
    return (
        files("bricky.render")
        .joinpath("assets", "viewer.js")
        .read_text(encoding="utf-8")
    )


def write_html(scene: Scene, path: Path) -> Path:
    """Write a standalone HTML viewer for a scene and return its path.

    Raises:
        BrickyError: If the file cannot be written.
    """
    imports = {
        "imports": {
            "three": _THREE_PACKAGE + "build/three.module.js",
            "three/addons/": _THREE_PACKAGE + "examples/jsm/",
        }
    }
    page = _PAGE.substitute(
        title=escape(f"{scene.name} - bricky"),
        heading=escape(scene.title),
        imports=json.dumps(imports),
        scene=scene.model_dump_json().replace("</", "<\\/"),
        viewer=_viewer_source(),
    )
    return write_file(path, page.encode())
