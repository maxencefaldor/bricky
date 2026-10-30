# Working on bricky

The repository holds bricky, a compiler-style toolkit that lets AI agents design buildable LEGO® models.
The README and the docs say what bricky does; the rules below say how to change it.

## Commands

```sh
uv sync                             # install Python 3.15 and every tool from uv.lock
uv run playwright install chromium  # the browser bricky renders in, once per machine
uv run pytest                       # tests; warnings are errors
uv run ruff format                  # format
uv run ruff check                   # lint, with every rule enabled
uv run ty check                     # types
uv run rumdl check .                # Markdown
```

A change is done when all five checks pass.
To render with a Chromium you already have, set `BRICKY_RENDER_BROWSER` to its executable instead of installing Playwright's.

## Architecture

The core package, `packages/bricky/src/bricky`, is ordered.
Each module imports only from the modules listed before it:

1. `errors`, `settings`: the error front ends show as a message, and configuration.
1. `units`, `geometry`: exact integer units (0.4 mm), the 24 grid rotations, boxes and convex solids with integer corners, and exact overlap tests between them.
1. `catalog`: parts and colors keyed by BrickLink ids, imported from BrickLink's catalog downloads; each part's shape is read from its official name, or converted from LDraw, and its geometry generated per family, with curves built as exact facets.
1. `model`, `provenance`, `fill`, `builder`, `files`: the canonical model format, the script lines that placed each element, the bricks and plates that fill voxels, how to write models, and their files and source maps.
1. `exports`: a model's lots, written in formats other tools read, such as BrickLink's Wanted List; one module per format.
1. `analysis`: derived data (world geometry, spatial index, connections, voxels), cached in `Context`, the differences between two builds, contacts (where faces press and studs sit, exactly), and stability: the forces that hold a model still, as a linear program.
1. `passes`, `diagnostics`, `check`: plugin passes, the rules they check, and the reports a check produces at each rule's level.
1. `instructions`: the steps to build a model, in an order that straight moves can follow, swept exactly.
1. `render`: scenes resolved from a model, rendered with three.js in headless Chromium, and the standalone viewer.
1. `runner`, `service`: build scripts in child processes, and every command defined once.
1. `cli`, and `bricky_mcp` in its own package: front ends that only adapt `service`.

The module `bricky_benchmark`, in `packages/bricky-benchmark`, runs the benchmark in `benchmark/` on top of bricky's public API.
Benchmark inputs are generated from each project's reference by `bricky-benchmark prepare` and committed; a reference never reaches the agent's workspace.

## Conventions

- **Tools:** use the standard, official, established tool in each category.
  That means uv, ruff, ty, rumdl, pytest with Hypothesis, pydantic and pydantic-settings, the official MCP SDK, Playwright with three.js for renders, and HiGHS with Clarabel for linear programs.
- **Format and lint:** ruff's default format at 88 columns, every ruff rule, every ty rule as an error, and Markdown one sentence per line.
  The file `.editorconfig` sets the editor to match, and `.rumdl.toml` holds the Markdown rules.
  A rule is switched off only in `pyproject.toml`, as narrowly as it can be, with its reason beside it.
  Types for a dependency that ships none live in `typings/`, for the parts bricky uses.
- **Python:** 3.12 or newer; development runs on 3.15 (`.python-version`), and CI tests every version.
  Use modern syntax: PEP 695 generics and `type` aliases.
  Every module starts with `from __future__ import annotations`, which ruff adds, so annotations stay lazy: never write `TYPE_CHECKING` blocks.
- **Concurrency:** asyncio only.
  Hand blocking work to `asyncio.to_thread`; never use threading, multiprocessing or other event loops directly.
- **Data:** pydantic models at every boundary (files, settings, command line, MCP).
  Use frozen, slotted dataclasses for hot geometry.
