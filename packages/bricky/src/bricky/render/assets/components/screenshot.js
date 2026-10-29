// Screenshot: save the 3D view as a PNG, at twice the screen's resolution.

export default function screenshot({ scene, engine, shell, h }) {
  const save = async () => {
    const blob = await engine.screenshot();
    if (!blob) return shell.toast("The browser could not save the image");
    const file = `${scene.name}.png`;
    const url = URL.createObjectURL(blob);
    const link = h("a", { href: url, download: file });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    shell.toast(`Saved ${file}`);
  };
  shell.toolbar.add({ group: "tools", order: 20, icon: "camera", label: "Save an image", shortcut: "S", onClick: save });
  shell.shortcuts.add({ key: "s", label: "Save an image", group: "View", run: save });
}
