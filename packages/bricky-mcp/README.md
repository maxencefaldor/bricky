# bricky-mcp

An MCP server that exposes [bricky](../../README.md) to any agent harness. Run it over stdio with
`uv run bricky-mcp`.

| Tool | Does |
| --- | --- |
| `build_model` | Runs a build script in its own process, saves, checks and renders the model |
| `render_model` | Draws a saved model: views, highlights by id or script line, cuts |
| `check_model` | Checks a saved model file |
| `search_parts` | Searches the parts catalog |
| `list_colors` | Lists the catalog's colours |
| `list_passes` | Lists the installed passes, their codes and the profiles that run them |
| `explain_code` | Gives the exact rule behind a diagnostic code |

Each tool's arguments come from a request model in `bricky.service`, so they match the CLI. Each
tool answers with the same text the CLI prints and the result as structured content. Builds and
renders also return their pictures as images, so the agent sees the model without another call.

The server keeps one render browser warm for its lifetime. Build scripts never run inside it:
whatever a script prints is captured and returned, and never reaches the protocol stream.
