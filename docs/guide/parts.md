# Parts and colors

Parts and colors carry their BrickLink ids, the ids LEGO® builders and sellers already use: `3001` is a Brick 2 x 4, and `5` is Red.
The [catalog](catalog.md) guide says where parts and colors come from, and how to import them all.

## Finding parts

The command `bricky parts` searches the catalog, so a script never needs to guess an id.

```sh
uv run bricky parts "plate 2x4"
uv run bricky parts "slope 45"
```

The search matches every word of the query against each part's id, name, category and family.
A size such as `2x4`, `4x2` or `2 x 4` matches whole sizes only, so `plate 1x2` finds Plate 1 x 2 and skips Plate 1 x 12.
Parts with a shape come first, plain parts before printed ones, and shorter names before longer ones.
DUPLO, Quatro, Primo and Modulex parts come last unless the query names their system.
Each row gives the family, the footprint, the height and the studs, and how the part sits when unrotated:

```text
id    name            family  x by y  height    studs
3040  Slope 45 2 x 1  slope   1 x 2   3 plates  1 stud
      falls toward -y (the front) when unrotated
3039  Slope 45 2 x 2  slope   2 x 2   3 plates  2 studs
      falls toward -y (the front) when unrotated
2 of 6 matching parts; --limit shows more
```

Sizes read x by y with the part unrotated: a Brick 2 x 4 (`3001`) spans 2 studs along x and 4 along y.
The rotation `R90` makes it span 4 studs along x.
Slope names give depth first: Slope 45 2 x 1 (`3040`) spans 1 stud along x and 2 along y.
In a script, `builder.catalog.find(family="plate", size=(1, 6))` returns every Plate 1 x 6, plain parts first.

## One part in full

The command `bricky catalog show` describes one part: its category, its other numbers, its shape, maps of its studs and anti-studs, and the colors it comes in.
A part with an uneven top also gets a map of its height over each stud square, so a slope shows which way it falls:

```text
3039: Slope 45 2 x 2
category: Slope
other numbers: 6227, 35277, 63341, 3039f1, 3039f2
shape: slope, 2 x 2 studs (x by y, unrotated), 3 plates tall, 2 studs, 4 anti-studs
  falls toward -y (the front) when unrotated
top studs, north up:
    o o
    . .
underside anti-studs, north up:
    o o
    o o
height over each square in plates, north up:
       3    3
    1.75 1.75
colors (34): White, Tan, Yellow, Orange, Red, Green, Blue, Black, Trans-Clear, ...
```

The option `--render` also renders the part, into bricky's cache folder.

## Families

A family converts a few numbers from the catalog into a part's exact solids and connectors, so one tested generator serves every part of the family.

![One part of each family on a baseplate, each labeled with its family](../images/families.png)

| Family | Parts | Shape |
| --- | --- | --- |
| brick, plate, tile | `3001`, `3020`, `87079` | Boxes; bricks and plates carry studs, tiles none |
| baseplate | `3867` | Half a plate thick: parts standing on it start at z = 0.5 |
| slope | `3039` | Falls toward -y; the rows behind the slope carry studs |
| inverted slope | `3660` | Its underside rises toward -y |
| curved slope | `15068` | Curves down toward -y, as flat facets |
| round | `3941`, `4032` | Round bricks, plates and tiles, as many-sided prisms |
| side studs | `87087`, `4733` | Studs on one or more sides, facing as the name says |
| jumper | `87580` | One stud in the middle, half a stud off the grid |
| arch | `3659` | A leg at each end, spanning along y |

Curved and round surfaces become flat facets whose corners stay on the grid, so the shape stays close to the real part and remains exact.

## Converted parts

Parts whose names follow no family pattern, such as windows, Technic bricks and logs, take their shape from the [LDraw.org Parts Library](https://library.ldraw.org).
The [catalog](catalog.md#two-sources) guide explains the conversion.

![Parts converted from LDraw: a Technic brick, a window, a log brick and more](../images/converted.png)

## Colors

A script names a color by its name or its id: `color="Red"` and `color=5` are the same color.
Each color carries BrickLink's name and id, an RGB value and a type: solid, transparent, pearl, metallic and more.
Each image shows transparent colors see-through and pearl colors with a sheen.

```sh
uv run bricky colors gray       # every color whose name contains "gray"
uv run bricky colors "#F2CD37"  # the five colors nearest to an RGB value
```

![Round bricks in 28 colors: solid, pearl, metallic and transparent](../images/colors.png)
