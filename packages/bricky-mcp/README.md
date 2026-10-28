# bricky-mcp

The MCP server for [bricky](https://github.com/maxencefaldor/bricky): it serves bricky to any agent harness over the Model Context Protocol, on stdio.
The guide [Connect an agent](https://maxencefaldor.github.io/bricky/agents/connect/) shows how to start it from a harness.

```sh
uv run bricky-mcp
```

| Tool | Does |
| --- | --- |
| `build_model` | Runs a build script in its own process, then saves, checks and renders the model |
| `render_model` | Renders a saved model again: other views, highlights, clips |
| `check_model` | Checks a saved model |
| `search_parts` | Searches the catalog's parts |
| `show_part` | Describes one part, and can render it |
| `search_colors` | Searches the catalog's colors |
| `list_passes` | Lists the installed passes, their codes and the profiles that run them |
| `explain_code` | Gives the exact rule behind a diagnostic code |

Each tool takes the same arguments as its command on the command line, and answers with the text the command prints and with the result as structured content.
The tools `build_model` and `render_model` also return their images, so the agent sees the model without another call.
