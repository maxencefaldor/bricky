# Copyright 2026 Maxence Faldor

from __future__ import annotations

import pytest

from bricky import ModelBuilder, Report, check_model, default_catalog, voxels
from bricky.catalog import Catalog, Connector, ConnectorKind, Part
from bricky.geometry import AXES, DOWN, ORIGIN, UP, Box, Convex, Vector
from bricky.units import PLATE, STUD

CATALOG = default_catalog()


def part(part_id: str) -> Part:
    found = CATALOG.part(part_id)
    assert found is not None
    return found


def studs(shape: Part) -> list[Connector]:
    return [c for c in shape.connectors if c.kind is ConnectorKind.STUD]


def anti_studs(shape: Part) -> list[Connector]:
    return [c for c in shape.connectors if c.kind is ConnectorKind.ANTI_STUD]


@pytest.mark.parametrize("p", CATALOG.parts, ids=lambda p: p.id)
def test_every_part_sits_in_its_box_with_connectors_on_its_faces(p: Part) -> None:
    assert Box.bounding(s.bounds for s in p.solids) == Box(ORIGIN, p.size)
    for c in anti_studs(p):
        assert (c.position.z, c.normal) == (0, DOWN)
        assert 0 < c.position.x < p.size.x
        assert 0 < c.position.y < p.size.y
    for c in studs(p):
        assert c.normal in AXES.values()
        if c.normal == UP:
            assert c.position.z == p.size.z
        else:  # a side stud: on a vertical face, half a stud below the top
            assert c.normal.z == 0
            assert c.position.z == p.size.z - STUD // 2
            face = {
                AXES["-x"]: 0,
                AXES["+x"]: p.size.x,
                AXES["-y"]: 0,
                AXES["+y"]: p.size.y,
            }
            assert (c.position.x if c.normal.x else c.position.y) == face[c.normal]


def test_a_slope_carries_studs_only_on_its_flat_top() -> None:
    slope = part("3039")  # Slope 45 2 x 2
    assert slope.size == Vector(2 * STUD, 2 * STUD, 3 * PLATE)
    assert sorted(c.position.as_tuple() for c in studs(slope)) == [
        (10, 30, 24),
        (30, 30, 24),
    ]
    assert len(anti_studs(slope)) == 4
    (body,) = slope.solids
    assert isinstance(body, Convex)
    assert body.contains(Vector(10, 5, 4))
    assert not body.contains(Vector(10, 5, 20))


def test_an_inverted_slope_grips_only_under_its_flat_back() -> None:
    slope = part("3660")  # Slope, Inverted 45 2 x 2
    assert len(studs(slope)) == 4
    assert sorted(c.position.as_tuple() for c in anti_studs(slope)) == [
        (10, 30, 0),
        (30, 30, 0),
    ]


def test_cheese_slopes_and_curved_slopes_have_no_studs() -> None:
    assert part("54200").stud_count == part("11477").stud_count == 0
    assert part("85984").footprint == (2, 1)


def test_round_parts_are_round_inside_their_square() -> None:
    brick = part("3062b")  # Brick, Round 1 x 1
    (body,) = brick.solids
    assert isinstance(body, Convex)
    assert len(body.faces) == 16 + 2
    assert body.contains(Vector(10, 10, 12))
    assert not body.contains(
        Vector(1, 1, 12)
    )  # a corner of the square is outside the circle


def test_side_studs_face_the_sides_they_name() -> None:
    brick = part("87087")  # Brick, Modified 1 x 1 with Stud on 1 Side
    side = [c for c in studs(brick) if c.normal != UP]
    assert [(c.position.as_tuple(), c.normal) for c in side] == [
        ((10, 0, 14), AXES["-y"])
    ]
    assert len([c for c in studs(part("4733")) if c.normal != UP]) == 4


def test_a_jumper_has_one_stud_half_a_stud_off_the_grid() -> None:
    jumper = part("15573")
    assert [c.position.as_tuple() for c in studs(jumper)] == [(10, 20, 8)]
    assert len(anti_studs(jumper)) == 3  # two on the grid, one in the middle


def test_an_arch_leaves_room_under_its_middle_but_not_its_edges() -> None:
    def plate_under_arch(y: float) -> Report:
        builder = ModelBuilder("arch")
        builder.place(
            "3659", at=(0, 0, 0), color="Tan"
        )  # Arch 1 x 4, opening from y 1 to 3
        builder.place("3024", at=(0, y, 0), color="Red")  # Plate 1 x 1
        return check_model(builder.build())

    assert not any(d.rule == "overlap" for d in plate_under_arch(1.5).diagnostics)
    assert any(d.rule == "overlap" for d in plate_under_arch(1).diagnostics)


def test_new_parts_build_together_without_errors() -> None:
    builder = ModelBuilder("mixed")
    builder.place("3001", at=(0, 0, 0), color="Red")
    builder.place("3039", at=(0, 0, 3), color="Red")  # a slope on a brick
    builder.place(
        "3004", at=(0, 1, 6), rotation="R90", color="White"
    )  # a brick on the slope's studs
    builder.place("15573", at=(4, 0, 0), color="Tan")  # a jumper
    builder.place(
        "3005", at=(4, 0.5, 1), color="Tan"
    )  # a brick half a stud off the grid
    builder.place(
        "87087", at=(7, 1, 0), color="Dark Bluish Gray"
    )  # a stud facing -y at y 1
    builder.place(
        "3070b", at=(7, 0.6, 0.5), rotation="+x+z", color="Yellow"
    )  # a tile gripping it
    report = check_model(builder.build())
    assert report.ok, [d.message for d in report.diagnostics]


def test_cells_of_a_slope_follow_its_face() -> None:
    builder = ModelBuilder("slope")
    builder.place("3040", at=(0, 0, 0), color="Red")  # Slope 45 2 x 1
    filled = voxels(builder.build())
    # The back stud's column is full; the front column only below the face z = y + 4.
    assert {(0, 1, z) for z in range(3)} <= set(filled)
    assert (0, 0, 0) in filled
    assert (0, 0, 2) not in filled


def test_short_and_tall_arches_build_and_stand_on_their_legs() -> None:
    for key, size, height, span in (("4490", (1, 3), 3, 1), ("2339", (1, 5), 12, 3)):
        shape = {"family": "arch", "size": size, "height": height, "span": span}
        arch = Catalog([{"id": key, "name": "Arch", "shape": shape}]).part(key)
        assert arch is not None
        assert len(anti_studs(arch)) == 2  # one under each leg
        assert arch.size.z == height * PLATE
