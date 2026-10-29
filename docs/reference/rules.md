# Rules

Each rule names one fact a check can state about a model, and `bricky explain` prints the same condition as this page.
A check reports each rule at its level: `error`, `warn` or `ignore`.
The default levels below hold until settings or options set others (see [Checks](../guide/checks.md#rules-and-levels)).

| Rule | Default level | Pass |
| --- | --- | --- |
| [`unknown-part`](#unknown-part) | `error` | schema |
| [`unknown-color`](#unknown-color) | `error` | schema |
| [`below-ground`](#below-ground) | `error` | schema |
| [`color-never-made`](#color-never-made) | `warn` | schema |
| [`overlap`](#overlap) | `error` | collision |
| [`blocked-stud`](#blocked-stud) | `error` | collision |
| [`floating-group`](#floating-group) | `error` | connectivity |
| [`unbalanced-group`](#unbalanced-group) | `warn` | stability |
| [`overloaded-studs`](#overloaded-studs) | `warn` | stability |
| [`strained-studs`](#strained-studs) | `warn` | stability |

## unknown-part

The element's part id is not in the catalog, or the catalog lists the part without a shape.
The element then has no geometry, and no other pass sees it.
The command `bricky parts` searches the catalog.

## unknown-color

The element's color id is not in the catalog.
The command `bricky colors` lists the catalog's colors.

## below-ground

The element's body reaches below the ground plane, z = 0.
The ground plane is the table the model stands on.

![A brick sunk two plates below the ground](../images/underground.png)

## color-never-made

The catalog lists the colors a part has come in, and the element's color is not among them: the part and the color both exist, but never together.
The pass reports each part and color once, with every element that uses them.
Parts the catalog lists without colors are not checked.

## overlap

The bodies of two elements share positive volume.
Faces that only touch do not count, and studs belong to no body (see blocked-stud).
The pass reports each overlapping pair once, with the box the two share.

![Two bricks placed into the same space](../images/overlap.png)

## blocked-stud

A stud stands inside another element's body where that element has no anti-stud facing it at the same position, so the two elements cannot sit where they are.
A stud is 1.6 mm tall and 4.8 mm wide.
The pass reports each pair of elements once, with the number of blocked studs and the box they span.

![A plate half a stud off the grid: the studs below push into it](../images/blocked.png)

## floating-group

Two elements are connected when a stud of one sits in an anti-stud of the other at the same position, facing it.
A connection works both ways: an element held only from above is connected.
A group of connected elements is grounded when any element in it has its bottom at z = 0 or below.
The pass reports every ungrounded group once, with all its elements and the box around them.

![A brick held by nothing](../images/floating.png)

## unbalanced-group

Elements are rigid and weigh their volume times the density setting.
Forces act only where elements touch.
Faces that face up and down press on each other, since weight closes any gap.
Faces that face sideways press only where each is the top or bottom of its part or holds its studs or anti-studs: the sides of parts stand 0.1 mm in from the grid.
Faces that no stud joins also rub, with the friction setting.
Studs bear any sideways force.
The ground, at z = 0, presses up wherever an element reaches it, with friction.
A group falls when no such forces balance the weight of each of its elements, however firmly studs grip.
The pass reports each group of touching elements that moves, with the box around them.
It leaves out elements with no chain of contacts to the ground, which floating-group reports.

## overloaded-studs

Elements are rigid and weigh their volume times the density setting.
Forces act only where elements touch.
Faces that face up and down press on each other, since weight closes any gap.
Faces that face sideways press only where each is the top or bottom of its part or holds its studs or anti-studs: the sides of parts stand 0.1 mm in from the grid.
Faces that no stud joins also rub, with the friction setting.
Studs bear any sideways force.
The ground, at z = 0, presses up wherever an element reaches it, with friction.
A stud's clutch, 2.94 N by default, is the force that pulls it out of its anti-stud.
A stud alone where two elements meet face to face also resists twisting, at its 2.4 mm radius, and its pull and twist share its clutch; two or more studs there resist any twist together.
The pass finds forces that hold the model still while the most loaded stud uses the least share of its clutch, with the groups of unbalanced-group held up.
The studs that set that share form sites, one for each group of elements that would move together to pull them out.
The search repeats with the studs of each site found holding without limit, so each site needs its share however much the sites before it hold.
The pass reports at most 16 sites, most loaded first: each whose studs need more than their clutch, with that share rounded up, the elements the studs join and the box around the studs.

## strained-studs

As overloaded-studs, for a site whose studs need more than 1 over the safety factor setting of their clutch, half by default, and at most all of it.
