# bricky-bench

The benchmark runner for [bricky](../../README.md).
The projects, and how to run them, are in [`bench/`](../../bench/README.md).

```sh
uv run bricky-bench list             # the ten projects
uv run bricky-bench prepare          # write inputs generated from references
uv run bricky-bench run --project 1  # run a project with Claude Code, then score it
```
