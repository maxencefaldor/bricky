# Copyright 2026 Maxence Faldor
"""What changed between two builds: elements added, removed and changed, and voxels.

The diff matches elements by what they are and the space they take: the same part in the
same color, filling the same space with its connectors in the same places, is the same
element. The builder numbers unnamed elements in the order a script places them, so one
part inserted early renumbers every later one, and a match by id would report them all
as changed. A match by space also counts a symmetric part rotated onto itself, such as a
2 x 2 brick rotated 180° in place, as unchanged.

The diff then pairs the elements left over on both sides by id. An element with the same
id and part in both models, but another position, rotation or color, has changed. The
remaining elements were added or removed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from bricky.analysis.voxels import world_voxels
from bricky.analysis.world import PlacedElement, World
from bricky.catalog import Connector
from bricky.geometry import Box, Vector

type Key = tuple[str, int, frozenset[Box | frozenset[Vector]], frozenset[Connector]]


@dataclass(frozen=True, slots=True)
class WorldDiff:
    """The difference between an earlier and a later version of a model."""

    added: tuple[str, ...]
    """Uids, in the later model, of elements the earlier one did not have."""

    removed: tuple[str, ...]
    """Uids, in the earlier model, of elements the later one no longer has."""

    changed: tuple[str, ...]
    """Uids of elements with the same id and part in both, but another pose or color."""

    unchanged: int
    """The number of elements with the same part, color and space in both models."""

    filled: int
    """The number of voxels empty before and filled after."""

    emptied: int
    """The number of voxels filled before and empty after."""

    recolored: int
    """The number of voxels filled in both models, in another color after."""


def diff_worlds(before: World, after: World) -> WorldDiff:
    """Compare two placed models, element by element and voxel by voxel."""
    waiting: defaultdict[Key, list[PlacedElement]] = defaultdict(list)
    for element in before.elements:
        waiting[_key(element)].append(element)
    matched: set[str] = set()
    unmatched: list[PlacedElement] = []
    for element in after.elements:
        same = waiting.get(_key(element), [])
        if same:
            matched.add(same.pop(0).uid)
        else:
            unmatched.append(element)
    left = {e.uid: e for e in before.elements if e.uid not in matched}
    added: list[str] = []
    changed: list[str] = []
    for element in unmatched:
        earlier = left.get(element.uid)
        if earlier is not None and earlier.part.id == element.part.id:
            changed.append(element.uid)
            del left[element.uid]
        else:
            added.append(element.uid)
    old, new = world_voxels(before), world_voxels(after)
    return WorldDiff(
        added=tuple(added),
        removed=tuple(left),
        changed=tuple(changed),
        unchanged=len(matched),
        filled=sum(1 for key in new if key not in old),
        emptied=sum(1 for key in old if key not in new),
        recolored=sum(
            1
            for key, voxel in new.items()
            if (was := old.get(key)) and was.color != voxel.color
        ),
    )


def _key(element: PlacedElement) -> Key:
    """Return what an element is and the space it takes, whatever pose put it there."""
    shapes = frozenset(
        solid if isinstance(solid, Box) else frozenset(solid.vertices)
        for solid in element.solids
    )
    return (element.part.id, element.color, shapes, frozenset(element.connectors))
