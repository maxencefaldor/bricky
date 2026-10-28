# Copyright 2026 Maxence Faldor

import shutil
from pathlib import Path

import pytest

from bricky import BrickyError
from bricky.catalog import Catalog, Family
from bricky.catalog.bricklink import read_downloads
from bricky.catalog.importing import import_catalog
from bricky.catalog.ldraw import Library, ldraw_parts, ldraw_shape

DATA = Path(__file__).parent / "data"
LIBRARY = Library(DATA / "ldraw")


def test_the_library_is_indexed_without_case_and_dated_by_its_newest_part() -> None:
    assert "3004" in LIBRARY
    assert "3004P01" in LIBRARY
    assert "3004s01" not in LIBRARY  # a part of a part, not a part
    assert LIBRARY.release == "release 2025-01"
    header = LIBRARY.header("990001")
    assert (header.description, header.category) == ("Sticker  2 x  2", "Sticker")
    with pytest.raises(BrickyError, match="holds no LDraw parts"):
        Library(DATA / "bricklink")


def test_a_brick_becomes_a_box_with_studs_on_top_and_anti_studs_below() -> None:
    shape = ldraw_shape(LIBRARY, "3004")
    assert shape.size == (40, 20, 24)  # LDraw's x stays x; its y, down, becomes z, up
    assert shape.boxes == ((0, 0, 0, 40, 20, 24),)  # the hollow underside is filled
    assert shape.studs == ((10, 10, 24, "+z"), (30, 10, 24, "+z"))
    assert shape.anti_studs == ((10, 10), (30, 10))
    assert shape.source == "LDraw 3004.dat"
    assert (
        ldraw_shape(LIBRARY, "3004old").boxes == shape.boxes
    )  # moved: follows the reference


def test_solid_undersides_have_no_anti_studs_and_openings_stay_open() -> None:
    baseplate = ldraw_shape(LIBRARY, "3867")
    assert (baseplate.size, len(baseplate.studs), baseplate.anti_studs) == (
        (40, 40, 4),
        4,
        (),
    )
    arch = ldraw_shape(LIBRARY, "4490")
    assert arch.anti_studs == ((10, 10), (50, 10))  # under the legs only
    assert arch.boxes == (
        (0, 0, 0, 20, 20, 24),
        (20, 0, 16, 60, 20, 24),
        (40, 0, 0, 60, 20, 16),
    )


def test_parts_that_cannot_be_converted_say_why() -> None:
    with pytest.raises(BrickyError, match="encloses no volume"):
        ldraw_shape(LIBRARY, "990001")
    with pytest.raises(
        BrickyError, match=r"no file missing\.dat, which 990002\.dat uses"
    ):
        ldraw_shape(LIBRARY, "990002")


def test_converted_shapes_build_parts_that_click_like_generated_ones() -> None:
    catalog = Catalog(
        [{"id": "3004", "name": "Brick 1 x 2", "shape": ldraw_shape(LIBRARY, "3004")}]
    )
    part = catalog.part("3004")
    assert part is not None
    assert part.family is Family.BOXES
    assert part.footprint == (2, 1)
    assert part.stud_count == 2
    assert part.note == "converted from LDraw 3004.dat, as it is oriented there"


def test_an_import_from_ldraw_alone_names_parts_as_ldraw_does() -> None:
    assert list(ldraw_parts(LIBRARY)) == [
        "3004",
        "3004p01",
        "3005",
        "3024",
        "3700",
        "3867",
        "4490",
        "990001",
        "990002",
    ]
    catalog_file, coverage = import_catalog(None, LIBRARY)
    parts = {part.id: part for part in catalog_file.parts}
    assert parts["3004"].name == "Brick 1 x 2"
    assert parts["3004p01"].base == "3004"
    assert parts["990001"].category == "Sticker"
    assert coverage.by_source == {"LDraw": 6, "printed": 1}
    assert coverage.ldraw_failures == {
        "encloses no volume": 1,
        "the LDraw library has no file missing.dat, which a part uses": 1,
    }
    assert coverage.colors == 40  # the sample's, until BrickLink's are imported


BRICKLINK_PARTS = [
    ("3004", "Brick 1 x 2"),
    ("3867", "Baseplate 16 x 16"),
    ("3700", "Technic, Brick 1 x 2 with Hole"),
    ("3700pb01", "Technic, Brick 1 x 2 with Hole with Logo Pattern"),
    ("4490", "Arch 1 x 3"),
]


def parts_download(parts: list[tuple[str, str]]) -> str:
    items = "".join(
        f"<ITEM><ITEMTYPE>P</ITEMTYPE><ITEMID>{key}</ITEMID><ITEMNAME>{name}</ITEMNAME>"
        "<CATEGORY>5</CATEGORY></ITEM>\n"
        for key, name in parts
    )
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<CATALOG>\n{items}</CATALOG>\n'


def test_an_import_from_both_shapes_by_name_then_by_ldraw_and_ldraw_wins_a_disagreement(
    tmp_path: Path,
) -> None:
    shutil.copy(DATA / "bricklink" / "Colors.xml", tmp_path / "Colors.xml")
    (tmp_path / "parts.xml").write_text(parts_download(BRICKLINK_PARTS))
    catalog_file, coverage = import_catalog(read_downloads(tmp_path), LIBRARY)
    parts = {part.id: part for part in catalog_file.parts}
    assert parts["3004"].shape is not None
    assert parts["3004"].shape.family is Family.BRICK  # its name's shape, exact, wins
    assert parts["3700"].shape is not None
    assert parts["3700"].shape.family is Family.BOXES
    assert parts["3700pb01"].base == "3700"
    assert coverage.by_source == {"name": 2, "LDraw": 2, "printed": 1}
    assert coverage.compared == 3
    assert coverage.disagreements == (
        (
            "3867 Baseplate 16 x 16 takes LDraw's shape: its name gives "
            "320 x 320 x 4 units, 256 studs, 0 anti-studs; "
            "LDraw gives 40 x 40 x 4 units, 4 studs, 0 anti-studs"
        ),
    )
    assert parts["3867"].shape is not None
    assert (
        parts["3867"].shape.family is Family.BOXES
    )  # LDraw's shape, where they disagree
    assert coverage.sources[1].startswith(
        "LDraw.org Parts Library, CC BY, release 2025-01, at "
    )


def test_a_part_whose_ldraw_shape_only_lacks_anti_studs_keeps_its_name_s_shape(
    tmp_path: Path,
) -> None:
    shutil.copy(DATA / "bricklink" / "Colors.xml", tmp_path / "Colors.xml")
    (tmp_path / "parts.xml").write_text(parts_download([("3005", "Brick 1 x 1")]))
    catalog_file, coverage = import_catalog(read_downloads(tmp_path), LIBRARY)
    (brick,) = catalog_file.parts
    assert brick.shape is not None
    assert (
        brick.shape.family is Family.BRICK
    )  # LDraw's solid underside finds no room for a stud
    assert coverage.disagreements == (
        (
            "3005 Brick 1 x 1 keeps its name's shape: its name gives "
            "20 x 20 x 24 units, 1 stud, 1 anti-stud; "
            "LDraw gives 20 x 20 x 24 units, 1 stud, 0 anti-studs"
        ),
    )
