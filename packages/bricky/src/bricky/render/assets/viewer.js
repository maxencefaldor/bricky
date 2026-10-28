// The bricky viewer draws a scene with three.js.
//
// One module serves two readers. Headless Chromium calls `load` and `draw` to make the pictures an
// agent reads after every build: orthographic views with rulers, a perspective view, and the marks
// and labels of diagnostics. The standalone HTML viewer calls `mount` to let people orbit the same
// scene.
//
// Scenes come from bricky.render.scene in base units of 0.4 mm. Model axes are x east, y north and
// z up. three.js axes are x right, y up and z toward the viewer, so model y maps to three.js -z.

import * as THREE from "three";

const BASE_UNIT = 0.4; // millimeters
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
  perspective: { title: "PERSPECTIVE", note: "from the south-east" },
  front: { title: "FRONT", note: "looking north", direction: [0, 0, 1], up: [0, 1, 0], u: { vector: [1, 0, 0], axis: "x", sign: 1 }, v: { vector: [0, 1, 0], axis: "z", sign: 1 } },
  back: { title: "BACK", note: "looking south", direction: [0, 0, -1], up: [0, 1, 0], u: { vector: [-1, 0, 0], axis: "x", sign: -1 }, v: { vector: [0, 1, 0], axis: "z", sign: 1 } },
  right: { title: "RIGHT", note: "looking west", direction: [1, 0, 0], up: [0, 1, 0], u: { vector: [0, 0, -1], axis: "y", sign: 1 }, v: { vector: [0, 1, 0], axis: "z", sign: 1 } },
  left: { title: "LEFT", note: "looking east", direction: [-1, 0, 0], up: [0, 1, 0], u: { vector: [0, 0, 1], axis: "y", sign: -1 }, v: { vector: [0, 1, 0], axis: "z", sign: 1 } },
  top: { title: "TOP", note: "north up", direction: [0, 1, 0], up: [0, 0, -1], u: { vector: [1, 0, 0], axis: "x", sign: 1 }, v: { vector: [0, 0, -1], axis: "y", sign: 1 } },
};
const SHEET = ["perspective", "front", "right", "top"];

function toThree(x, y, z) {
  return new THREE.Vector3(x * BASE_UNIT, z * BASE_UNIT, -y * BASE_UNIT);
}

function vector(a) {
  return new THREE.Vector3(a[0], a[1], a[2]);
}

// ---------------------------------------------------------------------------------------------
// Building the three.js scene from a bricky scene

