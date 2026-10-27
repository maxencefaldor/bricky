import asyncio
from pathlib import Path

from mcp import Client

from bricky import ModelBuilder, save_model
from bricky_mcp import create_server


def call(name: str, arguments: dict[str, object]):
    async def go():
        async with Client(create_server()) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(go())


def list_tools():
    async def go():
        async with Client(create_server()) as client:
            return await client.list_tools()

    return asyncio.run(go()).tools


def test_tools_mirror_the_service_requests():
    tools = {tool.name: tool for tool in list_tools()}
    assert set(tools) == {"build_model", "check_model", "search_parts", "list_passes"}
    check = tools["check_model"]
    assert set(check.input_schema["properties"]) == {
        "model",
        "profile",
        "passes",
        "max_diagnostics",
    }
    assert check.input_schema["required"] == ["model"]
    assert check.output_schema is not None
    assert check.annotations is not None
    assert check.annotations.read_only_hint is True
    assert tools["build_model"].annotations.read_only_hint is False


def test_check_model_returns_a_structured_report(tmp_path: Path):
    builder = ModelBuilder("floating")
    builder.place("3001", at=(0, 0, 3), color="Red")
    path = tmp_path / "m.bricky.json"
    save_model(builder.build(), path)
    result = call("check_model", {"model": str(path)})
    assert not result.is_error
    assert result.structured_content["errors"] == 1
    assert result.structured_content["diagnostics"][0]["code"] == "E301"


def test_errors_come_back_as_tool_errors(tmp_path: Path):
    result = call("check_model", {"model": str(tmp_path / "missing.json")})
    assert result.is_error
    assert "no such model file" in result.content[0].text


def test_search_parts():
    result = call("search_parts", {"query": "tile 2x2"})
    assert [p["id"] for p in result.structured_content["parts"]] == ["3068b"]
