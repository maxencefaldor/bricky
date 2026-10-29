# Copyright 2026 Maxence Faldor
"""MCP server exposing bricky's commands to any agent harness.

The server generates every tool from a request model in :mod:`bricky.service`, so tool
arguments, defaults and descriptions match the ``bricky`` command line exactly. Each
tool answers with the same text the command line prints, the result as structured
content, and, for builds and renders, the images themselves, so the agent sees the model
without another call.

The server holds one :class:`bricky.service.Session` for its lifetime, which keeps the
render browser warm between calls. The service runs each build script in a process of
its own, outside the server, so nothing a script prints can reach the protocol stream.
"""

from __future__ import annotations

import base64
import copy
import inspect
import sys
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Final, Protocol, runtime_checkable

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import (
    CallToolResult,
    ContentBlock,
    ImageContent,
    TextContent,
    ToolAnnotations,
)
from pydantic import BaseModel

from bricky import service
from bricky.diagnostics import Report, format_report
from bricky.errors import BrickyError

INSTRUCTIONS: Final = """\
bricky builds, checks and renders LEGO® models written as Python build scripts.

Workflow: write a script that defines build() and returns a bricky.ModelBuilder, then
call build_model on it. build_model returns diagnostics, each naming the script line
that placed its elements, and an image of the model: perspective, front, right and top
views, with rulers in studs and plates. From the second build on, the result also counts
what changed since the last build, by script line, and the image outlines new and
changed elements. Read everything, fix the script, and build again until the report has
no errors and the images show the intended model. render_model looks closer: it
highlights elements by uid or by script function, clips the model open, or renders
other views.

Coordinates: x points east and y north, both in studs; z points up, in plates (a brick
is 3 plates). `at` is the minimum corner of the rotated bounding box of what a script
places, a part or a component. Rotations 'R0', 'R90', 'R180' and 'R270' rotate about the
vertical axis. A rotation can also name where the part's x and y axes go, which reaches
all 24 grid rotations: '+x+z' stands a part up facing -y. search_parts and search_colors
find ids. search_parts also says which way a part faces unrotated, such as a slope
falling toward -y, and show_part describes one part and can render it. Scripts can place
only parts with a shape. explain_code gives the exact rule behind a diagnostic. In a
script, bricky.voxels(model) maps every voxel a model fills, to compare with a plan.
"""

READ_ONLY: Final = ToolAnnotations(read_only_hint=True, open_world_hint=False)
RUNS_CODE: Final = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=True,
)
"""A build runs any Python with the user's permissions, so harnesses should ask."""
WRITES_FILES: Final = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)


@runtime_checkable
class Described(Protocol):
    """A result that renders itself as text for people and agents."""

    def describe(self) -> str:
        """Return the result as text."""
        ...


@runtime_checkable
class Pictured(Protocol):
    """A result that carries images."""

    images: Sequence[service.Image]


def _text(result: BaseModel) -> str:
    if isinstance(result, Report):
        return format_report(result)
    if isinstance(result, Described):
        return result.describe()
    return result.model_dump_json(indent=2)


def _images(result: BaseModel) -> list[ContentBlock]:
    if not isinstance(result, Pictured):
        return []
    return [
        ImageContent(
            type="image",
            data=base64.b64encode(Path(image.path).read_bytes()).decode("ascii"),
            mime_type="image/png",
        )
        for image in result.images
    ]


