# Copyright 2026 Maxence Faldor
"""The ``bricky`` command line.

Each subcommand extends a request model from :mod:`bricky.service` with an output
format. The command line therefore accepts exactly what the MCP tools accept and prints
the text they return.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Final, Literal, NoReturn, get_args, get_origin, override

from pydantic import BaseModel, Field, ValidationError
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    CliApp,
    CliSettingsSource,
    CliSubCommand,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from bricky import __version__, service
from bricky.diagnostics import Report, format_report
from bricky.errors import BrickyError
from bricky.files import model_schema


class _Output(BaseModel):
    output_format: Literal["text", "json"] = Field(
        default="text", description="'text' for people and agents, 'json' for programs."
    )

    def emit(self, result: BaseModel, text: str) -> None:
        """Print a result in the requested format."""
        print(
            result.model_dump_json(indent=2) if self.output_format == "json" else text
        )


def _fail_on_errors(report: Report | None) -> None:
    if report is not None and not report.ok:
        raise SystemExit(1)


class BuildCommand(service.BuildRequest, _Output):
    """Run a build script, save its model, check it and render it."""

    async def cli_cmd(self) -> None:
        """Run the command."""
        async with service.Session() as session:
            result = await service.build(self, session)
        self.emit(result, result.describe())
        if result.render_error is not None:
            raise SystemExit(2)
        _fail_on_errors(result.report)


class CheckCommand(service.CheckRequest, _Output):
    """Check a model file and report diagnostics."""

    async def cli_cmd(self) -> None:
        """Run the command."""
        async with service.Session() as session:
            report = await service.check(self, session)
        self.emit(report, format_report(report))
        _fail_on_errors(report)


class RenderCommand(service.RenderRequest, _Output):
    """Render images of a model file."""

    async def cli_cmd(self) -> None:
        """Run the command."""
        async with service.Session() as session:
            result = await service.render(self, session)
        self.emit(result, result.describe())


class ExportCommand(service.ExportRequest, _Output):
    """Export a model file for another tool, such as a BrickLink Wanted List."""

    async def cli_cmd(self) -> None:
        """Run the command."""
        async with service.Session() as session:
            result = await service.export(self, session)
        self.emit(result, result.describe())


class InstructionsCommand(service.InstructionsRequest, _Output):
    """Write building instructions: a page that shows a model's steps in 3D."""

    async def cli_cmd(self) -> None:
        """Run the command."""
        async with service.Session() as session:
            result = await service.instructions(self, session)
        self.emit(result, result.describe())


class PartsCommand(service.PartsRequest, _Output):
    """Search the parts catalog."""

    async def cli_cmd(self) -> None:
        """Run the command."""
        async with service.Session() as session:
            result = await service.parts(self, session)
        self.emit(result, result.describe())


class ColorsCommand(service.ColorsRequest, _Output):
    """Search the catalog's colors."""

    async def cli_cmd(self) -> None:
        """Run the command."""
        async with service.Session() as session:
            result = await service.colors(self, session)
        self.emit(result, result.describe())


class ExplainCommand(service.ExplainRequest, _Output):
    """Explain rules: the exact condition each checks, its level and its pass."""

    async def cli_cmd(self) -> None:
        """Run the command."""
        async with service.Session() as session:
            result = await service.explain(self, session)
        self.emit(result, result.describe())


class CatalogImportCommand(service.CatalogImportRequest, _Output):
    """Import the catalog: BrickLink parts and colors, shapes from names and LDraw."""

    async def cli_cmd(self) -> None:
        """Run the command and print its progress to standard error."""
        async with service.Session() as session:
            result = await service.catalog_import(self, session, _progress)
        self.emit(result, result.describe())


def _progress(done: int, total: int) -> None:
    if done == total or done % 1000 == 0:
        end = "\n" if done == total else ""
        print(
            f"\rlooked at {done:,} of {total:,} parts",
            end=end,
            file=sys.stderr,
            flush=True,
        )


