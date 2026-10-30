# Why a compiler

The page explains why bricky works like a compiler, how far the comparison goes, and where it stops.

## Feedback an agent can act on

Agents write working code because a compiler answers every attempt with exact, local feedback.
An error names a rule, a place and a line of source, so the next edit is small and the agent knows when it is done.
A picture of a LEGO® model shows only that something looks wrong, and leaves the agent to find the part behind it.
A build gives a build script the same loop: each diagnostic names a rule, the elements and the script lines behind them.

```text
error[floating-group]: 1 element floats: no chain of stud connections leads to the ground
  --> x 4..6  y 2..4  z 9..10
   = floating: Plate 2 x 2 (3022), Tan, examples/broken.py:18 in build()
```

## The stages of a build

A build runs the stages of a compiler, from a source file to the files people use.
Each stage reads what the stage before it wrote, so each mistake shows up at the one stage that can state it exactly.

| Compiler | bricky |
| --- | --- |
| Source file | Build script: a Python file whose `build()` returns a `ModelBuilder` |
| Parsing | Running the script in its own process, which records the script line behind each element |
| Intermediate representation | Model: part ids, color ids and poses, in exact integer units |
| Passes | Passes: schema, collision, connectivity and stability, each checking its own rules |
| Diagnostics | Diagnostics: a rule, a region, the elements and their script lines |
| Code generation | Images, the 3D viewer, building instructions and the BrickLink Wanted List |

The build of the [Get started](../get-started.md) wall reports each stage in turn, leaving out the time each step took:

```text
saved models/wall.bricky.json: 8 elements, 8 x 1 studs, 13 plates tall

error[floating-group]: 1 element floats: no chain of stud connections leads to the ground
  --> x 3..5  y 0..1  z 10..13
   = chimney: Brick 1 x 2 (3004), Blue, models/wall.py:15 in build()

by source line:
  models/wall.py:15 in build(): 1 diagnostic

checked 8 elements against 8 rules (overloaded-studs, strained-studs ignored): 1 error, 0 warnings

rendered (open the images to see the model):
  sheet: models/wall.png
```

## Rules and levels, as in ty

People configure rules, never passes, as in the type checker [ty](https://docs.astral.sh/ty/).
Each rule has a name, a default level and an exact condition, which `bricky explain` prints.
A rule whose fact surely makes a model impossible to build defaults to `error`.
A rule that is slow to check and rests on uncertain measurements defaults to `ignore`, and any other rule defaults to `warn`.
An option such as `--warn overloaded-studs` changes a level for one build, and `[rules]` in a `bricky.toml` changes it for a project (see [Checks](../guide/checks.md#configuring-levels)).

```sh
uv run bricky explain overlap
```

```text
overlap (error, pass collision)
  The bodies of two elements share positive volume. Faces that only touch do not count, and studs belong to no body (see blocked-stud). The pass reports each overlapping pair once, with the box the two share.
```

## Where the comparison stops

A clean build means bricky knows no reason the model would fail, which is less than a proof that it stands.
A type checker such as ty works the same way: it rules out whole kinds of mistakes, and a program that passes can still be wrong.
A proof assistant such as [Lean](https://lean-lang.org/) goes further, since it checks every step and so certifies the proofs it accepts.
The geometric rules of bricky are exact: an overlap or a blocked stud is certain.
The stability rules rest on measured clutch, friction and density, so a model they pass can still come apart in hand.
Two of them are off by default, so a clean build can leave out what they would report, as with the crane of [Stability](../guide/stability.md):

```sh
uv run bricky check models/crane.bricky.json                          # the default levels
uv run bricky check models/crane.bricky.json --warn overloaded-studs  # the stud rule on
```

The two reports end with these lines:

```text
checked 11 elements against 8 rules (overloaded-studs, strained-studs ignored): 0 errors, 0 warnings
checked 11 elements against 9 rules (strained-studs ignored): 0 errors, 1 warning
```
