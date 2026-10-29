// The checks panel: every error and warning of the check, numbered, with a matching pin on the
// model. Choosing one selects the elements it names and brings them into view. A pin shows while
// the model shows its diagnostic, which instructions reveal once every element it names is built.

const STYLE = `
.checks .result { display: flex; align-items: center; gap: 8px; margin: 2px 0 12px; }
.checks ol { list-style: none; margin: 0 -8px; padding: 0; }
.checks li button {
  display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 10px; width: 100%; padding: 8px;
  border: 0; border-radius: var(--radius-control); background: transparent; text-align: left; cursor: pointer;
}
.checks li button:hover { background: var(--hover); }
.checks li button[aria-pressed="true"] { background: var(--accent-soft); }
.checks .rule { font-family: var(--mono); font-size: 12px; font-weight: 600; }
.checks .rule.error { color: var(--danger); }
.checks .rule.warning { color: var(--warning); }
.checks .message { display: block; margin-top: 1px; }
.checks .who { display: block; margin-top: 2px; color: var(--ink-2); font-size: 12px; font-family: var(--mono); overflow-wrap: anywhere; }
.checks .more { margin: 10px 0 0; color: var(--ink-2); font-size: 12px; }
.pin, .checks .number {
  display: grid; place-items: center; min-width: 22px; height: 22px; padding: 0 6px; border-radius: 11px;
  font-size: 11px; font-weight: 700; color: #ffffff; background: var(--danger); font-variant-numeric: tabular-nums;
}
.pin.warning, .checks .number.warning { background: var(--warning); }
.pin {
  position: absolute; transform: translate(-50%, -50%); border: 2px solid #ffffff; cursor: pointer;
  box-shadow: 0 1px 4px rgb(1 4 9 / 0.35); pointer-events: auto; transition: transform 120ms var(--ease);
}
.pin:hover { transform: translate(-50%, -50%) scale(1.12); }
@media (prefers-color-scheme: dark) {
  .pin, .checks .number { color: #0d1117; }
  .pin { border-color: #0d1117; }
}
.pin[hidden] { display: none; }`;

export default function checks({ scene, engine, shell, format, h }) {
  const summary = scene.summary;
  if (summary.errors === null) return;
  shell.style(STYLE);
  const findings = scene.diagnostics;
  const { errors, warnings } = summary;

  let chosen = null;
  const choose = (index) => {
    chosen = chosen === index ? null : index;
    const finding = chosen === null ? null : findings[chosen];
    engine.select(finding ? finding.elements : []);
    if (finding?.elements.length) engine.focus(finding.elements);
    rows.forEach((row, i) => row.setAttribute("aria-pressed", String(i === chosen)));
  };
  engine.on("selection", () => {
    if (chosen === null) return;
    const finding = findings[chosen];
    const same = engine.selection.size === finding.elements.length && finding.elements.every((i) => engine.selection.has(i));
    if (!same) {
      chosen = null;
      rows.forEach((row) => row.setAttribute("aria-pressed", "false"));
    }
  });

  const rows = findings.map((finding, i) => {
    const uids = finding.elements.slice(0, 3).map((element) => scene.uids[element]);
    const rest = finding.elements.length - uids.length;
    return h(
      "button",
      { type: "button", "aria-pressed": "false", onclick: () => choose(i) },
      h("span", { class: `number ${finding.kind}` }, String(i + 1)),
      h("span", {},
        h("span", { class: `rule ${finding.kind}` }, finding.rule),
        h("span", { class: "message" }, finding.message),
        uids.length ? h("span", { class: "who" }, uids.join(", ") + (rest > 0 ? `, and ${format.count(rest, "more element")}` : "")) : null,
      ),
    );
  });

  const result = errors || warnings
    ? h("span", { class: `badge ${errors ? "error" : "warning"}` }, shell.icon(errors ? "circle-x" : "triangle-alert"),
      [errors ? format.count(errors, "error") : "", warnings ? format.count(warnings, "warning") : ""].filter(Boolean).join(", "))
    : null;
  const view = h(
    "div",
    { class: "checks" },
    result ? h("div", { class: "result" }, result) : null,
    findings.length
      ? h("ol", { "aria-label": "Findings" }, ...rows.map((row) => h("li", {}, row)))
      : h("div", { class: "empty" }, shell.icon("circle-check"), h("p", {}, "The check found no errors or warnings.")),
    summary.omitted ? h("p", { class: "more" }, `${format.count(summary.omitted, "more finding")} not listed: the report's cap left them out.`) : null,
  );
  shell.panel.add({ id: "checks", label: "Checks", icon: "list-checks", shortcut: "C", order: 20, view });

  // Pins: each finding's number, on top of its first element.
  const pins = findings.map((finding, i) => {
    if (!finding.elements.length) return null;
    const pin = h("button", { type: "button", class: `pin ${finding.kind}`, "aria-label": `Finding ${i + 1}: ${finding.rule}`, "data-tip": `${finding.rule}: ${finding.message}` }, String(i + 1));
    pin.addEventListener("click", () => {
      shell.panel.open("checks");
      if (chosen !== i) choose(i);
    });
    shell.overlay.append(pin);
    const box = engine.elementBox(finding.elements[0]);
    const middle = box.getCenter(box.min.clone());
    const anchor = middle.clone().setY(box.max.y);
    return { pin, anchor, middle, element: finding.elements[0], index: i };
  });
  // Pins that would land on one another line up side by side instead.
  const place = () => {
    const placed = [];
    for (const item of pins) {
      if (!item) continue;
      const where = engine.project(item.anchor);
      item.pin.hidden = !where.front || !engine.showsDiagnostic(item.index) || engine.isHidden(item.element) || !engine.inSection(item.middle);
      if (item.pin.hidden) continue;
      let x = where.x;
      while (placed.some((other) => Math.abs(other.x - x) < 24 && Math.abs(other.y - where.y) < 24)) x += 26;
      placed.push({ x, y: where.y });
      item.pin.style.left = `${x}px`;
      item.pin.style.top = `${where.y}px`;
    }
  };
  engine.on("render", place);

  if (errors && window.innerWidth > 720) queueMicrotask(() => shell.panel.open("checks"));
}
