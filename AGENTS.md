# Working on bricky

bricky is a compiler-style toolkit that lets AI agents design buildable LEGO® models. Read
`README.md` for what it does. This file says how to change it.

## Commands

```sh
uv sync                              # install Python 3.15 and every tool from uv.lock
uv run playwright install chromium   # the browser renders draw in, once per machine
uv run pytest                        # tests; warnings are errors
uv run ruff format                   # format
uv run ruff check                    # lint, with every rule enabled
uv run ty check                      # types
uv run rumdl check .                 # Markdown
```

A change is done when all five checks pass. To render with a Chromium you already have, set
`BRICKY_RENDER_BROWSER` to its executable instead of installing Playwright's.

## Architecture

The core package, `packages/bricky/src/bricky`, is layered. Each module imports only from the
layers above it in this list:

1. `errors`, `settings`: the error front-ends show as a message, and configuration.
2. `units`, `geometry`: exact integer units (0.4 mm), the 24 grid rotations, boxes and convex
   solids with integer corners, and exact overlap tests between them.
3. `catalog`: parts and colors keyed by BrickLink ids, imported from BrickLink's catalog
   downloads; each part's shape is read from its official name, or converted from LDraw, and its
   geometry generated per family, with curves drawn as exact facets.
4. `model`, `provenance`, `builder`, `files`: the canonical model format, the script lines that
   placed each element, how to write models, and their files and source maps.
5. `analysis`: derived data (world geometry, spatial index, links, cells), cached in `Context`,
   and the differences between two builds.
6. `passes`, `diagnostics`, `check`: plugin passes and the reports they produce.
7. `render`: scenes resolved from a model, drawn with three.js in headless Chromium.
8. `runner`, `service`: build scripts in child processes, and every command defined once.
9. `cli`, and `bricky_mcp` in its own package: front-ends that only adapt `service`.

`bricky_bench`, in `packages/bricky-bench`, runs the benchmark in `bench/` on top of bricky's public
API. Benchmark inputs are generated from each project's reference by `bricky-bench prepare` and
committed; a reference never reaches the agent's workspace.

## Conventions

- **Tools:** use the standard, official, established tool in each category. That means uv, ruff,
  ty, rumdl, pytest with Hypothesis, pydantic and pydantic-settings, the official MCP SDK, and
  Playwright with three.js for renders.
- **Python:** 3.15 only. Use modern syntax: PEP 695 generics and `type` aliases. Annotations are
  lazy, so never write `TYPE_CHECKING` blocks.
- **Concurrency:** asyncio only. Hand blocking work to `asyncio.to_thread`; never use threading,
  multiprocessing or other event loops directly.
- **Data:** pydantic models at every boundary (files, settings, CLI, MCP). Use frozen, slotted
  dataclasses for hot geometry.
- **Exactness:** no floats inside the kernel. Convert agent units (studs, plates) at the edges.
- **One definition:** each command is a request model plus a function in `bricky.service`. The CLI
  and the MCP server derive from it and never redefine arguments.
- **Store once:** the model stores ids and poses only. Everything else is derived in `analysis` and
  never written back. Provenance is build metadata: it lives in the source map beside the model.
- **Feedback is facts:** bricky tells the agent what is true about its model and never fixes it or
  says how to. A diagnostic states what is wrong, where and which elements; the report adds what
  each element is and the script line that placed it. Advice belongs in the skill, not in bricky.
- **Passes:** pure functions of a `Context`, registered under the `bricky.passes` entry-point group.
  Each pass documents every code it emits, with the exact rule it checks (`bricky explain`), and
  emits diagnostics with that code, a message, the elements involved and a region.
- **Build scripts run in their own process** (`bricky.runner`), never in the CLI or the MCP server:
  their output is captured, a timeout stops them, and a cancelled command kills them.
- **Renders are first-class feedback:** every build draws its model by default. Renderer assets
  live in `bricky/render/assets`; three.js is vendored unmodified, so renders work offline.
- **Sources:** BrickLink, the LEGO Group's marketplace, is the source of what parts and colors
  exist. Shapes come from bricky's own families, read from official names, and otherwise from
  the LDraw.org Parts Library (CC BY, credited wherever its shapes go), the one decision to use
  a community library. Do not add other brands or community libraries. General-purpose tools
  such as three.js and numpy are fine.
- **Catalog data stays local:** imports write to bricky's data folder, never into the repository;
  tests use the sample catalog in `bricky/catalog/data`.
- **Trademark:** never put "LEGO" in a package, module or repository name. In prose, use "LEGO®"
  as an adjective.
- **Tests:** every pass gets a passing case and a failing case. Geometry gets property tests.
  Renders get a test that draws real pixels.
