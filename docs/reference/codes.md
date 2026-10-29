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
| [E401](#e401-unbalanced-group) | Unbalanced group | stability |
| [E402](#e402-overloaded-studs) | Overloaded studs | stability |
| [W403](#w403-strained-studs) | Strained studs | stability |

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

## E401 Unbalanced group

Elements are rigid and weigh their volume times the density setting.
Forces act only where elements touch.
Faces press on faces they rest against, where each face is the top or bottom of its part or holds its studs or anti-studs: the sides of parts stand 0.1 mm in from the grid.
Faces with no stud between them also rub, with the friction setting.
Studs bear any sideways force.
The ground, at z = 0, presses up on every face that rests on it, with friction.
A group falls when no such forces balance the weight of each of its elements, however firmly studs grip.
The pass reports each group of touching elements that moves, with the box around them.
It leaves out elements with no chain of contacts to the ground, which E301 reports.

## E402 Overloaded studs

Elements are rigid and weigh their volume times the density setting.
Forces act only where elements touch.
Faces press on faces they rest against, where each face is the top or bottom of its part or holds its studs or anti-studs: the sides of parts stand 0.1 mm in from the grid.
Faces with no stud between them also rub, with the friction setting.
Studs bear any sideways force.
The ground, at z = 0, presses up on every face that rests on it, with friction.
A stud's clutch, 2.94 N by default, is the force that pulls it out of its anti-stud.
A stud alone between two elements also resists twisting with its clutch, at its 2.4 mm radius.
The pass finds forces that hold the model still while the most loaded stud uses the least share of its clutch, with the groups of E401 held up.
The studs that set that share form a site.
The search repeats with the studs of each site found holding without limit, so each site needs its share however much the sites before it hold.
The pass reports at most 16 sites, most loaded first: each whose studs need more than their clutch, with that share, the elements the studs join and the box around the studs.

## W403 Strained studs

As E402, for a site whose studs need more than 1 over the safety factor setting of their clutch, half by default, and at most all of it.
