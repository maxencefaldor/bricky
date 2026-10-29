# Copyright 2026 Maxence Faldor
"""Write the reference pages that come from the code: commands, rules and settings.

Run from the repository root: ``uv run python docs/reference.py``. Every option's flag,
default and description come from the request models in :mod:`bricky.service`, the
single definition the command line and the MCP server share. Every rule's level and
condition come from the installed passes, as ``bricky explain`` prints them, and every
setting comes from :class:`bricky.Settings`. The pages therefore match the tools
exactly.
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path
from typing import Final

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from bricky import Settings
from bricky.cli import Bricky, CatalogCommand
from bricky.passes.registry import installed_rules

REFERENCE: Final = Path(__file__).resolve().parent / "reference"
_URL: Final = re.compile(r"(https?://[^\s<>]+?)([.,;:]?(?:\s|$))")

INTRODUCTION: Final = """\
# Command line

The `bricky` command builds, checks and renders models from the shell.

Every command but `json-schema` takes `--output-format json` to print its result as \
JSON for programs; the default, `text`, is for people and agents.
The command `bricky --version` prints the version.
The exit status is 0 for success, 1 when the model has errors or `catalog verify` \
finds problems, and 2 for invalid arguments or a failed command.
Each command's options come from a request model in `bricky.service`, which the \
[MCP server](../agents/connect.md#mcp-server) shares, so a tool takes the same \
arguments as its command.
"""


def _positional(field: FieldInfo) -> bool:
    """Whether pydantic-settings marks the field as a positional argument."""
    return any(
        getattr(item, "__name__", "") == "_CliPositionalArg" for item in field.metadata
    )


def _flag(name: str, field: FieldInfo) -> str:
    if _positional(field):
        return name.upper()
    flag = "--" + name.rstrip("_").replace("_", "-")
    if field.annotation is bool:
        return f"{flag}`, `--no-{flag.removeprefix('--')}"
    return flag


def _default(field: FieldInfo) -> str:
    if field.default is PydanticUndefined and field.default_factory is None:
        return "required"
    value = field.get_default(call_default_factory=True)
    if value in (None, "", [], ()):
        return ""
    if isinstance(value, list | tuple):
        return ", ".join(f"`{getattr(item, 'value', item)}`" for item in value)
    return f"`{getattr(value, 'value', value)}`"


def _options(command: type[BaseModel]) -> list[str]:
    rows = ["| Option | Default | Description |", "| --- | --- | --- |"]
    for name, field in command.model_fields.items():
        description = escape(" ".join((field.description or "").split()), quote=False)
        description = _URL.sub(r"<\1>\2", description.replace("|", "\\|"))
        rows.append(f"| `{_flag(name, field)}` | {_default(field)} | {description} |")
    return rows


def _section(path: str, command: type[BaseModel], summary: str) -> list[str]:
    options = (
        _options(command) if command.model_fields else ["The command takes no options."]
    )
    return [
        f"## `bricky {path}`",
        "",
        summary.rstrip(".") + ".",
        "",
        *options,
        "",
    ]


def _subcommands(
    group: type[BaseModel], prefix: str
) -> list[tuple[str, type[BaseModel], str]]:
    found = []
    for name, field in group.model_fields.items():
        command = next(
            (
                item
                for item in getattr(field.annotation, "__args__", ())
                if isinstance(item, type)
            ),
            None,
        )
        if command is None or not issubclass(command, BaseModel):
            continue
        # The command line spells fields in kebab case: json_schema is json-schema.
        path = prefix + name.rstrip("_").replace("_", "-")
        if command is CatalogCommand:
            found.extend(_subcommands(command, path + " "))
        else:
            found.append((path, command, field.description or ""))
    return found


RULES_INTRODUCTION: Final = """\
# Rules

Each rule names one fact a check can state about a model, and `bricky explain` prints \
the same condition as this page.
A check reports each rule at its level: `error`, `warn` or `ignore`.
The default levels below hold until settings or options set others (see \
[Checks](../guide/checks.md#rules-and-levels)).
"""

RULE_IMAGES: Final = {
    "below-ground": ("A brick sunk two plates below the ground", "underground.png"),
    "overlap": ("Two bricks placed into the same space", "overlap.png"),
    "blocked-stud": (
        "A plate half a stud off the grid: the studs below push into it",
        "blocked.png",
    ),
    "floating-group": ("A brick held by nothing", "floating.png"),
}
"""The image beside each rule that has one, with its description."""

_SENTENCE_END: Final = re.compile(r"(?<=[.:])\s+(?=[A-Z`(])")


def rules_page() -> str:
    """Return the page of rules: a table, then each rule's condition."""
    rules = installed_rules()
    lines = [
        RULES_INTRODUCTION,
        "| Rule | Default level | Pass |",
        "| --- | --- | --- |",
        *(
            f"| [`{name}`](#{name}) | `{rule.default_level}` | {pass_name} |"
            for name, (pass_name, rule) in rules.items()
        ),
    ]
    for name, (_, rule) in rules.items():
        lines.extend(("", f"## {name}", ""))
        lines.extend(_SENTENCE_END.split(rule.condition))
        if name in RULE_IMAGES:
            description, image = RULE_IMAGES[name]
            lines.extend(("", f"![{description}](../images/{image})"))
    return "\n".join(lines) + "\n"


SETTINGS_INTRODUCTION: Final = """\
# Configuration

Settings tune every command.
Each setting comes from the first source that sets it: a command's option, a \
`BRICKY_*` environment variable, or the configuration file in the working directory.
That file is `bricky.toml` when there is one, and otherwise the `[tool.bricky]` table \
of `pyproject.toml`.
A `bricky.toml` replaces that table entirely, as `ty.toml` replaces `[tool.ty]`.

| Setting | Environment variable | Default | Description |
| --- | --- | --- | --- |
"""

SETTINGS_EXAMPLE: Final = """\

A project that builds large models might raise the time limit and make two stability \
rules errors:

```toml title="pyproject.toml"
[tool.bricky]
build_timeout = 300

[tool.bricky.rules]
unbalanced-group = "error"
overloaded-studs = "error"
```

The same settings in `bricky.toml` drop the `tool.bricky` prefix:

```toml title="bricky.toml"
build_timeout = 300

[rules]
unbalanced-group = "error"
overloaded-studs = "error"
```
"""


def _setting_default(field: FieldInfo) -> str:
    """Return a setting's default as the page shows it."""
    value = field.get_default(call_default_factory=True, validated_data={})
    if value is None or value == {}:
        return "unset"
    return f"`{value}`"


def settings_page() -> str:
    """Return the page of settings: where they come from, then one row each."""
    rows = [
        f"| `{name}` | `BRICKY_{name.upper()}` | {_setting_default(field)} | "
        f"{escape(field.description or '', quote=False)} |"
        for name, field in Settings.model_fields.items()
    ]
    return SETTINGS_INTRODUCTION + "\n".join(rows) + "\n" + SETTINGS_EXAMPLE


def main() -> None:
    """Write every page."""
    lines = [INTRODUCTION]
    for path, command, summary in _subcommands(Bricky, ""):
        lines.extend(_section(path, command, summary))
    REFERENCE.mkdir(parents=True, exist_ok=True)
    pages = {
        REFERENCE / "cli.md": "\n".join(lines).rstrip() + "\n",
        REFERENCE / "rules.md": rules_page(),
        REFERENCE / "configuration.md": settings_page(),
    }
    for page, text in pages.items():
        page.write_text(text, encoding="utf-8")
        print(f"wrote {page}")


if __name__ == "__main__":
    main()
