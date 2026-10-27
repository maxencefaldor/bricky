import tomllib

import pytest

from bricky.catalog import SAMPLE_CATALOG, CatalogPart, Family
from bricky.catalog.models import (
    ArchShape,
    BaseplateShape,
    BlockShape,
    CurvedSlopeShape,
    InvertedSlopeShape,
    JumperShape,
    RoundShape,
    SideStudsShape,
    SlopeShape,
)
from bricky.catalog.names import plates, shape_from_name

SHAPED = {
    "Brick 2 x 4": BlockShape(family=Family.BRICK, size=(2, 4)),
    "Brick 1 x 2 x 2 with Inside Stud Holder": BlockShape(
        family=Family.BRICK, size=(1, 2), height=6
    ),
    "Brick 1 x 1 x 1 2/3": BlockShape(family=Family.BRICK, size=(1, 1), height=5),
    "Brick 1 x 2 without Bottom Tube": BlockShape(family=Family.BRICK, size=(1, 2)),
    "Plate 1 x 2": BlockShape(family=Family.PLATE, size=(1, 2)),
    "Tile 1 x 1 with Groove": BlockShape(family=Family.TILE, size=(1, 1)),
    "Baseplate 32 x 32": BaseplateShape(family=Family.BASEPLATE, size=(32, 32)),
    "Slope 45 2 x 4": SlopeShape(family=Family.SLOPE, size=(4, 2), run=1),
    "Slope 33 3 x 2": SlopeShape(family=Family.SLOPE, size=(2, 3), run=2),
    "Slope 75 2 x 1 x 3": SlopeShape(family=Family.SLOPE, size=(1, 2), run=1, height=9),
    "Slope 30 1 x 1 x 2/3": SlopeShape(
        family=Family.SLOPE, size=(1, 1), run=1, height=2, studs=False
    ),
    "Slope, Inverted 45 2 x 2": InvertedSlopeShape(
        family=Family.INVERTED_SLOPE, size=(2, 2), run=1
    ),
    "Slope, Curved 2 x 1 x 2/3": CurvedSlopeShape(
        family=Family.CURVED_SLOPE, size=(1, 2), height=2
    ),
    "Brick, Round 1 x 1 Open Stud": RoundShape(family=Family.ROUND, size=(1, 1), height=3),
    "Plate, Round 2 x 2 with Axle Hole": RoundShape(family=Family.ROUND, size=(2, 2), height=1),
    "Tile, Round 1 x 1": RoundShape(family=Family.ROUND, size=(1, 1), height=1, studs=False),
    "Brick, Modified 1 x 1 with Stud on 1 Side": SideStudsShape(
        family=Family.SIDE_STUDS, size=(1, 1), sides=("-y",)
    ),
    "Brick, Modified 1 x 1 with Studs on 2 Sides, Adjacent": SideStudsShape(
        family=Family.SIDE_STUDS, size=(1, 1), sides=("-y", "+x")
    ),
    "Brick, Modified 1 x 4 with 4 Studs on 1 Side": SideStudsShape(
        family=Family.SIDE_STUDS, size=(4, 1), sides=("-y",)
    ),
    "Plate, Modified 1 x 2 with 1 Stud with Groove and Bottom Stud Holder (Jumper)": JumperShape(
        family=Family.JUMPER, size=(1, 2), center_anti_stud=True
    ),
    "Plate, Modified 2 x 2 with Groove and 1 Stud in Center (Jumper)": JumperShape(
        family=Family.JUMPER, size=(2, 2)
    ),
    "Arch 1 x 6 x 2": ArchShape(family=Family.ARCH, size=(1, 6), height=6, span=4),
    "Brick, Arch 1 x 4": ArchShape(family=Family.ARCH, size=(1, 4), height=3, span=2),
}

UNSHAPED = [
    "Slope 45 2 x 2 Double",  # a ridge, not a slope
    "Slope 45 2 x 1 with 2/3 Cutout",
    "Slope, Inverted 45 1 x 1",  # no flat row to grip studs below
    "Slope, Curved 3 x 1",  # curved slopes come in several heights; the name gives none
    "Brick 1 x 2 Log",
    "Brick 2 x 2 Corner",
    "Plate 1 x 2 with Door Rail",
    "Plate 1 x 2 x 2",  # plates have no height of their own
    "Plate, Round 4 x 4 with Hole",  # bigger round parts have studs set in
    "Plate, Round 1 x 2",
    "Tile 1 x 2 Grille with Bottom Groove",
    "Brick, Modified 1 x 2 with 1 Stud on 1 Side",  # one stud, not one per position
    "Brick, Modified 1 x 1 x 1 2/3 with Studs on 1 Side",
    "Brick, Modified 1 x 2 with Studs on 2 Sides, Adjacent",
    "Arch 1 x 6 x 2 Curved Top",
    "Arch 1 x 2",
    "Technic, Brick 1 x 2 with Hole",
    "Duplo, Brick 2 x 4",
    "Brick 1 x 2 x 1/2",
]


@pytest.mark.parametrize(("name", "shape"), SHAPED.items())
def test_names_that_follow_a_pattern_have_its_shape(name, shape):
    assert shape_from_name(name) == shape


@pytest.mark.parametrize("name", UNSHAPED)
def test_names_with_other_details_have_no_shape(name):
    assert shape_from_name(name) is None


def test_heights_in_bricks_become_plates():
    assert [plates(h, 3) for h in (None, "2", "2/3", "1 1/3", "1 2/3", "1/2")] == [
        3,
        6,
        2,
        4,
        5,
        None,
    ]


def test_extra_spaces_do_not_matter():
    assert shape_from_name("Brick  2 x 4 ") == SHAPED["Brick 2 x 4"]


def test_names_give_the_sample_shapes():
    """The sample was entered by hand; a name that has a shape gives the same one."""
    parts = tomllib.loads(SAMPLE_CATALOG.read_text())["parts"]
    entries = [CatalogPart.model_validate(part) for part in parts]
    named = {entry.id: shape_from_name(entry.name) for entry in entries}
    assert [entry.id for entry in entries if named[entry.id] is None] == ["50950"]
    assert all(named[e.id] == e.shape for e in entries if named[e.id] is not None)
