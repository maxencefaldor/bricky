# Connect an agent

An agent reaches bricky through one of three front ends, all derived from the same request models so their arguments never drift apart.

| Front end | Suits |
| --- | --- |
| [Command line](#command-line) | Any agent that runs shell commands, such as Claude Code or Codex |
| [MCP server](#mcp-server) | Any harness that speaks the Model Context Protocol |
| [Skill](#skill) | Claude Code, and any harness that loads instructions from a file |

## Command line

An agent that runs shell commands needs nothing more: `bricky build` runs a script and prints the report, and the agent opens the images it names.
Every command takes `--output-format json` to print its result as JSON for programs.
The [command line reference](../reference/cli.md) lists every command and option.

```sh
uv run bricky build models/tower.py
```

## MCP server

The package `bricky-mcp` serves bricky over the [Model Context Protocol](https://modelcontextprotocol.io), on stdio.
A harness starts it from a project's `.mcp.json`, which Claude Code and other harnesses read:

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

Each tool matches one command and takes the same arguments:

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

Each tool answers twice: with the text the command line prints, for the agent, and with the result as structured content, for programs.
The tools `build_model` and `render_model` also return their images, so the agent sees the model without another call.

Three behaviors of the server matter to an agent:

- **One warm browser.**
  The server starts Chromium on its first render and keeps it alive, so later images take a second or two.
- **Scripts run apart.**
  Each build script runs in a child process with a time limit, and whatever it prints comes back in the result, never on the protocol stream.
  A cancelled call stops its child.
- **Self-contained instructions.**
  The server's instructions teach the workflow, the coordinates and the tools, so an agent can start without the skill.

## Skill

The skill `.claude/skills/build-model/SKILL.md` teaches an agent the loop: plan, write the script, build, read the report and the images, fix, and repeat.
The skill holds the advice, such as staggering joints like a brick wall, because bricky itself only states facts.
Claude Code loads the skill from the repository on its own, and other harnesses can include the file in the agent's context.
The [benchmark](benchmark.md) copies the skill into every workspace.

```markdown
--8<-- ".claude/skills/build-model/SKILL.md"
```
