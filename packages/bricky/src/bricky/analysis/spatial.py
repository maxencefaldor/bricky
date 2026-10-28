# Copyright 2026 Maxence Faldor
"""A uniform grid that finds what might touch a box without comparing every pair."""

from collections import defaultdict
from collections.abc import Hashable, Iterator
from itertools import product

from bricky.geometry import Box
from bricky.units import STUD


class SpatialHash[K: Hashable]:
    """A grid of cubic buckets holding boxes, to find boxes near a given one quickly."""

    def __init__(self, bucket: int = 2 * STUD) -> None:
        """Bucket boxes into cubes ``bucket`` base units wide."""
        self._bucket = bucket
        self._buckets: defaultdict[tuple[int, int, int], list[K]] = defaultdict(list)

    def insert(self, key: K, box: Box) -> None:
        """Add a box under a key; one key may hold several boxes."""
        for bucket in self._buckets_of(box):
            self._buckets[bucket].append(key)

    def query(self, box: Box) -> set[K]:
        """Return the keys of every box that shares a bucket with the given box."""
        found: set[K] = set()
        for bucket in self._buckets_of(box):
            found.update(self._buckets.get(bucket, ()))
        return found

    def _buckets_of(self, box: Box) -> Iterator[tuple[int, int, int]]:
        size = self._bucket
        low, high = box.min, box.max
        return product(
            range(low.x // size, (high.x - 1) // size + 1),
            range(low.y // size, (high.y - 1) // size + 1),
            range(low.z // size, (high.z - 1) // size + 1),
        )