class CatalogStatusCommand(service.CatalogStatusRequest, _Output):
    """Say which catalog bricky uses and what is in it."""

    async def cli_cmd(self) -> None:
        """Run the command."""
        async with service.Session() as session:
            result = await service.catalog_status(self, session)
        self.emit(result, result.describe())


class CatalogShowCommand(service.CatalogShowRequest, _Output):
    """Show everything the catalog knows about one part."""

    async def cli_cmd(self) -> None:
        """Run the command."""
        async with service.Session() as session:
            result = await service.catalog_show(self, session)
        self.emit(result, result.describe())


class CatalogVerifyCommand(service.CatalogVerifyRequest, _Output):
    """Generate every shaped part's geometry and check it."""

    async def cli_cmd(self) -> None:
        """Run the command; exit with status 1 when a part has a problem."""
        async with service.Session() as session:
            result = await service.catalog_verify(self, session)
        self.emit(result, result.describe())
        if result.problems:
            raise SystemExit(1)


class CatalogCommand(BaseModel):
    """Import the catalog of parts and colors, and inspect it."""

    import_: CliSubCommand[CatalogImportCommand] = Field(
        alias="import",
        description="Import parts and colors from BrickLink, shapes from LDraw.",
    )
    status: CliSubCommand[CatalogStatusCommand] = Field(
        description="Say which catalog bricky uses and what is in it."
    )
    show: CliSubCommand[CatalogShowCommand] = Field(description="Show one part.")
    verify: CliSubCommand[CatalogVerifyCommand] = Field(
        description="Check every shaped part's geometry."
    )

    def cli_cmd(self) -> None:
        """Run the chosen subcommand."""
        CliApp.run_subcommand(self)


class SchemaCommand(BaseModel):
    """Print the JSON Schema of the model file format."""

    def cli_cmd(self) -> None:
        """Run the command."""
        print(json.dumps(model_schema(), indent=2))


class Bricky(BaseSettings):
    """Build, check and render LEGO® models written as Python build scripts."""

    model_config = SettingsConfigDict(
        cli_prog_name="bricky",
        cli_kebab_case=True,
        cli_implicit_flags=True,
        cli_hide_none_type=True,
        cli_avoid_json=True,
        cli_enforce_required=True,
    )

    build: CliSubCommand[BuildCommand] = Field(
        description="Run a build script, then save, check and render its model."
    )
    check: CliSubCommand[CheckCommand] = Field(description="Check a model file.")
    render: CliSubCommand[RenderCommand] = Field(
        description="Render images of a model file."
    )
    instructions: CliSubCommand[InstructionsCommand] = Field(
        description="Write building instructions to follow step by step."
    )
    export: CliSubCommand[ExportCommand] = Field(
        description="Export a model file for another tool."
    )
    parts: CliSubCommand[PartsCommand] = Field(description="Search the parts catalog.")
    colors: CliSubCommand[ColorsCommand] = Field(
        description="Search the catalog's colors."
    )
    catalog: CliSubCommand[CatalogCommand] = Field(
        description="Import the catalog of parts and colors, and inspect it."
    )
    explain: CliSubCommand[ExplainCommand] = Field(
        description="Explain rules and their levels."
    )
    json_schema: CliSubCommand[SchemaCommand] = Field(
        description="Print the model file schema."
    )

    @classmethod
    @override
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Read the command line only.

        Configuration lives in :class:`bricky.Settings`.
        """
        return (init_settings,)

    def cli_cmd(self) -> None:
        """Run the chosen subcommand."""
        CliApp.run_subcommand(self)


_ENUM_REPR: Final = re.compile(r"<\w+\.\w+: '([^']*)'>")
"""An enum member as Python prints it, such as ``<View.SHEET: 'sheet'>``."""


_METAVARS: Final[dict[object, str]] = {
    Path: "PATH",
    str: "TEXT",
    int: "N",
    float: "NUMBER",
}
"""Words that name what an option takes, in place of Python's type names."""

