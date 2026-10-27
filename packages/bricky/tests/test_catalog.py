import re

import pytest

from bricky import BrickyError, Element, Model, ModelBuilder, check_model
from bricky.catalog import (
    SAMPLE_CATALOG,
    Catalog,
    CatalogFile,
    CatalogPart,
    Color,
    ColorType,
    ConnectorKind,
    Family,
    catalog_path,
    default_catalog,
    load_catalog,
)
from bricky.catalog.models import BlockShape
from bricky.geometry import DOWN, UP, Vec3
from bricky.settings import Settings
from bricky.units import BRICK, PLATE, STUD


def test_the_sample_catalog_is_used_here_and_covers_every_family():
    assert catalog_path() == SAMPLE_CATALOG
    catalog = default_catalog()
    assert len(catalog.parts) > 100
    assert {part.family for part in catalog.parts} == set(Family)
    assert catalog.source == "sample, entered by hand"


def test_brick_geometry():
    brick = default_catalog().part("3001")
    assert brick is not None
    assert brick.name == "Brick 2 x 4"
    assert brick.category == "Brick"
    assert brick.size == Vec3(2 * STUD, 4 * STUD, BRICK)
    assert brick.footprint == (2, 4)
    studs = [c for c in brick.connectors if c.kind is ConnectorKind.STUD]
    anti_studs = [c for c in brick.connectors if c.kind is ConnectorKind.ANTI_STUD]
    assert len(studs) == len(anti_studs) == 8
    assert all(c.normal == UP and c.pos.z == BRICK for c in studs)
    assert all(c.normal == DOWN and c.pos.z == 0 for c in anti_studs)


def test_tiles_have_anti_studs_but_no_studs():
    tile = default_catalog().part("3068b")
    assert tile is not None
    assert tile.size.z == PLATE
    assert tile.stud_count == 0
    assert len(tile.connectors) == 4


def test_colors_resolve_by_name_or_id():
    catalog = default_catalog()
    assert catalog.resolve_color("light bluish gray").id == 86
    assert catalog.resolve_color(5).name == "Red"
    assert catalog.resolve_color("11").name == "Black"
    with pytest.raises(ValueError, match="unknown color"):
        catalog.resolve_color("Chartreuse Sparkle")


def test_every_color_has_a_display_color_and_a_unique_id_and_name():
    colors = default_catalog().colors
    assert all(re.fullmatch(r"#[0-9A-F]{6}", c.rgb) for c in colors)
    assert len({c.id for c in colors}) == len(colors)
    assert len({c.name.casefold() for c in colors}) == len(colors)
    transparent = {c.name for c in colors if c.type is ColorType.TRANSPARENT}
    assert transparent == {c.name for c in colors if c.name.startswith("Trans-")}


def test_color_search_matches_ids_names_and_types():
    catalog = default_catalog()
    assert [c.id for c in catalog.search_colors("pearl gold")] == [115]
    assert {c.name for c in catalog.search_colors("bluish")} == {
        "Light Bluish Gray",
        "Dark Bluish Gray",
    }
    assert all(c.type is ColorType.TRANSPARENT for c in catalog.search_colors("transparent"))


def test_search_matches_every_word_and_both_size_spellings():
    catalog = default_catalog()
    assert [p.id for p in catalog.search("brick 2x4")] == ["3001", "30145"]
    assert [p.id for p in catalog.search("brick 2 x 4")] == ["3001", "30145"]
    families = {shape.family for p in catalog.search("plate 2x2") if (shape := catalog.shape(p.id))}
    assert families == {
        Family.PLATE,
        Family.ROUND,
        Family.JUMPER,
    }
    assert [p.id for p in catalog.search("slope 45 2x2")] == ["3039", "3660"]
    assert [p.name for p in catalog.search("round 1x1")] == [  # plainer names first
        "Tile, Round 1 x 1",
        "Brick, Round 1 x 1 Open Stud",
        "Plate, Round 1 x 1 Straight Side",
    ]


def test_find_by_family_and_footprint_in_either_order():
    catalog = default_catalog()
    assert [p.id for p in catalog.find(family=Family.PLATE, size=(6, 1))] == ["3666"]
    assert [p.id for p in catalog.find(family=Family.BRICK, size=(2, 2))] == ["3003"]
    assert [p.id for p in catalog.find(family=Family.SLOPE, size=(2, 2))] == [
        "3039",
        "3678b",
        "3684",
    ]
    assert {p.footprint for p in catalog.find(family=Family.TILE)} >= {(1, 1), (2, 2)}
    assert catalog.find(family=Family.PLATE, size=(5, 1)) == []


