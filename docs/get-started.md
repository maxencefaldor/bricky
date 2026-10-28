# Get started

The tutorial builds a small wall, breaks it and fixes it, and shows exactly what each build prints and renders.

## Install

Python 3.15 runs bricky, and [uv](https://docs.astral.sh/uv/) installs it along with every dependency at the versions in `uv.lock`.

```sh
git clone https://github.com/maxencefaldor/bricky && cd bricky
uv sync
uv run playwright install chromium
```

Playwright's Chromium renders the images.
To render with a Chromium already on the machine, set `BRICKY_RENDER_BROWSER` to its executable instead.

## Write a build script

A build script is a Python file whose `build()` returns a `ModelBuilder`.
Save this wall as `models/wall.py`:

```python title="models/wall.py"
from bricky import ModelBuilder


def build() -> ModelBuilder:
    builder = ModelBuilder("wall")
    for course in range(3):
        z = 3 * course  # a brick is three plates tall
        if course % 2 == 0:  # two bricks 1 x 4
            builder.place("3010", at=(0, 0, z), rotation="R90", color="Red")
            builder.place("3010", at=(4, 0, z), rotation="R90", color="Red")
        else:  # offset joints: a brick 1 x 4 between two bricks 1 x 2
            builder.place("3004", at=(0, 0, z), rotation="R90", color="Red")
            builder.place("3010", at=(2, 0, z), rotation="R90", color="Red")
            builder.place("3004", at=(6, 0, z), rotation="R90", color="Red")
    builder.place("3004", at=(3, 0, 10), rotation="R90", color="Blue", id="chimney")
    return builder
```

Each call to `place` names a part, the corner `at` where it goes, a rotation and a color.
The corner reads `(x, y, z)`: east and north in studs, up in plates.
The rotation `R90` rotates each brick 90 degrees about the vertical axis, so it runs east.
The last call gives the blue brick an id, so the report and the images name it.

## Build it

```sh
uv run bricky build models/wall.py
```

The build runs the script in a process of its own, then saves, checks and renders the model.
The report opens with the model's size and then states what is wrong:

```text
saved models/wall.bricky.json: 8 elements, 8 x 1 studs, 13 plates tall

error[E301]: 1 element floats: no chain of stud connections leads to the ground
  --> x 3..5  y 0..1  z 10..13
   = chimney: Brick 1 x 2 (3004), Blue, models/wall.py:15 in build()

by source line:
  models/wall.py:15 in build(): 1 diagnostic

checked 8 elements with profile digital (schema, collision, connectivity): 1 error, 0 warnings

rendered (open the images to see the model):
  sheet: models/wall.png
```

The diagnostic states one fact: the blue brick floats.
The top course ends at z = 9 and the brick starts at z = 10, one plate higher, so no stud holds it.
The region after `-->` says where, in studs and plates, and the line after `=` names the element, its part, its color and the script line that placed it.

The sheet shows the same fact: the floating brick is tinted red and labeled with its code.

![The wall with its floating chimney tinted red](images/wall-floating.png)

The front and right views carry rulers in the units of `at`, so the one-plate gap reads straight off the z ruler.

## Fix it

Lower the chimney onto the top course, at z = 9:

```python
builder.place("3004", at=(3, 0, 9), rotation="R90", color="Blue", id="chimney")
```

Build again.
The report now opens with what changed since the last build:

```text
saved models/wall.bricky.json: 8 elements, 8 x 1 studs, 12 plates tall

since the last build: 0 added, 0 removed, 1 changed, 7 unchanged
  voxels: 2 filled, 2 emptied, 0 recolored
  changed at:
    models/wall.py:15 in build(): 1 element

checked 8 elements with profile digital (schema, collision, connectivity): 0 errors, 0 warnings
```

One element changed, placed by line 15, and nothing else moved.
The model has no errors, and the sheet outlines the changed brick in purple:

![The fixed wall, its chimney outlined in purple](images/wall-fixed.png)

## Next steps

- [Coordinates](guide/coordinates.md): studs, plates, the `at` corner and rotations.
- [Build scripts](guide/scripts.md): components, instances, filling voxels and building sideways.
- [Parts and colors](guide/parts.md): finding parts and the shape of each family.
- [Gallery](gallery.md): every example in 3D, from a tower to the Colosseum.
