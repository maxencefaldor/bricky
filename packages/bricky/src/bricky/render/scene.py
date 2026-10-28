"""Scenes: a model resolved into the boxes, meshes, studs, colors and marks a render draws.

A scene is plain data in base units (0.4 mm), laid out as compact arrays so a large model crosses
into the browser quickly. An element made only of boxes appears as boxes. An element with other
solids, such as a slope or a round part, appears as a mesh: its corners, its faces and the edges
worth outlining. :func:`build_scene` is pure Python, and :mod:`bricky.render.browser` draws its
result.
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

from bricky.analysis import PlacedElement, World, build_world
from bricky.analysis.connections import anti_stud_index
from bricky.catalog import Catalog, ColorType, ConnectorKind
from bricky.diagnostics import Region, Report, Severity
from bricky.errors import BrickyError
from bricky.geometry import AXES, Box, Convex, Vector
from bricky.model import Model
from bricky.provenance import Frame, Provenance
from bricky.units import PLATE, STUD, STUD_HEIGHT, plates, studs, to_plates, to_studs


class View(StrEnum):
    """One picture of a scene."""

    SHEET = "sheet"
    """The perspective, front, right and top views on one image."""

    PERSPECTIVE = "perspective"
    """In perspective, from above the south-east."""

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
    """How a render draws an element."""

    HIGHLIGHT = 1
    """Chosen by a highlight selector."""

    GHOST = 2
    """Drawn faintly: outside a highlight, and named by no error or warning."""

    ERROR = 4
    """Named by an error."""

    WARNING = 8
    """Named by a warning."""

    CHANGED = 16
    """New or changed since the last build."""


_AXIS_CODES: Final = {vector: i for i, vector in enumerate(AXES.values())}
_CLIP: Final = re.compile(r"([xyz])\s*(<=|>=|<|>)\s*(-?\d+(?:\.\d+)?)")
_MAX_HIGHLIGHT_LABELS: Final = 40
_UNKNOWN_RGB: Final = "#FF00FF"


class Clip(BaseModel):
    """A plane and the side of it that a render keeps, to look inside a model."""

    model_config = ConfigDict(frozen=True)

    axis: Literal["x", "y", "z"]
    keep: Literal["below", "above"]
    value: int = Field(description="The plane's position along the axis, in base units.")

    @classmethod
    def parse(cls, text: str) -> Clip:
        """Parse a clip such as ``"z<130"`` (z in plates) or ``"x>=12"`` (x and y in studs).

        Raises:
            BrickyError: If the text is not a clip or lands off the grid.
        """
        match = _CLIP.fullmatch(text.strip())
        if match is None:
            message = (
                f"cannot read clip {text!r}: a clip is an axis, a comparison and a number, "
                "such as 'z<130'"
            )
            raise BrickyError(message)
        axis, operator, number = match.groups()
        try:
            value = (plates if axis == "z" else studs)(float(number))
        except ValueError as error:
            message = f"clip {text!r}: {error}"
            raise BrickyError(message) from None
        keep = "below" if operator.startswith("<") else "above"
        return cls.model_validate({"axis": axis, "keep": keep, "value": value})

    def __str__(self) -> str:
        unit = to_plates if self.axis == "z" else to_studs
        return f"{self.axis} {'<' if self.keep == 'below' else '>'} {unit(self.value):g}"


class SceneColor(BaseModel):
    """A color the scene uses."""

    id: int
    name: str
    rgb: str
    type: ColorType


class Label(BaseModel):
    """Text pinned to an element."""

    element: int = Field(description="Index into Scene.elements.")
    text: str
    kind: Literal["error", "warning", "highlight"]


class Mark(BaseModel):
    """A diagnostic's region: a box outlined over everything else."""

    box: tuple[int, int, int, int, int, int] = Field(description="Corners, in base units.")
    text: str
    kind: Literal["error", "warning"]


