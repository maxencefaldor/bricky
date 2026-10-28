import asyncio
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from bricky import ModelBuilder, save_model
from bricky_mcp import create_server

SCRIPT = """
from bricky import ModelBuilder


def build():
    print("chatter on stdout")
    builder = ModelBuilder("m")
    builder.place("3001", at=(0, 0, 0), color="Red")
    builder.place("3022", at=(5, 5, 5), color="Tan", name="float")
    return builder
"""


def call(name: str, arguments: Mapping[str, object]):
    async def go():
        async with Client(create_server()) as client:
            return await client.call_tool(name, dict(arguments))

    return asyncio.run(go())


def list_tools():
    async def go():
        async with Client(create_server()) as client:
            return await client.list_tools()

    return asyncio.run(go()).tools


def test_tools_mirror_the_service_requests():
    tools = {tool.name: tool for tool in list_tools()}
    assert set(tools) == {
        "build_model",
        "render_model",
        "check_model",
        "search_parts",
        "show_part",
        "list_colors",
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
    assert tools["build_model"].annotations.read_only_hint is False
    assert "highlight" in tools["render_model"].input_schema["properties"]


def test_check_model_answers_with_text_and_a_structured_report(tmp_path: Path):
    builder = ModelBuilder("floating")
    builder.place("3001", at=(0, 0, 3), color="Red")
    path = tmp_path / "m.bricky.json"
    save_model(builder.build(), path)
    result = call("check_model", {"model": str(path)})
    assert not result.is_error
    assert result.content[0].text.startswith("error[E301]")
    assert result.structured_content["errors"] == 1
    assert result.structured_content["diagnostics"][0]["code"] == "E301"


def test_build_model_returns_the_report_and_the_picture(tmp_path: Path):
    script = tmp_path / "m.py"
    script.write_text(SCRIPT)
    result = call("build_model", {"script": str(script), "views": ["front"]})
    assert not result.is_error
    text, image = result.content
    assert "chatter on stdout" in text.text
    assert "m.py:9 in build()" in text.text
    assert image.type == "image"
    assert image.mime_type == "image/png"
    data = result.structured_content
    assert data["output"]["stdout"] == "chatter on stdout\n"
    assert data["changes"] is None
    assert data["report"]["errors"] == 1
    assert data["images"][0]["view"] == "front"
    script.write_text(SCRIPT.replace("at=(5, 5, 5)", "at=(0, 0, 3)"))
    again = call("build_model", {"script": str(script), "render": False})
    assert "since the last build: 0 added, 0 removed, 1 changed, 1 unchanged" in (
        again.content[0].text
    )
    assert again.structured_content["changes"]["changed_at"] == [
        {"line": f"{script}:9 in build()", "elements": 1}
    ]
    assert again.structured_content["report"]["errors"] == 0


def test_render_model_returns_one_picture_per_view(tmp_path: Path):
    builder = ModelBuilder("m")
    builder.place("3001", at=(0, 0, 0), color="Red", name="base")
    path = tmp_path / "m.bricky.json"
    save_model(builder.build(), path)
    arguments = {"model": str(path), "views": ["iso", "top"], "highlight": ["base"]}
    result = call("render_model", arguments)
    assert not result.is_error
    text, *images = result.content
    assert [image.type for image in images] == ["image", "image"]
    assert f"top: {tmp_path / 'm.top.png'}" in text.text
    assert [image["view"] for image in result.structured_content["images"]] == ["iso", "top"]
    assert (tmp_path / "m.iso.png").is_file()


def test_errors_come_back_as_tool_errors(tmp_path: Path):
    result = call("check_model", {"model": str(tmp_path / "missing.json")})
    assert result.is_error
    assert "no such model file" in result.content[0].text


def test_catalog_tools():
    parts = call("search_parts", {"query": "tile 2x2"})
    assert [p["id"] for p in parts.structured_content["parts"]] == ["3068", "14769"]
    colors = call("list_colors", {"query": "pearl gold"})
    assert [c["id"] for c in colors.structured_content["colors"]] == [115]
    explained = call("explain_code", {"code": "E202"})
    assert explained.structured_content["codes"][0]["title"] == "Blocked stud"


def test_scripts_that_print_cannot_corrupt_the_stdio_channel(tmp_path: Path):
    script = tmp_path / "noisy.py"
    script.write_text(SCRIPT.replace('print("chatter on stdout")', 'print("{not json}" * 50)'))
    environment = {key: value for key, value in os.environ.items() if key.startswith("BRICKY_")}
    server = StdioServerParameters(
        command=sys.executable, args=["-m", "bricky_mcp"], env=environment, cwd=str(tmp_path)
    )

    async def go():
        async with Client(server) as client:
            built = await client.call_tool("build_model", {"script": str(script), "render": False})
            colors = await client.call_tool("list_colors", {"query": "red"})
            return built, colors

    built, colors = asyncio.run(go())
    assert not built.is_error
    assert built.structured_content["output"]["stdout"].startswith("{not json}")
    assert not colors.is_error
