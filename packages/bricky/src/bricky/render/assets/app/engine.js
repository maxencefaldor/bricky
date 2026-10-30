// The engine renders a scene interactively: cameras and controls, light, framing and animated
// views, element states for selection, isolation and hiding, picking, clipping and screenshots.
//
// Element states live in a texture with one texel per element, read by every material's shader:
// red holds the visibility (0 shown, 1 ghosted, 2 hidden), green the accent (1 hovered, 2 selected)
// plus the diagnostics shown (4 an error, 8 a warning), and blue and alpha an element arriving in
// place: the axis it moves along, and how far it still has to go. Changing a state rewrites one
// texel, so restyling elements costs nothing per frame, however large the model.
//
// A diagnostic shows once every element it names is built: instructions reveal it at the step that
// places the last of them.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import { LineSegments2 } from "three/addons/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/addons/lines/LineSegmentsGeometry.js";
import { BASE_UNIT, CLIP_SLACK, PLATE, STUD, TINT, buildModel, clipPlane, orderInstances, pushEdges, pushMeshEdges, pushRim, toThree } from "bricky/viewer.js";

const COLUMNS = 1024; // texels per row of the element state texture
const VISIBLE = 0, GHOSTED = 1, HIDDEN = 2;
const HOVERED = 1, SELECTED = 2;
const SHOWS_ERROR = 4, SHOWS_WARNING = 8; // the diagnostics an element shows, added to its accent
const FIELD_OF_VIEW = 30; // degrees, vertically
const DURATION = 480; // milliseconds a view change takes
const FILL = 0.86; // the share of the free area a framed model fills
const LIFT_UNIT = 0.5; // millimeters per step of an arriving element's distance
const ARRIVAL = { distance: 32, duration: 420, stagger: 70 }; // millimeters and milliseconds

// Every named view: where the camera looks from, and in which projection.
export const VIEWS = {
  perspective: { label: "3D, south-east", azimuth: 35, elevation: 30, projection: "perspective" },
  "perspective-south-west": { label: "3D, south-west", azimuth: -35, elevation: 30, projection: "perspective" },
  "perspective-north-west": { label: "3D, north-west", azimuth: 215, elevation: 30, projection: "perspective" },
  "perspective-north-east": { label: "3D, north-east", azimuth: 145, elevation: 30, projection: "perspective" },
  front: { label: "Front", azimuth: 0, elevation: 0, projection: "orthographic" },
  back: { label: "Back", azimuth: 180, elevation: 0, projection: "orthographic" },
  left: { label: "Left", azimuth: -90, elevation: 0, projection: "orthographic" },
  right: { label: "Right", azimuth: 90, elevation: 0, projection: "orthographic" },
  top: { label: "Top", azimuth: 0, elevation: 90, projection: "orthographic" },
};

// The direction from the target to the camera, in three.js axes, for an azimuth and elevation in
// degrees. Azimuth 0 looks north from the south; 90 looks west from the east.
export function direction(azimuth, elevation) {
  const a = THREE.MathUtils.degToRad(azimuth);
  const e = THREE.MathUtils.degToRad(Math.min(elevation, 89.99));
  return new THREE.Vector3(Math.sin(a) * Math.cos(e), Math.sin(e), Math.cos(a) * Math.cos(e)).normalize();
}

const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const easeOut = (t) => 1 - Math.pow(1 - t, 3);

