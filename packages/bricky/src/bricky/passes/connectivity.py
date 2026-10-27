"""Connectivity: groups of parts with no connected path to the ground."""

from collections import defaultdict
from collections.abc import Iterator
from typing import ClassVar

from bricky.analysis import Context
from bricky.diagnostics import Diagnostic, Region
from bricky.geometry import Box


class ConnectivityPass:
    """Report every group of connected parts that does not reach the ground plane (z = 0)."""

    name: ClassVar[str] = "connectivity"
    summary: ClassVar[str] = "Groups of parts with no connected path to the ground."

    def run(self, context: Context) -> Iterator[Diagnostic]:
        """Return the problems found in the model."""
        placed = context.world.placed
        parent = list(range(len(placed)))

        def root(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for link in context.links:
            parent[root(link.a)] = root(link.b)

        groups: defaultdict[int, list[int]] = defaultdict(list)
        for i in range(len(placed)):
            groups[root(i)].append(i)

        for members in sorted(groups.values()):
            if any(placed[k].bounds.lo.z <= 0 for k in members):
                continue
            single = len(members) == 1
            what = "1 element floats" if single else f"{len(members)} elements float"
            fix = "connect it" if single else "connect them"
            yield Diagnostic(
                code="E301",
                check=self.name,
                message=f"{what} with no path to the ground",
                elements=tuple(placed[k].uid for k in members),
                region=Region.of(Box.bounding(placed[k].bounds for k in members)),
                help=f"{fix} to the structure below, or rest a part on the ground (z = 0)",
            )
