# bricky-mcp

The MCP server for [bricky](https://github.com/maxencefaldor/bricky), a compiler-style toolkit that lets AI agents design buildable LEGO® models.

The server serves bricky to any agent harness over the Model Context Protocol, on stdio.
The command `uvx`, which comes with [uv](https://docs.astral.sh/uv/), runs it straight from PyPI.
With Claude Code, one command adds it:

```sh
claude mcp add bricky -- uvx bricky-mcp
```

Other harnesses start it from a project's `.mcp.json`:

```json
{
  "mcpServers": {
    "bricky": {
      "command": "uvx",
      "args": ["bricky-mcp"]
    }
  }
}
```

The server renders in Chromium, which Playwright installs once per machine:

```sh
uvx --from bricky-mcp playwright install chromium
```

The guide [Connect an agent](https://maxencefaldor.github.io/bricky/agents/connect/) covers every front end, and the [documentation](https://maxencefaldor.github.io/bricky/) covers bricky itself.

## Tools

| Tool | Does |
| --- | --- |
| `build_model` | Runs a build script in its own process, then saves, checks and renders the model |
| `render_model` | Renders a saved model again: other views, highlights, clips |
| `check_model` | Checks a saved model |
| `search_parts` | Searches the catalog's parts |
| `show_part` | Describes one part, and can render it |
| `search_colors` | Searches the catalog's colors |
| `explain_rule` | Gives the exact condition behind a rule, its level and its pass |

Each tool takes the same arguments as its command on the command line.
Each tool answers with the text the command prints and with the result as structured content.
The tools `build_model` and `render_model` also return their images, so the agent sees the model without another call.

## Disclaimer

LEGO® is a trademark of the LEGO Group, which does not sponsor, authorize or endorse this project.
