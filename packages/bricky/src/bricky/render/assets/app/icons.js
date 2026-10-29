// Icons from Lucide (https://lucide.dev), ISC license: Copyright (c) for portions of Lucide are
// held by Cole Bemis 2013-2022 as part of Feather (MIT); all other copyright (c) for Lucide is held
// by Lucide Contributors 2022. Permission to use, copy, modify, and/or distribute this software for
// any purpose with or without fee is hereby granted, provided that the above copyright notice and
// this permission notice appear in all copies. THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR
// DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE.
//
// The icons "perspective" and "orthographic" are bricky's own, drawn in Lucide's style.

const PATHS = {
  "blocks": '<rect width="7" height="7" x="14" y="3" rx="1"/> <path d="M10 21V8a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-5a1 1 0 0 0-1-1H3"/>',
  "list-checks": '<path d="m3 17 2 2 4-4"/> <path d="m3 7 2 2 4-4"/> <path d="M13 6h8"/> <path d="M13 12h8"/> <path d="M13 18h8"/>',
  "scissors": '<circle cx="6" cy="6" r="3"/> <path d="M8.12 8.12 12 12"/> <path d="M20 4 8.12 15.88"/> <circle cx="6" cy="18" r="3"/> <path d="M14.8 14.8 20 20"/>',
  "scan": '<path d="M3 7V5a2 2 0 0 1 2-2h2"/> <path d="M17 3h2a2 2 0 0 1 2 2v2"/> <path d="M21 17v2a2 2 0 0 1-2 2h-2"/> <path d="M7 21H5a2 2 0 0 1-2-2v-2"/>',
  "camera": '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/> <circle cx="12" cy="13" r="3"/>',
  "maximize": '<path d="M8 3H5a2 2 0 0 0-2 2v3"/> <path d="M21 8V5a2 2 0 0 0-2-2h-3"/> <path d="M3 16v3a2 2 0 0 0 2 2h3"/> <path d="M16 21h3a2 2 0 0 0 2-2v-3"/>',
  "minimize": '<path d="M8 3v3a2 2 0 0 1-2 2H3"/> <path d="M21 8h-3a2 2 0 0 1-2-2V3"/> <path d="M3 16h3a2 2 0 0 1 2 2v3"/> <path d="M16 21v-3a2 2 0 0 1 2-2h3"/>',
  "circle-help": '<circle cx="12" cy="12" r="10"/> <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/> <path d="M12 17h.01"/>',
  "x": '<path d="M18 6 6 18"/> <path d="m6 6 12 12"/>',
  "chevron-down": '<path d="m6 9 6 6 6-6"/>',
  "chevron-left": '<path d="m15 18-6-6 6-6"/>',
  "chevron-right": '<path d="m9 18 6-6-6-6"/>',
  "chevron-first": '<path d="m17 18-6-6 6-6"/> <path d="M7 6v12"/>',
  "chevron-last": '<path d="m7 18 6-6-6-6"/> <path d="M17 6v12"/>',
  "book-open": '<path d="M12 7v14"/> <path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>',
  "eye": '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/> <circle cx="12" cy="12" r="3"/>',
  "eye-off": '<path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/> <path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/> <path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/> <path d="m2 2 20 20"/>',
  "crosshair": '<circle cx="12" cy="12" r="10"/> <line x1="22" x2="18" y1="12" y2="12"/> <line x1="6" x2="2" y1="12" y2="12"/> <line x1="12" x2="12" y1="6" y2="2"/> <line x1="12" x2="12" y1="22" y2="18"/>',
  "focus": '<circle cx="12" cy="12" r="3"/> <path d="M3 7V5a2 2 0 0 1 2-2h2"/> <path d="M17 3h2a2 2 0 0 1 2 2v2"/> <path d="M21 17v2a2 2 0 0 1-2 2h-2"/> <path d="M7 21H5a2 2 0 0 1-2-2v-2"/>',
  "box": '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/> <path d="m3.3 7 8.7 5 8.7-5"/> <path d="M12 22V12"/>',
  "search": '<circle cx="11" cy="11" r="8"/> <path d="m21 21-4.3-4.3"/>',
  "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/> <polyline points="7 10 12 15 17 10"/> <line x1="12" x2="12" y1="15" y2="3"/>',
  "copy": '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/> <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  "check": '<path d="M20 6 9 17l-5-5"/>',
  "play": '<polygon points="6 3 20 12 6 21 6 3"/>',
  "pause": '<rect x="14" y="4" width="4" height="16" rx="1"/> <rect x="6" y="4" width="4" height="16" rx="1"/>',
  "rotate-ccw": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/> <path d="M3 3v5h5"/>',
  "triangle-alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/> <path d="M12 9v4"/> <path d="M12 17h.01"/>',
  "circle-x": '<circle cx="12" cy="12" r="10"/> <path d="m15 9-6 6"/> <path d="m9 9 6 6"/>',
  "circle-check": '<circle cx="12" cy="12" r="10"/> <path d="m9 12 2 2 4-4"/>',
  "info": '<circle cx="12" cy="12" r="10"/> <path d="M12 16v-4"/> <path d="M12 8h.01"/>',
  "perspective": '<path d="M8 4h8l5 16H3z"/> <path d="M12 4v16"/> <path d="M5.5 12h13"/>',
  "orthographic": '<rect x="3" y="4" width="18" height="16" rx="1"/> <path d="M12 4v16"/> <path d="M3 12h18"/>',
};

// Return an icon as an SVG element, 16 pixels square, drawn in the current text color.
export function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = PATHS[name] ?? "";
  return svg;
}
