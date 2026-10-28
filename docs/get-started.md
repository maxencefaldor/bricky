# Get started

A first model: a small wall, built, broken and fixed. Each step shows exactly what bricky prints
and draws.

## Install

bricky needs [uv](https://docs.astral.sh/uv/). uv installs Python 3.15 and every tool the project
uses, at the versions in `uv.lock`.

```sh
git clone https://github.com/maxencefaldor/bricky
cd bricky
uv sync
uv run playwright install chromium
```

Playwright's Chromium draws the pictures. To use a Chromium already on the machine, set
`BRICKY_RENDER_BROWSER` to its executable instead of installing one.

## Write a build script

A build script is a Python file that defines `build()` and returns a `ModelBuilder`. Save this
wall as `models/wall.py`:

```python title="models/wall.py"
from bricky import ModelBuilder


def build() -> ModelBuilder:
    builder = ModelBuilder("wall")
    for course in range(3):
        z = 3 * course  # a brick is three plates tall
        if course % 2 == 0:
            for x in (0, 4):
                builder.place("3010", at=(x, 0, z), rotation="R90", color="Red")  # Brick 1 x 4
        else:  # offset courses: a 1 x 2 brick at each end
            builder.place("3004", at=(0, 0, z), rotation="R90", color="Red")
            builder.place("3010", at=(2, 0, z), rotation="R90", color="Red")
            builder.place("3004", at=(6, 0, z), rotation="R90", color="Red")
    builder.place("3004", at=(3, 0, 10), rotation="R90", color="Blue", id="chimney")
    return builder
```

`place` takes a part id, the corner `at` where the part goes, a rotation and a color. `at` is
`(x, y, z)`: x east and y north in studs, z up in plates. `R90` rotates a part a quarter turn
about the vertical axis, so each Brick 1 x 4 runs along x. The last line gives the blue brick an
id, so the report and the pictures name it.

## Build it

```sh
uv run bricky build models/wall.py
```

bricky runs the script in a process of its own, saves the model, checks it and draws it:

```text
saved models/wall.bricky.json (8 elements)

error[E301]: 1 element floats: no chain of stud connections leads to the ground
  --> x 3..5  y 0..1  z 10..13
   = chimney: Brick 1 x 2 (3004), Blue, models/wall.py:15 in build()

by source line:
  models/wall.py:15 in build(): 1 diagnostic

checked 8 elements with profile digital (schema, collision, connectivity): 1 error, 0 warnings

rendered (open the images to see the model):
  sheet: models/wall.png

time: script 0.23 s, check 0.01 s, render 1.70 s
```

The diagnostic states a fact: the blue brick floats. The wall's top course ends at z = 9, and the
brick starts at z = 10, one plate higher, so no stud holds it. The region `x 3..5  y 0..1  z 10..13`
says where, in studs and plates, and the last line names the element, what it is, and the script
line that placed it.

The picture shows the same fact. The floating brick is tinted red and labeled with its code:

![The wall with its floating chimney tinted red](images/wall-floating.png)

The front and right views carry rulers in studs and plates, the units `at` uses. The gap between
the chimney and the wall reads straight off the z ruler: one plate.

## Fix it

Lower the chimney onto the top course, at z = 9:

```python
    builder.place("3004", at=(3, 0, 9), rotation="R90", color="Blue", id="chimney")
```

Build again. The report now opens with what changed since the last build:

```text
saved models/wall.bricky.json (8 elements)

since the last build: 0 added, 0 removed, 1 changed, 7 unchanged
  voxels: 2 filled, 2 emptied, 0 recolored
  changed at:
    models/wall.py:15 in build(): 1 element

checked 8 elements with profile digital (schema, collision, connectivity): 0 errors, 0 warnings
```

One element changed, placed by line 15, and nothing else moved. The model has no errors, and the
picture outlines the changed brick in purple:

![The fixed wall](images/wall-fixed.png)

## Next steps

- [Coordinates](guide/coordinates.md): studs, plates, `at` and rotations.
- [Parts and colors](guide/parts.md): finding parts and what each family looks like.
- [Build scripts](guide/scripts.md): components, instances, ids, and building sideways.
- [Checks](guide/checks.md): every diagnostic code, with a picture.
- [The examples](examples.md): a cottage, Stonehenge and the Elizabeth Tower.
