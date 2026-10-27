"""Diagnostics: the facts passes report, and how a report reads for agents and humans.

A diagnostic states a fact about the model: a stable code whose letter gives its severity (``E``
error, ``W`` warning, ``I`` info), what is wrong, the elements involved and the region they occupy
in agent units. It never prescribes a fix; deciding what to change is the agent's job. Each code's
exact rule is documented by the pass that reports it (see ``bricky explain``).

A report adds what the model and its source map know about each element a diagnostic names: the
part, the colour and the build-script line that placed it.
"""

from collections import Counter
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, computed_field

from bricky.geometry import Box
from bricky.provenance import Frame, InstanceStep, Source
from bricky.units import to_plates, to_studs


class Severity(StrEnum):
    """How bad a diagnostic is."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


_SEVERITY: Final = {"E": Severity.ERROR, "W": Severity.WARNING, "I": Severity.INFO}
_RANK: Final = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
_CODE_PATTERN: Final = r"^[EWI]\d{3}$"
_LISTED_ELEMENTS: Final = 6
_LISTED_SITES: Final = 10


class Code(BaseModel):
    """A diagnostic code, what it is called, and the exact rule behind it."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(pattern=_CODE_PATTERN, description="Stable code; its letter is the severity.")
    title: str = Field(description="Short name, such as 'Floating group'.")
    rule: str = Field(description="The exact condition the pass checks, in plain words.")

    @computed_field
    @property
    def severity(self) -> Severity:
        """Severity, read from the code's letter."""
        return _SEVERITY[self.code[0]]


class Region(BaseModel):
    """An axis-aligned region in agent units: x and y in studs, z in plates."""

    model_config = ConfigDict(frozen=True)

    x: tuple[float, float]
    y: tuple[float, float]
    z: tuple[float, float]

    @classmethod
    def of(cls, box: Box) -> Region:
        """Convert a box in base units to a region in agent units."""
        return cls(
            x=(to_studs(box.lo.x), to_studs(box.hi.x)),
            y=(to_studs(box.lo.y), to_studs(box.hi.y)),
            z=(to_plates(box.lo.z), to_plates(box.hi.z)),
        )

    def __str__(self) -> str:
        return "  ".join(
            f"{axis} {lo:g}..{hi:g}"
            for axis, (lo, hi) in zip("xyz", (self.x, self.y, self.z), strict=True)
        )


class Diagnostic(BaseModel):
    """One fact about the model, found by a pass."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(pattern=_CODE_PATTERN, description="Stable code; its letter is the severity.")
    check: str = Field(description="Name of the pass that found it.")
    message: str = Field(description="What is wrong, as a statement of fact.")
    elements: tuple[str, ...] = Field(default=(), description="Uids of the elements involved.")
    region: Region | None = Field(default=None, description="Where, in studs, studs and plates.")

    @computed_field
    @property
    def severity(self) -> Severity:
        """Severity, read from the code's letter."""
        return _SEVERITY[self.code[0]]

    def sort_key(self) -> tuple[int, str, str]:
        """Order errors first, then by code, then by first element."""
        return (_RANK[self.severity], self.code, self.elements[0] if self.elements else "")


class ElementInfo(BaseModel):
    """What an element named by a diagnostic is, and where the build script placed it."""

    model_config = ConfigDict(frozen=True)

    part: str = Field(description="BrickLink item number.")
    part_name: str | None = Field(description="BrickLink item name; null for unknown parts.")
    color: int = Field(description="BrickLink colour id.")
    color_name: str | None = Field(description="BrickLink colour name; null for unknown colours.")
    component: str | None = Field(default=None, description="Component defining the element.")
    source: Source | None = Field(
        default=None, description="Script stack that placed it, innermost first; null if unknown."
    )
    via: tuple[InstanceStep, ...] = Field(
        default=(), description="Instances that copied it into the model, outermost first."
    )


class Report(BaseModel):
    """The result of checking one model."""

    model: str = Field(description="Name of the model checked.")
    profile: str | None = Field(
        description="Profile used, or null when passes were named explicitly."
    )
    passes: tuple[str, ...] = Field(description="Passes that ran.")
    missing: tuple[str, ...] = Field(
        default=(), description="Requested passes that are not installed."
    )
    element_count: int = Field(description="Number of elements checked.")
    errors: int = Field(description="Errors found, including any omitted below.")
    warnings: int = Field(description="Warnings found, including any omitted below.")
    diagnostics: tuple[Diagnostic, ...] = Field(description="Diagnostics, most severe first.")
    omitted: int = Field(default=0, description="Diagnostics left out to respect the cap.")
    elements: dict[str, ElementInfo] = Field(
        default_factory=dict, description="Every element named by the diagnostics, by uid."
    )

    @computed_field
    @property
    def ok(self) -> bool:
        """Whether the model has no errors."""
        return self.errors == 0


def render_report(report: Report) -> str:
    """Render a report as compiler-style text."""
    blocks = [_render_diagnostic(d, report.elements) for d in report.diagnostics]
    if report.omitted:
        blocks.append(f"... {report.omitted} more not shown; raise --max-diagnostics to see them")
    sites = _sites(report)
    if sites:
        lines = ["by source line:"]
        lines += [
            f"  {site}: {_plural(count, 'diagnostic')}"
            for site, count in sites.most_common(_LISTED_SITES)
        ]
        if len(sites) > _LISTED_SITES:
            lines.append(f"  ... and {len(sites) - _LISTED_SITES} more lines")
        blocks.append("\n".join(lines))
    profile = f"profile {report.profile}" if report.profile else "explicit passes"
    passes = ", ".join(report.passes) or "none"
    summary = (
        f"checked {report.element_count} elements with {profile} ({passes}): "
        f"{_plural(report.errors, 'error')}, {_plural(report.warnings, 'warning')}"
    )
    if report.missing:
        summary += f"\nnot installed, skipped: {', '.join(report.missing)}"
    blocks.append(summary)
    return "\n\n".join(blocks)


def describe_element(uid: str, info: ElementInfo | None) -> str:
    """One line saying what an element is and which script line placed it."""
    if info is None:
        return uid
    part = f"{info.part_name} ({info.part})" if info.part_name else f"unknown part {info.part}"
    color = info.color_name or f"unknown colour {info.color}"
    text = f"{uid}: {part}, {color}"
    if info.source is not None:
        text += f", {info.source.site}"
    if info.via:
        step = info.via[-1]
        placed = f" placed at {step.source.site}" if step.source is not None else ""
        text += f", copy {step.id} of component {step.component}{placed}"
    return text


def _render_diagnostic(diagnostic: Diagnostic, elements: dict[str, ElementInfo]) -> str:
    lines = [f"{diagnostic.severity}[{diagnostic.code}]: {diagnostic.message}"]
    if diagnostic.region is not None:
        lines.append(f"  --> {diagnostic.region}")
    lines.extend(
        f"   = {describe_element(uid, elements.get(uid))}"
        for uid in diagnostic.elements[:_LISTED_ELEMENTS]
    )
    hidden = len(diagnostic.elements) - _LISTED_ELEMENTS
    if hidden > 0:
        lines.append(f"   = and {_plural(hidden, 'more element')}")
    return "\n".join(lines)


def _sites(report: Report) -> Counter[Frame]:
    """Count the diagnostics shown that name an element placed at each script line."""
    counts: Counter[Frame] = Counter()
    for diagnostic in report.diagnostics:
        sites = {
            info.source.site
            for uid in diagnostic.elements
            if (info := report.elements.get(uid)) is not None and info.source is not None
        }
        counts.update(sites)
    return counts


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"
