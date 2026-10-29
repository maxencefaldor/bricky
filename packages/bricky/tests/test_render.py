# Copyright 2026 Maxence Faldor

from __future__ import annotations

import asyncio
import base64
import json
import struct
from importlib.resources import files
from pathlib import Path
from typing import cast

import pytest
from playwright.async_api import Route, async_playwright

from bricky import BrickyError, ModelBuilder, Settings, check_model, default_catalog
from bricky.geometry import Box, Vector
from bricky.render import (
    COMPONENTS,
    THREE_VERSION,
    Clip,
    Flag,
    Renderer,
    View,
    build_scene,
    downloads,
    write_html,
)
from bricky.render.scene import ALL_FACES, visible_faces
from bricky.units import PLATE, STUD, STUD_HEIGHT


def stack() -> ModelBuilder:
    builder = ModelBuilder("stack")
    builder.place("3001", at=(0, 0, 0), color="Red", id="bottom")
    builder.place("3001", at=(0, 0, 3), color="Blue", id="top")
    return builder


def png_size(data: bytes) -> tuple[int, int]:
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_clips_read_studs_and_plates() -> None:
    assert Clip.parse("z<130") == Clip(axis="z", keep="below", value=130 * PLATE)
    assert Clip.parse(" x >= 2.5 ") == Clip(axis="x", keep="above", value=50)
    assert str(Clip.parse("y<8")) == "y < 8"
    with pytest.raises(BrickyError, match="cannot read clip"):
        Clip.parse("height below 3")
    with pytest.raises(BrickyError, match="not a whole number"):
        Clip.parse("x<0.01")


def test_faces_pressed_against_opaque_neighbors_are_left_out() -> None:
    lower = Box(Vector(0, 0, 0), Vector(40, 80, 24))
    upper = Box(Vector(0, 0, 24), Vector(40, 80, 48))
    offset = Box(Vector(20, 0, 48), Vector(60, 80, 72))
    masks = visible_faces([lower, upper, offset], [True, True, True])
    top, bottom = 1 << 5, 1 << 4
    assert masks[0] == ALL_FACES & ~top
    assert masks[1] == ALL_FACES & ~bottom  # its top is only half covered
    assert masks[2] & bottom
    # A transparent neighbor hides nothing.
    assert visible_faces([lower, upper], [True, False])[0] == ALL_FACES


def test_scenes_drop_seated_studs_and_keep_exposed_ones() -> None:
    scene = build_scene(stack().build(), default_catalog())
    assert len(scene.studs) == 8
    assert {stud[4] for stud in scene.studs} == {scene.uids.index("top")}
    assert scene.bounds == (
        0,
        0,
        0,
        2 * STUD,
        4 * STUD,
        6 * PLATE + STUD_HEIGHT,
    )  # stud tips
    assert scene.title.startswith("stack: 2 elements, 2 x 4 studs, 6 plates tall")


def test_scenes_mark_the_parts_diagnostics_name() -> None:
    builder = stack()
    builder.place("3022", at=(9, 9, 9), color="Tan", id="float")
    model = builder.build()
    report = check_model(model, settings=Settings())
    scene = build_scene(model, default_catalog(), report=report)
    flags = dict(
        zip(scene.uids, (element[1] for element in scene.elements), strict=True)
    )
    assert flags["float"] & Flag.ERROR
    assert not flags["top"] & Flag.ERROR
    assert [label.text for label in scene.labels] == ["E301 float"]
    assert [mark.text for mark in scene.marks] == ["E301"]
    assert "check: 1 error, 0 warnings" in scene.title


def test_highlights_select_by_uid_or_script_function() -> None:
    builder = ModelBuilder("m")

    def lintels() -> None:
        builder.place("3710", at=(0, 0, 3), color="Tan", id="lintel1")

    builder.place("3001", at=(0, 0, 0), color="Red", id="post")
    lintels()
    model, provenance = builder.build(), builder.provenance()
    by_uid = build_scene(model, default_catalog(), highlight=["lin*"])
    by_function = build_scene(
        model, default_catalog(), provenance=provenance, highlight=["@lintels"]
    )
    for scene in (by_uid, by_function):
        flags = dict(
            zip(scene.uids, (element[1] for element in scene.elements), strict=True)
        )
        assert flags["lintel1"] & Flag.HIGHLIGHT
        assert flags["post"] & Flag.GHOST
    with pytest.raises(BrickyError, match="matches no element"):
        build_scene(model, default_catalog(), highlight=["missing*"])
    with pytest.raises(BrickyError, match="needs the model's source map"):
        build_scene(model, default_catalog(), highlight=["@lintels"])


