"""The pass plugin protocol and discovery.

A pass is any class with a ``name``, a one-line ``summary`` and a ``run`` method. Packages
register passes under the ``bricky.passes`` entry-point group, so a pass pack such as a future
``bricky-physics`` can be installed or removed without touching the core.
"""

from collections.abc import Iterable, Mapping, Sequence
from functools import cache
from importlib.metadata import entry_points
from types import MappingProxyType
from typing import ClassVar, Final, Protocol

from bricky.analysis import Context
from bricky.diagnostics import Diagnostic

ENTRY_POINT_GROUP: Final = "bricky.passes"


class Pass(Protocol):
    """A check that reads a model's shared analyses and reports diagnostics."""

    name: ClassVar[str]
    summary: ClassVar[str]

    def run(self, context: Context) -> Iterable[Diagnostic]:
        """Return the problems found in the model."""
        ...


@cache
def installed_passes() -> Mapping[str, type[Pass]]:
    """Discover every installed pass, by name; the result is computed once per process."""
    found: dict[str, type[Pass]] = {}
    for entry_point in entry_points(group=ENTRY_POINT_GROUP):
        found[entry_point.name] = entry_point.load()
    return MappingProxyType(dict(sorted(found.items())))


def run_passes(
    context: Context,
    names: Sequence[str],
    available: Mapping[str, type[Pass]],
) -> tuple[list[Diagnostic], list[str]]:
    """Run the named passes in order and return their diagnostics and the names not installed."""
    diagnostics: list[Diagnostic] = []
    missing: list[str] = []
    for name in names:
        pass_type = available.get(name)
        if pass_type is None:
            missing.append(name)
            continue
        diagnostics.extend(pass_type().run(context))
    return diagnostics, missing
