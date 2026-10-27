"""Import BrickLink's catalog: every part and every color, from BrickLink's own downloads.

BrickLink, the LEGO Group's marketplace, publishes its whole catalog as XML files at
https://www.bricklink.com/catalogDownload.asp, for members who are signed in:

- **Catalog Items**, item type Parts: every part's item number, name and category.
- **Colors**: every color's id, name, RGB value and type.
- **Categories**: every category's id and name.
- **Codes**: the colors each part comes in, with LEGO's element number for each.

:func:`read_downloads` finds these files in a folder by what they hold, whatever they are called.
:func:`import_catalog` turns them into a catalog: every part and every color, each part shaped when
its name describes a shape bricky has a family for (see :mod:`bricky.catalog.names`), and each
printed part shaped like the part it is printed on. Parts without a shape stay in the catalog, so
bricky knows them, but cannot be placed.
"""

import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field

from bricky.catalog import CatalogFile
from bricky.catalog.models import CatalogPart, Color, ColorType
from bricky.catalog.names import shape_from_name
from bricky.errors import BrickyError

DOWNLOAD_PAGE: Final = "https://www.bricklink.com/catalogDownload.asp"
"""Where signed-in BrickLink members download the catalog."""


class BrickLinkColor(BaseModel):
    """A color as BrickLink's Colors download lists it."""

    id: int
    name: str
    rgb: str = Field(description="Hex RGB without the '#', as BrickLink writes it.")
    type: str = Field(description="BrickLink's color type, such as 'Solid' or 'Transparent'.")


class BrickLinkItem(BaseModel):
    """An item as BrickLink's Catalog Items download lists it."""

    type: str = Field(description="Item type: 'P' for parts.")
    id: str
    name: str
    category: int
    alternates: tuple[str, ...] = Field(default=(), description="Other item numbers.")


class BrickLinkCode(BaseModel):
    """One color an item comes in, as BrickLink's Codes download lists it."""

    item_type: str
    item_id: str
    color: str = Field(description="Color name.")
    code: str = Field(description="LEGO's element number for the item in that color.")


class Downloads(BaseModel):
    """BrickLink's catalog downloads, read."""

    colors: tuple[BrickLinkColor, ...]
    categories: dict[int, str]
    parts: tuple[BrickLinkItem, ...]
    codes: tuple[BrickLinkCode, ...]
    files: dict[str, Path] = Field(description="The file each download was read from, by kind.")


class Coverage(BaseModel):
    """What an import found: how many parts and colors, and how many parts have a shape."""

    parts: int = Field(description="Parts imported.")
    shaped: int = Field(description="Parts with a shape, which can be placed.")
    printed: int = Field(description="Printed parts shaped like the part they are printed on.")
    by_family: dict[str, int] = Field(description="Shaped parts by family, printed ones included.")
    unshaped_by_category: dict[str, int] = Field(
        description="Parts without a shape by BrickLink category, most first."
    )
    colors: int = Field(description="Colors imported.")
    skipped_colors: tuple[str, ...] = Field(
        default=(), description="Colors left out, with why: no RGB value, or a repeated name."
    )


_PARTS: Final = "parts"
_KINDS: Final = ("colors", "categories", _PARTS, "codes")
_PRINTED: Final = re.compile(r"p[a-z]{0,3}\d")
"""How BrickLink numbers printed parts: the base part's number, then p, letters and digits."""


