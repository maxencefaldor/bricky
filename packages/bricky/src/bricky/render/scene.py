"""What a render draws: a model resolved into boxes, shapes, studs, colours and marks.

A scene is plain data in base units (0.4 mm), shaped as compact arrays so a large model crosses into
the browser quickly. Parts made only of boxes are drawn as boxes; parts with other solids, such as
slopes and round parts, are drawn as shapes: corners, faces and the edges worth outlining. Building
a scene is pure Python; :mod:`bricky.render.browser` draws it.
"""

import fnmatch
import re
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from enum import IntFlag, StrEnum
from itertools import pairwise
from math import sqrt
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from bricky.analysis import Placed, World, build_world
from bricky.analysis.links import receptor_index
from bricky.catalog import Catalog, ColorType, ConnectorKind
from bricky.diagnostics import Region, Report, Severity
from bricky.errors import BrickyError
from bricky.geometry import AXES, Box, Convex, Vec3
from bricky.model import Model
from bricky.provenance import Frame, Provenance
from bricky.units import PLATE, STUD, STUD_HEIGHT, plates, studs, to_plates, to_studs


class View(StrEnum):
    """A picture of a model."""

    SHEET = "sheet"
    """The iso, front, right and top views on one image."""

    ISO = "iso"
    """Perspective from the south-east, above."""

    FRONT = "front"
    """Orthographic, looking north, with x and z rulers."""

    BACK = "back"
    """Orthographic, looking south, with x and z rulers."""

    LEFT = "left"
    """Orthographic, looking east, with y and z rulers."""

    RIGHT = "right"
    """Orthographic, looking west, with y and z rulers."""

    TOP = "top"
    """Orthographic plan, north up, with x and y rulers."""


class Flag(IntFlag):
    """How a part is drawn."""

    HIGHLIGHT = 1
    GHOST = 2
    ERROR = 4
    WARNING = 8
    CHANGED = 16
    """New or changed since the last build."""


_AXIS_CODES: Final = {vector: i for i, vector in enumerate(AXES.values())}
_CLIP: Final = re.compile(r"([xyz])\s*(<=|>=|<|>)\s*(-?\d+(?:\.\d+)?)")
_MAX_HIGHLIGHT_LABELS: Final = 40
_UNKNOWN_RGB: Final = "#FF00FF"


class Clip(BaseModel):
    """Keep only the part of a model on one side of a plane."""

    model_config = ConfigDict(frozen=True)

    axis: Literal["x", "y", "z"]
    keep: Literal["below", "above"]
    value: int = Field(description="Position of the plane, in base units.")

    @classmethod
    def parse(cls, text: str) -> Clip:
        """Parse a clip such as ``"z<130"`` (z in plates) or ``"x>=12"`` (x and y in studs).

        Raises:
            BrickyError: If the text is not a clip or lands off the grid.
        """
        match = _CLIP.fullmatch(text.strip())
        if match is None:
            msg = (
                f"cannot read clip {text!r}: write an axis, a comparison and a number, like 'z<130'"
            )
            raise BrickyError(msg)
        axis, operator, number = match.groups()
        try:
            value = (plates if axis == "z" else studs)(float(number))
        except ValueError as error:
            msg = f"clip {text!r}: {error}"
            raise BrickyError(msg) from None
        keep = "below" if operator.startswith("<") else "above"
        return cls.model_validate({"axis": axis, "keep": keep, "value": value})

    def __str__(self) -> str:
        unit = to_plates if self.axis == "z" else to_studs
        return f"{self.axis} {'<' if self.keep == 'below' else '>'} {unit(self.value):g}"


class SceneColor(BaseModel):
    """A colour the scene uses."""

    id: int
    name: str
    rgb: str
    type: ColorType


class Label(BaseModel):
    """Text pinned to a part."""

    part: int = Field(description="Index into Scene.parts.")
    text: str
    kind: Literal["error", "warning", "highlight"]


class Mark(BaseModel):
    """A box outlined on top of everything, such as a diagnostic's region."""

    box: tuple[int, int, int, int, int, int] = Field(description="Corners, in base units.")
    text: str
    kind: Literal["error", "warning"]


class Shape(BaseModel):
    """A part drawn from its faces, for parts that are not just boxes."""

    part: int = Field(description="Index into Scene.parts.")
    vertices: list[int] = Field(description="x, y, z of every corner, one after another.")
    faces: list[list[int]] = Field(
        description="Corner indices of each face, counter-clockwise seen from outside."
    )
    edges: list[int] = Field(
        description="Pairs of corner indices: the edges where the surface folds, to outline."
    )