def test_scenes_mark_the_parts_new_or_changed_since_the_last_build() -> None:
    scene = build_scene(stack().build(), default_catalog(), changed=["top"])
    flags = dict(
        zip(scene.uids, (element[1] for element in scene.elements), strict=True)
    )
    assert flags["top"] == Flag.CHANGED
    assert flags["bottom"] == 0


def test_clips_frame_the_part_left_to_see() -> None:
    scene = build_scene(stack().build(), default_catalog(), clips=[Clip.parse("z<3")])
    assert scene.bounds[5] == 3 * PLATE
    with pytest.raises(BrickyError, match="leaves nothing"):
        build_scene(stack().build(), default_catalog(), clips=[Clip.parse("z>40")])


def test_the_standalone_viewer_embeds_the_scene_and_its_modules(
    tmp_path: Path,
) -> None:
    model = stack().build()
    scene = build_scene(model, default_catalog(), cull=False)
    path = write_html(
        scene, tmp_path / "stack.html", downloads(model, default_catalog())
    )
    page = path.read_text()
    imports = json.loads(embedded(page, "importmap"))["imports"]
    assert imports["three"] == (
        "https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.module.js"
    )
    # Every module of the viewer travels inside the page.
    core = base64.b64decode(imports["bricky/app/app.js"].split(",", 1)[1]).decode()
    assert "export async function start" in core
    assert {f"bricky/components/{name}.js" for name in COMPONENTS} <= set(imports)
    assert json.loads(embedded(page, "application/json", "scene"))["uids"] == [
        "bottom",
        "top",
    ]
    options = json.loads(embedded(page, "application/json", "viewer"))
    assert options["heading"] == "Stack"
    assert options["components"] == list(COMPONENTS)
    [wanted] = options["downloads"]
    assert wanted["file"] == "stack.wanted.xml"
    assert "<ITEMID>3001</ITEMID>" in wanted["text"]
    assert "<title>Stack · bricky</title>" in page


def embedded(page: str, kind: str, element_id: str | None = None) -> str:
    """The text of the page's script of a type, and of an id when one is given."""
    tag = (
        f'<script type="{kind}"'
        + (f' id="{element_id}"' if element_id is not None else "")
        + ">"
    )
    start = page.index(tag) + len(tag)
    return page[start : page.index("</script>", start)]


def test_scenes_carry_what_the_viewer_shows() -> None:
    builder = ModelBuilder("named")
    builder.place("3001", at=(0, 0, 0), color="Red", id="base")
    builder.place("3001", at=(0, 0, 3), color="Red", id="top")
    builder.place("3022", at=(9, 9, 9), color="Blue", id="floating")
    model = builder.build()
    report = check_model(model)
    scene = build_scene(model, default_catalog(), report=report)
    assert [part.id for part in scene.parts] == ["3001", "3022"]
    assert scene.summary.elements == 3
    assert scene.summary.errors == report.errors > 0
    [floats] = [d for d in scene.diagnostics if d.code == "E301"]
    assert floats.kind == "error"
    assert [scene.uids[i] for i in floats.elements] == ["floating"]
    color, _, part, line = scene.elements[scene.uids.index("floating")]
    assert scene.colors[color].name == "Blue"
    assert scene.parts[part].name == "Plate 2 x 2"
    assert line == -1  # no source map, no script line
    assert scene.lines == []


def test_the_viewer_shows_the_model_and_names_what_is_clicked(tmp_path: Path) -> None:
    model = stack().build()
    scene = build_scene(model, default_catalog(), cull=False)
    path = write_html(
        scene, tmp_path / "stack.html", downloads(model, default_catalog())
    )
    three = files("bricky.render").joinpath("assets", "three")
    cdn = f"https://cdn.jsdelivr.net/npm/three@{THREE_VERSION}/"

    async def serve(route: Route) -> None:
        name = route.request.url.removeprefix(cdn).removeprefix("build/")
        await route.fulfill(
            body=three.joinpath(*name.split("/")).read_bytes(),
            content_type="text/javascript",
        )

    async def inspect() -> tuple[dict[str, object], dict[str, int]]:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=Settings().render_browser,
                args=["--enable-unsafe-swiftshader"],
            )
            page = await browser.new_page(viewport={"width": 640, "height": 480})
            problems: list[str] = []
            page.on("pageerror", lambda error: problems.append(str(error)))
            await page.route(cdn + "**", serve)
            await page.goto(path.as_uri())
            await page.wait_for_function(
                "() => document.getElementById('app').dataset.state !== 'loading'"
            )
            image = base64.b64encode(await page.screenshot()).decode()
            colors = cast("dict[str, int]", await page.evaluate(COUNT_COLORS, image))
            await page.mouse.click(320, 240)
            await page.wait_for_selector(".info-card:not([hidden])")
            await page.keyboard.press("p")
            found: dict[str, object] = {
                "state": await page.get_attribute("#app", "data-state"),
                "heading": await page.text_content(".title-card h1"),
                "selected": await page.text_content(".info-card .name strong"),
                "lots": await page.locator(".parts li").count(),
                "offer": await page.text_content(".parts .download strong"),
                "problems": problems,
            }
            await browser.close()
            return found, colors

    found, colors = asyncio.run(inspect())
    # The model, a red brick under a blue one, fills the middle of the stage.
    assert colors["red"] > 2000
    assert colors["blue"] > 2000
    assert found == {
        "state": "ready",
        "heading": "Stack",
        "selected": "Brick 2 x 4",
        "lots": 2,
        "offer": "BrickLink Wanted List",
        "problems": [],
    }


