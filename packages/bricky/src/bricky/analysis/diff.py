"""What changed between two builds of a model: elements added, removed and changed, and cells.

Elements are matched by what they are and the space they take, not by id: the same part in the
same colour, filling the same space with its connectors in the same places, is the same element.
Unnamed elements are numbered in the order a script places them, so inserting one part early
renumbers every later one, and matching by id would report them all as changed. Matching by space
also means that a symmetric part turned onto itself, such as a 2 x 2 brick turned a half turn in
place, has not changed.

Elements left over on both sides are then paired by id: an element whose id and part are the same
in both models, but whose place, rotation or colour differ, has changed. The rest were added or
removed.
"""

from collections import defaultdict
from dataclasses import dataclass

from bricky.analysis.cells import world_cells
from bricky.analysis.world import Placed, World
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
    """Uids of elements whose id and part are the same in both, now in another place, rotation
    or colour."""

    unchanged: int
    """Elements in both: the same part and colour, taking the same space."""

    filled: int
    """Cells filled now that were empty."""

    emptied: int
    """Cells empty now that were filled."""

    recoloured: int
    """Cells filled in both, in a different colour."""


def diff_worlds(before: World, after: World) -> WorldDiff:
    """Compare two placed models, element by element and cell by cell."""
    waiting: defaultdict[Key, list[Placed]] = defaultdict(list)
    for placed in before.placed:
        waiting[_key(placed)].append(placed)
    matched: set[str] = set()
    unmatched: list[Placed] = []
    for placed in after.placed:
        bucket = waiting.get(_key(placed))
        if bucket:
            matched.add(bucket.pop(0).uid)
        else:
            unmatched.append(placed)
    left = {p.uid: p for p in before.placed if p.uid not in matched}
    added: list[str] = []
    changed: list[str] = []
    for placed in unmatched:
        earlier = left.get(placed.uid)
        if earlier is not None and earlier.part.id == placed.part.id:
            changed.append(placed.uid)
            del left[placed.uid]
        else:
            added.append(placed.uid)
    old, new = world_cells(before), world_cells(after)
    return WorldDiff(
        added=tuple(added),
        removed=tuple(left),
        changed=tuple(changed),
        unchanged=len(matched),
        filled=sum(1 for key in new if key not in old),
        emptied=sum(1 for key in old if key not in new),
        recoloured=sum(
            1 for key, cell in new.items() if (was := old.get(key)) and was.color != cell.color
        ),
    )


def _key(placed: Placed) -> Key:
    """What an element is and the space it takes, whatever pose put it there."""
    shapes = frozenset(
        solid if isinstance(solid, Box) else frozenset(solid.vertices) for solid in placed.solids
    )
    return (placed.part.id, placed.color, shapes, frozenset(placed.connectors))
