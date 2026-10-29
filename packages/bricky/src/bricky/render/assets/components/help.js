// Help: the mouse, touch and keyboard controls, in a dialog.

const STYLE = `
.help h3 { margin: 16px 0 6px; font-size: 11px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--ink-2); }
.help h3:first-child { margin-top: 4px; }
.help dl { display: grid; grid-template-columns: minmax(120px, auto) 1fr; gap: 6px 16px; margin: 0; }
.help dt { white-space: nowrap; }
.help dd { margin: 0; color: var(--ink-2); }
.help kbd {
  display: inline-block; min-width: 22px; padding: 1px 6px; border: 1px solid var(--line-strong); border-bottom-width: 2px;
  border-radius: 5px; background: var(--surface-sunken); font: 11px/18px var(--font); text-align: center;
}
.help .columns { display: grid; grid-template-columns: 1fr 1fr; gap: 0 24px; }
@media (max-width: 560px) { .help .columns { grid-template-columns: 1fr; } }`;

const POINTER = [
  ["Drag", "Orbit"],
  ["Right-drag", "Pan"],
  ["Scroll", "Zoom toward the pointer"],
  ["Click", "Select a part"],
  ["Double-click", "Bring a part close"],
];
const TOUCH = [
  ["One finger", "Orbit"],
  ["Two fingers", "Pan and pinch to zoom"],
  ["Tap", "Select a part"],
  ["Double tap", "Bring a part close"],
];
const KEY_NAMES = { ArrowLeft: "←", ArrowRight: "→", ArrowUp: "↑", ArrowDown: "↓", Esc: "Esc", Home: "Home", End: "End" };

export default function help({ shell, h }) {
  shell.style(STYLE);
  const list = (rows) => h("dl", {}, ...rows.flatMap(([what, does]) => [h("dt", {}, what), h("dd", {}, does)]));
  const keys = () => {
    const groups = new Map();
    for (const { key, label, group } of shell.shortcuts.list()) {
      if (key === "+" || key === "=") continue;
      if (!groups.has(group)) groups.set(group, []);
      groups.get(group).push([h("kbd", {}, KEY_NAMES[key] ?? key.toUpperCase()), label]);
    }
    groups.get("Navigate")?.push([h("span", {}, h("kbd", {}, "+"), " ", h("kbd", {}, "−")), "Zoom in and out"]);
    return [...groups].flatMap(([group, rows]) => [h("h3", {}, group), list(rows.filter(([, label]) => label !== "Zoom in" && label !== "Zoom out"))]);
  };
  const content = h("div", { class: "help" });
  const dialog = shell.dialog({ title: "Controls", content });
  const open = () => {
    content.replaceChildren(
      h("div", { class: "columns" },
        h("div", {}, h("h3", {}, "Mouse"), list(POINTER)),
        h("div", {}, h("h3", {}, "Touch"), list(TOUCH)),
      ),
      ...keys(),
    );
    dialog.open();
  };
  shell.toolbar.add({ group: "tools", order: 90, icon: "circle-help", label: "Controls", shortcut: "?", onClick: open });
  shell.shortcuts.add({ key: "?", label: "Show the controls", group: "View", run: open });
}
