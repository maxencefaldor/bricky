"""Shapes from the LDraw parts library: a part's body as boxes, and its studs and anti-studs.

LDraw describes each part as a surface, triangles and quads, plus references to other files
(subparts and primitives), each placed by a 3 x 4 transform. Its unit, the LDraw unit, is 0.4 mm:
bricky's base unit, so coordinates carry over one to one. Its y axis points down.

:func:`ldraw_shape` converts one part:

1. **Flatten.** Follow every reference, composing transforms, into triangles in the part's frame.
   A reference to a stud primitive, such as ``stud.dat``, becomes a stud: where its base sits and
   which way it points. Stud geometry is not body: bricky's studs are connectors.
2. **Rotate.** LDraw (x, y, z) becomes bricky (x, z, -y), so LDraw's down becomes bricky's -z.
3. **Voxelize.** Sample the body every 2 units (0.8 mm). A sample is inside when rays along x, y
   and z, at least two of the three, cross the surface an odd number of times.
4. **Anti-studs.** On the bottom face, at every stud position, where the part leaves an opening a
   stud fits into, walled in on all four sides.
5. **Fill.** The openings over anti-studs become body, as bricky's families model them: a stud
   pushing in anywhere else hits the part.
6. **Merge** the samples into as few boxes as possible, from the minimum corner at the origin.

The result is exact on the 2-unit grid, which holds every wall, height and stud of ordinary parts;
curved surfaces become steps. The part's size is its surface's bounding box, so a round part fills
its square. Parts are converted as LDraw orients them.
"""

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray

from bricky.catalog.models import BoxesShape, CatalogPart, Family
from bricky.errors import BrickyError

type Floats = NDArray[np.float64]
type Mask = NDArray[np.bool_]

VOXEL: Final = 2
"""Sampling step, in LDraw units (and base units): 0.8 mm, which divides every stud position."""

_STUD_ROOM: Final = 4
"""How high above an anti-stud's position the part must be open, and how wide around it: the
stud is 4 units tall, and the narrowest openings that grip one are 4 units wide."""

STUD_PRIMITIVES: Final = frozenset(
    {
        "stud.dat",
        "studa.dat",
        "stud2.dat",
        "stud2a.dat",
        "stud6.dat",
        "stud6a.dat",
        "stud10.dat",
        "stud15.dat",
    }
)
"""LDraw primitives that draw a stud a part can connect with, standing on the primitive's origin
and pointing along its -y axis. Tubes under parts, such as ``stud3.dat`` and ``stud4.dat``, are
body."""

_FOLDERS: Final = ("parts", "p", "models", "unofficial/parts", "unofficial/p")
_TO_BRICKY: Final = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])
"""LDraw (x, y, z) to bricky (x, z, -y): a proper rotation, y down becoming z up."""

_JITTER: Final = np.array([0.0137, 0.0071, 0.0193])
"""Shifts the samples off the grid lines that edges of the surface run along."""

_STUD: Final = 20
_HALF_STUD: Final = 10
_FLAT: Final = 1e-9
"""Triangles whose shadow on a ray's plane is smaller than this have no inside to cross."""
_SNAP: Final = 0.01
_ON_GRID: Final = 1e-3
_REFERENCE: Final = 15
"""Fields of a line placing another file: type, color, 12 numbers and the file name."""

_FACES: Final = {"3": 11, "4": 14}
"""Fields of a triangle line and a quad line: type, color and 9 or 12 numbers."""

_TILE: Final = 32
"""Rays are cast in tiles of 32 x 32, each against only the triangles over it."""


@dataclass(frozen=True, slots=True)
class Flat:
    """A file flattened in its own frame: body triangles and studs."""

    triangles: Floats
    """Shape (n, 3, 3): n triangles of three corners."""

    studs: Floats
    """Shape (m, 2, 3): each stud's base and its unit direction."""


@dataclass(frozen=True, slots=True)
class PartFile:
    """A part file of the library: its name and what its header says."""

    name: str
    description: str
    category: str | None
    update: str | None
    """The library release that last changed the file, such as ``2024-05``."""


