# Coordinates

Scripts place parts in studs and plates, the units every LEGO® builder counts in, and bricky converts them to exact integers.

## Axes and units

The x axis points east and the y axis north, both in studs; the z axis points up, in plates.
Studs and plates are the natural units: a brick is three plates tall, and every footprint is a whole number of studs.

![Bricks along each axis: red along x, green along y, blue up z, from a white brick at the origin](../images/axes.png)

| Unit | Length | Base units |
| --- | --- | --- |
| stud | 8 mm, the distance between studs | 20 |
| plate | 3.2 mm, the height of a plate | 8 |
| brick | 9.6 mm, three plates | 24 |
| base unit | 0.4 mm | 1 |

## Exact integers

Every length in the kernel is a whole number of base units, so no check ever compares floating-point numbers.
The base unit, 0.4 mm, divides every LEGO System dimension exactly: a stud is 20 base units and a plate 8.
A script may still write fractions, such as `at=(0, 1.5, 2)` for half a stud off the grid, and a coordinate that falls between base units is an error.

The ground is the plane z = 0.
A part below it is an error (E103), and a group of parts that touches it stands on the ground.

## The `at` corner

The `at` of a part or a component is the minimum corner of its bounding box after rotation.
A rotation never moves that corner, so a footprint always starts at `at` and a script never needs to correct for rotation.

```python
builder.place("3001", at=(0, 0, 0), color="Red", id="R0")
builder.place("3001", at=(3, 0, 0), rotation="R90", color="Blue", id="R90")
builder.place("3001", at=(3, 3, 0), rotation="R180", color="Yellow", id="R180")
builder.place("3001", at=(8, 0, 0), rotation="R270", color="Green", id="R270")
```

![Four bricks 2 x 4 seen from above, each starting at its at](../images/corners.png)

## Rotations

The four rotations `R0`, `R90`, `R180` and `R270` rotate a part about the vertical axis, counterclockwise seen from above.
A part that faces one way says so in `bricky parts`: unrotated, a slope falls toward -y, the front.

![A Slope 45 2 x 2 in each rotation](../images/rotations.png)

A rotation can also name where the part's own x and y axes go, which reaches all 24 grid rotations.
The identity is `+x+y`, and `+y-x` equals `R90`.
The rotations below stand a part up, to [build sideways](scripts.md#building-sideways):

| Rotation | The part's top faces |
| --- | --- |
| `+x+z` | -y, the front |
| `-x+z` | +y, the back |
| `+y+z` | +x, east |
| `-y+z` | -x, west |
| `+x-y` | down: upside down |

## Positions off the grid

A jumper plate carries one stud centered between two, so the part on top of it sits half a stud off the grid.
The coordinates follow the part: the lamp post below stands at y = 1.5.

![A lamp post on a jumper, half a stud off the grid](../images/jumper.png)