export function buildModel(scene) {
  const root = new THREE.Group();
  const planes = scene.clips.map(clipPlane);
  // Bodies take their colors from vertices, and studs from instances: two sets of materials.
  const bodies = materials(planes, true);
  const studs = materials(planes, false);
  for (const material of Object.values(studs)) material.side = THREE.FrontSide;

  const colors = scene.colors.map((color) => new THREE.Color(color.rgb));
  const tint = { error: new THREE.Color(INK.error), warning: new THREE.Color("#e8a400") };
  const kindOf = (element) => {
    if (element[1] & FLAG.GHOST) return "ghost";
    const type = scene.colors[element[0]].type;
    return type === "transparent" ? "clear" : type === "pearl" ? "pearl" : "solid";
  };
  const colorOf = (element) => {
    const color = colors[element[0]].clone();
    if (element[1] & FLAG.ERROR) color.lerp(tint.error, 0.55);
    else if (element[1] & FLAG.WARNING) color.lerp(tint.warning, 0.45);
    return color;
  };

  // The bounds of each element, where its label points.
  const elementBounds = scene.elements.map(() => new THREE.Box3());
  for (const box of scene.boxes) {
    elementBounds[box[6]].expandByPoint(toThree(box[0], box[1], box[2])).expandByPoint(toThree(box[3], box[4], box[5]));
  }
  for (const mesh of scene.meshes) {
    const vertices = mesh.vertices;
    for (let k = 0; k < vertices.length; k += 3) elementBounds[mesh.element].expandByPoint(toThree(vertices[k], vertices[k + 1], vertices[k + 2]));
  }

  // Bodies: the faces of every box and mesh, merged into one three.js mesh per material kind. The
  // scene has already left out the faces pressed against opaque neighbors.
  const faces = { solid: new FaceBuffer(), pearl: new FaceBuffer(), clear: new FaceBuffer(), ghost: new FaceBuffer() };
  for (const box of scene.boxes) {
    const element = scene.elements[box[6]];
    faces[kindOf(element)].addBox(box, colorOf(element));
  }
  for (const mesh of scene.meshes) {
    const element = scene.elements[mesh.element];
    faces[kindOf(element)].addMesh(mesh, colorOf(element));
  }
  for (const [kind, buffer] of Object.entries(faces)) {
    if (!buffer.count) continue;
    const mesh = new THREE.Mesh(buffer.geometry(), bodies[kind]);
    mesh.castShadow = kind === "solid" || kind === "pearl";
    mesh.receiveShadow = kind !== "ghost";
    mesh.renderOrder = kind === "clear" || kind === "ghost" ? 2 : 0;
    root.add(mesh);
  }

  // Studs: cylinders standing on their element's face, along the stud's axis. The scene leaves out
  // the studs seated in an anti-stud, hidden inside the element above.
  const studMeshes = [];
  const cylinder = studGeometry();
  const byKind = { solid: [], pearl: [], clear: [], ghost: [] };
  for (const stud of scene.studs) byKind[kindOf(scene.elements[stud[4]])].push(stud);
  const matrix = new THREE.Matrix4();
  const rotation = new THREE.Quaternion();
  const upright = new THREE.Vector3(0, 1, 0);
  const one = new THREE.Vector3(1, 1, 1);
  for (const [kind, list] of Object.entries(byKind)) {
    if (!list.length) continue;
    const mesh = new THREE.InstancedMesh(cylinder, studs[kind], list.length);
    list.forEach((stud, i) => {
      const [x, y, z] = AXES[stud[3]];
      rotation.setFromUnitVectors(upright, new THREE.Vector3(x, z, -y));
      mesh.setMatrixAt(i, matrix.compose(toThree(stud[0], stud[1], stud[2]), rotation, one));
      if (kind !== "ghost") mesh.setColorAt(i, colorOf(scene.elements[stud[4]]));
    });
    mesh.castShadow = kind === "solid" || kind === "pearl";
    mesh.receiveShadow = kind !== "ghost";
    mesh.renderOrder = kind === "clear" || kind === "ghost" ? 2 : 0;
    studMeshes.push(remember(mesh));
    root.add(mesh);
  }

  // Edges: dark outlines that set every element apart. Highlighted, changed and diagnosed elements
  // get colored outlines, and the outlines of diagnosed elements draw over everything.
  const outline = (filter) => {
    const points = [];
    for (const box of scene.boxes) if (filter(scene.elements[box[6]][1])) pushEdges(points, box);
    for (const mesh of scene.meshes) if (filter(scene.elements[mesh.element][1])) pushMeshEdges(points, mesh);
    for (const stud of scene.studs) if (filter(scene.elements[stud[4]][1])) pushRim(points, stud);
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
    [outline((flags) => !(flags & (FLAG.GHOST | FLAG.ERROR | FLAG.WARNING | FLAG.HIGHLIGHT | FLAG.CHANGED))), edgeMaterials.plain, 1],
    [outline((flags) => flags & FLAG.CHANGED && !(flags & (FLAG.GHOST | FLAG.ERROR | FLAG.WARNING | FLAG.HIGHLIGHT))), edgeMaterials.changed, 2],
    [outline((flags) => flags & FLAG.GHOST), edgeMaterials.ghost, 3],
    [outline((flags) => flags & FLAG.HIGHLIGHT && !(flags & (FLAG.ERROR | FLAG.WARNING))), edgeMaterials.highlight, 4],
    [outline((flags) => flags & FLAG.WARNING && !(flags & FLAG.ERROR)), edgeMaterials.warning, 5],
    [outline((flags) => flags & FLAG.ERROR), edgeMaterials.error, 6],
  ];
  for (const [geometry, material, order] of lines) {
    if (!geometry.attributes.position.count) continue;
    const segments = new THREE.LineSegments(geometry, material);
    segments.renderOrder = order;
    root.add(segments);
  }

  // Diagnostic regions: dashed boxes drawn over everything.
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
  return { root, bounds, elementBounds, edgeMaterials, planes, studMeshes };
}

// Snapshot an instanced mesh's matrices and colors, so views can reorder its instances.
function remember(mesh) {
  const count = mesh.count;
  const matrices = mesh.instanceMatrix.array.slice();
  const colors = mesh.instanceColor ? mesh.instanceColor.array.slice() : null;
  const depth = new Float32Array(count);
  const order = new Uint32Array(count);
  return { mesh, count, matrices, colors, depth, order };
}