class Scene(BaseModel):
    """Everything a render draws, in base units (0.4 mm)."""

    name: str
    title: str = Field(description="One line describing the model, shown above the views.")
    colors: list[SceneColor]
    parts: list[tuple[int, int]] = Field(description="Per part: colour index, flags.")
    uids: list[str] = Field(description="Per part: its uid.")
    boxes: list[tuple[int, int, int, int, int, int, int, int]] = Field(
        description=(
            "Per solid: x0, y0, z0, x1, y1, z1, part index, and a mask of the faces to draw "
            "(bits -x +x -y +y -z +z); faces pressed flat against opaque neighbours are left out."
        )
    )
    shapes: list[Shape] = Field(
        default_factory=list, description="Parts that are not just boxes, by their faces."
    )
    studs: list[tuple[int, int, int, int, int]] = Field(
        description="Per stud: x, y, z of its base, axis code (+x -x +y -y +z -z), part index."
    )
    labels: list[Label] = Field(default_factory=list)
    marks: list[Mark] = Field(default_factory=list)
    clips: list[Clip] = Field(default_factory=list)
    bounds: tuple[int, int, int, int, int, int] = Field(
        description="Corners of what the views show: all solids and stud tips, cut by the clips."
    )


def build_scene(  # noqa: PLR0913 - keyword-only options, one per concern
    model: Model,
    catalog: Catalog,
    *,
    provenance: Provenance | None = None,
    report: Report | None = None,
    highlight: Sequence[str] = (),
    clips: Sequence[Clip] = (),
    changed: Sequence[str] = (),
    cull: bool = True,
) -> Scene:
    """Resolve a model into the scene a render draws.

    Args:
        model: The model.
        catalog: Catalog to resolve parts and colours against.
        provenance: Where the build script placed each element; needed by ``@`` selectors.
        report: A check report whose errors and warnings are marked on the parts they name.
        highlight: Selectors for parts to highlight; the rest are drawn faintly. A selector is a
            uid pattern such as ``"lintel*"`` or ``"tower/*"``, or ``@`` followed by a function
            name, a file or a file and line of the build script, such as ``"@horseshoe"`` or
            ``"@stonehenge.py:142"``.
        clips: Planes that cut the model, to look inside it.
        changed: Uids of parts that are new or changed since the last build, to mark.
        cull: Leave out faces pressed against opaque neighbours. Turn it off for viewers that
            cut the model interactively, where buried faces can come into view.

    Raises:
        BrickyError: If the model has no parts to draw, or a selector matches nothing.
    """
    world = build_world(model, catalog)
    placed = world.placed
    if not placed:
        msg = "nothing to render: the model has no parts the catalog knows"
        raise BrickyError(msg)
    colors, color_index = _colors(catalog, placed)
    flags = [Flag(0)] * len(placed)
    labels: list[Label] = []
    marks: list[Mark] = []
    if report is not None:
        _mark_diagnostics(report, placed, flags, labels, marks)
    if changed:
        new = set(changed)
        for i, p in enumerate(placed):
            if p.uid in new:
                flags[i] |= Flag.CHANGED
    if highlight:
        chosen = _select(model, [p.uid for p in placed], provenance, highlight)
        _highlight(chosen, placed, flags, labels)
    shaped = [i for i, p in enumerate(placed) if any(isinstance(s, Convex) for s in p.solids)]
    boxes = _boxes(catalog, placed, flags, clips, cull=cull, skip=set(shaped))
    shapes = [_shape(i, placed[i]) for i in shaped]
    studs_ = _exposed_studs(world)
    body = Box.bounding(p.bounds for p in placed)
    axes = list(AXES.values())
    tips = [Vec3(x, y, z) + axes[axis] * STUD_HEIGHT for x, y, z, axis, _ in studs_]
    framed = Box.bounding([body, *(Box(tip, tip) for tip in tips)])
    bounds = _cut(framed, clips)
    return Scene(
        name=model.name,
        title=_title(model, _cut(body, clips), len(placed), report),
        colors=colors,
        parts=[(color_index[p.color], int(flags[i])) for i, p in enumerate(placed)],
        uids=[p.uid for p in placed],
        boxes=boxes,
        shapes=shapes,
        studs=studs_,
        labels=labels,
        marks=marks,
        clips=list(clips),
        bounds=(*bounds.lo, *bounds.hi),
    )


