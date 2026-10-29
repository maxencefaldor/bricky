# Copyright 2026 Maxence Faldor
"""bricky-benchmark: benchmark projects for agents that build LEGO® models with bricky.

Projects live in ``benchmark/projects``. ``bricky-benchmark run`` runs them with Claude
Code and scores what it builds; see :mod:`bricky_benchmark.run`.
"""

from __future__ import annotations

from bricky_benchmark.projects import Project, ProjectFile, load_projects
from bricky_benchmark.score import Fidelity, Score, compare

__all__ = ["Fidelity", "Project", "ProjectFile", "Score", "compare", "load_projects"]
