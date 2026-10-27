// bricky viewer: draws a bricky scene with three.js.
//
// One module serves two readers. Headless Chromium uses `load` and `draw` to make the pictures an
// agent reads after every build: orthographic views with stud rulers, an iso view, error marks and
// labels. The standalone HTML viewer uses `mount` to let people orbit the same scene.
//
// Scenes come from bricky.render.scene in base units of 0.4 mm. Model axes are x east, y north and
// z up; three.js axes are x right, y up and z toward the viewer, so model y maps to three -z.

import * as THREE from "three";

const MM = 0.4;
const STUD = 20;
const PLATE = 8;
const FLAG = { HIGHLIGHT: 1, GHOST: 2, ERROR: 4, WARNING: 8, CHANGED: 16 };
const AXES = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]];
const INK = { error: "#cf222e", warning: "#b35900", highlight: "#0969da", changed: "#8250df", text: "#1f2328", quiet: "#59636e" };
const PAPER = "#f6f7f9";
const HEADER = 30;
const MARGIN = { left: 60, right: 16, top: 34, bottom: 44 };
const FONT = "12px system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";

const VIEWS = {
  iso: { title: "ISO", note: "from the south-east" },
  front: { title: "FRONT", note: "looking north", dir: [0, 0, 1], up: [0, 1, 0], u: { vec: [1, 0, 0], axis: "x", sign: 1 }, v: { vec: [0, 1, 0], axis: "z", sign: 1 } },
  back: { title: "BACK", note: "looking south", dir: [0, 0, -1], up: [0, 1, 0], u: { vec: [-1, 0, 0], axis: "x", sign: -1 }, v: { vec: [0, 1, 0], axis: "z", sign: 1 } },
  right: { title: "RIGHT", note: "looking west", dir: [1, 0, 0], up: [0, 1, 0], u: { vec: [0, 0, -1], axis: "y", sign: 1 }, v: { vec: [0, 1, 0], axis: "z", sign: 1 } },
  left: { title: "LEFT", note: "looking east", dir: [-1, 0, 0], up: [0, 1, 0], u: { vec: [0, 0, 1], axis: "y", sign: -1 }, v: { vec: [0, 1, 0], axis: "z", sign: 1 } },
  top: { title: "TOP", note: "north up", dir: [0, 1, 0], up: [0, 0, -1], u: { vec: [1, 0, 0], axis: "x", sign: 1 }, v: { vec: [0, 0, -1], axis: "y", sign: 1 } },
};
const SHEET = ["iso", "front", "right", "top"];

function toThree(x, y, z) {
  return new THREE.Vector3(x * MM, z * MM, -y * MM);
}

function vec(a) {
  return new THREE.Vector3(a[0], a[1], a[2]);
}

// ---------------------------------------------------------------------------------------------
// Building the three.js scene from a bricky scene

