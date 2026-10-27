"""The ``bricky`` command line.

Each subcommand extends a request model from :mod:`bricky.service` with an output format, so the
CLI accepts exactly what the MCP tools accept, and prints the same text the MCP tools return.
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
from bricky.diagnostics import Report, render_report
from bricky.errors import BrickyError
from bricky.files import model_schema


class _Output(BaseModel):
    output_format: Literal["text", "json"] = Field(
        default="text", description="text for people and agents, json for programs."
    )

    def emit(self, result: BaseModel, text: str) -> None:
        """Print a result in the requested format."""
        print(result.model_dump_json(indent=2) if self.output_format == "json" else text)


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
        _fail_on_errors(result.report)


class CheckCommand(service.CheckRequest, _Output):
    """Check a model file and report diagnostics."""

    async def cli_cmd(self) -> None:
        """Run the command."""
        async with service.Session() as session:
            report = await service.check(self, session)
        self.emit(report, render_report(report))
        _fail_on_errors(report)


class RenderCommand(service.RenderRequest, _Output):
    """Render pictures of a model file."""

    async def cli_cmd(self) -> None:
        """Run the command."""
        async with service.Session() as session:
            result = await service.render(self, session)
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


class PassesCommand(service.PassesRequest, _Output):
    """List the installed check passes and the profiles that run them."""

    async def cli_cmd(self) -> None:
        """Run the command."""
        async with service.Session() as session:
            result = await service.passes(self, session)
        self.emit(result, result.describe())


class ExplainCommand(service.ExplainRequest, _Output):
    """Explain diagnostic codes: what each means and the exact rule its pass checks."""

    async def cli_cmd(self) -> None:
        """Run the command."""
        async with service.Session() as session:
            result = await service.explain(self, session)
        self.emit(result, result.describe())


class CatalogImportCommand(service.CatalogImportRequest, _Output):
    """Import BrickLink's catalog: every part and every color, into the catalog bricky uses."""

    async def cli_cmd(self) -> None:
        """Run the command."""
        async with service.Session() as session:
            result = await service.catalog_import(self, session)
        self.emit(result, result.describe())


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
        """Run the command; exit 1 when a part has a problem."""
        async with service.Session() as session:
            result = await service.catalog_verify(self, session)
        self.emit(result, result.describe())
        if result.problems:
            raise SystemExit(1)


class CatalogCommand(BaseModel):
    """Import the catalog of parts and colors, and look into it."""

    import_: CliSubCommand[CatalogImportCommand] = Field(
        alias="import", description="Import BrickLink's catalog of parts and colors."
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
        description="Run a build script, save, check and render it."
    )
    check: CliSubCommand[CheckCommand] = Field(description="Check a model file.")
    render: CliSubCommand[RenderCommand] = Field(description="Render pictures of a model file.")
    parts: CliSubCommand[PartsCommand] = Field(description="Search the parts catalog.")
    colors: CliSubCommand[ColorsCommand] = Field(description="Search the catalog's colors.")
    catalog: CliSubCommand[CatalogCommand] = Field(
        description="Import the catalog of parts and colors, and look into it."
    )
    passes: CliSubCommand[PassesCommand] = Field(description="List installed passes and profiles.")
    explain: CliSubCommand[ExplainCommand] = Field(description="Explain diagnostic codes.")
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
