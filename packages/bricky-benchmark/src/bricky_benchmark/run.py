# Copyright 2026 Maxence Faldor
"""Run benchmark projects with Claude Code, then score what it built.

Each run gets a fresh workspace in the system's temporary folder, outside the
repository, so the agent cannot read the references. The workspace is a uv project that
installs bricky from a wheel built for the run, with the build-model skill, the examples
and the project's inputs. Claude Code runs there in print mode, within the project's
turn and time budget. When Claude Code stops, the runner builds the agent's final script
in the same workspace, exactly as the agent would, scores it, and keeps the workspace,
the transcript and the score in the run folder.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field, ValidationError

from bricky import voxels
from bricky.analysis import Voxel, VoxelKey
from bricky.errors import BrickyError
from bricky.files import load_model, write_file
from bricky.service import BuildResult, Session
from bricky_benchmark.prepare import reference_model
from bricky_benchmark.projects import Project
from bricky_benchmark.score import Score, compare, facts

SKILL: Final = Path(".claude/skills/build-model")
"""The skill the agent works with, relative to the repository root."""

EXAMPLES: Final = Path("examples")
"""Example build scripts the skill points to, relative to the repository root."""

FOOTER: Final = (
    "\n"
    "\n"
    "---\n"
    "Work in this folder.{inputs} Write your build script as `models/{slug}.py`: "
    "it defines `build()`,\n"
    "returning a `bricky.ModelBuilder`. Build it with "
    "`uv run bricky build models/{slug}.py` as often as\n"
    "you like. When you stop, the last version of that file is your answer.\n"
)

_BUILD_MINUTES: Final = 10
_STOP_GRACE_SECONDS: Final = 10
_PINNED_PACKAGES: Final = ("playwright", "pydantic", "pydantic-settings")
_REPOSITORY_ONLY: Final = frozenset(
    {"VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONPATH", "UV_LOCKED", "UV_FROZEN"}
)
"""Environment variables that describe the repository's setup, not a workspace's."""


class Agent(BaseModel):
    """How the runner starts the agent: Claude Code in print mode by default."""

    command: tuple[str, ...] = Field(
        default=("claude",),
        description="The agent's executable and any leading arguments.",
    )
    model: str | None = Field(
        default=None, description="Model for Claude Code's --model."
    )
    tools: str = Field(
        default="Read,Write,Edit,Glob,Grep,Bash(uv run *)",
        description="Tools the agent may use without asking, as Claude Code's "
        "--allowedTools.",
    )

    def argv(self, prompt: str, max_turns: int) -> list[str]:
        """The command line that starts the agent on a prompt."""
        arguments = [
            *self.command,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--max-turns",
            str(max_turns),
            "--permission-mode",
            "acceptEdits",
            "--allowedTools",
            self.tools,
            "--permission-prompts",
            "none",
            "--no-session-persistence",
        ]
        if self.model is not None:
            arguments += ["--model", self.model]
        return arguments


class AgentRun(BaseModel):
    """What the agent's process did."""

    exit_code: int | None = Field(
        description="Exit code; null when the runner stopped the agent at its "
        "time limit."
    )
    minutes: float
    turns: int | None = Field(
        default=None, description="Turns, from Claude Code's result event."
    )
    cost_usd: float | None = Field(
        default=None, description="Claude Code's own cost estimate."
    )
    outcome: str | None = Field(
        default=None, description="The result event's subtype, such as 'success'."
    )
    builds: int = Field(default=0, description="Times the agent ran bricky build.")


class Record(BaseModel):
    """One run of one project: what the agent did, and the score of what it built."""

    project: str
    title: str
    difficulty: int
    repeat: int
    started: datetime
    bricky: str = Field(default_factory=lambda: version("bricky"))
    model: str | None = Field(
        description="The model the runner asked the agent to use, if any."
    )
    agent: AgentRun
    score: Score


@dataclass(frozen=True, slots=True)
class Completed:
    """A finished process."""

    code: int | None
    """Exit code, or ``None`` if the runner stopped the process at its time limit."""

    stdout: bytes
    stderr: bytes
    seconds: float