class Mesh(BaseModel):
    """An element drawn by its faces, for an element with solids other than boxes."""

    element: int = Field(description="Index into Scene.elements.")
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
    elements: list[tuple[int, int]] = Field(
        description="Per element: its color's index in colors, and its flags."
    )
    uids: list[str] = Field(description="Per element: its uid.")
    boxes: list[tuple[int, int, int, int, int, int, int, int]] = Field(
        description=(
            "Per box: x0, y0, z0, x1, y1, z1, element index, and a mask of the faces to draw "
            "(bits -x +x -y +y -z +z) that leaves out faces pressed flat against opaque neighbors."
        )
    )
    meshes: list[Mesh] = Field(
        default_factory=list, description="Elements with solids other than boxes, by their faces."
    )
    studs: list[tuple[int, int, int, int, int]] = Field(
        description="Per stud not seated in an anti-stud: x, y, z of its base, axis code "
        "(+x -x +y -y +z -z), element index."
    )
    labels: list[Label] = Field(default_factory=list)
    marks: list[Mark] = Field(default_factory=list)
    clips: list[Clip] = Field(default_factory=list)
    bounds: tuple[int, int, int, int, int, int] = Field(
        description="Corners of what the views show: all solids and stud tips, within the clips."
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
        catalog: The catalog that resolves parts and colors.
        provenance: The script lines that placed each element; ``@`` selectors need it.
        report: A report whose errors and warnings mark the elements they name.
        highlight: Selectors of the elements to highlight; a render draws the rest faintly. A
            selector is a uid pattern such as ``"lintel*"`` or ``"tower/*"``, or ``@`` followed
            by a function name, a file, or a file and line of the build script, such as
            ``"@horseshoe"`` or ``"@stonehenge.py:142"``.
        clips: The clips that keep part of the model, to look inside it.
        changed: The uids of elements new or changed since the last build, to mark.
        cull: Whether to leave out faces pressed against opaque neighbors. A viewer that clips
            the model interactively sets it to false, as clipping can bring buried faces into view.

    Raises:
        BrickyError: If the model has no element to draw, a selector matches nothing, or the clips
            keep nothing.
    """
    world = build_world(model, catalog)
    elements = world.elements
    if not elements:
        message = "nothing to render: the model has no element the catalog can place"
        raise BrickyError(message)
    colors, color_index = _colors(catalog, elements)
    flags = [Flag(0)] * len(elements)
    labels: list[Label] = []
    marks: list[Mark] = []
    if report is not None:
        _mark_diagnostics(report, elements, flags, labels, marks)
    if changed:
        new = set(changed)
        for i, element in enumerate(elements):
            if element.uid in new:
                flags[i] |= Flag.CHANGED
    if highlight:
        chosen = _select(model, [element.uid for element in elements], provenance, highlight)
        _highlight(chosen, elements, flags, labels)
    meshed = [
        i
        for i, element in enumerate(elements)
        if any(isinstance(solid, Convex) for solid in element.solids)
    ]
    boxes = _boxes(catalog, elements, flags, clips, cull=cull, skip=set(meshed))
    meshes = [_mesh(i, elements[i]) for i in meshed]
    studs = _exposed_studs(world)
    body = Box.bounding(element.bounds for element in elements)
    axes = list(AXES.values())
    tips = [Vector(x, y, z) + axes[axis] * STUD_HEIGHT for x, y, z, axis, _ in studs]
    framed = Box.bounding([body, *(Box(tip, tip) for tip in tips)])
    bounds = _clipped(framed, clips)
    return Scene(
        name=model.name,
        title=_title(model, _clipped(body, clips), len(elements), report),
        colors=colors,
        elements=[(color_index[e.color], int(flags[i])) for i, e in enumerate(elements)],
        uids=[element.uid for element in elements],
        boxes=boxes,
        meshes=meshes,
        studs=studs,
        labels=labels,
        marks=marks,
        clips=list(clips),
        bounds=(*bounds.min, *bounds.max),
    )


def _colors(
    catalog: Catalog, elements: Sequence[PlacedElement]
) -> tuple[list[SceneColor], dict[int, int]]:
    """The colors the elements use, each once, and each color id's index in that list."""
    color_ids = sorted({element.color for element in elements})
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
    elements: Sequence[PlacedElement],
    flags: list[Flag],
    labels: list[Label],
    marks: list[Mark],
) -> None:
    """Flag the elements each error and warning names, label the first, and outline its region."""
    index = {element.uid: i for i, element in enumerate(elements)}
    for diagnostic in report.diagnostics:
        kind = _mark_kind(diagnostic.severity)
        if kind is None:
            continue
        flag = Flag.ERROR if kind == "error" else Flag.WARNING
        members = [index[uid] for uid in diagnostic.elements if uid in index]
        for i in members:
            flags[i] |= flag
        if members:
            text = f"{diagnostic.code} {elements[members[0]].uid}"
            labels.append(Label(element=members[0], text=text, kind=kind))
        if diagnostic.region is not None:
            marks.append(Mark(box=_box(diagnostic.region), text=diagnostic.code, kind=kind))


def _highlight(
    chosen: set[int], elements: Sequence[PlacedElement], flags: list[Flag], labels: list[Label]
) -> None:
    """Highlight the chosen elements and draw the others faintly, unless a diagnostic marks them."""
    for i in range(len(elements)):
        if i in chosen:
            flags[i] |= Flag.HIGHLIGHT
        elif not flags[i] & (Flag.ERROR | Flag.WARNING):
            flags[i] |= Flag.GHOST
    if len(chosen) <= _MAX_HIGHLIGHT_LABELS:
        labels.extend(
            Label(element=i, text=elements[i].uid, kind="highlight") for i in sorted(chosen)
        )


