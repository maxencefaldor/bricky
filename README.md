# bricky

A compiler-style toolkit that lets AI agents design buildable LEGO® models.

Agents write models as Python build scripts. bricky runs a script, compiles the model into exact
geometry, checks it and draws it. It answers with facts the agent can act on: diagnostics that name
the script line behind every part, and pictures with rulers in studs and plates. It never fixes the
model itself; that stays the agent's job.

![The Elizabeth Tower example: perspective, front, right and top views with rulers](docs/images/elizabeth-tower.png)

> Status: v0.2. Exact-geometry kernel, a catalog of every part and color imported from BrickLink,
> with shapes from eleven families and from the LDraw library, the digital checks, provenance from
> script lines, renders, the `bricky` command line, an MCP server and a benchmark. Physics comes
> next.

## Quick start

```sh
uv sync
uv run playwright install chromium            # once: the browser renders draw in
uv run bricky build examples/stonehenge.py    # 0 errors, and examples/stonehenge.png
uv run bricky build examples/broken.py        # one mistake of each kind
uv run bricky catalog import --ldraw ~/ldraw  # once: every part, shaped (see below)
uv run bricky parts "plate 2x4"
uv run bricky colors gray
uv run bricky explain E301
```

A broken model reads like compiler output, and every part it names points back at the script:

```text
error[E201]: base and overlap occupy the same space
  --> x 1..2  y 0..4  z 0..3
   = base: Brick 2 x 4 (3001), Red, examples/broken.py:12 in build()
   = overlap: Brick 2 x 4 (3001), Blue, examples/broken.py:13 in build()
```

The picture marks the same parts, so the agent sees where they are:

![The broken example, with every part a diagnostic names tinted red and labeled](docs/images/broken.png)

## Writing a model

```python
from bricky import ModelBuilder


def build() -> ModelBuilder:
    builder = ModelBuilder("wall")
    builder.place("3001", at=(0, 0, 0), color="Red")  # Brick 2 x 4
    builder.place("3001", at=(0, 2, 3), rotation="R90", color="Red")  # rotated a quarter turn
    return builder
```

- **Coordinates:** `(x, y, z)` with x east and y north in studs, and z up in plates. A brick is three
  plates tall.
- **Placement:** `at` is the minimum corner of the rotated bounding box of whatever is placed, a
  part or a whole component, so rotating something never moves the corner of its footprint.
- **Rotations:** `R0`, `R90`, `R180` and `R270` rotate about the vertical axis. Any of the 24 grid
  rotations can be named by the images of x and y, such as `+x-y` for upside down.
- **Reuse:** `builder.component("column")` stores a group of parts once;
  `builder.instance("column", at=...)` places copies.
- **Parts and colors:** ids follow the BrickLink catalog, such as `3001` and `Dark Bluish Gray`.
  Scripts can query the catalog: `builder.catalog.find(family="plate", size=(1, 6))`.
- **Families:** bricks, plates, tiles and baseplates; slopes, inverted and curved slopes; round
  parts; bricks with studs on their sides; jumpers; arches. `bricky parts` says which way a part
  faces when unrotated, such as a slope falling toward -y. Shapes are exact: curves are flat facets
  with corners on the grid, and studs on a side connect to parts rotated to face them.
- **Voxels:** `voxels(builder.build())` maps every voxel a model fills, one stud square and one
  plate tall, keyed `(x, y, z)` in the units of `at`, to the element and color that fill it.
  Comparing a model with a target, a plan or another model, takes a few exact lines.

![The cottage example: slopes, an arch, round parts, a tile on a side stud and a jumper](docs/images/cottage.png)

## The catalog

bricky knows parts and colors by their BrickLink ids. A catalog is built from two sources, each
for what it is best at, and every part's record says where its shape came from:

- **BrickLink**, the LEGO Group's marketplace, lists every part and color: ids, names,
  categories, RGB values, and the colors each part comes in.
