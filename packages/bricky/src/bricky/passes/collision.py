# Copyright 2026 Maxence Faldor
"""Collision: parts that share space, and studs that push into parts with no anti-stud."""

from collections import Counter
from collections.abc import Iterable, Iterator
from typing import ClassVar

from bricky.analysis import Context
from bricky.catalog import Connector, ConnectorKind
from bricky.diagnostics import Code, Diagnostic, Region
from bricky.geometry import Box, Solid, Vector, overlaps
from bricky.units import STUD_DIAMETER, STUD_HEIGHT

_STUD_RADIUS = STUD_DIAMETER // 2


def stud_volume(stud: Connector) -> Box:
    """Return the box a stud occupies as it stands out of its face along its normal."""
    side = Vector(*(0 if component else _STUD_RADIUS for component in stud.normal))
    tip = stud.position + stud.normal * STUD_HEIGHT
    return Box.spanning(stud.position - side, tip + side)


def _shared(first: Iterable[Solid], second: Iterable[Solid]) -> Box | None:
    """Return the box around the overlaps of two parts' solids, or ``None`` if none overlap."""
    shared = [
        box
        for solid in first
        for other in second
        if overlaps(solid, other)
        and (box := solid.bounds.intersection(other.bounds)) is not None
    ]
    return Box.bounding(shared) if shared else None


class CollisionPass:
    """Report parts that overlap, and studs that push into parts with no anti-stud there."""

    name: ClassVar[str] = "collision"
    summary: ClassVar[str] = (
        "Parts sharing space, and studs blocked by parts with no anti-stud."
    )
    codes: ClassVar[tuple[Code, ...]] = (
        Code(
            code="E201",
            title="Overlap",
            rule="The bodies of two parts share positive volume. Faces that only touch do not "
            "count, and studs belong to no body (see E202). The pass reports each overlapping "
            "pair once, with the box the two share.",
        ),
        Code(
            code="E202",
            title="Blocked stud",
            rule="A stud stands inside another part's body where that part has no anti-stud "
            "facing it at the same position, so the two parts cannot sit where they are. A stud "
            "is 1.6 mm tall and 4.8 mm wide. The pass reports each pair of parts once, with the "
            "number of blocked studs and the box they span.",
        ),
    )

    def run(self, context: Context) -> Iterator[Diagnostic]:
        """Yield the overlaps in the model, then the blocked studs."""
        yield from self._overlaps(context)
        yield from self._blocked_studs(context)

    def _overlaps(self, context: Context) -> Iterator[Diagnostic]:
        elements = context.world.elements
        for i, element in enumerate(elements):
            for j in sorted(context.solid_index.query(element.bounds)):
                if j <= i:
                    continue
                other = elements[j]
                shared = _shared(element.solids, other.solids)
                if shared is not None:
                    yield Diagnostic(
                        code="E201",
                        pass_name=self.name,
                        message=f"{element.uid} and {other.uid} occupy the same space",
                        elements=(element.uid, other.uid),
                        region=Region.of(shared),
                    )

    def _blocked_studs(self, context: Context) -> Iterator[Diagnostic]:
        elements = context.world.elements
        counts: Counter[tuple[int, int]] = Counter()
        regions: dict[tuple[int, int], Box] = {}
        for i, element in enumerate(elements):
            for stud in element.connectors:
                if stud.kind is not ConnectorKind.STUD:
                    continue
                volume = stud_volume(stud)
                anti_studs = context.anti_studs.get((stud.position, -stud.normal), ())
                for j in context.solid_index.query(volume):
                    if j == i or j in anti_studs:
                        continue
                    if any(overlaps(volume, solid) for solid in elements[j].solids):
                        counts[i, j] += 1
                        previous = regions.get((i, j))
                        regions[i, j] = (
                            volume
                            if previous is None
                            else Box.bounding((previous, volume))
                        )
        for (i, j), count in sorted(counts.items()):
            element, other = elements[i], elements[j]
            studs = "1 stud" if count == 1 else f"{count} studs"
            push = "pushes" if count == 1 else "push"
            yield Diagnostic(
                code="E202",
                pass_name=self.name,
                message=f"{studs} of {element.uid} {push} into {other.uid}, which has no anti-stud "
                "there",
                elements=(element.uid, other.uid),
                region=Region.of(regions[i, j]),
            )
