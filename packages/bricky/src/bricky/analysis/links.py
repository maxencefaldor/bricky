"""Find which elements click together.

A stud and a receptor mate when they sit at the same world position facing each other. Positions
are exact integers, so mating is a dictionary lookup, whatever the parts' orientations.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass

from bricky.analysis.world import World
from bricky.catalog import ConnectorKind
from bricky.geometry import Vec3

type ReceptorIndex = dict[tuple[Vec3, Vec3], list[int]]
"""Element indices owning a receptor, keyed by the receptor's world position and normal."""


@dataclass(frozen=True, slots=True)
class Link:
    """Two elements joined by one or more mated stud-receptor pairs."""

    a: int
    """Index into :attr:`World.placed`; always smaller than :attr:`b`."""

    b: int
    """Index into :attr:`World.placed`."""

    studs: int
    """Number of mated stud-receptor pairs."""


def receptor_index(world: World) -> ReceptorIndex:
    """Index every receptor by its world position and normal."""
    index: defaultdict[tuple[Vec3, Vec3], list[int]] = defaultdict(list)
    for i, placed in enumerate(world.placed):
        for connector in placed.connectors:
            if connector.kind is ConnectorKind.ANTI_STUD:
                index[connector.pos, connector.normal].append(i)
    return dict(index)


def find_links(world: World, receptors: ReceptorIndex) -> tuple[Link, ...]:
    """Return every pair of elements joined by studs, with how many studs join them."""
    counts: Counter[tuple[int, int]] = Counter()
    for i, placed in enumerate(world.placed):
        for connector in placed.connectors:
            if connector.kind is not ConnectorKind.STUD:
                continue
            for j in receptors.get((connector.pos, -connector.normal), ()):
                if j != i:
                    counts[min(i, j), max(i, j)] += 1
    return tuple(Link(a, b, studs) for (a, b), studs in sorted(counts.items()))