export function buildModel(scene) {
  const root = new THREE.Group();
  const planes = scene.clips.map(clipPlane);
  // Bodies take their colours from vertices, studs from instances: two sets of materials.
  const bodies = materials(planes, true);
  const studs = materials(planes, false);
  for (const material of Object.values(studs)) material.side = THREE.FrontSide;

  const colors = scene.colors.map((c) => new THREE.Color(c.rgb));
  const tint = { error: new THREE.Color(INK.error), warning: new THREE.Color("#e8a400") };
  const kindOf = (part) => {
    if (part[1] & FLAG.GHOST) return "ghost";
    const type = scene.colors[part[0]].type;
    return type === "transparent" ? "clear" : type === "pearl" ? "pearl" : "solid";
  };
  const colorOf = (part) => {
    const color = colors[part[0]].clone();
    if (part[1] & FLAG.ERROR) color.lerp(tint.error, 0.55);
    else if (part[1] & FLAG.WARNING) color.lerp(tint.warning, 0.45);
    return color;
  };

  // Part bounds, for labels and for framing.
  const partBounds = scene.parts.map(() => new THREE.Box3());
  for (const b of scene.boxes) {
    partBounds[b[6]].expandByPoint(toThree(b[0], b[1], b[2])).expandByPoint(toThree(b[3], b[4], b[5]));
  }
  for (const s of scene.shapes) {
    const v = s.vertices;
    for (let k = 0; k < v.length; k += 3) partBounds[s.part].expandByPoint(toThree(v[k], v[k + 1], v[k + 2]));
  }

  // Bodies: the visible faces of every box, merged into one mesh per material kind. The scene
  // already left out faces pressed against opaque neighbours, which nobody can see.
  const faces = { solid: new FaceBuffer(), pearl: new FaceBuffer(), clear: new FaceBuffer(), ghost: new FaceBuffer() };
  for (const b of scene.boxes) {
    const part = scene.parts[b[6]];
    faces[kindOf(part)].addBox(b, colorOf(part));
  }
  for (const s of scene.shapes) {
    const part = scene.parts[s.part];
    faces[kindOf(part)].addShape(s, colorOf(part));
  }
  for (const [kind, buffer] of Object.entries(faces)) {
    if (!buffer.count) continue;
    const mesh = new THREE.Mesh(buffer.geometry(), bodies[kind]);
    mesh.castShadow = kind === "solid" || kind === "pearl";
    mesh.receiveShadow = kind !== "ghost";
    mesh.renderOrder = kind === "clear" || kind === "ghost" ? 2 : 0;
    root.add(mesh);
  }

  // Studs: cylinders standing on their part's face, along the stud's axis. Studs seated in a
  // receptor are hidden inside the part above, and the scene leaves them out.
  const meshes = [];
  const cylinder = studGeometry();
  const byKind = { solid: [], pearl: [], clear: [], ghost: [] };
  for (const s of scene.studs) byKind[kindOf(scene.parts[s[4]])].push(s);
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const upright = new THREE.Vector3(0, 1, 0);
  const one = new THREE.Vector3(1, 1, 1);
  for (const [kind, list] of Object.entries(byKind)) {
    if (!list.length) continue;
    const mesh = new THREE.InstancedMesh(cylinder, studs[kind], list.length);
    list.forEach((s, i) => {
      const a = AXES[s[3]];
      q.setFromUnitVectors(upright, new THREE.Vector3(a[0], a[2], -a[1]));
      mesh.setMatrixAt(i, m.compose(toThree(s[0], s[1], s[2]), q, one));
      if (kind !== "ghost") mesh.setColorAt(i, colorOf(scene.parts[s[4]]));
    });
    mesh.castShadow = kind === "solid" || kind === "pearl";
    mesh.receiveShadow = kind !== "ghost";
    mesh.renderOrder = kind === "clear" || kind === "ghost" ? 2 : 0;
    meshes.push(remember(mesh));
    root.add(mesh);
  }

  // Edges: dark outlines so every part reads, coloured and always on top for marked parts.
  const outline = (filter) => {
    const points = [];
    for (const b of scene.boxes) if (filter(scene.parts[b[6]][1])) pushEdges(points, b);
    for (const s of scene.shapes) if (filter(scene.parts[s.part][1])) pushShapeEdges(points, s);
    for (const s of scene.studs) if (filter(scene.parts[s[4]][1])) pushRim(points, s);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
    return geometry;
  };
  const edgeMaterials = {
    plain: new THREE.LineBasicMaterial({ color: 0x14181d, transparent: true, opacity: 0.35, clippingPlanes: planes }),
    ghost: new THREE.LineBasicMaterial({ color: 0x8c959f, transparent: true, opacity: 0.12, depthWrite: false, clippingPlanes: planes }),
    highlight: new THREE.LineBasicMaterial({ color: INK.highlight, transparent: true, opacity: 0.95, clippingPlanes: planes }),
    changed: new THREE.LineBasicMaterial({ color: INK.changed, transparent: true, opacity: 0.95, clippingPlanes: planes }),
    error: new THREE.LineBasicMaterial({ color: INK.error, transparent: true, opacity: 0.95, depthTest: false, clippingPlanes: planes }),
    warning: new THREE.LineBasicMaterial({ color: INK.warning, transparent: true, opacity: 0.95, depthTest: false, clippingPlanes: planes }),
  };
  const lines = [
    [outline((f) => !(f & (FLAG.GHOST | FLAG.ERROR | FLAG.WARNING | FLAG.HIGHLIGHT | FLAG.CHANGED))), edgeMaterials.plain, 1],
    [outline((f) => f & FLAG.CHANGED && !(f & (FLAG.GHOST | FLAG.ERROR | FLAG.WARNING | FLAG.HIGHLIGHT))), edgeMaterials.changed, 2],
    [outline((f) => f & FLAG.GHOST), edgeMaterials.ghost, 3],
    [outline((f) => f & FLAG.HIGHLIGHT && !(f & (FLAG.ERROR | FLAG.WARNING))), edgeMaterials.highlight, 4],
    [outline((f) => f & FLAG.WARNING && !(f & FLAG.ERROR)), edgeMaterials.warning, 5],
    [outline((f) => f & FLAG.ERROR), edgeMaterials.error, 6],
  ];
  for (const [geometry, material, order] of lines) {
    if (!geometry.attributes.position.count) continue;
    const segments = new THREE.LineSegments(geometry, material);
    segments.renderOrder = order;
    root.add(segments);
  }

  // Diagnostic regions: outlined boxes drawn over everything.
  for (const mark of scene.marks) {
    const points = [];
    pushEdges(points, mark.box);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
    const material = new THREE.LineDashedMaterial({ color: INK[mark.kind], dashSize: 2, gapSize: 1.2, depthTest: false, transparent: true });
    const segments = new THREE.LineSegments(geometry, material);
    segments.computeLineDistances();
    segments.renderOrder = 7;
    root.add(segments);
  }

  const bounds = new THREE.Box3(toThree(scene.bounds[0], scene.bounds[4], scene.bounds[2]), toThree(scene.bounds[3], scene.bounds[1], scene.bounds[5]));
  return { root, bounds, partBounds, edgeMaterials, planes, meshes };
}

// Snapshot an instanced mesh's matrices and colours, so views can reorder its instances.
function remember(mesh) {
  const count = mesh.count;
  const matrices = mesh.instanceMatrix.array.slice();
  const colors = mesh.instanceColor ? mesh.instanceColor.array.slice() : null;
  const depth = new Float32Array(count);
  const order = new Uint32Array(count);
  return { mesh, count, matrices, colors, depth, order };
}

