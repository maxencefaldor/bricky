# Copyright 2026 Maxence Faldor

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Mapping
from importlib.metadata import version
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import CallToolResult, ImageContent, ListToolsResult, TextContent, Tool

from bricky import ModelBuilder, save_model
from bricky_mcp import create_server
from bricky_mcp.server import main

SCRIPT = """
from bricky import ModelBuilder


def build():
    print("chatter on stdout")
    builder = ModelBuilder("m")
    builder.place("3001", at=(0, 0, 0), color="Red")
    builder.place("3022", at=(5, 5, 5), color="Tan", id="float")
    return builder
"""


def call(name: str, arguments: Mapping[str, object]) -> CallToolResult:
    async def go() -> CallToolResult:
        async with Client(create_server()) as client:
            return await client.call_tool(name, dict(arguments))

    return asyncio.run(go())


def text_of(result: CallToolResult) -> str:
    """The text of a tool result's first content, which is always text."""
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


def list_tools() -> list[Tool]:
    async def go() -> ListToolsResult:
        async with Client(create_server()) as client:
            return await client.list_tools()

    return asyncio.run(go()).tools


def test_tools_mirror_the_service_requests() -> None:
    tools = {tool.name: tool for tool in list_tools()}
    assert set(tools) == {
        "build_model",
        "render_model",
        "check_model",
        "search_parts",
        "show_part",
        "search_colors",
        "list_passes",
        "explain_code",
    }
    check = tools["check_model"]
    assert set(check.input_schema["properties"]) == {
        "model",
        "profile",
        "passes",
        "max_diagnostics",
    }
    assert check.input_schema["required"] == ["model"]
    assert all(tool.output_schema is not None for tool in tools.values())
    assert check.annotations is not None
    assert check.annotations.read_only_hint is True
    build = tools["build_model"].annotations
    assert build is not None
    assert build.read_only_hint is False
    assert build.destructive_hint is True  # a build runs arbitrary Python
    assert "highlight" in tools["render_model"].input_schema["properties"]


def test_check_model_answers_with_text_and_a_structured_report(tmp_path: Path) -> None:
    builder = ModelBuilder("floating")
    builder.place("3001", at=(0, 0, 3), color="Red")
    path = tmp_path / "m.bricky.json"
    save_model(builder.build(), path)
    result = call("check_model", {"model": str(path)})
    assert not result.is_error
    assert text_of(result).startswith("error[E301]")
    assert result.structured_content["errors"] == 1
    assert result.structured_content["diagnostics"][0]["code"] == "E301"


def test_build_model_returns_the_report_and_the_image(tmp_path: Path) -> None:
    script = tmp_path / "m.py"
    script.write_text(SCRIPT)
    result = call("build_model", {"script": str(script), "views": ["front"]})
    assert not result.is_error
    text, image = text_of(result), result.content[1]
    assert "chatter on stdout" in text
    assert "m.py:9 in build()" in text
    assert isinstance(image, ImageContent)
    assert image.mime_type == "image/png"
    data = result.structured_content
    assert data["output"]["stdout"] == "chatter on stdout\n"
    assert data["changes"] is None
    assert data["report"]["errors"] == 1
    assert data["images"][0]["view"] == "front"
    script.write_text(SCRIPT.replace("at=(5, 5, 5)", "at=(0, 0, 3)"))
    again = call("build_model", {"script": str(script), "render": False})
    assert "since the last build: 0 added, 0 removed, 1 changed, 1 unchanged" in (
        text_of(again)
    )
    assert again.structured_content["changes"]["changed_at"] == [
        {"line": f"{script}:9 in build()", "elements": 1}
    ]
    assert again.structured_content["report"]["errors"] == 0


def test_render_model_returns_one_image_per_view(tmp_path: Path) -> None:
    builder = ModelBuilder("m")
    builder.place("3001", at=(0, 0, 0), color="Red", id="base")
    path = tmp_path / "m.bricky.json"
    save_model(builder.build(), path)
    arguments = {
        "model": str(path),
        "views": ["perspective", "top"],
        "highlight": ["base"],
    }
    result = call("render_model", arguments)
    assert not result.is_error
    images = result.content[1:]
    assert [image.type for image in images] == ["image", "image"]
    assert f"top: {tmp_path / 'm.top.png'}" in text_of(result)
    assert [image["view"] for image in result.structured_content["images"]] == [
        "perspective",
        "top",
    ]
    assert (tmp_path / "m.perspective.png").is_file()


def test_errors_come_back_as_tool_errors(tmp_path: Path) -> None:
    result = call("check_model", {"model": str(tmp_path / "missing.json")})
    assert result.is_error
    assert "no such model file" in text_of(result)


def test_catalog_tools() -> None:
    parts = call("search_parts", {"query": "tile 2x2"})
    assert [p["id"] for p in parts.structured_content["parts"]] == ["3068", "14769"]
    colors = call("search_colors", {"query": "pearl gold"})
    assert [c["id"] for c in colors.structured_content["colors"]] == [115]
    explained = call("explain_code", {"code": "E202"})
    assert explained.structured_content["codes"][0]["title"] == "Blocked stud"


def test_scripts_that_print_cannot_corrupt_the_stdio_channel(tmp_path: Path) -> None:
    script = tmp_path / "noisy.py"
    script.write_text(
        SCRIPT.replace('print("chatter on stdout")', 'print("{not json}" * 50)')
    )
    environment = {
        key: value for key, value in os.environ.items() if key.startswith("BRICKY_")
    }
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "bricky_mcp"],
        env=environment,
        cwd=str(tmp_path),
    )

    async def go() -> tuple[CallToolResult, CallToolResult]:
        async with Client(server) as client:
            built = await client.call_tool(
                "build_model", {"script": str(script), "render": False}
            )
            colors = await client.call_tool("search_colors", {"query": "red"})
            return built, colors

    built, colors = asyncio.run(go())
    assert not built.is_error
    assert built.structured_content["output"]["stdout"].startswith("{not json}")
    assert not colors.is_error


def test_the_command_answers_help_and_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["--version"])
    assert capsys.readouterr().out == f"bricky-mcp {version('bricky-mcp')}\n"
    main(["--help"])
    assert capsys.readouterr().out.startswith("usage: bricky-mcp")
    with pytest.raises(SystemExit) as exit_:
        main(["--bogus"])
    assert exit_.value.code == 2
