// The compass: where north lies on screen. Clicking it returns to the first view.

const STYLE = `
.compass { width: 44px; height: 44px; padding: 0; border-radius: 50%; display: grid; place-items: center; cursor: pointer; color: var(--ink); }
.compass:hover { background: var(--surface); }
.compass svg { width: 34px; height: 34px; overflow: visible; }
.compass .needle { transition: transform 60ms linear; transform-origin: 17px 17px; }
.compass .north { fill: var(--danger); }
.compass .south { fill: var(--ink-3); }
.compass text { font: 600 9px var(--font); fill: var(--ink); text-anchor: middle; }
@media (max-width: 720px) { .compass { width: 40px; height: 40px; } }`;

export default function compass({ engine, shell, h }) {
  shell.style(STYLE);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 34 34");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = `<g class="needle"><text x="17" y="6.5">N</text><path class="north" d="M17 8.5 20 17h-6z"/><path class="south" d="M17 25.5 14 17h6z"/></g>`;
  const needle = svg.querySelector(".needle");
  const button = h("button", { type: "button", class: "surface compass", "aria-label": "Reset the view", "data-tip": "Reset the view" }, svg);
  button.addEventListener("click", () => engine.look("perspective"));
  shell.regions.bottomRight.append(button);

  // Looking north, north points up; looking west from the east, north points right.
  const update = () => {
    needle.style.transform = `rotate(${engine.azimuth()}deg)`;
  };
  engine.on("camera", update);
  engine.on("view", update);
}
