// Instructions: build the model step by step. Each step shows what is built so far, moves the
// elements it adds into place along the way they go on, outlines them, and lists them as parts to
// find. The camera frames each step from a side where its elements show.

const STYLE = `
.step-card { padding: 12px 12px 12px 14px; width: max-content; min-width: 220px; max-width: min(372px, var(--beside-toolbar)); }
.step-card .head { display: flex; align-items: flex-start; gap: 10px; }
.step-card .where { flex: 1; min-width: 0; }
.step-card .count { display: flex; align-items: baseline; gap: 6px; margin: 0; }
.step-card .number { font-size: 30px; font-weight: 650; line-height: 1; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
.step-card .of { color: var(--ink-2); font-size: 13px; font-variant-numeric: tabular-nums; }
.step-card .section { margin: 4px 0 0; color: var(--ink-2); font-size: 12px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.step-card .head .button { margin: -4px -4px 0 0; }
.step-card .lots { display: grid; grid-template-columns: repeat(auto-fill, 68px); gap: 8px; margin: 12px 0 0; padding: 0; list-style: none; }
.step-card .lot {
  position: relative; display: block; width: 68px; height: 68px; padding: 0; border: 1px solid var(--line);
  border-radius: 10px; background: var(--surface-sunken); cursor: pointer;
  transition: border-color 120ms var(--ease), box-shadow 120ms var(--ease);
}
.step-card .lot:hover { border-color: var(--line-strong); }
.step-card .lot[aria-pressed="true"] { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.step-card .lot img { display: block; width: 100%; height: 100%; padding: 6px 6px 14px; object-fit: contain; }
.step-card .lot .times {
  position: absolute; left: 6px; bottom: 3px; font-size: 12px; font-weight: 650; font-variant-numeric: tabular-nums;
}
.step-card .more { display: grid; place-items: center; width: 68px; height: 68px; color: var(--ink-2); font-weight: 600; }
.step-card .note {
  display: flex; gap: 8px; margin: 12px 0 0; padding: 8px 10px; border-radius: var(--radius-control);
  background: var(--warning-soft); color: var(--ink); font-size: 12px; line-height: 1.4;
}
.step-card .note svg.icon { color: var(--warning); margin-top: 1px; }
.step-card .note[hidden] { display: none; }
.step-bar { display: flex; align-items: center; gap: 4px; padding: 4px; width: min(520px, calc(100cqw - 2 * var(--gap))); }
.step-bar .slider { flex: 1; min-width: 48px; height: var(--control); margin: 0 8px; background: none; -webkit-appearance: none; appearance: none; cursor: pointer; }
.step-bar .slider::-webkit-slider-runnable-track {
  height: 4px; border-radius: 2px;
  background: linear-gradient(to right, var(--accent) var(--progress), var(--line-strong) var(--progress));
}
.step-bar .slider::-moz-range-track { height: 4px; border-radius: 2px; background: var(--line-strong); }
.step-bar .slider::-moz-range-progress { height: 4px; border-radius: 2px; background: var(--accent); }
.step-bar .slider::-webkit-slider-thumb {
  -webkit-appearance: none; width: 18px; height: 18px; margin-top: -7px; border-radius: 50%;
  background: var(--surface); border: 2px solid var(--accent); box-shadow: var(--shadow);
}
.step-bar .slider::-moz-range-thumb {
  width: 14px; height: 14px; border-radius: 50%; background: var(--surface); border: 2px solid var(--accent); box-shadow: var(--shadow);
}
.step-bar .slider:focus-visible { outline: none; }
.step-bar .slider:focus-visible::-webkit-slider-thumb { box-shadow: 0 0 0 4px var(--accent-soft); }
.step-bar .slider:focus-visible::-moz-range-thumb { box-shadow: 0 0 0 4px var(--accent-soft); }
.step-bar .next { flex-direction: row-reverse; min-width: 96px; padding: 0 10px 0 14px; font-weight: 600; }
@container stage (max-width: 600px) {
  .step-card { padding: 10px 10px 10px 12px; min-width: 0; }
  .step-card .number { font-size: 24px; }
  .step-card .lots { grid-template-columns: none; grid-auto-flow: column; grid-auto-columns: 56px; overflow-x: auto; margin-top: 10px; }
  .step-card .lot, .step-card .more { width: 56px; height: 56px; }
  .step-card .lot img { padding: 4px 4px 12px; }
  .step-bar { width: calc(100cqw - 2 * var(--gap) - 2 * 52px); }
  .step-bar .first { display: none; }
  .step-bar .next { min-width: 0; }
}`;

const CORNERS = [35, -35, 145, 215]; // the azimuths of the four 3D views, at 30 degrees up
const CONTEXT = 32; // millimeters, at least, that a step's framing shows around its elements
const SHOWN_LOTS = 12; // the lots a step card shows before counting the rest