class Library:
    """An LDraw library folder: ``parts``, ``p`` and their subfolders, looked up without case."""

    def __init__(self, root: Path) -> None:
        if not root.is_dir():
            message = f"no such LDraw library folder: {root}"
            raise BrickyError(message)
        self.root = root
        self._files: dict[str, Path] = {}
        self._parts: dict[str, Path] = {}
        for folder in _FOLDERS:
            base = _find_folder(root, folder)
            if base is None:
                continue
            for path in base.rglob("*.dat"):
                key = path.relative_to(base).as_posix().casefold()
                self._files.setdefault(key, path)
                if folder.endswith("parts") and "/" not in key:
                    self._parts.setdefault(key.removesuffix(".dat"), path)
        if not self._parts:
            message = f"{root} holds no LDraw parts: expected a parts folder of .dat files"
            raise BrickyError(message)
        self._flat: dict[str, Flat] = {}
        self._headers: dict[str, PartFile] = {}

    def __contains__(self, number: str) -> bool:
        return number.casefold() in self._parts

    @property
    def numbers(self) -> tuple[str, ...]:
        """The number of every part file, such as ``3001``, in lower case."""
        return tuple(self._parts)

    def header(self, number: str) -> PartFile:
        """Read a part file's header: its description, category and release."""
        key = number.casefold()
        if key not in self._headers:
            self._headers[key] = self._read_header(self._parts[key])
        return self._headers[key]

    @staticmethod
    def _read_header(path: Path) -> PartFile:
        description, category, update = "", None, None
        for line in _lines(path):
            if not line.startswith("0"):
                if line.strip():
                    break
                continue
            text = line[1:].strip()
            if not description:
                description = text
            elif text.startswith("!CATEGORY"):
                category = text.removeprefix("!CATEGORY").strip()
            elif text.startswith("!LDRAW_ORG"):
                found = re.search(r"UPDATE (\d{4}-\d{2})", text)
                update = found.group(1) if found else None
        return PartFile(name=path.name, description=description, category=category, update=update)

    @cached_property
    def release(self) -> str:
        """The library's release: its newest update, such as ``2024-05``."""
        updates = [self.header(number).update for number in self._parts]
        newest = max((u for u in updates if u), default=None)
        return f"release {newest}" if newest else "unknown release"

    def flatten(self, number: str) -> Flat:
        """Flatten a part into triangles and studs, in LDraw's frame.

        Raises:
            BrickyError: If the part, or a file it references, is not in the library.
        """
        return self._flatten(number.casefold() + ".dat", ())

    def _flatten(self, key: str, chain: tuple[str, ...]) -> Flat:
        key = key.replace("\\", "/").casefold()
        if key in self._flat:
            return self._flat[key]
        if key in chain:
            message = f"LDraw files reference each other in a cycle: {' -> '.join((*chain, key))}"
            raise BrickyError(message)
        path = self._files.get(key)
        if path is None:
            user = chain[-1] if chain else "the part"
            message = f"the LDraw library has no file {key}, which {user} uses"
            raise BrickyError(message)
        triangles: list[Floats] = []
        studs: list[Floats] = []
        for line in _lines(path):
            fields = line.split()
            if fields and fields[0] == "1" and len(fields) >= _REFERENCE:
                self._reference(fields, (*chain, key), triangles, studs)
            elif fields and fields[0] in _FACES and len(fields) >= _FACES[fields[0]]:
                triangles.append(_faces(fields))
        flat = Flat(
            triangles=np.concatenate(triangles) if triangles else np.zeros((0, 3, 3)),
            studs=np.concatenate(studs) if studs else np.zeros((0, 2, 3)),
        )
        if chain:  # files other parts use are kept; a part converted once is not
            self._flat[key] = flat
        return flat

    def _reference(
        self,
        fields: list[str],
        chain: tuple[str, ...],
        triangles: list[Floats],
        studs: list[Floats],
    ) -> None:
        """Place a referenced file: a stud primitive becomes a stud, anything else is flattened."""
        matrix, offset = _transform(fields[2:14])
        name = " ".join(fields[14:]).replace("\\", "/").casefold()
        if name.rsplit("/", 1)[-1] in STUD_PRIMITIVES:
            up = matrix @ np.array([0.0, -1.0, 0.0])
            studs.append(np.array([[offset, up / np.linalg.norm(up)]]))
            return
        child = self._flatten(name, chain)
        if len(child.triangles):
            triangles.append(child.triangles @ matrix.T + offset)
        if len(child.studs):
            bases = child.studs[:, 0] @ matrix.T + offset
            ups = child.studs[:, 1] @ matrix.T
            ups /= np.linalg.norm(ups, axis=1, keepdims=True)
            studs.append(np.stack([bases, ups], axis=1))


