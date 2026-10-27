# bricky-mcp

An MCP server that exposes [bricky](../../README.md) to any agent harness. Run it over stdio with
`uv run bricky-mcp`.

| Tool | Does |
| --- | --- |
| `build_model` | Runs a build script, saves its model and checks it |
| `check_model` | Checks a saved model file |
| `search_parts` | Searches the parts catalog |
| `list_passes` | Lists the installed passes and the profiles that run them |

Each tool's arguments come from a request model in `bricky.service`, so they match the CLI.
