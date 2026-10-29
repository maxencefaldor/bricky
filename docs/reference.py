# Copyright 2026 Maxence Faldor
"""Write the reference pages that come from the code: commands, codes and settings.

Run from the repository root: ``uv run python docs/reference.py``. Every option's flag,
default and description come from the request models in :mod:`bricky.service`, the
single definition the command line and the MCP server share. Every code's title and rule
come from the installed passes, as ``bricky explain`` prints them, and every setting
comes from :class:`bricky.Settings`. The pages therefore match the tools exactly.
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
from bricky.passes.registry import installed_codes

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


CODES_INTRODUCTION: Final = """\
# Diagnostic codes

Each code names one fact a pass can state about a model, and `bricky explain` prints \
the same rule as this page.
"""

CODE_IMAGES: Final = {
    "E103": ("A brick sunk two plates below the ground", "underground.png"),
    "E201": ("Two bricks placed into the same space", "overlap.png"),
    "E202": (
        "A plate half a stud off the grid: the studs below push into it",
        "blocked.png",
    ),
    "E301": ("A brick held by nothing", "floating.png"),
}
"""The image beside each code that has one, with its description."""

_SENTENCE_END: Final = re.compile(r"(?<=[.:])\s+(?=[A-Z`(])")


def _anchor(code: str, title: str) -> str:
    """Return the anchor of a code's heading, such as ``e101-unknown-part``."""
    return f"{code} {title}".lower().replace(" ", "-")


def codes_page() -> str:
    """Return the page of diagnostic codes: a table, then each code's rule."""
    codes = sorted(installed_codes().items(), key=lambda item: int(item[0][1:]))
    lines = [
        CODES_INTRODUCTION,
        "| Code | Title | Pass |",
        "| --- | --- | --- |",
        *(
            f"| [{code}](#{_anchor(code, info.title)}) | {info.title} | {pass_name} |"
            for code, (pass_name, info) in codes
        ),
        "",
        "Codes that start with E are errors, and codes that start with W are warnings.",
    ]
    for code, (_, info) in codes:
        lines.extend(("", f"## {code} {info.title}", ""))
        lines.extend(_SENTENCE_END.split(info.rule))
        if code in CODE_IMAGES:
            description, image = CODE_IMAGES[code]
            lines.extend(("", f"![{description}](../images/{image})"))
    return "\n".join(lines) + "\n"


SETTINGS_INTRODUCTION: Final = """\
# Configuration

Settings tune every command.
Each setting comes from the first source that sets it: a command's option, a \
`BRICKY_*` environment variable, or the `[tool.bricky]` table of the `pyproject.toml` \
in the working directory.

| Setting | Environment variable | Default | Description |
| --- | --- | --- | --- |
"""

SETTINGS_EXAMPLE: Final = """\

A project that builds large models might raise the time limit and add a quick profile:

```toml title="pyproject.toml"
[tool.bricky]
build_timeout = 300
profiles = { quick = ["schema", "collision"] }
```
"""


def _setting_default(field: FieldInfo) -> str:
    """Return a setting's default as the page shows it."""
    value = field.get_default(call_default_factory=True, validated_data={})
    if value is None:
        return "unset"
    if isinstance(value, dict):
        return ", ".join(f"`{name}`" for name in value)
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
        REFERENCE / "codes.md": codes_page(),
        REFERENCE / "configuration.md": settings_page(),
    }
    for page, text in pages.items():
        page.write_text(text, encoding="utf-8")
        print(f"wrote {page}")


if __name__ == "__main__":
    main()
