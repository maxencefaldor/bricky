"""Renders: pictures of a model, for the agent that builds it and the people who review it.

A render is the richest feedback a build gets. The checks say whether a model is valid; the
pictures show whether it looks like what was meant. :func:`build_scene` resolves a model into plain
data, :class:`Renderer` draws it with three.js in headless Chromium, and :func:`write_html` writes a
standalone viewer people can orbit.

Every orthographic view carries rulers in studs and plates, so a position read off the picture is a
position to write in the build script.
"""

from bricky.render.browser import Renderer
from bricky.render.html import THREE_VERSION, write_html
from bricky.render.scene import Clip, Flag, Label, Mark, Scene, SceneColor, View, build_scene

__all__ = [
    "THREE_VERSION",
    "Clip",
    "Flag",
    "Label",
    "Mark",
    "Renderer",
    "Scene",
    "SceneColor",
    "View",
    "build_scene",
    "write_html",
]
