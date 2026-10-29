# Copyright 2026 Maxence Faldor
"""The pass plugin protocol, discovery, and the levels that checks report rules at.

A pass is any class with a ``name``, a one-line ``summary``, the ``rules`` it checks and
a ``run`` method. Packages register passes under the ``bricky.passes`` entry-point
group, so a pass pack installs and uninstalls without changes to the core. People
configure rules, never passes: a check runs each pass that checks a rule not ignored.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from functools import cache
from importlib.metadata import entry_points
from types import MappingProxyType
from typing import ClassVar, Final, Protocol

from bricky.analysis import Context
from bricky.diagnostics import Diagnostic, Rule
from bricky.errors import BrickyError
from bricky.settings import ALL, Level

ENTRY_POINT_GROUP: Final = "bricky.passes"
"""The entry-point group that packages register passes under."""

BUILT_IN: Final = ("schema", "collision", "connectivity", "stability")
"""bricky's own passes, in the order checks run them; other passes follow, by name."""


class Pass(Protocol):
    """A check that reads a model's shared analyses and reports facts as diagnostics."""

    name: ClassVar[str]
    """The pass's name, which ``bricky explain`` gives beside each of its rules."""

    summary: ClassVar[str]
    """One line on what the pass checks."""

    rules: ClassVar[tuple[Rule, ...]]
    """Every rule the pass checks, with its default level and exact condition."""

    def run(self, context: Context) -> Iterable[Diagnostic]:
        """Return the diagnostics found in the model."""
        ...


@cache
def installed_passes() -> Mapping[str, type[Pass]]:
    """Return every installed pass by name, discovered once per process.

    bricky's own passes come first, in the order of :data:`BUILT_IN`.
    """
    found: dict[str, type[Pass]] = {
        entry_point.name: entry_point.load()
        for entry_point in entry_points(group=ENTRY_POINT_GROUP)
    }
    order = sorted(
        found,
        key=lambda name: (
            BUILT_IN.index(name) if name in BUILT_IN else len(BUILT_IN),
            name,
        ),
    )
    return MappingProxyType({name: found[name] for name in order})


@cache
def installed_rules() -> Mapping[str, tuple[str, Rule]]:
    """Return every rule an installed pass checks, with the name of that pass.

    The rules come in the order checks report them: by pass, then as each pass lists
    them.

    Raises:
        BrickyError: If two installed passes claim the same rule.
    """
    found: dict[str, tuple[str, Rule]] = {}
    for name, pass_type in installed_passes().items():
        for rule in pass_type.rules:
            if rule.name in found:
                other = found[rule.name][0]
                message = f"passes {other!r} and {name!r} both check rule {rule.name}"
                raise BrickyError(message)
            found[rule.name] = (name, rule)
    return MappingProxyType(found)


def resolve_levels(*layers: Mapping[str, Level]) -> dict[str, Level]:
    """Return the level of every installed rule, in the order checks report them.

    Each rule starts at its default level. Each layer then applies in turn, such as the
    settings and then a command's options: ``all`` sets every rule, and a rule's own
    entry overrides it.

    Raises:
        BrickyError: If a layer names a rule that no installed pass checks.
    """
    rules = installed_rules()
    levels = {name: rule.default_level for name, (_, rule) in rules.items()}
    for layer in layers:
        if unknown := sorted(set(layer) - set(levels) - {ALL}):
            message = (
                f"no installed pass checks {_listed(unknown)}; "
                f"known rules: {', '.join(rules)}"
            )
            raise BrickyError(message)
        if ALL in layer:
            levels = dict.fromkeys(levels, Level(layer[ALL]))
        levels.update(
            {name: Level(level) for name, level in layer.items() if name != ALL}
        )
    return levels


def run_passes(context: Context, levels: Mapping[str, Level]) -> list[Diagnostic]:
    """Run every pass that checks a rule not ignored, and keep those rules' diagnostics.

    Raises:
        BrickyError: If a pass reports a rule it does not list.
    """
    diagnostics: list[Diagnostic] = []
    for name, pass_type in installed_passes().items():
        listed = {rule.name for rule in pass_type.rules}
        if all(levels[rule] is Level.IGNORE for rule in listed):
            continue
        for diagnostic in pass_type().run(context):
            if diagnostic.rule not in listed:
                message = (
                    f"pass {name!r} reports rule {diagnostic.rule!r}, "
                    "which its rules do not list"
                )
                raise BrickyError(message)
            if levels[diagnostic.rule] is not Level.IGNORE:
                diagnostics.append(diagnostic)
    return diagnostics


def _listed(names: list[str]) -> str:
    quoted = ", ".join(repr(name) for name in names)
    return f"a rule named {quoted}" if len(names) == 1 else f"rules named {quoted}"
