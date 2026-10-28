# MCP server

`bricky-mcp` serves bricky to any agent harness over the [Model Context Protocol](https://modelcontextprotocol.io), on stdio.
Every tool's arguments come from the same request model as the matching command-line command, so the two never drift apart.

## Connect

Add the server to a project's `.mcp.json`, which Claude Code and other harnesses read:

```json title=".mcp.json"
{
  "mcpServers": {
    "bricky": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/bricky", "bricky-mcp"]
    }
  }
}
```

With Claude Code, one command does the same:

```sh
claude mcp add bricky -- uv run --directory /path/to/bricky bricky-mcp
```

## Tools

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

Each tool answers twice: with the text the command line prints, for the agent to read, and with the result as structured content, for programs.
`build_model` and `render_model` also return their pictures as images, so the agent sees the model without another call.

## Behavior

- **One warm browser.**
  The server starts Chromium on its first render and keeps it for its lifetime, so later renders take a second or two.
- **Scripts run apart.**
  Build scripts never run inside the server.
  Each runs in a child process with a time limit; whatever it prints is captured and returned, and never reaches the protocol stream.
  A cancelled call stops its child.
- **Instructions.**
  The server's instructions tell the agent the workflow, the coordinates and the tools, so an agent can start without the skill.
