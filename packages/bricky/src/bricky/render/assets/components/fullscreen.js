// Full screen: give the viewer the whole screen, where the browser allows it.

export default function fullscreen({ shell }) {
  if (!document.fullscreenEnabled) return;
  const toggle = () => (document.fullscreenElement ? document.exitFullscreen() : shell.root.requestFullscreen());
  const button = shell.toolbar.add({ group: "tools", order: 30, icon: "maximize", label: "Full screen", onClick: toggle });
  document.addEventListener("fullscreenchange", () => {
    const on = Boolean(document.fullscreenElement);
    button.replaceChildren(shell.icon(on ? "minimize" : "maximize"));
    button.setAttribute("aria-label", on ? "Exit full screen" : "Full screen");
    button.dataset.tip = on ? "Exit full screen" : "Full screen";
  });
}
