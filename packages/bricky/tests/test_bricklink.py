import shutil
from pathlib import Path

import pytest

from bricky import BrickyError
from bricky.catalog import Catalog, ColorType
from bricky.catalog.bricklink import color_type, import_catalog, read_downloads

DOWNLOADS = Path(__file__).parent / "data" / "bricklink"


def test_downloads_are_recognized_by_what_they_hold():
    downloads = read_downloads(DOWNLOADS)
    assert {kind: path.name for kind, path in downloads.files.items()} == {
        "categories": "categories.xml",
        "codes": "codes.xml",
        "colors": "Colors.xml",
        "parts": "Catalog Items - Parts.xml",
    }
    assert [part.id for part in downloads.parts][:3] == ["3001", "3001pb001", "3068b"]
    assert downloads.parts[2].alternates == ("3068",)
    assert downloads.categories[5] == "Brick"
    assert len(downloads.codes) == 7


def test_an_import_keeps_every_part_and_shapes_what_it_can():
    catalog_file, coverage = import_catalog(read_downloads(DOWNLOADS))
    parts = {part.id: part for part in catalog_file.parts}
    assert list(parts) == [
        "3001",
        "3001pb001",
        "3068b",
        "3068bpb0001",
        "3068bpx1",
        "3039",
        "3044c",
        "3700",
        "973pb0001c01",
    ]
    assert parts["3001"].colors == (1, 5)
    assert parts["3001"].category == "Brick"
    assert parts["3068b"].colors == (12, 86)
    assert parts["3068bpb0001"].name == "Tile 2 x 2 with Groove with Red Heart Pattern"
    assert parts["3068bpb0001"].base == "3068b"
    assert parts["3068bpx1"].base is None  # its name is not the base part's
    assert parts["3044c"].shape is None
    assert (coverage.parts, coverage.shaped, coverage.printed) == (9, 5, 2)
    assert coverage.by_family == {"brick": 2, "tile": 2, "slope": 1}
    assert coverage.unshaped_by_category == {
        "Tile, Decorated": 1,
        "Slope": 1,
        "Technic, Brick": 1,
        "Minifigure, Torso Assembly": 1,
    }
    assert catalog_file.source.startswith("BrickLink catalog downloads of ")


def test_colors_come_with_their_bricklink_types():
    catalog_file, coverage = import_catalog(read_downloads(DOWNLOADS))
    colors = {color.id: color for color in catalog_file.colors}
    assert list(colors) == [1, 5, 12, 86, 101, 115]
    assert colors[5].rgb == "#C91A09"
    assert colors[12].type is ColorType.TRANSPARENT
    assert colors[101].type is ColorType.TRANSPARENT  # "Glitter", but see-through
    assert colors[115].type is ColorType.PEARL
    assert coverage.skipped_colors == ("Mystery Color (240): no RGB value",)
    assert color_type("Speckle", "Speckle Black-Silver") is ColorType.SPECKLE
    assert color_type("", "Black") is ColorType.SOLID


def test_an_imported_catalog_builds_and_searches(tmp_path):
    catalog_file, _ = import_catalog(read_downloads(DOWNLOADS))
    path = tmp_path / "catalog.json"
    path.write_bytes(catalog_file.dump())
    again, _ = import_catalog(read_downloads(DOWNLOADS))
    assert again.dump() == path.read_bytes()
    catalog = Catalog.from_data(__import__("json").loads(path.read_text()))
    assert catalog.part("3068bpb0001") is not None
    assert catalog.part("3700") is None
    assert [p.id for p in catalog.search("tile 2x2")] == ["3068b", "3068bpb0001"]
    assert [p.id for p in catalog.search("3068")] == ["3068b", "3068bpb0001"]


def test_missing_and_broken_downloads_are_reported(tmp_path):
    with pytest.raises(BrickyError, match="no such folder"):
        read_downloads(tmp_path / "nowhere")
    with pytest.raises(BrickyError, match=r"no BrickLink Colors and Catalog Items \(Parts\)"):
        read_downloads(tmp_path)
    shutil.copy(DOWNLOADS / "Colors.xml", tmp_path / "a.xml")
    shutil.copy(DOWNLOADS / "Colors.xml", tmp_path / "b.xml")
    with pytest.raises(BrickyError, match="both BrickLink colors downloads"):
        read_downloads(tmp_path)
    (tmp_path / "b.xml").write_text("<CATALOG><ITEM>")
    with pytest.raises(BrickyError, match=r"b\.xml is not valid XML"):
        read_downloads(tmp_path)


def test_downloads_in_windows_encoding_are_read(tmp_path):
    for name in ("Colors.xml", "Catalog Items - Parts.xml"):
        shutil.copy(DOWNLOADS / name, tmp_path / name)
    parts = (tmp_path / "Catalog Items - Parts.xml").read_text()
    accented = parts.replace("Torso Space Pattern", "Torso Café Pattern")
    (tmp_path / "Catalog Items - Parts.xml").write_bytes(accented.encode("cp1252"))
    downloads = read_downloads(tmp_path)
    assert downloads.parts[-1].name.startswith("Torso Café Pattern")
    assert downloads.codes == ()
    assert downloads.categories == {}
