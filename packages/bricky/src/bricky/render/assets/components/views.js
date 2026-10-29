// The view bar: the 3D views, the five flat views, and the projection.

const STYLE = `
.view-bar { display: flex; align-items: center; gap: 2px; padding: 4px; }
.view-bar .split { display: flex; }
.view-bar .split .button:first-child { border-radius: var(--radius-control) 0 0 var(--radius-control); padding-right: 6px; }
.view-bar .split .button:last-child { border-radius: 0 var(--radius-control) var(--radius-control) 0; min-width: 24px; width: 24px; padding: 0; }
.view-bar .divider { width: 1px; height: 20px; margin: 0 4px; background: var(--line); }
.view-bar .narrow { display: none; }
@container stage (max-width: 600px) {
  .view-bar .wide { display: none; }
  .view-bar .narrow { display: inline-flex; }
}`;

const CORNERS = ["perspective", "perspective-south-west", "perspective-north-west", "perspective-north-east"];
const FLAT = [["front", "1"], ["back", "2"], ["left", "3"], ["right", "4"], ["top", "5"]];
const NAMES = {
  perspective: "From the south-east", "perspective-south-west": "From the south-west",
  "perspective-north-west": "From the north-west", "perspective-north-east": "From the north-east",
  front: "Front", back: "Back", left: "Left", right: "Right", top: "Top",
};

export default function views({ engine, shell, h }) {
  shell.style(STYLE);
  let corner = "perspective";
  const look = (name) => {
    if (CORNERS.includes(name)) corner = name;
    engine.look(name);
  };

  const threeD = shell.button({ text: "3D", icon: "box", label: "3D view", shortcut: "0", pressed: true, onClick: () => look(corner) });
  threeD.dataset.tip = "3D view";
  const cornerMenu = shell.button({
    icon: "chevron-down", label: "Look from another corner",
    attributes: { "aria-haspopup": "menu", "aria-expanded": "false" },
    onClick: () => shell.menu(cornerMenu, CORNERS.map((name) => ({ label: NAMES[name], checked: engine.view === name, onSelect: () => look(name) }))),
  });
  const flat = FLAT.map(([name, key]) => {
    const button = shell.button({ text: NAMES[name], label: `${NAMES[name]} view`, shortcut: key, pressed: false, onClick: () => look(name) });
    button.dataset.tip = `${NAMES[name]} view`;
    button.dataset.view = name;
    return button;
  });
  const narrow = shell.button({
    text: "View", icon: "box", label: "Choose a view",
    attributes: { "aria-haspopup": "menu", "aria-expanded": "false" },
    onClick: () => shell.menu(narrow, [...CORNERS, ...FLAT.map(([name]) => name)].map((name) => ({
      label: CORNERS.includes(name) ? `3D, ${NAMES[name].toLowerCase()}` : NAMES[name],
      checked: engine.view === name,
      onSelect: () => look(name),
    }))),
  });
  narrow.classList.add("narrow");
  const projection = shell.button({
    icon: "perspective", label: "Orthographic projection", shortcut: "O", pressed: false,
    onClick: () => engine.setProjection(engine.projection === "orthographic" ? "perspective" : "orthographic"),
  });

  const wide = [h("div", { class: "split wide" }, threeD, cornerMenu), ...flat.map((button) => (button.classList.add("wide"), button))];
  const bar = h("nav", { class: "surface view-bar", "aria-label": "Views" }, ...wide, narrow, h("span", { class: "divider", role: "separator" }), projection);
  shell.regions.bottom.append(bar);

  const update = () => {
    const view = engine.view;
    threeD.setAttribute("aria-pressed", String(CORNERS.includes(view)));
    for (const button of flat) button.setAttribute("aria-pressed", String(button.dataset.view === view));
    narrow.querySelector("span").textContent = view ? (CORNERS.includes(view) ? "3D" : NAMES[view]) : "View";
    const flatOn = engine.projection === "orthographic";
    projection.setAttribute("aria-pressed", String(flatOn));
    projection.replaceChildren(shell.icon(flatOn ? "orthographic" : "perspective"));
  };
  engine.on("view", update);
  engine.on("projection", update);
  update();

  shell.shortcuts.add({ key: "0", label: "3D view", run: () => look(corner) });
  for (const [name, key] of FLAT) shell.shortcuts.add({ key, label: `${NAMES[name]} view`, run: () => look(name) });
  shell.shortcuts.add({ key: "o", label: "Switch between perspective and orthographic", run: () => projection.click() });
}
