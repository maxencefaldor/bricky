# Copyright 2026 Maxence Faldor
"""Run the passes over a model, at each rule's level, and assemble a report."""

from __future__ import annotations

from collections.abc import Mapping

from bricky.analysis import Context
from bricky.catalog import Catalog, default_catalog
from bricky.diagnostics import Diagnostic, ElementInfo, Report
from bricky.model import Model
from bricky.passes import resolve_levels, run_passes
from bricky.provenance import Provenance
from bricky.settings import Level, Settings


def check_model(  # noqa: PLR0913 - keyword-only options, one per concern
    model: Model,
    *,
    rules: Mapping[str, Level] | None = None,
    max_diagnostics: int | None = None,
    provenance: Provenance | None = None,
    catalog: Catalog | None = None,
    settings: Settings | None = None,
) -> Report:
    """Check a model and return a report.

    Args:
        model: The model to check.
        rules: Levels by rule name, or ``all`` for every rule, over those the settings
            give: error, warn or ignore.
        max_diagnostics: Maximum number of diagnostics in the report; the error and
            warning counts cover every diagnostic found.
        provenance: Where the build script placed each element, so the report names
            script lines; see :meth:`bricky.ModelBuilder.provenance`.
        catalog: Catalog to resolve parts and colors against;
            :func:`bricky.default_catalog` by default.
        settings: Settings to read rule levels and passes' options from; read from the
            environment and the configuration file by default.

    Raises:
        BrickyError: If the settings or ``rules`` name a rule no installed pass checks.
    """
    settings = settings or Settings()
    levels = resolve_levels(settings.rules, rules or {})
    context = Context(model, catalog or default_catalog(), settings)
    diagnostics = run_passes(context, levels)
    order = {name: i for i, name in enumerate(levels)}

    def rank(diagnostic: Diagnostic) -> tuple[bool, int, str]:
        first = diagnostic.elements[0] if diagnostic.elements else ""
        is_warning = levels[diagnostic.rule] is not Level.ERROR
        return is_warning, order[diagnostic.rule], first

    diagnostics.sort(key=rank)
    shown = diagnostics if max_diagnostics is None else diagnostics[:max_diagnostics]
    named = {uid for diagnostic in shown for uid in diagnostic.elements}
    errors = sum(levels[diagnostic.rule] is Level.ERROR for diagnostic in diagnostics)
    return Report(
        model=model.name,
        rules=levels,
        element_count=len(context.world.elements) + len(context.world.unknown),
        errors=errors,
        warnings=len(diagnostics) - errors,
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
