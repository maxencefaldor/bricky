# Benchmark

Ten projects, from a brick wall to Notre-Dame de Paris, that measure how well an agent builds LEGO® models with bricky.
The [benchmark page](https://maxencefaldor.github.io/bricky/agents/benchmark/) describes the projects, the scores and the results.

## Running it

Run the benchmark from the repository root, with Claude Code (`claude`) signed in:

```sh
uv run bricky-benchmark list                      # the projects and their inputs
uv run bricky-benchmark prepare                   # write the inputs generated from references
uv run bricky-benchmark run --project 1           # run one project, then score it
uv run bricky-benchmark run --repeats 3 --jobs 2  # every project three times, two at a time
```

## A project

Each project is a folder under `projects/`:

```text
projects/04-house-plans/
  project.toml   title, difficulty, prompt, turn and time budgets, and inputs to generate
  reference.py   the model the prompt asks for; never shown to the agent
  inputs/        what the agent receives besides the prompt
```

The command `bricky-benchmark prepare` renders the inputs listed under `[[generate]]` in `project.toml`, images and plans of layers, from the reference.
The inputs are committed, so every run gives the agent the same files.
