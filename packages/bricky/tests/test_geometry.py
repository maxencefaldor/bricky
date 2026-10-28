import pytest
from hypothesis import given
from hypothesis import strategies as st

from bricky.geometry import (
    ALIASES,
    IDENTITY,
    ROTATIONS,
    Box,
    Convex,
    Pose,
    Rotation,
    Vector,
    overlaps,
)

coordinates = st.integers(min_value=-1000, max_value=1000)
vectors = st.builds(Vector, coordinates, coordinates, coordinates)
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
    assert r.x_axis.cross(r.y_axis) == r.z_axis
    assert r.x_axis.dot(r.y_axis) == 0


@given(rotations)
def test_names_round_trip(r):
    assert Rotation.parse(r.name) == r


def test_aliases_turn_counter_clockwise_seen_from_above():
    assert Rotation.parse("R90").apply(Vector(1, 0, 0)) == Vector(0, 1, 0)
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
    a = Box(Vector(0, 0, 0), Vector(20, 20, 24))
    b = Box(Vector(20, 0, 0), Vector(40, 20, 24))
    assert not a.overlaps(b)
    assert a.overlaps(Box(Vector(19, 0, 0), Vector(40, 20, 24)))


def test_bounding_needs_at_least_one_box():
    with pytest.raises(ValueError, match="empty"):
        Box.bounding([])


# Convex solids

sizes = st.builds(Vector, st.integers(1, 200), st.integers(1, 200), st.integers(1, 200))
solid_boxes = st.builds(lambda lo, size: Box(lo, lo + size), vectors, sizes)
SLOPE = Convex.prism([(0, 0), (40, 0), (40, 24), (20, 24), (0, 4)], "x", 0, 20)
"""Slope 45 2 x 1: its slanted face is the plane z = y + 4."""


@given(solid_boxes, solid_boxes)
def test_convex_boxes_overlap_exactly_like_boxes(a, b):
    assert overlaps(a.as_convex(), b.as_convex()) == a.overlaps(b)
    assert overlaps(a.as_convex(), b) == a.overlaps(b)


@given(solid_boxes, vectors)
def test_convex_boxes_contain_points_like_boxes(box, point):
    assert box.as_convex().contains(point) == box.contains(point)


@given(solid_boxes, rotations, vectors)
def test_turning_a_convex_box_turns_its_bounds(box, rotation, shift):
    pose = Pose(rotation, shift)
    assert box.as_convex().transformed(pose).bounds == box.transformed(pose)


@given(rotations, vectors, solid_boxes)
def test_overlap_tests_agree_both_ways_and_under_any_pose(rotation, shift, box):
    pose = Pose(rotation, shift)
    slope, other = SLOPE.transformed(pose), box.transformed(pose)
    assert overlaps(slope, other) == overlaps(other, slope) == overlaps(SLOPE, box)


def test_touching_a_slanted_face_is_not_overlapping():
    # A box whose lower front edge lies on the slope's face, at y = 10, z = 14.
    touching = Box(Vector(0, 0, 14), Vector(20, 10, 24))
    assert not overlaps(SLOPE, touching)
    assert overlaps(SLOPE, Box(Vector(0, 0, 13), Vector(20, 10, 24)))
    assert overlaps(SLOPE, Box(Vector(5, 30, 20), Vector(15, 35, 30)))  # the flat top at the back


def test_points_on_shared_faces_belong_to_one_side():
    assert SLOPE.contains(Vector(10, 5, 2))
    assert not SLOPE.contains(Vector(10, 5, 20))
    assert SLOPE.contains(Vector(0, 10, 10))  # on the low x face: inside
    assert not SLOPE.contains(Vector(20, 10, 10))  # on the high x face: outside


def test_convex_solids_must_be_convex_and_face_outward():
    box = Box(Vector(0, 0, 0), Vector(10, 10, 10))
    with pytest.raises(ValueError, match="faces inward"):
        Convex(box.corners(), tuple(tuple(reversed(face)) for face in box.as_convex().faces))
    with pytest.raises(ValueError, match="faces inward"):
        Convex.prism([(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)], "z", 0, 5)  # an L
    with pytest.raises(ValueError, match="not flat"):
        Convex(
            (*box.corners()[:7], Vector(10, 10, 11)),
            box.as_convex().faces,
        )
