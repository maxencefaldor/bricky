# Copyright 2026 Maxence Faldor
"""Stability: groups that fall, and studs that grip near their limit."""

from __future__ import annotations

from collections.abc import Iterator
from typing import ClassVar

from bricky.analysis import Context
from bricky.diagnostics import Code, Diagnostic, Region
from bricky.errors import BrickyError
from bricky.geometry import Box

_MODEL = (
    "Elements are rigid and weigh their volume times the density setting. Forces act "
    "only where elements touch. Faces press on faces they rest against, where each "
    "face is the top or bottom of its part or holds its studs or anti-studs: the "
    "sides of parts stand 0.1 mm in from the grid. Faces with no stud between them "
    "also rub, with the friction setting. Studs bear any sideways force. The ground, "
    "at z = 0, presses up on every face that rests on it, with friction."
)


class StabilityPass:
    """Report groups that fall, and sites whose studs need much of their clutch."""

    name: ClassVar[str] = "stability"
    summary: ClassVar[str] = (
        "Groups that fall under their weight, and studs that grip near their limit."
    )
    codes: ClassVar[tuple[Code, ...]] = (
        Code(
            code="E401",
            title="Unbalanced group",
            rule=(
                f"{_MODEL} A group falls when no such forces balance the weight of "
                "each of its elements, however firmly studs grip. The pass reports "
                "each group of touching elements that moves, with the box around "
                "them. It leaves out elements with no chain of contacts to the "
                "ground, which E301 reports."
            ),
        ),
        Code(
            code="E402",
            title="Overloaded studs",
            rule=(
                f"{_MODEL} A stud's clutch, 2.94 N by default, is the force that pulls "
                "it out of its anti-stud. A stud alone between two elements also "
                "resists twisting with its clutch, at its 2.4 mm radius. The pass "
                "finds forces that hold the model still while the most loaded stud "
                "uses the least share of its clutch, with the groups of E401 held up. "
                "The studs that set that share form a site. The search repeats with "
                "the studs of each site found holding without limit, so each site "
                "needs its share however much the sites before it hold. The pass "
                "reports at most 16 sites, most loaded first: each whose studs need "
                "more than their clutch, with that share, the elements the studs join "
                "and the box around the studs."
            ),
        ),
        Code(
            code="W403",
            title="Strained studs",
            rule=(
                "As E402, for a site whose studs need more than 1 over the safety "
                "factor setting of their clutch, half by default, and at most all of "
                "it."
            ),
        ),
    )

    def run(self, context: Context) -> Iterator[Diagnostic]:
        """Yield the groups that fall, then the sites whose studs grip hard.

        Raises:
            BrickyError: If the solvers of the extra ``bricky[stability]`` are missing.
        """
        try:
            from bricky.analysis.stability import (  # noqa: PLC0415 - only checks of stability load the solvers, an optional extra
                Material,
                analyze_stability,
            )
        except ModuleNotFoundError as error:
            message = (
                f"the stability pass needs {error.name}: install bricky's solvers "
                "with the extra bricky[stability]"
            )
            raise BrickyError(message) from error

        settings = context.settings
        elements = context.world.elements
        stability = analyze_stability(
            context, Material.of(settings), threshold=1 / settings.safety_factor
        )
        for group in stability.falls:
            what = (
                "1 element falls" if len(group) == 1 else f"{len(group)} elements fall"
            )
            yield Diagnostic(
                code="E401",
                pass_name=self.name,
                message=(
                    f"{what}: no forces at their faces and studs balance their weight, "
                    "however firmly the studs grip"
                ),
                elements=tuple(elements[i].uid for i in group),
                region=Region.of(Box.bounding(elements[i].bounds for i in group)),
            )
        for site in stability.sites:
            count = len(site.joints)
            studs, need, their = (
                ("1 stud", "needs", "its")
                if count == 1
                else (f"{count} studs", "need", "their")
            )
            yield Diagnostic(
                code="E402" if site.load > 1 else "W403",
                pass_name=self.name,
                message=(
                    f"{studs} joining {len(site.elements)} elements {need} "
                    f"{site.load:.0%} of {their} clutch to hold the model together"
                ),
                elements=tuple(elements[i].uid for i in site.elements),
                region=Region.of(Box.bounding(joint.bounds for joint in site.joints)),
            )
