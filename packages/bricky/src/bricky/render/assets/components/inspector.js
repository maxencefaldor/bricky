// The inspector: point at a part to name it, click to select it, double-click to bring it close,
// and right-click for what to do with it. Shift- or Ctrl-click adds a part to the selection. A card
// says what the selection is and where the build script placed it, with actions to isolate, hide,
// or select every part like it.

const STYLE = `
.hover-label {
  position: absolute; z-index: 4; padding: 4px 8px; border-radius: 6px; pointer-events: none;
  background: var(--surface); color: var(--ink); font-size: 12px; white-space: nowrap;
  border: 1px solid var(--line); box-shadow: var(--shadow); opacity: 0; transition: opacity 120ms var(--ease);
}
.hover-label.shown { opacity: 1; }
.hover-label .quiet { margin-left: 6px; }
.info-card { width: min(392px, calc(100vw - 24px)); padding: 12px 12px 10px 14px; }
.info-card[hidden] { display: none; }
.info-card .head { display: flex; align-items: flex-start; gap: 10px; }
.info-card .swatch { width: 28px; height: 28px; border-radius: 7px; margin-top: 1px; }
.info-card .name { flex: 1; min-width: 0; }
.info-card .name strong { display: block; font-size: 14px; font-weight: 600; line-height: 1.3; overflow-wrap: anywhere; }
.info-card .name span { color: var(--ink-2); font-size: 12px; }
.info-card .head .button { margin: -6px -4px 0 0; }
.info-card dl { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 3px 12px; margin: 10px 0 8px; font-size: 12px; }
.info-card dt { color: var(--ink-2); }
.info-card dd { margin: 0; font-family: var(--mono); font-size: 11.5px; overflow-wrap: anywhere; }
.info-card dl:empty { display: none; }
.info-card dl:empty + .actions { margin-top: 8px; }
.info-card .actions { display: flex; flex-wrap: wrap; gap: 2px; margin: 0 -6px; }
.info-card .actions .button { padding: 0 8px; }
.visibility-pill {
  position: absolute; top: max(var(--gap), env(safe-area-inset-top)); left: 50%; transform: translateX(-50%);
  z-index: 3; display: flex; align-items: center; gap: 8px; padding: 4px 4px 4px 12px; font-size: 12px; white-space: nowrap;
}
.visibility-pill[hidden] { display: none; }
@container stage (max-width: 720px) {
  .visibility-pill { top: auto; bottom: calc(max(var(--gap), env(safe-area-inset-bottom)) + var(--sheet) + var(--rise)); }
  .stage:has(.info-card:not([hidden])) .visibility-pill { display: none; }
  .info-card { width: var(--beside-toolbar); }
  /* Over a phone's sheet the card keeps to the part's name and its actions, as icons. */
  .sheet-open .info-card { padding: 8px 8px 6px 12px; }
  .sheet-open .info-card dl { display: none; }
  .sheet-open .info-card .swatch { width: 22px; height: 22px; }
  .sheet-open .info-card .actions { margin-top: 4px; }
  .sheet-open .info-card .actions .button span { display: none; }
  .sheet-open .info-card .actions .button { width: var(--control); padding: 0; }
}`;

const DRAG = 5; // pixels a pointer may move and still click

