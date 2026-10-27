"""Schema: unknown parts and colours, and parts below the ground plane."""

from collections.abc import Iterator
from typing import ClassVar

from bricky.analysis import Context
from bricky.diagnostics import Diagnostic, Region


class SchemaPass:
    """Report references the catalog cannot resolve and parts that dip below the ground."""

    name: ClassVar[str] = "schema"
    summary: ClassVar[str] = "Unknown parts and colours, and parts below the ground plane."

    def run(self, context: Context) -> Iterator[Diagnostic]:
        """Return the problems found in the model."""
        for item in context.world.unresolved:
            yield Diagnostic(
                code="E101",
                check=self.name,
                message=f"{item.uid} uses unknown part {item.part!r}",
                elements=(item.uid,),
                help="search the catalog with `bricky parts <words>`",
            )
        for placed in context.world.placed:
            if context.catalog.color(placed.color) is None:
                yield Diagnostic(
                    code="E102",
                    check=self.name,
                    message=f"{placed.uid} uses unknown colour {placed.color}",
                    elements=(placed.uid,),
                    help="use a BrickLink colour id from the catalog",
                )
            if placed.bounds.lo.z < 0:
                yield Diagnostic(
                    code="E103",
                    check=self.name,
                    message=f"{placed.uid} reaches below the ground",
                    elements=(placed.uid,),
                    region=Region.of(placed.bounds),
                    help="raise it so its bottom sits at z = 0 or above",
                )
