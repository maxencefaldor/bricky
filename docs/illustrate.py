# Copyright 2026 Maxence Faldor
"""Render every image in bricky's docs with bricky's own renderer.

Run from the repository root: ``uv run python docs/illustrate.py``, or name figures to
render only those. Each figure is a small model built below, or an example script,
rendered into ``docs/images``. Figures use the sample catalog, so anyone can render them
again; the figures of converted LDraw parts need an imported catalog and are skipped
without one. Bare figures, for cards and the home page, carry no text at all.
"""

from __future__ import annotations

import asyncio
import base64
import os
import shutil
import sys
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from importlib.resources import files
from math import hypot
from pathlib import Path
from typing import Final

from playwright.async_api import Page, Route, async_playwright

from bricky import ModelBuilder, Settings, check_model, default_catalog, voxels
from bricky.analysis import build_world, diff_worlds
from bricky.catalog import IMPORTED_CATALOG, SAMPLE_CATALOG, Catalog, load_catalog
from bricky.model import Model
from bricky.provenance import Provenance
from bricky.render import Clip, Renderer, Scene, View, build_scene
from bricky.service import run_script

ROOT: Final = Path(__file__).resolve().parent.parent
IMAGES: Final = ROOT / "docs" / "images"
EXAMPLES: Final = ROOT / "examples"
BENCHMARK: Final = ROOT / "benchmark" / "projects"

type Make = Callable[[Catalog], ModelBuilder]


@dataclass(frozen=True, slots=True)
class Figure:
    """One image: a model, how to render it, and the file it goes to."""

    name: str
    model: Make | Path
    """A function that builds the model, or an example script."""

    view: View = View.SHEET
    size: tuple[int, int] = (1600, 1200)
    check: bool = False
    """Mark what the checks find."""

    highlight: tuple[str, ...] = ()
    clips: tuple[str, ...] = ()
    before: Make | None = None
    """An earlier version of the model, to outline what changed since."""

    imported: bool = False
    """Render with the imported catalog: for parts converted from LDraw."""

    buildable: bool = True
    """Whether the model has no errors.

    The script warns when a buildable model has some.
    """

    bare: bool = False
    """Render a perspective with no text on it: no title, caption, compass or labels."""


# --------------------------------------------------------------------------------------
# Coordinates


def axes(catalog: Catalog) -> ModelBuilder:
    """Bricks along x (red, east), y (green, north) and z (blue, up).

    The bricks start from a white origin.
    """
    builder = ModelBuilder("axes", catalog=catalog)
    builder.place("3005", at=(0, 0, 0), color="White", id="origin")
    for step in range(1, 7):
        builder.place("3005", at=(step, 0, 0), color="Red", id=f"x{step}")
        builder.place("3005", at=(0, step, 0), color="Green", id=f"y{step}")
        builder.place("3005", at=(0, 0, 3 * step), color="Blue", id=f"z{step}")
    return builder


def corners(catalog: Catalog) -> ModelBuilder:
    """One Brick 2 x 4 in four rotations.

    Each ``at`` is the minimum corner of its footprint.
    """
    builder = ModelBuilder("corners", catalog=catalog)
    builder.place("3001", at=(0, 0, 0), color="Red", id="R0")
    builder.place("3001", at=(3, 0, 0), rotation="R90", color="Blue", id="R90")
    builder.place("3001", at=(3, 3, 0), rotation="R180", color="Yellow", id="R180")
    builder.place("3001", at=(8, 0, 0), rotation="R270", color="Green", id="R270")
    return builder


def rotations(catalog: Catalog) -> ModelBuilder:
    """A Slope 45 2 x 2 in each rotation about the vertical axis, on a plate."""
    builder = ModelBuilder("rotations", catalog=catalog)
    builder.place(
        "3028", at=(0, 0, 0), rotation="R90", color="Light Bluish Gray", id="plate"
    )
    for index, rotation in enumerate(("R0", "R90", "R180", "R270")):
        builder.place(
            "3039",
            at=(1 + 3 * index, 2, 1),
            rotation=rotation,
            color="Red",
            id=rotation,
        )
    return builder