// Order opaque instances nearest first, so the depth test skips the fragments they hide.
function orderInstances(meshes, camera) {
  const forward = new THREE.Vector3();
  camera.getWorldDirection(forward);
  const origin = camera.position;
  for (const item of meshes) {
    const { mesh, count, matrices, colors, depth, order } = item;
    if (mesh.material.transparent) continue;
    for (let i = 0; i < count; i++) {
      const offset = i * 16;
      depth[i] = (matrices[offset + 12] - origin.x) * forward.x + (matrices[offset + 13] - origin.y) * forward.y + (matrices[offset + 14] - origin.z) * forward.z;
      order[i] = i;
    }
    order.sort((a, b) => depth[a] - depth[b]);
    const targetMatrices = mesh.instanceMatrix.array;
    const targetColors = mesh.instanceColor ? mesh.instanceColor.array : null;
    for (let k = 0; k < count; k++) {
      const i = order[k];
      targetMatrices.set(matrices.subarray(i * 16, i * 16 + 16), k * 16);
      if (targetColors && colors) targetColors.set(colors.subarray(i * 3, i * 3 + 3), k * 3);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }
}

// A stud: a cylinder 4.8 mm wide and 1.7 mm tall with a flat top, standing on the origin along +y.
// The stud's bottom always rests against its element, so the cylinder has no bottom cap.
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
  const center = positions.length / 3;
  positions.push(0, height, 0);
  normals.push(0, 1, 0);
  for (let i = 0; i <= segments; i++) {
    const angle = (i / segments) * Math.PI * 2;
    positions.push(Math.sin(angle) * radius, height, Math.cos(angle) * radius);
    normals.push(0, 1, 0);
  }
  for (let i = 0; i < segments; i++) indices.push(center, center + 1 + i, center + 2 + i);
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

// The six faces of a box in three.js axes: a normal, and two tangents whose cross product is the
// normal, so every face winds counter-clockwise seen from outside. Bits follow the scene's mask:
// model -x +x -y +y -z +z, where model y is three.js -z and model z is three.js y.
const FACES = [
  { bit: 0, axis: 0, high: false, normal: [-1, 0, 0], tangent1: 2, tangent2: 1 },
  { bit: 1, axis: 0, high: true, normal: [1, 0, 0], tangent1: 1, tangent2: 2 },
  { bit: 2, axis: 2, high: true, normal: [0, 0, 1], tangent1: 0, tangent2: 1 },
  { bit: 3, axis: 2, high: false, normal: [0, 0, -1], tangent1: 1, tangent2: 0 },
  { bit: 4, axis: 1, high: false, normal: [0, -1, 0], tangent1: 0, tangent2: 2 },
  { bit: 5, axis: 1, high: true, normal: [0, 1, 0], tangent1: 2, tangent2: 0 },
];

class FaceBuffer {
  constructor() {
    this.positions = [];
    this.normals = [];
    this.colors = [];
    this.indices = [];
    this.count = 0;
  }

  addBox(box, color) {
    const low = [box[0] * BASE_UNIT, box[2] * BASE_UNIT, -box[4] * BASE_UNIT];
    const high = [box[3] * BASE_UNIT, box[5] * BASE_UNIT, -box[1] * BASE_UNIT];
    for (const face of FACES) {
      if (!(box[7] & (1 << face.bit))) continue;
      const base = this.positions.length / 3;
      const point = [0, 0, 0];
      point[face.axis] = face.high ? high[face.axis] : low[face.axis];
      for (const [corner1, corner2] of [[low, low], [high, low], [high, high], [low, high]]) {
        point[face.tangent1] = corner1[face.tangent1];
        point[face.tangent2] = corner2[face.tangent2];
        this.positions.push(point[0], point[1], point[2]);
        this.normals.push(...face.normal);
        this.colors.push(color.r, color.g, color.b);
      }
      this.indices.push(base, base + 1, base + 2, base, base + 2, base + 3);
      this.count += 1;
    }
  }

  // A mesh element: its faces, each fanned into triangles with a flat normal.
  addMesh(mesh, color) {
    const vertices = mesh.vertices;
    for (const face of mesh.faces) {
      const points = face.map((i) => [vertices[3 * i] * BASE_UNIT, vertices[3 * i + 2] * BASE_UNIT, -vertices[3 * i + 1] * BASE_UNIT]);
      let x = 0, y = 0, z = 0;
      for (let k = 0; k < points.length; k++) {
        const p = points[k], q = points[(k + 1) % points.length];
        x += (p[1] - q[1]) * (p[2] + q[2]);
        y += (p[2] - q[2]) * (p[0] + q[0]);
        z += (p[0] - q[0]) * (p[1] + q[1]);
      }
      const length = Math.hypot(x, y, z) || 1;
      const base = this.positions.length / 3;
      for (const p of points) {
        this.positions.push(p[0], p[1], p[2]);
        this.normals.push(x / length, y / length, z / length);
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

// The rim of a stud's top. Seen from above, a stud is lit exactly like the face it stands on, so
// only its outline shows it.
const RIM = Array.from({ length: 16 }, (_, i) => [Math.cos((i / 16) * 2 * Math.PI) * 2.4, Math.sin((i / 16) * 2 * Math.PI) * 2.4]);
function pushRim(points, stud) {
  const [x, y, z] = AXES[stud[3]];
  const axis = new THREE.Vector3(x, z, -y);
  const center = toThree(stud[0], stud[1], stud[2]).addScaledVector(axis, 1.7);
  const side = Math.abs(axis.y) > 0.5 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0);
  const other = new THREE.Vector3().crossVectors(axis, side);
  for (let i = 0; i < RIM.length; i++) {
    const [x0, y0] = RIM[i];
    const [x1, y1] = RIM[(i + 1) % RIM.length];
    const p = center.clone().addScaledVector(side, x0).addScaledVector(other, y0);
    const q = center.clone().addScaledVector(side, x1).addScaledVector(other, y1);
    points.push(p.x, p.y, p.z, q.x, q.y, q.z);
  }
}

function pushEdges(points, box) {
  const low = toThree(box[0], box[4], box[2]);
  const high = toThree(box[3], box[1], box[5]);
  const xs = [low.x, high.x], ys = [low.y, high.y], zs = [low.z, high.z];
  for (const y of ys) for (const z of zs) points.push(xs[0], y, z, xs[1], y, z);
  for (const x of xs) for (const z of zs) points.push(x, ys[0], z, x, ys[1], z);
  for (const x of xs) for (const y of ys) points.push(x, y, zs[0], x, y, zs[1]);
}

// The edges where a mesh's surface folds, as the scene lists them.
function pushMeshEdges(points, mesh) {
  const vertices = mesh.vertices;
  for (let k = 0; k < mesh.edges.length; k += 2) {
    const a = 3 * mesh.edges[k], b = 3 * mesh.edges[k + 1];
    points.push(vertices[a] * BASE_UNIT, vertices[a + 2] * BASE_UNIT, -vertices[a + 1] * BASE_UNIT, vertices[b] * BASE_UNIT, vertices[b + 2] * BASE_UNIT, -vertices[b + 1] * BASE_UNIT);
  }
}

function clipPlane(clip) {
  // A three.js plane keeps the points where normal . p + constant >= 0.
  const value = clip.value * BASE_UNIT;
  const below = clip.keep === "below";
  if (clip.axis === "z") return new THREE.Plane(new THREE.Vector3(0, below ? -1 : 1, 0), below ? value : -value);
  if (clip.axis === "x") return new THREE.Plane(new THREE.Vector3(below ? -1 : 1, 0, 0), below ? value : -value);
  // Model y is three.js -z: keeping y < v keeps three.js z > -v.
  return new THREE.Plane(new THREE.Vector3(0, 0, below ? 1 : -1), value * (below ? 1 : -1));
}

// ---------------------------------------------------------------------------------------------
// Cameras

function orthographicCamera(view, bounds, width, height) {
  const layout = VIEWS[view];
  const u = vector(layout.u.vector), v = vector(layout.v.vector), direction = vector(layout.direction);
  const corners = boxCorners(bounds);
  const us = corners.map((corner) => corner.dot(u));
  const vs = corners.map((corner) => corner.dot(v));
  const depths = corners.map((corner) => corner.dot(direction));
  const [u0, u1, v0, v1] = [Math.min(...us), Math.max(...us), Math.min(...vs), Math.max(...vs)];
  const areaWidth = width - MARGIN.left - MARGIN.right, areaHeight = height - MARGIN.top - MARGIN.bottom;
  const scale = 0.92 * Math.min(areaWidth / Math.max(u1 - u0, 1e-3), areaHeight / Math.max(v1 - v0, 1e-3));
  // The screen center of the drawing area, in model millimeters along u and v.
  const uMiddle = (u0 + u1) / 2 + (width / 2 - (MARGIN.left + areaWidth / 2)) / scale;
  const vMiddle = (v0 + v1) / 2 - (height / 2 - (MARGIN.top + areaHeight / 2)) / scale;
  const depth = Math.max(...depths) + 200;
  const camera = new THREE.OrthographicCamera(-width / 2 / scale, width / 2 / scale, height / 2 / scale, -height / 2 / scale, 1, depth - Math.min(...depths) + 400);
  camera.up.copy(vector(layout.up));
  camera.position.copy(u.clone().multiplyScalar(uMiddle).add(v.clone().multiplyScalar(vMiddle)).add(direction.clone().multiplyScalar(depth)));
  camera.lookAt(camera.position.clone().sub(direction));
  camera.updateMatrixWorld();
  camera.updateProjectionMatrix();
  return { camera, scale, uMiddle, vMiddle, u0, u1, v0, v1 };
}

function perspectiveCamera(bounds, width, height, azimuthDegrees = 35, elevationDegrees = 30) {
  const camera = new THREE.PerspectiveCamera(24, width / height, 1, 1e6);
  const azimuth = THREE.MathUtils.degToRad(azimuthDegrees), elevation = THREE.MathUtils.degToRad(elevationDegrees);
  const direction = new THREE.Vector3(Math.sin(azimuth) * Math.cos(elevation), Math.sin(elevation), Math.cos(azimuth) * Math.cos(elevation));
  const target = bounds.getCenter(new THREE.Vector3());
  const corners = boxCorners(bounds);
  const radius = bounds.getSize(new THREE.Vector3()).length() / 2;
  let distance = radius * 4;
  const right = new THREE.Vector3(), up = new THREE.Vector3();
  // Fit the drawing area below the panel title: center the projected box, then scale the distance.
  // The title's height, in normalized device coordinates:
  const frameTop = (MARGIN.top - 8) / height * 2;
  for (let i = 0; i < 10; i++) {
    camera.position.copy(target).addScaledVector(direction, distance);
    camera.near = distance / 100;
    camera.far = distance * 10;
    camera.lookAt(target);
    camera.updateMatrixWorld();
    camera.updateProjectionMatrix();
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const corner of corners) {
      const point = corner.clone().project(camera);
      x0 = Math.min(x0, point.x); x1 = Math.max(x1, point.x); y0 = Math.min(y0, point.y); y1 = Math.max(y1, point.y);
    }
    const half = distance * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2);
    right.setFromMatrixColumn(camera.matrixWorld, 0);
    up.setFromMatrixColumn(camera.matrixWorld, 1);
    const wantedY = -frameTop / 2;
    target.addScaledVector(right, ((x0 + x1) / 2) * half * camera.aspect).addScaledVector(up, ((y0 + y1) / 2 - wantedY) * half);
    const extent = Math.max((x1 - x0) / 2, (y1 - y0) / 2 / (1 - frameTop / 2));
    distance *= 0.4 + 0.6 * (extent / 0.86);
  }
  camera.position.copy(target).addScaledVector(direction, distance);
  camera.lookAt(target);
  camera.updateMatrixWorld();
  camera.updateProjectionMatrix();
  const pixelsPerStud = (STUD * BASE_UNIT) / (2 * distance * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2)) * height;
  return { camera, target, direction, pixelsPerStud };
}

function boxCorners(box) {
  const corners = [];
  for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) corners.push(new THREE.Vector3(x, y, z));
  return corners;
}

