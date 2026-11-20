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
  /* Keyboard shortcuts, outside a text field and without Ctrl, Alt or ⌘ (render.CSS .kea-keys). Two menus that
     mirror the menu bar and the page's buttons: g opens a menu of places (g then q: this page's question; g then M: Map), a a menu of this page's
     actions (a then t: edit the title), grouped as the buttons are (sign-off · Change · More; feedback.js
     keaPageActions does exactly what each button does). n / p walk every page in the reading order, always the same
     (_order.json, written by kea build); N / P only the pages that need attention, in that same order. A key
     signs at most this page (a then a, or a then n: approve & next) and, like a click, nothing starts: the sign-off
     waits for the Harvest. ? lists every key. Entries that do not apply on this page are greyed out. */
  const topLink = (ending) => () => document.querySelector(`.topbar a[href$='${ending}']`);
  const visible = (selector) => [...document.querySelectorAll(selector)].find((item) => item.offsetParent !== null);
  const siteRoot = () => { const help = document.querySelector(".topbar .user a[href$='help.html']"); return help ? new URL("./", help.href) : null; };
  let readingOrder = null;
  function loadOrder() {
    if (readingOrder) return Promise.resolve(readingOrder);
    const root = siteRoot();
    if (!root) return Promise.resolve([]);
    return fetch(new URL("_order.json", root)).then((response) => response.ok ? response.json() : [])
      .catch(() => []).then((list) => (readingOrder = Array.isArray(list) ? list : []));
  }
  const hereIn = (list) => { const root = siteRoot(); return list.findIndex((item) => new URL(item.href, root).pathname === location.pathname); };
  async function readingStep(step) {
    const list = await loadOrder(), root = siteRoot();
    if (!list.length || !root) return;
    const here = hereIn(list);
    const index = here < 0 ? (step > 0 ? 0 : list.length - 1) : here + step;
    if (index < 0 || index >= list.length) { flash(step > 0 ? "This is the last page." : "This is the first page."); return; }
    markStep("reading");
    location.href = new URL(list[index].href, root).href;
  }
  /* After n/p or N/P: a thin bar under the menu bar for a moment, one segment per page of the order walked (amber:
     needs attention, green: approved on the site this round, grey: nothing to do), the page you are on raised,
     with where you are in words. The step is remembered across the page load in sessionStorage. */
  function markStep(kind) { try { sessionStorage.setItem("kea-step", JSON.stringify({ kind, at: Date.now() })); } catch (error) { /* private mode */ } }
  function statusReady() {
    if (window.keaStatus) return Promise.resolve(window.keaStatus);
    return new Promise((resolve) => {
      window.addEventListener("kea-status", () => resolve(window.keaStatus), { once: true });
      setTimeout(() => resolve(window.keaStatus || null), 3000);
    });
  }
  async function showStepBar(kind) {
    const root = siteRoot();
    if (!root) return;
    const [list, status] = await Promise.all([loadOrder(), statusReady()]);
    const order = status ? ((status.build || {}).sign_order || []).filter((item) => item.href) : [];
    const signed = new Set(status ? status.signing || [] : []), attention = new Set(order.map((item) => item.key));
    const group = kind === "sibling" ? await siblings() : null;
    const items = kind === "attention" ? order : group ? group.same : list;
    const here = hereIn(items);
    if (here < 0 || !items.length) return;
    const key = items[here].key, state = (item) => signed.has(item.key) ? "ok" : attention.has(item.key) ? "open" : "";
    const bar = document.createElement("div");
    bar.className = "kea-stepbar not-annotatable";
    const top = document.querySelector(".topbar");
    bar.style.top = (top ? Math.max(0, top.getBoundingClientRect().bottom) : 0) + "px";
    const track = document.createElement("div");
    track.className = "kea-stepbar-track" + (items.length > 80 ? " dense" : "");
    items.forEach((item, index) => {
      const segment = document.createElement("span");
      segment.className = ["seg", state(item), index === here ? "here" : ""].filter(Boolean).join(" ");
      track.append(segment);
    });
    const open = order.filter((item) => !signed.has(item.key)).length, done = order.length - open;
    const mine = signed.has(key) ? "approved this round" : attention.has(key) ? "needs attention" : "";
    const words = kind === "attention"
      ? `Needs attention · ${here + 1} of ${items.length} · ${open} open, ${done} approved this round`
      : group ? `${group.many} of this experiment · ${items[here].label} · ${here + 1} of ${items.length}`
      : `Reading order · ${here + 1} of ${items.length}` + (order.length ? ` · ${open} need attention` : "");
    const label = document.createElement("div");
    label.className = "kea-stepbar-label";
    label.textContent = words + (mine ? ` · this page: ${mine}` : "");
    bar.append(track, label);
    document.body.append(bar);
    setTimeout(() => bar.classList.add("gone"), 2600);
    setTimeout(() => bar.remove(), 3200);
  }
  function pendingStep() {
    let step = null;
    try { step = JSON.parse(sessionStorage.getItem("kea-step") || "null"); sessionStorage.removeItem("kea-step"); } catch (error) { step = null; }
    if (step && Date.now() - step.at < 10000) showStepBar(step.kind);
  }
  async function attentionStep(step) {
    if (window.keaAttention) {
      const list = await loadOrder();
      const item = window.keaAttention(step, list.map((entry) => entry.key));
      if (item) { markStep("attention"); window.keaGoTo(item); return; }
      flash("No page needs attention.");
      return;
    }
    const button = step > 0 ? (visible(".fb-sn-next") || visible(".fb-d-tosign")) : visible(".fb-sn-prev");
    if (button) { markStep("attention"); button.click(); } else flash("No page needs attention (or the comment server is not reachable).");
  }
  function flash(text) {
    const note = document.createElement("div");
    note.className = "kea-keys kea-keys-flash not-annotatable";
    note.textContent = text;
    document.body.append(note);
    setTimeout(() => note.remove(), 1800);
  }
  /* g, places on the site: small letters, in the menu bar's order (g p Plan, g m Map). */
  const GO = [
    ["s", "Start, the site's front page", () => document.querySelector(".topbar a.home")],
    ["e", "The experiment's front page", topLink("/home.html")],
    ["u", "Up: the page above this one", () => { const links = document.querySelectorAll("nav.crumbs a"); return document.querySelector(".node-content") ? links[links.length - 1] : null; }],
    ["a", "The first page that needs attention", () => window.keaAttention ? { go: () => attentionStep(1) } : null],
    ["r", "Progress: what waits for whom", topLink("progress.html")],
    ["p", "Plan of the current round", topLink("plan.html")],
    ["c", "Current comments", topLink("comments.html")],
    ["m", "Map", topLink("map.html")],
    ["l", "Relations: the graph of links", topLink("relations.html")],
    ["o", "Objects: every page by type", topLink("objects.html")],
    ["t", "Terms", topLink("objects.html#type=term")],
    ["b", "References (bibliography)", topLink("objects.html#type=reference")],
    ["d", "Data files", topLink("data.html")],
    ["k", "Code", topLink("code/index.html")],
    ["w", "What changed, per working session", topLink("changes/index.html")],
    ["h", "History: the review cycles", topLink("history.html")],
    ["f", "The PDF", () => document.querySelector(".topbar a[href$='.pdf']")],
    ["?", "Help", topLink("help.html")],
  ];
  /* g, the pages linked to this one: capitals, the letter of their number as the page shows it (g Q its question,
     g R its results, g W its caveats). The pages linked in the page's relations (its About part, both directions, provenance included) and
     then in its text; one page opens at once, several open a numbered choice. */
  const NEAR_TYPES = [
    ["Q", "question", "Question", "Questions"], ["P", "premise", "Premise", "Premises"],
    ["H", "hypothesis", "Hypothesis", "Hypotheses"], ["S", "step", "Step", "Steps"], ["R", "result", "Result", "Results"],
    ["F", "figure", "Figure", "Figures"], ["C", "conclusion", "Conclusion", "Conclusions"], ["W", "caveat", "Caveat", "Caveats"],
    ["D", "decision", "Decision", "Decisions"], ["A", "artefact", "Artefact", "Artefacts"],
    ["O", "resource", "Resource", "Resources"], ["T", "term", "Term", "Terms"], ["B", "reference", "Reference", "References"],
  ];
  const escHtml = (text) => String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const folderOf = (path) => path.split("/").slice(-2, -1)[0] || "";
  function relationOf(link) {
    let item = link.closest("ul, table, ol");
    for (let before = item && item.previousElementSibling; before; before = before.previousElementSibling)
      if (/^H[23]$/.test(before.tagName)) return before.textContent.trim();
    const heading = link.closest("section") && link.closest("section").querySelector("h2");
    return heading ? heading.textContent.trim() : "";
  }
  function nearPages() {
    const node = document.querySelector(".node-content");
    if (!node) return [];
    const seen = new Set([location.pathname]), found = [];
    const skip = "nav, .fb-thread, .fb-history, .fb-static, .round-diff, .tab-panel[data-tab='changes'], .tab-panel[data-tab='comments'], .kea-keys";
    const scopes = [...document.querySelectorAll("section.about")].map((scope) => [scope, null]).concat([[node, "in the text"]]);
    for (const [scope, where] of scopes) for (const link of scope.querySelectorAll("a.tagline, a.tag")) {
      if (link.closest(skip)) continue;
      const tag = link.classList.contains("tag") ? link : link.querySelector(".tag");
      const type = tag ? ([...tag.classList].find((name) => name.startsWith("t-")) || "").slice(2) : "";
      if (!NEAR_TYPES.some(([, name]) => name === type)) continue;
      const url = new URL(link.getAttribute("href"), location.href);
      if (seen.has(url.pathname)) continue;
      seen.add(url.pathname);
      const label = tag.textContent.trim();
      const hover = (link.getAttribute("title") || "").split(" — ")[0];
      const words = link.querySelector(".tl-text") ? link.querySelector(".tl-text").textContent.trim() : hover.replace(/^[^·]*·\s*/, "");
      const project = folderOf(url.pathname) !== folderOf(location.pathname) ? folderOf(url.pathname) : "";
      found.push({ type, label, words: words === label ? "" : words, href: url.href, relation: where || relationOf(link), project });
    }
    return found;
  }
  const nearLine = (page) => `<b>${escHtml(page.label)}</b> ${escHtml(page.words)}`
    + (page.project ? ` <small>(${escHtml(page.project)})</small>` : "")
    + (page.relation ? ` <small class='kea-rel'>· ${escHtml(page.relation.toLowerCase())}</small>` : "");
  const PICK_KEYS = "123456789abcdefghijklmnopqrstuvwxyz";
  function pickMenu(plural, pages) {
    keyBox("pick", plural + " linked from this page", [["", pages.slice(0, PICK_KEYS.length)
      .map((page, index) => [PICK_KEYS[index], nearLine(page), () => ({ href: page.href })])]], "Press a key, or Esc.");
  }
  function nearRows() {
    const rows = [], pages = nearPages();
    for (const [key, type, one, many] of NEAR_TYPES) {
      const mine = pages.filter((page) => page.type === type);
      if (mine.length === 1) rows.push([key, `${one}: ${nearLine(mine[0])}`, () => ({ href: mine[0].href })]);
      else if (mine.length > 1) rows.push([key, `${many} (${mine.length}): ` + mine.slice(0, 6).map((page) => escHtml(page.label + (page.project ? " (" + page.project + ")" : ""))).join(", ")
        + (mine.length > 6 ? " …" : "") + " <small>· then pick one</small>", () => ({ go: () => pickMenu(many, mine) })]);
    }
    return rows;
  }
  /* Pages of the same kind in the same experiment, by number (Q1, Q2, Q3): ← / → the previous and next one, g then
     a number that one (g 3: Q3 on a question; on the experiment's front page, its questions). From _order.json. */
  const numberOf = (item) => Number((/^[A-Z](\d+)$/.exec(item.label || "") || [0, 0])[1]);
  async function siblings() {
    const list = await loadOrder(), here = hereIn(list);
    if (here < 0) return null;
    const mine = list[here], project = mine.key.split(":")[0];
    const match = /^([A-Z])\d+$/.exec(mine.label || "");
    const letter = match ? match[1] : mine.key.endsWith(":home") ? "Q" : "";
    if (!letter) return null;
    const same = list.filter((item) => item.key.split(":")[0] === project && new RegExp("^" + letter + "\\d+$").test(item.label || ""))
      .sort((one, two) => numberOf(one) - numberOf(two));
    const kind = NEAR_TYPES.find(([key]) => key === letter);
    return { letter, same, here: same.findIndex((item) => item.key === mine.key), one: kind ? kind[2] : letter, many: kind ? kind[3] : letter };
  }
  async function siblingStep(step) {
    const group = await siblings(), root = siteRoot();
    if (!group || group.here < 0) { flash("This page has no numbered kind (Q1, R2 …) to step through."); return; }
    const next = group.same[group.here + step];
    if (!next) { flash(`This is the ${step > 0 ? "last" : "first"} ${group.one.toLowerCase()} of the experiment.`); return; }
    markStep("sibling");
    location.href = new URL(next.href, root).href;
  }
  async function siblingNumber(number) {
    const group = await siblings(), root = siteRoot();
    const target = group && group.same.find((item) => numberOf(item) === number);
    if (!target) { flash(group ? `No ${group.letter}${number} in this experiment.` : "Numbers go to pages of this page's kind (g 3: Q3 on a question)."); return; }
    if (group.here >= 0 && group.same[group.here] === target) { flash(`This is ${target.label}.`); return; }
    location.href = new URL(target.href, root).href;
  }
  let digits = "", digitTimer = null;          // g 1 2: a number of more than one digit, typed within 0.7 s
  function typeDigit(digit) {
    digits += digit;
    clearTimeout(digitTimer);
    digitTimer = setTimeout(() => { const number = Number(digits); digits = ""; siblingNumber(number); }, 700);
  }
  async function siblingRows() {
    const group = await siblings();
    if (!group || !group.same.length) return [];
    const show = (item) => `<b>${escHtml(item.label)}</b> ${escHtml(item.title)}`;
    const before = group.here > 0 ? group.same[group.here - 1] : null, after = group.here >= 0 ? group.same[group.here + 1] : null;
    const rows = [];
    if (group.here >= 0) {
      rows.push(["←", "Previous " + group.one.toLowerCase() + (before ? ": " + show(before) : ""), () => before ? { go: () => siblingStep(-1) } : null]);
      rows.push(["→", "Next " + group.one.toLowerCase() + (after ? ": " + show(after) : ""), () => after ? { go: () => siblingStep(1) } : null]);
    }
    const last = numberOf(group.same[group.same.length - 1]);
    rows.push([`1–${last}`, `${group.many} ${group.letter}1 to ${group.letter}${last} of this experiment, by number (also on any page: ← →)`, () => ({ go: () => flash("Press g, then the number.") })]);
    return rows;
  }
  /* A confirmation that the keyboard answers: Enter or y does it, Esc or n does not. */
  window.keaConfirm = function (title, text, okLabel, onOk) {
    closeKeys();
    const box = document.createElement("div");
    box.id = "kea-keys";
    box.dataset.kind = "confirm";
    box.className = "kea-keys kea-keys-confirm not-annotatable";
    box.setAttribute("role", "alertdialog");
    box.innerHTML = `<h2>${escHtml(title)}</h2><p>${escHtml(text)}</p><div class='kea-confirm-actions'>`
      + `<button type='button' class='kea-ok'>${escHtml(okLabel)} <kbd>Enter</kbd></button>`
      + `<button type='button' class='kea-no'>Cancel <kbd>Esc</kbd></button></div>`;
    box.keaOk = () => { closeKeys(); onOk(); };
    box.querySelector(".kea-ok").addEventListener("click", box.keaOk);
    box.querySelector(".kea-no").addEventListener("click", closeKeys);
    document.body.append(box);
  };
  const siteRows = () => (window.keaSiteActions ? window.keaSiteActions() : [])
    .map(([head, rows]) => [head, rows.map(([key, text, can, run]) => [key, text, () => (can ? { run } : null)])]);
  const siteMenu = () => {
    const sections = siteRows();
    if (!sections.length) { flash("Site actions need the comment server."); return; }
    keyBox("site", "This site …", sections, "Press a key, or Esc. Each asks first; Enter (or y) confirms.");
  };
  const NEAR_HELP = NEAR_TYPES.map(([key, , one]) => [key, "The linked " + one.toLowerCase() + " (several: pick one)",
    () => { const row = nearRows().find(([rowKey]) => rowKey === key); return row ? row[2]() : null; }]);
  function tabStep(step) {
    const strip = document.querySelector(".sep-tabs");
    if (!strip) return null;
    const buttons = [...strip.querySelectorAll(".sep-tab:not([hidden])")];
    const here = buttons.findIndex((item) => item.classList.contains("on"));
    return typeof step === "number" ? buttons[(here + step + buttons.length) % buttons.length] : buttons[step.index] || null;
  }
  /* After a tab key: the tab strip goes to just under the menu bar (as high as the page's length allows), so the
     tab's content is in view at once. */
  function tabToTop(button) {
    const strip = button.closest(".node-data-sep") || button.parentElement;
    const bar = document.querySelector(".topbar");
    const below = bar && getComputedStyle(bar).position !== "static" ? bar.getBoundingClientRect().height : 0;
    window.scrollTo({ top: Math.max(0, strip.getBoundingClientRect().top + window.scrollY - below - 8), behavior: "smooth" });
  }
  const PAGE_KEYS = [
    ["g", "Go to … (places by small letters, linked pages by capitals: g Q its question; g 3 the third of this kind)", () => true],
    ["s", "This site … (Harvest; Implement on the plan page; cancel a request), each confirmed with Enter", () => !!window.keaSiteActions],
    ["← →", "Previous / next page of the same kind in this experiment (Q2 ← Q3 → Q4)", () => true],
    ["a", "Act on this page … (approve, edit, revise, propose …)", () => !!(window.keaPageActions && window.keaPageActions().length)],
    ["c", "Comments on this page: opens with the cursor in the comment box (Esc closes)", () => visible(".fb-d-comment")],
    ["n", "Next page, in the reading order (always the same)", () => true],
    ["p", "Previous page, in the reading order", () => true],
    ["N", "Next page of this round's attention list (approved ones included, shown green)", () => !!window.keaAttention || visible(".fb-sn-next") || visible(".fb-d-tosign")],
    ["P", "Previous page of that list", () => !!window.keaAttention || visible(".fb-sn-prev")],
    ["]", "Next tab below the text", () => tabStep(1)],
    ["[", "Previous tab", () => tabStep(-1)],
    ["1–9", "Tab 1 to 9", () => tabStep({ index: 0 })],
    ["?", "This list", () => true],
  ];
  const actionRows = () => (window.keaPageActions ? window.keaPageActions() : [])
    .map(([head, rows]) => [head, rows.map(([key, text, can, run]) => [key, text, () => (can ? { run } : null)])]);
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
    const esc = (text) => text.replace(/&(?!amp;)/g, "&amp;").replace(/</g, "&lt;");
    let html = `<button type='button' class='kea-keys-close' title='Close (Esc)'>×</button><h2>${title}</h2>`
      + (note ? `<p>${note}</p>` : "");
    const actions = [];
    box.keaKeys = new Map();
    for (const [head, rows] of sections) {
      html += (head ? `<h3>${head}</h3>` : "") + (rows === GO && kind === "go" ? "<table class='cols2'>" : "<table>");
      for (const [key, text, find] of rows) {
        const target = find();
        if (target && !box.keaKeys.has(key)) box.keaKeys.set(key, target);
        const href = target && target.href ? ` data-href='${esc(target.href)}'` : "";
        const act = target && (target.run || target.go) ? ` data-act='${actions.push(target.run || target.go) - 1}'` : "";
        html += `<tr${target ? href + act : " class='off' title='Not on this page'"}><td><kbd>${esc(key)}</kbd></td><td>${text}</td></tr>`;
      }
      html += "</table>";
    }
    box.innerHTML = html;
    box.querySelector(".kea-keys-close").addEventListener("click", closeKeys);
    box.addEventListener("click", (event) => {
      const row = event.target.closest("tr[data-href], tr[data-act]");
      if (!row) return;
      closeKeys();
      if (row.dataset.act) actions[Number(row.dataset.act)]();
      else location.href = row.dataset.href;
    });
    document.body.append(box);
  }
  let goOpening = false, goQueued = null;      // a key typed after g before the menu is up (it reads _order.json)
  const goMenu = async () => {
    goOpening = true;
    const near = nearRows(), same = await siblingRows().catch(() => []);
    goOpening = false;
    keyBox("go", "Go to …", [["Places on the site", GO]].concat(near.length ? [["Linked to this page (capitals: the letter of their number)", near]] : [])
      .concat(same.length ? [["Same kind, by number", same]] : []),
      "Press a key, or Esc. Small letters: places; capitals: the pages linked to this one (Q question, R result, W caveat …); a number: that page of this kind.");
    if (goQueued) { const key = goQueued; goQueued = null; if (key === "Escape") closeKeys(); else secondKey(document.getElementById("kea-keys"), key); }
  };
  const actMenu = () => {
    const sections = actionRows();
    if (!sections.length) { flash("Page actions need the comment server, on a page of the experiment."); return; }
    keyBox("act", "This page …", sections, "Press a key, or Esc. Nothing starts: like a click, a sign-off or request waits for the Harvest.");
  };
  const keyList = () => keyBox("all", "Keyboard shortcuts",
    [["On any page", PAGE_KEYS], ["After g: places on the site", GO], ["After g: linked to this page", NEAR_HELP],
     ["After g: same kind", [["1–99", "That number of this page's kind (g 3: Q3 on a question)", () => null]]], ...siteRows().map(([head, rows]) => ["After s: " + head.toLowerCase(), rows]), ...actionRows().map(([head, rows]) => ["After a: " + head.toLowerCase(), rows])],
    "Outside a text field. In a comment: Ctrl+Enter (⌘+Enter) sends, Esc cancels.");
  /* The key after g, a or s (or in a numbered choice). */
  function secondKey(open, key) {
    const kind = open.dataset.kind, keys = open.keaKeys;
    closeKeys();
    if (kind === "go" && /^[0-9]$/.test(key)) typeDigit(key);
    else if (kind === "go" && (key === "ArrowLeft" || key === "ArrowRight")) siblingStep(key === "ArrowRight" ? 1 : -1);
    else if (kind === "site") {
      const link = keys && keys.get(key);
      if (link) link.run(); else flash("Not now (or not for you): the greyed-out entries say why.");
    } else if (kind !== "act") {
      const link = keys && keys.get(key);
      if (link && link.go) link.go(); else if (link) location.href = link.href;
      else if (kind === "go" && /^[A-Z]$/.test(key)) flash("No such page linked to this one.");
    } else {
      for (const [, rows] of window.keaPageActions ? window.keaPageActions() : []) {
        const entry = rows.find(([rowKey]) => rowKey === key);
        if (entry) { if (entry[2]) entry[3](); else flash("Not on this page."); break; }
      }
    }
  }
  document.addEventListener("keydown", (event) => {
    const open = document.getElementById("kea-keys");
    if (event.key === "Escape") { if (goOpening) goQueued = "Escape"; if (open) { closeKeys(); event.preventDefault(); } return; }
    if (event.ctrlKey || event.metaKey || event.altKey || event.defaultPrevented) return;
    const target = event.target;
    if (target instanceof Element && target.closest("input, textarea, select, [contenteditable=''], [contenteditable='true']")) return;
    if (["Shift", "CapsLock"].includes(event.key)) return;
    if (open && open.dataset.kind === "confirm") {           // Enter or y confirms; n cancels; other keys wait
      event.preventDefault();
      if (event.key === "Enter" || event.key === "y") open.keaOk();
      else if (event.key === "n") closeKeys();
      return;
    }
    if (digits && /^[0-9]$/.test(event.key)) { event.preventDefault(); typeDigit(event.key); return; }
    if (goOpening) { goQueued = event.key; event.preventDefault(); return; }
    if (open && ["go", "pick", "act", "site"].includes(open.dataset.kind)) {     // the key after g, a or s, or a pick
      event.preventDefault();
      secondKey(open, event.key);
      return;
    }
    let hit = null;
    const key = event.key;
    if (key === "g") { goMenu(); hit = true; }
    else if (key === "a") { actMenu(); hit = true; }
    else if (key === "s") { siteMenu(); hit = true; }
    else if ((key === "ArrowLeft" || key === "ArrowRight") && !event.shiftKey && (target === document.body || target === document.documentElement)
      && document.querySelector(".node-content, [data-page-type]")) { siblingStep(key === "ArrowRight" ? 1 : -1); hit = true; }
    else if (key === "?") { keyList(); hit = true; }
    else if (key === "n" || key === "p") { readingStep(key === "n" ? 1 : -1); hit = true; }
    else if (key === "N" || key === "P") { attentionStep(key === "N" ? 1 : -1); hit = true; }
    else if (/^[1-9]$/.test(key)) hit = tabStep({ index: Number(key) - 1 });
    else if (key === "]" || key === "[") hit = tabStep(key === "]" ? 1 : -1);
    else if (key === "c" && window.keaCommentKey) hit = window.keaCommentKey();
    else if (key === "c") hit = visible(".fb-d-comment");
    if (hit && hit !== true) { hit.click(); if (hit.classList.contains("sep-tab")) tabToTop(hit); }
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

  /* Each button and menu-bar link that has a key gets it in front of its hover text ("g p · Plan of …"), also when
     the page scripts rewrite the text later (a MutationObserver). The sign-off button sets its own (feedback.js). */
  const KEY_HINTS = [
    [".fb-d-comment", "c"], [".fb-d-edit", "a p"], [".fb-d-revise", "a r"], [".fb-d-reject", "a x"], [".fb-d-propose", "a +"],
    [".fb-d-next", "a w"], [".fb-d-ms", "a m"], [".fb-sn-next", "N"], [".fb-sn-prev", "P"], [".fb-d-tosign", "N"],
    [".cycle-tool .ct-harvest", "s h"], ["#fb-plan-actions .fb-implement, #fb-plan-actions .fb-secondary[title]", "s h"], [".fb-implement-big", "s i"],
  ];
  let hinting = false;
  function hint(element, key) {
    if (!element || !key) return;
    const title = element.getAttribute("title") || "";
    if (title.startsWith(key + " · ") || title === key) return;
    element.setAttribute("title", title ? key + " · " + title : key);
  }
  function keyHints() {
    if (hinting) return;
    hinting = true;
    for (const [selector, key] of KEY_HINTS) document.querySelectorAll(selector).forEach((element) => hint(element, key));
    for (const [key, , find] of GO) {
      if (["e", "u", "a"].includes(key)) continue;
      const target = find();
      if (target && target.tagName === "A" && target.closest(".topbar")) hint(target, "g " + key);
    }
    document.querySelectorAll(".sep-tabs").forEach((strip) => [...strip.querySelectorAll(".sep-tab:not([hidden])")]
      .forEach((button, index) => hint(button, index < 9 ? String(index + 1) : "] [")));
    hinting = false;
  }
  function watchHints() {
    keyHints();
    let queued = false;
    new MutationObserver(() => {
      if (hinting || queued) return;
      queued = true;
      requestAnimationFrame(() => { queued = false; keyHints(); });
    }).observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["title"] });
  }

  function start() {
    watchHints();
    pendingStep();
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
