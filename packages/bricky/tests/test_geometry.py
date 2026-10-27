import pytest
from hypothesis import given
from hypothesis import strategies as st

from bricky.geometry import ALIASES, IDENTITY, ROTATIONS, Box, Pose, Rotation, Vec3

coordinates = st.integers(min_value=-1000, max_value=1000)
vectors = st.builds(Vec3, coordinates, coordinates, coordinates)
rotations = st.sampled_from(ROTATIONS)
boxes = st.builds(Box.spanning, vectors, vectors)


def test_there_are_24_distinct_rotations():
    assert len(set(ROTATIONS)) == 24
    assert IDENTITY in ROTATIONS


@given(rotations, rotations)
def test_rotations_are_closed_under_composition(a, b):
    assert a @ b in ROTATIONS


@given(rotations, rotations, vectors)
def test_composition_applies_right_to_left(a, b, v):
    assert (a @ b).apply(v) == a.apply(b.apply(v))


@given(rotations, vectors)
def test_inverse_undoes_a_rotation(r, v):
    assert r.inverse().apply(r.apply(v)) == v
    assert r @ r.inverse() == IDENTITY


@given(rotations)
def test_rotations_are_proper(r):
    assert r.ex.cross(r.ey) == r.ez
    assert r.ex.dot(r.ey) == 0


@given(rotations)
def test_names_round_trip(r):
    assert Rotation.parse(r.name) == r


def test_aliases_turn_counter_clockwise_seen_from_above():
    assert Rotation.parse("R90").apply(Vec3(1, 0, 0)) == Vec3(0, 1, 0)
    assert Rotation.parse("r180") == Rotation.parse(ALIASES["R180"])
    assert Rotation.parse("R270") @ Rotation.parse("R90") == IDENTITY


@pytest.mark.parametrize("text", ["", "+x", "+x+x", "+x-x", "R45", "up"])
def test_bad_rotation_names_are_rejected(text):
    with pytest.raises(ValueError, match="unknown rotation"):
        Rotation.parse(text)


@given(boxes, rotations, vectors)
def test_poses_keep_box_volume(box, r, offset):
    assert box.transformed(Pose(r, offset)).volume == box.volume


@given(rotations, vectors, rotations, vectors, vectors)
def test_pose_composition(r1, t1, r2, t2, p):
    outer, inner = Pose(r1, t1), Pose(r2, t2)
    assert (outer @ inner).apply(p) == outer.apply(inner.apply(p))


@given(boxes, boxes)
def test_overlap_is_symmetric_and_matches_intersection(a, b):
    assert a.overlaps(b) == b.overlaps(a)
    assert (a.intersection(b) is not None) == a.overlaps(b)


def test_touching_boxes_do_not_overlap():
    a = Box(Vec3(0, 0, 0), Vec3(20, 20, 24))
    b = Box(Vec3(20, 0, 0), Vec3(40, 20, 24))
    assert not a.overlaps(b)
    assert a.overlaps(Box(Vec3(19, 0, 0), Vec3(40, 20, 24)))


def test_bounding_needs_at_least_one_box():
    with pytest.raises(ValueError, match="empty"):
        Box.bounding([])
