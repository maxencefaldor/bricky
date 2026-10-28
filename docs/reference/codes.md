# Diagnostic codes

Each code names one fact a pass can state about a model; `bricky explain` prints the exact rule behind each code.

| Code | Title | Pass |
| --- | --- | --- |
| [E101](#e101-unknown-part) | Unknown part | schema |
| [E102](#e102-unknown-color) | Unknown color | schema |
| [E103](#e103-below-the-ground) | Below the ground | schema |
| [W104](#w104-color-never-made) | Color never made | schema |
| [E201](#e201-overlap) | Overlap | collision |
| [E202](#e202-blocked-stud) | Blocked stud | collision |
| [E301](#e301-floating-group) | Floating group | connectivity |

Codes that start with E are errors, and codes that start with W are warnings.

## E101 Unknown part

The element's part id is missing from the catalog, or the catalog lists the part without a shape.
The element then has no geometry, and no other pass sees it.

## E102 Unknown color

The element's color id is missing from the catalog.

## E103 Below the ground

The element's body reaches below the ground plane, z = 0.

![A brick sunk two plates below the ground](../images/underground.png)

## W104 Color never made

BrickLink lists the colors each part has come in, and the element's color is not among them: the part and the color both exist, but never together.
The warning names the part and the color once, with every element that uses them.
A call to `builder.fill` picks only parts made in each color.

## E201 Overlap

The bodies of two parts share a positive volume.
Faces that only touch do not count, and studs belong to no body.
The region is the box the two parts share.

![Two bricks placed into the same space](../images/overlap.png)

## E202 Blocked stud

A stud stands inside another part's body where that part has no anti-stud to receive it, so the two parts cannot sit where they are.
A plate half a stud off the grid is the classic case: the studs below push into its underside between its anti-studs.

![A plate half a stud off the grid: the studs below push into it](../images/blocked.png)

## E301 Floating group

Two parts are connected when a stud of one sits in an anti-stud of the other.
A group of connected parts stands on the ground when any part in it reaches z = 0.
The pass reports each group that does not stand on the ground once, with all its elements.

![A brick held by nothing](../images/floating.png)
