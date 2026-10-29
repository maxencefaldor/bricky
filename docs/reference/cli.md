# Command line

The `bricky` command builds, checks and renders models from the shell.

Every command but `json-schema` takes `--output-format json` to print its result as JSON for programs; the default, `text`, is for people and agents.
The command `bricky --version` prints the version.
The exit status is 0 for success, 1 when the model has errors or `catalog verify` finds problems, and 2 for invalid arguments or a failed command.
Each command's options come from a request model in `bricky.service`, which the [MCP server](../agents/connect.md#mcp-server) shares, so a tool takes the same arguments as its command.

## `bricky build`

Run a build script, then save, check and render its model.

| Option | Default | Description |
| --- | --- | --- |
| `--output-format` | `text` | 'text' for people and agents, 'json' for programs. |
| `SCRIPT` | required | Python file defining build(), which returns a ModelBuilder or a Model. |
| `--output` |  | Where to save the model; defaults to &lt;script&gt;.bricky.json. |
| `--check`, `--no-check` | `True` | Check the model after building it. |
| `--render`, `--no-render` | `True` | Render the model after checking it. |
| `--views` | `sheet` | Views to render: sheet (perspective, front, right and top on one image), perspective (from the south-east), perspective-south-west, perspective-north-west, perspective-north-east, front, back, left, right or top. |
| `--profile` |  | Profile to run, such as 'digital'; defaults to the configured one. |
| `--passes` |  | Pass names to run instead of a profile. |
| `--max-diagnostics` |  | Maximum diagnostics to return; defaults to the configured cap. |

## `bricky check`

Check a model file.

| Option | Default | Description |
| --- | --- | --- |
| `--output-format` | `text` | 'text' for people and agents, 'json' for programs. |
| `MODEL` | required | Path to a .bricky.json model file. |
| `--profile` |  | Profile to run, such as 'digital'; defaults to the configured one. |
| `--passes` |  | Pass names to run instead of a profile. |
| `--max-diagnostics` |  | Maximum diagnostics to return; defaults to the configured cap. |

## `bricky render`

Render images of a model file.

| Option | Default | Description |
| --- | --- | --- |
| `--output-format` | `text` | 'text' for people and agents, 'json' for programs. |
| `MODEL` | required | Path to a .bricky.json model file. |
| `--views` | `sheet` | Views to render: sheet (perspective, front, right and top on one image), perspective (from the south-east), perspective-south-west, perspective-north-west, perspective-north-east, front, back, left, right or top. |
| `--highlight` |  | Elements to highlight, rendering the rest faintly: uid patterns such as 'sign*', or '@' and a function, file or file:line of the build script, such as '@roof'. |
| `--clip` |  | Clip the model to look inside: 'z&lt;130' keeps what lies below 130 plates; x and y are in studs. |
| `--check`, `--no-check` | `True` | Mark the elements that diagnostics name. |
| `--width` | `1600` | Image width in pixels. |
| `--height` | `1200` | Image height in pixels. |
| `--output` |  | Image file to write; with several views, each file name gets the view's name added. Defaults to &lt;model&gt;.&lt;view&gt;.png beside the model, so renders keep the sheet a build rendered. |
| `--html`, `--no-html` | `False` | Also write a standalone HTML viewer people can orbit and clip, highlighted like the images. |

## `bricky parts`

Search the parts catalog.

| Option | Default | Description |
| --- | --- | --- |
| `--output-format` | `text` | 'text' for people and agents, 'json' for programs. |
| `QUERY` |  | Words to match against ids, names, categories and sizes, such as 'plate 2x4' (quoted). |
| `--limit` | `20` | Maximum number of parts to return. |
| `--shapeless`, `--no-shapeless` | `False` | Also list the parts without a shape, which cannot be placed. |

## `bricky colors`

Search the catalog's colors.

| Option | Default | Description |
| --- | --- | --- |
| `--output-format` | `text` | 'text' for people and agents, 'json' for programs. |
| `QUERY` |  | Words to match against ids, names and types, such as 'gray', or an RGB value, such as '#F2CD37', to list the nearest colors. |

## `bricky catalog import`

Import parts and colors from BrickLink, shapes from LDraw.

| Option | Default | Description |
| --- | --- | --- |
| `--output-format` | `text` | 'text' for people and agents, 'json' for programs. |
| `--bricklink` |  | Folder holding BrickLink's catalog downloads as XML, from <https://www.bricklink.com/catalogDownload.asp>: Catalog Items (Parts), Colors, Categories and Codes, under any file names. Without it, parts come from LDraw and colors from bricky's sample. |
| `--ldraw` |  | LDraw parts library folder, holding parts and p, such as an unzipped complete.zip from library.ldraw.org; LDraw shapes the parts that no name describes. |
| `--output` |  | Catalog file to write; defaults to bricky's data folder, where bricky looks for it. |

## `bricky catalog status`

Say which catalog bricky uses and what is in it.

| Option | Default | Description |
| --- | --- | --- |
| `--output-format` | `text` | 'text' for people and agents, 'json' for programs. |

## `bricky catalog show`

Show one part.

| Option | Default | Description |
| --- | --- | --- |
| `--output-format` | `text` | 'text' for people and agents, 'json' for programs. |
| `PART` | required | BrickLink item number, such as '3001'. |
| `--render`, `--no-render` | `False` | Also render the part, in the first color it comes in. |
| `--output` |  | Image file to write; defaults to &lt;part&gt;.png in bricky's cache folder, outside the workspace. |

## `bricky catalog verify`

Check every shaped part's geometry.

| Option | Default | Description |
| --- | --- | --- |
| `--output-format` | `text` | 'text' for people and agents, 'json' for programs. |

## `bricky passes`

List installed passes and profiles.

| Option | Default | Description |
| --- | --- | --- |
| `--output-format` | `text` | 'text' for people and agents, 'json' for programs. |

## `bricky explain`

Explain diagnostic codes.

| Option | Default | Description |
| --- | --- | --- |
| `--output-format` | `text` | 'text' for people and agents, 'json' for programs. |
| `CODE` |  | A code such as 'E301'; every code when omitted. |

## `bricky json-schema`

Print the model file schema.

The command takes no options.
