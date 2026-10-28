"""Import BrickLink's catalog: every part and every color, from BrickLink's own downloads.

BrickLink, the LEGO Group's marketplace, publishes its whole catalog as XML files at
https://www.bricklink.com/catalogDownload.asp, for signed-in members:

- **Catalog Items**, item type Parts: every part's id, name and category.
- **Colors**: every color's id, name, RGB value and type.
- **Categories**: every category's id and name.
- **Codes**: the colors each part comes in, with the LEGO Group's number for each.

:func:`read_downloads` finds these files in a folder by their contents, whatever their names.
:func:`bricklink_parts` converts them into catalog colors and parts, and gives each part the shape
its name describes, when bricky has a family for it (see :mod:`bricky.catalog.names`).
:mod:`bricky.catalog.importing` combines them with shapes from LDraw.
"""

import html
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field

from bricky.catalog.models import CatalogPart, Color, ColorType
from bricky.catalog.names import shape_from_name
from bricky.errors import BrickyError

DOWNLOAD_PAGE: Final = "https://www.bricklink.com/catalogDownload.asp"
"""The page where signed-in BrickLink members download the catalog."""


class BrickLinkColor(BaseModel):
    """A color as BrickLink's Colors download lists it."""

    id: int
    name: str
    rgb: str = Field(description="Hexadecimal RGB without the '#', as BrickLink writes it.")
    type: str = Field(description="BrickLink's color type, such as 'Solid' or 'Transparent'.")


class BrickLinkItem(BaseModel):
    """An item as BrickLink's Catalog Items download lists it."""

    type: str = Field(description="Item type: 'P' for parts.")
    id: str
    name: str
    category: int
    alternates: tuple[str, ...] = Field(default=(), description="Other ids of the item.")


class BrickLinkCode(BaseModel):
    """One color an item comes in, as BrickLink's Codes download lists it."""

    item_type: str
    item_id: str
    color: str = Field(description="The color's name.")
    code: str = Field(description="The LEGO Group's number for the item in that color.")


class Downloads(BaseModel):
    """BrickLink's catalog downloads, as read from their files."""

    colors: tuple[BrickLinkColor, ...]
    categories: dict[int, str]
    parts: tuple[BrickLinkItem, ...]
    codes: tuple[BrickLinkCode, ...]
    files: dict[str, Path] = Field(description="The file each download was read from, by kind.")


_PARTS: Final = "parts"
_KINDS: Final = ("colors", "categories", _PARTS, "codes")


def read_downloads(folder: Path) -> Downloads:
    """Read BrickLink's catalog downloads from a folder, recognizing each file by its contents.

    Raises:
        BrickyError: If the folder is missing, a file is not valid XML, two files hold the same
            download, or the folder lacks the Parts or the Colors download.
    """
    if not folder.is_dir():
        message = f"no such folder: {folder}"
        raise BrickyError(message)
    found: dict[str, tuple[Path, list[dict[str, str]]]] = {}
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() != ".xml" or not path.is_file():
            continue
        kind, records = _read(path)
        if kind is not None:
            if kind in found:
                message = f"{path} and {found[kind][0]} are both BrickLink {kind} downloads"
                raise BrickyError(message)
            found[kind] = (path, records)
    missing = [kind for kind in ("colors", _PARTS) if kind not in found]
    if missing:
        names = {"colors": "Colors", _PARTS: "Catalog Items (Parts)"}
        wanted = " and ".join(names[kind] for kind in missing)
        message = f"{folder} has no BrickLink {wanted} download, as XML, from {DOWNLOAD_PAGE}"
        raise BrickyError(message)
    records = {kind: found[kind][1] if kind in found else [] for kind in _KINDS}
    try:
        return Downloads(
            colors=tuple(
                BrickLinkColor(
                    id=int(record["COLOR"]),
                    name=record["COLORNAME"],
                    rgb=record.get("COLORRGB", ""),
                    type=record.get("COLORTYPE", ""),
                )
                for record in records["colors"]
            ),
            categories={
                int(record["CATEGORY"]): record["CATEGORYNAME"] for record in records["categories"]
            },
            parts=tuple(
                BrickLinkItem(
                    type=record["ITEMTYPE"],
                    id=record["ITEMID"],
                    name=record["ITEMNAME"],
                    category=record["CATEGORY"],
                    alternates=tuple(record.get("ALTITEMIDS", "").replace(",", " ").split()),
                )
                for record in records[_PARTS]
                if record.get("ITEMTYPE") == "P"
            ),
            codes=tuple(
                BrickLinkCode(
                    item_type=record["ITEMTYPE"],
                    item_id=record["ITEMID"],
                    color=record["COLOR"],
                    code=record.get("CODENAME", ""),
                )
                for record in records["codes"]
            ),
            files={kind: path for kind, (path, _) in found.items()},
        )
    except (KeyError, ValueError) as error:
        message = f"a BrickLink download in {folder} lacks a field or has an invalid value: {error}"
        raise BrickyError(message) from None


