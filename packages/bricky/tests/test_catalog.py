import re

import pytest
from pydantic import ValidationError

from bricky.catalog import Catalog, ColorType, ConnectorKind, Family, default_catalog
from bricky.geometry import DOWN, UP, Vec3
from bricky.units import BRICK, PLATE, STUD


def test_default_catalog_loads_every_family():
    catalog = default_catalog()
    assert len(catalog.parts) > 100
    assert {part.family for part in catalog.parts} == set(Family)


def test_brick_geometry():
    brick = default_catalog().part("3001")
    assert brick is not None
    assert brick.name == "Brick 2 x 4"
    assert brick.size == Vec3(2 * STUD, 4 * STUD, BRICK)
    assert brick.footprint == (2, 4)
    studs = [c for c in brick.connectors if c.kind is ConnectorKind.STUD]
    receptors = [c for c in brick.connectors if c.kind is ConnectorKind.ANTI_STUD]
    assert len(studs) == len(receptors) == 8
    assert all(c.normal == UP and c.pos.z == BRICK for c in studs)
    assert all(c.normal == DOWN and c.pos.z == 0 for c in receptors)


def test_tiles_have_receptors_but_no_studs():
    tile = default_catalog().part("3068b")
    assert tile is not None
    assert tile.size.z == PLATE
    assert tile.stud_count == 0
    assert len(tile.connectors) == 4


def test_colours_resolve_by_name_or_id():
    catalog = default_catalog()
    assert catalog.resolve_color("light bluish gray").id == 86
    assert catalog.resolve_color(5).name == "Red"
    assert catalog.resolve_color("11").name == "Black"
    with pytest.raises(ValueError, match="unknown colour"):
        catalog.resolve_color("Chartreuse Sparkle")


def test_every_colour_has_a_display_colour_and_a_unique_id_and_name():
    colors = default_catalog().colors
    assert all(re.fullmatch(r"#[0-9A-F]{6}", c.rgb) for c in colors)
    assert len({c.id for c in colors}) == len(colors)
    assert len({c.name.casefold() for c in colors}) == len(colors)
    transparent = {c.name for c in colors if c.type is ColorType.TRANSPARENT}
    assert transparent == {c.name for c in colors if c.name.startswith("Trans-")}


def test_colour_search_matches_ids_names_and_types():
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
    assert {p.family for p in catalog.search("plate 2x2")} == {
        Family.PLATE,
        Family.ROUND,
        Family.JUMPER,
    }
    assert [p.id for p in catalog.search("slope 45 2x2")] == ["3039", "3660"]
    assert len(catalog.search("tile", limit=3)) == 3


def test_find_by_family_and_footprint_in_either_order():
    catalog = default_catalog()
    assert [p.id for p in catalog.find(family="plate", size=(6, 1))] == ["3666"]
    assert [p.id for p in catalog.find(family=Family.BRICK, size=(2, 2))] == ["3003"]
    assert [p.id for p in catalog.find(family="slope", size=(2, 2))] == ["3039", "3678b", "3684"]
    assert {p.footprint for p in catalog.find(family="tile")} >= {(1, 1), (2, 2)}
    assert catalog.find(family="plate", size=(5, 1)) == []


def test_repeated_ids_are_rejected():
    part = {"id": "3005", "name": "Brick 1 x 1", "family": "brick", "size": [1, 1]}
    with pytest.raises(ValidationError, match="repeated part id: 3005"):
        Catalog.from_data({"parts": [part, part]})
