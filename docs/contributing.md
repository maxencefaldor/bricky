# Contributing

The rules for changing bricky live in `AGENTS.md` at the repository root, so people and every agent harness read the same rules.
A change is done when five checks pass:

```sh
uv sync
uv run playwright install chromium
uv run ruff format && uv run ruff check && uv run ty check && uv run rumdl check . && uv run pytest
```

The docs build with [Zensical](https://zensical.org), and bricky renders their images itself:

```sh
uv run python docs/reference.py   # write the reference pages generated from the code
uv run python docs/illustrate.py  # render every image into docs/images
uv run python docs/gallery.py     # write a 3D viewer for every example
uv run zensical serve             # preview the site at http://localhost:8000
```

The rest of this page is `AGENTS.md`.

--8<-- "AGENTS.md:3:"