def sideways(catalog: Catalog) -> ModelBuilder:
    """A tile and a plate held sideways by the studs on the sides of bricks."""
    builder = ModelBuilder("sideways", catalog=catalog)
    builder.place(
        "3020", at=(0, 0, 0), rotation="R90", color="Dark Bluish Gray", id="base"
    )
    for x in (0, 3):
        builder.place("3005", at=(x, 1, 1), color="White", id=f"column{x}")
    builder.place("87087", at=(0, 1, 4), color="White", id="holder")
    builder.place("3070", at=(0, 0.6, 4.5), rotation="+x+z", color="Blue", id="sign")
    builder.place("3005", at=(3, 1, 4), color="White", id="column3-top")
    builder.place("30414", at=(0, 1, 7), color="White", id="studs-on-side")
    builder.place("3710", at=(0, 0.6, 7.5), rotation="-z+x", color="Red", id="facade")
    return builder


def half_stud(catalog: Catalog) -> ModelBuilder:
    """A jumper centers a lamp post half a stud off the grid, between two brick rows."""
    builder = ModelBuilder("jumper", catalog=catalog)
    builder.place("3020", at=(0, 0, 0), color="Dark Bluish Gray", id="base")
    builder.place("15573", at=(0, 1, 1), color="Black", id="jumper")
    for course in range(3):
        builder.place(
            "3062", at=(0, 1.5, 2 + 3 * course), color="Black", id=f"post{course}"
        )
    builder.place("4073", at=(0, 1.5, 11), color="Trans-Yellow", id="lamp")
    builder.place("3004", at=(1, 0, 1), color="Tan", id="bench")
    return builder


# --------------------------------------------------------------------------------------
# Parts and colors

FAMILIES: Final = (
    ("brick", "3001", "Red"),
    ("plate", "3020", "Yellow"),
    ("tile", "87079", "Blue"),
    ("slope", "3039", "Red"),
    ("inverted", "3660", "Dark Bluish Gray"),
    ("curved", "15068", "Lime"),
    ("round", "3941", "Green"),
    ("side-studs", "4733", "White"),
    ("jumper", "87580", "Black"),
    ("arch", "3659", "Tan"),
)


