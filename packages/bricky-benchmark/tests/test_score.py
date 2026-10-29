# Copyright 2026 Maxence Faldor

from __future__ import annotations

from bricky import ModelBuilder, check_model, voxels
from bricky.analysis import Voxel, VoxelKey
from bricky_benchmark.score import compare, facts


def grid(*rows: str, z: int = 0) -> dict[VoxelKey, Voxel]:
    """Voxels from rows, north first: '.' is empty, any other character a color."""
    result = {}
    for row, line in enumerate(rows):
        y = len(rows) - 1 - row
        for x, char in enumerate(line):
            if char != ".":
                result[x, y, z] = Voxel(uid=f"{x},{y}", color=ord(char))
    return result


L_SHAPE = grid("A..", "A..", "ABB")


def test_identical_models_match_fully() -> None:
    fidelity = compare(L_SHAPE, L_SHAPE)
    assert (fidelity.shape, fidelity.color, fidelity.rotation) == (1.0, 1.0, "R0")
    assert fidelity.voxels == fidelity.reference_voxels == 5


def test_position_and_rotation_are_free() -> None:
    # The same L, rotated by 90 degrees and moved far away.
    rotated = {
        (x + 30, y - 7, z): c for (x, y, z), c in grid("BBA", "..A", "..A").items()
    }
    fidelity = compare(rotated, L_SHAPE)
    assert (fidelity.shape, fidelity.color) == (1.0, 1.0)
    assert fidelity.rotation != "R0"


def test_colors_count_separately_from_shape() -> None:
    recolored = grid("A..", "A..", "AAA")
    fidelity = compare(recolored, L_SHAPE)
    assert fidelity.shape == 1.0
    assert fidelity.color == 3 / 5


def test_partial_overlap_is_intersection_over_union() -> None:
    fidelity = compare(grid("A..", "A..", "A.."), L_SHAPE)
    assert fidelity.shape == 3 / 5


def test_layers_line_up_on_the_ground() -> None:
    lifted = {(x, y, z + 4): c for (x, y, z), c in L_SHAPE.items()}
    assert compare(lifted, L_SHAPE).shape == 1.0


def test_an_empty_model_scores_zero() -> None:
    fidelity = compare({}, L_SHAPE)
    assert (fidelity.shape, fidelity.color, fidelity.voxels) == (0.0, 0.0, 0)


def test_facts_count_diagnostics_by_rule() -> None:
    builder = ModelBuilder("floating")
    builder.place("3001", at=(0, 0, 3), color="Red")
    builder.place("3001", at=(5, 5, 3), color="Red")
    model = builder.build()
    score = facts(check_model(model), model.element_count())
    assert score.built
    assert (score.errors, score.elements, score.rules) == (
        2,
        2,
        {"floating-group": 2},
    )


def test_real_models_compare_through_voxels() -> None:
    builder = ModelBuilder("pair")
    builder.place("3001", at=(0, 0, 0), color="Red")
    builder.place("3001", at=(0, 0, 3), rotation="R90", color="White")
    reference = voxels(builder.build())
    assert len(reference) == 2 * (
        2 * 4 * 3
    )  # two bricks, 2 x 4 studs and 3 plates each
    fidelity = compare(reference, reference)
    assert fidelity.shape == fidelity.color == 1.0
