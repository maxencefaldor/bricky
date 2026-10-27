"""Collision: parts that share space, and studs that push into parts with no receptor."""

from collections import Counter
from collections.abc import Iterable, Iterator
from typing import ClassVar

from bricky.analysis import Context
from bricky.catalog import Connector, ConnectorKind
from bricky.diagnostics import Code, Diagnostic, Region
from bricky.geometry import Box, Vec3
from bricky.units import STUD_DIAMETER, STUD_HEIGHT

_STUD_RADIUS = STUD_DIAMETER // 2


def stud_volume(stud: Connector) -> Box:
    """Return the space a stud occupies, standing out of its face along its normal."""
    side = Vec3(*(0 if n else _STUD_RADIUS for n in stud.normal))
    tip = stud.pos + stud.normal * STUD_HEIGHT
    return Box.spanning(stud.pos - side, tip + side)


def _shared(a: Iterable[Box], b: Iterable[Box]) -> Box | None:
    overlaps = [
        shared for box in a for other in b if (shared := box.intersection(other)) is not None
    ]
    return Box.bounding(overlaps) if overlaps else None


class CollisionPass:
    """Report parts that overlap and studs that push into parts without a receptor there."""

    name: ClassVar[str] = "collision"
    summary: ClassVar[str] = "Parts sharing space, and studs blocked by parts with no receptor."
    codes: ClassVar[tuple[Code, ...]] = (
        Code(
            code="E201",
            title="Overlap",
            rule="The solid bodies of two parts share positive volume. Faces that only touch do "
            "not count, and studs are not part of the body (see E202). Each overlapping pair is "
            "reported once, with the box they share.",
        ),
        Code(
            code="E202",
            title="Blocked stud",
            rule="A stud stands inside another part's body where that part has no receptor "
            "facing it at the same position, so the two parts cannot sit where they are. Studs "
            "are 1.6 mm tall and 4.8 mm wide. Each pair of parts is reported once, with how "
            "many studs are blocked and the box they span.",
        ),
    )

    def run(self, context: Context) -> Iterator[Diagnostic]:
        """Return the problems found in the model."""
        yield from self._overlaps(context)
        yield from self._blocked_studs(context)

    def _overlaps(self, context: Context) -> Iterator[Diagnostic]:
        placed = context.world.placed
        for i, a in enumerate(placed):
            for j in sorted(context.solid_index.query(a.bounds)):
                if j <= i:
                    continue
                b = placed[j]
                shared = _shared(a.solids, b.solids)
                if shared is not None:
                    yield Diagnostic(
                        code="E201",
                        check=self.name,
                        message=f"{a.uid} and {b.uid} occupy the same space",
                        elements=(a.uid, b.uid),
                        region=Region.of(shared),
                    )

    def _blocked_studs(self, context: Context) -> Iterator[Diagnostic]:
        placed = context.world.placed
        counts: Counter[tuple[int, int]] = Counter()
        regions: dict[tuple[int, int], Box] = {}
        for i, a in enumerate(placed):
            for stud in a.connectors:
                if stud.kind is not ConnectorKind.STUD:
                    continue
                volume = stud_volume(stud)
                receivers = context.receptors.get((stud.pos, -stud.normal), ())
                for j in context.solid_index.query(volume):
                    if j == i or j in receivers:
                        continue
                    if any(volume.overlaps(solid) for solid in placed[j].solids):
                        counts[i, j] += 1
                        previous = regions.get((i, j))
                        regions[i, j] = (
                            volume if previous is None else Box.bounding((previous, volume))
                        )
        for (i, j), count in sorted(counts.items()):
            a, b = placed[i], placed[j]
            studs = "1 stud" if count == 1 else f"{count} studs"
            yield Diagnostic(
                code="E202",
                check=self.name,
                message=f"{studs} of {a.uid} push into {b.uid}, which has no receptor there",
                elements=(a.uid, b.uid),
                region=Region.of(regions[i, j]),
            )
