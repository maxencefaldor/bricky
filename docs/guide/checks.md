# Checks

Every build checks its model and reports facts: what is wrong, never how to fix it.

## Reading a report

A report lists diagnostics, and each diagnostic states one fact about the model: what is wrong, where, and which elements.
The report adds what each element is and the script line that placed it, so every fact leads back to the code that caused it.
Deciding what to change stays with the agent: bricky never fixes a model and never suggests a fix.

The example `examples/broken.py` makes three mistakes: an overlap, a brick half a stud off and a floating plate.

```python
builder.place("3001", at=(0, 0, 0), color="Red", id="base")  # Brick 2 x 4
builder.place("3001", at=(1, 0, 0), color="Blue", id="overlap")  # shares space
builder.place("3003", at=(0.5, 0, 3), color="White", id="offset")  # half a stud off
builder.place("3022", at=(4, 2, 9), color="Tan", id="floating")  # touches nothing
```

```text
error[E201]: base and overlap occupy the same space
  --> x 1..2  y 0..4  z 0..3
   = base: Brick 2 x 4 (3001), Red, examples/broken.py:13 in build()
   = overlap: Brick 2 x 4 (3001), Blue, examples/broken.py:14 in build()

error[E202]: 4 studs of base push into offset, which has no anti-stud there
  --> x 0.2..1.8  y 0.2..1.8  z 3..3.5
   = base: Brick 2 x 4 (3001), Red, examples/broken.py:13 in build()
   = offset: Brick 2 x 2 (3003), White, examples/broken.py:15 in build()

error[E202]: 4 studs of overlap push into offset, which has no anti-stud there
  --> x 1.2..2.8  y 0.2..1.8  z 3..3.5
   = overlap: Brick 2 x 4 (3001), Blue, examples/broken.py:14 in build()
   = offset: Brick 2 x 2 (3003), White, examples/broken.py:15 in build()

error[E301]: 1 element floats: no chain of stud connections leads to the ground
  --> x 4..6  y 2..4  z 9..10
   = floating: Plate 2 x 2 (3022), Tan, examples/broken.py:16 in build()

error[E301]: 1 element floats: no chain of stud connections leads to the ground
  --> x 0.5..2.5  y 0..2  z 3..6
   = offset: Brick 2 x 2 (3003), White, examples/broken.py:15 in build()

by source line:
  examples/broken.py:15 in build(): 3 diagnostics
  examples/broken.py:13 in build(): 2 diagnostics
  examples/broken.py:14 in build(): 2 diagnostics
  examples/broken.py:16 in build(): 1 diagnostic

checked 4 elements with profile digital (schema, collision, connectivity): 5 errors, 0 warnings
```

Each diagnostic has three parts:

1. **The fact**, after the code: `error[E201]: base and overlap occupy the same space`.
1. **The region**, after `-->`: x and y in studs, z in plates, the units of `at`.
1. **The elements**, after `=`: uid, part name and id, color, and the script line that placed the element.

The summary `by source line` ranks script lines by how many diagnostics name their elements.
The first line listed is the one to read first.
The sheet tints elements an error names red and those a warning names orange.
Each diagnostic also labels its first element with its code and marks its region with a dashed box:

![The broken example: every element a diagnostic names is tinted red and labeled](../images/broken.png)

The [diagnostic codes](../reference/codes.md) page gives the exact rule behind every code, and `bricky explain E202` prints it.

## Passes and profiles

A check runs the passes of a profile, and each pass tests one kind of fact.
Passes are pure functions of the model's shared analyses, registered under the `bricky.passes` entry-point group, so any package can add a pass without changing bricky.
The command `bricky passes` lists the installed passes and profiles:

```text
collision     E201, E202              Parts sharing space, and studs blocked by parts with no anti-stud.
connectivity  E301                    Groups of parts with no connected path to the ground.
schema        E101, E102, E103, W104  Unknown parts and colors, parts below the ground plane, and colors a part never came in.

digital (default): schema, collision, connectivity
physical: schema, collision, connectivity, stability (not installed), buildability (not installed), budget (not installed)
```

The profile `physical` also names three passes that no package installs yet, and the report lists them as skipped.
The option `--profile physical` runs a profile, and `--passes collision` runs one pass alone.

## Changes between builds

From the second build of a script on, the report opens with what changed since the last build.
The agent can then confirm that an edit did what it meant and nothing more.
After an edit that recolors the top two courses of a tower and caps it with tiles, the report reads:

```text
since the last build: 4 added, 0 removed, 4 changed, 8 unchanged
  voxels: 16 filled, 0 emptied, 96 recolored
  added at:
    models/tower.py:19 in build(): 4 elements
  changed at:
    models/tower.py:11 in build(): 1 element
    models/tower.py:12 in build(): 1 element
    models/tower.py:15 in build(): 1 element
    models/tower.py:16 in build(): 1 element
```

Elements first match by part, color and the space they occupy, so renumbered elements count as unchanged.
The remaining elements then pair by id: the same id and part with another pose or color counts as changed.
The sheet outlines new and changed elements in purple:

![A tower whose top two courses were recolored and capped with tiles, outlined in purple](../images/changes.png)
