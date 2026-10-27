import pytest

from bricky.catalog import ConnectorKind, Family, default_catalog
from bricky.geometry import DOWN, UP, Vec3
from bricky.units import BRICK, PLATE, STUD


def test_default_catalog_loads():
    catalog = default_catalog()
    assert len(catalog.parts) == 30
    assert {part.family for part in catalog.parts} == set(Family)


def test_brick_geometry():
    brick = default_catalog().part("3001")
    assert brick is not None
    assert brick.name == "Brick 2 x 4"
    assert brick.size == Vec3(2 * STUD, 4 * STUD, BRICK)
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


def test_search_matches_every_word_and_both_size_spellings():
    catalog = default_catalog()
    assert [p.id for p in catalog.search("brick 2x4")] == ["3001"]
    assert [p.id for p in catalog.search("brick 2 x 4")] == ["3001"]
    assert {p.family for p in catalog.search("plate")} == {Family.PLATE}
    assert len(catalog.search("tile", limit=3)) == 3
