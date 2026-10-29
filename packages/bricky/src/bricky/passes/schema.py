# Copyright 2026 Maxence Faldor
"""Schema: unknown parts and colors, parts below the ground, and colors never made."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from typing import ClassVar

from bricky.analysis import Context
from bricky.diagnostics import Code, Diagnostic, Region


class SchemaPass:
    """Report what the catalog lacks, parts below the ground, and colors never made."""

    name: ClassVar[str] = "schema"
    summary: ClassVar[str] = (
        "Unknown parts and colors, parts below the ground plane, and colors a part "
        "never came in."
    )
    codes: ClassVar[tuple[Code, ...]] = (
        Code(
            code="E101",
            title="Unknown part",
            rule=(
                "The element's part id is not in the catalog, or the catalog lists the "
                "part without a shape. The element then has no geometry, and no other "
                "pass sees it. The command `bricky parts` searches the catalog."
            ),
        ),
        Code(
            code="E102",
            title="Unknown color",
            rule=(
                "The element's color id is not in the catalog. The command "
                "`bricky colors` lists the catalog's colors."
            ),
        ),
        Code(
            code="E103",
            title="Below the ground",
            rule=(
                "The element's body reaches below the ground plane, z = 0. The ground "
                "plane is the table the model stands on."
            ),
        ),
        Code(
            code="W104",
            title="Color never made",
            rule=(
                "The catalog lists the colors a part has come in, and the element's "
                "color is not among them: the part and the color both exist, but never "
                "together. The pass reports each part and color once, with every "
                "element that uses them. Parts the catalog lists without colors are "
                "not checked."
            ),
        ),
    )

    def run(self, context: Context) -> Iterator[Diagnostic]:
        """Yield unknown parts, then unknown colors and parts below the ground."""
        for unknown in context.world.unknown:
            entry = context.catalog.entry(unknown.part)
            what = (
                "which is not in the catalog"
                if entry is None
                else f"({entry.name}), which has no shape in the catalog"
            )
            yield Diagnostic(
                code="E101",
                pass_name=self.name,
                message=f"{unknown.uid} uses part {unknown.part!r} {what}",
                elements=(unknown.uid,),
            )
        yield from self._colors_never_made(context)
        for element in context.world.elements:
            if context.catalog.color(element.color) is None:
                yield Diagnostic(
                    code="E102",
                    pass_name=self.name,
                    message=(
                        f"{element.uid} uses color {element.color}, "
                        "which is not in the catalog"
                    ),
                    elements=(element.uid,),
                )
            if element.bounds.min.z < 0:
                yield Diagnostic(
                    code="E103",
                    pass_name=self.name,
                    message=f"{element.uid} reaches below the ground plane",
                    elements=(element.uid,),
                    region=Region.of(element.bounds),
                )

    def _colors_never_made(self, context: Context) -> Iterator[Diagnostic]:
        uses: defaultdict[tuple[str, int], list[str]] = defaultdict(list)
        for element in context.world.elements:
            entry = context.catalog.entry(element.part.id)
            if entry is None or not entry.colors or element.color in entry.colors:
                continue
            if context.catalog.color(element.color) is not None:
                uses[element.part.id, element.color].append(element.uid)
        for (part_id, color_id), uids in uses.items():
            color = context.catalog.color(color_id)
            name = color.name if color is not None else str(color_id)
            count = (
                "1 element uses it"
                if len(uids) == 1
                else f"{len(uids)} elements use it"
            )
            yield Diagnostic(
                code="W104",
                pass_name=self.name,
                message=f"part {part_id} never came in {name}; {count}",
                elements=tuple(uids),
            )
