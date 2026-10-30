# Copyright 2026 Maxence Faldor
"""Stability: groups that fall, and studs that grip near their limit."""

from __future__ import annotations

from collections.abc import Iterator
from math import ceil
from typing import ClassVar

from bricky.analysis import Context
from bricky.diagnostics import Diagnostic, Region, Rule
from bricky.geometry import Box
from bricky.settings import Level

_MODEL = (
    "Elements are rigid and weigh their volume times the density setting. Forces act "
    "only where elements touch. Faces that face up and down press on each other, since "
    "weight closes any gap. Faces that face sideways press only where each is the top "
    "or bottom of its part, or holds its studs or anti-studs. The sides of parts stand "
    "0.1 mm in from the grid, so they never touch. Faces that no stud joins also rub, "
    "with the friction setting. Studs bear any sideways force. The ground, at z = 0, "
    "presses up wherever an element reaches it, with friction."
)


_STUD_RULES = ("overloaded-studs", "strained-studs")


class StabilityPass:
    """Report groups that fall, and sites whose studs need much of their clutch."""

    name: ClassVar[str] = "stability"
    summary: ClassVar[str] = (
        "Groups that fall under their weight, and studs that grip near their limit."
    )
    rules: ClassVar[tuple[Rule, ...]] = (
        Rule(
            name="unbalanced-group",
            default_level=Level.WARN,
            condition=(
                f"{_MODEL} A group falls when no such forces balance the weight of "
                "each of its elements, however firmly studs grip. The pass reports "
                "each group of touching elements that moves, with the box around "
                "them. The pass leaves out elements with no chain of contacts to the "
                "ground, which floating-group reports."
            ),
        ),
        Rule(
            name="overloaded-studs",
            default_level=Level.IGNORE,
            condition=(
                f"{_MODEL} A stud's clutch, 2.94 N by default, is the force that pulls "
                "it out of its anti-stud. A stud alone where two elements meet face to "
                "face also resists twisting, at its 2.4 mm radius. The pull and twist "
                "of such a stud share its clutch, and two or more studs there resist "
                "any twist together. The pass finds forces that hold the model still "
                "while the most loaded stud uses the least share of its clutch. The "
                "groups that unbalanced-group reports stay held up meanwhile. The "
                "studs that set that share form sites, one for each group of elements "
                "that would move together to pull them out. The search repeats with "
                "the studs of each site found holding without limit. Each site "
                "therefore needs its share however much the sites before it hold. The "
                "pass reports at most 16 sites, most loaded first, each whose studs "
                "need more than their clutch. Each diagnostic gives that share rounded "
                "up, the elements the studs join and the box around the studs."
            ),
        ),
        Rule(
            name="strained-studs",
            default_level=Level.IGNORE,
            condition=(
                "The pass reports sites as for overloaded-studs. Each site's studs "
                "need more than 1 over the safety factor setting of their clutch, half "
                "by default, and at most all of it."
            ),
        ),
    )

    def run(self, context: Context) -> Iterator[Diagnostic]:
        """Yield the groups that fall, then the sites whose studs grip hard.

        The search for sites, the slow part, runs only when the check reports
        overloaded-studs or strained-studs, which are off by default, and only as deep
        as those rules need.
        """
        from bricky.analysis.stability import (  # noqa: PLC0415 - the solvers load only when a check runs the pass
            Material,
            analyze_stability,
        )

        settings = context.settings
        elements = context.world.elements
        overloaded, strained = (self._checks(context, name) for name in _STUD_RULES)
        threshold = None
        if overloaded:
            threshold = 1.0
        if strained:
            threshold = 1 / settings.safety_factor
        stability = analyze_stability(
            context, Material.of(settings), threshold=threshold
        )
        for group in stability.falls:
            what = (
                "1 element falls" if len(group) == 1 else f"{len(group)} elements fall"
            )
            yield Diagnostic(
                rule="unbalanced-group",
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
                rule="overloaded-studs" if site.load > 1 else "strained-studs",
                message=(
                    f"{studs} joining {len(site.elements)} elements {need} "
                    f"{ceil(site.load * 100)}% of {their} clutch to hold the model "
                    "together"
                ),
                elements=tuple(elements[i].uid for i in site.elements),
                region=Region.of(Box.bounding(joint.bounds for joint in site.joints)),
            )

    @classmethod
    def _checks(cls, context: Context, name: str) -> bool:
        """Whether the check reports the rule of this pass named ``name``."""
        rule = next(rule for rule in cls.rules if rule.name == name)
        return context.checks(name, rule.default_level)