def families(catalog: Catalog) -> ModelBuilder:
    """One part of each family, in a row on a baseplate."""
    builder = ModelBuilder("families", catalog=catalog)
    builder.place(
        "3857", at=(0, 0, 0), rotation="R90", color="Light Bluish Gray", id="baseplate"
    )
    for index, (family, part, color) in enumerate(FAMILIES):
        x, y = 1 + 6 * (index % 5), 9 - 7 * (index // 5)
        rotation = "R90" if family == "arch" else "R0"
        builder.place(part, at=(x, y, 0.5), rotation=rotation, color=color, id=family)
    return builder


COLORS: Final = (
    "White", "Light Bluish Gray", "Dark Bluish Gray", "Black", "Red", "Dark Red",
    "Orange", "Bright Light Orange", "Yellow", "Lime", "Green", "Dark Green",
    "Sand Green", "Dark Turquoise", "Medium Azure", "Blue", "Dark Blue", "Magenta",
    "Tan", "Nougat", "Reddish Brown", "Pearl Gold", "Flat Silver", "Trans-Clear",
    "Trans-Red", "Trans-Yellow", "Trans-Green", "Trans-Light Blue",
)  # fmt: skip


def colors(catalog: Catalog) -> ModelBuilder:
    """Round bricks in two rows, one stack per color.

    The colors are solid, pearl and transparent.
    """
    builder = ModelBuilder("colors", catalog=catalog)
    for index, color in enumerate(COLORS):
        row, column = divmod(index, len(COLORS) // 2)
        for course in range(1 + row):
            builder.place("3941", at=(3 * column, 3 * row, 3 * course), color=color)
    return builder


def converted(catalog: Catalog) -> ModelBuilder:
    """Parts no name describes, converted from LDraw.

    The figure shows their bodies as boxes, studs and all.
    """
    builder = ModelBuilder("converted", catalog=catalog)
    parts = (
        ("3700", "Dark Bluish Gray"),  # Technic, Brick 1 x 2 with Hole
        ("32064", "Light Bluish Gray"),  # Technic, Brick 1 x 2 with Axle Hole
        ("60593", "White"),  # Window 1 x 2 x 3 Flat Front
        ("87552", "Tan"),  # Panel 1 x 2 x 2 with Side Supports
        ("30136", "Reddish Brown"),  # Brick, Modified 1 x 2 with Log Profile
        ("2357", "Red"),  # Brick 2 x 2 Corner
        ("4070", "Yellow"),  # Brick, Modified 1 x 1 with Headlight
        ("6091", "Blue"),  # Slope, Curved 2 x 1 x 1 1/3 with Recessed Stud
    )
    x = 0
    for part, color in parts:
        found = catalog.part(part)
        if found is None:
            continue
        builder.place(part, at=(x, 0, 0), color=color, id=part)
        x += found.size.x // 20 + 1
    return builder


# --------------------------------------------------------------------------------------
# Building


def wall(catalog: Catalog) -> ModelBuilder:
    """The getting-started wall: three courses in running bond, eight studs long."""
    builder = ModelBuilder("wall", catalog=catalog)
    for course in range(3):
        z = 3 * course
        if course % 2 == 0:
            for x in (0, 4):
                builder.place("3010", at=(x, 0, z), rotation="R90", color="Red")
        else:
            builder.place("3004", at=(0, 0, z), rotation="R90", color="Red")
            builder.place("3010", at=(2, 0, z), rotation="R90", color="Red")
            builder.place("3004", at=(6, 0, z), rotation="R90", color="Red")
    return builder


def wall_floating(catalog: Catalog) -> ModelBuilder:
    """The wall with one brick left in the air, a plate above the top course."""
    builder = wall(catalog)
    builder.place("3004", at=(3, 0, 10), rotation="R90", color="Blue", id="chimney")
    return builder


def wall_fixed(catalog: Catalog) -> ModelBuilder:
    """The wall with the brick lowered onto the top course's studs."""
    builder = wall(catalog)
    builder.place("3004", at=(3, 0, 9), rotation="R90", color="Blue", id="chimney")
    return builder


def tower_before(catalog: Catalog) -> ModelBuilder:
    """A tower of crossed bricks: the build before an edit."""
    builder = ModelBuilder("tower", catalog=catalog)
    for course in range(6):
        z = 3 * course
        if course % 2 == 0:
            builder.place("3001", at=(0, 0, z), color="Red")
            builder.place("3001", at=(2, 0, z), color="Red")
        else:
            builder.place("3001", at=(0, 0, z), rotation="R90", color="White")
            builder.place("3001", at=(0, 2, z), rotation="R90", color="White")
    return builder


def tower_after(catalog: Catalog) -> ModelBuilder:
    """The tower after an edit: the top two courses recolored, and a tile cap added."""
    builder = ModelBuilder("tower", catalog=catalog)
    for course in range(6):
        z = 3 * course
        top = course >= 4
        if course % 2 == 0:
            color = "Blue" if top else "Red"
            builder.place("3001", at=(0, 0, z), color=color)
            builder.place("3001", at=(2, 0, z), color=color)
        else:
            color = "Yellow" if top else "White"
            builder.place("3001", at=(0, 0, z), rotation="R90", color=color)
            builder.place("3001", at=(0, 2, z), rotation="R90", color=color)
    for x in (0, 2):
        for y in (0, 2):
            builder.place("3068", at=(x, y, 18), color="Dark Bluish Gray")
    return builder


def filled(catalog: Catalog) -> ModelBuilder:
    """A round tower described as voxels and filled with bricks and plates."""
    builder = ModelBuilder("fill", catalog=catalog)
    tower = {
        (x, y, z): "White" if z // 3 % 4 == 3 else "Red"
        for x in range(-6, 7)
        for y in range(-6, 7)
        for z in range(24)
        if 4 <= hypot(x, y) < 6.5
    }
    builder.fill(tower, id="tower")
    return builder


# --------------------------------------------------------------------------------------
# Checks: one small model per diagnostic code


def overlap(catalog: Catalog) -> ModelBuilder:
    """E201: two bricks placed into the same space."""
    builder = ModelBuilder("overlap", catalog=catalog)
    builder.place("3020", at=(0, 0, 0), color="Dark Bluish Gray", id="base")
    builder.place("3001", at=(0, 0, 1), color="Red", id="left")
    builder.place("3003", at=(1, 2, 1), color="Blue", id="right")
    return builder


def blocked(catalog: Catalog) -> ModelBuilder:
    """E202: a plate half a stud off the grid.

    The studs below push into the plate's underside.
    """
    builder = ModelBuilder("blocked", catalog=catalog)
    builder.place("3001", at=(0, 0, 0), rotation="R90", color="Red", id="brick")
    builder.place("3022", at=(0.5, 0, 3), color="Yellow", id="shifted")
    return builder


def floating(catalog: Catalog) -> ModelBuilder:
    """E301: a brick held by nothing."""
    builder = ModelBuilder("floating", catalog=catalog)
    builder.place("3001", at=(0, 0, 0), color="Red", id="ground")
    builder.place("3003", at=(0, 0, 5), color="Blue", id="cloud")
    return builder


def underground(catalog: Catalog) -> ModelBuilder:
    """E103: a brick sunk below the ground plane."""
    builder = ModelBuilder("underground", catalog=catalog)
    builder.place("3001", at=(0, 0, 0), color="Red", id="standing")
    builder.place("3001", at=(3, 0, -2), color="Blue", id="sunk")
    return builder


# --------------------------------------------------------------------------------------
# Voxels


def voxelized(catalog: Catalog) -> ModelBuilder:
    """A slope and an arch beside the voxels they fill, rebuilt from 1 x 1 plates.

    The plates over the arch's opening float: the figure shows voxels, not a model to
    build.
    """
    source = ModelBuilder("source", catalog=catalog)
    source.place("3039", at=(0, 0, 0), color="Red", id="slope")
    source.place("3659", at=(0, 3, 0), color="Tan", id="arch")
    builder = ModelBuilder("voxels", catalog=catalog)
    builder.place("3039", at=(0, 0, 0), color="Red", id="slope")
    builder.place("3659", at=(0, 3, 0), color="Tan", id="arch")
    for (x, y, z), voxel in sorted(voxels(source.build(), catalog).items()):
        color = "Red" if voxel.uid == "slope" else "Tan"
        builder.place("3024", at=(x + 4, y, z), color=color)
    return builder


card: Final = partial(Figure, view=View.PERSPECTIVE, size=(1200, 900), bare=True)
"""Make the figure of a card's image: a bare perspective in a 4:3 frame."""

FIGURES: Final = (
    # Getting started
    Figure("wall-floating", wall_floating, check=True),
    Figure("wall-fixed", wall_fixed, check=True, before=wall_floating),
    # Coordinates
    Figure("axes", axes),
    Figure("corners", corners, view=View.TOP, size=(1200, 800), highlight=("R*",)),
    Figure(
        "rotations",
        rotations,
        view=View.PERSPECTIVE,
        size=(1200, 900),
        highlight=("R*",),
    ),
    Figure("sideways", sideways, view=View.PERSPECTIVE, size=(1000, 900)),
    Figure("jumper", half_stud),
    # Parts and colors
    Figure(
        "families",
        families,
        view=View.PERSPECTIVE,
        size=(1200, 900),
        highlight=tuple(family for family, _, _ in FAMILIES),
    ),
    Figure("colors", colors, view=View.PERSPECTIVE, size=(1600, 700)),
    Figure(
        "converted", converted, view=View.PERSPECTIVE, size=(1600, 800), imported=True
    ),
    # Build scripts
    Figure("tower", EXAMPLES / "tower.py"),
    Figure("colonnade", EXAMPLES / "colonnade.py", highlight=("i2/*",)),
    Figure("cottage", EXAMPLES / "cottage.py"),
    Figure("fill", filled, view=View.PERSPECTIVE, size=(1000, 1000)),
    Figure(
        "colosseum-north-west",
        EXAMPLES / "colosseum.py",
        view=View.PERSPECTIVE_NORTH_WEST,
        size=(1600, 1100),
    ),
    # Checks and changes
    Figure("broken", EXAMPLES / "broken.py", check=True),
    Figure("overlap", overlap, view=View.PERSPECTIVE, size=(1000, 800), check=True),
    Figure("blocked", blocked, view=View.PERSPECTIVE, size=(1000, 800), check=True),
    Figure("floating", floating, view=View.FRONT, size=(1000, 800), check=True),
    Figure("underground", underground, view=View.FRONT, size=(1000, 800), check=True),
    Figure(
        "changes",
        tower_after,
        view=View.PERSPECTIVE,
        size=(1200, 900),
        before=tower_before,
    ),
    # Images
    Figure("highlight", EXAMPLES / "cottage.py", highlight=("@roof",)),
    Figure("clip", EXAMPLES / "cottage.py", view=View.PERSPECTIVE, clips=("y>4",)),
    Figure("front", EXAMPLES / "cottage.py", view=View.FRONT, size=(1200, 900)),
    # Voxels
    Figure(
        "voxels", voxelized, view=View.PERSPECTIVE, size=(1200, 900), buildable=False
    ),
    # The home page and the cards: bare perspectives, with no text on them
    Figure(
        "hero",
        EXAMPLES / "japanese_garden.py",
        view=View.PERSPECTIVE,
        size=(1600, 1200),
        bare=True,
    ),
    card("card-coordinates", rotations, highlight=("R*",)),
    card("card-scripts", filled),
    card("card-parts", families, highlight=tuple(family for family, _, _ in FAMILIES)),
    card("card-checks", EXAMPLES / "broken.py", check=True),
    card("card-images", EXAMPLES / "cottage.py", highlight=("@roof",)),
    card("card-voxels", voxelized, buildable=False),
    card("card-catalog", converted, imported=True),
    *(
        Figure(
            f"gallery-{name}", EXAMPLES / script, view=view, size=(1200, 900), bare=True
        )
        for name, script, view in (
            ("street-corner", "street_corner.py", View.PERSPECTIVE),
            ("japanese-garden", "japanese_garden.py", View.PERSPECTIVE),
            ("pirate-ship", "pirate_ship.py", View.PERSPECTIVE),
            ("pumpkin-manor", "pumpkin_manor.py", View.PERSPECTIVE),
            ("lighthouse-island", "lighthouse_island.py", View.PERSPECTIVE),
            ("steam-train", "steam_train.py", View.PERSPECTIVE),
            ("macaw", "macaw.py", View.PERSPECTIVE),
            ("great-wave", "great_wave.py", View.PERSPECTIVE),
            ("cottage", "cottage.py", View.PERSPECTIVE),
            ("elizabeth-tower", "elizabeth_tower.py", View.PERSPECTIVE),
            ("colosseum", "colosseum.py", View.PERSPECTIVE_NORTH_WEST),
        )
    ),
)

COPIES: Final = {
    "benchmark-heart.png": BENCHMARK / "02-pixel-heart" / "inputs" / "heart.png",
    "benchmark-house.png": BENCHMARK / "04-house-plans" / "inputs" / "plans.png",
    "benchmark-toadstool.png": BENCHMARK
    / "05-mushroom-layers"
    / "inputs"
    / "toadstool.png",
    "benchmark-lighthouse.png": BENCHMARK
    / "06-lighthouse-image"
    / "inputs"
    / "lighthouse.png",
    "benchmark-castle.png": BENCHMARK / "09-castle-plans" / "inputs" / "plans.png",
}
"""Benchmark inputs the docs show as they are."""


async def model_of(
    figure: Figure, catalog: Catalog, settings: Settings
) -> tuple[Model, Provenance | None]:
    """Build a figure's model, from its function or by running its example script."""
    if isinstance(figure.model, Path):
        run = await run_script(figure.model, settings)
        return run.model, run.provenance
    builder = figure.model(catalog)
    return builder.build(), builder.provenance()


async def render(
    figure: Figure, renderer: Renderer, page: Page, settings: Settings
) -> Path | None:
    """Render one figure into the images folder and return its path."""
    if figure.imported and not IMPORTED_CATALOG.is_file():
        print(f"skipped {figure.name}: it needs an imported catalog")
        return None
    catalog = load_catalog(IMPORTED_CATALOG) if figure.imported else default_catalog()
    model, provenance = await model_of(figure, catalog, settings)
    report = check_model(
        model, provenance=provenance, catalog=catalog, settings=settings
    )
    if report.errors and figure.buildable and not figure.check:
        print(
            f"warning: {figure.name} has {report.errors} errors, "
            "which the image leaves out"
        )
    changed: list[str] = []
    if figure.before is not None:
        before = build_world(figure.before(catalog).build(), catalog)
        difference = diff_worlds(before, build_world(model, catalog))
        changed = [*difference.added, *difference.changed]
    scene = build_scene(
        model,
        catalog,
        provenance=provenance,
        report=report if figure.check else None,
        highlight=figure.highlight,
        clips=[Clip.parse(clip) for clip in figure.clips],
        changed=changed,
    )
    width, height = figure.size
    if figure.bare:
        image = await photograph(page, scene, figure.size, figure.view)
    else:
        (image,) = await renderer.render(
            scene, [figure.view], width=width, height=height
        )
    path = IMAGES / f"{figure.name}.png"
    path.write_bytes(image)
    return path


# --------------------------------------------------------------------------------------
# Studio: clean images for cards and the home page, with no text on them


STUDIO_ORIGIN: Final = "https://studio.invalid/"
"""The private origin the studio's page loads bricky's render assets from."""

RENDER_ASSETS: Final = files("bricky.render").joinpath("assets")
PNG_URL: Final = "data:image/png;base64,"
SUPERSAMPLE: Final = 2
"""How many times larger the studio renders an image before shrinking it."""

AZIMUTHS: Final = {
    View.PERSPECTIVE: 35,
    View.PERSPECTIVE_SOUTH_WEST: -35,
    View.PERSPECTIVE_NORTH_WEST: 215,
    View.PERSPECTIVE_NORTH_EAST: 145,
}
"""Each perspective's azimuth, in degrees from the south toward the east."""

STUDIO_PAGE: Final = """\
import * as THREE from "three";
import { buildModel } from "./viewer.js";

// The camera and lights match the renderer's perspective views: a 24-degree lens
// 30 degrees up, a sky light, and a sun left of the camera that casts shadows.
const LENS = 24;
const ELEVATION = THREE.MathUtils.degToRad(30);
const SUN = new THREE.Vector3(-0.55, 1.1, 0.75);
const SOUTH_EAST = THREE.MathUtils.degToRad(35);
const UP = new THREE.Vector3(0, 1, 0);
const FILL = 0.92;
const STUD = 8; // millimeters

function aim(camera, target, azimuth, distance) {
  const across = Math.cos(ELEVATION);
  camera.position.set(
    Math.sin(azimuth) * across, Math.sin(ELEVATION), Math.cos(azimuth) * across,
  );
  camera.position.multiplyScalar(distance).add(target);
  camera.lookAt(target);
  camera.updateMatrixWorld();
}

function corners(box) {
  const points = [];
  for (const x of [box.min.x, box.max.x]) {
    for (const y of [box.min.y, box.max.y]) {
      for (const z of [box.min.z, box.max.z]) points.push(new THREE.Vector3(x, y, z));
    }
  }
  return points;
}

// Render a scene from one azimuth, with no text, and return it as a PNG data URL.
function photograph(scene, options) {
  const { width, height, supersample, azimuth: degrees, background } = options;
  const azimuth = THREE.MathUtils.degToRad(degrees);
  const renderer = new THREE.WebGLRenderer({
    antialias: true, preserveDrawingBuffer: true,
  });
  renderer.setPixelRatio(1);
  renderer.setSize(width * supersample, height * supersample, false);
  renderer.localClippingEnabled = true;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.setClearColor(background, 1);
  const three = new THREE.Scene();
  const sun = new THREE.DirectionalLight(0xffffff, 2.1);
  sun.castShadow = true;
  sun.shadow.mapSize.set(4096, 4096);
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.6;
  three.add(new THREE.HemisphereLight(0xffffff, 0x8d949e, 1.45), sun, sun.target);
  const model = buildModel(scene);
  three.add(model.root);
  const center = model.bounds.getCenter(new THREE.Vector3());
  const radius = model.bounds.getSize(new THREE.Vector3()).length();
  const light = SUN.clone().applyAxisAngle(UP, azimuth - SOUTH_EAST).normalize();
  sun.position.copy(center).addScaledVector(light, radius * 1.5);
  sun.target.position.copy(center);
  Object.assign(sun.shadow.camera, {
    left: -radius, right: radius, top: radius, bottom: -radius,
    near: radius * 0.1, far: radius * 4,
  });
  sun.shadow.camera.updateProjectionMatrix();
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(radius * 6, radius * 6),
    new THREE.ShadowMaterial({ opacity: 0.16 }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.set(center.x, model.bounds.min.y - 0.02, center.z);
  ground.receiveShadow = true;
  three.add(ground);

  // Center the model, then move the camera until it and its shadow fill the image.
  // The top corners of each element cast the shadow along the sunlight, onto the floor.
  const floor = model.bounds.min.y;
  const box = corners(model.bounds);
  const shadows = model.elementBounds
    .filter((bounds) => !bounds.isEmpty())
    .flatMap((bounds) => corners(bounds).filter((corner) => corner.y === bounds.max.y))
    .map((corner) => corner.addScaledVector(light, -(corner.y - floor) / light.y));
  const camera = new THREE.PerspectiveCamera(
    LENS, width / height, radius / 100, radius * 100,
  );
  const half = Math.tan(THREE.MathUtils.degToRad(LENS) / 2);
  const target = center.clone();
  let distance = radius * 4;
  const extent = (points) => {
    let left = Infinity, right = -Infinity, low = Infinity, high = -Infinity;
    for (const corner of points) {
      const point = corner.clone().project(camera);
      left = Math.min(left, point.x);
      right = Math.max(right, point.x);
      low = Math.min(low, point.y);
      high = Math.max(high, point.y);
    }
    return { left, right, low, high };
  };
  for (let step = 0; step < 12; step++) {
    aim(camera, target, azimuth, distance);
    const body = extent(box);
    const all = extent([...box, ...shadows]);
    const middle = (body.left + body.right) / 2;
    const level = (body.low + body.high) / 2;
    const sideways = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0);
    target.addScaledVector(sideways, middle * distance * half * camera.aspect);
    target.y += level * distance * half / Math.cos(ELEVATION);
    const across = Math.max(all.right - middle, middle - all.left);
    const tall = Math.max(all.high - level, level - all.low);
    distance *= 0.4 + 0.6 * (Math.max(across, tall) / FILL);
  }
  aim(camera, target, azimuth, distance);
  // Edges fade when studs are small on screen, as in the renderer's images.
  const pixelsPerStud = (STUD / (2 * distance * half)) * height * supersample;
  const opacity = Math.min(0.42, Math.max(0.07, 0.03 * pixelsPerStud));
  model.edgeMaterials.plain.opacity = opacity;
  renderer.render(three, camera);
  const output = document.createElement("canvas");
  output.width = width;
  output.height = height;
  const context = output.getContext("2d", { alpha: false });
  context.imageSmoothingQuality = "high";
  context.drawImage(renderer.domElement, 0, 0, width, height);
  renderer.dispose();
  renderer.forceContextLoss();
  return output.toDataURL("image/png");
}

window.studio = { photograph };
"""
"""A module that renders a clean image of a scene with ``viewer.js``."""


async def serve(route: Route) -> None:
    """Answer the studio page's requests from bricky's render assets."""
    url = route.request.url
    name = url.removeprefix(STUDIO_ORIGIN)
    asset = RENDER_ASSETS.joinpath(*name.split("/"))
    if not url.startswith(STUDIO_ORIGIN) or not asset.is_file():
        await route.abort()
        return
    kind = "text/html" if name.endswith(".html") else "text/javascript"
    await route.fulfill(body=asset.read_bytes(), content_type=kind)


@asynccontextmanager
async def studio(settings: Settings) -> AsyncGenerator[Page]:
    """Open the studio's page in headless Chromium, and close it when done.

    Raises:
        RuntimeError: If the page reports an error.
    """
    problems: list[str] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=settings.render_browser,
            args=["--enable-unsafe-swiftshader"],
        )
        page = await browser.new_page()
        page.on("pageerror", lambda error: problems.append(str(error)))
        page.on(
            "console",
            lambda console: (
                problems.append(console.text) if console.type == "error" else None
            ),
        )
        await page.route("**/*", serve)
        await page.goto(STUDIO_ORIGIN + "render.html")
        await page.add_script_tag(type="module", content=STUDIO_PAGE)
        await page.wait_for_function("() => window.studio !== undefined")
        try:
            yield page
        finally:
            await browser.close()
    if problems:
        message = f"the studio's page failed: {'; '.join(problems)}"
        raise RuntimeError(message)


async def photograph(
    page: Page, scene: Scene, size: tuple[int, int], view: View
) -> bytes:
    """Render a scene in the studio with no text and return the image as PNG.

    Raises:
        RuntimeError: If the view is not a perspective, or the page returns no PNG.
    """
    if view not in AZIMUTHS:
        message = f"the studio renders perspectives only, not {view}"
        raise RuntimeError(message)
    width, height = size
    options = {
        "width": width,
        "height": height,
        "supersample": SUPERSAMPLE,
        "azimuth": AZIMUTHS[view],
        "background": "#ffffff",
    }
    url = await page.evaluate(
        "([scene, options]) => window.studio.photograph(scene, options)",
        [scene.model_dump(mode="json"), options],
    )
    if not isinstance(url, str) or not url.startswith(PNG_URL):
        message = "the studio returned no PNG"
        raise RuntimeError(message)
    return base64.b64decode(url.removeprefix(PNG_URL))


async def main() -> None:
    """Render every figure, then copy the benchmark inputs."""
    # Example scripts use the sample catalog too.
    os.environ["BRICKY_CATALOG"] = str(SAMPLE_CATALOG)
    IMAGES.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    wanted = set(sys.argv[1:])
    async with Renderer(settings.render_browser) as renderer, studio(settings) as page:
        for figure in FIGURES:
            if wanted and figure.name not in wanted:
                continue
            path = await render(figure, renderer, page, settings)
            if path is not None:
                print(f"rendered {path.relative_to(ROOT)}")
    for name, source in COPIES.items():
        shutil.copyfile(source, IMAGES / name)
        print(f"copied {source.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