// ---------------------------------------------------------------------------------------------
// Headless drawing: load a scene once, then draw any view onto the page

const state = { renderer: null, three: null, model: null, scene: null, hemisphere: null, sun: null, ground: null, timings: [] };

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
  state.hemisphere = new THREE.HemisphereLight(0xffffff, 0x8d949e, 1.5);
  state.sun = new THREE.DirectionalLight(0xffffff, 2.1);
  state.sun.shadow.mapSize.set(1024, 1024);
  state.sun.shadow.bias = -0.0004;
  state.sun.shadow.normalBias = 0.6;
  state.three.add(state.hemisphere, state.sun, state.sun.target);
  state.model = buildModel(scene);
  state.three.add(state.model.root);
  state.ground = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.ShadowMaterial({ opacity: 0.16 }));
  state.ground.rotation.x = -Math.PI / 2;
  state.ground.receiveShadow = true;
  state.three.add(state.ground);
  state.scene = scene;
  return { elements: scene.elements.length, milliseconds: Math.round(performance.now() - started) };
}

// Free the graphics memory of a scene about to be replaced.
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
  const panelWidth = Math.floor(width / columns), panelHeight = Math.floor((height - HEADER) / rows);
  views.forEach((name, i) => {
    const panel = drawPanel(name, panelWidth, panelHeight);
    panel.style.left = `${(i % columns) * panelWidth}px`;
    panel.style.top = `${HEADER + Math.floor(i / columns) * panelHeight}px`;
    sheet.append(panel);
  });
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  return { width, height, views, timings: state.timings };
}