export default function inspector({ scene, engine, shell, format, h }) {
  shell.style(STYLE);
  const describe = (i) => {
    const [color, , part, line] = scene.elements[i];
    return { part: scene.parts[part], color: scene.colors[color], line: line >= 0 ? scene.lines[line] : null, uid: scene.uids[i] };
  };
  const sameLot = (i) => {
    const [color, , part] = scene.elements[i];
    const lot = [];
    scene.elements.forEach((element, j) => {
      if (element[0] === color && element[2] === part && !engine.isHidden(j)) lot.push(j);
    });
    return lot;
  };

  // Hover: once the pointer rests, outline the part under it, then name it.
  const label = h("div", { class: "hover-label", "aria-hidden": "true" });
  shell.overlay.append(label);
  let pointer = null;
  let pickTimer = 0;
  let restTimer = 0;
  const canvas = engine.canvas;
  const showLabel = (index, x, y) => {
    if (index === null) return label.classList.remove("shown");
    const { part, color } = describe(index);
    label.replaceChildren(part.name, h("span", { class: "quiet" }, color.name));
    const stage = canvas.getBoundingClientRect();
    const left = Math.min(x - stage.left + 14, stage.width - label.offsetWidth - 8);
    const top = y - stage.top + 18 + label.offsetHeight > stage.height ? y - stage.top - label.offsetHeight - 10 : y - stage.top + 18;
    label.style.left = `${left}px`;
    label.style.top = `${top}px`;
    label.classList.add("shown");
  };
  canvas.addEventListener("pointermove", (event) => {
    if (event.pointerType !== "mouse" || event.buttons) {
      label.classList.remove("shown");
      return;
    }
    pointer = { x: event.clientX, y: event.clientY };
    label.classList.remove("shown");
    clearTimeout(restTimer);
    clearTimeout(pickTimer);
    // Picking renders the scene once: it waits until the pointer rests, never on every move.
    pickTimer = setTimeout(() => {
      if (!pointer) return;
      const index = engine.pick(pointer.x, pointer.y);
      engine.hover(index);
      canvas.style.cursor = index === null ? "" : "pointer";
      const at = pointer;
      restTimer = setTimeout(() => showLabel(index, at.x, at.y), 300);
    }, 60);
  });
  canvas.addEventListener("pointerleave", () => {
    pointer = null;
    clearTimeout(pickTimer);
    clearTimeout(restTimer);
    label.classList.remove("shown");
    engine.hover(null);
  });
  const hideLabel = () => {
    clearTimeout(restTimer);
    label.classList.remove("shown");
  };
  for (const event of ["interact", "selection", "visibility", "section", "projection", "view"]) engine.on(event, hideLabel);
  shell.on("panel", hideLabel);

  // A click selects, a double-click brings the part close, and a right-click opens the actions:
  // each only when one pointer pressed and barely moved, so orbiting, panning and pinching never
  // select anything.
  let down = null;
  let pressed = 0;
  let lastClick = 0;
  canvas.addEventListener("contextmenu", (event) => event.preventDefault());
  canvas.addEventListener("pointerdown", (event) => {
    pressed += 1;
    down = event.isPrimary && pressed === 1 ? { x: event.clientX, y: event.clientY, button: event.button } : null;
  });
  canvas.addEventListener("pointercancel", () => {
    pressed = Math.max(0, pressed - 1);
    down = null;
  });
  canvas.addEventListener("pointerup", (event) => {
    pressed = Math.max(0, pressed - 1);
    const start = down;
    down = null;
    if (!start || !event.isPrimary || Math.hypot(event.clientX - start.x, event.clientY - start.y) > DRAG) return;
    const index = engine.pick(event.clientX, event.clientY);
    if (start.button === 2) return openActions(index, event);
    if (start.button !== 0) return;
    const now = performance.now();
    if (now - lastClick < 320) {
      lastClick = 0;
      if (index === null) engine.fit();
      else engine.focus([index]);
      return;
    }
    lastClick = now;
    if (event.shiftKey || event.ctrlKey || event.metaKey) {
      if (index === null) return;
      const chosen = new Set(engine.selection);
      if (chosen.has(index)) chosen.delete(index);
      else chosen.add(index);
      engine.select([...chosen]);
      return;
    }
    engine.select(index === null ? [] : [index]);
  });

  // The actions at the pointer: on the part right-clicked, which joins the selection, or on the
  // whole model.
  const openActions = (index, event) => {
    if (index !== null && !engine.selection.has(index)) engine.select([index]);
    const chosen = engine.selection.size > 0;
    const items = [];
    if (chosen) {
      items.push(
        { label: engine.isolation ? "Show all" : "Isolate", icon: "crosshair", hint: "I", onSelect: toggleIsolation },
        { label: "Hide", icon: "eye-off", hint: "H", onSelect: hideSelection },
        { label: "Select all alike", icon: "blocks", onSelect: selectAlike },
        { label: "Focus", icon: "focus", onSelect: () => engine.focus([...engine.selection]) },
      );
    }
    const away = engine.isolation || engine.hiddenCount();
    if (away && !(chosen && engine.isolation)) items.push({ label: "Show all", icon: "eye", onSelect: () => engine.showAll() });
    if (!chosen) items.push({ label: "Fit to view", icon: "focus", hint: "F", onSelect: () => engine.fit() });
    shell.menu({ x: event.clientX, y: event.clientY }, items);
  };

  // The card describes the selection: one part, or many alike.
  const swatch = h("span", { class: "swatch" });
  const name = h("strong");
  const meta = h("span");
  const details = h("dl");
  const isolateButton = shell.button({ text: "Isolate", icon: "crosshair", label: "Isolate", shortcut: "I", variant: "small", onClick: () => toggleIsolation() });
  const hideButton = shell.button({ text: "Hide", icon: "eye-off", label: "Hide", shortcut: "H", variant: "small", onClick: () => hideSelection() });
  const sameButton = shell.button({ text: "Select all alike", icon: "blocks", label: "Select all alike", variant: "small", onClick: () => selectAlike() });
  const focusButton = shell.button({ text: "Focus", icon: "focus", label: "Focus", variant: "small", onClick: () => engine.focus([...engine.selection]) });
  const card = h(
    "section",
    { class: "surface info-card", hidden: true, "aria-label": "Selection" },
    h("div", { class: "head" }, swatch, h("div", { class: "name" }, name, meta), shell.button({ icon: "x", label: "Clear the selection", shortcut: "Esc", onClick: () => engine.select([]) })),
    details,
    h("div", { class: "actions" }, isolateButton, hideButton, sameButton, focusButton),
  );
  shell.regions.bottomLeft.prepend(card);

  const update = () => {
    const chosen = [...engine.selection];
    card.hidden = chosen.length === 0;
    if (!chosen.length) return;
    const first = describe(chosen[0]);
    const alike = chosen.every((i) => scene.elements[i][0] === scene.elements[chosen[0]][0] && scene.elements[i][2] === scene.elements[chosen[0]][2]);
    swatch.style.background = alike ? first.color.rgb : "conic-gradient(#d0d7de 0 25%, #8c959f 0 50%, #d0d7de 0 75%, #8c959f 0)";
    if (chosen.length === 1) {
      name.textContent = first.part.name;
      meta.textContent = `${first.part.id} · ${first.color.name}`;
      details.replaceChildren(
        h("dt", {}, "Element"), h("dd", {}, first.uid),
        ...(first.line ? [h("dt", {}, "Placed by"), h("dd", {}, first.line)] : []),
      );
    } else {
      name.textContent = alike ? `${format.number(chosen.length)} × ${first.part.name}` : format.count(chosen.length, "element");
      meta.textContent = alike ? `${first.part.id} · ${first.color.name}` : "Several parts";
      details.replaceChildren();
    }
    sameButton.hidden = !alike || chosen.length >= sameLot(chosen[0]).length;
    isolateButton.querySelector("span").textContent = engine.isolation ? "Show all" : "Isolate";
    shell.announce(`Selected ${name.textContent}, ${meta.textContent}`);
  };
  engine.on("selection", update);
  engine.on("visibility", update);

  const toggleIsolation = () => {
    if (engine.isolation) return engine.showAll();
    if (engine.selection.size) engine.isolate([...engine.selection]);
  };
  const hideSelection = () => {
    if (!engine.selection.size) return;
    const chosen = [...engine.selection];
    engine.select([]);
    engine.hide(chosen);
  };
  const selectAlike = () => {
    if (engine.selection.size) engine.select(sameLot([...engine.selection][0]));
  };

  // A pill says when parts are isolated or hidden, and brings them all back.
  const pillText = h("span");
  const pill = h("div", { class: "surface visibility-pill", hidden: true, role: "status" }, pillText, shell.button({ text: "Show all", variant: "small", label: "Show all", onClick: () => engine.showAll() }));
  shell.stage.append(pill);
  engine.on("visibility", () => {
    const hidden = engine.hiddenCount();
    const parts = [];
    if (engine.isolation) parts.push(`${format.count(engine.isolation.size, "element")} isolated`);
    if (hidden) parts.push(`${format.number(hidden)} hidden`);
    pill.hidden = parts.length === 0;
    pillText.textContent = parts.join(" · ");
  });

  shell.shortcuts.add({ key: "i", label: "Isolate the selection, or show all", group: "Selection", run: toggleIsolation });
  shell.shortcuts.add({ key: "h", label: "Hide the selection", group: "Selection", run: hideSelection });
  shell.shortcuts.describe({ key: "Esc", label: "Clear the selection, then show all", group: "Selection" });
  shell.shortcuts.escape(() => {
    if (engine.isolation || engine.hiddenCount()) {
      engine.showAll();
      return true;
    }
    return false;
  });
  shell.shortcuts.escape(() => {
    if (!engine.selection.size) return false;
    engine.select([]);
    return true;
  });
}
