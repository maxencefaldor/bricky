"""Diagnostics: what passes report, and how a report reads for agents and humans.

Every diagnostic has a stable code whose letter gives its severity (``E`` error, ``W`` warning,
``I`` info), names the elements involved and the region they occupy in agent units, and says
how to fix the problem.
"""

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, computed_field

from bricky.geometry import Box
from bricky.units import to_plates, to_studs


class Severity(StrEnum):
    """How bad a diagnostic is."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


_SEVERITY: Final = {"E": Severity.ERROR, "W": Severity.WARNING, "I": Severity.INFO}
_RANK: Final = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
_LISTED_ELEMENTS: Final = 8


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
    """One problem found by a pass, phrased so an agent can act on it."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(
        pattern=r"^[EWI]\d{3}$", description="Stable code; its letter gives the severity."
    )
    check: str = Field(description="Name of the pass that found the problem.")
    message: str = Field(description="What is wrong.")
    elements: tuple[str, ...] = Field(default=(), description="Ids of the elements involved.")
    region: Region | None = Field(default=None, description="Where, in studs, studs and plates.")
    help: str | None = Field(default=None, description="How to fix it.")

    @computed_field
    @property
    def severity(self) -> Severity:
        """Severity, read from the code's letter."""
        return _SEVERITY[self.code[0]]

    def sort_key(self) -> tuple[int, str, str]:
        """Order errors first, then by code, then by first element."""
        return (_RANK[self.severity], self.code, self.elements[0] if self.elements else "")


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
    elements: int = Field(description="Number of elements checked.")
    errors: int = Field(description="Errors found, including any omitted below.")
    warnings: int = Field(description="Warnings found, including any omitted below.")
    diagnostics: tuple[Diagnostic, ...] = Field(description="Diagnostics, most severe first.")
    omitted: int = Field(default=0, description="Diagnostics left out to respect the cap.")

    @computed_field
    @property
    def ok(self) -> bool:
        """Whether the model has no errors."""
        return self.errors == 0


def render_report(report: Report) -> str:
    """Render a report as compiler-style text."""
    blocks = [_render_diagnostic(d) for d in report.diagnostics]
    if report.omitted:
        blocks.append(f"... {report.omitted} more not shown; raise --max-diagnostics to see them")
    profile = f"profile {report.profile}" if report.profile else "explicit passes"
    passes = ", ".join(report.passes) or "none"
    summary = (
        f"checked {report.elements} elements with {profile} ({passes}): "
        f"{_plural(report.errors, 'error')}, {_plural(report.warnings, 'warning')}"
    )
    if report.missing:
        summary += f"\nnot installed, skipped: {', '.join(report.missing)}"
    blocks.append(summary)
    return "\n\n".join(blocks)


def _render_diagnostic(diagnostic: Diagnostic) -> str:
    lines = [f"{diagnostic.severity}[{diagnostic.code}]: {diagnostic.message}"]
    if diagnostic.region is not None:
        lines.append(f"  --> {diagnostic.region}")
    if diagnostic.elements:
        shown = ", ".join(diagnostic.elements[:_LISTED_ELEMENTS])
        hidden = len(diagnostic.elements) - _LISTED_ELEMENTS
        lines.append(f"   = elements: {shown}" + (f" and {hidden} more" if hidden > 0 else ""))
    if diagnostic.help:
        lines.append(f"   = help: {diagnostic.help}")
    return "\n".join(lines)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"