// Draw opaque instances nearest first, so the depth test skips the fragments they hide.
function orderInstances(meshes, camera) {
  const forward = new THREE.Vector3();
  camera.getWorldDirection(forward);
  const origin = camera.position;
  for (const item of meshes) {
    const { mesh, count, matrices, colors, depth, order } = item;
    if (mesh.material.transparent) continue;
    for (let i = 0; i < count; i++) {
      const o = i * 16;
      depth[i] = (matrices[o + 12] - origin.x) * forward.x + (matrices[o + 13] - origin.y) * forward.y + (matrices[o + 14] - origin.z) * forward.z;
      order[i] = i;
    }
    order.sort((a, b) => depth[a] - depth[b]);
    const m = mesh.instanceMatrix.array;
    const c = mesh.instanceColor ? mesh.instanceColor.array : null;
    for (let k = 0; k < count; k++) {
      const i = order[k];
      m.set(matrices.subarray(i * 16, i * 16 + 16), k * 16);
      if (c && colors) c.set(colors.subarray(i * 3, i * 3 + 3), k * 3);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }
}

// A stud: an open-bottomed cylinder 4.8 mm wide and 1.7 mm tall with a flat top, standing on the
// origin along +y. Its bottom is always against its part, so it has no bottom cap.
function studGeometry(segments = 12) {
  const radius = 2.4, height = 1.7;
  const positions = [], normals = [], indices = [];
  for (let i = 0; i <= segments; i++) {
    const angle = (i / segments) * Math.PI * 2;
    const x = Math.sin(angle), z = Math.cos(angle);
    positions.push(x * radius, 0, z * radius, x * radius, height, z * radius);
    normals.push(x, 0, z, x, 0, z);
  }
  for (let i = 0; i < segments; i++) {
    const a = 2 * i, b = a + 1, c = a + 2, d = a + 3;
    indices.push(a, c, b, b, c, d);
  }
  const centre = positions.length / 3;
  positions.push(0, height, 0);
  normals.push(0, 1, 0);
  for (let i = 0; i <= segments; i++) {
    const angle = (i / segments) * Math.PI * 2;
    positions.push(Math.sin(angle) * radius, height, Math.cos(angle) * radius);
    normals.push(0, 1, 0);
  }
  for (let i = 0; i < segments; i++) indices.push(centre, centre + 1 + i, centre + 2 + i);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
  geometry.setIndex(indices);
  return geometry;
}

function materials(planes, vertexColors) {
  const set = {
    solid: new THREE.MeshStandardMaterial({ roughness: 0.45, metalness: 0, side: THREE.DoubleSide, vertexColors }),
    pearl: new THREE.MeshStandardMaterial({ roughness: 0.32, metalness: 0.3, side: THREE.DoubleSide, vertexColors }),
    clear: new THREE.MeshStandardMaterial({ roughness: 0.08, metalness: 0, transparent: true, opacity: 0.42, depthWrite: false, side: THREE.DoubleSide, vertexColors }),
    ghost: new THREE.MeshStandardMaterial({ color: 0xc9ced6, roughness: 0.7, transparent: true, opacity: 0.16, depthWrite: false }),
  };
  for (const material of Object.values(set)) {
    material.clippingPlanes = planes;
    // Push faces back a little so outlines drawn on their edges stay in front.
    material.polygonOffset = true;
    material.polygonOffsetFactor = 1;
    material.polygonOffsetUnits = 1;
  }
  return set;
}

// The six faces of a box in three.js axes: normal, and two tangents whose cross product is the
// normal, so every face winds counter-clockwise seen from outside. Bits follow the scene's mask:
// model -x +x -y +y -z +z, where model y is three -z and model z is three y.
const FACES = [
  { bit: 0, axis: 0, high: false, normal: [-1, 0, 0], t1: 2, t2: 1 },
  { bit: 1, axis: 0, high: true, normal: [1, 0, 0], t1: 1, t2: 2 },
  { bit: 2, axis: 2, high: true, normal: [0, 0, 1], t1: 0, t2: 1 },
  { bit: 3, axis: 2, high: false, normal: [0, 0, -1], t1: 1, t2: 0 },
  { bit: 4, axis: 1, high: false, normal: [0, -1, 0], t1: 0, t2: 2 },
  { bit: 5, axis: 1, high: true, normal: [0, 1, 0], t1: 2, t2: 0 },
];

class FaceBuffer {
  constructor() {
    this.positions = [];
    this.normals = [];
    this.colors = [];
    this.indices = [];
    this.count = 0;
  }

  addBox(b, color) {
    const lo = [b[0] * MM, b[2] * MM, -b[4] * MM];
    const hi = [b[3] * MM, b[5] * MM, -b[1] * MM];
    for (const face of FACES) {
      if (!(b[7] & (1 << face.bit))) continue;
      const base = this.positions.length / 3;
      const p = [0, 0, 0];
      p[face.axis] = face.high ? hi[face.axis] : lo[face.axis];
      for (const [s, t] of [[lo, lo], [hi, lo], [hi, hi], [lo, hi]]) {
        p[face.t1] = s[face.t1];
        p[face.t2] = t[face.t2];
        this.positions.push(p[0], p[1], p[2]);
        this.normals.push(...face.normal);
        this.colors.push(color.r, color.g, color.b);
      }
      this.indices.push(base, base + 1, base + 2, base, base + 2, base + 3);
      this.count += 1;
    }
  }

  // A part that is not just boxes: its faces, each fanned into triangles with a flat normal.
  addShape(s, color) {
    const v = s.vertices;
    for (const face of s.faces) {
      const points = face.map((i) => [v[3 * i] * MM, v[3 * i + 2] * MM, -v[3 * i + 1] * MM]);
      let nx = 0, ny = 0, nz = 0;
      for (let k = 0; k < points.length; k++) {
        const p = points[k], q = points[(k + 1) % points.length];
        nx += (p[1] - q[1]) * (p[2] + q[2]);
        ny += (p[2] - q[2]) * (p[0] + q[0]);
        nz += (p[0] - q[0]) * (p[1] + q[1]);
      }
      const length = Math.hypot(nx, ny, nz) || 1;
      const base = this.positions.length / 3;
      for (const p of points) {
        this.positions.push(p[0], p[1], p[2]);
        this.normals.push(nx / length, ny / length, nz / length);
        this.colors.push(color.r, color.g, color.b);
      }
      for (let k = 1; k + 1 < points.length; k++) this.indices.push(base, base + k, base + k + 1);
      this.count += 1;
    }
  }

  geometry() {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(this.positions, 3));
    geometry.setAttribute("normal", new THREE.Float32BufferAttribute(this.normals, 3));
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(this.colors, 3));
    geometry.setIndex(this.indices.length > 65535 ? new THREE.Uint32BufferAttribute(this.indices, 1) : new THREE.Uint16BufferAttribute(this.indices, 1));
    return geometry;
  }
}

