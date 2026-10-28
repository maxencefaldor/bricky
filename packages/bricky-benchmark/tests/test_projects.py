# Copyright 2026 Maxence Faldor

import asyncio
from pathlib import Path

import pytest

from bricky import BrickyError, Settings, check_model, default_catalog
from bricky.service import run_script
from bricky_benchmark.prepare import layers_text
from bricky_benchmark.projects import Layers, Project, Render, load_projects

ROOT = Path(__file__).parents[3]
PROJECTS = load_projects(ROOT / "benchmark" / "projects")


def test_ten_projects_span_every_difficulty() -> None:
    assert len(PROJECTS) == 10
    assert sorted(p.spec.difficulty for p in PROJECTS) == list(range(1, 11))
    assert [p.slug for p in PROJECTS][:3] == ["wall", "pixel_heart", "bridge_repair"]


@pytest.mark.parametrize("project", PROJECTS, ids=lambda p: p.id)
def test_generated_inputs_exist_and_come_from_a_reference(project: Project) -> None:
    if project.spec.generate:
        assert project.reference is not None
    for item in project.spec.generate:
        assert (project.path / item.file).is_file(), item.file


@pytest.mark.parametrize(
    "project", [p for p in PROJECTS if p.reference is not None], ids=lambda p: p.id
)
def test_references_build_without_errors(project: Project) -> None:
    assert project.reference is not None
    run = asyncio.run(run_script(project.reference, Settings()))
    report = check_model(run.model)
    assert report.ok, [d.message for d in report.diagnostics]
    for item in project.spec.generate:
        if isinstance(item, Layers):
            expected = layers_text(run.model, default_catalog(), item.levels)
            assert (project.path / item.file).read_text() == expected


def test_projects_are_chosen_by_name_or_number() -> None:
    root = ROOT / "benchmark" / "projects"
    assert [p.id for p in load_projects(root, ("4", "01-wall"))] == [
        "04-house-plans",
        "01-wall",
    ]
    with pytest.raises(BrickyError, match="no project '42'"):
        load_projects(root, ("42",))


def test_pictures_are_captioned_so_they_give_no_counts_away() -> None:
    renders = [
        item for p in PROJECTS for item in p.spec.generate if isinstance(item, Render)
    ]
    assert renders
    assert all(item.caption for item in renders)