def _boxes(  # noqa: PLR0913 - keyword-only options, one per concern
    catalog: Catalog,
    elements: Sequence[PlacedElement],
    flags: Sequence[Flag],
    clips: Sequence[Clip],
    *,
    cull: bool,
    skip: set[int],
) -> list[tuple[int, int, int, int, int, int, int, int]]:
    """Return every box of every element not drawn as a mesh, with the mask of its visible faces."""
    solids = [
        (solid, i)
        for i, element in enumerate(elements)
        if i not in skip
        for solid in element.solids
        if isinstance(solid, Box)
    ]
    if cull:
        # A box hides a face only when its element is opaque and drawn in full, and the clips keep
        # all of the box.
        opaque = [
            _color_type(catalog, elements[i].color) is not ColorType.TRANSPARENT
            and not flags[i] & Flag.GHOST
            and all(_kept(solid, clip) for clip in clips)
            for solid, i in solids
        ]
        masks = visible_faces([solid for solid, _ in solids], opaque)
    else:
        masks = [ALL_FACES] * len(solids)
    return [
        (solid.min.x, solid.min.y, solid.min.z, solid.max.x, solid.max.y, solid.max.z, i, mask)
        for (solid, i), mask in zip(solids, masks, strict=True)
    ]


_CREASE: Final = 0.94
"""The cosine below which two faces' normals mark a visible fold, about 20 degrees apart: the mesh
outlines the edge between them."""


