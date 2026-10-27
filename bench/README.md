# bricky benchmark

Ten projects, from a brick wall to Notre-Dame de Paris, that measure how well an agent builds
LEGO® models with bricky. Each project is a prompt, sometimes with inputs: pictures, a cell-by-cell
plan, notes, or a broken script to repair. Seven have a reference model the agent never sees, and
are scored against it; the other three are open briefs, judged by looking at the result.

| # | Project | What the agent gets | Scored |
| --- | --- | --- | --- |
| 1 | A brick wall | A precise description | Against a reference |
| 2 | A pixel heart | A 12 x 12 pixel plan and a picture | Against a reference |
| 3 | Repair a footbridge | A build script with mistakes | Against a reference |
| 4 | A house from its plans | Plans with rulers: six views | Against a reference |
| 5 | A toadstool from its layers | A plan of every plate level | Against a reference |
| 6 | A lighthouse from one picture | One picture, no measurements | Against a reference |
| 7 | A red telephone box | Notes on the K6 kiosk | Judged |
| 8 | A five-storey pagoda | Notes on Tō-ji's pagoda | Judged |
| 9 | A castle from its plans | Plans with rulers, 493 elements | Against a reference |
| 10 | Notre-Dame de Paris | Notes on the cathedral | Judged |

## Running it

```sh
uv run bricky-bench list                     # the projects and their inputs
uv run bricky-bench run --project 1          # run one project with Claude Code
uv run bricky-bench run --repeats 3 --jobs 2 # every project three times, two at a time
uv run bricky-bench run --model opus         # choose Claude Code's model
```

Run from the repository root. Each run needs Claude Code (`claude`) signed in, and costs real
model usage.

For every run, the runner:

1. Builds bricky's wheel and makes a fresh workspace in the system's temporary folder, outside the
   repository: a uv project that installs that wheel, plus the `build-model` skill, the
   `examples/` scripts and the project's `inputs/`. The agent never sees `reference.py`.
2. Starts Claude Code there in print mode with the project's prompt and its turn and time budget.
   The agent may read, write and edit files, and run commands through `uv run`.
3. Builds the agent's final `models/<name>.py` in the same workspace, exactly as the agent would,
   and scores it.

Everything lands in `bench/runs/<time>/`: per run the transcript, the agent's log, its workspace
(script, model, source map and pictures) and `record.json`; for the whole invocation
`summary.json` and `summary.md`.

## Scores

- **Facts:** whether the final script builds, its element count, and its errors and warnings.
- **Fidelity**, for projects with a reference: the two models are compared cell by cell, a cell
  being 1 x 1 stud and 1 plate tall (see `bricky.cells`). The agent's model may be turned and
  shifted; the best match counts. `shape` is the share of cells filled in both models among cells
  filled in either. `colour` counts a shared cell only when its colours match too. 1 is identical.
- **Effort:** turns, minutes, Claude Code's cost estimate, and how often the agent built.

Judged projects have facts and effort but no fidelity: compare their pictures by eye.

## A project

```text
bench/projects/04-house-plans/
  project.toml   title, difficulty, prompt, max_turns, minutes, and inputs to generate
  reference.py   the model the prompt asks for; never shown to the agent
  inputs/        what the agent gets besides the prompt
```

Inputs listed under `[[generate]]` in `project.toml` (pictures and cell plans) come from the
reference: `uv run bricky-bench prepare` writes them again after a reference changes. They are
committed, so every run gives the agent the same files.