- **Exactness:** no floats inside the kernel.
  Convert studs and plates to base units at the edges.
  The stability analysis finds contacts exactly, then solves for forces in floats.
- **One definition:** each command is a request model plus a function in `bricky.service`.
  The command line and the MCP server derive from it and never redefine arguments.
- **Store once:** the model stores ids and poses only.
  Everything else is derived in `analysis` and never written back.
  Provenance is build metadata: it lives in the source map beside the model.
- **Feedback is facts:** bricky tells the agent what is true about its model and never fixes it or says how to.
  A diagnostic states what is wrong, where and which elements; the report adds what each element is and the script line that placed it.
  Advice belongs in the skill, not in bricky.
- **Passes:** pure functions of a `Context`, registered under the `bricky.passes` entry-point group.
  Each pass lists every rule it checks, with its default level and exact condition (`bricky explain`).
  Each diagnostic it emits names one of those rules and gives a message, the elements involved and a region.
- **Rules, as in ty:** people configure rules, never passes.
  A rule's name is lowercase words joined by hyphens, and its level is `error`, `warn` or `ignore`.
  A rule whose fact surely makes a model impossible to build defaults to `error`.
  A rule that is slow to check and rests on uncertain measurements defaults to `ignore`, so a check runs it only when asked.
  Any other rule defaults to `warn`.
- **Build scripts run in their own process** (`bricky.runner`), never in the command line or the MCP server: their output is captured, a timeout stops them, and a canceled command kills them.
- **Images are first-class feedback:** every build renders its model by default.
  Renderer assets live in `bricky/render/assets`; three.js is vendored unmodified, so rendering works offline.
  The agent's images and the viewer share `viewer.js`, so a change to the viewer leaves the images pixel for pixel the same.
- **The viewer is a core plus components:** the core, in `assets/app`, renders and lays out; each component, in `assets/components`, adds one feature through the shell and never reaches into another.
  `COMPONENTS` in `render/html.py` lists them, so removing one is removing its name there and its file.
- **Sources:** BrickLink, the LEGO Group's marketplace, is the source of what parts and colors exist.
  Shapes come from bricky's own families, read from official names, and otherwise from the LDraw.org Parts Library (CC BY, credited wherever its shapes go), the one decision to use a community library.
  Do not add other brands or community libraries.
  General-purpose tools such as three.js and numpy are fine, and the viewer's icons come from Lucide, credited in `icons.js`.
- **Exports are exact:** an export writes BrickLink's own ids, which bricky's parts and colors carry.
  A format that needs other numbers, such as LEGO element numbers or LDraw colors, stays out until a source maps them exactly.
- **Catalog data stays local:** imports write to bricky's data folder, never into the repository; tests use the sample catalog in `bricky/catalog/data`.
- **Trademark:** never put "LEGO" in a package, module or repository name.
  In prose, use "LEGO®" as an adjective.
- **Tests:** every rule gets a case that reports it and a case that passes.
  Geometry gets property tests.
  Rendering gets a test that checks real pixels.

## Vocabulary

Each concept has exactly one name, used alike in code, docs, messages and images.
A word missing from this table is plain English, never a second name for a concept in it.