def tool_from[RequestModel: BaseModel, ResultModel: BaseModel](
    name: str,
    request_type: type[RequestModel],
    handler: Callable[[RequestModel, service.Session], Awaitable[ResultModel]],
    result_type: type[ResultModel],
    session: service.Session,
) -> Callable[..., Awaitable[CallToolResult]]:
    """Build an async tool whose parameters are exactly the request model's fields.

    Each parameter's default is a copy of the request field's ``FieldInfo``, so the tool
    schema carries the same descriptions, defaults and constraints as the request model.
    The tool returns the result's text and any rendered images as content, and the
    result itself as structured content, validated against ``result_type``.
    """
    parameters = [
        inspect.Parameter(
            field,
            inspect.Parameter.KEYWORD_ONLY,
            default=copy.copy(info),
            annotation=info.annotation,
        )
        for field, info in request_type.model_fields.items()
    ]

    async def tool(**arguments: object) -> CallToolResult:
        try:
            request = request_type.model_validate(arguments)
            result = await handler(request, session)
        except BrickyError as error:
            raise ToolError(str(error)) from error
        content: list[ContentBlock] = [TextContent(type="text", text=_text(result))]
        content.extend(_images(result))
        return CallToolResult(
            content=content, structured_content=result.model_dump(mode="json")
        )

    tool.__signature__ = inspect.Signature(  # ty: ignore[unresolved-attribute]
        parameters, return_annotation=Annotated[CallToolResult, result_type]
    )
    tool.__name__ = name
    tool.__doc__ = request_type.__doc__
    return tool


def create_server(session: service.Session | None = None) -> MCPServer:
    """Create the bricky MCP server with all its tools.

    Args:
        session: Session shared by every tool call; a new one, closed with the server,
            by default.
    """
    shared = session or service.Session()

    @asynccontextmanager
    async def lifespan(_: MCPServer) -> AsyncGenerator[None]:
        try:
            yield
        finally:
            if session is None:
                await shared.close()

    server = MCPServer(
        "bricky",
        version=version("bricky-mcp"),
        instructions=INSTRUCTIONS,
        website_url="https://maxencefaldor.github.io/bricky/",
        lifespan=lifespan,
    )

    def register[RequestModel: BaseModel, ResultModel: BaseModel](
        name: str,
        request_type: type[RequestModel],
        handler: Callable[[RequestModel, service.Session], Awaitable[ResultModel]],
        result_type: type[ResultModel],
        annotations: ToolAnnotations,
    ) -> None:
        server.add_tool(
            tool_from(name, request_type, handler, result_type, shared),
            annotations=annotations,
            structured_output=True,
        )

    register(
        "build_model",
        service.BuildRequest,
        service.build,
        service.BuildResult,
        RUNS_CODE,
    )
    register(
        "render_model",
        service.RenderRequest,
        service.render,
        service.RenderResult,
        WRITES_FILES,
    )
    register("check_model", service.CheckRequest, service.check, Report, READ_ONLY)
    register(
        "search_parts",
        service.PartsRequest,
        service.parts,
        service.PartsResult,
        READ_ONLY,
    )
    register(
        "show_part",
        service.CatalogShowRequest,
        service.catalog_show,
        service.CatalogShowResult,
        WRITES_FILES,
    )
    register(
        "search_colors",
        service.ColorsRequest,
        service.colors,
        service.ColorsResult,
        READ_ONLY,
    )
    register(
        "list_passes",
        service.PassesRequest,
        service.passes,
        service.PassesResult,
        READ_ONLY,
    )
    register(
        "explain_code",
        service.ExplainRequest,
        service.explain,
        service.ExplainResult,
        READ_ONLY,
    )
    return server


USAGE: Final = """\
usage: bricky-mcp [--help | --version]

Serve bricky's tools to an agent harness over the Model Context Protocol, on stdio.
A harness starts this command: https://maxencefaldor.github.io/bricky/agents/connect/
"""


def main(argv: Sequence[str] | None = None) -> None:
    """Serve over stdio, or answer ``--help`` or ``--version``."""
    arguments = sys.argv[1:] if argv is None else list(argv)
    if arguments == ["--version"]:
        sys.stdout.write(f"bricky-mcp {version('bricky-mcp')}\n")
        return
    if arguments in (["--help"], ["-h"]):
        sys.stdout.write(USAGE)
        return
    if arguments:
        sys.stderr.write(USAGE)
        raise SystemExit(2)
    if sys.stdin.isatty():
        sys.stderr.write(
            "bricky-mcp serves MCP on stdio for a harness to start; Ctrl-C stops it.\n"
        )
    create_server().run()