- **Shapes.** A part whose official name follows a pattern gets that family's shape, exact:
  "Slope 45 2 x 4" is a slope two studs deep and four wide, "Brick 1 x 2 x 2" a brick two bricks
  tall. Printed parts take the shape of the part they are printed on. Every other part is
  converted from the [LDraw.org Parts Library](https://library.ldraw.org) (CC BY): its body as
  boxes on a 0.8 mm grid, its studs where LDraw draws them, its anti-studs wherever the underside
  leaves a stud room. Where a part has both, the import compares them: where they disagree,
  the name has hidden a detail, so the part takes LDraw's shape, and the import reports it.

```sh
uv run bricky catalog import --bricklink ~/bricklink --ldraw ~/ldraw   # either, or both
uv run bricky catalog status               # which catalog is in use, and what is in it
uv run bricky catalog show 3001 --render   # one part: its facts, its shape and a picture
uv run bricky catalog verify               # generate every shaped part's geometry and check it
```

BrickLink's downloads come from <https://www.bricklink.com/catalogDownload.asp>, signed in, as
XML: Catalog Items (item type Parts), Colors, Categories and Codes, in one folder. The LDraw
library is the unzipped `complete.zip` from library.ldraw.org. Without BrickLink's downloads,
parts are named as LDraw names them and colors come from the sample. Parts without a shape stay
in the catalog, so `bricky parts --shapeless` finds them, but cannot be placed. Until a catalog
is imported, bricky uses a small sample of common parts.

The import writes to bricky's data folder, outside any repository, and bricky uses it from then on.
Set `catalog` in `[tool.bricky]`, or `BRICKY_CATALOG`, to use another catalog file.

## The feedback loop

`bricky build script.py` runs the script in a process of its own, with a timeout, and returns:

- **What the script printed**, captured and shown.
- **The model** (`script.bricky.json`) and its **source map** (`script.bricky.map.json`), which
  records the script lines that placed each element. The map is tied to the model's exact bytes,
  so a stale map is ignored rather than trusted.
- **What changed since the last build**: elements added, removed, changed and unchanged, by the
  script line that placed them, and voxels filled, emptied and recolored. Elements match by part,
  color and the space they take, so renumbered elements count as unchanged; an element that kept
  its id and part but moved, rotated or recolored counts as changed. The picture outlines
  what is new or changed, so an edit that did more, or less, than intended shows at once.
- **The report**: each diagnostic states a fact (what, where, which elements) and each element
  carries its part, color and script line. A `by source line` summary says where to look first.
- **The picture** (`script.png`): perspective, front, right and top views. The orthographic views carry
  rulers in the units `at` uses, so a position read off the picture is a position to write.

`bricky render model.bricky.json` looks closer. It writes `model.<view>.png` beside the model, so
the picture the last build drew stays as it was:

| Option | Does |
| --- | --- |
| `--views front --views top` | Single views at full size; `sheet` is all four |
| `--highlight "lintel*"` | Highlights elements by uid pattern and draws the rest faintly |
| `--highlight @horseshoe` | Highlights what a script function, file or `file:line` placed |
| `--clip "z<120"` | Clips the model open; z in plates, x and y in studs |
| `--html` | Also writes a viewer people can orbit and clip in a browser |

Renders run three.js in headless Chromium through Playwright. three.js is vendored, so renders
work offline. Set `BRICKY_RENDER_BROWSER` to use a Chromium you already have.

## Checks

| Code | Pass | Fact |
| --- | --- | --- |
| E101 | schema | The part is not in the catalog |
| E102 | schema | The color is not in the catalog |
| E103 | schema | A part reaches below the ground plane |
| E201 | collision | Two parts occupy the same space |
| E202 | collision | Studs push into a part that has no anti-stud there |
| E301 | connectivity | A group of parts has no connected path to the ground |

`bricky explain <code>` gives the exact rule behind each one. Passes are plugins, registered under
the `bricky.passes` entry-point group, and each documents the codes it reports. Profiles choose
which passes run: `digital`, the default, runs the three above. `physical` adds stability,
buildability and budget, which a separate plugin pack will provide; until then, they are reported
as not installed.

## Using bricky from an agent

- **Claude Code:** run the CLI directly. The `build-model` skill in `.claude/skills` teaches the
  loop, and Claude Code reads the rendered PNGs.
- **Any MCP client:** `uv run bricky-mcp` serves `build_model`, `render_model`, `check_model`,
  `search_parts`, `search_colors`, `list_passes` and `explain_code` over stdio. Their arguments come
  from the same request models as the CLI; builds and renders return their pictures as images.

## Benchmark

[`bench/`](bench/README.md) holds ten projects, from a brick wall to Notre-Dame de Paris: prompts
with pictures, plans, notes or a broken script to repair. Seven are scored voxel by voxel against a
reference the agent never sees. `uv run bricky-bench run` runs them with Claude Code in fresh
workspaces and keeps every transcript, model and score.

## Layout

| Path | What lives there |
| --- | --- |
| `packages/bricky` | The core: geometry, catalog, model format, provenance, passes, renders, CLI |
| `packages/bricky-mcp` | The MCP server, a thin adapter over `bricky.service` |
| `packages/bricky-bench` | The benchmark runner: workspaces, Claude Code, scores |
| `bench` | The benchmark's projects, and the runs it keeps |
| `examples` | Build scripts to try, including Stonehenge and the Elizabeth Tower |

## Development

```sh
uv sync                              # Python 3.15 and every tool, from uv.lock
uv run playwright install chromium   # the browser renders draw in
uv run pytest                        # tests, with Hypothesis property tests
uv run ruff format                   # format
uv run ruff check                    # lint
uv run ty check                      # types
uv run rumdl check .                 # Markdown
uvx prek install                     # run the same checks before each commit
```

## Trademark

LEGO® is a trademark of the LEGO Group, which does not sponsor, authorize or endorse this project.

## License

[Apache-2.0](LICENSE). three.js, vendored for renders, is under the MIT license in
`packages/bricky/src/bricky/render/assets/three/LICENSE`.