| Term | Meaning |
| --- | --- |
| part | A design in the catalog, by its BrickLink id, such as `3001` (Brick 2 x 4) |
| color | A BrickLink color, by its id, such as `5` (Red) |
| catalog, sample | Every part and color bricky knows, and the 112 parts and 40 colors it ships with |
| shape, family | A part's catalog data, and the generator that builds its geometry |
| element | One part in one color, placed in a model, with an `id` |
| lot | One part in one color, with how many of it a model uses |
| uid | An element's id behind the ids of the instances that hold it, such as `bay2/e3` |
| component, instance | A group of elements stored once, and one placed copy of it |
| model | The elements, components and instances a build script places |
| build script | A Python file whose `build()` returns a `ModelBuilder`; "script" for short |
| build | One run of a build script: its model saved, checked and rendered |
| at | The minimum corner of what a script places, in studs and plates, whatever its rotation |
| position, rotation, pose | Where an element's origin lands, how it is rotated, and both |
| stud, anti-stud | A connector on a part's face, and the socket under a part that a stud fits |
| connection | Two elements joined by studs of one in anti-studs of the other |
| clutch, site | The force that pulls a stud out of its anti-stud, and the studs that together need a share of it to hold a model |
| solid | A box or a convex solid of a part's body |
| base unit | 0.4 mm, the integer unit of the kernel; scripts write studs and plates |
| voxel | One stud square and one plate tall: the grid that models are compared on |
| layer, course | Every voxel at one height, and the three layers a brick spans |
| fill | What an element does to the voxels its body covers; `builder.fill` places bricks and plates in staggered courses to fill given voxels |
| plan | A description of a model to build: views with rulers, layers, or voxels |
| check, pass | One run of the rules over a model, and the analysis that checks some of them |
| rule, level | A fact a check can state, by its name, such as `floating-group`, and how a check reports it: `error`, `warn` or `ignore` |
| diagnostic, report | One statement of a rule's fact, and all the diagnostics of a check |
| grounded | Said of a group of connected elements when one of them reaches z = 0 |
| render | Make images or a viewer of a model, with three.js in headless Chromium |
| image, view, sheet | A PNG of a model, one camera's look at it, and the four-view image every build writes |
| viewer | A standalone HTML page that renders a model in 3D, to orbit and inspect in a browser |
| export | A file another tool reads, listing a model's lots, such as a BrickLink Wanted List |
| instructions, step | The order to build a model in, and the few elements that go on together |
| approach, section | The direction an element goes on along, and the function that `build()` called to place it |
| scene, mesh | What bricky renders from a model, and an element rendered by its faces |
| mark | A tint, label, outline or box that an image adds to show a diagnostic or a change |
| clip, highlight | Keep one side of a plane; render some elements in full and the rest faintly |
| agent, harness | An AI model that writes build scripts, and the program that runs it, such as Claude Code |
| front end | How an agent reaches bricky: the command line, the MCP server or the skill |
| example | A build script in `examples/`; the gallery shows the larger ones |
| project, reference, run | A benchmark task, the model it is scored against, and one agent's attempt at it |

Rotate, never turn; clip, never cut; render, never draw.
Spell American English: color, center, neighbor.
Spell words out: the only abbreviations are `id`, `uid`, `info`, `cmd` and `e`, besides `x`, `y`, `z` and loop indices.

## Writing

Docs, docstrings, comments and messages are formal, direct and plain.

- **Pages:** each page does one job, as a tutorial, a guide or a reference, and opens with one sentence that says what it gives the reader.
- **Sections:** each section states its idea in one sentence, reasons from first principles to the consequence in one short paragraph, and ends with one example: code, output or an image.
- **Sentences:** one idea each, under 25 words, subject first, active voice, present tense.
  No sentence starts with a lowercase word (code, a variable, or a name such as bricky or uv) or with "Because", "It", "It's", "There is", "This" or "Note that": name the subject instead, as in "The x axis points east".
- **Words:** say what something is or does, not what it is not, and leave out filler.
  Lists hold parallel items, tables hold lookups, and prose holds reasoning.
- **Shell blocks:** comments align two spaces after the longest command.

## Releases

The packages `bricky` and `bricky-mcp` go to PyPI together, at one version; `bricky-benchmark` runs from a clone and never goes to PyPI.

1. Set the new version in the three `pyproject.toml` files, in the `bricky==` pins, and in `CITATION.cff` with its date, then run `uv lock`.
1. Commit, push, and wait for CI to pass.
1. Tag the commit `vX.Y.Z` and push the tag: the release workflow checks, builds and tests the packages, publishes them to PyPI by trusted publishing, and makes the GitHub release.
