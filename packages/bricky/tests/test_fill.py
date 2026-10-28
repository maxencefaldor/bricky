from hypothesis import given, settings
from hypothesis import strategies as st

from bricky import ModelBuilder, check_model, voxels
from bricky.fill import BRICKS, PLATES, plan_fill


def test_a_solid_course_takes_bricks_and_the_rest_takes_plates():
    block = {(x, y, z): "Red" for x in range(2) for y in range(4) for z in range(4)}
    parts = [(placement.part, placement.at) for placement in plan_fill(block)]
    assert parts == [(BRICKS[2, 4], (0, 0, 0)), (PLATES[2, 4], (0, 0, 3))]


def test_courses_alternate_their_direction_so_joints_stagger():
    wall = {(x, 0, z): "Red" for x in range(8) for z in range(6)}
    builder = ModelBuilder("wall")
    builder.fill(wall)
    model = builder.build()
    assert set(voxels(model)) == set(wall)
    assert check_model(model).ok


def test_an_overhang_takes_a_part_that_reaches_back_over_its_support():
    shelf = {(0, 0, z): "Tan" for z in range(3)} | {(x, 0, 3): "Tan" for x in range(3)}
    builder = ModelBuilder("shelf")
    ids = builder.fill(shelf, id="shelf")
    model = builder.build()
    assert ids == ["shelf.0.0.0", "shelf.0.0.3"]
    assert check_model(model).ok


def test_colors_are_never_mixed_within_a_part():
    stripes = {(x, 0, 0): "Red" if x < 2 else "Blue" for x in range(4)}
    builder = ModelBuilder("stripes")
    builder.fill(stripes)
    filled = voxels(builder.build())
    assert {key: voxel.color for key, voxel in filled.items()} == {
        (0, 0, 0): 5,
        (1, 0, 0): 5,
        (2, 0, 0): 7,
        (3, 0, 0): 7,
    }


columns = st.dictionaries(
    st.tuples(st.integers(0, 5), st.integers(0, 5)),
    st.tuples(st.integers(1, 9), st.sampled_from(["Red", "White"])),
    min_size=1,
    max_size=12,
)


@settings(deadline=None, max_examples=40)
@given(columns)
def test_columns_standing_on_the_ground_fill_exactly_and_hold_together(heights):
    shape = {(x, y, z): color for (x, y), (height, color) in heights.items() for z in range(height)}
    builder = ModelBuilder("columns")
    builder.fill(shape)
    model = builder.build()
    assert set(voxels(model)) == set(shape)
    report = check_model(model)
    assert report.ok, [diagnostic.message for diagnostic in report.diagnostics]