async def run_projects(  # noqa: PLR0913 - keyword-only options, one per concern
    projects: Sequence[Project],
    *,
    repository: Path,
    output: Path,
    agent: Agent,
    repeats: int,
    jobs: int,
    session: Session,
) -> list[Record]:
    """Run every project ``repeats`` times, at most ``jobs`` at once, scoring each run.

    Raises:
        BrickyError: If the repository lacks the skill or the examples, a reference does
            not build, or bricky's wheel fails to build.
    """
    for needed in (SKILL, EXAMPLES):
        if not (repository / needed).is_dir():
            message = (
                f"{repository} has no {needed}; "
                "run bricky-benchmark from the bricky repository root"
            )
            raise BrickyError(message)
    references: dict[str, dict[VoxelKey, Voxel]] = {}
    for project in projects:
        if project.reference is not None:
            references[project.id] = voxels(await reference_model(project, session))
    gate = asyncio.Semaphore(jobs)
    with tempfile.TemporaryDirectory(prefix="bricky-benchmark-wheel-") as scratch:
        wheel = await build_wheel(repository, Path(scratch))

        async def run_one(project: Project, repeat: int) -> Record:
            async with gate:
                return await run_project(
                    project,
                    repeat=repeat,
                    repository=repository,
                    output=output / project.id / str(repeat),
                    wheel=wheel,
                    agent=agent,
                    reference=references.get(project.id),
                    session=session,
                )

        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(run_one(project, repeat))
                for project in projects
                for repeat in range(1, repeats + 1)
            ]
    records = [task.result() for task in tasks]
    await asyncio.to_thread(write_summary, records, output)
    return records


async def run_project(  # noqa: PLR0913 - keyword-only options, one per concern
    project: Project,
    *,
    repeat: int,
    repository: Path,
    output: Path,
    wheel: Path,
    agent: Agent,
    reference: dict[VoxelKey, Voxel] | None,
    session: Session,
) -> Record:
    """Run one project once in a fresh workspace, score it, and keep the evidence.

    The evidence goes in ``output``.
    """
    started = datetime.now(UTC)
    workspace = await asyncio.to_thread(_scratch_folder, f"bricky-{project.id}-")
    try:
        await asyncio.to_thread(
            make_workspace, workspace, project, wheel=wheel, repository=repository
        )
        await _setup(workspace)
        project_file = project.spec
        prompt = project_file.prompt.strip() + footer(project)
        done = await execute(
            agent.argv(prompt, project_file.max_turns),
            folder=workspace,
            seconds=project_file.minutes * 60,
        )
        await asyncio.to_thread(write_file, output / "transcript.jsonl", done.stdout)
        await asyncio.to_thread(write_file, output / "agent.log", done.stderr)
        score = await score_workspace(workspace, project, reference, session)
        await asyncio.to_thread(_keep, workspace, output / "workspace")
    finally:
        await asyncio.to_thread(shutil.rmtree, workspace, ignore_errors=True)
    record = Record(
        project=project.id,
        title=project.spec.title,
        difficulty=project.spec.difficulty,
        repeat=repeat,
        started=started,
        model=agent.model,
        agent=read_transcript(done),
        score=score,
    )
    await asyncio.to_thread(
        write_file, output / "record.json", record.model_dump_json(indent=2).encode()
    )
    return record


def footer(project: Project) -> str:
    """The prompt's closing instructions: where to work and where the answer goes."""
    files = project.input_files()
    inputs = f" The `inputs/` folder holds {_listing(files)}." if files else ""
    return FOOTER.format(inputs=inputs, slug=project.slug)


