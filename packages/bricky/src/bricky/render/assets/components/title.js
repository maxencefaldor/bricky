// The title card: the model's name, its size, and what the check found.

const STYLE = `
.title-card { padding: 10px 14px 11px; min-width: 0; max-width: min(440px, 100%); }
.title-card h1 { margin: 0; font-size: 15px; font-weight: 600; line-height: 1.3; overflow-wrap: anywhere; }
.title-card .facts { margin: 2px 0 0; color: var(--ink-2); font-size: 12px; }
.title-card .status { margin-top: 8px; }
.title-card button.badge { border: 0; cursor: pointer; font: inherit; font-size: 12px; font-weight: 500; }
.title-card button.badge:hover { filter: brightness(0.96); }
@container stage (max-width: 720px) {
  .title-card { padding: 8px 12px; max-width: calc(100cqw - 80px); }
  .title-card h1 { font-size: 14px; }
  .title-card .status { margin-top: 6px; }
}`;

export default function title({ scene, heading, shell, format, h }) {
  shell.style(STYLE);
  const summary = scene.summary;
  const [east, north] = summary.studs;
  const facts = `${format.count(summary.elements, "element")} · ${format.number(east)} × ${format.number(north)} studs · ${format.number(summary.plates)} plates tall`;
  const card = h("header", { class: "surface title-card" }, h("h1", {}, heading), h("p", { class: "facts numeric" }, facts));

  if (summary.errors !== null) {
    const { errors, warnings } = summary;
    const kind = errors ? "error" : warnings ? "warning" : "ok";
    const text = errors || warnings
      ? [errors ? format.count(errors, "error") : "", warnings ? format.count(warnings, "warning") : ""].filter(Boolean).join(", ")
      : "No errors";
    const badge = h(
      "button",
      { type: "button", class: `badge ${kind}`, "data-tip": "Show the check's findings", onclick: () => shell.panel.open("checks") },
      shell.icon(errors ? "circle-x" : warnings ? "triangle-alert" : "circle-check"),
      text,
    );
    card.append(h("div", { class: "status" }, badge));
    // Without a checks panel, the badge only states the result.
    queueMicrotask(() => {
      if (!shell.panel.has("checks")) badge.replaceWith(h("span", { class: `badge ${kind}` }, ...badge.childNodes));
    });
  }
  shell.regions.topLeft.append(card);
}
