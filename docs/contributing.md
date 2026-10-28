# Contributing

bricky's conventions live in `AGENTS.md` at the repository root, so people and every agent harness read the same rules.
A change is done when the five checks pass:

```sh
uv sync
uv run playwright install chromium
uv run ruff format && uv run ruff check && uv run ty check && uv run rumdl check . && uv run pytest
```

The docs build with [Zensical](https://zensical.org), and their pictures come from bricky itself:

```sh
uv run python docs/illustrate.py   # draw every picture into docs/images
uv run zensical serve              # preview the site at http://localhost:8000
```

--8<-- "AGENTS.md:3:"
