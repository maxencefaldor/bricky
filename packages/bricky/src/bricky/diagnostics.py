# Copyright 2026 Maxence Faldor
"""Diagnostics: the facts that passes report, and the reports that collect them.

A rule is one kind of fact a pass checks, such as ``floating-group``. It has a default
level and an exact condition, which ``bricky explain`` prints. A diagnostic states one
such fact about the model: what is wrong, the elements involved and their region. A
diagnostic never prescribes a fix: the agent decides what to change.

A check reports each rule at a level: error, warn or ignore. A report gives the level of
every rule. It also says what each element a diagnostic names is, and which line of the
build script placed it.
"""

from __future__ import annotations

from collections import Counter
from typing import Final, override

from pydantic import BaseModel, ConfigDict, Field, computed_field

from bricky.geometry import Box
from bricky.provenance import Frame, InstanceStep, Source
from bricky.settings import RULE_NAME, Level
from bricky.units import to_plates, to_studs

_LISTED_ELEMENTS: Final = 6
_LISTED_SITES: Final = 10
_LISTED_IGNORED: Final = 3


class Rule(BaseModel):
    """A fact a pass checks: its name, its default level and the exact condition."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(
        pattern=RULE_NAME,
        description="Lowercase words joined by hyphens, such as 'floating-group'.",
    )
    default_level: Level = Field(
        description="The level checks report it at unless settings or options set one."
    )
    condition: str = Field(
        description="The exact condition the pass checks, in plain words."
    )


class Region(BaseModel):
    """An axis-aligned region: x and y in studs, z in plates."""

    model_config = ConfigDict(frozen=True)

    x: tuple[float, float]
    y: tuple[float, float]
    z: tuple[float, float]

    @classmethod
    def of(cls, box: Box) -> Region:
        """Convert a box in base units to a region in studs and plates."""
        return cls(
            x=(to_studs(box.min.x), to_studs(box.max.x)),
            y=(to_studs(box.min.y), to_studs(box.max.y)),
            z=(to_plates(box.min.z), to_plates(box.max.z)),
        )

    @override
    def __str__(self) -> str:
        """The region as text, such as ``x 1..2  y 0..4  z 0..3``."""
        return "  ".join(
            f"{axis} {low:g}..{high:g}"
            for axis, (low, high) in zip("xyz", (self.x, self.y, self.z), strict=True)
        )


class Diagnostic(BaseModel):
    """One fact about the model, found by a pass under one rule."""

    model_config = ConfigDict(frozen=True)

    rule: str = Field(
        pattern=RULE_NAME, description="Name of the rule whose fact it states."
    )
    message: str = Field(description="What is wrong, as a statement of fact.")
    elements: tuple[str, ...] = Field(
        default=(), description="Uids of the elements involved."
    )
    region: Region | None = Field(
        default=None, description="Where, in studs, studs and plates."
    )


class ElementInfo(BaseModel):
    """What an element named by a diagnostic is, and which script line placed it."""

    model_config = ConfigDict(frozen=True)

    part: str = Field(description="Part id.")
    part_name: str | None = Field(
        description="Part name; null when the catalog cannot place it."
    )
    color: int = Field(description="Color id.")
    color_name: str | None = Field(description="Color name; null for an unknown color.")
    component: str | None = Field(
        default=None, description="Component defining the element."
    )
    source: Source | None = Field(
        default=None,
        description="Script frames that placed it, innermost first; null if unknown.",
    )
    via: tuple[InstanceStep, ...] = Field(
        default=(),
        description="Instances that copied it into the model, outermost first.",
    )


class Report(BaseModel):
    """The result of a check: a model's diagnostics and what each named element is."""

    model: str = Field(description="Name of the model checked.")
    rules: dict[str, Level] = Field(
        description="The level of every installed rule in this check, by name."
    )
    element_count: int = Field(description="Number of elements checked.")
    errors: int = Field(description="Number of errors found, omitted ones included.")
    warnings: int = Field(
        description="Number of warnings found, omitted ones included."
    )
    counts: dict[str, int] = Field(
        default_factory=dict,
        description="Number of diagnostics found under each rule that has some, "
        "omitted ones included.",
    )
    diagnostics: tuple[Diagnostic, ...] = Field(
        description="Diagnostics, errors first, then by rule and first element."
    )
    omitted: int = Field(
        default=0, description="Number of diagnostics left out by the cap."
    )
    elements: dict[str, ElementInfo] = Field(
        default_factory=dict,
        description="Every element named by the diagnostics, by uid.",
    )

    @computed_field
    @property
    def ok(self) -> bool:
        """Whether the model is free of errors."""
        return self.errors == 0

    def is_error(self, diagnostic: Diagnostic) -> bool:
        """Whether the check reported a diagnostic as an error, not as a warning."""
        return self.rules[diagnostic.rule] is Level.ERROR