// The rim of a stud's top: from above, a stud is lit exactly like the face it stands on, so only
// its outline shows it.
const RIM = Array.from({ length: 16 }, (_, i) => [Math.cos((i / 16) * 2 * Math.PI) * 2.4, Math.sin((i / 16) * 2 * Math.PI) * 2.4]);
function pushRim(points, s) {
  const a = AXES[s[3]];
  const axis = new THREE.Vector3(a[0], a[2], -a[1]);
  const centre = toThree(s[0], s[1], s[2]).addScaledVector(axis, 1.7);
  const side = Math.abs(axis.y) > 0.5 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0);
  const other = new THREE.Vector3().crossVectors(axis, side);
  for (let i = 0; i < RIM.length; i++) {
    const [x0, y0] = RIM[i];
    const [x1, y1] = RIM[(i + 1) % RIM.length];
    const p = centre.clone().addScaledVector(side, x0).addScaledVector(other, y0);
    const q = centre.clone().addScaledVector(side, x1).addScaledVector(other, y1);
    points.push(p.x, p.y, p.z, q.x, q.y, q.z);
  }
}

function pushEdges(points, b) {
  const lo = toThree(b[0], b[4], b[2]);
  const hi = toThree(b[3], b[1], b[5]);
  const xs = [lo.x, hi.x], ys = [lo.y, hi.y], zs = [lo.z, hi.z];
  for (const y of ys) for (const z of zs) points.push(xs[0], y, z, xs[1], y, z);
  for (const x of xs) for (const z of zs) points.push(x, ys[0], z, x, ys[1], z);
  for (const x of xs) for (const y of ys) points.push(x, y, zs[0], x, y, zs[1]);
}

// The creased edges of a shape, which the scene picked out.
function pushShapeEdges(points, s) {
  const v = s.vertices;
  for (let k = 0; k < s.edges.length; k += 2) {
    const a = 3 * s.edges[k], b = 3 * s.edges[k + 1];
    points.push(v[a] * MM, v[a + 2] * MM, -v[a + 1] * MM, v[b] * MM, v[b + 2] * MM, -v[b + 1] * MM);
  }
}

function clipPlane(clip) {
  // Keep points where normal . p + constant >= 0.
  const value = clip.value * MM;
  const below = clip.keep === "below";
  if (clip.axis === "z") return new THREE.Plane(new THREE.Vector3(0, below ? -1 : 1, 0), below ? value : -value);
  if (clip.axis === "x") return new THREE.Plane(new THREE.Vector3(below ? -1 : 1, 0, 0), below ? value : -value);
  // Model y is three -z: keep y < v means keep z3 > -v.
  return new THREE.Plane(new THREE.Vector3(0, 0, below ? 1 : -1), value * (below ? 1 : -1));
}

// ---------------------------------------------------------------------------------------------
// Cameras

function orthoCamera(view, bounds, width, height) {
  const spec = VIEWS[view];
  const u = vec(spec.u.vec), v = vec(spec.v.vec), dir = vec(spec.dir);
  const corners = boxCorners(bounds);
  const us = corners.map((c) => c.dot(u)), vs = corners.map((c) => c.dot(v)), ds = corners.map((c) => c.dot(dir));
  const [u0, u1, v0, v1] = [Math.min(...us), Math.max(...us), Math.min(...vs), Math.max(...vs)];
  const innerW = width - MARGIN.left - MARGIN.right, innerH = height - MARGIN.top - MARGIN.bottom;
  const scale = 0.92 * Math.min(innerW / Math.max(u1 - u0, 1e-3), innerH / Math.max(v1 - v0, 1e-3));
  // Screen centre of the drawing area, in model millimetres along u and v.
  const uMid = (u0 + u1) / 2 + (width / 2 - (MARGIN.left + innerW / 2)) / scale;
  const vMid = (v0 + v1) / 2 - (height / 2 - (MARGIN.top + innerH / 2)) / scale;
  const depth = Math.max(...ds) + 200;
  const camera = new THREE.OrthographicCamera(-width / 2 / scale, width / 2 / scale, height / 2 / scale, -height / 2 / scale, 1, depth - Math.min(...ds) + 400);
  camera.up.copy(vec(spec.up));
  camera.position.copy(u.clone().multiplyScalar(uMid).add(v.clone().multiplyScalar(vMid)).add(dir.clone().multiplyScalar(depth)));
  camera.lookAt(camera.position.clone().sub(dir));
  camera.updateMatrixWorld();
  camera.updateProjectionMatrix();
  return { camera, scale, uMid, vMid, u0, u1, v0, v1 };
}

