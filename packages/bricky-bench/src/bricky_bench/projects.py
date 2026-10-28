# Copyright 2026 Maxence Faldor
"""Benchmark projects: a prompt, inputs and a budget, and sometimes a reference.

Each project is a folder under ``bench/projects``, named ``NN-name``:

- ``project.toml``: the title, difficulty (1 to 10), prompt and budget, and any inputs
  to generate from the reference (see :class:`ProjectFile`).
- ``inputs/``: everything the agent receives besides the prompt: pictures, descriptions,
  blueprints, scripts. The runner copies this folder into the agent's workspace.
- ``reference.py``, optional: a build script for the model the project asks for. The
  agent never sees the reference. The runner scores a project with a reference by
  comparing voxels (see :mod:`bricky_bench.score`).
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from bricky.errors import BrickyError
from bricky.render import View

PROJECT_FILE: Final = "project.toml"
REFERENCE_FILE: Final = "reference.py"
INPUTS_DIR: Final = "inputs"


class _FileModel(BaseModel):
    """A part of ``project.toml``: frozen, and rejecting keys it does not define."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Render(_FileModel):
    """A picture of the reference, drawn by bricky's renderer."""

    kind: Literal["render"]
    file: str = Field(
        description="Path of the PNG to write, relative to the project folder."
    )
    view: View = Field(default=View.SHEET, description="The view to draw.")
    caption: str | None = Field(
        default=None,
        description="Text for the line above the views, replacing bricky's summary, "
        "which states the model's size and element count.",
    )
    width: int = Field(default=1600, ge=200, le=4096)
    height: int = Field(default=1200, ge=200, le=4096)


class Layers(_FileModel):
    """The reference's voxels as text: one plan per plate level, with a color legend."""

    kind: Literal["layers"]
    file: str = Field(
        description="Path of the text file to write, relative to the project folder."
    )
    levels: tuple[int, ...] | None = Field(
        default=None, description="Plate levels to write, all of them when omitted."
    )


type Generated = Annotated[Render | Layers, Field(discriminator="kind")]


class ProjectFile(_FileModel):
    """What ``project.toml`` holds."""

    title: str = Field(description="A short name, such as 'A brick wall'.")
    difficulty: int = Field(
        ge=1, le=10, description="1 is the easiest, 10 the hardest."
    )
    prompt: str = Field(description="What the agent is asked to build.")
    max_turns: int = Field(ge=1, description="Agentic turns the agent may take.")
    minutes: int = Field(ge=1, description="Wall-clock time the agent may take.")
    generate: tuple[Generated, ...] = Field(
        default=(),
        description="Inputs written from the reference by `bricky-bench prepare`.",
    )


@dataclass(frozen=True, slots=True)
class Project:
    """A project folder and what its ``project.toml`` says."""

    id: str
    """The folder name, such as ``"04-house-plans"``."""

    path: Path
    spec: ProjectFile

    @property
    def slug(self) -> str:
        """The agent's script name: the folder name without its number.

        The folder ``04-house-plans`` gives the script name ``house_plans``.
        """
        _, _, name = self.id.partition("-")
        return (name or self.id).replace("-", "_")

    @property
    def reference(self) -> Path | None:
        """The reference build script, if the project has one."""
        path = self.path / REFERENCE_FILE
        return path if path.is_file() else None

    @property
    def inputs(self) -> Path:
        """The folder of inputs the agent receives."""
        return self.path / INPUTS_DIR

    def input_files(self) -> list[str]:
        """The agent's inputs, as paths relative to the inputs folder, sorted."""
        if not self.inputs.is_dir():
            return []
        return sorted(
            path.relative_to(self.inputs).as_posix()
            for path in self.inputs.rglob("*")
            if path.is_file()
        )


def load_project(path: Path) -> Project:
    """Read one project folder.

    Raises:
        BrickyError: If the folder has no valid ``project.toml``.
    """
    file = path / PROJECT_FILE
    try:
        project_file = ProjectFile.model_validate(
            tomllib.loads(file.read_text(encoding="utf-8"))
        )
    except FileNotFoundError:
        message = f"{path} has no {PROJECT_FILE}"
        raise BrickyError(message) from None
    except (tomllib.TOMLDecodeError, ValidationError) as error:
        message = f"{file} is not a valid project file:\n{error}"
        raise BrickyError(message) from None
    return Project(id=path.name, path=path, spec=project_file)


def load_projects(root: Path, wanted: tuple[str, ...] = ()) -> list[Project]:
    """Read every project under a folder, sorted by name, or just the wanted ones.

    A wanted name is a folder name or a project number, so ``"4"`` and ``"04"`` both
    find ``04-house-plans``.

    Raises:
        BrickyError: If the folder holds no projects, or a wanted project is missing.
    """
    if not root.is_dir():
        message = (
            f"no projects folder at {root}; "
            "run bricky-bench from the bricky repository root"
        )
        raise BrickyError(message)
    projects = [load_project(path) for path in sorted(root.iterdir()) if path.is_dir()]
    if not projects:
        message = f"{root} holds no projects"
        raise BrickyError(message)
    if not wanted:
        return projects
    chosen: list[Project] = []
    for name in wanted:
        matches = [project for project in projects if _named(project, name)]
        if not matches:
            known = ", ".join(project.id for project in projects)
            message = f"no project {name!r}; projects: {known}"
            raise BrickyError(message)
        chosen.extend(match for match in matches if match not in chosen)
    return chosen


def _named(project: Project, name: str) -> bool:
    """Whether ``name`` is the project's folder name or its number."""
    number, _, _ = project.id.partition("-")
    return name == project.id or (
        name.isdigit() and number.isdigit() and int(name) == int(number)
    )
