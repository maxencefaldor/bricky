# Diagnostic codes

Each code names one fact a pass can state about a model, and `bricky explain` prints the same rule as this page.

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

The element's part id is not in the catalog, or the catalog lists the part without a shape.
The element then has no geometry, and no other pass sees it.
The command `bricky parts` searches the catalog.

## E102 Unknown color

The element's color id is not in the catalog.
The command `bricky colors` lists the catalog's colors.

## E103 Below the ground

The element's body reaches below the ground plane, z = 0.
The ground plane is the table the model stands on.

![A brick sunk two plates below the ground](../images/underground.png)

## W104 Color never made

The catalog lists the colors a part has come in, and the element's color is not among them: the part and the color both exist, but never together.
The pass reports each part and color once, with every element that uses them.
Parts the catalog lists without colors are not checked.

## E201 Overlap

The bodies of two elements share positive volume.
Faces that only touch do not count, and studs belong to no body (see E202).
The pass reports each overlapping pair once, with the box the two share.

![Two bricks placed into the same space](../images/overlap.png)

## E202 Blocked stud

A stud stands inside another element's body where that element has no anti-stud facing it at the same position, so the two elements cannot sit where they are.
A stud is 1.6 mm tall and 4.8 mm wide.
The pass reports each pair of elements once, with the number of blocked studs and the box they span.

![A plate half a stud off the grid: the studs below push into it](../images/blocked.png)

## E301 Floating group

Two elements are connected when a stud of one sits in an anti-stud of the other at the same position, facing it.
A connection works both ways: an element held only from above is connected.
A group of connected elements is grounded when any element in it has its bottom at z = 0 or below.
The pass reports every ungrounded group once, with all its elements and the box around them.

![A brick held by nothing](../images/floating.png)