function isoCamera(bounds, width, height, azimuth = 35, elevation = 30) {
  const camera = new THREE.PerspectiveCamera(24, width / height, 1, 1e6);
  const az = THREE.MathUtils.degToRad(azimuth), el = THREE.MathUtils.degToRad(elevation);
  const dir = new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el));
  const target = bounds.getCenter(new THREE.Vector3());
  const corners = boxCorners(bounds);
  const radius = bounds.getSize(new THREE.Vector3()).length() / 2;
  let distance = radius * 4;
  const right = new THREE.Vector3(), up = new THREE.Vector3();
  // Fit the drawing area below the panel title: centre the projected box, then scale the distance.
  const frameTop = (MARGIN.top - 8) / height * 2; // NDC height reserved for the title
  for (let i = 0; i < 10; i++) {
    camera.position.copy(target).addScaledVector(dir, distance);
    camera.near = distance / 100;
    camera.far = distance * 10;
    camera.lookAt(target);
    camera.updateMatrixWorld();
    camera.updateProjectionMatrix();
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const c of corners) {
      const p = c.clone().project(camera);
      x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x); y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y);
    }
    const half = distance * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2);
    right.setFromMatrixColumn(camera.matrixWorld, 0);
    up.setFromMatrixColumn(camera.matrixWorld, 1);
    const wantY = -frameTop / 2;
    target.addScaledVector(right, ((x0 + x1) / 2) * half * camera.aspect).addScaledVector(up, ((y0 + y1) / 2 - wantY) * half);
    const extent = Math.max((x1 - x0) / 2, (y1 - y0) / 2 / (1 - frameTop / 2));
    distance *= 0.4 + 0.6 * (extent / 0.86);
  }
  camera.position.copy(target).addScaledVector(dir, distance);
  camera.lookAt(target);
  camera.updateMatrixWorld();
  camera.updateProjectionMatrix();
  const pxPerStud = (STUD * MM) / (2 * distance * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2)) * height;
  return { camera, target, dir, pxPerStud };
}

function boxCorners(box) {
  const out = [];
  for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) out.push(new THREE.Vector3(x, y, z));
  return out;
}

// ---------------------------------------------------------------------------------------------
// Headless drawing: load a scene once, then draw any view onto the page

const state = { renderer: null, three: null, model: null, scene: null, hemi: null, sun: null, ground: null, timings: [] };

export function load(scene) {
  const started = performance.now();
  if (!state.renderer) {
    state.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    state.renderer.setPixelRatio(1);
    state.renderer.localClippingEnabled = true;
    state.renderer.shadowMap.enabled = true;
    state.renderer.shadowMap.type = THREE.PCFShadowMap;
    state.renderer.toneMapping = THREE.NeutralToneMapping;
  }
  if (state.three) dispose(state.three);
  state.three = new THREE.Scene();
  state.hemi = new THREE.HemisphereLight(0xffffff, 0x8d949e, 1.5);
  state.sun = new THREE.DirectionalLight(0xffffff, 2.1);
  state.sun.shadow.mapSize.set(1024, 1024);
  state.sun.shadow.bias = -0.0004;
  state.sun.shadow.normalBias = 0.6;
  state.three.add(state.hemi, state.sun, state.sun.target);
  state.model = buildModel(scene);
  state.three.add(state.model.root);
  state.ground = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.ShadowMaterial({ opacity: 0.16 }));
  state.ground.rotation.x = -Math.PI / 2;
  state.ground.receiveShadow = true;
  state.three.add(state.ground);
  state.scene = scene;
  return { parts: scene.parts.length, ms: Math.round(performance.now() - started) };
}

// Free the GPU memory of a scene that is about to be replaced.
function dispose(root) {
  root.traverse((object) => {
    object.geometry?.dispose();
    const list = Array.isArray(object.material) ? object.material : object.material ? [object.material] : [];
    for (const material of list) material.dispose();
  });
}

export async function draw(view, width, height) {
  state.timings = [];
  const sheet = document.getElementById("sheet");
  sheet.replaceChildren();
  sheet.style.width = `${width}px`;
  sheet.style.height = `${height}px`;
  sheet.append(header(state.scene, width));
  const views = view === "sheet" ? SHEET : [view];
  const columns = views.length > 1 ? 2 : 1;
  const rows = Math.ceil(views.length / columns);
  const panelW = Math.floor(width / columns), panelH = Math.floor((height - HEADER) / rows);
  views.forEach((name, i) => {
    const panel = drawPanel(name, panelW, panelH);
    panel.style.left = `${(i % columns) * panelW}px`;
    panel.style.top = `${HEADER + Math.floor(i / columns) * panelH}px`;
    sheet.append(panel);
  });
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  return { width, height, views, timings: state.timings };
}

