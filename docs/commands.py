# Copyright 2026 Maxence Faldor
"""Write the command-line reference from the commands themselves.

Run from the repository root: ``uv run python docs/commands.py``. Every option's flag,
default and description come from the request models in :mod:`bricky.service`, the
single definition the command line and the MCP server share, so the page matches the
tools exactly.
"""

import re
from html import escape
from pathlib import Path
from typing import Final

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from bricky.cli import Bricky, CatalogCommand

PAGE: Final = Path(__file__).resolve().parent / "reference" / "cli.md"
_URL: Final = re.compile(r"(https?://[^\s<>]+?)([.,;:]?(?:\s|$))")

INTRODUCTION: Final = """\
# Command line

The `bricky` command builds, checks and renders models from the shell.

Every command takes `--output-format json` to print its result as JSON for programs; \
the default, `text`, is for people and agents.
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
    return [
        f"## `bricky {path}`",
        "",
        summary.rstrip(".") + ".",
        "",
        *_options(command),
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


def main() -> None:
    """Write the page."""
    lines = [INTRODUCTION]
    for path, command, summary in _subcommands(Bricky, ""):
        lines.extend(_section(path, command, summary))
    PAGE.parent.mkdir(parents=True, exist_ok=True)
    PAGE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"wrote {PAGE}")


if __name__ == "__main__":
    main()