export default function instructions({ scene, engine, shell, format, h, mode }) {
  const steps = scene.steps ?? [];
  if (!steps.length) return;
  shell.style(STYLE);
  const last = steps.length - 1;

  // What each step builds: every element up to its end, and the box around them.
  const order = steps.flatMap((step) => step.elements);
  const ends = [];
  const builtBoxes = [];
  let built = null;
  for (const step of steps) {
    for (const i of step.elements) built = built ? built.union(engine.elementBox(i)) : engine.elementBox(i);
    ends.push((ends.at(-1) ?? 0) + step.elements.length);
    builtBoxes.push(built.clone());
  }
  const boxOf = (elements) => elements.reduce((box, i) => (box ? box.union(engine.elementBox(i)) : engine.elementBox(i)), null);

  // The lots a step adds: its elements by part and color, in the order they first go on.
  const lotsOf = (step) => {
    const lots = new Map();
    for (const i of step.elements) {
      const [color, , part] = scene.elements[i];
      const key = `${part}:${color}`;
      if (!lots.has(key)) lots.set(key, { part: scene.parts[part], color: scene.colors[color], elements: [] });
      lots.get(key).elements.push(i);
    }
    return [...lots.values()];
  };

  // ------------------------------------------------------------------------------------------
  // The step card, at the top left, and the step bar, at the bottom

  const number = h("span", { class: "number" });
  const section = h("p", { class: "section" });
  const lotList = h("ul", { class: "lots", "aria-label": "Parts this step adds" });
  const note = h("p", { class: "note", hidden: true });
  const exit = shell.button({ icon: "x", label: "Exit the instructions", shortcut: "Esc", onClick: () => leave() });
  const card = h(
    "section",
    { class: "surface step-card", "aria-label": "Building step" },
    h("div", { class: "head" },
      h("div", { class: "where" }, h("p", { class: "count" }, number, h("span", { class: "of" }, `of ${format.number(steps.length)}`)), section),
      exit,
    ),
    lotList,
    note,
  );

  const first = shell.button({ icon: "chevron-first", label: "First step", shortcut: "Home", onClick: () => go(0) });
  first.classList.add("first");
  const previous = shell.button({ icon: "chevron-left", label: "Previous step", shortcut: "←", onClick: () => go(current - 1) });
  previous.setAttribute("aria-keyshortcuts", "ArrowLeft");
  const slider = h("input", { type: "range", class: "slider", min: 1, max: steps.length, step: 1, value: 1, "aria-label": "Step" });
  const next = shell.button({ text: "Next", icon: "chevron-right", variant: "primary next", onClick: () => (current === last ? leave() : go(current + 1)) });
  next.dataset.tip = "Next step";
  next.dataset.shortcut = "→";
  next.setAttribute("aria-keyshortcuts", "ArrowRight");
  const bar = h("nav", { class: "surface step-bar", "aria-label": "Steps" }, first, previous, slider, next);
  // Dragging the slider builds the model up or down under a still camera; letting go frames the
  // step it stops on.
  slider.addEventListener("input", () => go(Number(slider.value) - 1, { still: true }));
  slider.addEventListener("change", () => frame(steps[current], true));

  const toggle = shell.toolbar.add({ group: "panels", order: 5, icon: "book-open", label: "Instructions", shortcut: "N", pressed: false, onClick: () => (active ? leave() : enter()) });

  // ------------------------------------------------------------------------------------------
  // Showing a step

  let active = false;
  let current = 0;
  let releases = [];

  // Frame the step's elements with some of what they join, from the side that shows them best:
  // the camera's own side when it shows them nearly as well as the best of the 3D views.
  const frame = (step, animate) => {
    const added = boxOf(step.elements);
    const size = added.getSize(added.min.clone());
    const margin = Math.max(CONTEXT, 0.5 * Math.max(size.x, size.z));
    const context = added.clone().expandByScalar(margin).intersect(builtBoxes[current]).union(added);
    const candidates = [engine.direction, ...CORNERS.map((azimuth) => engine.along(azimuth, 30))];
    const counts = engine.coverage(step.elements, context, candidates);
    const best = Math.max(...counts);
    let along = candidates[0];
    if (best > 0 && counts[0] < 0.7 * best) {
      let angle = Infinity;
      candidates.forEach((candidate, k) => {
        if (k === 0 || counts[k] < 0.85 * best) return;
        const turn = candidate.angleTo(candidates[0]);
        if (turn < angle) [angle, along] = [turn, candidate];
      });
    }
    engine.frameBox(context, { along, animate });
  };

  const showLots = (step) => {
    const lots = lotsOf(step);
    const items = lots.slice(0, SHOWN_LOTS).map((lot) => {
      const count = lot.elements.length;
      const image = h("img", { alt: "", width: 68, height: 68 });
      const tile = h(
        "button",
        {
          type: "button", class: "lot", "aria-pressed": "false",
          "aria-label": `${count} × ${lot.part.name}, ${lot.color.name}`, "data-tip": `${count} × ${lot.part.name}, ${lot.color.name}`,
          onclick: () => {
            const same = engine.selection.size === count && lot.elements.every((i) => engine.selection.has(i));
            engine.select(same ? [] : lot.elements);
          },
        },
        image,
        h("span", { class: "times" }, `${count}×`),
      );
      tile.lot = lot;
      // Pictures render after the step shows, so stepping stays quick.
      requestAnimationFrame(() => {
        if (tile.isConnected) image.src = engine.portrait(lot.elements[0]);
      });
      return h("li", {}, tile);
    });
    if (lots.length > SHOWN_LOTS) items.push(h("li", { class: "more" }, `+${lots.length - SHOWN_LOTS}`));
    lotList.replaceChildren(...items);
    return lots;
  };

  const show = ({ forward = false, still = false } = {}) => {
    const step = steps[current];
    engine.select([]);
    engine.limit(order.slice(0, ends[current]));
    engine.emphasize(step.elements);
    if (!still) frame(step, true);
    engine.arrive(forward ? step.elements : [], step.approaches);
    number.textContent = format.number(current + 1);
    section.textContent = step.section;
    section.hidden = !step.section;
    const lots = showLots(step);
    note.hidden = !step.notes.length;
    note.replaceChildren(shell.icon("triangle-alert"), h("span", {}, `Out of order: ${step.notes.join("; ")}.`));
    slider.value = String(current + 1);
    slider.style.setProperty("--progress", `${(last ? current / last : 1) * 100}%`);
    slider.setAttribute("aria-valuetext", `Step ${current + 1} of ${steps.length}`);
    first.disabled = previous.disabled = current === 0;
    next.replaceChildren(shell.icon(current === last ? "check" : "chevron-right"), h("span", {}, current === last ? "Finish" : "Next"));
    next.dataset.tip = current === last ? "Leave the instructions" : "Next step";
    const parts = lots.map((lot) => `${lot.elements.length} ${lot.part.name}, ${lot.color.name}`).join("; ");
    shell.announce(`Step ${current + 1} of ${steps.length}${step.section ? `, ${step.section}` : ""}: ${parts}.`);
    history.replaceState(null, "", `#step-${current + 1}`);
  };

  const go = (k, { still = false } = {}) => {
    if (!active) return;
    const target = Math.max(0, Math.min(last, k));
    if (target === current) return;
    const forward = target === current + 1 && !still;
    current = target;
    show({ forward, still });
  };

  const enter = (k = 0) => {
    if (active) return;
    active = true;
    releases = [shell.claim("topLeft", card), shell.claim("bottom", bar)];
    toggle.setAttribute("aria-pressed", "true");
    current = Math.max(0, Math.min(last, k));
    show({ forward: true });
  };

  const leave = () => {
    if (!active) return;
    active = false;
    releases.forEach((release) => release());
    releases = [];
    lotList.replaceChildren();
    toggle.setAttribute("aria-pressed", "false");
    engine.select([]);
    engine.arrive([], []);
    engine.emphasize([]);
    engine.limit(null);
    engine.fit();
    history.replaceState(null, "", location.pathname + location.search);
    shell.announce("Left the instructions: the whole model shows.");
  };

  // A tile stays pressed while its lot is the selection.
  engine.on("selection", () => {
    for (const tile of lotList.querySelectorAll(".lot")) {
      const { elements } = tile.lot;
      tile.setAttribute("aria-pressed", String(engine.selection.size === elements.length && elements.every((i) => engine.selection.has(i))));
    }
  });

  // ------------------------------------------------------------------------------------------
  // Keys: the arrows step while the instructions show, unless the focus is in a field or panel

  const free = () => active && !document.activeElement?.closest("input, textarea, select, .panel, .menu, dialog");
  shell.shortcuts.add({ key: "n", label: "Show or hide the instructions", group: "Instructions", run: () => (active ? leave() : enter()) });
  shell.shortcuts.add({ key: "ArrowRight", label: "Next step", group: "Instructions", when: free, run: () => go(current + 1) });
  shell.shortcuts.add({ key: "ArrowLeft", label: "Previous step", group: "Instructions", when: free, run: () => go(current - 1) });
  shell.shortcuts.add({ key: "Home", label: "First step", group: "Instructions", when: free, run: () => go(0) });
  shell.shortcuts.add({ key: "End", label: "Last step", group: "Instructions", when: free, run: () => go(last) });
  // Escape leaves the instructions once nothing else wants it, such as a selection.
  shell.shortcuts.escape(() => {
    if (!active || engine.selection.size || engine.isolation !== null) return false;
    leave();
    return true;
  });

  // A link to a step opens the instructions there, and so does a page made for them.
  const linked = /^#step-(\d+)$/.exec(location.hash);
  if (linked || mode === "instructions") queueMicrotask(() => enter(linked ? Number(linked[1]) - 1 : 0));
}
