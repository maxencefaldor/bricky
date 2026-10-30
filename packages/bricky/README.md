# bricky

A compiler for LEGO® models, built for AI agents.

[![The Japanese garden example: a pagoda, a torii and cherry trees in bloom around a koi pond](https://raw.githubusercontent.com/maxencefaldor/bricky/main/docs/images/hero.jpg)](https://maxencefaldor.github.io/bricky/gallery/)

An AI agent writes a LEGO® model as a Python build script, and bricky builds it [the way a compiler builds code](https://maxencefaldor.github.io/bricky/agents/why-a-compiler/).
Each build places every part in exact geometry, reports each mistake with the script line behind it, and renders four views with rulers.

## Install

A [uv](https://docs.astral.sh/uv/) project holds your build scripts, and uv installs Python if needed.
The project pins Python 3.14, the version bricky recommends: on 3.15, installing compiles the solver HiGHS, which needs a C++ compiler.

```sh
uv init --bare --pin-python --python 3.14 my-models  # a project for your build scripts
cd my-models
uv add bricky                                        # bricky and every dependency, from PyPI
uv run playwright install chromium                   # the browser bricky renders in, once per machine
```

With pip on Python 3.12 to 3.14, run `pip install bricky` and then `playwright install chromium`.
On Linux, `playwright install --with-deps chromium` also installs the browser's system libraries.
To install bricky as a tool, run `uv tool install --python 3.14 bricky --with-executables-from playwright`, then `playwright install chromium`.
The command is then `bricky`, without `uv run`.

## Build a model

A build script defines `build()`, which places parts by their BrickLink id, in studs and plates.
Save this tower as `tower.py`:

```python
from bricky import ModelBuilder


def build() -> ModelBuilder:
    builder = ModelBuilder("tower")
    for level in range(6):
        z = 3 * level  # a brick is three plates tall
        if level % 2 == 0:
            builder.place("3001", at=(0, 0, z), color="Red")  # Brick 2 x 4
            builder.place("3001", at=(2, 0, z), color="Red")
        else:  # rotated 90 degrees, each brick bridges the two below
            builder.place("3001", at=(0, 0, z), rotation="R90", color="White")
            builder.place("3001", at=(0, 2, z), rotation="R90", color="White")
    return builder
```

The build saves the model as `tower.bricky.json`, prints the report and renders the sheet `tower.png`:

```sh
uv run bricky build tower.py
```

## Learn more

- [Get started](https://maxencefaldor.github.io/bricky/get-started/): a tutorial that builds a wall, reads its report and fixes it.
- [Connect an agent](https://maxencefaldor.github.io/bricky/agents/connect/): the command line, the MCP server (`bricky-mcp`) and the skill.
- [Gallery](https://maxencefaldor.github.io/bricky/gallery/): larger models in 3D viewers, each with its build script.
- [Source](https://github.com/maxencefaldor/bricky): the repository, with every example and the benchmark.

## Disclaimer

LEGO® is a trademark of the LEGO Group, which does not sponsor, authorize or endorse this project.