def _colors(catalog: Catalog, placed: Sequence[Placed]) -> tuple[list[SceneColor], dict[int, int]]:
    """The colours the parts use, each once, and each colour id's index in that list."""
    color_ids = sorted({p.color for p in placed})
    colors = []
    for color_id in color_ids:
        color = catalog.color(color_id)
        colors.append(
            SceneColor(id=color_id, name=color.name, rgb=color.rgb, type=color.type)
            if color is not None
            else SceneColor(
                id=color_id, name=f"unknown {color_id}", rgb=_UNKNOWN_RGB, type=ColorType.SOLID
            )
        )
    return colors, {color_id: i for i, color_id in enumerate(color_ids)}


def _mark_diagnostics(
    report: Report,
    placed: Sequence[Placed],
    flags: list[Flag],
    labels: list[Label],
    marks: list[Mark],
) -> None:
    """Flag the parts each error and warning names, label the first, and outline its region."""
    index = {p.uid: i for i, p in enumerate(placed)}
    for diagnostic in report.diagnostics:
        kind = _mark_kind(diagnostic.severity)
        if kind is None:
            continue
        flag = Flag.ERROR if kind == "error" else Flag.WARNING
        members = [index[uid] for uid in diagnostic.elements if uid in index]
        for i in members:
            flags[i] |= flag
        if members:
            text = f"{diagnostic.code} {placed[members[0]].uid}"
            labels.append(Label(part=members[0], text=text, kind=kind))
        if diagnostic.region is not None:
            marks.append(Mark(box=_box(diagnostic.region), text=diagnostic.code, kind=kind))


def _highlight(
    chosen: set[int], placed: Sequence[Placed], flags: list[Flag], labels: list[Label]
) -> None:
    """Highlight the chosen parts and draw the others faintly, unless a diagnostic marks them."""
    for i in range(len(placed)):
        if i in chosen:
            flags[i] |= Flag.HIGHLIGHT
        elif not flags[i] & (Flag.ERROR | Flag.WARNING):
            flags[i] |= Flag.GHOST
    if len(chosen) <= _MAX_HIGHLIGHT_LABELS:
        labels.extend(Label(part=i, text=placed[i].uid, kind="highlight") for i in sorted(chosen))


def _boxes(  # noqa: PLR0913 - keyword-only options, one per concern
    catalog: Catalog,
    placed: Sequence[Placed],
    flags: Sequence[Flag],
    clips: Sequence[Clip],
    *,
    cull: bool,
    skip: set[int],
) -> list[tuple[int, int, int, int, int, int, int, int]]:
    """Every box of every part not drawn as a shape, with the mask of faces worth drawing."""
    solids = [
        (solid, i)
        for i, p in enumerate(placed)
        if i not in skip
        for solid in p.solids
        if isinstance(solid, Box)
    ]
    if cull:
        # Only parts that are opaque, drawn solid and wholly kept by the cut can hide a face.
        opaque = [
            catalog_type(catalog, placed[i].color) is not ColorType.TRANSPARENT
            and not flags[i] & Flag.GHOST
            and all(_kept(solid, clip) for clip in clips)
            for solid, i in solids
        ]
        masks = visible_faces([solid for solid, _ in solids], opaque)
    else:
        masks = [ALL_FACES] * len(solids)
    return [
        (solid.lo.x, solid.lo.y, solid.lo.z, solid.hi.x, solid.hi.y, solid.hi.z, i, mask)
        for (solid, i), mask in zip(solids, masks, strict=True)
    ]


_CREASE: Final = 0.94
"""Faces meeting at a cosine below this, about 20 degrees, fold visibly: their edge is drawn."""


def _shape(index: int, part: Placed) -> Shape:
    """A part's solids as one surface: the faces two solids share are inside, and left out."""
    faces: list[tuple[tuple[int, int, int], ...]] = []
    for solid in part.solids:
        convex = solid if isinstance(solid, Convex) else solid.as_convex()
        faces.extend(tuple(convex.vertices[i].as_tuple() for i in face) for face in convex.faces)
    inside = Counter(frozenset(face) for face in faces)
    outer = [face for face in faces if inside[frozenset(face)] == 1]
    corners: dict[tuple[int, int, int], int] = {}
    indexed = [[corners.setdefault(point, len(corners)) for point in face] for face in outer]
    normals: dict[tuple[int, int], list[tuple[float, float, float]]] = {}
    for face, points in zip(indexed, outer, strict=True):
        normal = _unit(_newell(points))
        for a, b in zip(face, [*face[1:], face[0]], strict=True):
            normals.setdefault((min(a, b), max(a, b)), []).append(normal)
    edges = [
        corner
        for edge, around in normals.items()
        if len(around) != 2 or _dot(*around) < _CREASE  # noqa: PLR2004 - an edge joins two faces
        for corner in edge
    ]
    return Shape(
        part=index,
        vertices=[c for point in corners for c in point],
        faces=indexed,
        edges=edges,
    )