_NO_DEFAULT: Final = re.compile(r" \(default( factory)?: (None|list|)\)")
"""A default that says nothing, such as ``(default: None)``."""

_LIST_DEFAULT: Final = re.compile(r"\(default: \[([^\]]*)\]\)")
"""A default list, such as ``(default: [sheet])``, which the help writes ``sheet``."""

_FLAG_DEFAULT: Final = re.compile(r"\(default: (True|False)\)")
"""A switch's default, such as ``(default: True)``, which the help writes as a flag."""


class _Source(CliSettingsSource[Bricky]):
    """Writes help in the command line's own words, not in Python's.

    The help shows ``View.SHEET`` as ``sheet``, ``list[str]`` as ``TEXT``, an option
    that repeats as what one occurrence takes, and leaves out defaults that are empty.
    """

    @override
    def _metavar_format_recurse(self, obj: object) -> str:
        if isinstance(obj, type) and issubclass(obj, Enum):
            return self._metavar_format_choices([str(member.value) for member in obj])
        if get_origin(obj) in {list, tuple, set} and (arguments := get_args(obj)):
            return self._metavar_format_recurse(arguments[0])
        if obj in _METAVARS:
            return _METAVARS[obj]
        return super()._metavar_format_recurse(obj)

    @override
    def _help_format(
        self,
        field_name: str,
        field_info: FieldInfo,
        model_default: object,
        is_model_suppressed: bool,
        env_var_names: tuple[str, ...] = (),
    ) -> str:
        text = super()._help_format(
            field_name, field_info, model_default, is_model_suppressed, env_var_names
        )
        text = _LIST_DEFAULT.sub(r"(default: \1)", _ENUM_REPR.sub(r"\1", text))
        flag = field_name.replace("_", "-")
        text = _FLAG_DEFAULT.sub(
            lambda match: f"(default: --{'' if match[1] == 'True' else 'no-'}{flag})",
            text,
        )
        return _NO_DEFAULT.sub("", text)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the command line.

    The exit status is 1 when a model has errors or a part fails verification, and 2
    when the arguments are invalid, a command needs a subcommand, or a command fails
    with a :class:`~bricky.BrickyError`. The lone argument ``--version`` prints the
    version.
    """
    arguments = sys.argv[1:] if argv is None else list(argv)
    if arguments == ["--version"]:
        print(f"bricky {__version__}")
        return
    try:
        CliApp.run(
            Bricky,
            cli_args=arguments,
            cli_settings_source=_Source(Bricky),
        )
    except BrickyError as error:
        _fail(str(error), as_json=_wants_json(arguments))
    except ValidationError as error:
        _fail(_invalid(error), as_json=_wants_json(arguments))
    except SystemExit as exit_:
        # A command run without its subcommand exits with a message, after its help.
        if isinstance(exit_.code, str):
            raise SystemExit(2) from None
        raise
    except BrokenPipeError:
        # The reader stopped reading, as `head` does: stop quietly.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        raise SystemExit(1) from None


def _fail(message: str, *, as_json: bool) -> NoReturn:
    """Print an error, as JSON on standard output when asked to, and exit with 2."""
    if as_json:
        print(json.dumps({"error": message}))
    else:
        print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def _wants_json(arguments: Sequence[str]) -> bool:
    """Whether the arguments ask for JSON output."""
    pairs = zip(arguments, [*arguments[1:], ""], strict=True)
    return "--output-format=json" in arguments or ("--output-format", "json") in pairs


def _invalid(error: ValidationError) -> str:
    """Name each invalid option and say what it accepts."""
    problems = []
    for problem in error.errors():
        names = [part for part in problem["loc"] if isinstance(part, str)]
        option = "--" + names[-1].replace("_", "-") if names else "arguments"
        problems.append(f"{option}: {problem['msg']}")
    return "invalid arguments: " + "; ".join(problems)