def make_workspace(
    workspace: Path, project: Project, *, wheel: Path, repository: Path
) -> None:
    """Lay out a workspace: a uv project that uses bricky's wheel.

    The workspace also holds the skill, the examples and the project's inputs. The
    workspace pins bricky's own dependencies to the runner's versions, so renders find
    the same Playwright browser.
    """
    dependencies = [
        f"bricky @ {wheel.as_uri()}",
        *(f"{name}=={version(name)}" for name in _PINNED_PACKAGES),
    ]
    pyproject = "\n".join(
        [
            "[project]",
            'name = "workspace"',
            'version = "0"',
            # The workspace runs the Python that runs the benchmark, so its pins hold.
            f'requires-python = ">={sys.version_info.major}.{sys.version_info.minor}"',
            "dependencies = [",
            *(f'  "{dependency}",' for dependency in dependencies),
            "]",
            "",
        ]
    )
    (workspace / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    shutil.copytree(repository / SKILL, workspace / SKILL)
    (workspace / "examples").mkdir()
    for example in sorted((repository / EXAMPLES).glob("*.py")):
        shutil.copy2(example, workspace / "examples" / example.name)
    if project.inputs.is_dir():
        shutil.copytree(project.inputs, workspace / "inputs")
    (workspace / "models").mkdir()


async def build_wheel(repository: Path, output: Path) -> Path:
    """Build bricky's wheel from the repository and return its path.

    Raises:
        BrickyError: If the build fails.
    """
    command = [
        "uv",
        "build",
        "--quiet",
        "--package",
        "bricky",
        "--wheel",
        "--out-dir",
        str(output),
    ]
    done = await execute(
        command,
        folder=repository,
        seconds=_BUILD_MINUTES * 60,
        environment=_clean_environment(),
    )
    wheels = await asyncio.to_thread(lambda: sorted(output.glob("bricky-*.whl")))
    if done.code != 0 or not wheels:
        message = (
            f"could not build bricky's wheel:\n{done.stderr.decode(errors='replace')}"
        )
        raise BrickyError(message)
    return wheels[-1]


async def score_workspace(
    workspace: Path,
    project: Project,
    reference: dict[VoxelKey, Voxel] | None,
    session: Session,
) -> Score:
    """Build the agent's final script in its workspace and score the model it makes."""
    script = Path("models") / f"{project.slug}.py"
    if not await asyncio.to_thread((workspace / script).is_file):
        return Score(built=False, failure=f"the agent wrote no {script.as_posix()}")
    command = [
        "uv",
        "run",
        "--quiet",
        "bricky",
        "build",
        script.as_posix(),
        "--output-format",
        "json",
    ]
    done = await execute(
        command,
        folder=workspace,
        seconds=_BUILD_MINUTES * 60,
        environment=_clean_environment(),
    )
    if done.code is None:
        return Score(
            built=False, failure=f"building {script.as_posix()} did not finish"
        )
    try:
        result = BuildResult.model_validate_json(done.stdout)
    except ValidationError:
        failure = (
            done.stderr.decode(errors="replace").strip() or f"exit code {done.code}"
        )
        return Score(built=False, failure=failure.removeprefix("error: "))
    if result.report is None:
        return Score(built=False, failure="the build was not checked")
    score = facts(result.report, result.elements)
    if reference is not None:
        model = await asyncio.to_thread(load_model, workspace / result.model)
        score.fidelity = compare(voxels(model, session.catalog), reference)
    return score


def read_transcript(done: Completed) -> AgentRun:
    """Read the agent's stream-json transcript: its result event and bricky builds."""
    run = AgentRun(exit_code=done.code, minutes=round(done.seconds / 60, 2))
    for line in done.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "result":
            run.turns = event.get("num_turns")
            run.cost_usd = event.get("total_cost_usd")
            run.outcome = event.get("subtype")
        elif event.get("type") == "assistant":
            run.builds += sum(
                1 for command in _bash_commands(event) if "bricky build" in command
            )
    return run


def write_summary(records: Sequence[Record], output: Path) -> None:
    """Write every record as JSON, and a table of them as Markdown."""
    data = [record.model_dump(mode="json") for record in records]
    write_file(output / "summary.json", (json.dumps(data, indent=2) + "\n").encode())
    write_file(output / "summary.md", summary_table(records).encode())


def summary_table(records: Sequence[Record]) -> str:
    """A Markdown table with one row per run."""
    columns = [
        "Project",
        "Difficulty",
        "Run",
        "Built",
        "Errors",
        "Shape",
        "Color",
        "Turns",
        "Builds",
        "Minutes",
    ]
    header = ["| " + " | ".join(columns) + " |", "|" + " --- |" * len(columns)]
    rows = []
    for record in sorted(
        records, key=lambda item: (item.difficulty, item.project, item.repeat)
    ):
        score, agent = record.score, record.agent
        fidelity = score.fidelity
        rows.append(
            "| "
            + " | ".join(
                [
                    record.project,
                    str(record.difficulty),
                    str(record.repeat),
                    "yes" if score.built else "no",
                    str(score.errors) if score.built else "-",
                    f"{fidelity.shape:.2f}" if fidelity else "-",
                    f"{fidelity.color:.2f}" if fidelity else "-",
                    "-" if agent.turns is None else str(agent.turns),
                    str(agent.builds),
                    f"{agent.minutes:g}",
                ]
            )
            + " |"
        )
    return "\n".join([*header, *rows]) + "\n"


async def execute(
    command: Sequence[str],
    *,
    folder: Path,
    seconds: float,
    environment: dict[str, str] | None = None,
) -> Completed:
    """Run a command in ``folder`` for at most ``seconds`` and return its output.

    A cancelled caller stops the process before the cancellation goes on.
    """
    started = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=folder,
        env=environment if environment is not None else _clean_environment(),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if (
        process.stdout is None or process.stderr is None
    ):  # pragma: no cover - pipes requested
        message = "could not capture the process's output"
        raise BrickyError(message)
    readers = [
        asyncio.create_task(process.stdout.read()),
        asyncio.create_task(process.stderr.read()),
    ]
    code: int | None = None
    try:
        async with asyncio.timeout(seconds):
            code = await process.wait()
    except TimeoutError:
        await _stop(process)
    except BaseException:
        await _stop(process)
        for reader in readers:
            reader.cancel()
        raise
    stdout, stderr = await asyncio.gather(*readers)
    return Completed(
        code=code, stdout=stdout, stderr=stderr, seconds=time.monotonic() - started
    )


async def _stop(process: asyncio.subprocess.Process) -> None:
    """Ask a process to stop, then kill it if it lingers."""
    if process.returncode is not None:
        return
    process.terminate()
    try:
        async with asyncio.timeout(_STOP_GRACE_SECONDS):
            await process.wait()
    except TimeoutError:
        process.kill()
        await process.wait()


async def _setup(workspace: Path) -> None:
    """Create the workspace's environment, so the agent's first build starts at once."""
    done = await execute(
        ["uv", "sync", "--quiet"], folder=workspace, seconds=_BUILD_MINUTES * 60
    )
    if done.code != 0:
        message = (
            f"could not set up {workspace}:\n{done.stderr.decode(errors='replace')}"
        )
        raise BrickyError(message)


def _clean_environment() -> dict[str, str]:
    """The environment of this process, without the repository's virtual environment.

    uv's lock settings go too: a workspace has its own project, which its first sync
    locks.
    """
    executables = str(Path(sys.prefix) / "bin")
    environment = {
        key: value for key, value in os.environ.items() if key not in _REPOSITORY_ONLY
    }
    path = environment.get("PATH", "")
    environment["PATH"] = os.pathsep.join(
        folder for folder in path.split(os.pathsep) if folder != executables
    )
    return environment


def _scratch_folder(prefix: str) -> Path:
    """Make a fresh folder in the system's temporary folder, outside the repository."""
    return Path(tempfile.mkdtemp(prefix=prefix))


def _keep(workspace: Path, destination: Path) -> None:
    """Copy what the agent made into the run folder, leaving out its environment."""
    shutil.copytree(
        workspace,
        destination,
        ignore=shutil.ignore_patterns(".venv", "__pycache__", "uv.lock"),
        dirs_exist_ok=True,
    )


def _bash_commands(event: dict[str, object]) -> list[str]:
    """The commands of the Bash tool calls in an assistant event."""
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    commands = []
    for block in content:
        if (
            isinstance(block, dict)
            and block.get("type") == "tool_use"
            and block.get("name") == "Bash"
        ):
            tool_input = block.get("input")
            command = (
                tool_input.get("command") if isinstance(tool_input, dict) else None
            )
            if isinstance(command, str):
                commands.append(command)
    return commands


def _listing(files: Sequence[str]) -> str:
    quoted = [f"`{name}`" for name in files]
    if len(quoted) == 1:
        return quoted[0]
    return ", ".join(quoted[:-1]) + " and " + quoted[-1]