function drawPanel(view, width, height) {
  const { renderer, three, model, sun, hemi, ground } = state;
  const panel = document.createElement("div");
  panel.className = "panel";
  panel.style.width = `${width}px`;
  panel.style.height = `${height}px`;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = PAPER;
  ctx.fillRect(0, 0, width, height);
  const svg = svgElement("svg", { width, height, viewBox: `0 0 ${width} ${height}` });
  const size = model.bounds.getSize(new THREE.Vector3());
  const centre = model.bounds.getCenter(new THREE.Vector3());

  let camera, pxPerStud, ortho = null;
  if (view === "iso") {
    const iso = isoCamera(model.bounds, width, height);
    camera = iso.camera;
    pxPerStud = iso.pxPerStud;
    const radius = size.length();
    const light = new THREE.Vector3(-0.55, 1.1, 0.75).normalize();
    sun.position.copy(centre).addScaledVector(light, radius * 1.5);
    sun.target.position.copy(centre);
    sun.castShadow = true;
    const cam = sun.shadow.camera;
    cam.left = -radius; cam.right = radius; cam.top = radius; cam.bottom = -radius;
    cam.near = radius * 0.1; cam.far = radius * 4;
    cam.updateProjectionMatrix();
    ground.visible = true;
    ground.position.set(centre.x, model.bounds.min.y - 0.02, centre.z);
    ground.scale.set(radius * 6, radius * 6, 1);
    renderer.setClearColor(PAPER, 1);
  } else {
    ortho = orthoCamera(view, model.bounds, width, height);
    camera = ortho.camera;
    pxPerStud = ortho.scale * STUD * MM;
    const spec = VIEWS[view];
    const light = vec(spec.dir).multiplyScalar(2).add(vec(spec.up).multiplyScalar(1.2)).sub(vec(spec.u.vec).multiplyScalar(0.8)).normalize();
    sun.position.copy(centre).addScaledVector(light, size.length() * 2);
    sun.target.position.copy(centre);
    sun.castShadow = false;
    ground.visible = false;
    renderer.setClearColor(0x000000, 0);
    drawGrid(ctx, view, ortho, width, height);
  }
  hemi.intensity = view === "iso" ? 1.45 : 1.7;
  // Thin edges when parts are small on screen, so outlines never swamp the colours.
  const opacity = Math.min(0.42, Math.max(0.07, 0.03 * pxPerStud));
  model.edgeMaterials.plain.opacity = opacity;

  const started = performance.now();
  orderInstances(model.meshes, camera);
  renderer.setSize(width, height, false);
  renderer.render(three, camera);
  ctx.drawImage(renderer.domElement, 0, 0, width, height);
  if (ortho) drawGrid(ctx, view, ortho, width, height, "rgba(31, 35, 40, 0.10)");
  state.timings.push([view, Math.round(performance.now() - started)]);

  svg.append(text(12, 20, `${VIEWS[view].title}`, { weight: 700, fill: INK.text }));
  svg.append(text(12 + measure(VIEWS[view].title, 700) + 8, 20, VIEWS[view].note, { fill: INK.quiet }));
  if (view === "iso") drawCompass(svg, camera, centre, width);
  else drawRulers(svg, view, ortho, width, height);
  drawLabels(svg, camera, width, height);
  panel.append(canvas, svg);
  return panel;
}

// ---------------------------------------------------------------------------------------------
// Overlays: header, grid, rulers, labels, compass

function header(scene, width) {
  const bar = document.createElement("div");
  bar.className = "header";
  bar.style.width = `${width}px`;
  const title = document.createElement("span");
  title.textContent = scene.title;
  bar.append(title);
  const legend = document.createElement("span");
  legend.className = "legend";
  const flags = scene.parts.reduce((all, p) => all | p[1], 0);
  const keys = [];
  if (flags & FLAG.ERROR) keys.push(["error", "error"]);
  if (flags & FLAG.WARNING) keys.push(["warning", "warning"]);
  if (flags & FLAG.HIGHLIGHT) keys.push(["highlight", "highlighted"]);
  if (flags & FLAG.CHANGED) keys.push(["changed", "new or changed since the last build"]);
  if (scene.clips.length) keys.push([null, `cut: ${scene.clips.map(describeClip).join(", ")}`]);
  for (const [kind, label] of keys) {
    const item = document.createElement("span");
    if (kind) {
      const swatch = document.createElement("i");
      swatch.style.background = INK[kind];
      item.append(swatch);
    }
    item.append(label);
    legend.append(item);
  }
  bar.append(legend);
  return bar;
}

function describeClip(clip) {
  const unit = clip.axis === "z" ? PLATE : STUD;
  return `${clip.axis} ${clip.keep === "below" ? "<" : ">"} ${+(clip.value / unit).toFixed(2)}`;
}

function axisInfo(axis) {
  return axis === "z" ? { unit: PLATE, name: "z (plates)", steps: [1, 3, 6, 12, 24, 30, 48, 60, 120, 240, 480] } : { unit: STUD, name: `${axis} (studs)`, steps: [1, 2, 4, 5, 8, 10, 16, 20, 40, 50, 100, 200] };
}

// Pick a tick step, in model units, that leaves at least `minPx` between labels.
function tickStep(info, pxPerUnit, minPx) {
  return info.steps.find((s) => s * info.unit * MM * pxPerUnit >= minPx) ?? info.steps.at(-1);
}