def ldraw_parts(library: Library) -> dict[str, CatalogPart]:
    """Every part the library lists, by number, named and categorized as LDraw does it.

    Files whose description starts with "~" (moved, obsolete or parts of parts), "=" (aliases)
    or "_" (variants in a fixed color) are left out. Shapes are added by the import.
    """
    parts: dict[str, CatalogPart] = {}
    for number in sorted(library.numbers):
        header = library.header(number)
        if not header.description or header.description[0] in "~=_":
            continue
        name = " ".join(header.description.split())
        parts[number] = CatalogPart(
            id=number, name=name, category=header.category or name.split(" ", 1)[0]
        )
    return parts


def ldraw_shape(library: Library, number: str) -> BoxesShape:
    """Convert an LDraw part into a shape: its body as boxes, its studs and its anti-studs.

    Raises:
        BrickyError: If the part is missing, references a missing file, or has no body.
    """
    flat = library.flatten(number)
    triangles = _snap(flat.triangles @ _TO_BRICKY.T)
    if not len(triangles):
        message = f"LDraw part {number} has no body"
        raise BrickyError(message)
    corners = triangles.reshape(-1, 3)
    low = np.floor(corners.min(axis=0) / VOXEL) * VOXEL
    high = np.ceil(corners.max(axis=0) / VOXEL) * VOXEL
    counts = np.round((high - low) / VOXEL).astype(int)
    rays = [_Rays.cast(triangles - low, counts, axis) for axis in range(3)]
    votes = np.sum([ray.beyond % 2 for ray in rays], axis=0)
    material: Mask = votes >= 2  # noqa: PLR2004 - a majority of three
    if not material.any():
        message = f"LDraw part {number} encloses no volume"
        raise BrickyError(message)
    walled = _walled(rays[0], rays[1]) & ~material[:, :, 0]
    cavity = _cavity(material, walled)
    return BoxesShape(
        family=Family.BOXES,
        size=tuple(int(n) * VOXEL for n in counts),
        boxes=tuple(_boxes(material | cavity)),
        studs=tuple(_studs(flat.studs, low)),
        anti_studs=tuple(_anti_studs(material, walled)),
        source=f"LDraw {library.header(number).name}",
    )


