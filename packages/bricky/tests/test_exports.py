# Copyright 2026 Maxence Faldor

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from bricky import BrickyError, ModelBuilder, default_catalog, save_model
from bricky.cli import main
from bricky.exports import FORMATS, Format, Lot, model_lots


def bay() -> ModelBuilder:
    builder = ModelBuilder("bay")
    pillar = builder.component("pillar")
    pillar.place("3005", at=(0, 0, 0), color="White")
    pillar.place("3005", at=(0, 0, 3), color="White")
    builder.place("3001", at=(0, 0, 0), color="Red")
    builder.instance("pillar", at=(0, 0, 3))
    builder.instance("pillar", at=(3, 0, 3))
    builder.place("3068b", at=(0, 0, 9), color="Red")  # an alternate id of 3068
    return builder


def test_lots_count_every_instance_by_bricklink_id() -> None:
    lots = model_lots(bay().build(), default_catalog())
    assert lots == (
        Lot(part="3001", color=5, quantity=1),
        Lot(part="3005", color=1, quantity=4),
        Lot(part="3068", color=5, quantity=1),
    )


def test_lots_need_every_part_and_color_in_the_catalog() -> None:
    builder = ModelBuilder("odd")
    builder.place("3001", at=(0, 0, 0), color="Red")
    model = builder.build()
    unknown = model.model_copy(
        update={"elements": (model.elements[0].model_copy(update={"part": "x9999"}),)}
    )
    with pytest.raises(BrickyError, match="catalog lacks part x9999"):
        model_lots(unknown, default_catalog())


def test_a_wanted_list_lists_each_lot_as_a_bricklink_item() -> None:
    lots = model_lots(bay().build(), default_catalog())
    xml = FORMATS[Format.WANTED_LIST].write(lots)
    root = ET.fromstring(xml)  # noqa: S314 - the list bricky just wrote
    assert root.tag == "INVENTORY"
    items = [{field.tag: field.text for field in item} for item in root]
    assert items[1] == {"ITEMTYPE": "P", "ITEMID": "3005", "COLOR": "1", "MINQTY": "4"}
    assert len(items) == len(lots)


def test_export_writes_the_list_beside_the_model(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    model = tmp_path / "bay.bricky.json"
    save_model(bay().build(), model)
    main(["export", str(model)])
    out = capsys.readouterr().out
    assert out.startswith(f"wrote {tmp_path / 'bay.wanted.xml'}: 3 lots, 6 elements")
    assert "Upload BrickLink XML format" in out
    assert (tmp_path / "bay.wanted.xml").read_text().startswith("<INVENTORY>")
    output = tmp_path / "lists" / "bay.xml"
    main(["export", str(model), "--output", str(output), "--output-format", "json"])
    assert json.loads(capsys.readouterr().out)["lots"] == 3
    assert output.is_file()