BRICK_2X4 = {"id": "3001", "name": "Brick 2 x 4", "shape": {"family": "brick", "size": [2, 4]}}
PRINTED = {"id": "3001pb001", "name": "Brick 2 x 4 with Pattern", "base": "3001"}
TECHNIC = {"id": "3700", "name": "Technic, Brick 1 x 2 with Hole", "category": "Technic"}


def catalog_of(*parts: dict) -> Catalog:
    red = {"id": 5, "name": "Red", "rgb": "#C91A09"}
    return Catalog.from_data({"format": "bricky.catalog/1", "parts": list(parts), "colors": [red]})


def test_parts_without_a_shape_are_known_but_cannot_be_built():
    catalog = catalog_of(BRICK_2X4, TECHNIC)
    assert catalog.entry("3700") == CatalogPart.model_validate(TECHNIC)
    assert catalog.part("3700") is None
    assert catalog.entry("nope") is None
    assert [p.id for p in catalog.search("brick")] == ["3001"]
    assert [p.id for p in catalog.search("brick", shapeless=True)] == ["3001", "3700"]
    assert [p.id for p in catalog.search("technic", shapeless=True)] == ["3700"]


def test_printed_parts_take_their_base_part_shape():
    catalog = catalog_of(PRINTED, BRICK_2X4)
    printed, plain = catalog.part("3001pb001"), catalog.part("3001")
    assert printed is not None
    assert plain is not None
    assert printed.name == "Brick 2 x 4 with Pattern"
    assert (printed.size, printed.connectors) == (plain.size, plain.connectors)
    assert [p.id for p in catalog.search("brick 2x4")] == ["3001", "3001pb001"]
    assert [p.id for p in catalog.find(family=Family.BRICK)] == ["3001pb001", "3001"]


def test_entries_are_checked_when_first_used():
    broken = {"id": "9999", "name": "Brick 1 x 1", "shape": {"family": "brick", "size": [0, 1]}}
    catalog = catalog_of(BRICK_2X4, broken)
    assert catalog.part("3001") is not None
    with pytest.raises(BrickyError, match="catalog part '9999' is not valid"):
        catalog.part("9999")


def test_catalog_data_is_checked_when_loaded():
    with pytest.raises(BrickyError, match="repeated part id: 3001"):
        catalog_of(BRICK_2X4, BRICK_2X4)
    with pytest.raises(BrickyError, match="not a bricky catalog"):
        Catalog.from_data({"parts": []})
    with pytest.raises(BrickyError, match="every part needs a string id"):
        catalog_of({"name": "Brick 1 x 1"})


def test_catalog_files_round_trip_and_are_configurable(tmp_path):
    written = CatalogFile(
        source="test",
        colors=(Color(id=5, name="Red", rgb="#C91A09"),),
        parts=(
            CatalogPart(
                id="3001", name="Brick 2 x 4", shape=BlockShape(family=Family.BRICK, size=(2, 4))
            ),
            CatalogPart.model_validate(PRINTED),
        ),
    )
    path = tmp_path / "catalog.json"
    path.write_bytes(written.dump())
    lines = path.read_text().splitlines()
    assert lines[1] == '{"id":5,"name":"Red","rgb":"#C91A09"}'
    assert len(lines) == 6
    catalog = load_catalog(path)
    assert catalog.source == "test"
    assert catalog.entries == written.parts
    assert catalog_path(Settings(catalog=path)) == path
    path.write_text("{}")
    with pytest.raises(BrickyError, match="not a bricky catalog"):
        load_catalog(path)
    with pytest.raises(BrickyError, match="cannot read catalog"):
        load_catalog(tmp_path / "missing.json")


def test_parts_without_a_shape_are_reported_by_the_builder_and_the_checks():
    catalog = catalog_of(BRICK_2X4, TECHNIC)
    builder = ModelBuilder(catalog=catalog)
    with pytest.raises(ValueError, match=r"part 3700 \(Technic, Brick 1 x 2 with Hole\) has no"):
        builder.place("3700", at=(0, 0, 0), color="Red")
    model = Model(elements=(Element(id="axle", part="3700", color=5),))
    report = check_model(model, catalog=catalog, settings=Settings())
    assert [d.message for d in report.diagnostics] == [
        "axle uses part '3700' (Technic, Brick 1 x 2 with Hole), which has no shape in the catalog"
    ]
