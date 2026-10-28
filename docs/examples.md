# Examples

The scripts in [`examples/`](https://github.com/maxencefaldor/bricky/tree/main/examples) build
models of growing size. Each one builds with one command:

```sh
uv run bricky build examples/stonehenge.py
```

## Tower

`examples/tower.py`: crossed courses of bricks 2 x 4, each level rotated a quarter turn so every
brick bridges the two below it, capped with tiles.

![The tower](images/tower.png)

## Colonnade

`examples/colonnade.py`: one column component, instanced four times, under a two-layer beam. A
change to the component changes every column.

![The colonnade, its second column highlighted](images/colonnade.png)

## Cottage

`examples/cottage.py`: walls in running bond, an arch over the door, a roof of slopes with a ridge
of cheese slopes, a sign held sideways by a side stud, a lamp post on a jumper, and a round bush.

![The cottage](images/cottage.png)

## Stonehenge

`examples/stonehenge.py`: the sarsen circle with its lintels, the horseshoe of trilithons, the
bluestones and the heel stone, from measurements of the monument.

![Stonehenge](images/stonehenge.png)

## Elizabeth Tower

`examples/elizabeth_tower.py`: Big Ben's tower, voxelized from its measurements and covered layer
by layer with the biggest parts that fit, every part resting on the layer below.

![The Elizabeth Tower](images/elizabeth-tower.png)

## Broken

`examples/broken.py`: one mistake of each kind the checks catch, to show what bricky reports.

![The broken example](images/broken.png)
