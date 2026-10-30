// The standalone viewer: the shell, the engine, and the components the page lists.
//
// A component is a function that receives the viewer and adds itself through the shell: a title, a
// view bar, a panel. The page lists the components to load, so removing one is removing its name
// there and its file in `components/`. The core keeps what no component may drop: the credits the
// part shapes require, and orbiting from the keyboard.

import { createEngine } from "bricky/app/engine.js";
import { createShell, h } from "bricky/app/shell.js";

const numbers = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

export const format = {
  number: (value) => numbers.format(value),
  count: (value, noun, plural = `${noun}s`) => `${numbers.format(value)} ${value === 1 ? noun : plural}`,
};

export async function start(root, scene, { heading, downloads = [], components = [], mode = "explore" }) {
  const shell = createShell(root, { heading });
  const engine = createEngine(shell.stage, scene, { insets: shell.insets });
  const viewer = { scene, heading, downloads, mode, engine, shell, h, format };

  if (scene.credits.length) shell.regions.bottomLeft.append(h("p", { class: "credit" }, scene.credits.join("; ")));

  // Orbit and zoom from the keyboard, unless the focus is in a field, a list or a menu.
  const free = () => !document.activeElement?.closest("input, textarea, select, .panel, .menu, dialog");
  const orbit = (azimuth, elevation) => () => free() && engine.orbit(azimuth, elevation);
  shell.shortcuts.add({ key: "ArrowLeft", label: "Orbit left", group: "Navigate", run: orbit(-15, 0) });
  shell.shortcuts.add({ key: "ArrowRight", label: "Orbit right", group: "Navigate", run: orbit(15, 0) });
  shell.shortcuts.add({ key: "ArrowUp", label: "Orbit up", group: "Navigate", run: orbit(0, 10) });
  shell.shortcuts.add({ key: "ArrowDown", label: "Orbit down", group: "Navigate", run: orbit(0, -10) });
  shell.shortcuts.add({ key: "=", label: "Zoom in", group: "Navigate", run: () => engine.zoom(1.25) });
  shell.shortcuts.add({ key: "+", label: "Zoom in", group: "Navigate", run: () => engine.zoom(1.25) });
  shell.shortcuts.add({ key: "-", label: "Zoom out", group: "Navigate", run: () => engine.zoom(0.8) });

  for (const component of components) component(viewer);

  engine.setAccentColor(getComputedStyle(root).getPropertyValue("--accent").trim() || "#0969da");
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    engine.setAccentColor(getComputedStyle(root).getPropertyValue("--accent").trim());
  });
  // The browser can take the graphics context back, on a phone short of memory for instance.
  engine.on("lost", () => {
    root.dataset.state = "failed";
    root.querySelector(".splash p").textContent = "The browser stopped the 3D view to free graphics memory. Reload the page to see the model again.";
  });
  engine.start();
  root.dataset.state = "ready";
  return viewer;
}
