"""A uniform grid that answers "what might touch this box?" without comparing every pair."""

from collections import defaultdict
from collections.abc import Hashable, Iterator
from itertools import product

from bricky.geometry import Box
from bricky.units import STUD


class SpatialHash[K: Hashable]:
    """Buckets boxes into cubic grid cells for fast candidate lookup."""

    def __init__(self, cell: int = 2 * STUD) -> None:
        self._cell = cell
        self._buckets: defaultdict[tuple[int, int, int], list[K]] = defaultdict(list)

    def insert(self, key: K, box: Box) -> None:
        """Register a box under a key; a key may own several boxes."""
        for cell in self._cells(box):
            self._buckets[cell].append(key)

    def query(self, box: Box) -> set[K]:
        """Return the keys of every box that shares a grid cell with this one."""
        found: set[K] = set()
        for cell in self._cells(box):
            found.update(self._buckets.get(cell, ()))
        return found

    def _cells(self, box: Box) -> Iterator[tuple[int, int, int]]:
        size = self._cell
        lo, hi = box.min, box.max
        return product(
            range(lo.x // size, (hi.x - 1) // size + 1),
            range(lo.y // size, (hi.y - 1) // size + 1),
            range(lo.z // size, (hi.z - 1) // size + 1),
        )
