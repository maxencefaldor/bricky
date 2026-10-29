// The shell lays out the viewer around the stage, the 3D view, and gives components one way to add
// themselves: toolbar buttons, panel views, menus, dialogs, keyboard shortcuts, tooltips, toasts
// and announcements for screen readers. Components never reach into each other's markup.

import { icon } from "bricky/app/icons.js";

// Create an element with attributes and children. Attributes starting with "on" add listeners.
export function h(tag, attributes = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith("on") && typeof value === "function") element.addEventListener(key.slice(2), value);
    else if (key === "class") element.className = value;
    else element.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === undefined || child === null || child === false) continue;
    element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return element;
}

const TOOLBAR_GROUPS = ["panels", "tools"];

export function createShell(root, { heading }) {
  const listeners = new Map();
  const emit = (event, value) => (listeners.get(event) ?? []).forEach((listener) => listener(value));
  const on = (event, listener) => {
    listeners.set(event, [...(listeners.get(event) ?? []), listener]);
    return () => listeners.set(event, listeners.get(event).filter((other) => other !== listener));
  };

  const regions = {
    topLeft: h("div", { class: "region top-left" }),
    topRight: h("div", { class: "region top-right" }),
    bottom: h("div", { class: "region bottom" }),
    bottomLeft: h("div", { class: "region bottom-left" }),
    bottomRight: h("div", { class: "region bottom-right" }),
  };
  const overlay = h("div", { class: "overlay" });
  const toastElement = h("div", { class: "toast", role: "status" });
  const stage = h("main", { class: "stage", "aria-label": `3D view of ${heading}` }, overlay, ...Object.values(regions), toastElement);
  const live = h("div", { class: "sr-only", "aria-live": "polite" });
  const tooltip = h("div", { class: "tooltip", role: "tooltip" });
  root.append(stage, live, tooltip);

  // Styles: each component adds its own, once.
  const styled = new Set();
  const style = (css) => {
    if (styled.has(css)) return;
    styled.add(css);
    document.head.append(h("style", {}, css));
  };
  style(SHELL_STYLE);

  // Tooltips name a control and its shortcut, after a short hover or on keyboard focus.
  let tipTimer = 0;
  const showTip = (target) => {
    const label = target.dataset.tip;
    if (!label) return;
    tooltip.replaceChildren(label, ...(target.dataset.shortcut ? [h("kbd", {}, target.dataset.shortcut)] : []));
    const box = target.getBoundingClientRect();
    tooltip.classList.add("shown");
    const width = tooltip.offsetWidth, height = tooltip.offsetHeight;
    const below = box.bottom + 8 + height < window.innerHeight;
    let left = box.left + box.width / 2 - width / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${below ? box.bottom + 8 : box.top - 8 - height}px`;
  };
  const hideTip = () => {
    clearTimeout(tipTimer);
    tooltip.classList.remove("shown");
  };
  root.addEventListener("pointerover", (event) => {
    const target = event.target.closest?.("[data-tip]");
    hideTip();
    if (target && event.pointerType === "mouse") tipTimer = setTimeout(() => showTip(target), 450);
  });
  root.addEventListener("pointerdown", hideTip);
  root.addEventListener("focusin", (event) => {
    const target = event.target.closest?.("[data-tip]");
    hideTip();
    if (target?.matches(":focus-visible")) showTip(target);
  });
  root.addEventListener("focusout", hideTip);

  // Buttons: an icon, a text label, or both, with a tooltip naming the action and its shortcut.
  const button = ({ icon: name, label, text, shortcut, variant = "", pressed, onClick, attributes = {} }) => {
    const element = h(
      "button",
      {
        type: "button",
        class: `button ${text ? "" : "icon-only"} ${variant}`.trim(),
        "aria-label": text ? undefined : label,
        "data-tip": text ? undefined : label,
        "data-shortcut": shortcut,
        "aria-pressed": pressed === undefined ? undefined : String(pressed),
        "aria-keyshortcuts": shortcut,
        onclick: onClick,
        ...attributes,
      },
      name ? icon(name) : null,
      text ? h("span", {}, text) : null,
    );
    return element;
  };

  // The toolbar, at the top right: panel toggles, then tools.
  const toolbarElement = h("div", { class: "surface toolbar", role: "toolbar", "aria-label": "Viewer tools" });
  const toolbarItems = [];
  const layoutToolbar = () => {
    const children = [];
    TOOLBAR_GROUPS.forEach((group) => {
      const items = toolbarItems.filter((item) => item.group === group).sort((a, b) => a.order - b.order);
      if (items.length && children.length) children.push(h("span", { class: "divider", role: "separator" }));
      children.push(...items.map((item) => item.element));
    });
    toolbarElement.replaceChildren(...children);
    if (children.length && !toolbarElement.isConnected) regions.topRight.append(toolbarElement);
  };
  const toolbar = {
    add({ group = "tools", order = 50, ...options }) {
      const element = button(options);
      toolbarItems.push({ group, order, element });
      layoutToolbar();
      return element;
    },
  };

  // The panel: one view per tab, docked beside the stage, or a sheet on phones.
  const tabs = h("div", { class: "panel-tabs", role: "tablist", "aria-label": "Panels" });
  const body = h("div", { class: "panel-body" });
  const panelElement = h(
    "aside",
    { class: "panel", hidden: true, "aria-label": "Panel" },
    h("div", { class: "panel-handle", "aria-hidden": "true" }),
    h("div", { class: "panel-header" }, tabs, button({ icon: "x", label: "Close panel", shortcut: "Esc", onClick: () => panel.close() })),
    body,
  );
  root.append(panelElement);
  const views = new Map();
  let current = null;
  const panel = {
    add({ id, label, icon: name, shortcut, order = 50, view, onOpen }) {
      const tab = h("button", {
        type: "button", class: "button", role: "tab", id: `tab-${id}`, "aria-selected": "false",
        "aria-controls": `view-${id}`, onclick: () => panel.open(id),
      }, icon(name), h("span", {}, label));
      const container = h("section", { class: "panel-view", role: "tabpanel", id: `view-${id}`, "aria-labelledby": `tab-${id}`, hidden: true }, view);
      const toggle = toolbar.add({ group: "panels", order, icon: name, label, shortcut, pressed: false, onClick: () => panel.toggle(id) });
      views.set(id, { tab, container, toggle, order, onOpen });
      const sorted = [...views.entries()].sort((a, b) => a[1].order - b[1].order);
      tabs.replaceChildren(...sorted.map(([, item]) => item.tab));
      body.replaceChildren(...sorted.map(([, item]) => item.container));
      if (shortcut) shortcuts.add({ key: shortcut, label: `Show or hide ${label.toLowerCase()}`, group: "Panels", run: () => panel.toggle(id) });
      return { view: container, toggle };
    },
    has: (id) => views.has(id),
    isOpen: (id) => current === id,
    open(id) {
      if (!views.has(id)) return;
      current = id;
      panelElement.hidden = false;
      for (const [key, item] of views) {
        const selected = key === id;
        item.tab.setAttribute("aria-selected", String(selected));
        item.container.hidden = !selected;
        item.toggle.setAttribute("aria-pressed", String(selected));
      }
      views.get(id).onOpen?.();
      emit("panel", id);
    },
    close() {
      if (current === null) return;
      current = null;
      panelElement.hidden = true;
      for (const item of views.values()) item.toggle.setAttribute("aria-pressed", "false");
      emit("panel", null);
    },
    toggle(id) {
      if (current === id) panel.close();
      else panel.open(id);
    },
  };

  // Menus: a list of choices under a button, closed by a choice, a click elsewhere or Escape.
  let openMenu = null;
  const closeMenu = () => {
    if (!openMenu) return;
    openMenu.element.remove();
    openMenu.anchor.setAttribute("aria-expanded", "false");
    openMenu = null;
  };
  const menu = (anchor, items) => {
    if (openMenu?.anchor === anchor) return closeMenu();
    closeMenu();
    const element = h("div", { class: "menu", role: "menu" }, items.map((item) => h(
      "button",
      {
        type: "button", class: "button", role: item.checked === undefined ? "menuitem" : "menuitemradio",
        "aria-checked": item.checked === undefined ? undefined : String(item.checked),
        onclick: () => { closeMenu(); item.onSelect(); },
      },
      item.icon ? icon(item.icon) : null,
      h("span", {}, item.label),
      item.hint ? h("span", { class: "hint" }, item.hint) : null,
    )));
    root.append(element);
    const box = anchor.getBoundingClientRect();
    const height = element.offsetHeight, width = element.offsetWidth;
    const above = box.top - 8 - height > 0 && box.bottom + 8 + height > window.innerHeight;
    element.style.top = `${above ? box.top - 8 - height : box.bottom + 8}px`;
    element.style.left = `${Math.max(8, Math.min(box.left, window.innerWidth - width - 8))}px`;
    anchor.setAttribute("aria-expanded", "true");
    openMenu = { element, anchor };
    element.querySelector("[aria-checked='true']")?.focus() ?? element.querySelector("button")?.focus();
  };
  root.addEventListener("pointerdown", (event) => {
    if (openMenu && !openMenu.element.contains(event.target) && !openMenu.anchor.contains(event.target)) closeMenu();
  });
  root.addEventListener("keydown", (event) => {
    if (!openMenu || !openMenu.element.contains(event.target)) return;
    const items = [...openMenu.element.querySelectorAll("button")];
    const index = items.indexOf(event.target);
    if (event.key === "ArrowDown") items[(index + 1) % items.length].focus();
    else if (event.key === "ArrowUp") items[(index - 1 + items.length) % items.length].focus();
    else if (event.key === "Escape") { const anchor = openMenu.anchor; closeMenu(); anchor.focus(); }
    else return;
    event.preventDefault();
    event.stopPropagation();
  });

  // Dialogs: modal, closed by their button, Escape, or a click on the backdrop.
  const dialog = ({ title, content }) => {
    const element = h(
      "dialog",
      { class: "dialog", "aria-label": title },
      h("div", { class: "dialog-header" }, h("h2", {}, title), button({ icon: "x", label: "Close", onClick: () => element.close() })),
      h("div", { class: "dialog-body" }, content),
    );
    element.addEventListener("click", (event) => {
      if (event.target === element) element.close();
    });
    root.append(element);
    return { open: () => element.showModal(), close: () => element.close(), element };
  };

  // Keyboard shortcuts: single keys, ignored while typing or with a modifier held. Escape undoes
  // the latest thing that asked for it: the handlers added last run first, until one handles it.
  const shortcutList = [];
  const escapes = [];
  const shortcuts = {
    add({ key, label, group = "View", run }) {
      shortcutList.push({ key, label, group, run });
    },
    describe({ key, label, group = "View" }) {
      shortcutList.push({ key, label, group });
    },
    escape(handler) {
      escapes.push(handler);
    },
    list: () => shortcutList.slice(),
  };
  window.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.target.closest?.("input, textarea, select, dialog[open]")) return;
    if (event.key === "Escape") {
      if (escapes.slice().reverse().some((handler) => handler())) event.preventDefault();
      return;
    }
    const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
    const match = shortcutList.find((item) => item.run && item.key.toLowerCase() === key.toLowerCase());
    if (!match) return;
    event.preventDefault();
    hideTip();
    match.run(event);
  });
  shortcuts.escape(() => {
    if (current === null) return false;
    panel.close();
    return true;
  });

  let toastTimer = 0;
  const toast = (text) => {
    toastElement.textContent = text;
    toastElement.classList.add("shown");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastElement.classList.remove("shown"), 2200);
  };
  const announce = (text) => {
    live.textContent = "";
    requestAnimationFrame(() => (live.textContent = text));
  };

  return { root, stage, overlay, regions, h, icon, style, button, toolbar, panel, menu, dialog, shortcuts, toast, announce, on };
}

const SHELL_STYLE = `
@media (max-width: 720px) {
  .region.top-right .toolbar { flex-direction: column; }
  .region.top-right .toolbar .divider { width: 20px; height: 1px; margin: 4px 0; }
}`;