@dataclass(frozen=True, slots=True)
class _Rays:
    """Rays along one axis through every sample: surface crossings beyond each, and in all."""

    beyond: NDArray[np.int16]
    """Shape (nx, ny, nz): crossings from the sample toward +axis."""

    total: NDArray[np.int16]
    """Shape (nx, ny, nz): crossings along the whole ray through the sample."""

    @classmethod
    def cast(cls, triangles: Floats, counts: NDArray[np.int_], axis: int) -> _Rays:
        """Cast a ray along ``axis`` through every column of samples and count its crossings.

        Rays are cast in square tiles, each against only the triangles whose shadow reaches the
        tile; each ray's crossings are then sorted, so counting those beyond every sample is a
        binary search.
        """
        centers = [(np.arange(int(n)) + 0.5) * VOXEL + _JITTER[i] for i, n in enumerate(counts)]
        u, v = (a for a in range(3) if a != axis)
        nu, nv = len(centers[u]), len(centers[v])
        p0 = triangles[:, 0]
        d, e = triangles[:, 1] - p0, triangles[:, 2] - p0
        det = d[:, u] * e[:, v] - d[:, v] * e[:, u]
        keep = np.abs(det) > _FLAT
        p0, d, e, det = p0[keep], d[keep], e[keep], det[keep]
        corners = triangles[keep]
        low_u, high_u = corners[:, :, u].min(axis=1), corners[:, :, u].max(axis=1)
        low_v, high_v = corners[:, :, v].min(axis=1), corners[:, :, v].max(axis=1)
        rays: list[NDArray[np.int64]] = []
        depths: list[Floats] = []
        for i0 in range(0, nu, _TILE):
            for j0 in range(0, nv, _TILE):
                tile_u, tile_v = centers[u][i0 : i0 + _TILE], centers[v][j0 : j0 + _TILE]
                near = (
                    (high_u >= tile_u[0])
                    & (low_u <= tile_u[-1])
                    & (high_v >= tile_v[0])
                    & (low_v <= tile_v[-1])
                )
                if not near.any():
                    continue
                grid_u, grid_v = np.meshgrid(tile_u, tile_v, indexing="ij")
                ids = (
                    np.arange(i0, i0 + len(tile_u))[:, None] * nv + np.arange(j0, j0 + len(tile_v))
                ).ravel()
                q0, qd, qe, qdet = p0[near], d[near], e[near], det[near]
                wu = grid_u.ravel()[:, None] - q0[None, :, u]
                wv = grid_v.ravel()[:, None] - q0[None, :, v]
                a = (wu * qe[None, :, v] - wv * qe[None, :, u]) / qdet[None]
                b = (qd[None, :, u] * wv - qd[None, :, v] * wu) / qdet[None]
                ray, tri = np.nonzero((a >= 0) & (b >= 0) & (a + b <= 1))
                a, b = a[ray, tri], b[ray, tri]
                depths.append(q0[tri, axis] + a * qd[tri, axis] + b * qe[tri, axis])
                rays.append(ids[ray])
        hit_rays = np.concatenate(rays) if rays else np.zeros(0, dtype=np.int64)
        hit_depths = np.concatenate(depths) if depths else np.zeros(0)
        span = float(counts.max() * VOXEL + 4 * VOXEL)
        keys = np.sort(hit_rays * span + hit_depths)
        all_rays = np.arange(nu * nv)
        starts = np.searchsorted(keys, all_rays * span, side="left")
        ends = np.searchsorted(keys, (all_rays + 1) * span, side="left")
        queries = all_rays[:, None] * span + centers[axis][None, :]
        beyond = ends[:, None] - np.searchsorted(keys, queries.ravel(), side="right").reshape(
            queries.shape
        )
        total = np.broadcast_to((ends - starts)[:, None], beyond.shape)
        shape = (nu, nv, len(centers[axis]))
        order = [u, v, axis]
        return cls(
            beyond=np.moveaxis(beyond.reshape(shape).astype(np.int16), [0, 1, 2], order),
            total=np.moveaxis(total.reshape(shape).astype(np.int16), [0, 1, 2], order),
        )


def _walled(along_x: _Rays, along_y: _Rays) -> Mask:
    """Bottom samples with the part's surface on all four sides: in an opening, not outside.

    Walls are found by rays along x and y through the bottom samples, in both directions, so a
    wall thinner than the sampling still counts.
    """
    sides = [
        along_x.beyond[:, :, 0] > 0,
        along_x.total[:, :, 0] - along_x.beyond[:, :, 0] > 0,
        along_y.beyond[:, :, 0] > 0,
        along_y.total[:, :, 0] - along_y.beyond[:, :, 0] > 0,
    ]
    return np.all(np.stack(sides), axis=0)