def read_downloads(folder: Path) -> Downloads:
    """Read BrickLink's catalog downloads from a folder, recognizing each file by its contents.

    Raises:
        BrickyError: If the folder is missing, a file is not valid XML, or the Parts or Colors
            download is not there.
    """
    if not folder.is_dir():
        msg = f"no such folder: {folder}"
        raise BrickyError(msg)
    found: dict[str, tuple[Path, list[dict[str, str]]]] = {}
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() != ".xml" or not path.is_file():
            continue
        kind, records = _read(path)
        if kind is not None:
            if kind in found:
                msg = f"{path} and {found[kind][0]} are both BrickLink {kind} downloads"
                raise BrickyError(msg)
            found[kind] = (path, records)
    missing = [kind for kind in ("colors", _PARTS) if kind not in found]
    if missing:
        names = {"colors": "Colors", _PARTS: "Catalog Items (Parts)"}
        wanted = " and ".join(names[kind] for kind in missing)
        msg = f"{folder} has no BrickLink {wanted} download, as XML, from {DOWNLOAD_PAGE}"
        raise BrickyError(msg)
    records = {kind: found[kind][1] if kind in found else [] for kind in _KINDS}
    try:
        return Downloads(
            colors=tuple(
                BrickLinkColor(
                    id=int(r["COLOR"]),
                    name=r["COLORNAME"],
                    rgb=r.get("COLORRGB", ""),
                    type=r.get("COLORTYPE", ""),
                )
                for r in records["colors"]
            ),
            categories={int(r["CATEGORY"]): r["CATEGORYNAME"] for r in records["categories"]},
            parts=tuple(
                BrickLinkItem(
                    type=r["ITEMTYPE"],
                    id=r["ITEMID"],
                    name=r["ITEMNAME"],
                    category=r["CATEGORY"],
                    alternates=tuple(r.get("ALTITEMIDS", "").replace(",", " ").split()),
                )
                for r in records[_PARTS]
                if r.get("ITEMTYPE") == "P"
            ),
            codes=tuple(
                BrickLinkCode(
                    item_type=r["ITEMTYPE"],
                    item_id=r["ITEMID"],
                    color=r["COLOR"],
                    code=r.get("CODENAME", ""),
                )
                for r in records["codes"]
            ),
            files={kind: path for kind, (path, _) in found.items()},
        )
    except (KeyError, ValueError) as error:
        msg = f"a BrickLink download in {folder} is missing a field or has a bad value: {error}"
        raise BrickyError(msg) from None


def import_catalog(downloads: Downloads) -> tuple[CatalogFile, Coverage]:
    """Turn BrickLink's downloads into a catalog file, and say how much of it has a shape.

    The same downloads always give the same file: parts and colors keep BrickLink's order, and the
    file is dated by the newest download.
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
        if item.id in entries:
            continue
        entries[item.id] = CatalogPart(
            id=item.id,
            name=" ".join(item.name.split()),
            category=downloads.categories.get(item.category),
            alternates=item.alternates,
            colors=tuple(sorted(known.get(item.id, ()))),
            shape=shape_from_name(item.name),
        )
    printed = _shape_printed_parts(entries)

    families: Counter[str] = Counter()
    unshaped: Counter[str] = Counter()
    for entry in entries.values():
        shape = entry.shape or (entries[entry.base].shape if entry.base else None)
        if shape is None:
            unshaped[entry.category or "no category"] += 1
        else:
            families[shape.family.value] += 1
    coverage = Coverage(
        parts=len(entries),
        shaped=families.total(),
        printed=printed,
        by_family=dict(families.most_common()),
        unshaped_by_category=dict(unshaped.most_common()),
        colors=len(colors),
        skipped_colors=skipped,
    )
    newest = max(path.stat().st_mtime for path in downloads.files.values())
    date = datetime.fromtimestamp(newest, UTC).date().isoformat()
    catalog = CatalogFile(
        source=f"BrickLink catalog downloads of {date}",
        colors=tuple(colors),
        parts=tuple(entries.values()),
    )
    return catalog, coverage


def color_type(bricklink_type: str, name: str) -> ColorType:
    """Map a BrickLink color type to bricky's, seeing transparency in the name too.

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
    for color in sorted(found, key=lambda c: c.id):
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


def _shape_printed_parts(entries: dict[str, CatalogPart]) -> int:
    """Name the part each printed part is printed on, as its base, and count them.

    A printed part's number is its base part's number followed by p, letters and digits, such as
    3068bpb0001 for a print on 3068b, and its name starts with the base part's name. Both must
    hold, and the base part must have a shape.
    """
    count = 0
    for key, entry in entries.items():
        if entry.shape is not None:
            continue
        for match in _PRINTED.finditer(key):
            base = entries.get(key[: match.start()])
            if (
                base is not None
                and base.shape is not None
                and entry.name.startswith(base.name + " ")
            ):
                entries[key] = entry.model_copy(update={"base": base.id})
                count += 1
                break
    return count


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
        msg = f"{path} is not valid XML: {error}"
        raise BrickyError(msg) from None
    records = [
        {child.tag: (child.text or "").strip() for child in item} for item in root.iter("ITEM")
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
