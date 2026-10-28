# Build scripts

A build script is a Python file that defines `build()` and returns a `ModelBuilder` (or a finished
`Model`). Scripts are ordinary Python: loops, functions and data drive the model, and `print()`
output appears in the build's report.

```python
from bricky import ModelBuilder


def build() -> ModelBuilder:
    builder = ModelBuilder("tower")
    for level in range(8):
        z = 3 * level
        if level % 2 == 0:
            builder.place("3001", at=(0, 0, z), color="Red")
            builder.place("3001", at=(2, 0, z), color="Red")
        else:  # each level rotates a quarter turn, so every brick bridges the two below
            builder.place("3001", at=(0, 0, z), rotation="R90", color="White")
            builder.place("3001", at=(0, 2, z), rotation="R90", color="White")
    return builder
```

![The tower example: crossed courses of bricks 2 x 4](../images/tower.png)

`bricky build` runs the script in a child process with a time limit, so a script that hangs or
crashes never takes the tool down with it.

## Placing parts

`builder.place(part, at=(x, y, z), color=..., rotation="R0", id=None)` places one part and returns
its id.

- `part` is a part id such as `"3001"`, or any other BrickLink number of the same part.
- `at` is the minimum corner of the rotated part, in studs, studs and plates
  (see [Coordinates](coordinates.md)).
- `color` is a color name or id.
- `rotation` is `R0`, `R90`, `R180`, `R270`, or any of the 24 grid rotations.
- `id` names the element. Unnamed elements get `e1`, `e2` and so on, in placing order.

Give the elements that matter an id: the report and the pictures label elements by id, and
`--highlight` selects them by id pattern.

## Components and instances

A component stores a group of parts once; instances place copies of it. A change to the component
changes every copy.

```python
column = builder.component("column")
for level in range(5):
    column.place("3003", at=(0, 0, 3 * level), color="Tan")

for index in range(4):
    builder.instance("column", at=(index * 4, 0, 0))
```

`at` works for instances exactly as for parts: the minimum corner of the rotated component.
Components may hold instances of other components. An element inside an instance has a uid that
joins the ids of the instances that hold it, such as `i2/e3`: the third element of the second
instance. The colonnade below highlights `i2/*`, its second column:

![The colonnade example, its second column highlighted](../images/colonnade.png)

## Filling voxels

Many shapes are easiest to draw as voxels: which color fills each stud square, one plate tall.
`builder.fill(voxels)` covers such a drawing with bricks and plates. Bricks go where three plate
levels of a course share a color, plates everywhere else, each part as large as fits. Courses
alternate direction, so joints stagger, and every part rests on the level below.

```python
from math import hypot

tower = {
    (x, y, z): "White" if z // 3 % 4 == 3 else "Red"
    for x in range(-6, 7)
    for y in range(-6, 7)
    for z in range(24)
    if 4 <= hypot(x, y) < 6.5
}
builder.fill(tower, id="tower")  # ids such as tower.4.-2.9: the prefix, then the corner
```

![A round tower drawn as voxels and filled with bricks and plates](../images/fill.png)

`plan_fill` in `bricky.fill` returns the same parts as data, to inspect or adjust before placing.

## Building sideways

Bricks with studs on their sides hold parts rotated to face them. A tile or plate rotated `+x+z`
faces -y, so its underside grips a side stud that faces -y:

```python
builder.place("87087", at=(0, 1, 4), color="White")  # Brick 1 x 1, stud on its side
builder.place("3070", at=(0, 0.6, 4.5), rotation="+x+z", color="Blue")  # Tile 1 x 1, upright
```

The tile's bounding box is 0.4 studs deep (a plate's height) and one stud tall (2.5 plates), so its
minimum corner sits 0.4 studs in front of the brick and half a plate above its base, so the tile
ends flush with the brick's top.

![A tile and a plate held sideways by studs on the sides of bricks](../images/sideways.png)

## The cottage

`examples/cottage.py` puts the families together: walls in running bond, an arch over the door, a
roof of slopes with a ridge of cheese slopes, a sign on a side stud, a lamp post on a jumper, and a
round bush.

![The cottage example](../images/cottage.png)

## What a build writes

`bricky build models/name.py` writes three files beside the script:

| File | Holds |
| --- | --- |
| `name.bricky.json` | The model: part ids, colors and poses, nothing else |
| `name.bricky.map.json` | The source map: the script lines that placed each element |
| `name.png` | The picture: four views with rulers |

The source map is tied to the model's exact bytes, so a stale map is ignored rather than trusted.
`bricky check` and `bricky render` read both files.
