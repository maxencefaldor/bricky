---
name: build-model
description: Design a buildable LEGO model with bricky. Use when asked to build, model or recreate something in bricks, or to fix a bricky build script.
---

# Build a model with bricky

Work like a programmer with a compiler: write a build script, build it, read the diagnostics, fix,
and repeat until the report says `0 errors`.

## Loop

1. Plan the footprint and height in studs and plates. One stud is 8 mm, one plate 3.2 mm, and a
   brick is three plates.
2. Write `models/<name>.py`, defining `build()` that returns a `bricky.ModelBuilder`.
3. Run `uv run bricky build models/<name>.py`.
4. Fix every error, then build again. Stop only at `0 errors`.

## Writing the script

```python
from bricky import ModelBuilder


def build() -> ModelBuilder:
    builder = ModelBuilder("name")
    builder.place("3001", at=(0, 0, 0), color="Red")
    return builder
```

- `at=(x, y, z)`: x east and y north in studs, z up in plates. It is the minimum corner of the
  part's rotated bounding box.
- `rot`: `R0`, `R90`, `R180` or `R270` about the vertical axis.
- Use loops and functions for anything that repeats. Use `builder.component(...)` with
  `builder.instance(...)` for identical groups.
- Find parts with `uv run bricky parts "plate 2x4"`. Colours use BrickLink names, such as
  `Dark Bluish Gray`.
- Stagger joints between layers, like a brick wall, so every brick bridges the ones below it.

## Fixing diagnostics

| Code | Meaning | Usual fix |
| --- | --- | --- |
| E101 | Unknown part | Search with `bricky parts` and use a listed id |
| E102 | Unknown colour | Use a colour name from the catalog |
| E103 | Below the ground | Raise the part so its bottom is at z = 0 or above |
| E201 | Parts overlap | Move one part, or remove it |
| E202 | Studs blocked | Align the upper part to whole studs, or move it clear |
| E301 | Floating group | Connect it to the structure below, or rest it on the ground |
