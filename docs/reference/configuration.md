# Configuration

Settings tune every command.
Each setting comes whole from the first source that sets it: a command's option, a `BRICKY_*` variable, or the configuration file.
The options `--error`, `--warn` and `--ignore` instead apply over the levels that `rules` sets.
The configuration file is `bricky.toml` when there is one, and otherwise the `[tool.bricky]` table of `pyproject.toml`.
A `bricky.toml` replaces that table entirely, as `ty.toml` replaces `[tool.ty]`.

| Setting | Environment variable | Default | Description |
| --- | --- | --- | --- |
| `max_diagnostics` | `BRICKY_MAX_DIAGNOSTICS` | `20` | Maximum number of diagnostics a report lists. |
| `build_timeout` | `BRICKY_BUILD_TIMEOUT` | `60.0` | Seconds a build script may run before bricky stops it. |
| `output_limit` | `BRICKY_OUTPUT_LIMIT` | `20000` | Characters kept from each of a build script's standard output and standard error. |
| `render_browser` | `BRICKY_RENDER_BROWSER` | unset | Chromium executable for renders; Playwright's own browser when unset. |
| `catalog` | `BRICKY_CATALOG` | unset | Catalog file to use. When unset, bricky uses the catalog that `bricky catalog import` wrote to its data folder, or its sample catalog when there is none. |
| `clutch` | `BRICKY_CLUTCH` | `2.94` | Newtons that pull one stud out of its anti-stud: three contact points of 0.98 N, as StableLego measured. |
| `friction` | `BRICKY_FRICTION` | `0.2` | Coefficient of friction between faces that press together, a cautious value for ABS. |
| `density` | `BRICKY_DENSITY` | `0.54` | Grams per cubic centimeter of an element's body, hollows included; 0.54 fits the bricks StableLego weighed. |
| `safety_factor` | `BRICKY_SAFETY_FACTOR` | `2.0` | Times a stud's clutch must exceed what it holds before the rule strained-studs leaves it out. |
| `rules` | `BRICKY_RULES` | unset | Level of each rule by name, or of every rule with 'all': error, warn or ignore. A rule's own entry overrides 'all', and rules left out keep their default level. |

A `bricky.toml` holds the same settings without the `tool.bricky` prefix: `[rules]` for `[tool.bricky.rules]`.
A project that builds large models might raise the time limit and make two stability rules errors:

```toml title="pyproject.toml"
[tool.bricky]
build_timeout = 300

[tool.bricky.rules]
unbalanced-group = "error"
overloaded-studs = "error"
```