def _newell(points: Sequence[tuple[int, int, int]]) -> tuple[int, int, int]:
    x = y = z = 0
    for p, q in zip(points, [*points[1:], points[0]], strict=True):
        x += (p[1] - q[1]) * (p[2] + q[2])
        y += (p[2] - q[2]) * (p[0] + q[0])
        z += (p[0] - q[0]) * (p[1] + q[1])
    return x, y, z


def _unit(vector: tuple[int, int, int]) -> tuple[float, float, float]:
    length = sqrt(sum(c * c for c in vector)) or 1.0
    return vector[0] / length, vector[1] / length, vector[2] / length


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _exposed_studs(world: World) -> list[tuple[int, int, int, int, int]]:
    """Every stud not seated in another part's receptor, where it would be hidden."""
    receptors = receptor_index(world)
    return [
        (c.pos.x, c.pos.y, c.pos.z, _AXIS_CODES[c.normal], i)
        for i, p in enumerate(world.placed)
        for c in p.connectors
        if c.kind is ConnectorKind.STUD
        and not any(j != i for j in receptors.get((c.pos, -c.normal), ()))
    ]


def _cut(bounds: Box, clips: Sequence[Clip]) -> Box:
    """Shrink the bounds to what the clips keep, so views frame the part left to see.

    Raises:
        BrickyError: If the clips keep nothing.
    """
    lo, hi = list(bounds.lo), list(bounds.hi)
    for clip in clips:
        axis = "xyz".index(clip.axis)
        if clip.keep == "below":
            hi[axis] = min(hi[axis], clip.value)
        else:
            lo[axis] = max(lo[axis], clip.value)
    if any(a >= b for a, b in zip(lo, hi, strict=True)):
        cut = ", ".join(str(clip) for clip in clips)
        msg = f"the cut {cut} leaves nothing of the model to draw"
        raise BrickyError(msg)
    return Box(Vec3(*lo), Vec3(*hi))


def _mark_kind(severity: Severity) -> Literal["error", "warning"] | None:
    if severity is Severity.ERROR:
        return "error"
    if severity is Severity.WARNING:
        return "warning"
    return None


def _box(region: Region) -> tuple[int, int, int, int, int, int]:
    return (
        round(region.x[0] * STUD),
        round(region.y[0] * STUD),
        round(region.z[0] * PLATE),
        round(region.x[1] * STUD),
        round(region.y[1] * STUD),
        round(region.z[1] * PLATE),
    )


def _title(model: Model, bounds: Box, count: int, report: Report | None) -> str:
    size = bounds.size
    title = (
        f"{model.name}: {count} element{'' if count == 1 else 's'}, "
        f"{to_studs(size.x):g} x {to_studs(size.y):g} studs, "
        f"{to_plates(size.z):g} plates tall"
    )
    if report is not None:
        title += f"; check: {report.errors} errors, {report.warnings} warnings"
    return title


def _select(
    model: Model,
    uids: Sequence[str],
    provenance: Provenance | None,
    selectors: Sequence[str],
) -> set[int]:
    chosen: set[int] = set()
    for selector in selectors:
        if selector.startswith("@"):
            if provenance is None:
                msg = (
                    f"selector {selector!r} needs the model's source map, which `bricky build` "
                    "writes beside the model"
                )
                raise BrickyError(msg)
            matches = _frame_matcher(selector[1:])
            hits = {
                i
                for i, uid in enumerate(uids)
                if any(matches(frame) for frame in _frames(provenance, model, uid))
            }
        else:
            hits = {i for i, uid in enumerate(uids) if fnmatch.fnmatchcase(uid, selector)}
        if not hits:
            msg = f"highlight {selector!r} matches no part"
            raise BrickyError(msg)
        chosen |= hits
    return chosen


def _frames(provenance: Provenance, model: Model, uid: str) -> Iterator[Frame]:
    for source in provenance.trace(model, uid).sources():
        yield from source.frames


