# Copyright 2026 Maxence Faldor
"""Checks: check a model file, and explain the rules a check applies."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import CliPositionalArg

from bricky.check import check_model
from bricky.diagnostics import Report, Rule
from bricky.errors import BrickyError
from bricky.model import Model
from bricky.passes import installed_rules, resolve_levels
from bricky.provenance import Provenance
from bricky.service.session import (
    ERROR_HELP,
    IGNORE_HELP,
    MAX_DIAGNOSTICS_HELP,
    WARN_HELP,
    Session,
    indent,
    read_model,
)
from bricky.settings import Level, Settings


class CheckRequest(BaseModel):
    """Check a model file and report diagnostics."""

    model: CliPositionalArg[Path] = Field(
        description="Path to a .bricky.json model file."
    )
    error: list[str] = Field(default_factory=list, description=ERROR_HELP)
    warn: list[str] = Field(default_factory=list, description=WARN_HELP)
    ignore: list[str] = Field(default_factory=list, description=IGNORE_HELP)
    max_diagnostics: int | None = Field(
        default=None, ge=1, description=MAX_DIAGNOSTICS_HELP
    )


async def check(request: CheckRequest, session: Session) -> Report:
    """Check a model file, naming script lines when its source map is current.

    Raises:
        BrickyError: If the file is missing or invalid, or a rule is unknown or given
            two levels.
    """
    rules = await asyncio.to_thread(
        rule_levels, request.error, request.warn, request.ignore, session.settings
    )
    model, provenance = await asyncio.to_thread(read_model, request.model)
    return await asyncio.to_thread(
        run_check,
        model,
        provenance=provenance,
        rules=rules,
        max_diagnostics=request.max_diagnostics,
        session=session,
    )


class ExplainRequest(BaseModel):
    """Explain rules: the exact condition each checks, its level and its pass."""

    rule: CliPositionalArg[str] = Field(
        default="",
        description="A rule such as 'floating-group'; every rule when omitted.",
    )


class RuleInfo(Rule):
    """A rule, the level the settings give it and the pass that checks it."""

    level: Level = Field(description="The level the settings give the rule.")
    pass_name: str = Field(description="Name of the pass that checks the rule.")


class ExplainResult(BaseModel):
    """Explanations of rules."""

    rules: tuple[RuleInfo, ...]

    def describe(self) -> str:
        """Return the explanations as text."""
        blocks = []
        for info in self.rules:
            default = (
                ""
                if info.level is info.default_level
                else f", by default {info.default_level}"
            )
            heading = f"{info.name} ({info.level}{default}, pass {info.pass_name})"
            blocks.append(heading + "\n" + indent(info.condition))
        return "\n\n".join(blocks)


async def explain(request: ExplainRequest, session: Session) -> ExplainResult:
    """Explain one rule, or all of them, at the levels the settings give them.

    Raises:
        BrickyError: If no installed pass checks the rule.
    """
    rules = await asyncio.to_thread(installed_rules)
    levels = await asyncio.to_thread(
        resolve_levels, ("settings", session.settings.rules)
    )
    wanted = request.rule.strip()
    if wanted and wanted not in rules:
        message = (
            f"no installed pass checks a rule named {wanted!r}; "
            f"known rules: {', '.join(rules)}"
        )
        raise BrickyError(message)
    chosen = [wanted] if wanted else list(rules)
    return ExplainResult(
        rules=tuple(
            RuleInfo(
                **rules[name][1].model_dump(),
                level=levels[name],
                pass_name=rules[name][0],
            )
            for name in chosen
        )
    )


def run_check(
    model: Model,
    *,
    provenance: Provenance | None,
    rules: dict[str, Level],
    max_diagnostics: int | None,
    session: Session,
) -> Report:
    """Check a model at the given levels, with the session's catalog and settings."""
    return check_model(
        model,
        rules=rules,
        max_diagnostics=max_diagnostics or session.settings.max_diagnostics,
        provenance=provenance,
        catalog=session.catalog,
        settings=session.settings,
    )


def rule_levels(
    error: Sequence[str],
    warn: Sequence[str],
    ignore: Sequence[str],
    settings: Settings,
) -> dict[str, Level]:
    """Return the levels that a command's options give rules, as ty's options do.

    The options and the settings are checked before the command does any work.

    Raises:
        BrickyError: If the options give one rule, or ``all``, two levels, or the
            options or the settings name a rule that no installed pass checks.
    """
    levels: dict[str, Level] = {}
    for level, names in (
        (Level.ERROR, error),
        (Level.WARN, warn),
        (Level.IGNORE, ignore),
    ):
        for name in names:
            if levels.setdefault(name, level) is not level:
                message = (
                    f"the options give {name!r} two levels: {levels[name]} and {level}"
                )
                raise BrickyError(message)
    resolve_levels(("settings", settings.rules), ("options", levels))
    return levels
