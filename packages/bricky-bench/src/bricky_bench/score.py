"""Scores: what is true of the model an agent ends with, and how closely it matches a reference.

A score has two parts. The facts come from building the agent's final script with bricky: whether
it builds, how many elements it has, and its errors and warnings. Fidelity, for projects with a
reference, compares the cells the two models fill (see :func:`bricky.cells`). Position is free:
the agent's model is turned about the vertical axis and shifted to line up with the reference,
and the best match counts.
"""

from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from typing import Final

from pydantic import BaseModel, Field

from bricky.analysis import Cell, CellKey
from bricky.diagnostics import Report

type Turn = Callable[[int, int], tuple[int, int]]

TURNS: Final[dict[str, Turn]] = {
    "R0": lambda x, y: (x, y),
    "R90": lambda x, y: (-y, x),
    "R180": lambda x, y: (-x, -y),
    "R270": lambda x, y: (y, -x),
}
"""The four turns about the vertical axis, counter-clockwise seen from above."""


class Fidelity(BaseModel):
    """How closely a model's cells match a reference's."""

    shape: float = Field(
        description="Cells filled in both models over cells filled in either: 1 is identical."
    )
    color: float = Field(
        description="Like shape, but a cell filled in both counts only when the colours match."
    )
    turn: str = Field(description="The turn of the agent's model that matched best.")
    shift: tuple[int, int, int] = Field(
        description="The shift, in studs and plates, that lined the turned model up."
    )
    cells: int = Field(description="Cells the agent's model fills.")
    reference_cells: int = Field(description="Cells the reference fills.")


class Score(BaseModel):
    """What is true of an agent's final model."""

    built: bool = Field(description="Whether the final script built a model.")
    failure: str | None = Field(default=None, description="Why it did not, if it did not.")
    elements: int = 0
    errors: int = 0
    warnings: int = 0
    codes: dict[str, int] = Field(
        default_factory=dict, description="Diagnostics by code, such as {'E301': 2}."
    )
    fidelity: Fidelity | None = Field(
        default=None, description="Match against the reference, for projects that have one."
    )


def facts(report: Report, elements: int) -> Score:
    """Score a model that built, from its check report."""
    codes = Counter(d.code for d in report.diagnostics)
    return Score(
        built=True,
        elements=elements,
        errors=report.errors,
        warnings=report.warnings,
        codes=dict(sorted(codes.items())),
    )


def compare(model: Mapping[CellKey, Cell], reference: Mapping[CellKey, Cell]) -> Fidelity:
    """Match a model's cells against a reference's, over every turn and three ways to line up.

    For each turn, the turned model is shifted so its bounding box's low corner, high corner or
    centre meets the reference's, and the shift that matches most cells wins. Colour breaks ties.
    """
    ours = {key: cell.color for key, cell in model.items()}
    theirs = {key: cell.color for key, cell in reference.items()}
    if not ours or not theirs:
        return Fidelity(
            shape=0.0,
            color=0.0,
            turn="R0",
            shift=(0, 0, 0),
            cells=len(ours),
            reference_cells=len(theirs),
        )

    def candidates() -> Iterator[tuple[int, int, str, tuple[int, int, int]]]:
        for name, turn in TURNS.items():
            turned = {(*turn(x, y), z): color for (x, y, z), color in ours.items()}
            for shift in sorted(_shifts(turned, theirs)):
                shared, matched = _overlap(turned, theirs, shift)
                yield matched, shared, name, shift

    matched, shared, name, shift = max(candidates(), key=lambda c: (c[0], c[1]))
    union = len(ours) + len(theirs) - shared
    return Fidelity(
        shape=shared / union,
        color=matched / union,
        turn=name,
        shift=shift,
        cells=len(ours),
        reference_cells=len(theirs),
    )


def _bounds(cells: Mapping[CellKey, int]) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    xs, ys, zs = zip(*cells, strict=True)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _shifts(
    turned: Mapping[CellKey, int], reference: Mapping[CellKey, int]
) -> set[tuple[int, int, int]]:
    (lo, hi), (rlo, rhi) = _bounds(turned), _bounds(reference)
    low = tuple(r - o for r, o in zip(rlo, lo, strict=True))
    high = tuple(r - o for r, o in zip(rhi, hi, strict=True))
    centre = tuple(
        (r0 + r1) // 2 - (o0 + o1) // 2 for r0, r1, o0, o1 in zip(rlo, rhi, lo, hi, strict=True)
    )
    # The ground stays the ground: line levels up by the low corner.
    return {(s[0], s[1], low[2]) for s in (low, high, centre)}


def _overlap(
    turned: Mapping[CellKey, int],
    reference: Mapping[CellKey, int],
    shift: tuple[int, int, int],
) -> tuple[int, int]:
    dx, dy, dz = shift
    shared = matched = 0
    for (x, y, z), color in turned.items():
        other = reference.get((x + dx, y + dy, z + dz))
        if other is not None:
            shared += 1
            matched += other == color
    return shared, matched