export function createEngine(stage, scene, { insets = () => ({ top: 0, right: 0, bottom: 0, left: 0 }) } = {}) {
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const listeners = new Map();
  const emit = (event, value) => (listeners.get(event) ?? []).forEach((listener) => listener(value));
  const count = scene.elements.length;

  // ------------------------------------------------------------------------------------------
  // Renderer, scene and light

  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.localClippingEnabled = true;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  // The sun and the model never move: shadows render again only when what casts them changes.
  renderer.shadowMap.autoUpdate = false;
  renderer.toneMapping = THREE.NeutralToneMapping;
  const canvas = renderer.domElement;
  canvas.addEventListener("webglcontextlost", (event) => {
    event.preventDefault();
    emit("lost");
  });
  canvas.tabIndex = 0;
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", "The model in 3D. Drag to orbit, scroll to zoom, right-drag to pan.");
  stage.prepend(canvas);

  const three = new THREE.Scene();
  const environment = new THREE.PMREMGenerator(renderer);
  three.environment = environment.fromScene(new RoomEnvironment(), 0.04).texture;
  three.environmentIntensity = 0.3;
  environment.dispose();
  const hemisphere = new THREE.HemisphereLight(0xffffff, 0x8d949e, 1.15);
  const sun = new THREE.DirectionalLight(0xffffff, 2.0);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.6;
  three.add(hemisphere, sun, sun.target);

  const model = buildModel(scene, { live: true });
  three.add(model.root);
  const bounds = model.bounds.clone();
  const center = bounds.getCenter(new THREE.Vector3());
  const radius = Math.max(bounds.getSize(new THREE.Vector3()).length() / 2, 1);
  // The sun stands high in the south-west, so shadows stay short from every side.
  sun.position.copy(center).addScaledVector(new THREE.Vector3(-0.5, 1.6, 0.6).normalize(), radius * 3);
  sun.target.position.copy(center);
  Object.assign(sun.shadow.camera, { left: -radius, right: radius, top: radius, bottom: -radius, near: radius * 0.5, far: radius * 6 });
  sun.shadow.camera.updateProjectionMatrix();
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(radius * 12, radius * 12), new THREE.ShadowMaterial({ opacity: 0.14 }));
  ground.rotation.x = -Math.PI / 2;
  ground.position.set(center.x, bounds.min.y - 0.02, center.z);
  ground.receiveShadow = true;
  three.add(ground);

  const canvasColor = () => getComputedStyle(stage).getPropertyValue("--canvas").trim() || "#f3f4f6";
  const applyTheme = () => {
    renderer.setClearColor(canvasColor(), 1);
    invalidate();
  };
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);

  // ------------------------------------------------------------------------------------------
  // Element states: a texture every material reads

  const rows = Math.max(1, Math.ceil(count / COLUMNS));
  const states = new Uint8Array(COLUMNS * rows * 4);
  const stateTexture = new THREE.DataTexture(states, COLUMNS, rows, THREE.RGBAFormat, THREE.UnsignedByteType);
  stateTexture.magFilter = stateTexture.minFilter = THREE.NearestFilter;
  stateTexture.needsUpdate = true;
  const accent = new THREE.Color();
  const uniforms = {
    elementStates: { value: stateTexture },
    accentColor: { value: accent },
    errorTint: { value: new THREE.Color(TINT.error.color) },
    warningTint: { value: new THREE.Color(TINT.warning.color) },
  };

  // Patch a material to read each element's state. A pass of "normal" discards ghosted and hidden
  // elements; "ghost" draws only ghosted ones; "pick" writes element indices instead of colors.
  // Surfaces in their elements' colors take the tint of the diagnostics they show, as images bake
  // it into those colors. An outline rendered for a kind of diagnostic shows while its element
  // shows one of that kind, and an element's own outline while it shows none.
  const patch = (material, pass, { outline } = {}) => {
    material.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, uniforms);
      shader.vertexShader = shader.vertexShader
        .replace("#include <common>", `#include <common>
attribute float element;
uniform highp sampler2D elementStates;
flat varying vec2 vElementState;
flat varying float vElement;`)
        .replace("#include <begin_vertex>", `#include <begin_vertex>
vElement = element;
vec4 elementTexel = floor(texelFetch(elementStates, ivec2(int(mod(element, ${COLUMNS}.0)), int(floor(element / ${COLUMNS}.0))), 0) * 255.0 + 0.5);
vElementState = elementTexel.rg;
if (elementTexel.b > 0.0) {
  // An arriving element sits back along its axis, by its remaining distance.
  float axis = elementTexel.b;
  vec3 along = axis == 1.0 ? vec3(1.0, 0.0, 0.0) : axis == 2.0 ? vec3(-1.0, 0.0, 0.0) : axis == 3.0 ? vec3(0.0, 0.0, -1.0)
    : axis == 4.0 ? vec3(0.0, 0.0, 1.0) : axis == 5.0 ? vec3(0.0, 1.0, 0.0) : vec3(0.0, -1.0, 0.0);
  vec3 shift = -along * elementTexel.a * ${LIFT_UNIT.toFixed(2)};
#ifdef USE_INSTANCING
  shift = transpose(mat3(instanceMatrix)) * shift;
#endif
  transformed += shift;
}`);
      const outlines = { own: " && !error && !warning", warning: " && warning && !error", error: " && error" };
      const keep = pass === "ghost" ? "vElementState.x == 1.0" : `vElementState.x == 0.0${outlines[outline] ?? ""}`;
      let fragment = shader.fragmentShader
        .replace("#include <common>", `#include <common>
uniform vec3 accentColor;
uniform vec3 errorTint;
uniform vec3 warningTint;
flat varying vec2 vElementState;
flat varying float vElement;`)
        .replace("void main() {", `void main() {
  float accented = mod(vElementState.y, 4.0);
  bool error = mod(floor(vElementState.y / 4.0), 2.0) == 1.0;
  bool warning = vElementState.y >= 8.0;
  if (!(${keep})) discard;`);
      // An override material still takes instance colors from instanced studs: the ghost pass
      // drops them, so every ghosted surface takes the ghost's one color.
      if (pass === "ghost") fragment = fragment.replace("#include <color_fragment>", "");
      // Vertex or instance colors, which three.js flags with USE_COLOR, hold elements' own colors.
      if (pass === "normal") {
        fragment = fragment.replace("#include <color_fragment>", `#include <color_fragment>
#ifdef USE_COLOR
  if (error) diffuseColor.rgb = mix(diffuseColor.rgb, diffuse * errorTint, ${TINT.error.share.toFixed(2)});
  else if (warning) diffuseColor.rgb = mix(diffuseColor.rgb, diffuse * warningTint, ${TINT.warning.share.toFixed(2)});
#endif
  if (accented == 2.0) diffuseColor.rgb = mix(diffuseColor.rgb, accentColor, 0.18);
  else if (accented == 1.0) diffuseColor.rgb = mix(diffuseColor.rgb, accentColor, 0.1);`);
      }
      if (pass === "pick") {
        fragment = fragment.replace("#include <dithering_fragment>", `#include <dithering_fragment>
  float id = vElement + 1.0;
  gl_FragColor = vec4(floor(id / 65536.0), mod(floor(id / 256.0), 256.0), mod(id, 256.0), 255.0) / 255.0;`);
      }
      shader.fragmentShader = fragment;
    };
    material.customProgramCacheKey = () => `bricky-${pass}-${outline}`;
    return material;
  };

  for (const set of Object.values(model.materials)) for (const material of Object.values(set)) patch(material, "normal");
  for (const segments of model.meshes.edges) patch(segments.material, "normal", { outline: segments.userData.kind ?? "own" });
  // Clipping opens the model: the inner sides of opaque parts render flat, in a darker shade of
  // their color, so a clipped part reads as solid.
  for (const [kind, mesh] of Object.entries(model.meshes.insides)) {
    const inside = new THREE.MeshBasicMaterial({ vertexColors: true, color: kind === "pearl" ? 0xc4c4c4 : 0xb4b4b4, side: THREE.BackSide, clippingPlanes: model.planes });
    inside.polygonOffset = true;
    inside.polygonOffsetFactor = inside.polygonOffsetUnits = 4;
    mesh.material = patch(inside, "normal");
  }
  // Outlines of diagnosed elements respect depth here: the checks panel finds hidden ones.
  model.edgeMaterials.error.depthTest = model.edgeMaterials.warning.depthTest = true;

  // Hidden and ghosted elements cast no shadow.
  const depthMaterial = () => {
    const material = patch(new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking }), "normal");
    material.clone = depthMaterial;
    return material;
  };
  for (const mesh of [...Object.values(model.meshes.bodies), ...Object.values(model.meshes.studs)]) mesh.customDepthMaterial = depthMaterial();

  // Ghosted elements render as one translucent shell: a depth pass keeps only the nearest of their
  // surfaces, then a color pass tints exactly those, so no surface stacks over another.
  const ghostDepth = patch(new THREE.MeshBasicMaterial({ colorWrite: false }), "ghost");
  const ghostMaterial = patch(new THREE.MeshLambertMaterial({ color: 0xaab2bd, transparent: true, opacity: 0.22, depthWrite: false, depthFunc: THREE.EqualDepth }), "ghost");
  const pickMaterial = patch(new THREE.MeshBasicMaterial({ side: THREE.DoubleSide, toneMapped: false, blending: THREE.NoBlending }), "pick");
  const pickTarget = new THREE.WebGLRenderTarget(1, 1);
  const pickPixel = new Uint8Array(4);

  const visibility = new Uint8Array(count); // what the reader hides or isolates
  const beyond = new Uint8Array(count); // past the build's progress, so hidden whatever the reader does
  const accented = new Uint8Array(count); // 1 hovered, 2 selected
  const diagnosed = new Uint8Array(count); // the kinds of diagnostic each element shows
  const shown = (i) => (beyond[i] ? HIDDEN : visibility[i]);
  const writeState = (i) => {
    states[i * 4] = shown(i);
    states[i * 4 + 1] = accented[i] | diagnosed[i];
  };
  // Show each diagnostic whose elements are all built: on its elements, and as its region's box.
  let showing = [];
  const showDiagnostics = () => {
    diagnosed.fill(0);
    showing = scene.diagnostics.map(({ kind, elements }) => {
      if (elements.some((i) => beyond[i])) return false;
      for (const i of elements) diagnosed[i] |= kind === "error" ? SHOWS_ERROR : SHOWS_WARNING;
      return true;
    });
    for (const box of model.meshes.marks) box.visible = showing[box.userData.diagnostic];
  };
  showDiagnostics();
  for (let i = 0; i < count; i++) writeState(i);
  const commitStates = () => {
    stateTexture.needsUpdate = true;
    invalidate();
  };
  const refreshShadows = () => {
    renderer.shadowMap.needsUpdate = true;
    invalidate();
  };

  // ------------------------------------------------------------------------------------------
  // Cameras, controls and framing

  const perspective = new THREE.PerspectiveCamera(FIELD_OF_VIEW, 1, radius * 0.002, radius * 200);
  const orthographic = new THREE.OrthographicCamera(-1, 1, 1, -1, -radius * 100, radius * 100);
  let camera = perspective;
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = !reducedMotion.matches;
  controls.dampingFactor = 0.12;
  controls.zoomToCursor = true;
  controls.screenSpacePanning = true;
  controls.rotateSpeed = 0.9;
  controls.minDistance = radius * 0.02;
  controls.maxDistance = radius * 40;
  // The orthographic frustum spans the model's radius at zoom 1, so these limits mean the same
  // for every model: from 20 times the model's size down to a 200th of it.
  controls.minZoom = 0.05;
  controls.maxZoom = 200;
  controls.target.copy(center);

  let view = "perspective";
  let preferred = null; // the projection the reader chose, which every view then keeps
  let tween = null;
  let needsRender = true;
  let sorted = false;
  let moved = 0;
  let restTimer = 0;
  const invalidate = () => {
    needsRender = true;
  };
  // Studs render nearest first, which spares the depth test work; sorting them waits until the
  // camera rests, so a drag never pays for it.
  const cameraMoved = () => {
    sorted = false;
    moved = performance.now();
    clearTimeout(restTimer);
    restTimer = setTimeout(invalidate, 200);
    invalidate();
  };

  let stageSize = { width: 1, height: 1 };
  const size = () => stageSize;
  // The orthographic camera shows radius / zoom above and below its center: zoom 1 frames the
  // whole model, whatever its size, which keeps OrbitControls' zoom limits meaningful.
  const updateOrthographic = (halfHeight) => {
    const { width, height } = size();
    const aspect = width / height;
    Object.assign(orthographic, { left: -aspect * radius, right: aspect * radius, top: radius, bottom: -radius });
    if (halfHeight !== undefined) orthographic.zoom = radius / halfHeight;
    orthographic.updateProjectionMatrix();
  };
  const orthographicHalfHeight = () => radius / orthographic.zoom;
  const halfHeightAt = (distance) => distance * Math.tan(THREE.MathUtils.degToRad(FIELD_OF_VIEW / 2));

  // Find the target and distance that frame a box from a direction in the free part of the stage:
  // what the toolbars leave. The box's projection is centered there and fills FILL of it.
  const frame = (box, along, projection) => {
    const { width, height } = size();
    const free = insets();
    const freeWidth = Math.max(width - free.left - free.right, width * 0.4);
    const freeHeight = Math.max(height - free.top - free.bottom, height * 0.4);
    // The free area's center, in pixels from the stage's center.
    const offsetX = (free.left - free.right) / 2, offsetY = (free.bottom - free.top) / 2;
    const corners = [];
    for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) corners.push(new THREE.Vector3(x, y, z));
    const target = box.getCenter(new THREE.Vector3());
    const probe = new THREE.PerspectiveCamera(FIELD_OF_VIEW, width / height, 0.01, 1e9);
    const right = new THREE.Vector3(), up = new THREE.Vector3();
    if (projection === "orthographic") {
      probe.position.copy(target).addScaledVector(along, radius * 4);
      probe.lookAt(target);
      probe.updateMatrixWorld();
      right.setFromMatrixColumn(probe.matrixWorld, 0);
      up.setFromMatrixColumn(probe.matrixWorld, 1);
      const us = corners.map((corner) => corner.clone().sub(target).dot(right));
      const vs = corners.map((corner) => corner.clone().sub(target).dot(up));
      const [u0, u1, v0, v1] = [Math.min(...us), Math.max(...us), Math.min(...vs), Math.max(...vs)];
      const scale = Math.max((u1 - u0) / (freeWidth * FILL), (v1 - v0) / (freeHeight * FILL)); // world per pixel
      const halfHeight = Math.max((scale * height) / 2, 1e-3);
      target.addScaledVector(right, (u0 + u1) / 2 - offsetX * scale).addScaledVector(up, (v0 + v1) / 2 - offsetY * scale);
      return { target, distance: radius * 4, halfHeight };
    }
    let distance = radius * 3;
    for (let i = 0; i < 12; i++) {
      probe.position.copy(target).addScaledVector(along, distance);
      probe.lookAt(target);
      probe.updateMatrixWorld();
      probe.updateProjectionMatrix();
      let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
      for (const corner of corners) {
        const point = corner.clone().project(probe);
        x0 = Math.min(x0, point.x); x1 = Math.max(x1, point.x); y0 = Math.min(y0, point.y); y1 = Math.max(y1, point.y);
      }
      const half = halfHeightAt(distance);
      right.setFromMatrixColumn(probe.matrixWorld, 0);
      up.setFromMatrixColumn(probe.matrixWorld, 1);
      // Pixels per normalized unit: width / 2 across, height / 2 up.
      const centerX = ((x0 + x1) / 2) * (width / 2) - offsetX, centerY = ((y0 + y1) / 2) * (height / 2) - offsetY;
      const pixelsToWorld = (2 * half) / height;
      target.addScaledVector(right, centerX * pixelsToWorld).addScaledVector(up, centerY * pixelsToWorld);
      const extent = Math.max(((x1 - x0) * width) / 2 / (freeWidth * FILL), ((y1 - y0) * height) / 2 / (freeHeight * FILL));
      distance *= 0.35 + 0.65 * extent;
    }
    return { target, distance, halfHeight: halfHeightAt(distance) };
  };

  const currentDistance = () => camera.position.distanceTo(controls.target);
  const currentDirection = () => camera.position.clone().sub(controls.target).normalize();

  // Put the camera at a target, a direction and a framing, in a projection.
  const place = (projection, target, along, distance, halfHeight) => {
    if ((projection === "orthographic") !== (camera === orthographic)) {
      camera = projection === "orthographic" ? orthographic : perspective;
      controls.object = camera;
      ground.visible = projection === "perspective";
      emit("projection", projection);
    }
    controls.target.copy(target);
    camera.position.copy(target).addScaledVector(along, distance);
    camera.up.set(0, 1, 0);
    camera.lookAt(target);
    if (camera === orthographic) updateOrthographic(halfHeight);
    else camera.updateProjectionMatrix();
    controls.update();
    cameraMoved();
  };

  // Drop what remains of a drag's momentum, so it cannot carry the camera past a new view.
  const stopMomentum = () => {
    controls.enableDamping = false;
    controls.update();
    controls.enableDamping = !reducedMotion.matches;
  };

  // Move the camera to a framing, animated unless the reader asked for reduced motion.
  const travel = (projection, framing, along, { animate = true } = {}) => {
    stopMomentum();
    const from = {
      target: controls.target.clone(),
      along: currentDirection(),
      distance: currentDistance(),
      halfHeight: camera === orthographic ? orthographicHalfHeight() : halfHeightAt(currentDistance()),
    };
    if (!animate || reducedMotion.matches) {
      tween = null;
      place(projection, framing.target, along, framing.distance, framing.halfHeight);
      return;
    }
    // Switch to the target's projection first, keeping the picture the same size.
    const distance = projection === "perspective" ? from.halfHeight / Math.tan(THREE.MathUtils.degToRad(FIELD_OF_VIEW / 2)) : from.distance;
    place(projection, from.target, from.along, projection === "perspective" ? distance : radius * 4, from.halfHeight);
    tween = { start: performance.now(), projection, from: { ...from, distance: currentDistance() }, to: { ...framing, along } };
  };

  const step = (time) => {
    if (!tween) return;
    const t = Math.min(1, (time - tween.start) / DURATION);
    const k = easeInOut(t);
    const { from, to, projection } = tween;
    const target = from.target.clone().lerp(to.target, k);
    const rotation = new THREE.Quaternion().setFromUnitVectors(from.along, to.along);
    const along = from.along.clone().applyQuaternion(new THREE.Quaternion().slerp(rotation, k));
    if (from.along.dot(to.along) < -0.999) along.copy(from.along).lerp(to.along, k).add(new THREE.Vector3(0, Math.sin(Math.PI * k), 0)).normalize();
    const distance = THREE.MathUtils.lerp(from.distance, to.distance, k);
    const halfHeight = THREE.MathUtils.lerp(from.halfHeight, to.halfHeight, k);
    place(projection, target, along, distance, halfHeight);
    if (t === 1) {
      tween = null;
      emit("camera");
    }
  };

  const visibleBox = () => {
    const box = new THREE.Box3();
    const isolated = isolation !== null;
    for (let i = 0; i < count; i++) {
      if (shown(i) === HIDDEN || (isolated && shown(i) === GHOSTED)) continue;
      box.union(model.elementBounds[i]);
    }
    if (box.isEmpty()) box.copy(bounds);
    box.intersect(clipBox());
    return box.isEmpty() ? bounds.clone() : box;
  };

  const look = (name, options = {}) => {
    const named = VIEWS[name];
    if (!named) return;
    const along = direction(named.azimuth, named.elevation);
    const projection = preferred ?? named.projection;
    travel(projection, frame(visibleBox(), along, projection), along, options);
    setView(name);
  };

  const setView = (name) => {
    if (view === name) return;
    view = name;
    emit("view", name);
  };

  const fit = (options = {}) => {
    const along = currentDirection();
    const projection = camera === orthographic ? "orthographic" : "perspective";
    travel(projection, frame(visibleBox(), along, projection), along, options);
  };

  // Frame a box from a direction, the camera's own by default.
  const frameBox = (box, { along = currentDirection(), ...options } = {}) => {
    const projection = camera === orthographic ? "orthographic" : "perspective";
    travel(projection, frame(box, along, projection), along, options);
    setView(null);
  };

  const focus = (elements, options = {}) => {
    const box = new THREE.Box3();
    for (const i of elements) box.union(model.elementBounds[i]);
    if (box.isEmpty()) return;
    // Frame a single small part with room around it, so it reads in its surroundings.
    const grown = box.clone().expandByScalar(Math.max(STUD * BASE_UNIT * 2, box.getSize(new THREE.Vector3()).length() * 0.35));
    const along = currentDirection();
    const projection = camera === orthographic ? "orthographic" : "perspective";
    travel(projection, frame(grown, along, projection), along, options);
    setView(null);
  };

  // Switch projection, and keep the choice for every view after. On a named view the model is
  // framed again, since perspective enlarges what is near; after the reader's own zoom, the
  // picture keeps its scale at the target.
  const setProjection = (projection) => {
    preferred = projection;
    if ((projection === "orthographic") === (camera === orthographic)) return;
    if (view !== null) return look(view);
    tween = null;
    stopMomentum();
    const along = currentDirection();
    const halfHeight = camera === orthographic ? orthographicHalfHeight() : halfHeightAt(currentDistance());
    const distance = projection === "perspective" ? halfHeight / Math.tan(THREE.MathUtils.degToRad(FIELD_OF_VIEW / 2)) : radius * 4;
    place(projection, controls.target.clone(), along, distance, halfHeight);
  };

  // Orbit by angles in degrees, and zoom by a factor, from the keyboard.
  const orbit = (azimuth, elevation) => {
    const offset = camera.position.clone().sub(controls.target);
    const spherical = new THREE.Spherical().setFromVector3(offset);
    spherical.theta += THREE.MathUtils.degToRad(azimuth);
    spherical.phi = THREE.MathUtils.clamp(spherical.phi - THREE.MathUtils.degToRad(elevation), 0.001, Math.PI - 0.001);
    camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(spherical));
    camera.lookAt(controls.target);
    controls.update();
    setView(null);
    hover(null);
    cameraMoved();
  };
  const zoom = (factor) => {
    if (camera === orthographic) {
      orthographic.zoom = THREE.MathUtils.clamp(orthographic.zoom * factor, controls.minZoom, controls.maxZoom);
      orthographic.updateProjectionMatrix();
    } else {
      const offset = camera.position.clone().sub(controls.target).divideScalar(factor);
      const length = THREE.MathUtils.clamp(offset.length(), controls.minDistance, controls.maxDistance);
      camera.position.copy(controls.target).add(offset.setLength(length));
    }
    controls.update();
    cameraMoved();
  };

  controls.addEventListener("start", () => {
    tween = null;
    setView(null);
    hover(null);
    emit("interact");
  });
  controls.addEventListener("change", () => {
    cameraMoved();
    emit("camera");
  });

  // ------------------------------------------------------------------------------------------
  // Clipping: a section box, inside the clips the scene came with

  const full = { x: [scene.bounds[0], scene.bounds[3]], y: [scene.bounds[1], scene.bounds[4]], z: [scene.bounds[2], scene.bounds[5]] };
  let section = structuredClone(full);
  const planes = model.planes; // shared by every material, so changing it in place reaches them all
  const fixedPlanes = planes.slice();
  pickMaterial.clippingPlanes = ghostMaterial.clippingPlanes = ghostDepth.clippingPlanes = planes;
  const clipBox = () => new THREE.Box3(toThree(section.x[0], section.y[1], section.z[0]), toThree(section.x[1], section.y[0], section.z[1]));
  // The inner sides of parts only show where a clip opens the model, so they render only then.
  const showInsides = () => {
    const open = planes.length > 0;
    for (const mesh of Object.values(model.meshes.insides)) mesh.visible = open;
  };
  const setSection = (next) => {
    section = { ...section, ...next };
    planes.length = 0;
    planes.push(...fixedPlanes);
    for (const axis of ["x", "y", "z"]) {
      const [low, high] = section[axis];
      if (low > full[axis][0]) planes.push(clipPlane({ axis, keep: "above", value: low }));
      if (high < full[axis][1]) planes.push(clipPlane({ axis, keep: "below", value: high }));
    }
    showInsides();
    refreshShadows();
    emit("section", section);
  };

  // ------------------------------------------------------------------------------------------
  // Selection, isolation and hiding

  let hovered = null;
  let selection = new Set();
  let emphasis = new Set();
  let isolation = null;

  const hover = (index) => {
    if (index === hovered) return;
    if (hovered !== null && !selection.has(hovered)) { accented[hovered] = 0; writeState(hovered); }
    hovered = index;
    if (index !== null && !selection.has(index)) { accented[index] = HOVERED; writeState(index); }
    commitStates();
    emit("hover", index);
  };

  const select = (indices) => {
    for (const i of selection) { accented[i] = i === hovered ? HOVERED : 0; writeState(i); }
    selection = new Set(indices ?? []);
    for (const i of selection) { accented[i] = SELECTED; writeState(i); }
    commitStates();
    updateOutline();
    emit("selection", selection);
  };

  const refreshVisibility = () => {
    for (let i = 0; i < count; i++) writeState(i);
    commitStates();
    refreshShadows();
    updateOutline();
    emit("visibility");
  };
  const isolate = (indices) => {
    isolation = indices === null ? null : new Set(indices);
    for (let i = 0; i < count; i++) {
      if (visibility[i] === HIDDEN) continue;
      visibility[i] = isolation === null || isolation.has(i) ? VISIBLE : GHOSTED;
    }
    refreshVisibility();
  };
  const hide = (indices) => {
    for (const i of indices) visibility[i] = HIDDEN;
    refreshVisibility();
  };
  const showAll = () => {
    isolation = null;
    visibility.fill(VISIBLE);
    refreshVisibility();
  };
  // Show only the elements built so far, or every element again with null. The reader's own
  // hiding and isolating apply within what is built.
  const limit = (indices) => {
    beyond.fill(indices === null ? 0 : 1);
    if (indices !== null) for (const i of indices) beyond[i] = 0;
    showDiagnostics();
    refreshVisibility();
  };
  // Outline elements in the accent color, keeping their own colors, such as the ones a step adds.
  const emphasize = (indices) => {
    emphasis = new Set(indices ?? []);
    updateOutline();
  };

  // ------------------------------------------------------------------------------------------
  // Arrivals: elements moving into place, one after another

  let arrivals = [];
  const settle = (item) => {
    states[item.element * 4 + 2] = 0;
    states[item.element * 4 + 3] = 0;
  };
  // Move elements in along their axes: codes 0 to 5 for +x, -x, +y, -y, +z and -z.
  const arrive = (elements, axes) => {
    arrivals.forEach(settle);
    arrivals = [];
    if (!reducedMotion.matches) {
      const start = performance.now();
      const stagger = Math.min(ARRIVAL.stagger, 360 / Math.max(1, elements.length));
      arrivals = elements.map((element, k) => ({ element, axis: axes[k] + 1, start: start + k * stagger }));
      advance(start);
    }
    commitStates();
    refreshShadows();
  };
  const advance = (time) => {
    if (!arrivals.length) return;
    let moving = false;
    for (const item of arrivals) {
      const t = Math.min(1, Math.max(0, (time - item.start) / ARRIVAL.duration));
      const left = (1 - easeOut(t)) * ARRIVAL.distance;
      if (t < 1) moving = true;
      states[item.element * 4 + 2] = t < 1 ? item.axis : 0;
      states[item.element * 4 + 3] = Math.round(left / LIFT_UNIT);
    }
    stateTexture.needsUpdate = true;
    invalidate();
    if (!moving) {
      arrivals.forEach(settle);
      arrivals = [];
      refreshShadows();
    }
  };

  // The outline of the selection: bold where it shows, faint where other parts hide it.
  const outlineMaterials = [
    new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.95, clippingPlanes: planes }),
    new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.28, depthTest: false, clippingPlanes: planes }),
  ];
  // Emphasized elements get wide lines, which read at a glance over the model's own edges.
  const emphasisMaterial = new LineMaterial({ color: 0xffffff, linewidth: 2.5, clippingPlanes: planes });
  const outline = new THREE.Group();
  outline.renderOrder = 8;
  three.add(outline);
  // The selection shows its outline faintly through what hides it, so a hidden selection can be
  // found; emphasized elements, such as a step's, outline only where they show.
  const updateOutline = () => {
    const geometries = new Set(outline.children.map((lines) => lines.geometry));
    geometries.forEach((geometry) => geometry.dispose());
    outline.clear();
    const showing = (indices) => new Set([...indices].filter((i) => shown(i) !== HIDDEN));
    const chosen = showing(selection);
    const emphasized = showing([...emphasis].filter((i) => !selection.has(i)));
    const edges = (set, { rims }) => {
      const points = [];
      for (const box of scene.boxes) if (set.has(box[6])) pushEdges(points, box);
      for (const mesh of scene.meshes) if (set.has(mesh.element)) pushMeshEdges(points, mesh);
      // Stud rims would crowd a large plate a step adds, so only the selection gets them.
      if (rims) for (const stud of scene.studs) if (set.has(stud[4])) pushRim(points, stud);
      return points;
    };
    if (chosen.size) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.Float32BufferAttribute(edges(chosen, { rims: true }), 3));
      outlineMaterials.forEach((material, i) => {
        const lines = new THREE.LineSegments(geometry, material);
        lines.renderOrder = 8 + i;
        outline.add(lines);
      });
    }
    if (emphasized.size) {
      const lines = new LineSegments2(new LineSegmentsGeometry().setPositions(edges(emphasized, { rims: false })), emphasisMaterial);
      lines.renderOrder = 8;
      outline.add(lines);
    }
    invalidate();
  };

  // ------------------------------------------------------------------------------------------
  // Picking: render element indices under one pixel

  const decorations = () => [ground, outline, ...model.meshes.edges, ...model.root.children.filter((child) => child.isLineSegments)];
  const pick = (clientX, clientY) => {
    const box = canvas.getBoundingClientRect();
    const x = clientX - box.left, y = clientY - box.top;
    if (x < 0 || y < 0 || x >= box.width || y >= box.height) return null;
    const hidden = decorations().filter((object) => object.visible);
    hidden.forEach((object) => (object.visible = false));
    camera.setViewOffset(box.width, box.height, x, y, 1, 1);
    three.overrideMaterial = pickMaterial;
    const shadows = renderer.shadowMap.needsUpdate;
    renderer.shadowMap.needsUpdate = false;
    renderer.setRenderTarget(pickTarget);
    renderer.setClearColor(0x000000, 0);
    renderer.clear();
    renderer.render(three, camera);
    renderer.readRenderTargetPixels(pickTarget, 0, 0, 1, 1, pickPixel);
    renderer.setRenderTarget(null);
    renderer.setClearColor(canvasColor(), 1);
    renderer.shadowMap.needsUpdate = shadows;
    three.overrideMaterial = null;
    camera.clearViewOffset();
    hidden.forEach((object) => (object.visible = true));
    const id = pickPixel[0] * 65536 + pickPixel[1] * 256 + pickPixel[2];
    return id === 0 ? null : id - 1;
  };

  // How many pixels of some elements show from each of several directions, each framing a box:
  // the elements can hide behind others, which count against them.
  const coverageTarget = new THREE.WebGLRenderTarget(1, 1);
  const coverage = (elements, box, directions) => {
    const wanted = new Set(elements);
    const { width, height } = size();
    const across = 160, down = Math.max(16, Math.round((across * height) / width));
    coverageTarget.setSize(across, down);
    const pixels = new Uint8Array(across * down * 4);
    const probe = new THREE.PerspectiveCamera(FIELD_OF_VIEW, width / height, perspective.near, perspective.far);
    const hidden = decorations().filter((object) => object.visible);
    hidden.forEach((object) => (object.visible = false));
    const shadows = renderer.shadowMap.needsUpdate;
    renderer.shadowMap.needsUpdate = false;
    three.overrideMaterial = pickMaterial;
    renderer.setRenderTarget(coverageTarget);
    renderer.setClearColor(0x000000, 0);
    const counts = directions.map((along) => {
      const framing = frame(box, along, "perspective");
      probe.position.copy(framing.target).addScaledVector(along, framing.distance);
      probe.up.set(0, 1, 0);
      probe.lookAt(framing.target);
      probe.updateMatrixWorld();
      renderer.clear();
      renderer.render(three, probe);
      renderer.readRenderTargetPixels(coverageTarget, 0, 0, across, down, pixels);
      let total = 0;
      for (let k = 0; k < pixels.length; k += 4) {
        const id = pixels[k] * 65536 + pixels[k + 1] * 256 + pixels[k + 2];
        if (id && wanted.has(id - 1)) total += 1;
      }
      return total;
    });
    renderer.setRenderTarget(null);
    renderer.setClearColor(canvasColor(), 1);
    three.overrideMaterial = null;
    renderer.shadowMap.needsUpdate = shadows;
    hidden.forEach((object) => (object.visible = true));
    return counts;
  };

  // ------------------------------------------------------------------------------------------
  // Portraits: one element alone, as a small picture, such as for a step's list of parts

  let portraits = null;
  const plainElements = scene.elements.map(([color, , part, line]) => [color, 0, part, line]);
  const portrait = (element, pixels = 96) => {
    if (!portraits) {
      const painter = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
      painter.toneMapping = THREE.NeutralToneMapping;
      const stage = new THREE.Scene();
      const light = new THREE.PMREMGenerator(painter);
      stage.environment = light.fromScene(new RoomEnvironment(), 0.04).texture;
      stage.environmentIntensity = 0.3;
      light.dispose();
      const key = new THREE.DirectionalLight(0xffffff, 2.0);
      key.position.set(-0.5, 1.6, 0.6);
      stage.add(new THREE.HemisphereLight(0xffffff, 0x8d949e, 1.15), key);
      portraits = { painter, stage, cache: new Map() };
    }
    if (portraits.cache.has(element)) return portraits.cache.get(element);
    const { painter, stage } = portraits;
    const alone = {
      ...scene,
      elements: plainElements,
      boxes: scene.boxes.filter((box) => box[6] === element).map((box) => [...box.slice(0, 7), 63]),
      meshes: scene.meshes.filter((mesh) => mesh.element === element),
      studs: scene.studs.filter((stud) => stud[4] === element),
      marks: [],
      clips: [],
    };
    const built = buildModel(alone);
    const box = built.elementBounds[element].clone().expandByScalar(1.2);
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const camera = new THREE.PerspectiveCamera(20, 1, 0.1, sphere.radius * 20);
    const distance = sphere.radius / Math.sin(THREE.MathUtils.degToRad(10)) * 1.02;
    camera.position.copy(sphere.center).addScaledVector(direction(35, 30), distance);
    camera.lookAt(sphere.center);
    stage.add(built.root);
    painter.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    painter.setSize(pixels, pixels, false);
    painter.setClearColor(0x000000, 0);
    painter.render(stage, camera);
    const url = painter.domElement.toDataURL("image/png");
    stage.remove(built.root);
    built.root.traverse((object) => {
      object.geometry?.dispose();
      for (const material of [object.material].flat()) material?.dispose();
    });
    portraits.cache.set(element, url);
    return url;
  };

  // ------------------------------------------------------------------------------------------
  // Drawing

  const draw = () => {
    if (!sorted && !tween && performance.now() - moved >= 180) {
      orderInstances(model.studMeshes, camera);
      sorted = true;
    }
    renderer.render(three, camera);
    if (isolation !== null) {
      // Ghosted elements, faintly over the rest, where the rest leaves room.
      const hidden = [...decorations(), ...Object.values(model.meshes.insides)].filter((object) => object.visible);
      hidden.forEach((object) => (object.visible = false));
      renderer.autoClear = false;
      three.overrideMaterial = ghostDepth;
      renderer.render(three, camera);
      three.overrideMaterial = ghostMaterial;
      renderer.render(three, camera);
      renderer.autoClear = true;
      three.overrideMaterial = null;
      hidden.forEach((object) => (object.visible = true));
    }
  };

  const resize = () => {
    stageSize = { width: Math.max(1, stage.clientWidth), height: Math.max(1, stage.clientHeight) };
    const { width, height } = stageSize;
    renderer.setSize(width, height, false);
    perspective.aspect = width / height;
    perspective.updateProjectionMatrix();
    emphasisMaterial.resolution.set(width, height);
    updateOrthographic();
    // Resizing clears the canvas: draw now, before the browser shows it empty.
    if (running) draw();
    emit("camera");
    emit("render");
  };
  new ResizeObserver(resize).observe(stage);

  let running = false;
  let frames = 0;
  const loop = (time) => {
    if (!running) return;
    requestAnimationFrame(loop);
    step(time);
    advance(time);
    if (!tween && controls.update()) invalidate();
    if (!needsRender) return;
    needsRender = false;
    frames += 1;
    draw();
    emit("render");
  };

  // Twice the screen's resolution, within 4,096 pixels a side and 16 megapixels in all.
  const screenshot = async () => {
    const { width, height } = size();
    const ratio = renderer.getPixelRatio();
    const scale = Math.min(2 * Math.max(ratio, 1), 4096 / Math.max(width, height), Math.sqrt(16e6 / (width * height)));
    renderer.setPixelRatio(scale);
    renderer.setSize(width, height, false);
    draw();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    renderer.setPixelRatio(ratio);
    renderer.setSize(width, height, false);
    invalidate();
    return blob;
  };

  // Where a point in model space lands on the stage, in pixels, and whether it is in front.
  const project = (point) => {
    const { width, height } = size();
    const projected = point.clone().project(camera);
    return { x: ((projected.x + 1) / 2) * width, y: ((1 - projected.y) / 2) * height, front: projected.z < 1 && projected.z > -1 };
  };
  const inSection = (point) => {
    const values = { x: point.x / BASE_UNIT, y: -point.z / BASE_UNIT, z: point.y / BASE_UNIT };
    return ["x", "y", "z"].every((axis) => values[axis] >= section[axis][0] - CLIP_SLACK && values[axis] <= section[axis][1] + CLIP_SLACK);
  };

  // Azimuth of the camera in degrees: 0 from the south, 90 from the east.
  const azimuth = () => {
    const along = currentDirection();
    return THREE.MathUtils.radToDeg(Math.atan2(along.x, along.z));
  };

  const engine = {
    scene,
    canvas,
    count,
    full,
    units: { stud: STUD, plate: PLATE },
    get view() { return view; },
    get projection() { return camera === orthographic ? "orthographic" : "perspective"; },
    get selection() { return selection; },
    get hovered() { return hovered; },
    get isolation() { return isolation; },
    get section() { return section; },
    get frames() { return frames; },
    get direction() { return currentDirection(); },
    // Whether the camera or an element is still moving, for a screenshot to wait out.
    get moving() { return tween !== null || arrivals.length > 0; },
    along: direction,
    isHidden: (i) => shown(i) === HIDDEN,
    // Whether the model shows a diagnostic, by its index in the scene's diagnostics.
    showsDiagnostic: (k) => showing[k],
    // The elements the reader hid, leaving out those past the build's progress.
    hiddenCount: () => visibility.reduce((total, value, i) => total + (value === HIDDEN && !beyond[i] ? 1 : 0), 0),
    elementBox: (i) => model.elementBounds[i].clone(),
    start() {
      running = true;
      applyTheme();
      showInsides();
      // The first frame renders the shadows too: until they exist, no material may sample them.
      refreshShadows();
      resize();
      look("perspective", { animate: false });
      requestAnimationFrame(loop);
    },
    stop() { running = false; },
    look, fit, focus, frameBox, setProjection, orbit, zoom, setSection,
    hover, select, isolate, hide, showAll, limit, emphasize, arrive, coverage, portrait, pick, project, inSection, azimuth, screenshot, invalidate,
    setAccentColor(color) {
      accent.set(color);
      for (const material of [...outlineMaterials, emphasisMaterial]) material.color.set(color);
      invalidate();
    },
    on(event, listener) {
      listeners.set(event, [...(listeners.get(event) ?? []), listener]);
    },
  };
  return engine;
}
