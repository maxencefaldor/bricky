# bricky-benchmark

The benchmark runner for [bricky](https://github.com/maxencefaldor/bricky): it runs each project with Claude Code and scores the model the agent builds.

The [benchmark page](https://maxencefaldor.github.io/bricky/agents/benchmark/) describes the projects and the scores.

The package ships only with the repository, because it runs the projects in the repository's `benchmark/` folder.
Run it from a clone, after `uv sync`, with Claude Code (`claude`) signed in:

```sh
uv run bricky-benchmark list                      # the projects and their inputs
uv run bricky-benchmark prepare                   # write the inputs generated from references
uv run bricky-benchmark run --project 1           # run one project, then score it
uv run bricky-benchmark run --repeats 3 --jobs 2  # every project three times, two at a time
uv run bricky-benchmark run --model opus          # choose Claude Code's model
```
