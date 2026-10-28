# Working on bricky

bricky is a compiler-style toolkit that lets AI agents design buildable LEGO® models.
`README.md` and the docs say what it does; the rules below say how to change it.

## Commands

```sh
uv sync                             # install Python 3.15 and every tool from uv.lock
uv run playwright install chromium  # the browser renders draw in, once per machine
uv run pytest                       # tests; warnings are errors
uv run ruff format                  # format
uv run ruff check                   # lint, with every rule enabled
uv run ty check                     # types
uv run rumdl check .                # Markdown
```

A change is done when all five checks pass.
To render with a Chromium you already have, set `BRICKY_RENDER_BROWSER` to its executable instead of installing Playwright's.

## Architecture

The core package, `packages/bricky/src/bricky`, is layered.
Each module imports only from the layers above it in this list:

1. `errors`, `settings`: the error front-ends show as a message, and configuration.
1. `units`, `geometry`: exact integer units (0.4 mm), the 24 grid rotations, boxes and convex solids with integer corners, and exact overlap tests between them.
1. `catalog`: parts and colors keyed by BrickLink ids, imported from BrickLink's catalog downloads; each part's shape is read from its official name, or converted from LDraw, and its geometry generated per family, with curves drawn as exact facets.
1. `model`, `provenance`, `builder`, `files`: the canonical model format, the script lines that placed each element, how to write models, and their files and source maps.
1. `analysis`: derived data (world geometry, spatial index, connections, voxels), cached in `Context`, and the differences between two builds.
1. `passes`, `diagnostics`, `check`: plugin passes and the reports they produce.
1. `render`: scenes resolved from a model, drawn with three.js in headless Chromium.
1. `runner`, `service`: build scripts in child processes, and every command defined once.
1. `cli`, and `bricky_mcp` in its own package: front-ends that only adapt `service`.

`bricky_bench`, in `packages/bricky-bench`, runs the benchmark in `bench/` on top of bricky's public API.
Benchmark inputs are generated from each project's reference by `bricky-bench prepare` and committed; a reference never reaches the agent's workspace.

## Conventions

- **Tools:** use the standard, official, established tool in each category.
  That means uv, ruff, ty, rumdl, pytest with Hypothesis, pydantic and pydantic-settings, the official MCP SDK, and Playwright with three.js for renders.
- **Format and lint:** bricky follows [toolchain](https://github.com/maxencefaldor/toolchain): ruff's default format at 88 columns, every ruff rule, every ty rule as an error, and Markdown one sentence per line.
  `.editorconfig` is the toolchain's, verbatim; `.rumdl.toml` is too, followed by the docs' MkDocs flavor.
  A rule is switched off only in `pyproject.toml`, as narrowly as it can be, with its reason beside it.
- **Python:** 3.15 only.
  Use modern syntax: PEP 695 generics and `type` aliases.
  Annotations are lazy, so never write `TYPE_CHECKING` blocks.
- **Concurrency:** asyncio only.
  Hand blocking work to `asyncio.to_thread`; never use threading, multiprocessing or other event loops directly.
- **Data:** pydantic models at every boundary (files, settings, CLI, MCP).
  Use frozen, slotted dataclasses for hot geometry.
- **Exactness:** no floats inside the kernel.
  Convert studs and plates to base units at the edges.
- **One definition:** each command is a request model plus a function in `bricky.service`.
  The CLI and the MCP server derive from it and never redefine arguments.
- **Store once:** the model stores ids and poses only.
  Everything else is derived in `analysis` and never written back.
  Provenance is build metadata: it lives in the source map beside the model.
- **Feedback is facts:** bricky tells the agent what is true about its model and never fixes it or says how to.
  A diagnostic states what is wrong, where and which elements; the report adds what each element is and the script line that placed it.
  Advice belongs in the skill, not in bricky.
- **Passes:** pure functions of a `Context`, registered under the `bricky.passes` entry-point group.
  Each pass documents every code it emits, with the exact rule it checks (`bricky explain`), and emits diagnostics with that code, a message, the elements involved and a region.
- **Build scripts run in their own process** (`bricky.runner`), never in the CLI or the MCP server: their output is captured, a timeout stops them, and a cancelled command kills them.
- **Renders are first-class feedback:** every build draws its model by default.
  Renderer assets live in `bricky/render/assets`; three.js is vendored unmodified, so renders work offline.
- **Sources:** BrickLink, the LEGO Group's marketplace, is the source of what parts and colors exist.
  Shapes come from bricky's own families, read from official names, and otherwise from the LDraw.org Parts Library (CC BY, credited wherever its shapes go), the one decision to use a community library.
  Do not add other brands or community libraries.
  General-purpose tools such as three.js and numpy are fine.
- **Catalog data stays local:** imports write to bricky's data folder, never into the repository; tests use the sample catalog in `bricky/catalog/data`.
- **Trademark:** never put "LEGO" in a package, module or repository name.
  In prose, use "LEGO®" as an adjective.
- **Tests:** every pass gets a passing case and a failing case.
  Geometry gets property tests.
  Renders get a test that draws real pixels.

## Vocabulary

Each concept has one name, used in code, docs, messages and pictures alike.

| Term | Meaning |
| --- | --- |
| part | A design in the catalog, by its BrickLink id, such as `3001` (Brick 2 x 4) |
| color | A BrickLink color, by its id, such as `5` (Red) |
| element | One part in one color, placed in a model, with an `id` |
| uid | An element's id behind the ids of the instances that hold it, such as `bay2/e3` |
| component, instance | A group of elements stored once, and one placed copy of it |
| at | The minimum corner of what a script places, in studs and plates, whatever its rotation |
| position, rotation, pose | Where an element's origin lands, how it is rotated, and both |
| stud, anti-stud | A connector on a part's face, and the socket under a part that a stud fits |
| connection | Two elements joined by studs of one in anti-studs of the other |
| shape, family | A part's catalog data, and the generator that turns it into geometry |
| solid | A box or a convex solid of a part's body |
| voxel | One stud square and one plate tall: the grid that models are compared on |
| base unit | 0.4 mm, the integer unit of the kernel; agents write studs and plates |
| pass, code, diagnostic, report | A check, a fact it can state, one statement of it, and all of them |
| scene, view, mesh | What a render draws, one picture of it, and an element drawn by its faces |
| clip, highlight | Keep one side of a plane; draw some elements and the rest faintly |

Rotate, never turn; clip, never cut.
Spell American English: color, center, neighbor.
Spell words out: the only abbreviations are `id`, `uid`, `info`, `cmd` and `e`, besides `x`, `y`, `z` and loop indices.

## Writing

Docs, docstrings, comments and messages are formal, direct and plain.
Each sentence opens with its subject and states one thing in the active voice.
No sentence starts with "Because", "It", "It's", "There is", "This" or "Note that": name the subject instead.
Say what something is or does, not what it is not, and leave out filler.