COUNT_COLORS = """async (png) => {
  const image = new Image();
  image.src = "data:image/png;base64," + png;
  await image.decode();
  const canvas = new OffscreenCanvas(200, 200);
  const context = canvas.getContext("2d");
  context.drawImage(image, 220, 140, 200, 200, 0, 0, 200, 200);
  const pixels = context.getImageData(0, 0, 200, 200).data;
  let red = 0, blue = 0;
  for (let i = 0; i < pixels.length; i += 4) {
    const [r, g, b] = [pixels[i], pixels[i + 1], pixels[i + 2]];
    if (r > g + 60 && r > b + 60) red += 1;
    if (b > r + 60 && b > g + 30) blue += 1;
  }
  return { red, blue };
}"""
"""Count the strongly red and blue pixels in the middle of a 640 x 480 screenshot."""


def test_the_renderer_renders_every_view_at_the_requested_size() -> None:
    scene = build_scene(stack().build(), default_catalog())
    views = [View.SHEET, View.FRONT, View.TOP]

    async def render_images() -> list[bytes]:
        async with Renderer(Settings().render_browser) as renderer:
            first = await renderer.render(scene, views, width=640, height=480)
            again = await renderer.render(
                scene, [View.PERSPECTIVE], width=320, height=240
            )
        return [*first, *again]

    images = asyncio.run(render_images())
    assert [png_size(image) for image in images] == [(640, 480)] * 3 + [(320, 240)]
    assert all(len(image) > 5000 for image in images)


def test_the_perspectives_from_each_corner_render_different_images() -> None:
    builder = ModelBuilder("corner")
    builder.place("3001", at=(0, 0, 0), color="Red")
    builder.place(
        "3003", at=(0, 0, 3), color="Blue"
    )  # off center, so every corner differs
    scene = build_scene(builder.build(), default_catalog())
    corners = [view for view in View if view.value.startswith("perspective")]

    async def render_images() -> list[bytes]:
        async with Renderer(Settings().render_browser) as renderer:
            return await renderer.render(scene, corners, width=320, height=240)

    images = asyncio.run(render_images())
    assert len(corners) == 4
    assert all(png_size(image) == (320, 240) for image in images)
    assert len(set(images)) == len(corners)


def test_elements_that_are_not_boxes_become_meshes() -> None:
    builder = ModelBuilder("mixed")
    builder.place("3001", at=(0, 0, 0), color="Red", id="brick")
    builder.place("3039", at=(0, 4, 0), color="Red", id="slope")  # Slope 45 2 x 2
    builder.place("3659", at=(3, 0, 0), color="Tan", id="arch")  # Arch 1 x 4
    scene = build_scene(builder.build(), default_catalog())
    assert {box[6] for box in scene.boxes} == {scene.uids.index("brick")}
    meshes = {scene.uids[mesh.element]: mesh for mesh in scene.meshes}
    assert set(meshes) == {"slope", "arch"}
    assert len(meshes["slope"].faces) == 7  # a five-sided profile, extruded
    arch = meshes["arch"]
    # The arch is two legs and a dozen slices; its mesh leaves out the inner faces they
    # share.
    assert len({frozenset(face) for face in arch.faces}) == len(arch.faces)
    corners = len(arch.vertices) // 3
    assert len(arch.edges) % 2 == 0
    assert all(0 <= corner < corners for corner in arch.edges)


def test_meshes_are_rendered_as_their_own_profile() -> None:
    def front(part: str) -> bytes:
        builder = ModelBuilder("one")
        builder.place(part, at=(0, 0, 0), color="Red")
        scene = build_scene(builder.build(), default_catalog())

        async def render_images() -> bytes:
            async with Renderer(Settings().render_browser) as renderer:
                (image,) = await renderer.render(
                    scene, [View.RIGHT], width=400, height=300
                )
            return image

        return asyncio.run(render_images())

    # A Slope 45 2 x 2 and a Brick 2 x 2 share their bounding box, but not their side
    # view.
    assert front("3039") != front("3003")
