"""Run passes over a model and assemble a report."""

from collections.abc import Sequence

from bricky.analysis import Context
from bricky.catalog import Catalog, default_catalog
from bricky.diagnostics import Diagnostic, Report, Severity
from bricky.model import Model
from bricky.passes import installed_passes, run_passes
from bricky.settings import Settings


def check_model(  # noqa: PLR0913 - keyword-only options, one per concern
    model: Model,
    *,
    profile: str | None = None,
    passes: Sequence[str] | None = None,
    max_diagnostics: int | None = None,
    catalog: Catalog | None = None,
    settings: Settings | None = None,
) -> Report:
    """Check a model and return a report.

    Args:
        model: The model to check.
        profile: Profile to run; defaults to the configured profile, normally ``digital``.
        passes: Pass names to run instead of a profile. Names not installed are reported, not run.
        max_diagnostics: Cap on the diagnostics returned; counts still cover everything found.
        catalog: Catalog to resolve parts against; the shipped catalog by default.
        settings: Settings to read profiles from; loaded from the environment by default.

    Raises:
        BrickyError: If the profile is unknown.
    """
    profile_name, names = (settings or Settings()).resolve_passes(profile, passes)
    context = Context(model, catalog or default_catalog())
    diagnostics, missing = run_passes(context, names, installed_passes())
    diagnostics.sort(key=Diagnostic.sort_key)
    shown = diagnostics if max_diagnostics is None else diagnostics[:max_diagnostics]
    return Report(
        model=model.name,
        profile=profile_name,
        passes=tuple(name for name in names if name not in missing),
        missing=tuple(missing),
        elements=len(context.world.placed) + len(context.world.unresolved),
        errors=sum(d.severity is Severity.ERROR for d in diagnostics),
        warnings=sum(d.severity is Severity.WARNING for d in diagnostics),
        diagnostics=tuple(shown),
        omitted=len(diagnostics) - len(shown),
    )
