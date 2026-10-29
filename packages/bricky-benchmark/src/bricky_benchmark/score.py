# Copyright 2026 Maxence Faldor
"""Scores: the facts of an agent's final model, and how closely it matches a reference.

A score has two parts. The facts come from building the agent's final script with
bricky: whether the script builds, how many elements the model has, and its errors and
warnings. Fidelity, for projects with a reference, compares the voxels the two models
fill (see :func:`bricky.voxels`). Position is free: the comparison rotates the agent's
model about the vertical axis and shifts it to line up with the reference, and the best
match counts.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from typing import Final

from pydantic import BaseModel, Field

from bricky.analysis import Voxel, VoxelKey
from bricky.diagnostics import Report

type Rotate = Callable[[int, int], tuple[int, int]]

ROTATIONS: Final[dict[str, Rotate]] = {
    "R0": lambda x, y: (x, y),
    "R90": lambda x, y: (-y, x),
    "R180": lambda x, y: (-x, -y),
    "R270": lambda x, y: (y, -x),
}
"""The four rotations about the vertical axis, counterclockwise seen from above."""


class Fidelity(BaseModel):
    """How closely a model's voxels match a reference's."""

    shape: float = Field(
        description=(
            "Voxels filled in both models over voxels filled in either: 1 is identical."
        )
    )
    color: float = Field(
        description=(
            "Like shape, but a voxel filled in both counts only when the colors match."
        )
    )
    rotation: str = Field(
        description="The rotation of the agent's model that matched best."
    )
    shift: tuple[int, int, int] = Field(
        description="The shift, in studs and plates, that lined the rotated model up."
    )
    voxels: int = Field(description="Voxels the agent's model fills.")
    reference_voxels: int = Field(description="Voxels the reference fills.")


class Score(BaseModel):
    """What is true of an agent's final model."""

    built: bool = Field(description="Whether the final script built a model.")
    failure: str | None = Field(
        default=None,
        description="Why the final script built no model; null when it built one.",
    )
    elements: int = 0
    errors: int = 0
    warnings: int = 0
    codes: dict[str, int] = Field(
        default_factory=dict, description="Diagnostics by code, such as {'E301': 2}."
    )
    fidelity: Fidelity | None = Field(
        default=None,
        description="Match against the reference, for projects that have one.",
    )


def facts(report: Report, elements: int) -> Score:
    """Score a model that built, from its check report."""
    codes = Counter(diagnostic.code for diagnostic in report.diagnostics)
    return Score(
        built=True,
        elements=elements,
        errors=report.errors,
        warnings=report.warnings,
        codes=dict(sorted(codes.items())),
    )


def compare(
    model: Mapping[VoxelKey, Voxel], reference: Mapping[VoxelKey, Voxel]
) -> Fidelity:
    """Match a model's voxels to a reference's, over each rotation and three alignments.

    For each rotation, the comparison shifts the rotated model so its bounding box's low
    corner, high corner or center meets the reference's; layers always line up by the
    low corner. The candidate with the most voxels filled in both models wins, and the
    most voxels filled in the same color in both breaks ties.
    """
    ours = {key: voxel.color for key, voxel in model.items()}
    theirs = {key: voxel.color for key, voxel in reference.items()}
    if not ours or not theirs:
        return Fidelity(
            shape=0.0,
            color=0.0,
            rotation="R0",
            shift=(0, 0, 0),
            voxels=len(ours),
            reference_voxels=len(theirs),
        )

    def candidates() -> Iterator[tuple[int, int, str, tuple[int, int, int]]]:
        for name, rotate in ROTATIONS.items():
            rotated = {(*rotate(x, y), z): color for (x, y, z), color in ours.items()}
            for shift in sorted(_shifts(rotated, theirs)):
                shared, matched = _overlap(rotated, theirs, shift)
                yield matched, shared, name, shift

    matched, shared, name, shift = max(
        candidates(), key=lambda candidate: (candidate[1], candidate[0])
    )
    union = len(ours) + len(theirs) - shared
    return Fidelity(
        shape=shared / union,
        color=matched / union,
        rotation=name,
        shift=shift,
        voxels=len(ours),
        reference_voxels=len(theirs),
    )


def _bounds(
    voxels: Mapping[VoxelKey, int],
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    xs = [x for x, _, _ in voxels]
    ys = [y for _, y, _ in voxels]
    zs = [z for _, _, z in voxels]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _shifts(
    rotated: Mapping[VoxelKey, int], reference: Mapping[VoxelKey, int]
) -> set[tuple[int, int, int]]:
    """The shifts that line up the two models' low corners, high corners or centers."""
    (low, high), (reference_low, reference_high) = _bounds(rotated), _bounds(reference)
    by_low = tuple(
        theirs - ours for theirs, ours in zip(reference_low, low, strict=True)
    )
    by_high = tuple(
        theirs - ours for theirs, ours in zip(reference_high, high, strict=True)
    )
    by_center = tuple(
        (their_low + their_high) // 2 - (our_low + our_high) // 2
        for their_low, their_high, our_low, our_high in zip(
            reference_low, reference_high, low, high, strict=True
        )
    )
    # The ground stays the ground: layers line up by the low corner.
    return {(shift[0], shift[1], by_low[2]) for shift in (by_low, by_high, by_center)}


def _overlap(
    rotated: Mapping[VoxelKey, int],
    reference: Mapping[VoxelKey, int],
    shift: tuple[int, int, int],
) -> tuple[int, int]:
    """Count shifted voxels the reference also fills, and those in the same color."""
    shift_x, shift_y, shift_z = shift
    shared = matched = 0
    for (x, y, z), color in rotated.items():
        other = reference.get((x + shift_x, y + shift_y, z + shift_z))
        if other is not None:
            shared += 1
            matched += other == color
    return shared, matched
