# Copyright 2026 Maxence Faldor

from hypothesis import given
from hypothesis import strategies as st

from bricky import ModelBuilder, default_catalog, voxels
from bricky.analysis import Context
from bricky.geometry import Box, Vector

PARTS = [
    "3001",
    "3004",
    "3024",
    "3022",
    "3020",
    "3070b",
    "3068b",
]  # bricks, plates, tiles


def test_a_brick_fills_its_footprint_three_plates_high():
    builder = ModelBuilder("one")
    builder.place("3001", at=(2, 3, 6), color="Red")  # Brick 2 x 4
    filled = voxels(builder.build())
    assert set(filled) == {
        (x, y, z) for x in (2, 3) for y in range(3, 7) for z in (6, 7, 8)
    }
    assert {voxel.uid for voxel in filled.values()} == {"e1"}
    assert {voxel.color for voxel in filled.values()} == {5}


def test_rotated_parts_fill_their_rotated_footprint():
    builder = ModelBuilder("rotated")
    builder.place(
        "3020", at=(0, 0, 0), rotation="R90", color="Blue"
    )  # Plate 2 x 4, along x
    assert set(voxels(builder.build())) == {
        (x, y, 0) for x in range(4) for y in range(2)
    }


def test_a_voxel_belongs_to_the_part_holding_its_center():
    builder = ModelBuilder("offset")
    builder.place("3024", at=(0.5, 0, 0), color="Red")  # Plate 1 x 1, half a stud east
    assert set(voxels(builder.build())) == {(0, 0, 0)}


def test_overlapping_parts_leave_a_voxel_to_the_first():
    builder = ModelBuilder("clash")
    builder.place("3005", at=(0, 0, 0), color="Red", id="first")
    builder.place("3005", at=(0, 0, 1), color="Blue", id="second")
    filled = voxels(builder.build())
    assert [filled[0, 0, z].uid for z in range(4)] == [
        "first",
        "first",
        "first",
        "second",
    ]


def test_studs_fill_no_voxel_and_the_context_agrees():
    builder = ModelBuilder("stack")
    builder.place("3022", at=(0, 0, 0), color="Red")
    builder.place("3022", at=(0, 0, 1), color="Red")
    model = builder.build()
    assert len(voxels(model)) == 2 * 2 * 2
    assert Context(model, default_catalog()).voxels == voxels(model)


placements = st.tuples(
    st.sampled_from(PARTS),
    st.integers(-10, 10),
    st.integers(-10, 10),
    st.integers(0, 12),
    st.sampled_from(["R0", "R90", "R180", "R270"]),
)


@given(
    st.lists(placements, min_size=1, max_size=6), st.integers(-5, 5), st.integers(-5, 5)
)
def test_moving_a_model_moves_its_voxels(parts, dx, dy):
    def model(shift_x: int, shift_y: int):
        builder = ModelBuilder("moved")
        for part, x, y, z, rotation in parts:
            builder.place(
                part, at=(x + shift_x, y + shift_y, z), rotation=rotation, color="Red"
            )
        return builder.build()

    before = voxels(model(0, 0))
    after = voxels(model(dx, dy))
    assert set(after) == {(x + dx, y + dy, z) for x, y, z in before}


@given(placements)
def test_a_grid_aligned_part_fills_its_volume(placement):
    part_id, x, y, z, rotation = placement
    builder = ModelBuilder("single")
    builder.place(part_id, at=(x, y, z), rotation=rotation, color="Red")
    part = default_catalog().part(part_id)
    assert part is not None
    body = Box(Vector(0, 0, 0), part.size)
    assert len(voxels(builder.build())) == body.volume // (20 * 20 * 8)