function rulerGeometry(view, ortho, width, height) {
  const spec = VIEWS[view];
  const h = axisInfo(spec.u.axis), v = axisInfo(spec.v.axis);
  // Screen position of a model coordinate along each ruler.
  const xOf = (value) => width / 2 + (spec.u.sign * value * h.unit * MM - ortho.uMid) * ortho.scale;
  const yOf = (value) => height / 2 - (spec.v.sign * value * v.unit * MM - ortho.vMid) * ortho.scale;
  // Model ranges covered by the model's bounds.
  const hLo = Math.min(spec.u.sign * ortho.u0, spec.u.sign * ortho.u1) / (h.unit * MM);
  const hHi = Math.max(spec.u.sign * ortho.u0, spec.u.sign * ortho.u1) / (h.unit * MM);
  const vLo = Math.min(spec.v.sign * ortho.v0, spec.v.sign * ortho.v1) / (v.unit * MM);
  const vHi = Math.max(spec.v.sign * ortho.v0, spec.v.sign * ortho.v1) / (v.unit * MM);
  const hStep = tickStep(h, ortho.scale, 34), vStep = tickStep(v, ortho.scale, 22);
  const ticks = (lo, hi, step) => {
    const out = [];
    for (let t = Math.ceil(lo / step - 1e-9) * step; t <= hi + 1e-9; t += step) out.push(Math.round(t * 1000) / 1000);
    return out;
  };
  return { h, v, xOf, yOf, hTicks: ticks(hLo, hHi, hStep), vTicks: ticks(vLo, vHi, vStep), hLo, hHi, vLo, vHi };
}

function drawGrid(ctx, view, ortho, width, height, colour = "rgba(31, 35, 40, 0.07)") {
  const g = rulerGeometry(view, ortho, width, height);
  ctx.save();
  ctx.strokeStyle = colour;
  ctx.lineWidth = 1;
  const top = MARGIN.top - 4, bottom = height - MARGIN.bottom + 4;
  for (const t of g.hTicks) {
    const x = Math.round(g.xOf(t)) + 0.5;
    ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke();
  }
  for (const t of g.vTicks) {
    const y = Math.round(g.yOf(t)) + 0.5;
    ctx.beginPath(); ctx.moveTo(MARGIN.left - 4, y); ctx.lineTo(width - MARGIN.right + 4, y); ctx.stroke();
  }
  ctx.restore();
}

function drawRulers(svg, view, ortho, width, height) {
  const g = rulerGeometry(view, ortho, width, height);
  const axisY = height - MARGIN.bottom + 8, axisX = MARGIN.left - 8;
  const group = svgElement("g", { stroke: INK.quiet, "stroke-width": 1, fill: "none" });
  group.append(svgElement("line", { x1: g.xOf(g.hLo), y1: axisY, x2: g.xOf(g.hHi), y2: axisY }));
  group.append(svgElement("line", { x1: axisX, y1: g.yOf(g.vLo), x2: axisX, y2: g.yOf(g.vHi) }));
  svg.append(group);
  for (const t of g.hTicks) {
    const x = g.xOf(t);
    svg.append(svgElement("line", { x1: x, y1: axisY, x2: x, y2: axisY + 4, stroke: INK.quiet }));
    svg.append(text(x, axisY + 16, format(t), { anchor: "middle", fill: INK.text }));
  }
  for (const t of g.vTicks) {
    const y = g.yOf(t);
    svg.append(svgElement("line", { x1: axisX - 4, y1: y, x2: axisX, y2: y, stroke: INK.quiet }));
    svg.append(text(axisX - 7, y + 4, format(t), { anchor: "end", fill: INK.text }));
  }
  svg.append(text(width - MARGIN.right, height - 6, g.h.name, { anchor: "end", fill: INK.quiet }));
  const middle = (g.yOf(g.vLo) + g.yOf(g.vHi)) / 2;
  const vertical = text(0, 0, g.v.name, { anchor: "middle", fill: INK.quiet });
  vertical.setAttribute("transform", `translate(13 ${middle}) rotate(-90)`);
  svg.append(vertical);
}

function format(value) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function drawLabels(svg, camera, width, height) {
  const { scene, model } = state;
  const taken = [];
  const limit = 24;
  let shown = 0;
  const order = [...scene.labels].sort((a, b) => rank(a.kind) - rank(b.kind));
  for (const label of order) {
    if (shown >= limit) break;
    const box = model.partBounds[label.part];
    if (box.isEmpty()) continue;
    const anchor = new THREE.Vector3((box.min.x + box.max.x) / 2, box.max.y, (box.min.z + box.max.z) / 2).project(camera);
    if (anchor.z > 1 || Math.abs(anchor.x) > 1 || Math.abs(anchor.y) > 1) continue;
    const ax = (anchor.x + 1) / 2 * width, ay = (1 - anchor.y) / 2 * height;
    const w = measure(label.text, 600) + 8, h = 16;
    const spot = [[14, -22], [14, 8], [-14 - w, -22], [-14 - w, 8], [-w / 2, -34], [-w / 2, 18]]
      .map(([dx, dy]) => ({ x: ax + dx, y: ay + dy }))
      .find((r) => r.x > 2 && r.y > MARGIN.top - 6 && r.x + w < width - 2 && r.y + h < height - 2 && !taken.some((t) => overlaps(t, r.x, r.y, w, h)));
    if (!spot) continue;
    taken.push({ x: spot.x, y: spot.y, w, h });
    const colour = INK[label.kind];
    const tx = spot.x < ax ? spot.x + w : spot.x, ty = spot.y + h / 2;
    svg.append(svgElement("line", { x1: ax, y1: ay, x2: tx, y2: ty, stroke: colour, "stroke-width": 1.2 }));
    svg.append(svgElement("circle", { cx: ax, cy: ay, r: 2.5, fill: colour }));
    svg.append(svgElement("rect", { x: spot.x, y: spot.y, width: w, height: h, rx: 3, fill: "#ffffff", stroke: colour, "stroke-width": 1 }));
    svg.append(text(spot.x + 4, spot.y + 12, label.text, { weight: 600, fill: colour }));
    shown += 1;
  }
}

