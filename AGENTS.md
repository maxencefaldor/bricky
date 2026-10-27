# Working on bricky

bricky is a compiler-style toolkit that lets AI agents design buildable LEGO® models. Read
`README.md` for what it does. This file says how to change it.

## Commands

```sh
uv sync                  # install Python 3.15 and every tool from uv.lock
uv run pytest            # tests; warnings are errors
uv run ruff format       # format
uv run ruff check        # lint, with every rule enabled
uv run ty check          # types
uv run rumdl check .     # Markdown
```

A change is done when all five pass.

## Architecture

The core package, `packages/bricky/src/bricky`, is layered. Each module imports only from the
layers above it in this list:

1. `units`, `geometry`: exact integer units (0.4 mm) and the 24 grid rotations.
2. `catalog`: parts and colours keyed by BrickLink ids; geometry is generated per family.
3. `model`, `builder`, `files`: the canonical model format and how to write it.
4. `analysis`: derived data (world geometry, spatial index, links), cached in `Context`.
5. `passes`, `diagnostics`, `check`: plugin passes and the reports they produce.
6. `settings`, `service`: configuration, and every command defined once.
7. `cli`, and `bricky_mcp` in its own package: front-ends that only adapt `service`.

## Conventions

- **Tools:** use the standard, official, established tool in each category. That means uv, ruff,
  ty, rumdl, pytest with Hypothesis, pydantic and pydantic-settings, and the official MCP SDK.
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
  never written back.
- **Passes:** pure functions of a `Context`, registered under the `bricky.passes` entry-point group.
  Each pass emits diagnostics with a stable code, the elements involved, a region and a fix.
- **Official sources only:** LEGO and BrickLink data and formats. Do not add LDraw, other brands or
  community libraries.
- **Trademark:** never put "LEGO" in a package, module or repository name. In prose, use "LEGO®"
  as an adjective.
- **Tests:** every pass gets a passing case and a failing case. Geometry gets property tests.
