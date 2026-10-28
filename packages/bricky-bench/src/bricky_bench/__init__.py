# Copyright 2026 Maxence Faldor
"""bricky-bench: benchmark projects for agents that build LEGO® models with bricky.

Projects live in ``bench/projects``. ``bricky-bench run`` runs them with Claude Code and scores
what it builds; see :mod:`bricky_bench.run`.
"""

from bricky_bench.projects import Project, ProjectFile, load_projects
from bricky_bench.score import Fidelity, Score, compare

__all__ = ["Fidelity", "Project", "ProjectFile", "Score", "compare", "load_projects"]
