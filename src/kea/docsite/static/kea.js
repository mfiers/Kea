/* The parts of a page of the graph after its text (docsite/pages.py tab_strip, comments.inject):
 *  - tabs hanging under the separator: one panel at a time; #tab=<key> in the address opens a tab, and a link to
 *    something inside a closed panel (a comment, #fb-…) opens that panel first;
 *  - long tables of pages (table.nodes in a panel) in pages of data-rows rows (12), with a pager under them;
 *  - the experiment's list of its pages: a filter per kind (.kind-filter chips, rows carry data-kind);
 *  - keyboard shortcuts outside text fields (? lists them).
 * Without this script every panel shows, and every row (render.py CSS: .js only).
 */
(function () {
  "use strict";
  const ROWS = 12;

  function choose(strip, key, focus) {
    const buttons = [...strip.querySelectorAll(".sep-tab:not([hidden])")];
    const button = buttons.find((item) => item.dataset.tab === key) || buttons[0];
    if (!button) return;
    const panels = strip.closest(".tab-sep").nextElementSibling;
    for (const item of strip.querySelectorAll(".sep-tab")) {
      item.classList.toggle("on", item === button);
      item.setAttribute("aria-selected", String(item === button));
      item.tabIndex = item === button ? 0 : -1;
    }
    for (const panel of panels.querySelectorAll(":scope > .tab-panel")) {
      panel.classList.toggle("on", panel.dataset.tab === button.dataset.tab);
    }
    if (focus) button.focus();
  }

  /* #tab=changes opens that tab; #<id> inside a closed panel opens the panel holding it */
  function followHash() {
    const hash = decodeURIComponent(location.hash.slice(1));
    if (!hash) return;
    const wanted = hash.match(/^tab=([\w-]+)$/);
    if (wanted) {
      for (const strip of document.querySelectorAll(".sep-tabs")) choose(strip, wanted[1]);
      return;
    }
    const target = document.getElementById(hash);
    const panel = target && target.closest(".tab-panel");
    if (panel && !panel.classList.contains("on")) {
      choose(panel.parentElement.previousElementSibling.querySelector(".sep-tabs"), panel.dataset.tab);
      target.scrollIntoView({ block: "center" });
    }
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest && event.target.closest("button.sep-tab");
    if (!button) return;
    choose(button.parentElement, button.dataset.tab);
    const first = button.parentElement.querySelector(".sep-tab:not([hidden])");
    const hash = button === first ? "" : "#tab=" + button.dataset.tab;
    if (!location.hash || /^#tab=/.test(location.hash)) {   // never replace a link to a comment
      history.replaceState(null, "", hash || location.pathname + location.search);
    }
  });
  document.addEventListener("keydown", (event) => {
    const button = event.target.closest && event.target.closest("button.sep-tab");
    if (!button || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
    const buttons = [...button.parentElement.querySelectorAll(".sep-tab:not([hidden])")];
    const next = buttons[(buttons.indexOf(button) + (event.key === "ArrowRight" ? 1 : buttons.length - 1)) % buttons.length];
    choose(button.parentElement, next.dataset.tab, true);
    event.preventDefault();
  });
  /* feedback.js hides the build-time copy of the comments when the comment server answers (the live ones are in
     the Comments panel): then the Comments tab goes too */
  /* Keyboard shortcuts, outside a text field and without Ctrl, Alt or ⌘ (render.CSS .kea-keys). g opens a menu of
     places (g then m: Map); a few single keys act on this page; ? lists them all. They only go somewhere or open
     something: no key signs, harvests or implements. Entries that lead nowhere on this page are greyed out. */
  const topLink = (ending) => () => document.querySelector(`.topbar a[href$='${ending}']`);
  const visible = (selector) => [...document.querySelectorAll(selector)].find((item) => item.offsetParent !== null);
  const GO = [
    ["s", "Start, the site's front page", () => document.querySelector(".topbar a.home")],
    ["e", "The experiment's front page", topLink("/home.html")],
    ["u", "Up: the page above this one", () => { const links = document.querySelectorAll("nav.crumbs a"); return links[links.length - 1]; }],
    ["m", "Map", topLink("map.html")],
    ["o", "Objects: every page by type", topLink("objects.html")],
    ["r", "Progress: what waits for whom", topLink("progress.html")],
    ["p", "Plan of the current round", topLink("plan.html")],
    ["c", "Current comments", topLink("comments.html")],
    ["h", "History: the review cycles", topLink("history.html")],
    ["d", "Data files", topLink("data.html")],
    ["k", "Code", topLink("code/index.html")],
    ["?", "Help", topLink("help.html")],
  ];
  function tabStep(step) {
    const strip = document.querySelector(".sep-tabs");
    if (!strip) return null;
    const buttons = [...strip.querySelectorAll(".sep-tab:not([hidden])")];
    const here = buttons.findIndex((item) => item.classList.contains("on"));
    return typeof step === "number" ? buttons[(here + step + buttons.length) % buttons.length] : buttons[step.index] || null;
  }
  const PAGE_KEYS = [
    ["g", "Go to … (a menu of places)", () => true],
    ["c", "Comments on this page (open or close)", () => visible(".fb-d-comment")],
    ["n", "Next page to sign (opens it; signing stays a click)", () => visible(".fb-sn-next") || visible(".fb-d-tosign")],
    ["N", "Previous page to sign", () => visible(".fb-sn-prev")],
    ["]", "Next tab below the text", () => tabStep(1)],
    ["[", "Previous tab", () => tabStep(-1)],
    ["1–9", "Tab 1 to 9", () => tabStep({ index: 0 })],
    ["?", "This list", () => true],
  ];
  function closeKeys() { const box = document.getElementById("kea-keys"); if (box) box.remove(); }
  function keyBox(kind, title, sections, note) {
    const was = document.getElementById("kea-keys");
    closeKeys();
    if (was && was.dataset.kind === kind) return;
    const box = document.createElement("div");
    box.id = "kea-keys";
    box.dataset.kind = kind;
    box.className = "kea-keys not-annotatable kea-keys-" + kind;
    box.setAttribute("role", "dialog");
    const esc = (text) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;");
    let html = `<button type='button' class='kea-keys-close' title='Close (Esc)'>×</button><h2>${title}</h2>`
      + (note ? `<p>${note}</p>` : "");
    for (const [head, rows] of sections) {
      html += (head ? `<h3>${head}</h3>` : "") + "<table>";
      for (const [key, text, find] of rows) {
        const target = find();
        const href = target && target.href ? ` data-href='${esc(target.href)}'` : "";
        html += `<tr${target ? href : " class='off' title='Not on this page'"}><td><kbd>${esc(key)}</kbd></td><td>${text}</td></tr>`;
      }
      html += "</table>";
    }
    box.innerHTML = html;
    box.querySelector(".kea-keys-close").addEventListener("click", closeKeys);
    box.addEventListener("click", (event) => {
      const row = event.target.closest("tr[data-href]");
      if (row) location.href = row.dataset.href;
    });
    document.body.append(box);
  }
  const goMenu = () => keyBox("go", "Go to …", [["", GO]], "Press a key, or Esc.");
  const keyList = () => keyBox("all", "Keyboard shortcuts", [["On any page", PAGE_KEYS], ["After g", GO]],
    "Outside a text field. In a comment: Ctrl+Enter (⌘+Enter) sends, Esc cancels.");
  document.addEventListener("keydown", (event) => {
    const open = document.getElementById("kea-keys");
    if (event.key === "Escape") { if (open) { closeKeys(); event.preventDefault(); } return; }
    if (event.ctrlKey || event.metaKey || event.altKey || event.defaultPrevented) return;
    const target = event.target;
    if (target instanceof Element && target.closest("input, textarea, select, [contenteditable=''], [contenteditable='true']")) return;
    if (["Shift", "CapsLock"].includes(event.key)) return;
    if (open && open.dataset.kind === "go") {               // the second key after g
      closeKeys();
      event.preventDefault();
      const entry = GO.find(([key]) => key === event.key);
      const link = entry && entry[2]();
      if (link) location.href = link.href;
      return;
    }
    let hit = null;
    if (event.key === "g") { goMenu(); hit = true; }
    else if (event.key === "?") { keyList(); hit = true; }
    else if (/^[1-9]$/.test(event.key)) hit = tabStep({ index: Number(event.key) - 1 });
    else if (event.key === "]" || event.key === "[") hit = tabStep(event.key === "]" ? 1 : -1);
    else {
      const entry = PAGE_KEYS.find(([key]) => key === event.key && "cnN".includes(key));
      hit = entry && entry[2]();
    }
    if (hit && hit !== true) { hit.click(); if (hit.classList.contains("sep-tab")) hit.scrollIntoView({ block: "nearest" }); }
    if (hit) event.preventDefault();
  });

  window.keaDropTab = function (key) {
    for (const button of document.querySelectorAll(`.sep-tab[data-tab='${key}']`)) {
      const strip = button.parentElement, open = button.classList.contains("on");
      button.hidden = true;
      if (open) choose(strip, "");
    }
  };

  function pager(table, size, kindOf) {
    const rows = [...table.rows].filter((row) => !row.querySelector("th"));
    const bar = document.createElement("div");
    bar.className = "obj-pager";
    table.after(bar);
    let page = 0;
    function draw() {
      const kind = kindOf();
      const shown = rows.filter((row) => !kind || row.dataset.kind === kind);
      const pages = Math.max(1, Math.ceil(shown.length / size));
      page = Math.min(page, pages - 1);
      for (const row of rows) row.classList.add("pg-off");
      shown.slice(page * size, (page + 1) * size).forEach((row) => row.classList.remove("pg-off"));
      bar.replaceChildren();
      if (pages < 2) return;
      const button = (label, to, disabled) => {
        const item = document.createElement("button");
        item.type = "button"; item.textContent = label; item.disabled = disabled;
        item.onclick = () => { page = to; draw(); };
        return item;
      };
      const where = document.createElement("span");
      where.textContent = `${page * size + 1}–${Math.min((page + 1) * size, shown.length)} of ${shown.length}`;
      bar.append(button("‹ previous", page - 1, page === 0), where, button("next ›", page + 1, page === pages - 1));
    }
    draw();
    return (reset) => { if (reset) page = 0; draw(); };
  }

  function start() {
    for (const strip of document.querySelectorAll(".sep-tabs")) {
      for (const button of strip.querySelectorAll(".sep-tab")) button.tabIndex = button.classList.contains("on") ? 0 : -1;
    }
    for (const holder of document.querySelectorAll(".paged")) {     // the experiment's pages, with the kind filter
      const table = holder.querySelector("table.nodes");
      const chips = holder.previousElementSibling && holder.previousElementSibling.classList.contains("kind-filter")
        ? holder.previousElementSibling : null;
      let kind = "";
      const redraw = pager(table, Number(holder.dataset.rows) || ROWS, () => kind);
      if (chips) {
        chips.addEventListener("click", (event) => {
          const chip = event.target.closest("button.obj-chip");
          if (!chip) return;
          kind = chip.dataset.kind;
          for (const item of chips.querySelectorAll(".obj-chip")) item.classList.toggle("on", item === chip);
          redraw(true);
        });
      }
    }
    for (const table of document.querySelectorAll(".tab-panel table.nodes")) {   // any other long list of pages
      if (!table.closest(".paged") && table.rows.length > ROWS + 3) pager(table, ROWS, () => "");
    }
    followHash();
  }
  window.addEventListener("hashchange", followHash);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
