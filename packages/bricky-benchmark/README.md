# bricky-benchmark

The benchmark runner for [bricky](https://github.com/maxencefaldor/bricky): it runs each project with Claude Code and scores the model the agent builds.
The [benchmark page](https://maxencefaldor.github.io/bricky/agents/benchmark/) describes the projects and the scores.

```sh
uv run bricky-benchmark list             # the ten projects
uv run bricky-benchmark prepare          # write the inputs generated from references
uv run bricky-benchmark run --project 1  # run one project, then score it
```
