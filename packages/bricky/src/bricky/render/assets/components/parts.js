// The parts panel: every part in every color the model uses, with how many. Choosing one selects
// those elements. The panel ends with the files the page offers, such as a BrickLink Wanted List.

const STYLE = `
.parts .summary { display: flex; align-items: baseline; justify-content: space-between; margin: 2px 0 10px; }
.parts .summary strong { font-size: 13px; font-weight: 600; }
.parts .field { margin-bottom: 8px; }
.parts ul { list-style: none; margin: 0 -8px; padding: 0; }
.parts li button {
  display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 10px;
  width: 100%; padding: 6px 8px; border: 0; border-radius: var(--radius-control); background: transparent;
  text-align: left; cursor: pointer;
}
.parts li button:hover { background: var(--hover); }
.parts li button[aria-pressed="true"] { background: var(--accent-soft); }
.parts .lot-name { display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.parts .lot-meta { display: block; color: var(--ink-2); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.parts .lot-count { color: var(--ink-2); font-variant-numeric: tabular-nums; }
.parts .none { padding: 16px 0; color: var(--ink-2); text-align: center; }
.parts .downloads { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--line); }
.parts .download { padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; }
.parts .download + .download { margin-top: 8px; }
.parts .download strong { display: block; font-weight: 600; }
.parts .download p { margin: 2px 0 10px; color: var(--ink-2); font-size: 12px; }
.parts .download .row { display: flex; gap: 6px; }`;

export default function parts({ scene, downloads, engine, shell, format, h }) {
  shell.style(STYLE);
  // Lots: elements grouped by part and color, most used first.
  const lots = new Map();
  scene.elements.forEach(([color, , part], i) => {
    const key = `${part}:${color}`;
    if (!lots.has(key)) lots.set(key, { part: scene.parts[part], color: scene.colors[color], elements: [] });
    lots.get(key).elements.push(i);
  });
  const sorted = [...lots.values()].sort((a, b) => b.elements.length - a.elements.length || a.part.name.localeCompare(b.part.name));

  const search = h("input", { type: "search", placeholder: "Search parts and colors", "aria-label": "Search parts and colors", autocomplete: "off" });
  const list = h("ul", { "aria-label": "Parts" });
  const rows = sorted.map((lot) => {
    const button = h(
      "button",
      { type: "button", "aria-pressed": "false", onclick: () => choose(lot) },
      h("span", { class: "swatch", style: `background:${lot.color.rgb}` }),
      h("span", {}, h("span", { class: "lot-name" }, lot.part.name), h("span", { class: "lot-meta" }, `${lot.part.id} · ${lot.color.name}`)),
      h("span", { class: "lot-count" }, `×${format.number(lot.elements.length)}`),
    );
    const text = `${lot.part.name} ${lot.part.id} ${lot.color.name}`.toLowerCase();
    return { lot, button, item: h("li", {}, button), text };
  });
  const none = h("p", { class: "none", hidden: true }, "No part or color matches.");
  list.append(...rows.map((row) => row.item));

  const filter = () => {
    const words = search.value.toLowerCase().split(/\s+/).filter(Boolean);
    let shown = 0;
    for (const row of rows) {
      const match = words.every((word) => row.text.includes(word));
      row.item.hidden = !match;
      shown += match;
    }
    none.hidden = shown > 0;
  };
  search.addEventListener("input", filter);

  const choose = (lot) => {
    const same = engine.selection.size === lot.elements.length && lot.elements.every((i) => engine.selection.has(i));
    engine.select(same ? [] : lot.elements);
  };
  engine.on("selection", () => {
    for (const row of rows) {
      const pressed = engine.selection.size === row.lot.elements.length && row.lot.elements.every((i) => engine.selection.has(i));
      row.button.setAttribute("aria-pressed", String(pressed));
    }
  });

  const total = scene.elements.length;
  const view = h(
    "div",
    { class: "parts" },
    h("div", { class: "summary" }, h("strong", {}, format.count(sorted.length, "lot")), h("span", { class: "quiet numeric" }, format.count(total, "element"))),
    h("label", { class: "field" }, shell.icon("search"), search),
    list,
    none,
    downloads.length ? h("div", { class: "downloads" }, h("p", { class: "section-title" }, "Order the parts"), ...downloads.map((file) => offer(file, shell, h))) : null,
  );
  shell.panel.add({ id: "parts", label: "Parts", icon: "blocks", shortcut: "P", order: 10, view });
}

// One file to download or copy, with how to use it.
function offer(file, shell, h) {
  const save = () => {
    const url = URL.createObjectURL(new Blob([file.text], { type: file.media_type }));
    const link = h("a", { href: url, download: file.file });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    shell.toast(`Saved ${file.file}`);
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(file.text);
      shell.toast("Copied to the clipboard");
    } catch {
      shell.toast("The browser did not allow copying; download the file instead");
    }
  };
  return h(
    "div",
    { class: "download" },
    h("strong", {}, file.title),
    h("p", {}, file.usage),
    h("div", { class: "row" },
      shell.button({ text: "Download", icon: "download", label: `Download ${file.file}`, variant: "small outlined", onClick: save }),
      shell.button({ text: "Copy", icon: "copy", label: "Copy the file's contents", variant: "small outlined", onClick: copy }),
    ),
  );
}
