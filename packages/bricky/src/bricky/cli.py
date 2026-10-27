"""The ``bricky`` command line.

Each subcommand extends a request model from :mod:`bricky.service` with an output format, so the
CLI accepts exactly what the MCP tools accept.
"""

import json
import sys
from collections.abc import Sequence
from typing import Literal, override

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    CliApp,
    CliSubCommand,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from bricky import service
from bricky.diagnostics import render_report
from bricky.errors import BrickyError
from bricky.files import model_schema


class _Output(BaseModel):
    output_format: Literal["text", "json"] = Field(
        default="text", description="text for people and agents, json for programs."
    )

    def emit(self, result: BaseModel, text: str) -> None:
        """Print a result in the requested format."""
        print(result.model_dump_json(indent=2) if self.output_format == "json" else text)


class BuildCommand(service.BuildRequest, _Output):
    """Run a build script, save the model it returns, then check it."""

    def cli_cmd(self) -> None:
        """Run the command."""
        result = service.build(self)
        lines = [f"saved {result.output} ({result.elements} elements)"]
        if result.report is not None:
            lines.append(render_report(result.report))
        self.emit(result, "\n\n".join(lines))
        if result.report is not None and not result.report.ok:
            raise SystemExit(1)


class CheckCommand(service.CheckRequest, _Output):
    """Check a model file and report diagnostics."""

    def cli_cmd(self) -> None:
        """Run the command."""
        report = service.check(self)
        self.emit(report, render_report(report))
        if not report.ok:
            raise SystemExit(1)


class PartsCommand(service.PartsRequest, _Output):
    """Search the parts catalog."""

    def cli_cmd(self) -> None:
        """Run the command."""
        result = service.parts(self)
        rows = [
            f"{p.id:<7} {p.name:<24} {p.family:<6} {p.width}x{p.length}  "
            f"{p.height:g} plates  {p.studs} studs"
            for p in result.parts
        ]
        rows.append(f"{len(result.parts)} of {result.total} matching parts")
        self.emit(result, "\n".join(rows))


class PassesCommand(service.PassesRequest, _Output):
    """List the installed check passes and the profiles that run them."""

    def cli_cmd(self) -> None:
        """Run the command."""
        result = service.passes(self)
        installed = {p.name for p in result.installed}
        rows = [f"{p.name:<14} {p.summary}" for p in result.installed]
        rows.append("")
        for name, names in result.profiles.items():
            marked = ", ".join(n if n in installed else f"{n} (not installed)" for n in names)
            default = " (default)" if name == result.default_profile else ""
            rows.append(f"{name}{default}: {marked}")
        self.emit(result, "\n".join(rows))


class SchemaCommand(BaseModel):
    """Print the JSON Schema of the model file format."""

    def cli_cmd(self) -> None:
        """Run the command."""
        print(json.dumps(model_schema(), indent=2))


class Bricky(BaseSettings):
    """Check and inspect LEGO® models written as Python build scripts."""

    model_config = SettingsConfigDict(
        cli_prog_name="bricky",
        cli_kebab_case=True,
        cli_implicit_flags=True,
        cli_hide_none_type=True,
        cli_avoid_json=True,
        cli_enforce_required=True,
    )

    build: CliSubCommand[BuildCommand] = Field(description="Run a build script, save and check it.")
    check: CliSubCommand[CheckCommand] = Field(description="Check a model file.")
    parts: CliSubCommand[PartsCommand] = Field(description="Search the parts catalog.")
    passes: CliSubCommand[PassesCommand] = Field(description="List installed passes and profiles.")
    json_schema: CliSubCommand[SchemaCommand] = Field(description="Print the model file schema.")

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
        """Take arguments from the command line only; configuration lives in Settings."""
        return (init_settings,)

    def cli_cmd(self) -> None:
        """Run the chosen subcommand."""
        CliApp.run_subcommand(self)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the command line; exit 1 when a model has errors and 2 on usage errors."""
    try:
        CliApp.run(Bricky, cli_args=None if argv is None else list(argv))
    except BrickyError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from None
