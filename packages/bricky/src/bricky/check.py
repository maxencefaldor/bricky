# Copyright 2026 Maxence Faldor
"""Run passes over a model and assemble a report."""

from __future__ import annotations

from collections.abc import Sequence

from bricky.analysis import Context
from bricky.catalog import Catalog, default_catalog
from bricky.diagnostics import Diagnostic, ElementInfo, Report, Severity
from bricky.errors import BrickyError
from bricky.model import Model
from bricky.passes import installed_passes, run_passes
from bricky.provenance import Provenance
from bricky.settings import Settings


def check_model(  # noqa: PLR0913 - keyword-only options, one per concern
    model: Model,
    *,
    profile: str | None = None,
    passes: Sequence[str] | None = None,
    max_diagnostics: int | None = None,
    provenance: Provenance | None = None,
    catalog: Catalog | None = None,
    settings: Settings | None = None,
) -> Report:
    """Check a model and return a report.

    Args:
        model: The model to check.
        profile: Profile to run; the configured profile, normally ``digital``, by
            default.
        passes: Pass names to run instead of a profile; each must be installed. A
            profile may name passes that are not installed, and the report lists them.
        max_diagnostics: Maximum number of diagnostics in the report; the error and
            warning counts cover every diagnostic found.
        provenance: Where the build script placed each element, so the report names
            script lines; see :meth:`bricky.ModelBuilder.provenance`.
        catalog: Catalog to resolve parts and colors against;
            :func:`bricky.default_catalog` by default.
        settings: Settings to read profiles and passes' options from; read from the
            environment and ``pyproject.toml`` by default.

    Raises:
        BrickyError: If the profile is unknown, or ``passes`` names a pass that is not
            installed.
    """
    settings = settings or Settings()
    profile_name, names = settings.resolve_passes(profile, passes)
    available = installed_passes()
    if passes is not None and (
        unknown := [name for name in names if name not in available]
    ):
        message = (
            f"no installed pass is named {', '.join(map(repr, unknown))}; "
            f"installed passes: {', '.join(available)}"
        )
        raise BrickyError(message)
    context = Context(model, catalog or default_catalog(), settings)
    diagnostics, missing = run_passes(context, names, available)
    diagnostics.sort(key=Diagnostic.sort_key)
    shown = diagnostics if max_diagnostics is None else diagnostics[:max_diagnostics]
    named = {uid for diagnostic in shown for uid in diagnostic.elements}
    return Report(
        model=model.name,
        profile=profile_name,
        passes=tuple(name for name in names if name not in missing),
        missing=tuple(missing),
        element_count=len(context.world.elements) + len(context.world.unknown),
        errors=sum(diagnostic.severity is Severity.ERROR for diagnostic in diagnostics),
        warnings=sum(
            diagnostic.severity is Severity.WARNING for diagnostic in diagnostics
        ),
        diagnostics=tuple(shown),
        omitted=len(diagnostics) - len(shown),
        elements=_describe(context, named, provenance),
    )


def _describe(
    context: Context, uids: set[str], provenance: Provenance | None
) -> dict[str, ElementInfo]:
    """Describe each named element: part, color and the script lines that placed it."""
    catalog = context.catalog
    found: dict[str, ElementInfo] = {}
    for element in context.world.elements:
        if element.uid in uids:
            color = catalog.color(element.color)
            found[element.uid] = ElementInfo(
                part=element.part.id,
                part_name=element.part.name,
                color=element.color,
                color_name=color.name if color else None,
            )
    for unknown in context.world.unknown:
        if unknown.uid in uids:
            color = catalog.color(unknown.color)
            entry = catalog.entry(unknown.part)
            found[unknown.uid] = ElementInfo(
                part=unknown.part,
                part_name=entry.name if entry else None,
                color=unknown.color,
                color_name=color.name if color else None,
            )
    if provenance is not None:
        for uid, info in found.items():
            trace = provenance.trace(context.model, uid)
            found[uid] = info.model_copy(
                update={
                    "component": trace.component,
                    "source": trace.source,
                    "via": trace.via,
                }
            )
    return dict(sorted(found.items()))
