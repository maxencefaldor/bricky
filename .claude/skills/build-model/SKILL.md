---
name: build-model
description: Design a buildable LEGO® model with bricky. Use when asked to build, model or recreate something in bricks, or to fix a bricky build script.
---

# Build a model with bricky

Work like a programmer with a compiler and a camera: write a build script, build it, read the
report and look at the pictures, fix, and repeat. Stop when the report says `0 errors` and the
pictures show what you meant. The report alone cannot tell you the second part.

## Loop

1. Plan the footprint and height in studs and plates. One stud is 8 mm, one plate 3.2 mm, and a
   brick is three plates.
2. Write `models/<name>.py` (create `models/` if needed), defining `build()` that returns a
   `bricky.ModelBuilder`. The scripts in `examples/` show the style.
3. Run `uv run bricky build models/<name>.py`. It runs the script, saves the model, checks it and
   renders it.
4. Read the report, then open the image it names (`models/<name>.png`): iso, front, right and top
   views, with rulers in studs and plates. Parts that diagnostics name are tinted red and labelled.
5. Fix the script and build again.

## Writing the script

```python
from bricky import ModelBuilder


def build() -> ModelBuilder:
    builder = ModelBuilder("name")
    builder.place("3001", at=(0, 0, 0), color="Red")
    return builder
```

- `at=(x, y, z)`: x east and y north in studs, z up in plates. It is the minimum corner of the
  rotated bounding box of what you place, a part or a whole component.
- `rot`: `R0`, `R90`, `R180` or `R270` about the vertical axis. Any of the 24 grid rotations can be
  named by where the part's x and y axes go: `+x+z` stands a part up with its top facing -y.
- Parts that face a way say so in `uv run bricky parts slope`: unturned, slopes fall toward -y
  (the front), bricks with side studs list the faces their studs are on, arches span along y.
  Turn them with `rot`, for example `R180` for a slope falling toward +y.
- Baseplates are half a plate thick: parts standing on one start at `z = 0.5`.
- Building sideways: a tile or plate turned `+x+z` faces -y, so its underside grips a side stud
  facing -y. `examples/cottage.py` shows one, with an arch, a roof of slopes and a jumper.
- Use loops and functions for anything that repeats. Use `builder.component(...)` with
  `builder.instance(...)` for identical groups.
- `uv run bricky catalog show 3001 --render` describes one part and draws it. Parts the catalog
  lists without a shape cannot be placed; `bricky parts` lists only parts that can be.
- Find parts with `uv run bricky parts "plate 2x4"`, or from Python with
  `builder.catalog.find(family="plate", size=(1, 6))`. List colours with
  `uv run bricky colors gray`; names follow BrickLink, such as `Dark Bluish Gray`.
- Give important parts a `name=`; the report and the pictures label parts by name.
- To compare with a target (a plan, layers or another model), `from bricky import cells`:
  `cells(builder.build())` maps every filled cell `(x, y, z)`, in studs, studs and plates, to the
  element and colour that fill it.
- `print()` freely: the build shows what the script printed.

## Reading the feedback

- Every diagnostic names its elements, what they are and the script line that placed them. The
  `by source line` summary says which lines to look at first.
- From the second build on, `since the last build` counts the elements added, removed, changed
  (same id and part, moved, turned or recoloured) and unchanged, by script line, and the cells
  filled, emptied and recoloured. The picture outlines new and changed parts in purple. Check
  that an edit changed what you meant, and nothing else.
- `uv run bricky explain E301` gives the exact rule behind a code.
- Read positions off the orthographic views: their rulers use the same units as `at`.
- Look closer with `uv run bricky render models/<name>.bricky.json`, which writes
  `models/<name>.<view>.png` and leaves the build's picture alone:
  - `--views front --views top` for single, larger views.
  - `--highlight "lintel*"` or `--highlight @horseshoe` (a function of your script) to see what
    those parts are; everything else is drawn faintly.
  - `--clip "z<120"` (plates) or `--clip "x<10"` (studs) to cut the model open and look inside.
  - `--html` to write a viewer you can orbit in a browser.

## Building well

This advice is yours to weigh; bricky only reports facts.

- Stagger joints between layers, like a brick wall, so every brick bridges the ones below it.
- Overhanging parts must reach back over something that holds them: E301 reports anything that is
  not connected to the ground through studs.
- Compare the pictures with the subject: proportions, silhouette from each side, colours. A model
  with no errors can still look wrong.
