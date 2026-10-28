---
name: build-model
description: Design a buildable LEGO® model with bricky. Use when asked to build, model or recreate something in bricks, or to fix a bricky build script.
---

# Build a model with bricky

Work like a programmer with a compiler and a camera: write a build script, build it, read the report and look at the images, fix, and repeat.
Stop when the report says `0 errors` and the images show what you meant.
The report alone cannot tell you the second part.

## Loop

1. Plan the footprint and height in studs and plates.
   One stud is 8 mm, one plate 3.2 mm, and a brick is three plates.
1. Write `models/<name>.py` (create `models/` if needed), defining `build()` that returns a `bricky.ModelBuilder`.
   The scripts in `examples/` show the style.
1. Run `uv run bricky build models/<name>.py`.
   The command runs the script, saves the model, checks it and renders it.
1. Read the report, then open the image it names (`models/<name>.png`): perspective, front, right and top views, with rulers in studs and plates.
   Elements that diagnostics name are tinted red and labeled.
1. Fix the script and build again.

## Writing the script

```python
from bricky import ModelBuilder


def build() -> ModelBuilder:
    builder = ModelBuilder("name")
    builder.place("3001", at=(0, 0, 0), color="Red")
    return builder
```

- `at=(x, y, z)`: x east and y north in studs, z up in plates.
  `at` is the minimum corner of the rotated bounding box of what you place, a part or a whole component.
- Sizes read x by y when a part is unrotated: Brick 2 x 4 (`3001`) is 2 studs along x and 4 along y, and `R90` makes it 4 along x.
  `bricky parts` and `bricky catalog show` print sizes that way.
- `rotation`: `R0`, `R90`, `R180` or `R270` about the vertical axis, counterclockwise seen from above: `R90` rotates the part's x axis to +y.
  Any of the 24 grid rotations can be named by where the part's x and y axes go.
  To stand a part up, its top then faces: `+x+z` → -y, `-x+z` → +y, `+y+z` → +x, `-y+z` → -x; `+x-y` rotates it upside down.
- Parts that face a way say so in `uv run bricky parts slope`: unrotated, slopes fall toward -y (the front), bricks with side studs list the faces their studs are on, arches span along y.
  Rotate them with `rotation`, for example `R180` for a slope falling toward +y.
- Baseplates are half a plate thick: parts standing on one start at `z = 0.5`.
- Building sideways: a tile or plate rotated `+x+z` faces -y, so its underside grips a side stud facing -y.
  `examples/cottage.py` shows one, with an arch, a roof of slopes and a jumper.
- Use loops and functions for anything that repeats.
  Use `builder.component(...)` with `builder.instance(...)` for identical groups.
- For shapes easiest to describe as voxels (curves, domes, terrain, anything copied from a plan), build a dict `{(x, y, z): color}` and call `builder.fill(voxels, id="name")`: it lays bricks and plates in staggered courses, every part resting on the layer below.
- `uv run bricky catalog show 3001 --render` describes one part and renders it: its studs and anti-studs as maps, and, for slopes and other parts with an uneven top, its height over each square, so you see which way it falls.
  Parts the catalog lists without a shape cannot be placed; `bricky parts` lists only parts that can be.
- Find parts with `uv run bricky parts "plate 2x4"` (20 at a time; `--limit 100` lists more), or from Python with `builder.catalog.find(family="plate", size=(1, 6))`.
  List colors with `uv run bricky colors gray`, or the nearest to an RGB value with `uv run bricky colors "#F2CD37"`; names follow BrickLink, such as `Dark Bluish Gray`.
- Give important parts an `id=` of letters, digits, `.`, `_` and `-`; the report and the images label elements by id.
- To compare with a plan or another model, `from bricky import voxels`: `voxels(builder.build())` maps every filled voxel `(x, y, z)`, in studs, studs and plates, to the element's uid and its color id; `builder.catalog.resolve_color("Red").id` gives a name's id.
- `print()` freely: the build shows what the script printed.

## Reading the feedback

- Every diagnostic names its elements, what they are and the script line that placed them.
  The `by source line` summary says which lines to look at first.
- From the second build on, `since the last build` counts the elements added, removed, changed (same id and part, moved, rotated or recolored) and unchanged, by script line, and the voxels filled, emptied and recolored.
  The sheet outlines new and changed elements in purple.
  Check that an edit changed what you meant, and nothing else.
- `uv run bricky explain E301` gives the exact rule behind a code.
- Read positions off the orthographic views: their rulers use the same units as `at`.
- Look closer with `uv run bricky render models/<name>.bricky.json`, which writes `models/<name>.<view>.png` and leaves the build's sheet alone:
    - `--views front --views top` for single, larger views.
    - `--views perspective-north-west` (or `-south-west`, `-north-east`) to see the sides the south-east perspective hides.
    - `--highlight "lintel*"` or `--highlight @horseshoe` (a function of your script) to see what those parts are; everything else is rendered faintly.
    - `--clip "z<120"` (plates) or `--clip "x<10"` (studs) to clip the model open and look inside.
    - `--html` to write a viewer you can orbit in a browser.

## Building well

The advice below is yours to weigh; bricky only reports facts.

- Stagger joints between courses, like a brick wall, so every brick bridges the ones below it.
- Overhanging parts must reach back over something that holds them: E301 reports anything that is not connected to the ground through studs.
- Compare the images with the subject: proportions, silhouette from each side, colors.
  A model with no errors can still look wrong.
