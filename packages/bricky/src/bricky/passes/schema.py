"""Schema: unknown parts and colours, and parts below the ground plane."""

from collections.abc import Iterator
from typing import ClassVar

from bricky.analysis import Context
from bricky.diagnostics import Code, Diagnostic, Region


class SchemaPass:
    """Report references the catalog cannot resolve and parts that dip below the ground."""

    name: ClassVar[str] = "schema"
    summary: ClassVar[str] = "Unknown parts and colours, and parts below the ground plane."
    codes: ClassVar[tuple[Code, ...]] = (
        Code(
            code="E101",
            title="Unknown part",
            rule="The element's part id is not in the catalog, or the catalog lists the part "
            "without a shape, so it has no geometry and no other check can see it. `bricky parts` "
            "searches the catalog.",
        ),
        Code(
            code="E102",
            title="Unknown colour",
            rule="The element's colour id is not in the catalog. `bricky colors` lists the "
            "catalog's colours.",
        ),
        Code(
            code="E103",
            title="Below the ground",
            rule="Some of the part's body lies below the ground plane, z = 0. The ground plane is "
            "the table the model stands on.",
        ),
    )

    def run(self, context: Context) -> Iterator[Diagnostic]:
        """Return the diagnostics found in the model."""
        for item in context.world.unresolved:
            entry = context.catalog.entry(item.part)
            what = (
                "which is not in the catalog"
                if entry is None
                else f"({entry.name}), which has no shape in the catalog"
            )
            yield Diagnostic(
                code="E101",
                check=self.name,
                message=f"{item.uid} uses part {item.part!r} {what}",
                elements=(item.uid,),
            )
        for placed in context.world.placed:
            if context.catalog.color(placed.color) is None:
                yield Diagnostic(
                    code="E102",
                    check=self.name,
                    message=f"{placed.uid} uses colour {placed.color}, which is not in the catalog",
                    elements=(placed.uid,),
                )
            if placed.bounds.lo.z < 0:
                yield Diagnostic(
                    code="E103",
                    check=self.name,
                    message=f"{placed.uid} reaches below the ground plane",
                    elements=(placed.uid,),
                    region=Region.of(placed.bounds),
                )