function rank(kind) {
  return kind === "error" ? 0 : kind === "warning" ? 1 : 2;
}

function overlaps(t, x, y, w, h) {
  return x < t.x + t.w + 4 && t.x < x + w + 4 && y < t.y + t.h + 2 && t.y < y + h + 2;
}

function drawCompass(svg, camera, centre, width) {
  const a = centre.clone().project(camera);
  const b = centre.clone().add(new THREE.Vector3(0, 0, -50)).project(camera);
  let dx = b.x - a.x, dy = -(b.y - a.y);
  const length = Math.hypot(dx, dy) || 1;
  dx /= length; dy /= length;
  const cx = width - 30, cy = 30, r = 14;
  const g = svgElement("g", {});
  g.append(svgElement("circle", { cx, cy, r: r + 4, fill: "#ffffff", stroke: "#d0d7de" }));
  g.append(svgElement("line", { x1: cx - dx * r, y1: cy - dy * r, x2: cx + dx * r, y2: cy + dy * r, stroke: INK.text, "stroke-width": 1.5 }));
  g.append(svgElement("circle", { cx: cx + dx * r, cy: cy + dy * r, r: 2.5, fill: INK.text }));
  g.append(text(cx + dx * (r + 13), cy + dy * (r + 13) + 4, "N", { anchor: "middle", weight: 700, fill: INK.text }));
  svg.append(g);
}

let measureContext = null;
function measure(value, weight = 400) {
  measureContext ??= document.createElement("canvas").getContext("2d");
  measureContext.font = `${weight} ${FONT}`;
  return measureContext.measureText(value).width;
}

function svgElement(name, attributes) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
  return element;
}

function text(x, y, value, { anchor = "start", weight = 400, fill = INK.text } = {}) {
  const element = svgElement("text", { x, y, "text-anchor": anchor, "font-weight": weight, fill, style: `font: ${weight} ${FONT}`, "paint-order": "stroke", stroke: "#ffffff", "stroke-width": 3, "stroke-linejoin": "round" });
  element.textContent = value;
  return element;
}

// ---------------------------------------------------------------------------------------------
// The standalone viewer: orbit the scene in a browser

export async function mount(element, scene) {
  const { OrbitControls } = await import("three/addons/controls/OrbitControls.js");
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.localClippingEnabled = true;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.setClearColor(PAPER, 1);
  element.append(renderer.domElement);
  const three = new THREE.Scene();
  const hemi = new THREE.HemisphereLight(0xffffff, 0x8d949e, 1.45);
  const sun = new THREE.DirectionalLight(0xffffff, 2.1);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.6;
  three.add(hemi, sun, sun.target);
  let model = buildModel(scene);
  three.add(model.root);
  const size = model.bounds.getSize(new THREE.Vector3());
  const centre = model.bounds.getCenter(new THREE.Vector3());
  const radius = size.length();
  sun.position.copy(centre).addScaledVector(new THREE.Vector3(-0.55, 1.1, 0.75).normalize(), radius * 1.5);
  sun.target.position.copy(centre);
  Object.assign(sun.shadow.camera, { left: -radius, right: radius, top: radius, bottom: -radius, near: radius * 0.1, far: radius * 4 });
  sun.shadow.camera.updateProjectionMatrix();
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(radius * 6, radius * 6), new THREE.ShadowMaterial({ opacity: 0.16 }));
  ground.rotation.x = -Math.PI / 2;
  ground.position.set(centre.x, model.bounds.min.y - 0.02, centre.z);
  ground.receiveShadow = true;
  three.add(ground);

  const camera = new THREE.PerspectiveCamera(30, 1, 1, radius * 40);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = !matchMedia("(prefers-reduced-motion: reduce)").matches;
  const render = () => renderer.render(three, camera);
  controls.addEventListener("change", render);

  const look = (view) => {
    const w = element.clientWidth, h = element.clientHeight;
    camera.aspect = w / h;
    if (view === "iso") {
      const iso = isoCamera(model.bounds, w, h);
      camera.position.copy(iso.camera.position);
      controls.target.copy(iso.target);
    } else {
      const spec = VIEWS[view];
      const fit = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov) / 2) * 0.55;
      camera.position.copy(centre).addScaledVector(vec(spec.dir), fit);
      camera.up.copy(vec(spec.up));
      controls.target.copy(centre);
    }
    camera.updateProjectionMatrix();
    controls.update();
    render();
  };
  const resize = () => {
    renderer.setSize(element.clientWidth, element.clientHeight);
    camera.aspect = element.clientWidth / element.clientHeight;
    camera.updateProjectionMatrix();
    render();
  };
  new ResizeObserver(resize).observe(element);
  resize();
  look("iso");
  const loop = () => {
    if (controls.update()) render();
    requestAnimationFrame(loop);
  };
  loop();

  // Cut the model at a height, plate by plate, to look inside.
  const cut = (plates) => {
    const plane = new THREE.Plane(new THREE.Vector3(0, -1, 0), plates * PLATE * MM);
    model.root.traverse((object) => {
      if (object.material) object.material.clippingPlanes = [...model.planes, plane];
    });
    render();
  };
  return { look, cut, topPlates: scene.bounds[5] / PLATE };
}

// Headless pages call these through window.bricky.
export const api = { load, draw, ready: true };