function drawPanel(view, width, height) {
  const { renderer, three, model, sun, hemisphere, ground } = state;
  const panel = document.createElement("div");
  panel.className = "panel";
  panel.style.width = `${width}px`;
  panel.style.height = `${height}px`;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  context.fillStyle = PAPER;
  context.fillRect(0, 0, width, height);
  const svg = svgElement("svg", { width, height, viewBox: `0 0 ${width} ${height}` });
  const size = model.bounds.getSize(new THREE.Vector3());
  const center = model.bounds.getCenter(new THREE.Vector3());

  let camera, pixelsPerStud, orthographic = null;
  if (view === "perspective") {
    const perspective = perspectiveCamera(model.bounds, width, height);
    camera = perspective.camera;
    pixelsPerStud = perspective.pixelsPerStud;
    const radius = size.length();
    const light = new THREE.Vector3(-0.55, 1.1, 0.75).normalize();
    sun.position.copy(center).addScaledVector(light, radius * 1.5);
    sun.target.position.copy(center);
    sun.castShadow = true;
    const shadowCamera = sun.shadow.camera;
    shadowCamera.left = -radius; shadowCamera.right = radius; shadowCamera.top = radius; shadowCamera.bottom = -radius;
    shadowCamera.near = radius * 0.1; shadowCamera.far = radius * 4;
    shadowCamera.updateProjectionMatrix();
    ground.visible = true;
    ground.position.set(center.x, model.bounds.min.y - 0.02, center.z);
    ground.scale.set(radius * 6, radius * 6, 1);
    renderer.setClearColor(PAPER, 1);
  } else {
    orthographic = orthographicCamera(view, model.bounds, width, height);
    camera = orthographic.camera;
    pixelsPerStud = orthographic.scale * STUD * BASE_UNIT;
    const layout = VIEWS[view];
    const light = vector(layout.direction).multiplyScalar(2).add(vector(layout.up).multiplyScalar(1.2)).sub(vector(layout.u.vector).multiplyScalar(0.8)).normalize();
    sun.position.copy(center).addScaledVector(light, size.length() * 2);
    sun.target.position.copy(center);
    sun.castShadow = false;
    ground.visible = false;
    renderer.setClearColor(0x000000, 0);
    drawGrid(context, view, orthographic, width, height);
  }
  hemisphere.intensity = view === "perspective" ? 1.45 : 1.7;
  // Fainter edges when elements are small on screen, so outlines never swamp the colors.
  const opacity = Math.min(0.42, Math.max(0.07, 0.03 * pixelsPerStud));
  model.edgeMaterials.plain.opacity = opacity;

  const started = performance.now();
  orderInstances(model.studMeshes, camera);
  renderer.setSize(width, height, false);
  renderer.render(three, camera);
  context.drawImage(renderer.domElement, 0, 0, width, height);
  if (orthographic) drawGrid(context, view, orthographic, width, height, "rgba(31, 35, 40, 0.10)");
  state.timings.push([view, Math.round(performance.now() - started)]);

  svg.append(text(12, 20, `${VIEWS[view].title}`, { weight: 700, fill: INK.text }));
  svg.append(text(12 + measure(VIEWS[view].title, 700) + 8, 20, VIEWS[view].note, { fill: INK.quiet }));
  if (view === "perspective") drawCompass(svg, camera, center, width);
  else drawRulers(svg, view, orthographic, width, height);
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
  const flags = scene.elements.reduce((all, element) => all | element[1], 0);
  const keys = [];
  if (flags & FLAG.ERROR) keys.push(["error", "error"]);
  if (flags & FLAG.WARNING) keys.push(["warning", "warning"]);
  if (flags & FLAG.HIGHLIGHT) keys.push(["highlight", "highlighted"]);
  if (flags & FLAG.CHANGED) keys.push(["changed", "new or changed since the last build"]);
  if (scene.clips.length) keys.push([null, `clip: ${scene.clips.map(describeClip).join(", ")}`]);
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

// Pick the smallest tick step, in studs or plates, that leaves `minimumPixels` between labels.
function tickStep(info, pixelsPerMillimeter, minimumPixels) {
  return info.steps.find((step) => step * info.unit * BASE_UNIT * pixelsPerMillimeter >= minimumPixels) ?? info.steps.at(-1);
}

function rulerGeometry(view, orthographic, width, height) {
  const layout = VIEWS[view];
  const u = axisInfo(layout.u.axis), v = axisInfo(layout.v.axis);
  // The screen position of a coordinate along each ruler.
  const xOf = (value) => width / 2 + (layout.u.sign * value * u.unit * BASE_UNIT - orthographic.uMiddle) * orthographic.scale;
  const yOf = (value) => height / 2 - (layout.v.sign * value * v.unit * BASE_UNIT - orthographic.vMiddle) * orthographic.scale;
  // The ranges the model's bounds cover, in studs or plates.
  const uLow = Math.min(layout.u.sign * orthographic.u0, layout.u.sign * orthographic.u1) / (u.unit * BASE_UNIT);
  const uHigh = Math.max(layout.u.sign * orthographic.u0, layout.u.sign * orthographic.u1) / (u.unit * BASE_UNIT);
  const vLow = Math.min(layout.v.sign * orthographic.v0, layout.v.sign * orthographic.v1) / (v.unit * BASE_UNIT);
  const vHigh = Math.max(layout.v.sign * orthographic.v0, layout.v.sign * orthographic.v1) / (v.unit * BASE_UNIT);
  const uStep = tickStep(u, orthographic.scale, 34), vStep = tickStep(v, orthographic.scale, 22);
  const ticks = (low, high, step) => {
    const values = [];
    for (let tick = Math.ceil(low / step - 1e-9) * step; tick <= high + 1e-9; tick += step) values.push(Math.round(tick * 1000) / 1000);
    return values;
  };
  return { u, v, xOf, yOf, uTicks: ticks(uLow, uHigh, uStep), vTicks: ticks(vLow, vHigh, vStep), uLow, uHigh, vLow, vHigh };
}

function drawGrid(context, view, orthographic, width, height, color = "rgba(31, 35, 40, 0.07)") {
  const ruler = rulerGeometry(view, orthographic, width, height);
  context.save();
  context.strokeStyle = color;
  context.lineWidth = 1;
  const top = MARGIN.top - 4, bottom = height - MARGIN.bottom + 4;
  for (const tick of ruler.uTicks) {
    const x = Math.round(ruler.xOf(tick)) + 0.5;
    context.beginPath(); context.moveTo(x, top); context.lineTo(x, bottom); context.stroke();
  }
  for (const tick of ruler.vTicks) {
    const y = Math.round(ruler.yOf(tick)) + 0.5;
    context.beginPath(); context.moveTo(MARGIN.left - 4, y); context.lineTo(width - MARGIN.right + 4, y); context.stroke();
  }
  context.restore();
}

function drawRulers(svg, view, orthographic, width, height) {
  const ruler = rulerGeometry(view, orthographic, width, height);
  const axisY = height - MARGIN.bottom + 8, axisX = MARGIN.left - 8;
  const group = svgElement("g", { stroke: INK.quiet, "stroke-width": 1, fill: "none" });
  group.append(svgElement("line", { x1: ruler.xOf(ruler.uLow), y1: axisY, x2: ruler.xOf(ruler.uHigh), y2: axisY }));
  group.append(svgElement("line", { x1: axisX, y1: ruler.yOf(ruler.vLow), x2: axisX, y2: ruler.yOf(ruler.vHigh) }));
  svg.append(group);
  for (const tick of ruler.uTicks) {
    const x = ruler.xOf(tick);
    svg.append(svgElement("line", { x1: x, y1: axisY, x2: x, y2: axisY + 4, stroke: INK.quiet }));
    svg.append(text(x, axisY + 16, format(tick), { anchor: "middle", fill: INK.text }));
  }
  for (const tick of ruler.vTicks) {
    const y = ruler.yOf(tick);
    svg.append(svgElement("line", { x1: axisX - 4, y1: y, x2: axisX, y2: y, stroke: INK.quiet }));
    svg.append(text(axisX - 7, y + 4, format(tick), { anchor: "end", fill: INK.text }));
  }
  svg.append(text(width - MARGIN.right, height - 6, ruler.u.name, { anchor: "end", fill: INK.quiet }));
  const middle = (ruler.yOf(ruler.vLow) + ruler.yOf(ruler.vHigh)) / 2;
  const vertical = text(0, 0, ruler.v.name, { anchor: "middle", fill: INK.quiet });
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
    const box = model.elementBounds[label.element];
    if (box.isEmpty()) continue;
    const anchor = new THREE.Vector3((box.min.x + box.max.x) / 2, box.max.y, (box.min.z + box.max.z) / 2).project(camera);
    if (anchor.z > 1 || Math.abs(anchor.x) > 1 || Math.abs(anchor.y) > 1) continue;
    const anchorX = (anchor.x + 1) / 2 * width, anchorY = (1 - anchor.y) / 2 * height;
    const boxWidth = measure(label.text, 600) + 8, boxHeight = 16;
    const spot = [[14, -22], [14, 8], [-14 - boxWidth, -22], [-14 - boxWidth, 8], [-boxWidth / 2, -34], [-boxWidth / 2, 18]]
      .map(([offsetX, offsetY]) => ({ x: anchorX + offsetX, y: anchorY + offsetY }))
      .find((candidate) => candidate.x > 2 && candidate.y > MARGIN.top - 6 && candidate.x + boxWidth < width - 2 && candidate.y + boxHeight < height - 2 && !taken.some((other) => overlaps(other, candidate.x, candidate.y, boxWidth, boxHeight)));
    if (!spot) continue;
    taken.push({ x: spot.x, y: spot.y, width: boxWidth, height: boxHeight });
    const color = INK[label.kind];
    const endX = spot.x < anchorX ? spot.x + boxWidth : spot.x, endY = spot.y + boxHeight / 2;
    svg.append(svgElement("line", { x1: anchorX, y1: anchorY, x2: endX, y2: endY, stroke: color, "stroke-width": 1.2 }));
    svg.append(svgElement("circle", { cx: anchorX, cy: anchorY, r: 2.5, fill: color }));
    svg.append(svgElement("rect", { x: spot.x, y: spot.y, width: boxWidth, height: boxHeight, rx: 3, fill: "#ffffff", stroke: color, "stroke-width": 1 }));
    svg.append(text(spot.x + 4, spot.y + 12, label.text, { weight: 600, fill: color }));
    shown += 1;
  }
}

