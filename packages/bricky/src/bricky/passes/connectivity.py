"""Connectivity: groups of parts with no connected path to the ground."""

from collections import defaultdict
from collections.abc import Iterator
from typing import ClassVar

from bricky.analysis import Context
from bricky.diagnostics import Code, Diagnostic, Region
from bricky.geometry import Box


class ConnectivityPass:
    """Report every group of connected parts that does not reach the ground plane (z = 0)."""

    name: ClassVar[str] = "connectivity"
    summary: ClassVar[str] = "Groups of parts with no connected path to the ground."
    codes: ClassVar[tuple[Code, ...]] = (
        Code(
            code="E301",
            title="Floating group",
            rule="Two parts are connected when a stud of one sits in an anti-stud of the other at "
            "the same position, facing it. Connection works both ways: a part held only from "
            "above is connected. A group of connected parts is grounded when any part in it "
            "has its bottom at z = 0 or below. Every group that is not grounded is reported "
            "once, with all its elements and the box around them.",
        ),
    )

    def run(self, context: Context) -> Iterator[Diagnostic]:
        """Return the problems found in the model."""
        elements = context.world.elements
        parent = list(range(len(elements)))

        def root(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for connection in context.connections:
            parent[root(connection.a)] = root(connection.b)

        groups: defaultdict[int, list[int]] = defaultdict(list)
        for i in range(len(elements)):
            groups[root(i)].append(i)

        for members in sorted(groups.values()):
            if any(elements[k].bounds.min.z <= 0 for k in members):
                continue
            what = "1 element floats" if len(members) == 1 else f"{len(members)} elements float"
            yield Diagnostic(
                code="E301",
                pass_name=self.name,
                message=f"{what}: no chain of stud connections leads to the ground",
                elements=tuple(elements[k].uid for k in members),
                region=Region.of(Box.bounding(elements[k].bounds for k in members)),
            )
