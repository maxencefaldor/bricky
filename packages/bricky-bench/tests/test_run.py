import asyncio
import json
import sys
from pathlib import Path

from bricky.service import Session
from bricky_bench.projects import load_projects
from bricky_bench.run import Agent, Completed, footer, read_transcript, run_projects

ROOT = Path(__file__).parents[3]
FAKE = Path(__file__).with_name("fake_claude.py")
PROJECTS = {p.id: p for p in load_projects(ROOT / "bench" / "projects")}


def test_prompts_end_with_where_to_work_and_where_the_answer_goes():
    text = footer(PROJECTS["02-pixel-heart"])
    assert "The `inputs/` folder holds `heart.png` and `heart.txt`." in text
    assert "`models/pixel_heart.py`" in text
    assert "inputs/" not in footer(PROJECTS["01-wall"])


def test_claude_code_runs_headless_within_the_budget():
    argv = Agent(model="opus").argv("Build a wall.", max_turns=30)
    assert argv[:3] == ["claude", "-p", "Build a wall."]
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in argv
    assert argv[argv.index("--max-turns") + 1] == "30"
    assert argv[argv.index("--allowedTools") + 1].endswith("Bash(uv run *)")
    assert argv[argv.index("--model") + 1] == "opus"


def test_transcripts_give_turns_cost_and_builds():
    lines = [
        "not json",
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "uv run bricky build models/a.py"},
                        },
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "uv run bricky parts slope"},
                        },
                    ]
                },
            }
        ),
        json.dumps({"type": "result", "subtype": "error_max_turns", "num_turns": 30}),
    ]
    done = Completed(code=1, stdout="\n".join(lines).encode(), stderr=b"", seconds=90)
    run = read_transcript(done)
    assert (run.builds, run.turns, run.outcome, run.minutes) == (1, 30, "error_max_turns", 1.5)


def test_a_run_builds_the_answer_in_its_workspace_and_scores_it(tmp_path, monkeypatch):
    project = PROJECTS["01-wall"]
    monkeypatch.setenv("FAKE_SOLUTION", str(project.reference))
    agent = Agent(command=(sys.executable, str(FAKE)))

    async def go():
        async with Session() as session:
            return await run_projects(
                [project],
                repository=ROOT,
                output=tmp_path,
                agent=agent,
                repeats=1,
                jobs=1,
                session=session,
            )

    (record,) = asyncio.run(go())
    score = record.score
    assert score.built, score.failure
    assert (score.errors, score.elements) == (0, 27)
    assert score.fidelity is not None
    assert (score.fidelity.shape, score.fidelity.color) == (1.0, 1.0)
    assert (record.agent.exit_code, record.agent.turns, record.agent.builds) == (0, 3, 1)

    run = tmp_path / "01-wall" / "1"
    assert (run / "transcript.jsonl").read_text().count('"type": "result"') == 1
    assert json.loads((run / "record.json").read_text())["project"] == "01-wall"
    workspace = run / "workspace"
    assert (workspace / "models" / "wall.py").is_file()
    assert (workspace / "models" / "wall.bricky.json").is_file()
    assert (workspace / ".claude" / "skills" / "build-model" / "SKILL.md").is_file()
    assert not (workspace / ".venv").exists()
    assert not list(workspace.rglob("reference.py"))
    assert (
        "| 01-wall | 1 | 1 | yes | 0 | 1.00 | 1.00 | 3 | 1 |"
        in (tmp_path / "summary.md").read_text()
    )
