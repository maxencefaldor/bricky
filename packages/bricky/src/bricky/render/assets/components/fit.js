// Fit: frame what is shown, from where the camera looks.

export default function fit({ engine, shell }) {
  shell.toolbar.add({ group: "tools", order: 10, icon: "focus", label: "Fit to view", shortcut: "F", onClick: () => engine.fit() });
  shell.shortcuts.add({ key: "f", label: "Fit to view", group: "Navigate", run: () => engine.fit() });
}
