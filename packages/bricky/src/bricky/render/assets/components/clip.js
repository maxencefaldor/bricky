// The clip panel: keep the part of the model within a range along each axis, to look inside, and
// build the model up layer by layer.

const STYLE = `
.clip p.intro { margin: 2px 0 14px; color: var(--ink-2); }
.clip .axis + .axis { margin-top: 18px; }
.clip .axis-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 6px; }
.clip .axis-head strong { font-weight: 600; }
.clip .axis-head output { color: var(--ink-2); font-variant-numeric: tabular-nums; }
.clip .range { position: relative; height: 28px; --thumb: 18px; }
.clip .range .track { position: absolute; left: calc(var(--thumb) / 2); right: calc(var(--thumb) / 2); top: 12px; height: 4px; border-radius: 2px; background: var(--line); }
.clip .range .fill { position: absolute; top: 0; bottom: 0; border-radius: 2px; background: var(--accent); }
.clip .range input {
  position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; background: none; pointer-events: none;
  -webkit-appearance: none; appearance: none;
}
.clip .range input::-webkit-slider-thumb {
  -webkit-appearance: none; pointer-events: auto; width: var(--thumb); height: var(--thumb); border-radius: 50%;
  background: var(--surface); border: 2px solid var(--accent); box-shadow: var(--shadow); cursor: grab;
}
.clip .range input::-moz-range-thumb {
  pointer-events: auto; width: calc(var(--thumb) - 4px); height: calc(var(--thumb) - 4px); border-radius: 50%;
  background: var(--surface); border: 2px solid var(--accent); box-shadow: var(--shadow); cursor: grab;
}
.clip .range input::-webkit-slider-runnable-track { background: none; }
.clip .range input::-moz-range-track { background: none; }
.clip .range input:focus-visible { outline: none; }
.clip .range input:focus-visible::-webkit-slider-thumb { box-shadow: 0 0 0 4px var(--accent-soft); }
.clip .range input:focus-visible::-moz-range-thumb { box-shadow: 0 0 0 4px var(--accent-soft); }
.clip .row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 20px; }
.clip .row .spacer { flex: 1; }
@media (pointer: coarse) { .clip .range { height: 36px; --thumb: 26px; } .clip .range .track { top: 16px; } }`;

const AXES = [
  { axis: "z", name: "Height", unit: "plate", units: "plates" },
  { axis: "x", name: "West to east", unit: "stud", units: "studs" },
  { axis: "y", name: "South to north", unit: "stud", units: "studs" },
];

