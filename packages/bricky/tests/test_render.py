import asyncio
import json
import struct

import pytest

from bricky import BrickyError, ModelBuilder, Settings, check_model, default_catalog
from bricky.geometry import Box, Vector
from bricky.render import Clip, Flag, Renderer, View, build_scene, write_html
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


def test_clips_read_studs_and_plates():
    assert Clip.parse("z<130") == Clip(axis="z", keep="below", value=130 * PLATE)
    assert Clip.parse(" x >= 2.5 ") == Clip(axis="x", keep="above", value=50)
    assert str(Clip.parse("y<8")) == "y < 8"
    with pytest.raises(BrickyError, match="cannot read clip"):
        Clip.parse("height below 3")
    with pytest.raises(BrickyError, match="not a whole number"):
        Clip.parse("x<0.01")


def test_faces_pressed_against_opaque_neighbours_are_left_out():
    lower = Box(Vector(0, 0, 0), Vector(40, 80, 24))
    upper = Box(Vector(0, 0, 24), Vector(40, 80, 48))
    offset = Box(Vector(20, 0, 48), Vector(60, 80, 72))
    masks = visible_faces([lower, upper, offset], [True, True, True])
    top, bottom = 1 << 5, 1 << 4
    assert masks[0] == ALL_FACES & ~top
    assert masks[1] == ALL_FACES & ~bottom  # its top is only half covered
    assert masks[2] & bottom
    # A transparent neighbour hides nothing.
    assert visible_faces([lower, upper], [True, False])[0] == ALL_FACES


def test_scenes_drop_seated_studs_and_keep_exposed_ones():
    scene = build_scene(stack().build(), default_catalog())
    assert len(scene.studs) == 8
    assert {stud[4] for stud in scene.studs} == {scene.uids.index("top")}
    assert scene.bounds == (0, 0, 0, 2 * STUD, 4 * STUD, 6 * PLATE + STUD_HEIGHT)  # stud tips
    assert scene.title.startswith("stack: 2 elements, 2 x 4 studs, 6 plates tall")


def test_scenes_mark_the_parts_diagnostics_name():
    builder = stack()
    builder.place("3022", at=(9, 9, 9), color="Tan", id="float")
    model = builder.build()
    report = check_model(model, settings=Settings())
    scene = build_scene(model, default_catalog(), report=report)
    flags = dict(zip(scene.uids, (part[1] for part in scene.parts), strict=True))
    assert flags["float"] & Flag.ERROR
    assert not flags["top"] & Flag.ERROR
    assert [label.text for label in scene.labels] == ["E301 float"]
    assert [mark.text for mark in scene.marks] == ["E301"]
    assert "1 errors" in scene.title


def test_highlights_select_by_uid_or_script_function():
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
        flags = dict(zip(scene.uids, (part[1] for part in scene.parts), strict=True))
        assert flags["lintel1"] & Flag.HIGHLIGHT
        assert flags["post"] & Flag.GHOST
    with pytest.raises(BrickyError, match="matches no part"):
        build_scene(model, default_catalog(), highlight=["missing*"])
    with pytest.raises(BrickyError, match="needs the model's source map"):
        build_scene(model, default_catalog(), highlight=["@lintels"])


def test_scenes_mark_the_parts_new_or_changed_since_the_last_build():
    scene = build_scene(stack().build(), default_catalog(), changed=["top"])
    flags = dict(zip(scene.uids, (part[1] for part in scene.parts), strict=True))
    assert flags["top"] == Flag.CHANGED
    assert flags["bottom"] == 0


def test_clips_frame_the_part_left_to_see():
    scene = build_scene(stack().build(), default_catalog(), clips=[Clip.parse("z<3")])
    assert scene.bounds[5] == 3 * PLATE
    with pytest.raises(BrickyError, match="leaves nothing"):
        build_scene(stack().build(), default_catalog(), clips=[Clip.parse("z>40")])


def test_the_standalone_viewer_embeds_the_scene(tmp_path):
    scene = build_scene(stack().build(), default_catalog(), cull=False)
    path = write_html(scene, tmp_path / "stack.html")
    page = path.read_text()
    assert '"three": "https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.module.js"' in page
    start = page.index('<script type="application/json" id="scene">') + len(
        '<script type="application/json" id="scene">'
    )
    embedded = json.loads(page[start : page.index("</script>", start)])
    assert embedded["uids"] == ["bottom", "top"]
    assert "export async function mount" in page


def test_the_renderer_draws_every_view_at_the_requested_size():
    scene = build_scene(stack().build(), default_catalog())
    views = [View.SHEET, View.FRONT, View.TOP]

    async def draw() -> list[bytes]:
        async with Renderer(Settings().render_browser) as renderer:
            first = await renderer.render(scene, views, width=640, height=480)
            again = await renderer.render(scene, [View.ISO], width=320, height=240)
        return [*first, *again]

    images = asyncio.run(draw())
    assert [png_size(image) for image in images] == [(640, 480)] * 3 + [(320, 240)]
    assert all(len(image) > 5000 for image in images)


def test_parts_that_are_not_boxes_become_shapes():
    builder = ModelBuilder("mixed")
    builder.place("3001", at=(0, 0, 0), color="Red", id="brick")
    builder.place("3039", at=(0, 4, 0), color="Red", id="slope")  # Slope 45 2 x 2
    builder.place("3659", at=(3, 0, 0), color="Tan", id="arch")  # Arch 1 x 4
    scene = build_scene(builder.build(), default_catalog())
    assert {box[6] for box in scene.boxes} == {scene.uids.index("brick")}
    shapes = {scene.uids[s.part]: s for s in scene.shapes}
    assert set(shapes) == {"slope", "arch"}
    assert len(shapes["slope"].faces) == 7  # a five-sided profile, extruded
    arch = shapes["arch"]
    # The arch is two legs and a dozen slices; the faces they share are inside, and left out.
    assert len({frozenset(face) for face in arch.faces}) == len(arch.faces)
    corners = len(arch.vertices) // 3
    assert len(arch.edges) % 2 == 0
    assert all(0 <= corner < corners for corner in arch.edges)


def test_shapes_are_drawn_as_their_own_profile():
    def front(part: str) -> bytes:
        builder = ModelBuilder("one")
        builder.place(part, at=(0, 0, 0), color="Red")
        scene = build_scene(builder.build(), default_catalog())

        async def draw() -> bytes:
            async with Renderer(Settings().render_browser) as renderer:
                (image,) = await renderer.render(scene, [View.RIGHT], width=400, height=300)
            return image

        return asyncio.run(draw())

    # A Slope 45 2 x 2 and a Brick 2 x 2 share their bounding box, but not their side view.
    assert front("3039") != front("3003")