def _cavity(material: Mask, walled: Mask) -> Mask:
    """Openings at the bottom, walled in, up to the part above them: they become body.

    Only columns with material above count, so a hole straight through the part stays open.
    """
    above = np.flip(np.cumsum(np.flip(material, axis=2), axis=2), axis=2) > 0
    below = np.cumsum(material, axis=2) > 0
    return walled[:, :, None] & above & ~below


def _snap(points: Floats) -> Floats:
    """Round coordinates within a hundredth of a unit to the whole unit, as LDraw means them."""
    rounded = np.round(points)
    return np.where(np.abs(points - rounded) < _SNAP, rounded, points)


def _anti_studs(material: Mask, walled: Mask) -> Iterator[tuple[int, int]]:
    """Stud positions on the bottom face with an opening a stud goes into.

    Stud positions are every 20 units from 10 in, on both axes. Around the position, the bottom
    must be walled in and free of material from the bottom face up to a stud's height.
    """
    nx, ny, _ = material.shape
    reach, depth = _STUD_ROOM // VOXEL // 2, _STUD_ROOM // VOXEL
    for x in range(_HALF_STUD, nx * VOXEL, _STUD):
        for y in range(_HALF_STUD, ny * VOXEL, _STUD):
            i, j = x // VOXEL, y // VOXEL
            near = (slice(i - reach, i + reach), slice(j - reach, j + reach))
            free = ~material[*near, :depth].any() and walled[near].all()
            if walled[near].shape == (2 * reach, 2 * reach) and free:
                yield (x, y)


def _studs(studs: Floats, low: Floats) -> Iterator[tuple[int, int, int, str]]:
    """Studs on grid axes, in bricky's frame from the minimum corner; others are left out."""
    for base, up in studs:
        position = _snap(_TO_BRICKY @ base - low)
        direction = _TO_BRICKY @ up
        axis = int(np.argmax(np.abs(direction)))
        on_axis = abs(direction[axis]) > 1 - _ON_GRID
        if not on_axis or np.any(np.abs(position - np.round(position)) > _ON_GRID):
            continue
        sign = "+" if direction[axis] > 0 else "-"
        x, y, z = (round(float(c)) for c in position)
        yield (x, y, z, sign + "xyz"[axis])


def _boxes(body: Mask) -> Iterator[tuple[int, int, int, int, int, int]]:
    """Cover the samples with boxes, greedily: grow along x, then y, then z."""
    left = body.copy()
    while left.any():
        i, j, k = (int(index) for index in np.unravel_index(np.argmax(left), left.shape))
        i1 = i + 1
        while i1 < left.shape[0] and left[i1, j, k]:
            i1 += 1
        j1 = j + 1
        while j1 < left.shape[1] and left[i:i1, j1, k].all():
            j1 += 1
        k1 = k + 1
        while k1 < left.shape[2] and left[i:i1, j:j1, k1].all():
            k1 += 1
        left[i:i1, j:j1, k:k1] = False
        yield (i * VOXEL, j * VOXEL, k * VOXEL, i1 * VOXEL, j1 * VOXEL, k1 * VOXEL)


def _faces(fields: list[str]) -> Floats:
    """A triangle line as one triangle, a quad line as two."""
    if fields[0] == "3":
        return np.array([_points(fields[2:11])])
    a, b, c, d = _points(fields[2:14])
    return np.array([[a, b, c], [a, c, d]])


def _transform(numbers: list[str]) -> tuple[Floats, Floats]:
    x, y, z, a, b, c, d, e, f, g, h, i = (float(n) for n in numbers)
    return np.array([[a, b, c], [d, e, f], [g, h, i]]), np.array([x, y, z])


def _points(numbers: list[str]) -> Floats:
    return np.array([float(n) for n in numbers]).reshape(-1, 3)


def _lines(path: Path) -> Iterable[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _find_folder(root: Path, folder: str) -> Path | None:
    """Find a folder such as ``parts`` or ``unofficial/p`` under the root, ignoring case."""
    current = root
    for name in folder.split("/"):
        match = next(
            (p for p in current.iterdir() if p.is_dir() and p.name.casefold() == name), None
        )
        if match is None:
            return None
        current = match
    return current
