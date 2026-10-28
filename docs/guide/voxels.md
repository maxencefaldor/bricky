# Voxels

A voxel is one stud square and one plate tall: the grid parts are placed on. `voxels(model)` maps
every voxel a model fills to the element and color that fill it, keyed `(x, y, z)` in studs,
studs and plates, the units of `at`.

```python
from bricky import ModelBuilder, voxels

builder = ModelBuilder("wall")
builder.place("3004", at=(0, 0, 0), color="Red")  # Brick 1 x 2
filled = voxels(builder.build())
sorted(filled)
# [(0, 0, 0), (0, 0, 1), (0, 0, 2), (0, 1, 0), (0, 1, 1), (0, 1, 2)]
filled[0, 0, 0].uid, filled[0, 0, 0].color
# ('e1', 5)
```

An element fills a voxel when the voxel's center lies inside its body. Every voxel therefore
belongs to at most one element of a valid model, and studs fill none. Below, a slope and an arch
stand beside their voxels, rebuilt from 1 x 1 plates: the slope fills its back row three plates
high and its front row two; the arch fills its legs and the span above the opening.

![A slope and an arch beside the voxels they fill](../images/voxels.png)

## Comparing with a target

Voxels make comparisons exact and short. A script can check a model against a plan, a layer
drawing or another model in a few lines:

```python
from bricky import voxels

target = {(x, 0, z) for x in range(8) for z in range(9)}  # a wall 8 studs long, 3 bricks tall
filled = set(voxels(builder.build()))
print("missing:", sorted(target - filled))
print("extra:", sorted(filled - target))
```

The [benchmark](../agents/benchmark.md) scores models this way: it compares the voxels an agent's
model fills with a reference's, over every rotation about the vertical axis and the best shift.

## Changes

Each build compares the new model's voxels with the last build's and counts the voxels filled,
emptied and recolored, beside the elements added, removed and changed (see
[Checks](checks.md#changes-since-the-last-build)).
