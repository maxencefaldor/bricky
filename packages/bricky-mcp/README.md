# bricky-mcp

An MCP server that serves [bricky](../../README.md) to any agent harness, over stdio: `uv run bricky-mcp`.
The [MCP server guide](https://maxencefaldor.github.io/bricky/agents/mcp/) shows how to connect it.

| Tool | Does |
| --- | --- |
| `build_model` | Runs a build script in its own process, then saves, checks and draws the model |
| `render_model` | Draws a saved model again: other views, highlights, clips |
| `check_model` | Checks a saved model |
| `search_parts` | Searches the catalog's parts |
| `show_part` | Describes one part and can draw it |
| `search_colors` | Searches the catalog's colors |
| `list_passes` | Lists the installed passes, their codes and the profiles that run them |
| `explain_code` | Gives the exact rule behind a diagnostic code |

Each tool's arguments come from a request model in `bricky.service`, so they match the command line.
Each tool answers with the text the command line prints and with the result as structured content.
Builds and renders also return their pictures as images, so the agent sees the model without another call.

The server keeps one render browser warm for its lifetime.
Build scripts never run inside it: whatever a script prints is captured and returned, and never reaches the protocol stream.