def _mesh(index: int, element: PlacedElement) -> Mesh:
    """Return an element's solids as one surface, leaving out the faces two solids share."""
    faces: list[tuple[tuple[int, int, int], ...]] = []
    for solid in element.solids:
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
    return Mesh(
        element=index,
        vertices=[coordinate for point in corners for coordinate in point],
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
    length = sqrt(sum(component * component for component in vector)) or 1.0
    return vector[0] / length, vector[1] / length, vector[2] / length


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _exposed_studs(world: World) -> list[tuple[int, int, int, int, int]]:
    """Return every stud that no other element's anti-stud hides."""
    anti_studs = anti_stud_index(world)
    return [
        (
            connector.position.x,
            connector.position.y,
            connector.position.z,
            _AXIS_CODES[connector.normal],
            i,
        )
        for i, element in enumerate(world.elements)
        for connector in element.connectors
        if connector.kind is ConnectorKind.STUD
        and not any(j != i for j in anti_studs.get((connector.position, -connector.normal), ()))
    ]


def _clipped(bounds: Box, clips: Sequence[Clip]) -> Box:
    """Shrink the bounds to what the clips keep, so the views frame what remains.

    Raises:
        BrickyError: If the clips keep nothing.
    """
    low, high = list(bounds.min), list(bounds.max)
    for clip in clips:
        axis = "xyz".index(clip.axis)
        if clip.keep == "below":
            high[axis] = min(high[axis], clip.value)
        else:
            low[axis] = max(low[axis], clip.value)
    if any(a >= b for a, b in zip(low, high, strict=True)):
        listed = ", ".join(str(clip) for clip in clips)
        which = f"the clip {listed} leaves" if len(clips) == 1 else f"the clips {listed} leave"
        message = f"{which} nothing of the model to draw"
        raise BrickyError(message)
    return Box(Vector(*low), Vector(*high))


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
        title += f"; check: {_count(report.errors, 'error')}, {_count(report.warnings, 'warning')}"
    return title


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


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
                message = (
                    f"selector {selector!r} needs the model's source map, which `bricky build` "
                    "writes beside the model"
                )
                raise BrickyError(message)
            matches = _frame_matcher(selector[1:])
            hits = {
                i
                for i, uid in enumerate(uids)
                if any(matches(frame) for frame in _frames(provenance, model, uid))
            }
        else:
            hits = {i for i, uid in enumerate(uids) if fnmatch.fnmatchcase(uid, selector)}
        if not hits:
            message = f"highlight {selector!r} matches no element"
            raise BrickyError(message)
        chosen |= hits
    return chosen


def _frames(provenance: Provenance, model: Model, uid: str) -> Iterator[Frame]:
    for source in provenance.trace(model, uid).sources():
        yield from source.frames


def _frame_matcher(target: str) -> Callable[[Frame], bool]:
    file, _, line = target.rpartition(":")
    if file and line.isdigit():
        number = int(line)
        return lambda frame: frame.line == number and _same_file(frame.file, file)
    if target.endswith(".py"):
        return lambda frame: _same_file(frame.file, target)
    return lambda frame: frame.function == target


def _same_file(recorded: str, wanted: str) -> bool:
    """Whether a recorded script path is the wanted one, matching whole trailing path segments."""
    recorded_segments = recorded.replace("\\", "/").split("/")
    wanted_segments = wanted.replace("\\", "/").split("/")
    return recorded_segments[-len(wanted_segments) :] == wanted_segments


ALL_FACES: Final = 0b111111
"""Face mask with every face drawn."""


def _color_type(catalog: Catalog, color_id: int) -> ColorType:
    """Return the type of a color, treating an unknown color as solid."""
    color = catalog.color(color_id)
    return color.type if color is not None else ColorType.SOLID


def _kept(box: Box, clip: Clip) -> bool:
    """Whether a box lies wholly on the side of a clip's plane that the clip keeps."""
    axis = "xyz".index(clip.axis)
    if clip.keep == "below":
        return tuple(box.max)[axis] <= clip.value
    return tuple(box.min)[axis] >= clip.value


def visible_faces(boxes: Sequence[Box], opaque: Sequence[bool]) -> list[int]:
    """Return, per box, a mask of the faces not pressed flat against opaque boxes.

    Bit ``2 * axis`` is the low face along that axis and bit ``2 * axis + 1`` the high face. The
    opaque boxes whose opposite faces lie in a face's plane hide the face when they cover it whole.
    """
    corners = [(tuple(box.min), tuple(box.max)) for box in boxes]
    # Opaque faces by plane (axis, which side of their box, coordinate), in buckets of a grid.
    planes: dict[tuple[int, int, int], dict[tuple[int, int], list[int]]] = {}
    for j, (low, high) in enumerate(corners):
        if not opaque[j]:
            continue
        for axis in range(3):
            u, v = _others(axis)
            for side, coordinate in ((0, low[axis]), (1, high[axis])):
                buckets = planes.setdefault((axis, side, coordinate), {})
                for bucket in _buckets(low[u], low[v], high[u], high[v]):
                    buckets.setdefault(bucket, []).append(j)
    masks: list[int] = []
    for i, (low, high) in enumerate(corners):
        mask = 0
        for axis in range(3):
            u, v = _others(axis)
            face = (low[u], low[v], high[u], high[v])
            # A low face meets the high faces of the boxes below it, and vice versa.
            for side, coordinate, facing in ((0, low[axis], 1), (1, high[axis], 0)):
                buckets = planes.get((axis, facing, coordinate))
                candidates = (
                    {j for bucket in _buckets(*face) for j in buckets.get(bucket, ())} - {i}
                    if buckets
                    else set()
                )
                rectangles = [
                    (corners[j][0][u], corners[j][0][v], corners[j][1][u], corners[j][1][v])
                    for j in candidates
                ]
                if not _covered(face, rectangles):
                    mask |= 1 << (2 * axis + side)
        masks.append(mask)
    return masks


_BUCKET: Final = 4 * STUD


def _others(axis: int) -> tuple[int, int]:
    u, v = (a for a in range(3) if a != axis)
    return u, v


def _buckets(u0: int, v0: int, u1: int, v1: int) -> Iterator[tuple[int, int]]:
    for a in range(u0 // _BUCKET, (u1 - 1) // _BUCKET + 1):
        for b in range(v0 // _BUCKET, (v1 - 1) // _BUCKET + 1):
            yield a, b


def _covered(
    face: tuple[int, int, int, int], rectangles: Sequence[tuple[int, int, int, int]]
) -> bool:
    """Whether the union of rectangles covers a face rectangle, by coordinate compression."""
    u0, v0, u1, v1 = face
    touching = [
        rectangle
        for rectangle in rectangles
        if rectangle[0] < u1 and u0 < rectangle[2] and rectangle[1] < v1 and v0 < rectangle[3]
    ]
    if not touching:
        return False
    us = sorted(
        {
            u0,
            u1,
            *(min(max(rectangle[0], u0), u1) for rectangle in touching),
            *(min(max(rectangle[2], u0), u1) for rectangle in touching),
        }
    )
    vs = sorted(
        {
            v0,
            v1,
            *(min(max(rectangle[1], v0), v1) for rectangle in touching),
            *(min(max(rectangle[3], v0), v1) for rectangle in touching),
        }
    )
    for a, b in pairwise(us):
        for c, d in pairwise(vs):
            if not any(
                rectangle[0] <= a and b <= rectangle[2] and rectangle[1] <= c and d <= rectangle[3]
                for rectangle in touching
            ):
                return False
    return True
