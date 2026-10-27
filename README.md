# bricky

A compiler-style toolkit that lets AI agents design buildable LEGO® models.

Agents write models as Python build scripts. bricky compiles them into exact geometry, checks
them, and answers with diagnostics an agent can act on, the way a compiler answers a programmer.

> Status: v0.1, the foundation. It has the exact-geometry kernel, a starter catalog of 30 classic
> parts, the digital checks (schema, collision, connectivity), the `bricky` command line and an MCP
> server. Brick packing, renders, targets and physics come next.

## Quick start

```sh
uv sync
uv run bricky build examples/tower.py    # 0 errors
uv run bricky build examples/broken.py   # one mistake of each kind
uv run bricky parts "plate 2x4"
uv run bricky passes
```

A broken model reads like a compiler error:

```text
error[E202]: 4 studs of base push into offset, which has no receptor there
  --> x 0.2..1.8  y 0.2..1.8  z 3..3.5
   = elements: base, offset
   = help: line offset up with the stud grid of base, or move it clear
```

## Writing a model

```python
from bricky import ModelBuilder


def build() -> ModelBuilder:
    builder = ModelBuilder("wall")
    builder.place("3001", at=(0, 0, 0), color="Red")  # Brick 2 x 4
    builder.place("3001", at=(0, 2, 3), rot="R90", color="Red")  # turned a quarter
    return builder
```

- **Coordinates:** `(x, y, z)` with x east and y north in studs, and z up in plates. A brick is three
  plates tall.
- **Placement:** `at` is the minimum corner of the part's rotated bounding box.
- **Rotations:** `R0`, `R90`, `R180` and `R270` turn about the vertical axis. Any of the 24 grid
  rotations can be named by the images of x and y, such as `+x-y` for upside down.
- **Reuse:** `builder.component("column")` stores a group of parts once;
  `builder.instance("column", at=...)` places copies.
- **Parts and colours:** ids follow the BrickLink catalog, such as `3001` and `Dark Bluish Gray`.

## Checks

| Code | Pass | Meaning |
| --- | --- | --- |
| E101 | schema | The part is not in the catalog |
| E102 | schema | The colour is not in the catalog |
| E103 | schema | A part reaches below the ground plane |
| E201 | collision | Two parts occupy the same space |
| E202 | collision | Studs push into a part that has no receptor there |
| E301 | connectivity | A group of parts has no connected path to the ground |

Passes are plugins, registered under the `bricky.passes` entry-point group. Profiles choose which
passes run: `digital`, the default, runs the three above. `physical` adds stability, buildability
and budget, which a separate plugin pack will provide; until then, they are reported as not
installed.

## Using bricky from an agent

- **Claude Code:** run the CLI directly. The `build-model` skill in `.claude/skills` teaches the
  workflow.
- **Any MCP client:** `uv run bricky-mcp` serves `build_model`, `check_model`, `search_parts` and
  `list_passes` over stdio. Their arguments are generated from the same request models as the CLI.

## Layout

| Path | What lives there |
| --- | --- |
| `packages/bricky` | The core: units, geometry, catalog, model format, analyses, passes, service, CLI |
| `packages/bricky-mcp` | The MCP server, a thin adapter over `bricky.service` |
| `examples` | Build scripts to try |

## Development

```sh
uv sync                      # Python 3.15 and every tool, from uv.lock
uv run pytest                # tests, with Hypothesis property tests
uv run ruff format           # format
uv run ruff check            # lint
uv run ty check              # types
uv run rumdl check .         # Markdown
uvx prek install             # run the same checks before each commit
```

## Trademark

LEGO® is a trademark of the LEGO Group, which does not sponsor, authorize or endorse this project.

## License

[Apache-2.0](LICENSE)
