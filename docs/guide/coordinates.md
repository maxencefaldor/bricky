# Coordinates

Scripts place parts in studs and plates, the units every LEGO® builder counts in. bricky converts
them to exact integers before any geometry runs.

## Axes and units

x points east and y north, both in studs. z points up, in plates. A brick is three plates tall.

![Bricks along each axis: red along x, green along y, blue up z, from a white brick at the origin](../images/axes.png)

| Unit | Length | In base units |
| --- | --- | --- |
| stud | 8 mm, the stud pitch | 20 |
| plate | 3.2 mm, a plate's height | 8 |
| brick | 9.6 mm, three plates | 24 |
| base unit | 0.4 mm | 1 |

The base unit, 0.4 mm, divides every LEGO System dimension exactly, so every position is a whole
number and no check ever compares floats. Coordinates in a script may be fractions, such as
`at=(0, 1.5, 2)` for half a stud off the grid; a coordinate that lands between base units is an
error.

The ground plane is z = 0. Parts below it are reported (E103), and a group of parts touching it
counts as grounded.

## `at`: the minimum corner

`at` names the minimum corner of the rotated bounding box of whatever a script places, a part or a
whole component. A rotation never moves that corner, so a footprint always starts at `at`.

```python
builder.place("3001", at=(0, 0, 0), color="Red", id="R0")
builder.place("3001", at=(3, 0, 0), rotation="R90", color="Blue", id="R90")
builder.place("3001", at=(3, 3, 0), rotation="R180", color="Yellow", id="R180")
builder.place("3001", at=(8, 0, 0), rotation="R270", color="Green", id="R270")
```

Seen from above, each Brick 2 x 4 starts at its `at`, whatever its rotation:

![Four bricks 2 x 4 seen from above, each starting at its at](../images/corners.png)

## Rotations

`R0`, `R90`, `R180` and `R270` rotate a part about the vertical axis, counter-clockwise seen from
above. Parts that face a way say so in `bricky parts`: unrotated, a slope falls toward -y, the
front.

![A Slope 45 2 x 2 in each rotation](../images/rotations.png)

A rotation can also be named by where the part's own x and y axes go, which reaches all 24 grid
rotations. `+x+y` is the identity, `+y-x` is `R90`, and `+x+z` stands a part up so that its top
faces -y. Building sideways uses these rotations; see
[Build scripts](scripts.md#building-sideways).

## Half a stud off the grid

Jumper plates carry one stud in the middle of two, so whatever stands on them sits half a stud off
the grid. Coordinates follow: the lamp post below stands at `y = 1.5`.

![A lamp post on a jumper, half a stud off the grid](../images/jumper.png)
