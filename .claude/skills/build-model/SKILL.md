---
name: build-model
description: Design a buildable LEGO® model with bricky. Use when asked to build, model or recreate something in bricks, or to fix a bricky build script.
---

# Build a model with bricky

Work in a loop: write a build script, build it, read the report and look at the images, fix the script, and build again.
Stop when the report says `0 errors`, you have weighed every warning, and the images show what you meant.
The report alone cannot tell you the last part.

## Loop

1. Plan the footprint and height in studs and plates.
   One stud is 8 mm, one plate 3.2 mm, and a brick is three plates.
1. Write `models/<name>.py` (create `models/` if needed), defining `build()` that returns a `bricky.ModelBuilder`.
   The scripts in `examples/`, also [on GitHub](https://github.com/maxencefaldor/bricky/tree/main/examples), show the style.
1. Run `uv run bricky build models/<name>.py`.
   The command runs the script, saves the model, checks it and renders it.
   Where bricky is installed as a tool or with pip, run `bricky` without `uv run`.
1. Read the report, then open the image it names (`models/<name>.png`): perspective, front, right and top views, with rulers in studs and plates.
   Elements that errors name are tinted red, those that warnings name orange, and each diagnostic labels its first element with its rule.
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
  The corner `at` is the minimum corner of the rotated bounding box of what you place, a part or a whole component.
- Sizes read x by y when a part is unrotated: Brick 2 x 4 (`3001`) is 2 studs along x and 4 along y.
  The rotation `R90` makes it 4 along x.
  The commands `bricky parts` and `bricky catalog show` print sizes that way.
- `rotation`: `R0`, `R90`, `R180` or `R270` about the vertical axis, counterclockwise seen from above: `R90` rotates the part's x axis to +y.
  Any of the 24 grid rotations can be named by where the part's x and y axes go.
  To stand a part up, its top then faces: `+x+z` → -y, `-x+z` → +y, `+y+z` → +x, `-y+z` → -x; `+x-y` rotates it upside down.
- Parts that face a way say so in `uv run bricky parts slope`.
  Unrotated, slopes fall toward -y (the front), arches span along y, and bricks with side studs list the faces their studs are on.
  Rotate them with `rotation`, for example `R180` for a slope falling toward +y.
- Baseplates are half a plate thick: parts standing on one start at `z = 0.5`.
- Building sideways: a tile or plate rotated `+x+z` faces -y, so its underside grips a side stud facing -y.
  The example `examples/cottage.py` shows one, with an arch, a roof of slopes and a jumper.
- Use loops and functions for anything that repeats.
  Use `builder.component(...)` with `builder.instance(...)` for identical groups.
- For shapes easiest to describe as voxels (curves, domes, terrain, anything copied from a plan), build a dict `{(x, y, z): color}`.
  Then call `builder.fill(voxels, id="name")`, which lays bricks and plates in staggered courses, every part resting on the layer below.
- The command `uv run bricky catalog show 3001 --render` describes one part and renders it, with its studs and anti-studs as maps.
  For slopes and other parts with an uneven top, it also maps the height over each square, showing which way the part falls.
  Parts the catalog lists without a shape cannot be placed; `bricky parts` lists only parts that can be.
- Find parts with `uv run bricky parts "plate 2x4"` (20 at a time; `--limit 100` lists more), or from Python with `builder.catalog.find(family="plate", size=(1, 6))`.
  List colors with `uv run bricky colors gray`, or the nearest to an RGB value with `uv run bricky colors "#F2CD37"`; names follow BrickLink, such as `Dark Bluish Gray`.
- Give important parts an `id=` of letters, digits, `.`, `_` and `-`; the report and the images label elements by id.
- To compare with a plan or another model, use `from bricky import voxels`.
  The call `voxels(builder.build())` maps every filled voxel `(x, y, z)`, in studs, studs and plates, to the element's uid and its color id.
  The expression `builder.catalog.resolve_color("Red").id` gives a color name's id.
- Call `print()` freely: the build shows what the script printed.

## Reading the feedback

- Every diagnostic names its elements, what they are and the script line that placed them.
  The `by source line` summary says which lines to look at first.
- From the second build on, `since the last build` counts the elements added, removed, changed and unchanged, by script line.
  A changed element keeps its id and part but has a new position, rotation or color.
  The same section counts the voxels filled, emptied and recolored.
  The sheet outlines new and changed elements in purple.
  Check that an edit changed what you meant, and nothing else.
- Each diagnostic names its rule, such as `floating-group`, and `uv run bricky explain floating-group` gives the exact condition behind it.
- Read positions off the orthographic views: their rulers use the same units as `at`.
- Look closer with `uv run bricky render models/<name>.bricky.json`, which writes `models/<name>.<view>.png` and leaves the build's sheet alone:
    - `--views front --views top` for single, larger views.
    - `--views perspective-north-west` (or `-south-west`, `-north-east`) to see the sides the south-east perspective hides.
    - `--highlight "sign*"` or `--highlight @roof` (a function of your script) to see what those parts are; everything else is rendered faintly.
    - `--clip "z<130"` (plates) or `--clip "x<10"` (studs) to clip the model open and look inside.
    - `--html` to write a viewer people can orbit and inspect in a browser.
- When the model is done, `uv run bricky export models/<name>.bricky.json` writes its parts as a BrickLink Wanted List, `models/<name>.wanted.xml`, to buy them on BrickLink.
- `uv run bricky instructions models/<name>.bricky.json` writes `models/<name>.instructions.html`, a page that walks people through building the model step by step.
- Every build also checks that the model stands under its own weight, and reports what fails as warnings.
  The rule `unbalanced-group` names groups that tip or fall, however firmly their studs grip.
  The rule `overloaded-studs` names studs that need more than their clutch to hold the model, and `strained-studs` studs that need more than half of it.
  For a model someone will build for real, fix these warnings too.

## Building well

The advice below is yours to weigh; bricky only reports facts.

- Stagger joints between courses, like a brick wall, so every brick bridges the ones below it.
- Overhanging parts must reach back over something that holds them: `floating-group` reports anything that is not connected to the ground through studs.
- A long or heavy overhang needs many studs far from the edge it would rotate about.
  Studs in one line, or a single stud, hold little weight at a distance: `overloaded-studs` and `strained-studs` name them.
  Interleave plates across the joint so that more studs share the load.
- Compare the images with the subject: proportions, silhouette from each side, colors.
  A model with no errors can still look wrong.