def bricklink_parts(
    downloads: Downloads,
) -> tuple[list[Color], tuple[str, ...], dict[str, CatalogPart]]:
    """Return BrickLink's colors, the colors left out with their reasons, and its parts by id.

    Each part gets the shape its name describes, if any, and the colors the Codes download lists
    for it. Parts keep BrickLink's order, and colors are sorted by id.
    """
    colors, skipped = _colors(downloads.colors)
    color_ids = {color.name.casefold(): color.id for color in colors}
    known: defaultdict[str, set[int]] = defaultdict(set)
    for code in downloads.codes:
        color_id = color_ids.get(code.color.casefold())
        if code.item_type == "P" and color_id is not None:
            known[code.item_id].add(color_id)
    entries: dict[str, CatalogPart] = {}
    for item in downloads.parts:
        if item.id not in entries:
            entries[item.id] = CatalogPart(
                id=item.id,
                name=" ".join(item.name.split()),
                category=downloads.categories.get(item.category),
                alternates=item.alternates,
                colors=tuple(sorted(known.get(item.id, ()))),
                shape=shape_from_name(item.name),
            )
    return colors, skipped, entries


def downloaded(downloads: Downloads) -> str:
    """Return the date of the downloads, from the newest file, such as ``2026-10-28``."""
    newest = max(path.stat().st_mtime for path in downloads.files.values())
    return datetime.fromtimestamp(newest, UTC).date().isoformat()


def color_type(bricklink_type: str, name: str) -> ColorType:
    """Map a BrickLink color type to bricky's, reading transparency from the name too.

    BrickLink gives some see-through colors another type, such as "Glitter Trans-Clear", so a name
    containing "Trans-" counts as transparent whatever its type.
    """
    if "transparent" in bricklink_type.casefold() or re.search(r"(^|\s)Trans-", name):
        return ColorType.TRANSPARENT
    for kind in ColorType:
        if kind.value in bricklink_type.casefold():
            return kind
    return ColorType.SOLID


def _colors(found: Iterable[BrickLinkColor]) -> tuple[list[Color], tuple[str, ...]]:
    colors: list[Color] = []
    skipped: list[str] = []
    names: set[str] = set()
    for color in sorted(found, key=lambda color: color.id):
        rgb = color.rgb.strip().upper()
        if color.id < 1:
            continue  # BrickLink's "(Not Applicable)", for items that have no color
        if not re.fullmatch(r"[0-9A-F]{6}", rgb):
            skipped.append(f"{color.name} ({color.id}): no RGB value")
            continue
        if color.name.casefold() in names:
            skipped.append(f"{color.name} ({color.id}): repeated name")
            continue
        names.add(color.name.casefold())
        colors.append(
            Color(
                id=color.id, name=color.name, type=color_type(color.type, color.name), rgb=f"#{rgb}"
            )
        )
    return colors, tuple(skipped)


def _read(path: Path) -> tuple[str | None, list[dict[str, str]]]:
    """Read one download: what kind it is, and its records as tag-to-text mappings."""
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1252")
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
    try:
        root = ET.fromstring(text)  # noqa: S314 - BrickLink's own downloads, read locally
    except ET.ParseError as error:
        message = f"{path} is not valid XML: {error}"
        raise BrickyError(message) from None
    records = [  # BrickLink escapes some characters twice, such as "(" as "&amp;#40;"
        {child.tag: html.unescape(child.text or "").strip() for child in item}
        for item in root.iter("ITEM")
    ]
    return _kind(root.tag, records), records


def _kind(root: str, records: Sequence[dict[str, str]]) -> str | None:
    if not records:
        return None
    tags = records[0].keys()
    if root == "CODES" or "CODENAME" in tags:
        return "codes"
    if "COLORNAME" in tags:
        return "colors"
    if "CATEGORYNAME" in tags:
        return "categories"
    if "ITEMNAME" in tags:  # Catalog Items: parts, or another item type such as sets
        return _PARTS if records[0].get("ITEMTYPE") == "P" else None
    return None
