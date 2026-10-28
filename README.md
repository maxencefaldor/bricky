# bricky

A compiler-style toolkit that lets AI agents design buildable LEGO® models.

[![The Colosseum example: 44,968 elements on a plaza of baseplates](docs/images/hero.png)](https://maxencefaldor.github.io/bricky/gallery/)

An AI agent can describe a castle, but it cannot tell whether the castle's bricks hold together.

With bricky, the agent writes its model as a Python build script.
Each build places every part in exact geometry, checks that the model holds together, and renders it.

Each diagnostic names the script line behind it, and the orthographic views carry rulers in studs and plates.
The agent therefore knows what is wrong, where, and which line placed it.

## 🚀 Quick start

The quick start needs [uv](https://docs.astral.sh/uv/), which installs Python 3.15 and every dependency:

```sh
git clone https://github.com/maxencefaldor/bricky && cd bricky
uv sync
uv run playwright install chromium       # the browser bricky renders in
uv run bricky build examples/cottage.py  # build, check and render the cottage
```

## 🧱 How it works

A build script places parts by their BrickLink id, in studs and plates.
The four lines below come from `examples/broken.py`, which makes three mistakes: an overlap, a brick half a stud off and a floating plate.

```python
builder.place("3001", at=(0, 0, 0), color="Red", id="base")  # Brick 2 x 4
builder.place("3001", at=(1, 0, 0), color="Blue", id="overlap")  # shares space
builder.place("3003", at=(0.5, 0, 3), color="White", id="offset")  # half a stud off
builder.place("3022", at=(4, 2, 9), color="Tan", id="floating")  # touches nothing
```

The report reads like compiler output, and every element it names points back at the script:

```text
error[E201]: base and overlap occupy the same space
  --> x 1..2  y 0..4  z 0..3
   = base: Brick 2 x 4 (3001), Red, examples/broken.py:13 in build()
   = overlap: Brick 2 x 4 (3001), Blue, examples/broken.py:14 in build()
```

The image marks the same elements in red, so the agent sees where they are:

![The broken example: every element a diagnostic names is tinted red and labeled](docs/images/broken.png)

## ⚖️ Disclaimer

LEGO® is a trademark of the LEGO Group, which does not sponsor, authorize or endorse this project.
