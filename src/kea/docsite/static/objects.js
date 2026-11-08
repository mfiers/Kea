/* The Objects page (<experiment>/objects.html): every page of an experiment in one table that stays usable with
 * thousands of pages: search (number, title, summary), subsets by type and by status, sorting by column, and pages
 * of 50 rows. The rows come as JSON in <script id='objects-data'> (written by docsite/pages.py objects_page); the
 * state lives in the address after '#' (e.g. #type=hypothesis&status=open&q=gate&page=2), so a filtered view can be
 * linked and the back button works.
 */
(function () {
  "use strict";
  const data = JSON.parse(document.getElementById("objects-data").textContent);
  const rows = data.rows;
  const root = document.getElementById("objects");
  const PAGE_SIZE = 50;
  const esc = text => String(text).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const natural = text => String(text).replace(/\d+/g, digits => digits.padStart(8, "0"));
  for (const row of rows) row.search = (row.n + " " + row.t + " " + row.s + " " + row.id).toLowerCase();

  let state = { q: "", types: new Set(), statuses: new Set(), page: 1, sort: "type", desc: false };
  function readHash() {
    const params = new URLSearchParams(location.hash.slice(1));
    const single = location.hash.slice(1);
    if (single && !single.includes("=") && data.types.some(type => type.key === single)) params.set("type", single);
    state.q = params.get("q") || "";
    state.types = new Set((params.get("type") || "").split(",").filter(Boolean));
    state.statuses = new Set((params.get("status") || "").split(",").filter(Boolean));
    state.page = Math.max(1, parseInt(params.get("page") || "1", 10) || 1);
    state.sort = params.get("sort") || "type";
    state.desc = params.get("desc") === "1";
  }
  function writeHash() {
    const params = new URLSearchParams();
    if (state.q) params.set("q", state.q);
    if (state.types.size) params.set("type", [...state.types].join(","));
    if (state.statuses.size) params.set("status", [...state.statuses].join(","));
    if (state.page > 1) params.set("page", state.page);
    if (state.sort !== "type") params.set("sort", state.sort);
    if (state.desc) params.set("desc", "1");
    const hash = params.toString();
    history.replaceState(null, "", hash ? "#" + hash : location.pathname + location.search);
  }

  const typeOrder = Object.fromEntries(data.types.map((type, index) => [type.key, index]));
  const SORTS = {
    type: row => [typeOrder[row.k] ?? 99, natural(row.n), natural(row.t)],
    page: row => [natural(row.n || row.t)],
    title: row => [row.t.toLowerCase()],
    status: row => [row.st || "~", typeOrder[row.k] ?? 99, natural(row.n)],
  };
  function compare(left, right) {
    for (let i = 0; i < left.length; i++) {
      if (left[i] < right[i]) return -1;
      if (left[i] > right[i]) return 1;
    }
    return 0;
  }
  function selected() {
    const words = state.q.toLowerCase().split(/\s+/).filter(Boolean);
    const key = SORTS[state.sort] || SORTS.type;
    const found = rows.filter(row => (!state.types.size || state.types.has(row.k))
      && (!state.statuses.size || state.statuses.has(row.st || "none"))
      && words.every(word => row.search.includes(word)));
    found.sort((a, b) => compare(key(a), key(b)) * (state.desc ? -1 : 1));
    return found;
  }

  // ---------- the controls (built once) and the table (on every change) ----------
  const search = document.createElement("input");
  search.type = "search";
  search.className = "obj-search";
  search.placeholder = "Search number, title or summary…";
  search.setAttribute("aria-label", "Search the pages");
  const typeRow = document.createElement("div");
  typeRow.className = "obj-chips";
  const statusRow = document.createElement("div");
  statusRow.className = "obj-chips";
  const info = document.createElement("div");
  info.className = "obj-info";
  const table = document.createElement("table");
  table.className = "nodes obj-table";
  const pager = document.createElement("div");
  pager.className = "obj-pager";
  root.replaceChildren(search, typeRow, statusRow, info, table, pager);

  function chip(label, count, active, cls, onclick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "obj-chip " + cls + (active ? " on" : "");
    button.setAttribute("aria-pressed", String(active));
    button.innerHTML = label + " <span class='obj-count'>" + count + "</span>";
    button.addEventListener("click", onclick);
    return button;
  }
  function toggle(set, key) { set.has(key) ? set.delete(key) : set.add(key); state.page = 1; render(); }

  function render() {
    writeHash();
    if (search.value !== state.q) search.value = state.q;
    const found = selected();
    // counts per type and status within the other filters, so a chip shows what clicking it would give
    const byType = {}, byStatus = {};
    const words = state.q.toLowerCase().split(/\s+/).filter(Boolean);
    for (const row of rows) {
      if (!words.every(word => row.search.includes(word))) continue;
      if (!state.statuses.size || state.statuses.has(row.st || "none")) byType[row.k] = (byType[row.k] || 0) + 1;
      if (!state.types.size || state.types.has(row.k)) byStatus[row.st || "none"] = (byStatus[row.st || "none"] || 0) + 1;
    }
    typeRow.replaceChildren(Object.assign(document.createElement("span"), { className: "obj-label", textContent: "Type" }),
      ...data.types.map(type => chip(`<span class='k-${esc(type.key)}'>${esc(type.label)}</span>`, byType[type.key] || 0, state.types.has(type.key), "t-chip",
        () => toggle(state.types, type.key))));
    const statuses = [...new Set(rows.map(row => row.st || "none"))].sort();
    statusRow.replaceChildren(Object.assign(document.createElement("span"), { className: "obj-label", textContent: "Status" }),
      ...statuses.map(status => chip(esc(status === "none" ? "no status" : status.replace(/_/g, " ")), byStatus[status] || 0,
        state.statuses.has(status), "s-chip", () => toggle(state.statuses, status))));
    if (state.types.size || state.statuses.size || state.q) {
      const clear = document.createElement("button");
      clear.type = "button"; clear.className = "obj-clear"; clear.textContent = "Show all";
      clear.addEventListener("click", () => { state.q = ""; state.types.clear(); state.statuses.clear(); state.page = 1; render(); });
      statusRow.append(clear);
    }
    const pages = Math.max(1, Math.ceil(found.length / PAGE_SIZE));
    state.page = Math.min(state.page, pages);
    const first = (state.page - 1) * PAGE_SIZE;
    const shown = found.slice(first, first + PAGE_SIZE);
    info.textContent = found.length
      ? `${first + 1}–${first + shown.length} of ${found.length} page${found.length === 1 ? "" : "s"}` + (found.length < rows.length ? ` (of ${rows.length})` : "")
      : "No page matches.";
    const arrow = key => state.sort === key ? (state.desc ? " ▾" : " ▴") : "";
    table.innerHTML = "<colgroup><col class='c-page'><col><col class='c-status'></colgroup>"
      + `<tr><th><button type='button' data-sort='page'>Page${arrow("page")}</button> · <button type='button' data-sort='type'>type${arrow("type")}</button></th>`
      + `<th>In short</th><th><button type='button' data-sort='status'>Status${arrow("status")}</button></th></tr>`
      + shown.map(row => `<tr class='${row.r}'><td><a class='tagline' href='${esc(data.prefix + row.h)}'>`
        + `<span class='tag t-${esc(row.k)}'>${data.icons[row.k] || ""}${esc(row.n)}</span>`
        + `<span class='tl-text'>${esc(row.t)}</span></a></td><td>${esc(row.s)}</td>`
        + `<td>${row.st ? `<span class='pill s-${esc(row.st)}'>${esc(row.st.replace(/_/g, " "))}</span>` : ""}</td></tr>`).join("");
    table.querySelectorAll("th button").forEach(button => button.addEventListener("click", () => {
      const key = button.dataset.sort;
      state.desc = state.sort === key ? !state.desc : false;
      state.sort = key; state.page = 1; render();
    }));
    pager.replaceChildren();
    if (pages > 1) {
      const go = (label, page, disabled) => {
        const button = document.createElement("button");
        button.type = "button"; button.textContent = label; button.disabled = disabled;
        button.addEventListener("click", () => { state.page = page; render(); root.scrollIntoView({ block: "start" }); });
        return button;
      };
      pager.append(go("« first", 1, state.page === 1), go("‹ previous", state.page - 1, state.page === 1),
        Object.assign(document.createElement("span"), { textContent: `page ${state.page} of ${pages}` }),
        go("next ›", state.page + 1, state.page === pages), go("last »", pages, state.page === pages));
    }
  }
  let timer = null;
  search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { state.q = search.value.trim(); state.page = 1; render(); }, 150); });
  window.addEventListener("hashchange", () => { readHash(); render(); });
  readHash();
  render();
})();
