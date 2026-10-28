"""What changed between two builds of a model: elements added, removed and changed, and voxels.

Elements are matched by what they are and the space they take, not by id: the same part in the
same color, filling the same space with its connectors in the same places, is the same element.
Unnamed elements are numbered in the order a script places them, so inserting one part early
renumbers every later one, and matching by id would report them all as changed. Matching by space
also means that a symmetric part rotated onto itself, such as a 2 x 2 brick rotated a half turn in
place, has not changed.

Elements left over on both sides are then paired by id: an element whose id and part are the same
in both models, but whose position, rotation or color differ, has changed. The rest were added or
removed.
"""

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
    """Uids of elements whose id and part are the same in both, now in another position,
    rotation or color."""

    unchanged: int
    """Elements in both: the same part and color, taking the same space."""

    filled: int
    """Voxels filled now that were empty."""

    emptied: int
    """Voxels empty now that were filled."""

    recolored: int
    """Voxels filled in both, in a different color."""


def diff_worlds(before: World, after: World) -> WorldDiff:
    """Compare two placed models, element by element and voxel by voxel."""
    waiting: defaultdict[Key, list[PlacedElement]] = defaultdict(list)
    for element in before.elements:
        waiting[_key(element)].append(element)
    matched: set[str] = set()
    unmatched: list[PlacedElement] = []
    for element in after.elements:
        same = waiting.get(_key(element))
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
            1 for key, voxel in new.items() if (was := old.get(key)) and was.color != voxel.color
        ),
    )


def _key(element: PlacedElement) -> Key:
    """What an element is and the space it takes, whatever pose put it there."""
    shapes = frozenset(
        solid if isinstance(solid, Box) else frozenset(solid.vertices) for solid in element.solids
    )
    return (element.part.id, element.color, shapes, frozenset(element.connectors))
