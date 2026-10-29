# Stability

The page shows how bricky checks that a model stands under its own weight and that its studs hold it together.

## The physical profile

The pass `stability` checks a model as a real build that stands on a table.
A model that only renders needs no such check, so the pass runs in the profile `physical`, which adds it to the digital passes.
The pass solves linear programs, with solvers that the extra `bricky[stability]` installs.
The option `--profile physical` runs the profile once, and the setting `profile = "physical"` makes it the default (see [Configuration](../reference/configuration.md)):

```sh
uv add "bricky[stability]"                              # the solvers, once per project
uv run bricky build models/crane.py --profile physical
```

```text
error[E402]: 1 stud joining 2 elements needs 106% of its clutch to hold the model together
  --> x 3.2..3.8  y 7.2..7.8  z 12.5..13
   = mast3: Brick 2 x 2 (3003), Yellow, models/crane.py:8 in build()
   = jib0: Brick 2 x 10 (3006), White, models/crane.py:10 in build()
```

## Forces

Each element is a rigid body that weighs its volume times a density, and forces act only where elements touch.

- A face presses on a face it rests against, where each face is the top or bottom of its part or holds its studs or anti-studs.
  The sides of LEGO® parts stand 0.1 mm in from the grid, so the sides of neighbors never touch.
- Faces that no stud joins also rub, with friction.
- A stud bears any sideways force and resists pulling out of its anti-stud with its clutch.
  A stud alone between two elements also resists twisting with its clutch, at its 2.4 mm radius.
- The ground presses up on every face that rests on it, with friction.

A model stands when some set of these forces balances every element: the forces and torques on each sum to zero.
Finding such forces is a linear program, the lower bound of limit analysis that studies of masonry and of LEGO® structures use ([Whiting et al., 2009](https://doi.org/10.1145/1618452.1618458); [Liu et al., 2024](https://arxiv.org/abs/2402.10711)).
The interior point solver [Clarabel](https://clarabel.org) settles most models in a few seconds.
When some stud grips hard, the simplex solver [HiGHS](https://highs.dev) starts from those forces and finds the exact loads, within a minute for thousands of elements.
The module `bricky.analysis.stability` gives the same analysis to Python: here a 1 x 8 plate reaches 6 studs past the brick it stands on.

```python
from bricky import ModelBuilder, Settings, default_catalog
from bricky.analysis import Context
from bricky.analysis.stability import Material, analyze_stability

builder = ModelBuilder("arm")
builder.place("3031", at=(0, 0, 0), color="Green", id="base")
builder.place("3003", at=(0, 0, 1), color="Yellow", id="post")
builder.place("3460", at=(0, 0, 4), color="Red", rotation="R90", id="arm")
context = Context(builder.build(), default_catalog())
stability = analyze_stability(context, Material.of(Settings()), threshold=0.001)
uids = [element.uid for element in context.world.elements]
```

```pycon
>>> [([uids[i] for i in site.elements], f"{site.load:.2%}") for site in stability.sites]
[(['post', 'arm'], '0.30%')]
```

## Groups that fall

A group falls when no forces balance it, however firmly its studs grip: it tips over an edge, slides, or drops off what it rests on.
Studs that grip without limit hold elements together rigidly, so the check moves whole groups of joined elements.
The code E401 names each group that moves, such as a post and the arm on it that reaches past its foot:

![A post with a long arm on top, both tinted red, labeled E401](../images/tipping.png)

## Studs that pull out

A stud holds its anti-stud with a force called its clutch, and the check finds how much of that clutch each stud must use.
Many sets of forces hold a model still, so the check takes the one where the most loaded stud uses the least share of its clutch.
The studs that set that share form a site, and the search repeats with those studs holding without limit.
Each site therefore needs its share of clutch however much the sites before it hold.
The code E402 names a site that needs more than its whole clutch, and W403 one that needs more than half, the default safety factor of 2.
A heavy jib on a single stud of a crane's mast needs 106% of that stud's clutch:

![A crane whose jib stands on one stud of the mast, the two elements tinted red, labeled E402](../images/crane.png)

## Settings

Four settings describe the material, and their defaults come from measurements of real elements.

| Setting | Default | Meaning |
| --- | --- | --- |
| `clutch` | 2.94 N | Force that pulls one stud out: three contact points of 0.98 N each, as [StableLego](https://arxiv.org/abs/2402.10711) measured |
| `friction` | 0.2 | Coefficient of friction between faces, a cautious value for ABS |
| `density` | 0.54 g/cm³ | Mass of an element's body per volume, hollows included, fitted to the bricks StableLego weighed |
| `safety_factor` | 2 | Times a stud's clutch must exceed its load before W403 stops warning |

A project that builds with worn elements might lower the clutch, in its `pyproject.toml`:

```toml
[tool.bricky]
profile = "physical"
clutch = 2.0
```

## Limits

The analysis answers whether forces exist that hold the model, and leaves out what changes those forces.

- Elements are rigid, so a long beam of plates holds as if it never bent.
- Loads are the model's own weight, at rest: no hand that lifts it, and no shaking.
- Weights come from volumes, within about a quarter of what real elements weigh.
- Clutch varies with wear, color and temperature, which the safety factor covers.

The lower bound of limit analysis also lets studs share loads in the best way they can, so a site's share is the least it needs.
A site near its limit in the report is therefore a site to strengthen first.
