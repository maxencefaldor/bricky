# Copyright 2026 Maxence Faldor
"""BrickLink Wanted Lists: the parts to buy, in BrickLink's XML.

BrickLink, the LEGO Group's marketplace, imports a Wanted List from XML: an
``INVENTORY`` of ``ITEM`` records (https://www.bricklink.com/help.asp?helpID=207). Each
item here holds the item type ``P`` (a part), the part's BrickLink id, its BrickLink
color id and the wanted quantity, ``MINQTY``. bricky's ids are BrickLink's own, so the
list is exact. BrickLink then finds the stores that sell each part.
"""

from __future__ import annotations

from collections.abc import Sequence
from xml.sax.saxutils import escape

from bricky.exports.lots import Lot


def write(lots: Sequence[Lot]) -> bytes:
    """Write lots as a BrickLink Wanted List, one ``ITEM`` per lot."""
    items = "".join(
        "  <ITEM>\n"
        "    <ITEMTYPE>P</ITEMTYPE>\n"
        f"    <ITEMID>{escape(lot.part)}</ITEMID>\n"
        f"    <COLOR>{lot.color}</COLOR>\n"
        f"    <MINQTY>{lot.quantity}</MINQTY>\n"
        "  </ITEM>\n"
        for lot in lots
    )
    return f"<INVENTORY>\n{items}</INVENTORY>\n".encode()