export default function clip({ engine, shell, format, h }) {
  shell.style(STYLE);
  const unitOf = (axis) => (axis === "z" ? engine.units.plate : engine.units.stud);

  // Each slider moves a whole stud or plate at a time. Its ends lie on that grid around the model,
  // and stand for the model's own ends, which rarely fall on it: at an end, the range keeps all.
  const controls = AXES.map(({ axis, name, units }) => {
    const unit = unitOf(axis);
    const [min, max] = engine.full[axis];
    const lowest = Math.floor(min / unit) * unit;
    const highest = Math.ceil(max / unit) * unit;
    const exact = (value) => (value <= lowest ? min : value >= highest ? max : value);
    const describe = (value) => `${format.number(exact(value) / unit)} ${units}`;
    const attributes = { type: "range", min: lowest, max: highest, step: unit };
    const low = h("input", { ...attributes, value: lowest, "aria-label": `${name}: lowest kept` });
    const high = h("input", { ...attributes, value: highest, "aria-label": `${name}: highest kept` });
    const fill = h("span", { class: "fill" });
    const output = h("output");
    const range = h("div", { class: "range" }, h("span", { class: "track" }, fill), low, high);
    const read = () => [exact(Number(low.value)), exact(Number(high.value))];
    const show = () => {
      const a = Number(low.value), b = Number(high.value);
      const span = highest - lowest || 1;
      fill.style.left = `${((a - lowest) / span) * 100}%`;
      fill.style.right = `${((highest - b) / span) * 100}%`;
      output.textContent = `${format.number(exact(a) / unit)} – ${format.number(exact(b) / unit)} ${units}`;
      low.setAttribute("aria-valuetext", describe(a));
      high.setAttribute("aria-valuetext", describe(b));
      // Where the thumbs meet, the one that can still move takes the pointer.
      const upper = a > (lowest + highest) / 2;
      low.style.zIndex = upper ? "2" : "1";
      high.style.zIndex = upper ? "1" : "2";
    };
    const apply = (moved) => {
      if (Number(low.value) > Number(high.value) - unit) {
        if (moved === low) low.value = String(Math.max(lowest, Number(high.value) - unit));
        else high.value = String(Math.min(highest, Number(low.value) + unit));
      }
      show();
      engine.setSection({ [axis]: read() });
    };
    low.addEventListener("input", () => apply(low));
    high.addEventListener("input", () => apply(high));
    show();
    const element = h("div", { class: "axis" }, h("div", { class: "axis-head" }, h("strong", {}, name), output), range);
    return { axis, unit, low, high, show, apply, read, element, lowest, highest };
  });
  const height = controls[0];

  // Building up raises the top of the height range a plate at a time; pausing keeps the layer
  // reached, and playing again goes on from it.
  let building = null;
  const play = shell.button({ icon: "play", text: "Build up", label: "Build up", shortcut: "B", variant: "small outlined", onClick: () => toggleBuild() });
  const playLabel = play.querySelector("span");
  const stopBuild = () => {
    if (!building) return;
    cancelAnimationFrame(building.frame);
    building = null;
    play.replaceChild(shell.icon("play"), play.querySelector("svg"));
    playLabel.textContent = "Build up";
  };
  const toggleBuild = () => {
    if (building) return stopBuild();
    const plate = height.unit;
    const bottom = Number(height.low.value) + plate;
    const current = Number(height.high.value);
    const start = current >= height.highest ? bottom : current + plate;
    const end = height.highest;
    const layers = Math.max(1, (end - start) / plate);
    const duration = Math.min(9000, Math.max(1500, layers * 70));
    const began = performance.now();
    building = { frame: 0 };
    play.replaceChild(shell.icon("pause"), play.querySelector("svg"));
    playLabel.textContent = "Pause";
    const tick = (now) => {
      if (!building) return;
      const t = Math.min(1, (now - began) / duration);
      height.high.value = String(Math.min(end, start + Math.round(((end - start) * t) / plate) * plate));
      height.apply(height.high);
      if (t < 1) building.frame = requestAnimationFrame(tick);
      else stopBuild();
    };
    building.frame = requestAnimationFrame(tick);
  };
  // One layer up or down, from the keyboard or the buttons.
  const stepLayer = (direction) => {
    stopBuild();
    const plate = height.unit;
    const next = Number(height.high.value) + direction * plate;
    height.high.value = String(Math.min(height.highest, Math.max(Number(height.low.value) + plate, next)));
    height.apply(height.high);
  };
  const reset = () => {
    stopBuild();
    const next = {};
    for (const control of controls) {
      control.low.value = String(control.lowest);
      control.high.value = String(control.highest);
      control.show();
      next[control.axis] = control.read();
    }
    engine.setSection(next);
  };

  const view = h(
    "div",
    { class: "clip" },
    h("p", { class: "intro" }, "Keep what lies within each range, to look inside the model."),
    ...controls.map((control) => control.element),
    h("div", { class: "row" },
      play,
      shell.button({ icon: "chevron-left", label: "One layer down", shortcut: "[", variant: "small outlined", onClick: () => stepLayer(-1) }),
      shell.button({ icon: "chevron-right", label: "One layer up", shortcut: "]", variant: "small outlined", onClick: () => stepLayer(1) }),
      h("span", { class: "spacer" }),
      shell.button({ icon: "rotate-ccw", text: "Reset", label: "Keep everything", variant: "small outlined", onClick: reset }),
    ),
  );
  const { toggle } = shell.panel.add({ id: "clip", label: "Clip", icon: "scissors", shortcut: "X", order: 30, view });

  // The toolbar button shows a dot while a clip keeps part of the model.
  shell.style(`.button.clipping { position: relative; } .button.clipping::after { content: ""; position: absolute; top: 6px; right: 6px; width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }`);
  engine.on("section", (section) => {
    const clipped = ["x", "y", "z"].some((axis) => section[axis][0] > engine.full[axis][0] || section[axis][1] < engine.full[axis][1]);
    toggle.classList.toggle("clipping", clipped);
  });
  shell.shortcuts.add({ key: "b", label: "Build the model up, or pause", group: "Clip", run: () => toggleBuild() });
  shell.shortcuts.add({ key: "[", label: "One layer down", group: "Clip", run: () => stepLayer(-1) });
  shell.shortcuts.add({ key: "]", label: "One layer up", group: "Clip", run: () => stepLayer(1) });
}
