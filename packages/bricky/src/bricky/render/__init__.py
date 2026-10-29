# Copyright 2026 Maxence Faldor
"""Rendering: images of a model, for the agent building it and the people reviewing it.

A render is the richest feedback a build gets. The report states whether a model is
valid; the images show whether it looks as intended. :func:`build_scene` resolves a
model into a scene of plain data, :class:`Renderer` renders its views with three.js in
headless Chromium, and :func:`write_html` writes a standalone viewer that people can
orbit and inspect.

Every orthographic view carries rulers in studs and plates, so a position read off the
image is a position to write in the build script.
"""

from __future__ import annotations

from bricky.render.browser import Renderer
from bricky.render.html import (
    COMPONENTS,
    THREE_VERSION,
    Download,
    downloads,
    write_html,
)
from bricky.render.scene import (
    Clip,
    Flag,
    Label,
    Mark,
    Mesh,
    Scene,
    SceneColor,
    SceneDiagnostic,
    ScenePart,
    SceneStep,
    Summary,
    View,
    build_scene,
)

__all__ = [
    "COMPONENTS",
    "THREE_VERSION",
    "Clip",
    "Download",
    "Flag",
    "Label",
    "Mark",
    "Mesh",
    "Renderer",
    "Scene",
    "SceneColor",
    "SceneDiagnostic",
    "ScenePart",
    "SceneStep",
    "Summary",
    "View",
    "build_scene",
    "downloads",
    "write_html",
]
