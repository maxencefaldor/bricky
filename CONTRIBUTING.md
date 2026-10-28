# Contributing

`AGENTS.md` holds bricky's architecture, conventions, vocabulary and writing rules, for people and
agents alike. The [contributing guide](https://maxencefaldor.github.io/bricky/contributing/) shows
the same rules with the commands that check them.

A change is done when the five checks pass:

```sh
uv sync
uv run playwright install chromium
uv run ruff format && uv run ruff check && uv run ty check && uv run rumdl check . && uv run pytest
```

Changes that alter what a picture shows also redraw the docs' pictures:
`uv run python docs/illustrate.py`.