def _frame_matcher(spec: str) -> Callable[[Frame], bool]:
    file, _, line = spec.rpartition(":")
    if file and line.isdigit():
        number = int(line)
        return lambda frame: frame.line == number and _same_file(frame.file, file)
    if spec.endswith(".py"):
        return lambda frame: _same_file(frame.file, spec)
    return lambda frame: frame.function == spec


def _same_file(recorded: str, wanted: str) -> bool:
    """Whether a recorded script path is the wanted one, matching whole trailing path segments."""
    recorded_parts = recorded.replace("\\", "/").split("/")
    wanted_parts = wanted.replace("\\", "/").split("/")
    return recorded_parts[-len(wanted_parts) :] == wanted_parts


ALL_FACES: Final = 0b111111
"""Face mask with every face drawn."""


def catalog_type(catalog: Catalog, color_id: int) -> ColorType:
    """The type of a colour, treating unknown colors as solid."""
    color = catalog.color(color_id)
    return color.type if color is not None else ColorType.SOLID


def _kept(box: Box, clip: Clip) -> bool:
    """Whether a box lies wholly on the side of a clip plane that stays visible."""
    axis = "xyz".index(clip.axis)
    if clip.keep == "below":
        return tuple(box.hi)[axis] <= clip.value
    return tuple(box.lo)[axis] >= clip.value


def visible_faces(boxes: Sequence[Box], opaque: Sequence[bool]) -> list[int]:
    """Return, per box, a mask of the faces not pressed flat against opaque boxes.

    Bit ``2 * axis`` is the low face along that axis and bit ``2 * axis + 1`` the high face. A face
    is hidden when the opaque boxes whose opposite faces lie in the same plane cover it entirely.
    """
    corners = [(tuple(box.lo), tuple(box.hi)) for box in boxes]
    # Opaque faces by plane (axis, which side of their box, coordinate), bucketed on a coarse grid.
    planes: dict[tuple[int, int, int], dict[tuple[int, int], list[int]]] = {}
    for j, (lo, hi) in enumerate(corners):
        if not opaque[j]:
            continue
        for axis in range(3):
            u, v = _others(axis)
            for side, coordinate in ((0, lo[axis]), (1, hi[axis])):
                cells = planes.setdefault((axis, side, coordinate), {})
                for cell in _cells(lo[u], lo[v], hi[u], hi[v]):
                    cells.setdefault(cell, []).append(j)
    masks: list[int] = []
    for i, (lo, hi) in enumerate(corners):
        mask = 0
        for axis in range(3):
            u, v = _others(axis)
            face = (lo[u], lo[v], hi[u], hi[v])
            # A low face meets the high faces of the boxes below it, and vice versa.
            for side, coordinate, facing in ((0, lo[axis], 1), (1, hi[axis], 0)):
                cells = planes.get((axis, facing, coordinate))
                candidates = (
                    {j for cell in _cells(*face) for j in cells.get(cell, ())} - {i}
                    if cells
                    else set()
                )
                rects = [
                    (corners[j][0][u], corners[j][0][v], corners[j][1][u], corners[j][1][v])
                    for j in candidates
                ]
                if not _covered(face, rects):
                    mask |= 1 << (2 * axis + side)
        masks.append(mask)
    return masks


_CELL: Final = 4 * STUD


def _others(axis: int) -> tuple[int, int]:
    u, v = (a for a in range(3) if a != axis)
    return u, v


def _cells(u0: int, v0: int, u1: int, v1: int) -> Iterator[tuple[int, int]]:
    for a in range(u0 // _CELL, (u1 - 1) // _CELL + 1):
        for b in range(v0 // _CELL, (v1 - 1) // _CELL + 1):
            yield a, b


def _covered(face: tuple[int, int, int, int], rects: Sequence[tuple[int, int, int, int]]) -> bool:
    """Whether the union of rectangles covers a face rectangle, by coordinate compression."""
    u0, v0, u1, v1 = face
    touching = [r for r in rects if r[0] < u1 and u0 < r[2] and r[1] < v1 and v0 < r[3]]
    if not touching:
        return False
    us = sorted(
        {
            u0,
            u1,
            *(min(max(r[0], u0), u1) for r in touching),
            *(min(max(r[2], u0), u1) for r in touching),
        }
    )
    vs = sorted(
        {
            v0,
            v1,
            *(min(max(r[1], v0), v1) for r in touching),
            *(min(max(r[3], v0), v1) for r in touching),
        }
    )
    for a, b in pairwise(us):
        for c, d in pairwise(vs):
            if not any(r[0] <= a and b <= r[2] and r[1] <= c and d <= r[3] for r in touching):
                return False
    return True