def format_report(report: Report) -> str:
    """Format a report as compiler-style text."""
    blocks = [
        _format_diagnostic(diagnostic, report) for diagnostic in report.diagnostics
    ]
    if report.omitted:
        blocks.append(f"... {_plural(report.omitted, 'more diagnostic')} not shown")
    sites = _sites(report)
    if sites:
        lines = ["by source line:"]
        lines += [
            f"  {site}: {_plural(count, 'diagnostic')}"
            for site, count in sites.most_common(_LISTED_SITES)
        ]
        if len(sites) > _LISTED_SITES:
            more = _plural(len(sites) - _LISTED_SITES, "more line")
            lines.append(f"  ... and {more}")
        blocks.append("\n".join(lines))
    ignored = [name for name, level in report.rules.items() if level is Level.IGNORE]
    rules = _plural(len(report.rules) - len(ignored), "rule")
    if len(ignored) > _LISTED_IGNORED:
        rules += f" ({len(ignored)} ignored)"
    elif ignored:
        rules += f" ({', '.join(ignored)} ignored)"
    blocks.append(
        f"checked {_plural(report.element_count, 'element')} against {rules}: "
        f"{_plural(report.errors, 'error')}, {_plural(report.warnings, 'warning')}"
    )
    return "\n\n".join(blocks)


def describe_element(uid: str, info: ElementInfo | None) -> str:
    """Return one line that says what an element is and which script line placed it."""
    if info is None:
        return uid
    part = (
        f"unknown part {info.part}"
        if info.part_name is None
        else f"{info.part_name} ({info.part})"
    )
    color = info.color_name or f"unknown color {info.color}"
    text = f"{uid}: {part}, {color}"
    if info.source is not None:
        text += f", {info.source.site}"
    if info.via:
        step = info.via[-1]
        placed = f" placed at {step.source.site}" if step.source is not None else ""
        text += f", instance {step.id} of component {step.component}{placed}"
    return text


def _format_diagnostic(diagnostic: Diagnostic, report: Report) -> str:
    kind = "error" if report.is_error(diagnostic) else "warning"
    lines = [f"{kind}[{diagnostic.rule}]: {diagnostic.message}"]
    if diagnostic.region is not None:
        lines.append(f"  --> {diagnostic.region}")
    lines.extend(
        f"   = {describe_element(uid, report.elements.get(uid))}"
        for uid in diagnostic.elements[:_LISTED_ELEMENTS]
    )
    hidden = len(diagnostic.elements) - _LISTED_ELEMENTS
    if hidden > 0:
        lines.append(f"   = and {_plural(hidden, 'more element')}")
    return "\n".join(lines)


def _sites(report: Report) -> Counter[Frame]:
    """Count, per script line, the listed diagnostics naming an element it placed.

    Lines count in the order diagnostics first name them, so ties list the same way on
    every run.
    """
    counts: Counter[Frame] = Counter()
    for diagnostic in report.diagnostics:
        sites = dict.fromkeys(
            info.source.site
            for uid in diagnostic.elements
            if (info := report.elements.get(uid)) is not None
            and info.source is not None
        )
        counts.update(sites.keys())
    return counts


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"
