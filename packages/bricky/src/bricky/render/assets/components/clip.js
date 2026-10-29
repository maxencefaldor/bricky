// The clip panel: keep the part of the model within a range along each axis, to look inside, and
// build the model up layer by layer.

const STYLE = `
.clip p.intro { margin: 2px 0 14px; color: var(--ink-2); }
.clip .axis + .axis { margin-top: 18px; }
.clip .axis-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 6px; }
.clip .axis-head strong { font-weight: 600; }
.clip .axis-head output { color: var(--ink-2); font-variant-numeric: tabular-nums; }
.clip .range { position: relative; height: 28px; }
.clip .range .track { position: absolute; left: 9px; right: 9px; top: 12px; height: 4px; border-radius: 2px; background: var(--line); }
.clip .range .fill { position: absolute; top: 0; bottom: 0; border-radius: 2px; background: var(--accent); }
.clip .range input {
  position: absolute; inset: 0; width: 100%; margin: 0; background: none; pointer-events: none;
  -webkit-appearance: none; appearance: none;
}
.clip .range input::-webkit-slider-thumb {
  -webkit-appearance: none; pointer-events: auto; width: 18px; height: 18px; border-radius: 50%;
  background: var(--surface); border: 2px solid var(--accent); box-shadow: var(--shadow); cursor: grab;
}
.clip .range input::-moz-range-thumb {
  pointer-events: auto; width: 14px; height: 14px; border-radius: 50%;
  background: var(--surface); border: 2px solid var(--accent); box-shadow: var(--shadow); cursor: grab;
}
.clip .range input::-webkit-slider-runnable-track { background: none; }
.clip .range input::-moz-range-track { background: none; }
.clip .range input:focus-visible { outline: none; }
.clip .range input:focus-visible::-webkit-slider-thumb { box-shadow: 0 0 0 4px var(--accent-soft); }
.clip .row { display: flex; gap: 6px; margin-top: 20px; }`;

const AXES = [
  { axis: "z", name: "Height", unit: "plate", units: "plates" },
  { axis: "x", name: "West to east", unit: "stud", units: "studs" },
  { axis: "y", name: "South to north", unit: "stud", units: "studs" },
];

export default function clip({ engine, shell, format, h }) {
  shell.style(STYLE);
  const unitOf = (axis) => (axis === "z" ? engine.units.plate : engine.units.stud);
  const step = (axis) => unitOf(axis); // one plate up, one stud across
  const toUnits = (axis, value) => value / unitOf(axis);

  const controls = AXES.map(({ axis, name, units }) => {
    const [min, max] = engine.full[axis];
    const low = h("input", { type: "range", min, max, step: step(axis), value: min, "aria-label": `${name}: lowest kept` });
    const high = h("input", { type: "range", min, max, step: step(axis), value: max, "aria-label": `${name}: highest kept` });
    // The model's extent rarely falls on whole studs or plates: let the ends reach it exactly.
    low.min = high.min = String(min);
    low.max = high.max = String(max);
    const fill = h("span", { class: "fill" });
    const output = h("output");
    const range = h("div", { class: "range" }, h("span", { class: "track" }, fill), low, high);
    const show = () => {
      const a = Number(low.value), b = Number(high.value);
      const span = max - min || 1;
      fill.style.left = `${((a - min) / span) * 100}%`;
      fill.style.right = `${((max - b) / span) * 100}%`;
      output.textContent = `${format.number(toUnits(axis, a))} – ${format.number(toUnits(axis, b))} ${units}`;
    };
    const apply = (moved) => {
      if (Number(low.value) > Number(high.value) - step(axis)) {
        if (moved === low) low.value = String(Math.max(min, Number(high.value) - step(axis)));
        else high.value = String(Math.min(max, Number(low.value) + step(axis)));
      }
      show();
      engine.setSection({ [axis]: [Number(low.value), Number(high.value)] });
    };
    low.addEventListener("input", () => apply(low));
    high.addEventListener("input", () => apply(high));
    show();
    const element = h("div", { class: "axis" }, h("div", { class: "axis-head" }, h("strong", {}, name), output), range);
    return { axis, low, high, show, element, min, max };
  });

  // Build up: raise the top of the height range from the bottom, a plate at a time.
  let building = null;
  const playLabel = h("span", {}, "Build up");
  const play = shell.button({ icon: "play", text: "Build up", label: "Build up", shortcut: "B", variant: "small outlined", onClick: () => toggleBuild() });
  play.replaceChild(playLabel, play.querySelector("span"));
  const stopBuild = () => {
    if (!building) return;
    cancelAnimationFrame(building.frame);
    building = null;
    play.replaceChild(shell.icon("play"), play.querySelector("svg"));
    playLabel.textContent = "Build up";
  };
  const toggleBuild = () => {
    if (building) return stopBuild();
    const height = controls[0];
    const start = Number(height.low.value) + engine.units.plate;
    const end = height.max;
    const layers = Math.max(1, (end - start) / engine.units.plate);
    const duration = Math.min(9000, Math.max(2500, layers * 70));
    const began = performance.now();
    building = { frame: 0 };
    play.replaceChild(shell.icon("pause"), play.querySelector("svg"));
    playLabel.textContent = "Pause";
    const tick = (now) => {
      if (!building) return;
      const t = Math.min(1, (now - began) / duration);
      const top = Math.min(end, start + Math.round(((end - start) * t) / engine.units.plate) * engine.units.plate);
      height.high.value = String(t === 1 ? end : top);
      height.show();
      engine.setSection({ z: [Number(height.low.value), Number(height.high.value)] });
      if (t < 1) building.frame = requestAnimationFrame(tick);
      else stopBuild();
    };
    building.frame = requestAnimationFrame(tick);
  };
  const reset = () => {
    stopBuild();
    const next = {};
    for (const control of controls) {
      control.low.value = String(control.min);
      control.high.value = String(control.max);
      control.show();
      next[control.axis] = [control.min, control.max];
    }
    engine.setSection(next);
  };

  const view = h(
    "div",
    { class: "clip" },
    h("p", { class: "intro" }, "Keep what lies within each range, to look inside the model."),
    ...controls.map((control) => control.element),
    h("div", { class: "row" }, play, shell.button({ icon: "rotate-ccw", text: "Reset", label: "Keep everything", variant: "small outlined", onClick: reset })),
  );
  const { toggle } = shell.panel.add({ id: "clip", label: "Clip", icon: "scissors", shortcut: "X", order: 30, view });

  // The toolbar button shows a dot while a clip keeps part of the model.
  shell.style(`.button.clipping { position: relative; } .button.clipping::after { content: ""; position: absolute; top: 6px; right: 6px; width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }`);
  engine.on("section", (section) => {
    const clipped = controls.some((control) => section[control.axis][0] > control.min || section[control.axis][1] < control.max);
    toggle.classList.toggle("clipping", clipped);
  });
  shell.shortcuts.add({ key: "b", label: "Build the model up, or pause", group: "Clip", run: () => toggleBuild() });
}
