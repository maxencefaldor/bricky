# Configuration

Settings tune every command.
Each setting comes from the first source that sets it: a command's option, a `BRICKY_*` environment variable, or the `[tool.bricky]` table of the `pyproject.toml` in the working directory.

| Setting | Environment variable | Default | Description |
| --- | --- | --- | --- |
| `profile` | `BRICKY_PROFILE` | `digital` | Profile used when a command names none. |
| `max_diagnostics` | `BRICKY_MAX_DIAGNOSTICS` | `20` | Maximum number of diagnostics a report lists. |
| `build_timeout` | `BRICKY_BUILD_TIMEOUT` | `60.0` | Seconds a build script may run before bricky stops it. |
| `output_limit` | `BRICKY_OUTPUT_LIMIT` | `20000` | Characters kept from each of a build script's standard output and standard error. |
| `render_browser` | `BRICKY_RENDER_BROWSER` | unset | Chromium executable for renders; Playwright's own browser when unset. |
| `catalog` | `BRICKY_CATALOG` | unset | Catalog file to use. When unset, bricky uses the catalog that `bricky catalog import` wrote to its data folder, or its sample catalog when there is none. |
| `profiles` | `BRICKY_PROFILES` | `digital`, `physical` | Named pass lists; entries extend or override the built-in profiles. |

A project that builds large models might raise the time limit and add a quick profile:

```toml title="pyproject.toml"
[tool.bricky]
build_timeout = 300
profiles = { quick = ["schema", "collision"] }
```
