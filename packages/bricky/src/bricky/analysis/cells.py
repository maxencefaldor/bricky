"""The model as cells: which part fills each stud x stud x plate cell, and in which colour.

A cell is one stud wide, one stud deep and one plate tall, the grid agents place parts on. A part
fills a cell when the cell's centre lies inside the part's body, so every cell belongs to at most
one part of a model whose parts do not overlap, and comparing a model with a target made of cells
is exact. Studs are not part of a body and fill no cell.
"""

from dataclasses import dataclass
from typing import Final

from bricky.analysis.world import World, build_world
from bricky.catalog import Catalog, default_catalog
from bricky.geometry import Box, Vec3
from bricky.model import Model
from bricky.units import PLATE, STUD

type CellKey = tuple[int, int, int]
"""A cell by its minimum corner: x and y in studs, z in plates."""


@dataclass(frozen=True, slots=True)
class Cell:
    """A filled cell: the element whose body fills it, and that element's colour."""

    uid: str
    """The element's uid, such as ``"bay2/e3"``."""

    color: int
    """BrickLink colour id."""


_HALF_STUD: Final = STUD // 2
_HALF_PLATE: Final = PLATE // 2


def world_cells(world: World) -> dict[CellKey, Cell]:
    """Return every filled cell of a placed model, keyed by its minimum corner.

    Where overlapping parts both fill a cell, the cell belongs to the one placed first.
    """
    cells: dict[CellKey, Cell] = {}
    for placed in world.placed:
        cell = Cell(placed.uid, placed.color)
        for solid in placed.solids:
            for key in _candidates(solid):
                if key not in cells and solid.contains(_centre(key)):
                    cells[key] = cell
    return cells


def model_cells(model: Model, catalog: Catalog | None = None) -> dict[CellKey, Cell]:
    """Return every filled cell of a model, keyed by its minimum corner in studs and plates.

    Example:
        >>> from bricky import ModelBuilder, cells
        >>> builder = ModelBuilder("wall")
        >>> builder.place("3004", at=(0, 0, 0), color="Red")  # Brick 1 x 2
        'e1'
        >>> sorted(cells(builder.build()))
        [(0, 0, 0), (0, 0, 1), (0, 0, 2), (0, 1, 0), (0, 1, 1), (0, 1, 2)]
    """
    return world_cells(build_world(model, catalog or default_catalog()))


def _candidates(solid: Box) -> list[CellKey]:
    lo, hi = solid.lo, solid.hi
    return [
        (x, y, z)
        for x in range(lo.x // STUD, -(-hi.x // STUD))
        for y in range(lo.y // STUD, -(-hi.y // STUD))
        for z in range(lo.z // PLATE, -(-hi.z // PLATE))
    ]


def _centre(key: CellKey) -> Vec3:
    x, y, z = key
    return Vec3(x * STUD + _HALF_STUD, y * STUD + _HALF_STUD, z * PLATE + _HALF_PLATE)