function rank(kind) {
  return kind === "error" ? 0 : kind === "warning" ? 1 : 2;
}

function overlaps(box, x, y, width, height) {
  return x < box.x + box.width + 4 && box.x < x + width + 4 && y < box.y + box.height + 2 && box.y < y + height + 2;
}

function drawCompass(svg, camera, center, width) {
  const a = center.clone().project(camera);
  const b = center.clone().add(new THREE.Vector3(0, 0, -50)).project(camera);
  let northX = b.x - a.x, northY = -(b.y - a.y);
  const length = Math.hypot(northX, northY) || 1;
  northX /= length; northY /= length;
  const centerX = width - 30, centerY = 30, radius = 14;
  const group = svgElement("g", {});
  group.append(svgElement("circle", { cx: centerX, cy: centerY, r: radius + 4, fill: "#ffffff", stroke: "#d0d7de" }));
  group.append(svgElement("line", { x1: centerX - northX * radius, y1: centerY - northY * radius, x2: centerX + northX * radius, y2: centerY + northY * radius, stroke: INK.text, "stroke-width": 1.5 }));
  group.append(svgElement("circle", { cx: centerX + northX * radius, cy: centerY + northY * radius, r: 2.5, fill: INK.text }));
  group.append(text(centerX + northX * (radius + 13), centerY + northY * (radius + 13) + 4, "N", { anchor: "middle", weight: 700, fill: INK.text }));
  svg.append(group);
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
  const hemisphere = new THREE.HemisphereLight(0xffffff, 0x8d949e, 1.45);
  const sun = new THREE.DirectionalLight(0xffffff, 2.1);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.6;
  three.add(hemisphere, sun, sun.target);
  let model = buildModel(scene);
  three.add(model.root);
  const size = model.bounds.getSize(new THREE.Vector3());
  const center = model.bounds.getCenter(new THREE.Vector3());
  const radius = size.length();
  sun.position.copy(center).addScaledVector(new THREE.Vector3(-0.55, 1.1, 0.75).normalize(), radius * 1.5);
  sun.target.position.copy(center);
  Object.assign(sun.shadow.camera, { left: -radius, right: radius, top: radius, bottom: -radius, near: radius * 0.1, far: radius * 4 });
  sun.shadow.camera.updateProjectionMatrix();
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(radius * 6, radius * 6), new THREE.ShadowMaterial({ opacity: 0.16 }));
  ground.rotation.x = -Math.PI / 2;
  ground.position.set(center.x, model.bounds.min.y - 0.02, center.z);
  ground.receiveShadow = true;
  three.add(ground);

  const camera = new THREE.PerspectiveCamera(30, 1, 1, radius * 40);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = !matchMedia("(prefers-reduced-motion: reduce)").matches;
  const render = () => renderer.render(three, camera);
  controls.addEventListener("change", render);

  const look = (view) => {
    const width = element.clientWidth, height = element.clientHeight;
    camera.aspect = width / height;
    if (view === "perspective") {
      const perspective = perspectiveCamera(model.bounds, width, height);
      camera.position.copy(perspective.camera.position);
      controls.target.copy(perspective.target);
    } else {
      const layout = VIEWS[view];
      const fit = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov) / 2) * 0.55;
      camera.position.copy(center).addScaledVector(vector(layout.direction), fit);
      camera.up.copy(vector(layout.up));
      controls.target.copy(center);
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
  look("perspective");
  const loop = () => {
    if (controls.update()) render();
    requestAnimationFrame(loop);
  };
  loop();

  // Clip the model at a height, plate by plate, to look inside.
  const clip = (plates) => {
    const plane = new THREE.Plane(new THREE.Vector3(0, -1, 0), plates * PLATE * BASE_UNIT);
    model.root.traverse((object) => {
      if (object.material) object.material.clippingPlanes = [...model.planes, plane];
    });
    render();
  };
  return { look, clip, topPlates: scene.bounds[5] / PLATE };
}

// Headless pages call these through window.bricky.
export const api = { load, draw, ready: true };
