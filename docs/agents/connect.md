# Connect an agent

The page shows how an agent reaches bricky through each of its three front ends.

The command line and the MCP server derive from the same request models, so their arguments always match.

| Front end | Suits |
| --- | --- |
| [Command line](#command-line) | Any harness that runs shell commands, such as Claude Code or Codex |
| [MCP server](#mcp-server) | Any harness that speaks the Model Context Protocol |
| [Skill](#skill) | Claude Code, and any harness that loads instructions from a file |

## Command line

An agent whose harness runs shell commands needs nothing more.
The command `bricky build` runs a script and prints the report, and the agent opens the images it names.
Every command takes `--output-format json` to print its result as JSON for programs.
Where bricky is installed as a tool or with pip, the command is `bricky`, without `uv run`.
The [command line reference](../reference/cli.md) lists every command and option.

```sh
uv run bricky build models/tower.py
```

## MCP server

The package `bricky-mcp` serves bricky over the [Model Context Protocol](https://modelcontextprotocol.io), on stdio.
A harness starts it from a project's `.mcp.json`, which Claude Code and other harnesses read.
The command `uvx`, which comes with uv, runs the server straight from PyPI:

```json title=".mcp.json"
{
  "mcpServers": {
    "bricky": {
      "command": "uvx",
      "args": ["bricky-mcp"]
    }
  }
}
```

With Claude Code, one command does the same:

```sh
claude mcp add bricky -- uvx bricky-mcp
```

The server renders in Chromium, which Playwright installs once per machine:

```sh
uvx --from bricky-mcp playwright install chromium
```

From a clone of the repository, the server runs with the clone's code instead:

```sh
claude mcp add bricky -- uv run --project /path/to/bricky bricky-mcp
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
| `explain_rule` | Gives the exact condition behind a rule, its level and its pass |

Each tool answers twice: with the text the command line prints, for the agent, and with the result as structured content, for programs.
The tools `build_model` and `render_model` also return their images, so the agent sees the model without another call.

Three behaviors of the server matter to an agent:

- **One warm browser.**
  The server starts Chromium on its first render and keeps it alive, so later images take a second or two.
- **Scripts run apart.**
  Each build script runs in a child process with a time limit.
  Whatever the script prints comes back in the result, never on the protocol stream.
  A canceled call stops its child.
  A build script still runs as ordinary Python with your permissions, so run only scripts you trust.
- **Self-contained instructions.**
  The server's instructions teach the workflow, the coordinates and the tools, so an agent can start without the skill.

## Skill

The skill `.claude/skills/build-model/SKILL.md` teaches an agent the loop: plan, write the script, build, read the report and the images, fix, and repeat.
The skill holds the advice, such as staggering joints like a brick wall, because bricky itself only states facts.
Claude Code loads the skill on its own inside the bricky repository.
To use it in another project, download it into that project's `.claude/skills/`:

```sh
mkdir -p .claude/skills/build-model && curl -o .claude/skills/build-model/SKILL.md https://raw.githubusercontent.com/maxencefaldor/bricky/main/.claude/skills/build-model/SKILL.md
```

To use it in every project, download it into `~/.claude/skills/` the same way.
Other harnesses can include the file in the agent's context.
The [benchmark](benchmark.md) copies the skill into every workspace.
The skill in full:

````markdown
--8<-- ".claude/skills/build-model/SKILL.md"
````
