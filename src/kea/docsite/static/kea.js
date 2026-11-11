/* The parts of a page of the graph after its text (docsite/pages.py tab_strip, comments.inject):
 *  - tabs hanging under the separator: one panel at a time; #tab=<key> in the address opens a tab, and a link to
 *    something inside a closed panel (a comment, #fb-…) opens that panel first;
 *  - long tables of pages (table.nodes in a panel) in pages of data-rows rows (12), with a pager under them;
 *  - the experiment's list of its pages: a filter per kind (.kind-filter chips, rows carry data-kind).
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
