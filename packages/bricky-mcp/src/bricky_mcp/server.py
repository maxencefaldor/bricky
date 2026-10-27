"""MCP server exposing bricky's commands to any agent harness.

Every tool is generated from a request model in :mod:`bricky.service`, so tool arguments, defaults
and descriptions match the ``bricky`` command line exactly. Tools are async and hand the work to
:func:`asyncio.to_thread`, so the server stays responsive while a model is checked.
"""

import asyncio
import copy
import inspect
from collections.abc import Awaitable, Callable
from typing import Final

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from bricky import service
from bricky.diagnostics import Report
from bricky.errors import BrickyError

INSTRUCTIONS: Final = """\
bricky checks LEGO models that you write as Python build scripts.

Workflow: write a script that defines build() and returns a bricky.ModelBuilder, call build_model
on it, read the diagnostics, fix the script, and repeat until the report is ok.

Coordinates: x points east and y north, both in studs; z points up, in plates (a brick is 3
plates). In ModelBuilder.place, `at` is the minimum corner of the part's rotated bounding box.
Rotations are 'R0', 'R90', 'R180' and 'R270' about the vertical axis. Use search_parts to find
part ids, such as '3001' for Brick 2 x 4.
"""

READ_ONLY: Final = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITES_FILES: Final = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)


def tool_from[Req: BaseModel, Res: BaseModel](
    name: str,
    request_type: type[Req],
    handler: Callable[[Req], Res],
    result_type: type[Res],
) -> Callable[..., Awaitable[Res]]:
    """Build an async tool whose parameters are exactly the request model's fields.

    Each parameter's default is a copy of the request field's ``FieldInfo``, so the tool schema
    carries the same descriptions, defaults and constraints as the request model.
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

    async def tool(**arguments: object) -> Res:
        try:
            request = request_type.model_validate(arguments)
            return await asyncio.to_thread(handler, request)
        except BrickyError as error:
            raise ToolError(str(error)) from error

    tool.__signature__ = inspect.Signature(parameters, return_annotation=result_type)  # ty: ignore[unresolved-attribute]
    tool.__name__ = name
    tool.__doc__ = request_type.__doc__
    return tool


def create_server() -> MCPServer:
    """Create the bricky MCP server with all its tools."""
    server = MCPServer("bricky", instructions=INSTRUCTIONS)
    server.add_tool(
        tool_from("build_model", service.BuildRequest, service.build, service.BuildResult),
        annotations=WRITES_FILES,
        structured_output=True,
    )
    server.add_tool(
        tool_from("check_model", service.CheckRequest, service.check, Report),
        annotations=READ_ONLY,
        structured_output=True,
    )
    server.add_tool(
        tool_from("search_parts", service.PartsRequest, service.parts, service.PartsResult),
        annotations=READ_ONLY,
        structured_output=True,
    )
    server.add_tool(
        tool_from("list_passes", service.PassesRequest, service.passes, service.PassesResult),
        annotations=READ_ONLY,
        structured_output=True,
    )
    return server


def main() -> None:
    """Serve over stdio."""
    create_server().run()
