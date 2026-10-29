# Copyright 2026 Maxence Faldor
"""Connectivity: groups of parts with no connected path to the ground."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from typing import ClassVar

from bricky.analysis import Context
from bricky.diagnostics import Diagnostic, Region, Rule
from bricky.geometry import Box
from bricky.settings import Level


class ConnectivityPass:
    """Report every group of connected parts that stays above the ground (z = 0)."""

    name: ClassVar[str] = "connectivity"
    summary: ClassVar[str] = "Groups of parts with no connected path to the ground."
    rules: ClassVar[tuple[Rule, ...]] = (
        Rule(
            name="floating-group",
            default_level=Level.ERROR,
            condition=(
                "Two elements are connected when a stud of one sits in an anti-stud of "
                "the other at the same position, facing it. A connection works both "
                "ways: an element held only from above is connected. A group of "
                "connected elements is grounded when any element in it has its bottom "
                "at z = 0 or below. The pass reports every ungrounded group once, with "
                "all its elements and the box around them."
            ),
        ),
    )

    def run(self, context: Context) -> Iterator[Diagnostic]:
        """Yield one diagnostic for every ungrounded group of connected parts."""
        elements = context.world.elements
        parent = list(range(len(elements)))

        def root(i: int) -> int:
            path = [i]
            while (up := parent[path[-1]]) != path[-1]:
                path.append(up)
            for node in path:
                parent[node] = up
            return up

        for connection in context.connections:
            parent[root(connection.a)] = root(connection.b)

        groups: defaultdict[int, list[int]] = defaultdict(list)
        for i in range(len(elements)):
            groups[root(i)].append(i)

        for members in sorted(groups.values()):
            if any(elements[k].bounds.min.z <= 0 for k in members):
                continue
            what = (
                "1 element floats"
                if len(members) == 1
                else f"{len(members)} elements float"
            )
            yield Diagnostic(
                rule="floating-group",
                message=f"{what}: no chain of stud connections leads to the ground",
                elements=tuple(elements[k].uid for k in members),
                region=Region.of(Box.bounding(elements[k].bounds for k in members)),
            )
