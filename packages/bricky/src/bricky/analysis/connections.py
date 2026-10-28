"""Connections: which elements join, stud in anti-stud.

A stud fits an anti-stud when the two sit at the same world position, facing each other.
Positions are exact integers, so a dictionary lookup finds every match, whatever the rotations.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass

from bricky.analysis.world import World
from bricky.catalog import ConnectorKind
from bricky.geometry import Vector

type AntiStudIndex = dict[tuple[Vector, Vector], list[int]]
"""Indices of the elements that have an anti-stud, keyed by its world position and normal."""


@dataclass(frozen=True, slots=True)
class Connection:
    """Two elements joined by studs of one in anti-studs of the other."""

    a: int
    """Index into :attr:`World.elements`; always smaller than :attr:`b`."""

    b: int
    """Index into :attr:`World.elements`."""

    studs: int
    """The number of studs that join the two."""


def anti_stud_index(world: World) -> AntiStudIndex:
    """Index every anti-stud by its world position and normal."""
    index: defaultdict[tuple[Vector, Vector], list[int]] = defaultdict(list)
    for i, element in enumerate(world.elements):
        for connector in element.connectors:
            if connector.kind is ConnectorKind.ANTI_STUD:
                index[connector.position, connector.normal].append(i)
    return dict(index)


def find_connections(world: World, anti_studs: AntiStudIndex) -> tuple[Connection, ...]:
    """Return every pair of elements joined by studs, with the number of studs that join them."""
    counts: Counter[tuple[int, int]] = Counter()
    for i, element in enumerate(world.elements):
        for connector in element.connectors:
            if connector.kind is not ConnectorKind.STUD:
                continue
            for j in anti_studs.get((connector.position, -connector.normal), ()):
                if j != i:
                    counts[min(i, j), max(i, j)] += 1
    return tuple(Connection(a, b, studs) for (a, b), studs in sorted(counts.items()))
