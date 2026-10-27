"""The ``bricky-bench`` command line: list projects, prepare their inputs, run them.

Run it from the bricky repository root, where ``bench/projects`` lives.
"""

import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import override

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    CliApp,
    CliSubCommand,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from bricky.errors import BrickyError
from bricky.service import Session
from bricky_bench.prepare import prepare
from bricky_bench.projects import load_projects
from bricky_bench.run import Agent, run_projects, summary_table

_PROJECTS_HELP = "Folder holding the projects."
_WANTED_HELP = "Projects to use, by folder name or number, such as '04-house-plans' or '4'."


class _Selection(BaseModel):
    projects_dir: Path = Field(default=Path("bench/projects"), description=_PROJECTS_HELP)
    project: tuple[str, ...] = Field(default=(), description=_WANTED_HELP)


class ListCommand(_Selection):
    """List the projects: difficulty, title, whether a reference scores them, and inputs."""

    def cli_cmd(self) -> None:
        """Run the command."""
        for project in load_projects(self.projects_dir, self.project):
            scored = "scored" if project.reference is not None else "judged"
            inputs = ", ".join(project.input_files()) or "prompt only"
            print(f"{project.id}  [{project.spec.difficulty}] {project.spec.title} ({scored})")
            print(f"    inputs: {inputs}")


class PrepareCommand(_Selection):
    """Write the inputs each project generates from its reference: pictures and cell plans."""

    async def cli_cmd(self) -> None:
        """Run the command."""
        projects = load_projects(self.projects_dir, self.project)
        async with Session() as session:
            for project in projects:
                for path in await prepare(project, session):
                    print(f"wrote {path}")


class RunCommand(_Selection):
    """Run projects with Claude Code, score what it builds, and keep everything in a run folder."""

    repeats: int = Field(default=1, ge=1, description="Runs of each project.")
    jobs: int = Field(default=1, ge=1, description="Runs at the same time.")
    out: Path = Field(
        default=Path("bench/runs"), description="Folder for run folders, one per invocation."
    )
    model: str | None = Field(default=None, description="Model for Claude Code's --model.")
    agent_command: tuple[str, ...] = Field(
        default=("claude",), description="The agent's executable and any leading arguments."
    )

    async def cli_cmd(self) -> None:
        """Run the command."""
        projects = load_projects(self.projects_dir, self.project)
        out = self.out / datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        agent = Agent(command=self.agent_command, model=self.model)
        async with Session() as session:
            records = await run_projects(
                projects,
                repo=Path.cwd(),
                out=out,
                agent=agent,
                repeats=self.repeats,
                jobs=self.jobs,
                session=session,
            )
        print(summary_table(records), end="")
        print(f"\nruns kept in {out}")


class BrickyBench(BaseSettings):
    """Benchmark agents that build LEGO® models with bricky."""

    model_config = SettingsConfigDict(
        cli_prog_name="bricky-bench",
        cli_kebab_case=True,
        cli_implicit_flags=True,
        cli_hide_none_type=True,
        cli_avoid_json=True,
        cli_enforce_required=True,
    )

    list: CliSubCommand[ListCommand] = Field(description="List the projects.")
    prepare: CliSubCommand[PrepareCommand] = Field(
        description="Write the inputs projects generate from their references."
    )
    run: CliSubCommand[RunCommand] = Field(description="Run projects with Claude Code.")

    @classmethod
    @override
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Take arguments from the command line only."""
        return (init_settings,)

    def cli_cmd(self) -> None:
        """Run the chosen subcommand."""
        CliApp.run_subcommand(self)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the command line; exit 2 on errors."""
    try:
        CliApp.run(BrickyBench, cli_args=None if argv is None else list(argv))
    except BrickyError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from None
