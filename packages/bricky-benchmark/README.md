# bricky-benchmark

The benchmark runner for [bricky](../../README.md).
The projects, and how to run them, are in [`benchmark/`](../../benchmark/README.md).

```sh
uv run bricky-benchmark list             # the ten projects
uv run bricky-benchmark prepare          # write inputs generated from references
uv run bricky-benchmark run --project 1  # run a project with Claude Code, then score it
```
