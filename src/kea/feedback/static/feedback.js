/* Reader comments and tags on the site: select text -> "Comment" or "Tag", or comment on / tag the whole page.
 * Tags (feedback/tags.py; the list comes with the threads from the server) are stored on a thread: task tags
 * (challenge, explain, …) ask for work like a comment; mark tags (introduction, methods, …) only label text for the
 * manuscript and give the thread the state "marked".
 *
 * Uses @recogito/text-annotator (BSD-3, vendored as recogito-text-annotator-4.3.7.umd.js) only to
 * draw highlights and to turn a selection into {quote, start, end}; the comment form, the side
 * panel and the storage (feedback/server.py -> data/feedback/events.jsonl) are ours.
 *
 * The page's <script> tag carries: data-page (path relative to the site root), data-commit
 * (git commit of the page's source), data-title.
 * Without the server (file:// or plain static hosting) the panel stays off and the static copy of
 * the threads written at build time remains visible.
 */
(function () {
  "use strict";
  // The vendored Recogito build reads process.env.NODE_ENV (a bundler leftover); give it the production value.
  if (typeof window.process === "undefined") window.process = { env: { NODE_ENV: "production" } };
  const script = document.currentScript;
  const PAGE = script.dataset.page;
  const COMMIT = script.dataset.commit || "";
  const TITLE = script.dataset.title || document.title;
  const ASSET_BASE = script.src.replace(/[^/]*$/, "");      // .../_feedback/
  const BASE = ASSET_BASE.replace(/_feedback\/$/, "");      // the site root (also under a hub prefix /p/<name>/)
  const API = BASE + "api/threads";
  let editable = false;
  let readOnly = false;                          // a signed-in auditor (hub role): sees comments, writes none
  const CONTEXT = 40;
  const NOT = "not-annotatable";
  const STATUS_TEXT = {
    "open": "open", "answered": "answered", "page-changed": "page changed",
    "wont-fix": "won't fix", "resolved": "resolved", "planned": "in the plan", "marked": "marked"
  };
  let vocab = { tags: [], groups: {}, free_tags: false };

  let threads = [];
  let annotator = null;
  let container = null;
  let panel, listEl, orphanEl, toggleBtn, selectBtn, nameBox, dockEl;      // selectBtn: the bar with "Comment" and "Tag"
  let pendingSelection = null;

  // ---------- small helpers ----------
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (key === "class") node.className = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value);
    }
    for (const child of children) {
      if (child === null || child === undefined) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }
  let accountName = "";                          // signed in with ORCID (kea hub): the verified name, set by the server
  function getName() {
    if (accountName) return accountName;
    const match = document.cookie.match(/(?:^|; )fb_name=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : "";
  }
  function setName(name) {
    document.cookie = "fb_name=" + encodeURIComponent(name) + "; max-age=" + 365 * 86400 + "; path=/; samesite=lax";
  }
  function when(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) + " " +
      date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }
  // One key per submit: a submit sent again while it is under way or after it failed (double click, retry after a
  // slow server) carries the same key, and the server stores it once. Once it succeeded, the same click is a new
  // request (Confirm, take it back, Confirm again) and gets a new key.
  const LOAD_ID = Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
  const pendingKeys = new Map();
  let keyCount = 0;
  function requestKey(method, url, payload) {
    let hash = 2166136261;                       // FNV-1a over method, url and body
    const text = method + " " + url + " " + payload;
    for (let i = 0; i < text.length; i++) { hash ^= text.charCodeAt(i); hash = Math.imul(hash, 16777619) >>> 0; }
    const fingerprint = hash.toString(36);
    if (!pendingKeys.has(fingerprint)) pendingKeys.set(fingerprint, LOAD_ID + "-" + fingerprint + "-" + (++keyCount).toString(36));
    return [fingerprint, pendingKeys.get(fingerprint)];
  }
  async function api(method, url, body) {
    const payload = body ? JSON.stringify(body) : undefined;
    const headers = body ? { "Content-Type": "application/json" } : {};
    let fingerprint = "";
    if (method !== "GET") { const [print, key] = requestKey(method, url, payload || ""); fingerprint = print; headers["X-Kea-Request"] = key; }
    const response = await fetch(url, { method, credentials: "same-origin", headers, body: payload });
    let data = {};
    try { data = await response.json(); } catch (error) { /* not JSON */ }
    if (!response.ok) {
      const error = new Error(data.error || ("HTTP " + response.status));
      error.needSteer = !!data.need_steer;
      throw error;
    }
    if (fingerprint) pendingKeys.delete(fingerprint);   // stored: the next identical click is a new request
    return data;
  }

  // ---------- text anchoring (same text model as Recogito: text nodes outside .not-annotatable) ----------
  function annotatableText() {
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, node =>
      node.parentElement && node.parentElement.closest("." + NOT) ? NodeFilter.FILTER_SKIP : NodeFilter.FILTER_ACCEPT);
    let text = "";
    for (let node = walker.nextNode(); node; node = walker.nextNode()) text += node.textContent;
    return text;
  }
  function commonSuffix(left, right) {
    let count = 0;
    while (count < left.length && count < right.length &&
           left[left.length - 1 - count] === right[right.length - 1 - count]) count++;
    return count;
  }
  function commonPrefix(left, right) {
    let count = 0;
    while (count < left.length && count < right.length && left[count] === right[count]) count++;
    return count;
  }
  /* Where is the quote now? Best match of quote + context; ties go to the one nearest the old offset. */
  function locate(thread, text) {
    if (!thread.quote) return null;
    let best = null;
    for (let index = text.indexOf(thread.quote); index !== -1; index = text.indexOf(thread.quote, index + 1)) {
      const score = commonSuffix(text.slice(Math.max(0, index - CONTEXT), index), thread.prefix || "") +
        commonPrefix(text.slice(index + thread.quote.length, index + thread.quote.length + CONTEXT), thread.suffix || "");
      const distance = Math.abs(index - (thread.start || 0));
      if (!best || score > best.score || (score === best.score && distance < best.distance)) {
        best = { start: index, end: index + thread.quote.length, score, distance };
      }
    }
    return best;
  }
  function contextOf(range) {
    const text = annotatableText();
    const selector = RecogitoJS.rangeToSelector(range, container);
    return {
      quote: selector.quote, start: selector.start, end: selector.end,
      prefix: text.slice(Math.max(0, selector.start - CONTEXT), selector.start),
      suffix: text.slice(selector.end, selector.end + CONTEXT)
    };
  }

  // ---------- highlights ----------
  function stateOf(thread) {
    return thread.state || ({ open: "open", planned: "planned", resolved: "resolved" }[thread.status] || "addressed");
  }
  function highlightStyle(annotation) {
    const thread = threads.find(item => item.thread_id === annotation.id);
    const state = thread ? stateOf(thread) : "open";
    if (state === "open") return { fill: "#ffd54f", fillOpacity: 0.45, underlineColor: "#e0a800", underlineThickness: 2 };
    if (state === "marked") return { fill: "#90caf9", fillOpacity: 0.25, underlineColor: "#1565c0", underlineThickness: 1 };
    if (state === "planned") return { fill: "#ffb74d", fillOpacity: 0.3, underlineColor: "#c77800", underlineThickness: 1 };
    if (state === "addressed") return { fill: "#bdbdbd", fillOpacity: 0.18 };
    return { fill: "#ffffff", fillOpacity: 0 };
  }
  function drawHighlights() {
    if (!annotator) return;
    const text = annotatableText();
    const annotations = [];
    for (const thread of threads) {
      thread._anchored = false;
      const place = locate(thread, text);
      if (!place) continue;
      thread._anchored = true;
      annotations.push({
        id: thread.thread_id, bodies: [],
        target: { annotation: thread.thread_id, selector: [{ quote: thread.quote, start: place.start, end: place.end }] }
      });
    }
    annotator.setAnnotations(annotations, true);
  }


  // ---------- tags ----------
  function tagInfo(name) {
    return vocab.tags.find(tag => tag.name === name) || { name, label: name, group: "own", task: true, help: "" };
  }
  function tagPill(name) {
    const info = tagInfo(name);
    return el("span", { class: "fb-tag fb-tag-" + info.group, title: info.help || "" }, info.label || name);
  }
  function tagLine(thread) {
    const line = el("div", { class: "fb-tags" }, ...(thread.tags || []).map(name => {
      const pill = tagPill(name);
      pill.append(el("button", { class: "fb-x", type: "button", title: "Remove this tag", onclick: () =>
        send(() => api("POST", API + "/" + thread.thread_id + "/tags", { tags: thread.tags.filter(other => other !== name) })) }, "×"));
      return pill;
    }));

    return line;
  }


  // ---------- one-click tags: the selection bar, the page strip, a toast with Undo ----------
  function tagsOf(group, scope) {
    return vocab.tags.filter(tag => tag.group === group && (scope === "page" || (tag.scope || "any") !== "page"));
  }
  /* Proposals (tags.py PROPOSALS): the next step of the reasoning for this page's type, written by the reader. */
  // a page's type: its node, or the project's front page (data-page-type="project"), where only proposals apply
  const pageType = () => { const node = container && container.querySelector(".node-content, [data-page-type]");
    return node ? node.dataset.type || node.dataset.pageType || "" : ""; };
  function proposals() { return vocab.tags.filter(tag => tag.group === "propose" && (tag.types || []).includes(pageType())); }
  /* A small form for one proposal: the reader's text, Send and Cancel; selection = the quoted text or null. */
  function proposalForm(tag, selection, done, heading) {
    const area = el("textarea", { rows: "4", class: "fb-propose-text", placeholder: tag.help || "" });
    const status = el("span", { class: "fb-help" });
    const box = el("div", { class: "fb-propose " + NOT },
      el("div", { class: "fb-sel-label" }, heading || ("Propose " + tag.label + (selection ? " · on the selected text" : " · whole page"))),
      selection ? el("blockquote", { class: "fb-quote" }, selection.quote) : null,
      area,
      el("div", { class: "fb-propose-actions" },
        el("button", { onclick: async () => {
          const text = area.value.trim();
          if (!text) { status.textContent = "Write your proposal first."; area.focus(); return; }
          const thread = await tagThread(selection, [tag.name], text);
          if (thread) { done(); toast(heading ? "Saved: the revision is asked." : "Proposal saved: it goes into the next plan.", () => retag(thread.thread_id, [])); }
        } }, "Send"),
        el("button", { class: "fb-secondary", onclick: () => done() }, "Cancel"), status));
    setTimeout(() => area.focus(), 0);
    return box;
  }
  function toast(message, undo) {
    document.querySelectorAll(".fb-toast").forEach(node => node.remove());
    const box = el("div", { class: "fb-toast " + NOT }, message);
    if (undo) box.append(" ", el("button", { onclick: async () => { box.remove(); await undo(); } }, "Undo"));
    document.body.append(box);
    setTimeout(() => box.remove(), 7000);
  }
  async function tagThread(selection, names, text) {
    const created = await sendQuiet(() => api("POST", API, { page: PAGE, page_title: TITLE, page_commit: COMMIT,
      page_version: pageVersion(), text: text || "", tags: names, ...(selection || {}) }));
    return created && created.thread;
  }
  async function retag(threadId, names) {
    return sendQuiet(() => api("POST", API + "/" + threadId + "/tags", { tags: names }));
  }
  /* like send(), without opening the panel: for one-click tags */
  async function sendQuiet(action) {
    if (!getName()) {
      const name = (prompt("Your name (shown with your comments and tags):") || "").trim();
      if (!name) return null;
      setName(name);
    }
    try { const result = await action(); await reload(); return result; }
    catch (error) { toast("Could not save: " + error.message); return null; }
  }
  function selectionBar(startForm) {
    // a light popup next to the selection: Comment and Edit on top, then one-click tags in two labelled groups
    const bar = el("div", { class: "fb-select-bar " + NOT, role: "dialog", "aria-label": "Comment on, edit or tag the selected text",
      onmousedown: event => { if (event.target.tagName !== "BUTTON") event.preventDefault(); } });
    bar.append(el("span", { class: "fb-pop-arrow" }),
      el("div", { class: "fb-sel-actions" },
        el("button", { class: "fb-sel-btn", title: "Ask about this text or say what is wrong (opens the comment panel)",
          onmousedown: event => event.preventDefault(), onclick: () => startForm(false), "data-key": "c" }, "💬 Comment"),
        el("button", { class: "fb-sel-btn fb-sel-edit", title: "Suggest new wording for the paragraph(s) with this text",
          onmousedown: event => event.preventDefault(), onclick: () => {
            bar.hidden = true;
            if (pendingSelection) openEditor({ selection: pendingSelection.quote });
          }, "data-key": "e" }, "✎ Edit")),
      el("div", { class: "fb-sel-group" }, el("div", { class: "fb-sel-label" }, "Next run"),
        el("div", { class: "fb-sel-row fb-sel-next" })),
      el("div", { class: "fb-sel-group fb-sel-propose" }, el("div", { class: "fb-sel-label" }, "Propose"),
        el("div", { class: "fb-sel-row fb-pr-row" })),
      el("div", { class: "fb-sel-group" }, el("div", { class: "fb-sel-label" }, "Manuscript"),
        el("div", { class: "fb-sel-row fb-ms-row" })),
      el("div", { class: "fb-sel-hint" }, "One click (or its key) saves a tag · Esc closes"));
    bar.hidden = true;
    document.addEventListener("keydown", event => { if (event.key === "Escape") bar.hidden = true; });
    return bar;
  }
  /* Below the selection, or above it when there is no room below; never over the selected lines. The arrow points
     at the end of the selection (below) or its start (above). */
  function placePopup(range) {
    const rects = [...range.getClientRects()].filter(rect => rect.width > 0);
    const box = range.getBoundingClientRect();
    const anchorBelow = rects.length ? rects[rects.length - 1] : box;
    const anchorAbove = rects.length ? rects[0] : box;
    selectBtn.hidden = false;
    const width = selectBtn.offsetWidth, height = selectBtn.offsetHeight, gap = 10;
    const viewport = document.documentElement.clientWidth, viewHeight = window.innerHeight;
    const below = box.bottom + gap + height <= viewHeight || box.top - gap - height < 0;
    const anchor = below ? anchorBelow : anchorAbove;
    const center = anchor.left + anchor.width / 2;
    const left = Math.max(8, Math.min(viewport - width - 8, center - width / 2));
    selectBtn.style.left = (window.scrollX + left) + "px";
    selectBtn.style.top = (window.scrollY + (below ? box.bottom + gap : box.top - gap - height)) + "px";
    selectBtn.classList.toggle("fb-pop-above", !below);
    selectBtn.querySelector(".fb-pop-arrow").style.left = Math.max(14, Math.min(width - 14, center - left)) + "px";
  }
  function fillSelectionBar() {
    const quick = async name => {
      selectBtn.hidden = true;
      const selection = pendingSelection;
      window.getSelection().removeAllRanges();
      const thread = await tagThread(selection, [name]);
      if (thread) toast("Tagged “" + tagInfo(name).label + "”.", () => retag(thread.thread_id, []));
    };
    const chip = tag => el("button", { class: "fb-qchip fb-tag-" + tag.group, title: tag.help || "",
      onmousedown: event => event.preventDefault(), onclick: () => quick(tag.name) }, tag.label || tag.name);
    selectBtn.querySelector(".fb-sel-next").replaceChildren(...tagsOf("review").map(chip));
    selectBtn.querySelector(".fb-ms-row").replaceChildren(...tagsOf("manuscript").map(chip));
    const offered = proposals();
    selectBtn.querySelector(".fb-sel-propose").hidden = !offered.length;
    selectBtn.querySelector(".fb-pr-row").replaceChildren(...offered.map(tag => el("button", {
      class: "fb-qchip fb-tag-propose", title: tag.help || "", onmousedown: event => event.preventDefault(),
      onclick: () => {
        const selection = pendingSelection;
        window.getSelection().removeAllRanges();
        selectBtn.hidden = true;
        const holder = el("div", { class: "fb-propose-float " + NOT });
        holder.append(proposalForm(tag, selection, () => holder.remove()));
        document.body.append(holder);
      } }, tag.label)));
    selectBtn.dataset.filled = "1";
    selectionKeys();
  }
  /* Keys in the selection popup: c Comment, e Edit, and one letter per tag, the first letter of its label not yet
     taken (else a digit), shown on the chip. While the popup is open a single key belongs to it (kea.js's page keys
     wait); Shift with the arrows still extends the selection, Esc closes. */
  function selectionKeys() {
    const taken = new Set(["c", "e"]);
    for (const button of selectBtn.querySelectorAll(".fb-sel-actions .fb-sel-btn")) badge(button, button.dataset.key);
    let digit = 1;
    for (const chip of selectBtn.querySelectorAll(".fb-sel-next .fb-qchip, .fb-pr-row .fb-qchip, .fb-ms-row .fb-qchip")) {
      const label = chip.textContent.toLowerCase().replace(/^(?:a|an|the)\s+/, "");     // "a premise": from premise
      let key = [...label].find(letter => /[a-z]/.test(letter) && !taken.has(letter));
      if (!key && digit <= 9) key = String(digit++);
      if (!key) continue;
      taken.add(key);
      chip.dataset.key = key;
      badge(chip, key);
    }
  }
  function badge(button, key) {
    if (!key || button.querySelector(".fb-key")) return;
    button.append(el("kbd", { class: "fb-key", "aria-hidden": "true" }, key));
    button.setAttribute("aria-keyshortcuts", key);
  }
  document.addEventListener("keydown", event => {
    if (!selectBtn || selectBtn.hidden || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.target instanceof Element && event.target.closest("input, textarea, select, [contenteditable]")) return;
    if (event.key.length !== 1) return;                       // arrows, Shift, Esc: as before
    event.preventDefault();
    event.stopImmediatePropagation();
    const button = [...selectBtn.querySelectorAll("[data-key]")].find(item => item.dataset.key === event.key.toLowerCase()
      && item.offsetParent !== null);
    if (button) button.click();
  }, true);
  /* What readers said about the page as a whole, as read-only pills next to the title: confirmed (yellow when the page
     changed since), removal asked, the manuscript section, open next-run tags. The controls are in the page popup. */
  function pageLevel() {
    return threads.filter(thread => !thread.quote && (thread.tags || []).length && thread.status !== "resolved");
  }
  function latestWith(name) { return pageLevel().filter(thread => thread.tags.includes(name)).slice(-1)[0]; }
  function pageSection() {
    const names = new Set(tagsOf("manuscript", "page").map(tag => tag.name));
    return pageLevel().filter(thread => thread.status === "marked" && thread.tags.every(name => names.has(name))).slice(-1)[0];
  }
  const shortDate = iso => iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "";
  function renderPageStrip() {
    document.querySelectorAll(".fb-page-pill").forEach(node => node.remove());
    const pills = container && container.querySelector(".kindrow .pills");
    if (!pills || !PAGE.includes(":")) return;
    const add = (cls, text, title) => pills.append(el("span", { class: "pill fb-page-pill " + cls, title: title || "" }, text));
    if (openThread("confirm")) add("fb-pp-ok", "✓ keep as is · waits for Harvest", "A reader asked to keep this page as it is; Claude records the confirmation on the page at the next Harvest");
    if (openThread("unconfirm")) add("fb-pp-stale", "confirmation withdrawn · waits for Harvest");
    const rejected = openThread("drop") || openThread("reject");
    if (rejected) add("fb-pp-remove", "✕ drop asked", "Asked by " + rejected.author + (rejected.text ? ": " + rejected.text : ""));
    const approval = openThread("approve");
    if (approval) add("fb-pp-ok", "✓ signed · waits for Harvest", "Signed off by " + approval.author + " on the site. At the next Harvest Claude writes it onto the page and puts the next step in the plan; nothing runs before Implement.");
    const revision = openThread("revise");
    if (revision) add("fb-pp-next", "↻ revise asked", "Asked by " + revision.author + ": " + (revision.text || ""));
    const section = pageSection();
    if (section) add("fb-pp-ms", "manuscript: " + tagInfo(section.tags[0]).label, "The whole page goes in this part of the manuscript");
    const open = [...new Set(pageLevel().filter(thread => thread.status !== "marked")
      .flatMap(thread => thread.tags).filter(name => tagInfo(name).group === "review"))];
    for (const name of open) add("fb-pp-next", tagInfo(name).label, "Asked for the next run");
    const proposed = [...new Set(pageLevel().filter(thread => thread.status !== "marked")
      .flatMap(thread => thread.tags).filter(name => tagInfo(name).group === "propose"))];
    for (const name of proposed) add("fb-pp-propose", "proposed: " + tagInfo(name).label, "A reader proposed this; it goes into the next plan");
  }

  /* The dock: a column of pill buttons, bottom right, under a small kea head that folds it open and shut (remembered
     across the site). Comment · Edit | Approve (pages that wait) · Revise ▸ · Drop · Propose ▸ | Next run ▸ · Manuscript ▸. The verdicts are definitive
     requests for the next plan; they stay highlighted while pending, and Confirm stays on once the page records it. */
  const DOCK_KEY = "kea-dock-open";
  function dockOpen() { try { return localStorage.getItem(DOCK_KEY) !== "0"; } catch (error) { return true; } }
  function setDockOpen(open) { try { localStorage.setItem(DOCK_KEY, open ? "1" : "0"); } catch (error) { /* private window */ } }
  function openThread(name) {
    return pageLevel().filter(thread => thread.tags.includes(name) && ["open", "planned"].includes(thread.status)).slice(-1)[0];
  }
  function withdraw(thread, note) {
    return sendQuiet(() => api("POST", API + "/" + thread.thread_id + "/status", { status: "resolved", note }));
  }
  const pageConfirmed = () => !!(container && container.querySelector(".node-content[data-confirmed]"));
  const contentData = () => { const content = container && container.querySelector(".node-content"); return content ? content.dataset : {}; };
  const pageVersion = () => contentData().version || "";
  /* The pages that wait for a sign-off, top down through the tree (signing.sign_order, in _build.json, handed over by
     cycle.js's status poll): one Approve signs one page; "Approve & next" then opens the next page still unsigned. */
  const signOrder = () => (((window.keaStatus || {}).build || {}).sign_order || []);
  const signedOnSite = () => new Set((window.keaStatus || {}).signing || []);
  function nextToSign() {
    const order = signOrder(), signed = signedOnSite(), here = order.findIndex(item => item.key === PAGE);
    const open = item => item.key !== PAGE && !signed.has(item.key) && item.href;
    return order.slice(here + 1).find(open) || order.slice(0, Math.max(here, 0)).find(open) || null;
  }
  const goTo = item => { location.href = BASE + (item ? item.href : "progress.html"); };
  /* A group of pills behind one pill (Change ▸, More ▸): opens in place; opening one closes the other. */
  function dockGroup(cls, label, title, members) {
    const box = el("div", { class: "fb-dgroup " + cls });
    const head = el("button", { class: "fb-dpill fb-dgroup-head", title, "aria-expanded": "false", onclick: () => {
      const open = sub.hidden;
      for (const other of document.querySelectorAll(".fb-dgroup")) {
        other.querySelector(".fb-dgroup-items").hidden = true;
        other.querySelector(".fb-dgroup-head").setAttribute("aria-expanded", "false");
      }
      sub.hidden = !open; head.setAttribute("aria-expanded", String(open));
      if (dockPop) dockPop.hidden = true;
    } }, label);
    const sub = el("div", { class: "fb-dgroup-items" }, ...members);
    sub.hidden = true;
    box.append(head, sub);
    return box;
  }
  /* On a page that does not wait: one pill to the first page still waiting for a sign-off (renderSignNav). */
  const toSignPill = () => el("button", { class: "fb-dpill fb-d-tosign", hidden: "" });
  function buildDock() {
    const dock = el("div", { class: "fb-dock " + NOT });
    const items = el("div", { class: "fb-dock-items" });
    const pill = (cls, label, title, onclick) => el("button", { class: "fb-dpill " + cls, title, onclick }, label);
    toggleBtn = pill("fb-d-comment", "💬 Comment", "Comments on this page", () =>
      panel.classList.contains("fb-open") ? closePanel() : openPanel());
    const edit = pill("fb-d-edit", "✎ Edit", "Edit the page: title, summary and text (saved as a suggestion)", () => openEditor(null));
    edit.hidden = true;
    items.append(toggleBtn, edit);
    if (PAGE.includes(":")) {
      /* Comment · ✓ Approve (on a page that waits; a settled page has none) · Change ▸ (Edit,
         Revise, Drop) · More ▸ (Propose, Next run, Manuscript): two groups that open in place, one at a time.
         Every button records a request; nothing changes on the site before a Harvest and an Implement. */
      const confirm = pill("fb-d-confirm", "✓ Keep as is", "", () => {});
      const revise = pill("fb-d-revise", "↻ Revise ▸", "Rewrite this page: say what to change; this branch is reworked", () => toggleDockPop(revise, "revise"));
      const reject = pill("fb-d-reject", "✕ Drop", "", () => {});
      const next = pill("fb-d-next", "Next run ▸", "Ask for work on the whole page in the next run", () => toggleDockPop(next, "review"));
      const manuscript = pill("fb-d-ms", "Manuscript ▸", "Which part of the manuscript the whole page belongs in", () => toggleDockPop(manuscript, "manuscript"));
      const propose = pill("fb-d-propose", "Propose ▸", "Propose the next step of the reasoning: a question, hypothesis, step, conclusion, caveat …", () => toggleDockPop(propose, "propose"));
      items.querySelector(".fb-d-edit").remove();
      const change = dockGroup("fb-d-change", "Change ▸", "Edit the text, ask Claude to revise the page, or drop it", [edit, revise, reject]);
      const more = dockGroup("fb-d-more", "More ▸", "Propose a next step, ask for work in the next run, or place the page in the manuscript", [propose, next, manuscript]);
      // ‹ 2 of 7 ›: the pages that wait for a sign-off, top down (shown on such a page)
      const signNav = el("div", { class: "fb-signnav", hidden: "" },
        el("button", { class: "fb-dpill fb-sn-prev", title: "The page before this one in the sign-off order" }, "‹"),
        el("span", { class: "fb-sn-where" }),
        el("button", { class: "fb-dpill fb-sn-next", title: "The next page to sign" }, "›"));
      items.append(el("span", { class: "fb-dock-gap" }), signNav, toSignPill(), confirm, change, more);
    } else {
      // the project's front page: propose an experiment (renderDock hides the button where nothing can be proposed)
      const propose = pill("fb-d-propose", "Propose ▸", "Propose a new experiment for this project", () => toggleDockPop(propose, "propose"));
      items.append(el("span", { class: "fb-dock-gap" }), toSignPill(), propose);
    }
    const head = el("button", { class: "fb-dock-head", title: "Show or hide the page buttons", "aria-expanded": "true",
      onclick: () => { const open = items.hidden; items.hidden = !open; head.setAttribute("aria-expanded", String(open));
        if (!window.matchMedia("(max-width: 760px)").matches) setDockOpen(open); dockPop.hidden = true; } },
      el("img", { src: BASE + "_assets/kea-badge-96.png", alt: "Kea", width: "46", height: "46" }));
    const fold = () => { if (items.hidden) return; items.hidden = true; head.setAttribute("aria-expanded", "false"); dockPop.hidden = true; };
    // phones: the buttons cover the text, so the dock starts folded and folds again on a scroll or a tap elsewhere
    // (the stored choice holds on wide screens only)
    const small = window.matchMedia("(max-width: 760px)").matches;
    items.hidden = small || !dockOpen();
    head.setAttribute("aria-expanded", String(!items.hidden));
    if (small) {
      let lastY = window.scrollY;
      window.addEventListener("scroll", () => { if (Math.abs(window.scrollY - lastY) > 40 && dockPop.hidden) fold(); lastY = window.scrollY; }, { passive: true });
      document.addEventListener("pointerdown", event => { if (!dock.contains(event.target) && !dockPop.contains(event.target)) fold(); });
    }
    dock.append(head, items);                  // the head on top of the column; folded, it drops to the corner
    return dock;
  }
  /* Refresh the dock's states from the threads (after every reload). */
  function renderDock() {
    if (!dockEl) return;
    const edit = dockEl.querySelector(".fb-d-edit");
    if (edit) edit.hidden = !editable;
    const propose = dockEl.querySelector(".fb-d-propose");
    if (propose) propose.hidden = !proposals().length;
    const confirm = dockEl.querySelector(".fb-d-confirm"), reject = dockEl.querySelector(".fb-d-reject");
    if (!confirm) { renderSignNav(false); return; }
    const content = container && container.querySelector(".node-content");
    const waitingPage = !!(content && content.dataset.waiting);           // pace: guided, not yet approved
    const dropAlso = content ? content.dataset.drop || "" : "";
    const asked = openThread(waitingPage ? "approve" : "confirm"), unasked = openThread("unconfirm");
    // signed on another page with a Signs: line (Approve all, 1.29-1.31.0): nothing to click here; it waits for the harvest
    const signedWith = waitingPage && !asked && ((window.keaStatus || {}).signing || []).includes(PAGE);
    const dropped = openThread("drop") || openThread("reject"), revising = openThread("revise");
    const done = !waitingPage && pageConfirmed();
    // every verdict waits for the harvest: Claude records sign-offs then and plans the rest; nothing runs before Implement
    const when = "at the next Harvest";
    const word = waitingPage ? "Approve" : "Keep as is";
    const following = waitingPage ? nextToSign() : null;    // the next page to sign, top down
    const then = " Nothing else starts: the next step goes into the plan at the Harvest and runs only when a PI presses Implement.";
    confirm.className = "fb-dpill fb-d-confirm" + (done && !unasked ? " fb-active" : asked || signedWith ? " fb-pending"
      : unasked ? " fb-pending-off" : waitingPage ? " fb-main" : "");
    if (asked || signedWith) {
      confirm.textContent = waitingPage ? "✓ Signed · waits for Harvest" : "✓ Keep as is · waits for Harvest";
      confirm.title = signedWith ? "Signed on another page. Claude writes it onto this page at the next Harvest."
        : "a d · " + (waitingPage ? `Signed: written onto the page ${when}. Click to take it back.` : `Recorded: written onto the page ${when}, nothing else changes. Click to take it back.`);
    } else if (unasked) {
      confirm.textContent = "✓ Withdrawn · waits for Harvest";
      confirm.title = "Claude removes the confirmation at the next Harvest; click to keep it after all";
    } else if (done) {
      confirm.textContent = "✓ Confirmed";
      confirm.title = "This page is confirmed as it is; click to withdraw the confirmation (done at the next Harvest)";
    } else if (waitingPage) {
      confirm.textContent = following ? "✓ Approve & next →" : "✓ Approve";
      confirm.title = (following ? "a n · " : "a a · ") + `Sign off on this page${pageVersion() ? " (version " + pageVersion() + ")" : ""}`
        + (following ? `, then open ${following.label ? following.label + " " : ""}${following.title}` : "")
        + `. Written onto the page ${when}; nothing starts.` + (following ? " a a: this page only." : "");
    } else {
      confirm.textContent = "✓ " + word;
      confirm.title = "This page is settled. Say it is right as it is: Claude records your confirmation on the page at the next Harvest and changes nothing. Nothing else starts.";
    }
    // a settled page has no green button: it is signed already, or never waited; only an old confirmation request
    // (before 1.31.3) still shows, so it can be taken back
    confirm.hidden = !waitingPage && !asked && !unasked;
    confirm.onclick = async () => {
      if (signedWith) return;
      if (asked) return withdraw(asked, (waitingPage ? "approval" : "confirmation") + " taken back");
      if (unasked) return withdraw(unasked, "withdrawal taken back");
      if (done) { if (confirm_("Withdraw the confirmation of this page? Claude removes it at the next Harvest.")) await tagThread(null, ["unconfirm"]); return; }
      if (dropped) await withdraw(dropped, "drop replaced by " + word.toLowerCase());
      const made = await tagThread(null, [waitingPage ? "approve" : "confirm"]);
      if (made && waitingPage) {
        const left = nextToSign();
        if (!left) toast("Signed. Every page that waited is signed now: next, a PI presses Harvest.");
        setTimeout(() => goTo(left), left ? 400 : 1600);         // top down: the next page to sign, or Progress
      }
    };
    renderSignNav(waitingPage);
    const revise = dockEl.querySelector(".fb-d-revise");
    const soon = "waits for Harvest";
    revise.className = "fb-dpill fb-d-revise" + (revising ? " fb-pending" : "");
    revise.textContent = revising ? "↻ Revise · " + soon : "↻ Revise ▸";
    reject.className = "fb-dpill fb-d-reject" + (dropped ? " fb-pending" : "");
    reject.textContent = dropped ? "✕ Drop · " + soon : "✕ Drop";
    const change = dockEl.querySelector(".fb-d-change .fb-dgroup-head");
    if (change) {
      change.textContent = revising ? "Change · revise " + soon : dropped ? "Change · drop " + soon : "Change ▸";
      change.classList.toggle("fb-pending", !!(revising || dropped));
    }
    reject.title = dropped ? "Drop asked: it goes into the plan at the next Harvest and is done at Implement; click to take it back"
      : "Remove this page" + (dropAlso ? " and the pages that rest only on it (" + dropAlso + ")" : "") + "; it goes into the next plan and is done at Implement";
    reject.onclick = async () => {
      if (dropped) return withdraw(dropped, "drop taken back");
      const also = dropAlso ? `\n\nThis also removes the pages that rest only on it: ${dropAlso}.` : "";
      const why = prompt(`Drop this page? It goes into the plan at the next Harvest and is removed at Implement.${also}\n\nWhy (optional):`);
      if (why === null) return;
      if (asked) await withdraw(asked, (waitingPage ? "approval" : "confirmation") + " replaced by a drop");
      await tagThread(null, ["drop"], why.trim());
    };
    const nextCount = new Set(pageLevel().filter(thread => thread.status !== "marked").flatMap(thread => thread.tags)
      .filter(name => tagInfo(name).group === "review")).size;
    dockEl.querySelector(".fb-d-next").textContent = "Next run" + (nextCount ? " · " + nextCount : "") + " ▸";
    const section = pageSection();
    dockEl.querySelector(".fb-d-ms").textContent = "Manuscript" + (section ? ": " + tagInfo(section.tags[0]).label : "") + " ▸";
    const more = dockEl.querySelector(".fb-d-more .fb-dgroup-head");
    const marked = nextCount + (section ? 1 : 0);
    if (more) more.textContent = "More" + (marked ? " · " + marked : "") + " ▸";
    if (!dockPop.hidden) fillDockPop();
  }
  /* ‹ n of N ›: where this page is in the sign-off order, with the pages before and after it. */
  function renderSignNav(waitingPage) {
    const order = signOrder(), here = order.findIndex(item => item.key === PAGE);
    const toSign = dockEl && dockEl.querySelector(".fb-d-tosign");
    if (toSign) {
      const signed = signedOnSite(), open = order.filter(item => item.href && !signed.has(item.key));
      toSign.hidden = !!waitingPage || !open.length || readOnly;
      if (!toSign.hidden) {
        toSign.textContent = `Needs attention (${open.length}) →`;
        toSign.title = `${open.length} page${open.length === 1 ? " needs" : "s need"} your attention: a sign-off, or a new look because a page `
          + `${open.length === 1 ? "it is" : "they are"} built on changed. Top down through the tree. `
          + `Open the first: ${open[0].label ? open[0].label + " " : ""}${open[0].title}`;
        toSign.onclick = () => goTo(open[0]);
      }
    }
    const nav = dockEl && dockEl.querySelector(".fb-signnav");
    if (!nav) return;
    nav.hidden = !waitingPage || here < 0 || order.length < 2;
    if (nav.hidden) return;
    const signed = signedOnSite();
    const left = order.filter(item => !signed.has(item.key)).length;
    nav.querySelector(".fb-sn-where").textContent = `${here + 1} of ${order.length}` + (left < order.length ? ` · ${left} to sign` : "");
    const prev = order[here - 1], next = order[here + 1];
    const prevButton = nav.querySelector(".fb-sn-prev"), nextButton = nav.querySelector(".fb-sn-next");
    prevButton.disabled = !prev; nextButton.disabled = !next;
    prevButton.title = prev ? `Previous: ${prev.label ? prev.label + " " : ""}${prev.title}` : "This is the first page to sign";
    nextButton.title = next ? `Next: ${next.label ? next.label + " " : ""}${next.title}` : "This is the last page to sign";
    prevButton.onclick = () => prev && goTo(prev);
    nextButton.onclick = () => next && goTo(next);
  }
  // the status poll (cycle.js) hands over the sign-off order and the pages signed on the site
  window.addEventListener("kea-status", () => renderDock());

  /* Keyboard (kea.js): the page's actions behind "a", grouped as the dock is (sign-off · Change · More), each doing
     exactly what its button does; and N/P, the pages that need attention. A key never signs more than this page,
     and nothing starts: like a click, a sign-off waits for the Harvest. */
  function pressPill(cls) {
    const pill = dockEl && dockEl.querySelector("." + cls);
    if (!pill || pill.hidden) return;
    const items = dockEl.querySelector(".fb-dock-items");
    if (items.hidden) dockEl.querySelector(".fb-dock-head").click();
    const group = pill.closest(".fb-dgroup");
    if (group && group.querySelector(".fb-dgroup-items").hidden) group.querySelector(".fb-dgroup-head").click();
    pill.click();
  }
  const pillThere = cls => !!(dockEl && dockEl.querySelector("." + cls) && !dockEl.querySelector("." + cls).hidden);
  function signState() {
    const content = container && container.querySelector(".node-content");
    const waitingPage = !!(content && content.dataset.waiting);
    const asked = openThread("approve");
    const signedWith = waitingPage && !asked && ((window.keaStatus || {}).signing || []).includes(PAGE);
    return { waitingPage, asked, signedWith, canSign: waitingPage && !asked && !signedWith && !readOnly && !!dockEl };
  }
  async function approveByKey(andNext) {
    const state = signState();
    if (!state.canSign) return;
    const dropped = openThread("drop") || openThread("reject");
    if (dropped) await withdraw(dropped, "drop replaced by approve");
    const made = await tagThread(null, ["approve"]);
    if (!made) return;
    const left = nextToSign();
    if (andNext) {
      if (!left) toast("Signed. Every page that waited is signed now: next, a PI presses Harvest.");
      setTimeout(() => goTo(left), left ? 400 : 1600);
    } else toast("Approved: Claude writes the sign-off onto the page at the next Harvest. a then d takes it back.");
  }
  const titleNode = () => container && container.querySelector(".node-content h1 .node-title");
  const shortNode = () => container && container.querySelector(".node-content .short");
  window.keaPageActions = function () {
    if (!PAGE.includes(":")) return [];
    const state = signState(), following = state.waitingPage ? nextToSign() : null;
    const name = item => item ? (item.label ? item.label + " " : "") + item.title : "";
    return [
      ["Sign-off", [
        ["a", "Approve this page (only this one)", state.canSign, () => approveByKey(false)],
        ["n", "Approve &amp; next" + (following ? ": then open " + name(following) : ""), state.canSign, () => approveByKey(true)],
        ["d", "Take back my Approve (before the Harvest)", !!state.asked && !readOnly,
         () => withdraw(state.asked, "approval taken back")],
      ]],
      ["Change", [
        ["t", "Edit the title", editable && !!titleNode(), () => editInPlace(titleNode(), "title")],
        ["s", "Edit the summary", editable && !!shortNode(), () => editInPlace(shortNode(), "short")],
        ["p", "Edit the page: title, summary and text", editable, () => openEditor(null)],
        ["r", "Revise: ask Claude to rewrite it …", pillThere("fb-d-revise"), () => pressPill("fb-d-revise")],
        ["x", "Drop the page …", pillThere("fb-d-reject"), () => pressPill("fb-d-reject")],
      ]],
      ["More", [
        ["c", "Comment on the page (the cursor goes in the box)", pillThere("fb-d-comment"), () => commentByKey(false)],
        ["+", "Propose a next step …", pillThere("fb-d-propose"), () => pressPill("fb-d-propose")],
        ["w", "Work for the next run …", pillThere("fb-d-next"), () => pressPill("fb-d-next")],
        ["m", "Manuscript: where the page belongs …", pillThere("fb-d-ms"), () => pressPill("fb-d-ms")],
      ]],
    ];
  };
  /* N / P: the next or previous page of this round's attention list, top down (wraps around), including the pages
     approved on the site since the Harvest; from a page outside the list, the nearest one in the reading order. */
  window.keaAttention = function (step, reading) {
    // this round's list, pages approved since the last Harvest included (kea.js's bar shows them green)
    const order = signOrder(), open = order.filter(item => item.href);
    const others = open.filter(item => item.key !== PAGE);
    if (!others.length) return null;
    const here = open.findIndex(item => item.key === PAGE);
    if (here >= 0) return open[(here + step + open.length) % open.length];
    // this page is not in the list: the nearest one after (before) it in the reading order (kea.js passes the keys)
    const position = key => (reading || []).indexOf(key), mine = position(PAGE);
    if (mine >= 0) {
      const after = others.filter(item => position(item.key) > mine), before = others.filter(item => position(item.key) < mine);
      if (step > 0) return after[0] || others[0];
      return before[before.length - 1] || others[others.length - 1];
    }
    return step > 0 ? others[0] : others[others.length - 1];
  };
  window.keaGoTo = item => goTo(item);
  const confirm_ = text => window.confirm(text);
  /* The popup of Next run / Manuscript chips, to the left of its pill. */
  let dockPop = null, dockPopGroup = "", dockPopAnchor = null;
  function toggleDockPop(anchor, group) {
    if (!dockPop.hidden && dockPopGroup === group) { dockPop.hidden = true; return; }
    dockPopGroup = group; dockPopAnchor = anchor;
    fillDockPop();
  }
  function fillDockPop() {
    const chip = (tag, active, onclick) => el("button", { class: "fb-qchip fb-tag-" + tag.group + (active ? " fb-on" : ""),
      title: tag.help || "", "aria-pressed": String(!!active), onclick }, (active ? "✓ " : "") + (tag.label || tag.name));
    let chips;
    if (dockPopGroup === "revise") {
      const revising = openThread("revise");
      const tag = tagInfo("revise");
      dockPop.replaceChildren(revising
        ? el("div", { class: "fb-propose" }, el("div", { class: "fb-sel-label" }, "Revise · asked"),
            el("div", {}, revising.text || ""),
            el("div", { class: "fb-propose-actions" }, el("button", { class: "fb-secondary", onclick: async () => {
              dockPop.hidden = true; await withdraw(revising, "revision taken back"); } }, "Take it back")))
        : proposalForm({ ...tag, label: "", help: "What should change, and why? The page is rewritten; pages that rest on it are rechecked." },
            null, () => { dockPop.hidden = true; }, "Revise this page"));
      dockPop.hidden = false;
      placeDockPop();
      return;
    }
    if (dockPopGroup === "propose") {
      const place = placeDockPop;
      const options = proposals().map(tag => el("button", { class: "fb-qchip fb-tag-propose", title: tag.help || "",
        onclick: () => { dockPop.replaceChildren(proposalForm(tag, null, () => { dockPop.hidden = true; })); place(); } }, tag.label));
      dockPop.replaceChildren(el("div", { class: "fb-sel-label" }, "Propose · whole page"),
        options.length ? el("div", { class: "fb-sel-row" }, ...options)
          : el("div", { class: "fb-help" }, "Nothing to propose on this kind of page; comment instead."));
      dockPop.hidden = false;
      place();
      return;
    }
    if (dockPopGroup === "review") {
      const asked = new Map();
      for (const thread of pageLevel()) if (thread.status !== "marked") for (const name of thread.tags) asked.set(name, thread);
      chips = tagsOf("review", "page").map(tag => {
        const thread = asked.get(tag.name);
        return chip(tag, !!thread, () => thread ? retag(thread.thread_id, thread.tags.filter(name => name !== tag.name))
          : tagThread(null, [tag.name]));
      });
    } else {
      const section = pageSection();
      chips = tagsOf("manuscript", "page").map(tag => {
        const active = section && section.tags[0] === tag.name;
        return chip(tag, active, () => section ? retag(section.thread_id, active ? [] : [tag.name]) : tagThread(null, [tag.name]));
      });
    }
    dockPop.replaceChildren(el("div", { class: "fb-sel-label" }, dockPopGroup === "review" ? "Next run · whole page" : "Manuscript · whole page"),
      el("div", { class: "fb-sel-row" }, ...chips));
    dockPop.hidden = false;
    placeDockPop();
  }
  /* Beside the dock, level with its pill, where there is room; on a phone (or wherever it would run off the screen
     on the left) a sheet across the bottom of the screen, above the dock, that scrolls when it is long. */
  function placeDockPop() {
    const width = document.documentElement.clientWidth;
    const dockLeft = dockEl.querySelector(".fb-dock-items").getBoundingClientRect().left;
    const rect = dockPopAnchor.getBoundingClientRect();
    dockPop.classList.remove("fb-dock-sheet");
    Object.assign(dockPop.style, { left: "", right: (width - dockLeft + 10) + "px", bottom: Math.max(8, window.innerHeight - rect.bottom) + "px" });
    if (width <= 760 || dockPop.getBoundingClientRect().left < 8) {
      dockPop.classList.add("fb-dock-sheet");
      if (!dockPop.querySelector(".fb-sheet-close"))
        dockPop.append(el("button", { class: "fb-sheet-close", title: "Close", "aria-label": "Close", onclick: () => { dockPop.hidden = true; } }, "×"));
      Object.assign(dockPop.style, { left: "8px", right: "8px", bottom: "8px" });
    }
  }

  /* In-place edits of the title and the summary: a pencil on hover; the new text is saved as a suggested edit. */
  function inlineEditors() {
    const targets = [[container.querySelector(".node-content h1 .node-title"), "title"],
                     [container.querySelector(".node-content .short"), "short"]];
    for (const [node, key] of targets) {
      if (!node || node.dataset.inline) continue;
      node.dataset.inline = "1";
      const holder = key === "title" ? node.parentElement : node;
      holder.classList.add("fb-inline-host");
      const button = el("button", { class: "fb-inline-pencil " + NOT, title: "Edit the " + (key === "title" ? "title" : "summary") + " here",
        onclick: event => { event.preventDefault(); editInPlace(node, key); } });
      button.innerHTML = PENCIL;
      if (key === "title") node.after(button);
      else node.append(button);
    }
    // the kind above the title ("Question Q1"): a pencil on hover opens the editor of the whole page
    const kind = container.querySelector(".node-content .kindrow .kind");
    if (kind && !kind.dataset.inline) {
      kind.dataset.inline = "1";
      const button = el("button", { class: "fb-kind-pencil " + NOT, title: "Edit the whole page: title, summary and text",
        onclick: event => { event.preventDefault(); openEditor(null); } });
      button.innerHTML = PENCIL;
      kind.append(button);
    }
  }
  function editInPlace(node, key) {
    if (node.parentElement.querySelector(".fb-inline-form")) return;
    const field = key === "title" ? el("input", { class: "fb-inline-input fb-ed-title" })
      : el("textarea", { class: "fb-inline-input fb-ed-short", rows: "3" });
    field.value = node.textContent.trim();
    const status = el("span", { class: "fb-help" });
    const form = el("div", { class: "fb-inline-form " + NOT }, field, el("div", { class: "fb-actions" },
      el("button", { onclick: async () => {
        const value = field.value.replace(/\s+/g, " ").trim();
        if (!value || value === node.textContent.trim()) { form.remove(); node.hidden = false; return; }
        try {
          const source = await api("GET", BASE + "api/source?page=" + encodeURIComponent(PAGE));
          const [front, body] = splitFrontMatter(source.text);
          const newText = "---\n" + withField(front, key, value) + "\n---\n" + body;
          if (!getName()) { const name = (prompt("Your name (shown with your suggestion):") || "").trim(); if (!name) return; setName(name); }
          await api("POST", BASE + "api/suggest", { page: PAGE, page_title: TITLE, new_text: newText,
            text: "New " + (key === "title" ? "title" : "summary") + " (edited in place)." });
          form.remove(); node.hidden = false;
          await reload();
          toast("Saved as a suggested edit; Claude takes it into the next plan.");
        } catch (error) { status.textContent = error.message; }
      } }, "Save as suggestion"),
      el("button", { class: "fb-secondary", onclick: () => { form.remove(); node.hidden = false; } }, "Cancel"), status));
    field.addEventListener("keydown", event => {
      if (event.key === "Escape") { form.remove(); node.hidden = false; }
      if (event.key === "Enter" && key === "title") { event.preventDefault(); form.querySelector("button").click(); }
    });
    node.hidden = true;
    node.after(form);
    if (key === "title") node.parentElement.after(form);
    field.focus(); field.select();
  }

  /* The lines of the page's Markdown that hold a selected passage: whole paragraphs (blank-line blocks, code fences
     kept whole, each front-matter line on its own), found by the first and last words of the selection. */
  function plainOf(text) {
    return text.replace(/\[\[([^\]|]+)(?:\|([^\]|]*))?(?:\|[^\]]*)?\]\]/g, (all, target, label) => label || target)
      .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/^\s*([-*+]|\d+\.)\s+/gm, "").replace(/[*_`#>|]/g, " ")
      .replace(/\s+/g, " ").trim().toLowerCase();
  }
  function selectionRange(text, quote) {
    const lines = text.split("\n");
    const blocks = [];
    let i = 0;
    if (lines[0] === "---") {
      const close = lines.indexOf("---", 1);
      if (close > 0) { for (let k = 1; k < close; k++) blocks.push([k, k + 1]); i = close + 1; }
    }
    while (i < lines.length) {
      if (!lines[i].trim()) { i++; continue; }
      let j = i;
      if (/^(```|~~~)/.test(lines[i])) { j = i + 1; while (j < lines.length && !/^(```|~~~)/.test(lines[j])) j++; j++; }
      else { while (j < lines.length && lines[j].trim() && !(j > i && /^(```|~~~)/.test(lines[j]))) j++; }
      blocks.push([i, Math.min(j, lines.length)]);
      i = j;
    }
    const plain = blocks.map(([from, to]) => plainOf(lines.slice(from, to).join("\n")));
    const words = plainOf(quote).split(" ").filter(Boolean);
    if (!words.length) return null;
    const find = (probe, from) => {
      for (let n = Math.min(6, probe.length); n >= 2; n--) {
        const part = probe.slice(0, n).join(" ");
        const index = plain.findIndex((block, k) => k >= from && block.includes(part));
        if (index >= 0) return index;
      }
      return -1;
    };
    let first = find(words, 0);
    const frontBlocks = lines[0] === "---" ? Math.max(0, lines.indexOf("---", 1) - 1) : 0;
    if (first >= 0 && first < frontBlocks) return "front";     // title or summary: edited in their own fields
    if (first < 0) {                             // starts in generated text (a link label): most shared words
      let best = -1, score = 0;
      plain.forEach((block, k) => { const hits = words.filter(word => block.includes(word)).length; if (hits > score) { score = hits; best = k; } });
      if (best < 0 || score < Math.min(3, words.length)) return null;
      first = best;
    }
    let last = first;                           // the block with the last words (else the first block only)
    const tail = words.slice(-Math.min(6, words.length)).join(" ");
    const tailIndex = plain.findIndex((block, k) => k >= first && block.includes(tail));
    if (tailIndex >= 0) last = tailIndex;
    const from = blocks[first][0], to = blocks[last][1];
    return [lines.slice(0, from).join("\n"), lines.slice(from, to).join("\n"), lines.slice(to).join("\n")];
  }

  // ---------- panel ----------
  function statusPill(status, thread) {
    if (thread && thread.state_label) return el("span", { class: "fb-pill fb-state-" + stateOf(thread) }, thread.state_label);
    return el("span", { class: "fb-pill fb-s-" + status }, STATUS_TEXT[status] || status);
  }
  function messageView(author, text, createdAt, isQuestion) {
    return el("div", { class: "fb-msg" + (author === "claude" ? " fb-claude" : "") },
      el("div", { class: "fb-meta" }, el("b", {}, author === "claude" ? "Claude" : author), " · ", when(createdAt),
        isQuestion ? "" : ""),
      el("div", { class: "fb-text" }, text));
  }
  function diffView(suggestion) {
    const lines = (suggestion.diff || "").split("\n").filter(line => !line.startsWith("---") && !line.startsWith("+++"));
    const pre = el("pre", { class: "fb-diff" }, ...lines.map(line => el("span", {
      class: line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : line.startsWith("@@") ? "hunk" : "ctx" }, line || " ")));  // block spans: no "\n" (it would add a blank line)
    return el("details", { class: "fb-suggestion", open: "open" },
      el("summary", {}, "Suggested edit of ", el("code", {}, suggestion.path), " (version ", suggestion.base_commit || "?", ")"), pre);
  }

  // ---------- suggested edits: the page's Markdown in an editor; saved as a thread with the diff ----------
  let markedLoading = null;
  function loadMarked() {
    if (window.marked) return Promise.resolve();
    if (!markedLoading) markedLoading = new Promise((resolve, reject) => {
      const tag = document.createElement("script");
      tag.src = ASSET_BASE + "marked-12.0.2.min.js"; tag.onload = resolve; tag.onerror = reject;
      document.head.append(tag);
    });
    return markedLoading;
  }
  function splitFrontMatter(text) {
    const match = text.match(/^---\n([\s\S]*?)\n---\n?/);
    return match ? [match[1], text.slice(match[0].length)] : ["", text];
  }
  // The nth "## " heading of the Markdown body (outside code fences) to the next "## " or "# " heading: the
  // section that the nth <h2> inside the page's <article> elements shows.
  function sectionRange(text, index) {
    const lines = text.split("\n");
    let first = 0;
    if (lines[0] === "---") { const close = lines.indexOf("---", 1); if (close > 0) first = close + 1; }
    let fence = false, count = -1, start = -1, end = lines.length;
    for (let i = first; i < lines.length; i++) {
      if (/^(```|~~~)/.test(lines[i])) fence = !fence;
      if (fence) continue;
      if (/^## /.test(lines[i])) {
        count++;
        if (count === index) start = i;
        else if (start >= 0) { end = i; break; }
      } else if (start >= 0 && /^# /.test(lines[i])) { end = i; break; }
    }
    if (start < 0) return null;
    return [lines.slice(0, start).join("\n"), lines.slice(start, end).join("\n"), lines.slice(end).join("\n")];
  }
  const PENCIL = '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" '
    + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/>'
    + '<path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>';
  function addEditButtons() {
    // the whole-page Edit is in the page popup ("This page"); title and summary are edited in place
    inlineEditors();
    document.querySelectorAll("main article h2").forEach((heading, index) => {
      if (heading.querySelector(".fb-sec-edit")) return;
      const button = el("button", { class: "fb-sec-edit " + NOT, title: "Edit just this section (saved as a suggestion)",
        onclick: event => { event.preventDefault(); openEditor({ index, title: heading.textContent.trim() }); } });
      button.innerHTML = PENCIL;                 // icon only, right after the heading text (no wrap, no new line)
      const holder = el("span", { class: "fb-sec-holder " + NOT });
      holder.append(button);
      heading.append(holder);
    });
  }
  // ---------- front matter: read and replace single fields (title, short) without touching the rest ----------
  function fieldRange(front, key) {
    // [first line, end line) of `key:` and its indented continuation lines in the front matter's lines
    const lines = front.split("\n");
    const start = lines.findIndex(line => line.startsWith(key + ":"));
    if (start < 0) return null;
    let end = start + 1;
    while (end < lines.length && /^\s+\S/.test(lines[end])) end++;
    return [start, end, lines];
  }
  function fieldValue(front, key) {
    const found = fieldRange(front, key);
    if (!found) return "";
    const [start, end, lines] = found;
    let first = lines[start].slice(key.length + 1).trim();
    const rest = lines.slice(start + 1, end).map(line => line.trim());
    if (/^[>|][+-]?$/.test(first)) return rest.join(first[0] === ">" ? " " : "\n");
    const text = [first, ...rest].join(" ");
    if (text.startsWith('"')) { try { return JSON.parse(text); } catch (error) { return text.slice(1, -1); } }
    if (text.startsWith("'")) return text.slice(1, -1).replace(/''/g, "'");
    return text;
  }
  function yamlValue(value) {
    const plain = value && !/^[\s'"{}\[\]>|*&!%@`#?,:-]/.test(value) && !/(: | #|\s$)/.test(value) && !value.includes("\n");
    return plain ? value : JSON.stringify(value);      // JSON strings are valid YAML double-quoted scalars
  }
  function withField(front, key, value) {
    if (fieldValue(front, key) === value) return front;   // unchanged: keep the original lines (no diff noise)
    const found = fieldRange(front, key);
    const line = key + ": " + yamlValue(value);
    if (!found) return front + "\n" + line;
    const [start, end, lines] = found;
    return [...lines.slice(0, start), line, ...lines.slice(end)].join("\n");
  }

  // ---------- minimal Markdown highlighting: a coloured copy behind a transparent textarea ----------
  function escapeHtml(text) { return text.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]); }
  function highlightInline(line) {
    return escapeHtml(line)
      .replace(/(`[^`]+`)/g, "<span class='hl-code'>$1</span>")
      .replace(/(\[\[[^\]]+\]\])/g, "<span class='hl-link'>$1</span>")
      .replace(/(\[[^\]]+\]\([^)]+\))/g, "<span class='hl-link'>$1</span>")
      .replace(/(\*\*[^*]+\*\*|__[^_]+__)/g, "<b>$1</b>")
      .replace(/(^|[^*\w])(\*[^*\s][^*]*\*|_[^_\s][^_]*_)(?=[^*\w]|$)/g, "$1<i>$2</i>");
  }
  function highlightMarkdown(text) {
    const lines = text.split("\n");
    let inFront = lines[0] === "---", fence = false;
    return lines.map((line, index) => {
      if (inFront) {
        if (index > 0 && line === "---") { inFront = false; return "<span class='hl-meta'>---</span>"; }
        if (index === 0) return "<span class='hl-meta'>---</span>";
        const match = line.match(/^(\s*[\w-]+:)(.*)$/);
        return match ? "<span class='hl-key'>" + escapeHtml(match[1]) + "</span>" + escapeHtml(match[2]) : escapeHtml(line);
      }
      if (/^(```|~~~)/.test(line)) { fence = !fence; return "<span class='hl-code'>" + escapeHtml(line) + "</span>"; }
      if (fence) return "<span class='hl-code'>" + escapeHtml(line) + "</span>";
      if (/^#{1,6}\s/.test(line)) return "<span class='hl-head'>" + escapeHtml(line) + "</span>";
      const list = line.match(/^(\s*(?:[-*+]|\d+\.)\s)(.*)$/);
      if (list) return "<span class='hl-mark'>" + escapeHtml(list[1]) + "</span>" + highlightInline(list[2]);
      if (/^\s*>/.test(line)) return "<span class='hl-quote'>" + highlightInline(line) + "</span>";
      return highlightInline(line);
    }).join("\n") + "\n";
  }
  function markdownArea(value, rows) {
    const back = el("pre", { class: "fb-hl-back", "aria-hidden": "true" });
    const area = el("textarea", { class: "fb-hl-text", spellcheck: "true" });
    if (rows) area.rows = rows;
    const box = el("div", { class: "fb-hl" + (rows ? " fb-hl-small" : "") }, back, area);
    const paint = () => { back.innerHTML = highlightMarkdown(area.value); back.scrollTop = area.scrollTop; back.scrollLeft = area.scrollLeft; };
    area.addEventListener("input", paint);
    area.addEventListener("scroll", () => { back.scrollTop = area.scrollTop; back.scrollLeft = area.scrollLeft; });
    area.value = value;
    paint();
    return { box, area, paint, get value() { return area.value; }, set value(text) { area.value = text; paint(); } };
  }

  /* The editor. Whole page: "Text" mode (title, summary and the body; the type, id, parent, status and relations stay
     as they are) or "Raw Markdown" (the whole file with its front matter). A section or passage: its Markdown only. */
  async function openEditor(section) {
    let source;
    try { source = await api("GET", BASE + "api/source?page=" + encodeURIComponent(PAGE)); }
    catch (error) { alert(error.message); return; }
    await loadMarked().catch(() => null);
    let before = "", after = "", original = source.text, focusField = null;
    if (section) {
      const parts = section.selection !== undefined ? selectionRange(source.text, section.selection)
        : sectionRange(source.text, section.index);
      if (parts === "front") { section = null; focusField = "short"; }    // the selection is the title or summary
      else if (!parts) { alert("This " + (section.selection !== undefined ? "passage" : "section") + " could not be found in the page's Markdown; the whole page opens instead."); section = null; }
      else { [before, original, after] = parts; }
    }
    const wholePage = !section;
    const [frontStart, bodyStart] = splitFrontMatter(source.text);
    let front = frontStart;
    let mode = "text";
    const titleBox = el("input", { class: "fb-ed-title", placeholder: "Title" });
    const shortBox = el("textarea", { class: "fb-ed-short", rows: "3", placeholder: "Summary: one or two sentences for the reader" });
    titleBox.value = fieldValue(front, "title");
    shortBox.value = fieldValue(front, "short");
    const body = markdownArea(wholePage ? bodyStart.replace(/^\n/, "") : original);
    const raw = markdownArea(source.text);
    const bodyLead = wholePage && /^\n/.test(bodyStart) ? "\n" : "";
    function current() {
      if (!wholePage) return [before, body.value, after].filter((part, i) => i === 1 || part !== "").join("\n");
      if (mode === "raw") return raw.value;
      const head = withField(withField(front, "title", titleBox.value.trim()), "short", shortBox.value.replace(/\s+/g, " ").trim());
      return front || frontStart ? "---\n" + head + "\n---\n" + bodyLead + body.value : body.value;
    }
    const preview = el("div", { class: "fb-editor-preview" });
    const why = el("textarea", { rows: "2", placeholder: "Why this change? (optional)" });
    const status = el("span", { class: "fb-help" });
    function refresh() {
      const text = current();
      const [frontNow, bodyNow] = wholePage ? splitFrontMatter(text) : ["", body.value];
      const linked = bodyNow.replace(/\[\[([^\]|]+)(?:\|([^\]|]*))?(?:\|[^\]]*)?\]\]/g, (all, target, label) => `[${label || target}](#)`);
      const head = wholePage ? "<h1>" + escapeHtml(fieldValue(frontNow, "title")) + "</h1>"
        + "<blockquote class='fb-ed-sum'>" + escapeHtml(fieldValue(frontNow, "short")) + "</blockquote>" : "";
      preview.innerHTML = head + (window.marked ? window.marked.parse(linked) : "<pre>" + escapeHtml(linked) + "</pre>");
      status.textContent = text === source.text || (!wholePage && body.value === original) ? "No changes yet." : "Changed (not saved).";
    }
    let timer = null;
    const later = () => { clearTimeout(timer); timer = setTimeout(refresh, 250); };
    for (const field of [titleBox, shortBox, body.area, raw.area]) field.addEventListener("input", later);
    const textPane = el("div", { class: "fb-ed-fields" },
      wholePage ? el("label", { class: "fb-ed-label" }, "Title") : null, wholePage ? titleBox : null,
      wholePage ? el("label", { class: "fb-ed-label" }, "Summary") : null, wholePage ? shortBox : null,
      wholePage ? el("label", { class: "fb-ed-label" }, "Text") : null, body.box);
    const rawPane = el("div", { class: "fb-ed-fields", hidden: "hidden" },
      el("p", { class: "fb-help" }, "The whole file. Change the fields between the --- lines only when you know what they do: the type, id and relations hold the page in the graph."),
      raw.box);
    function setMode(next) {
      if (next === mode) return;
      if (next === "raw") raw.value = current();
      else {                                                 // back to text: take title, summary and body from the raw file
        const [frontRaw, bodyRaw] = splitFrontMatter(raw.value);
        front = frontRaw;
        titleBox.value = fieldValue(front, "title"); shortBox.value = fieldValue(front, "short");
        body.value = bodyRaw.replace(/^\n/, "");
      }
      mode = next;
      textPane.hidden = mode !== "text"; rawPane.hidden = mode !== "raw";
      modeButtons.forEach(button => button.classList.toggle("fb-on", button.dataset.mode === mode));
      refresh();
    }
    const modeButtons = wholePage ? [["text", "Text"], ["raw", "Raw Markdown"]].map(([value, label]) =>
      el("button", { class: "fb-ed-mode" + (value === mode ? " fb-on" : ""), "data-mode": value, type: "button",
        onclick: () => setMode(value) }, label)) : [];
    const overlay = el("div", { class: "fb-editor " + NOT },
      el("div", { class: "fb-editor-box" },
        el("div", { class: "fb-editor-head" }, el("b", {}, !section ? "Suggest an edit" : section.selection !== undefined ? "Suggest an edit of the selected passage"
          : "Suggest an edit of one section"), " ",
          el("code", {}, source.path), section && section.selection === undefined
            ? el("span", {}, " · section “" + section.title.replace(/edit section$/, "").trim() + "”") : null,
          el("span", { class: "fb-help fb-ed-version" }, " · version " + source.commit),
          modeButtons.length ? el("span", { class: "fb-ed-modes" }, ...modeButtons) : null),
        el("p", { class: "fb-help fb-ed-about" }, "Your edit is saved as a comment with the changes shown as a diff; the page itself is "
          + "not changed. Claude takes it into the plan of the review cycle, merges it, checks every number against its "
          + "source file and commits it with you as co-author."),
        el("div", { class: "fb-editor-panes" }, el("div", { class: "fb-ed-left" }, textPane, rawPane), preview),
        why,
        el("div", { class: "fb-actions" },
          el("button", { onclick: async () => {
            const text = current();
            if (text === source.text) { status.textContent = "Nothing changed."; return; }
            if (wholePage && mode === "text" && !titleBox.value.trim()) { status.textContent = "The title cannot be empty."; return; }
            try {
              await api("POST", BASE + "api/suggest", { page: PAGE, page_title: TITLE, text: why.value, new_text: text });
              overlay.remove(); await reload(); openPanel();
            } catch (error) { status.textContent = error.message; }
          } }, "Save as suggestion"),
          el("button", { class: "fb-secondary", onclick: () => {
            if (current() !== source.text && !confirm("Discard your changes?")) return;
            overlay.remove();
          } }, "Cancel"), status)));
    if (section && section.selection !== undefined) overlay.classList.add("fb-editor-passage");
    document.body.append(overlay);
    refresh();
    const target = focusField === "short" ? shortBox : body.area;
    target.focus();
    if (target === body.area) { body.area.setSelectionRange(0, 0); body.area.scrollTop = 0; body.paint(); }
  }

  function threadView(thread) {
    const box = el("div", { class: "fb-thread fb-thread-" + stateOf(thread), id: "fb-" + thread.thread_id });
    const head = el("div", { class: "fb-thread-head" }, statusPill(thread.status, thread));
    if (thread.quote) {
      const quote = el("blockquote", { class: "fb-quote", title: "Show in the text" }, thread.quote);
      if (thread._anchored) {
        quote.classList.add("fb-jump");
        quote.addEventListener("click", () => annotator.scrollIntoView(thread.thread_id));
      }
      box.append(head, quote);
    } else {
      head.append(el("span", { class: "fb-whole" }, "about the whole page"));
      box.append(head);
    }
    box.append(tagLine(thread));
    if (thread.text) box.append(messageView(thread.author, thread.text, thread.created_at, true));
    else box.append(el("div", { class: "fb-meta" }, "Tagged by ", el("b", {}, thread.author), " · ", when(thread.created_at)));
    if (thread.suggestion) box.append(diffView(thread.suggestion));
    for (const reply of thread.replies) box.append(messageView(reply.author, reply.text, reply.created_at));
    if (!["open", "marked"].includes(thread.status) && thread.status_by) {
      const commitLink = sha => el("a", { href: BASE + "commits/" + sha.split("+")[0] + ".html" }, sha);
      const note = thread.status === "page-changed" && thread.commit
        ? el("span", {}, "Page changed in commit ", commitLink(thread.commit),
            thread.status_note ? ": " + thread.status_note : "")
        : thread.status_note;
      box.append(el("div", { class: "fb-statusline" },
        "Marked " + (STATUS_TEXT[thread.status] || thread.status) + " by " +
        (thread.status_by === "claude" ? "Claude" : thread.status_by) + " · " + when(thread.status_at),
        note ? el("div", {}, note) : null));
    }
    if (thread.page_commit && COMMIT && thread.page_commit !== COMMIT) {
      box.append(el("div", { class: "fb-version" },
        "Asked on version ", el("a", { href: BASE + "commits/" + thread.page_commit.split("+")[0] + ".html" }, thread.page_commit),
        "; this page is now version ", el("a", { href: BASE + "commits/" + COMMIT.split("+")[0] + ".html" }, COMMIT), "."));
    }
    // reply + resolve
    const textarea = el("textarea", { rows: "2", placeholder: "Reply…", title: "Ctrl+Enter (⌘+Enter) sends · Esc clears" });
    const actions = el("div", { class: "fb-actions" },
      el("button", { onclick: async () => {
        if (!textarea.value.trim()) return;
        await send(() => api("POST", API + "/" + thread.thread_id + "/reply", { text: textarea.value }));
      } }, "Reply"),
      thread.status === "resolved"
        ? el("button", { class: "fb-secondary", onclick: () => send(() =>
            api("POST", API + "/" + thread.thread_id + "/status", { status: "open" })) }, "Reopen")
        : el("button", { class: "fb-secondary", title: "You are satisfied with the answer", onclick: () => send(() =>
            api("POST", API + "/" + thread.thread_id + "/status", { status: "resolved" })) }, "Mark resolved"));
    if (thread.status === "marked" && !thread.text && !thread.replies.length) {
      // a bare mark (manuscript section, confirmation): remove it with × on its tag; a note can still be added
      const more = el("details", { class: "fb-more" }, el("summary", {}, "add a note"), textarea, actions);
      box.append(more);
    } else box.append(textarea, actions);
    return box;
  }
  function renderPanel() {
    listEl.replaceChildren();
    orphanEl.replaceChildren();
    const anchored = threads.filter(thread => !thread.quote || thread._anchored);
    const orphaned = threads.filter(thread => thread.quote && !thread._anchored);
    if (!threads.length) listEl.append(el("p", { class: "fb-empty" },
      "No comments on this page yet. Select any text to ask about it, or write about the whole page above."));
    const resolved = anchored.filter(thread => stateOf(thread) === "resolved");
    for (const thread of anchored) if (stateOf(thread) !== "resolved") listEl.append(threadView(thread));
    if (resolved.length) {
      const fold = el("details", { class: "fb-resolved" }, el("summary", {}, resolved.length + " resolved comment(s)"));
      for (const thread of resolved) fold.append(threadView(thread));
      listEl.append(fold);
    }
    if (orphaned.length) {
      orphanEl.append(el("h3", {}, "Comments on earlier wording"),
        el("p", { class: "fb-help" }, "The text these comments point at is no longer on the page, usually because the page was rewritten after the comment."));
      for (const thread of orphaned) orphanEl.append(threadView(thread));
    }
    const open = threads.filter(thread => ["open", "planned"].includes(stateOf(thread))).length;
    const marks = threads.filter(thread => stateOf(thread) === "marked").length;
    const total = threads.length - marks;
    toggleBtn.textContent = "💬 Comment" + (total ? " · " + open + "/" + total : "");
    toggleBtn.title = open + " open of " + total + " comments on this page" + (marks ? "; " + marks + " fragment(s) marked for the manuscript" : "");
    renderName();
  }
  function renderName() {
    const name = getName();
    nameBox.replaceChildren();
    if (accountName) {
      nameBox.append("You comment as ", el("b", {}, accountName), " (signed in with ORCID)");
    } else if (name) {
      nameBox.append("You comment as ", el("b", {}, name), " · ",
        el("a", { href: "#", onclick: event => { event.preventDefault(); setName(""); renderName(); } }, "change"));
    } else {
      const input = el("input", { placeholder: "Your name", maxlength: "60" });
      nameBox.append(el("label", {}, "Your name (shown with your comments): "), input,
        el("button", { onclick: () => { if (input.value.trim()) { setName(input.value.trim()); renderName(); } } }, "Save"));
    }
  }
  let sending = false;                           // no second submit while one is on its way
  async function send(action) {
    if (!getName()) { openPanel(); alertIn("Set your name first."); return null; }
    if (sending) { alertIn("Still saving the previous message…"); return null; }
    sending = true;
    document.querySelectorAll(".fb-panel button, .fb-pop button").forEach(button => button.disabled = true);
    try {
      await action();
      await reload();
      return true;
    } catch (error) {
      alertIn("Could not save: " + error.message);
      return null;
    } finally {
      sending = false;
      document.querySelectorAll(".fb-panel button, .fb-pop button").forEach(button => button.disabled = false);
    }
  }
  function alertIn(message) {
    const note = el("div", { class: "fb-alert" }, message);
    panel.querySelector(".fb-body").prepend(note);
    setTimeout(() => note.remove(), 6000);
  }
  function openPanel(threadId) {
    panel.classList.add("fb-open");
    document.documentElement.classList.add("fb-panel-open");
    if (threadId) {
      const target = document.getElementById("fb-" + threadId);
      if (target) { target.scrollIntoView({ block: "center" }); target.classList.add("fb-flash"); setTimeout(() => target.classList.remove("fb-flash"), 1600); }
    }
  }
  /* A key (a then c, or c): open the comments with the cursor in the whole-page comment box, so typing starts the
     comment (Esc leaves the box and closes the panel; c again also closes it when the cursor is not in a field). */
  function commentByKey(toggle) {
    if (toggle && panel.classList.contains("fb-open")) { closePanel(); return true; }
    if (!dockEl || !dockEl.querySelector(".fb-d-comment") || dockEl.querySelector(".fb-d-comment").hidden) return false;
    openPanel();
    const field = panel.querySelector(".fb-body > .fb-new textarea");
    if (field) setTimeout(() => field.focus(), 50);
    return true;
  }
  window.keaCommentKey = () => commentByKey(true);
  function closePanel() {
    panel.classList.remove("fb-open");
    document.documentElement.classList.remove("fb-panel-open");
  }
  /* In a comment, reply or proposal field: Ctrl/Cmd+Enter presses its Send (or Reply) button; Esc presses its
     Cancel button, or, where the form has none (the page's comment box, a reply), clears the field and leaves it. */
  document.addEventListener("keydown", event => {
    const field = event.target;
    if (!(field instanceof HTMLTextAreaElement) || !field.closest(".fb-panel, .fb-propose")) return;
    let box = field.parentElement;
    while (box && !box.querySelector(":scope > .fb-actions, :scope > .fb-propose-actions")) box = box.parentElement;
    const actions = box && box.querySelector(":scope > .fb-actions, :scope > .fb-propose-actions");
    if (!actions) return;
    const buttons = Array.from(actions.querySelectorAll("button"));
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      const send = buttons.find(button => !button.classList.contains("fb-secondary"));
      if (send) send.click();
    } else if (event.key === "Escape") {
      event.preventDefault(); event.stopPropagation();
      const cancel = buttons.find(button => button.textContent.trim() === "Cancel");
      if (cancel) cancel.click();
      else { field.value = ""; field.dispatchEvent(new Event("input")); field.blur(); }
    }
  }, true);
  function newCommentForm(selection, tagging) {
    const form = el("div", { class: "fb-new" });
    form.append(el("h3", {}, selection ? "Comment on the selected text" : "Comment on the whole page"));
    if (selection) form.append(el("blockquote", { class: "fb-quote" }, selection.quote));
    const textarea = el("textarea", { rows: "4", title: "Ctrl+Enter (⌘+Enter) sends · Esc cancels", placeholder: selection
      ? "What is unclear, wrong or missing here?" : "A question or remark about this page…" });
    form.append(textarea, el("div", { class: "fb-actions" },
      el("button", { onclick: async () => {
        if (!textarea.value.trim()) return;
        const ok = await send(() => api("POST", API, {
          page: PAGE, page_title: TITLE, page_commit: COMMIT, text: textarea.value, ...(selection || {})
        }));
        if (ok) { textarea.value = ""; if (selection) form.remove(); }
      } }, "Send"),
      selection ? el("button", { class: "fb-secondary", onclick: () => form.remove() }, "Cancel") : null));
    return form;
  }

  // ---------- selection -> "Comment" button ----------
  function onSelectionEnd() {
    if (readOnly) return;
    setTimeout(() => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || !selection.rangeCount) { selectBtn.hidden = true; return; }
      const range = selection.getRangeAt(0);
      if (!container.contains(range.commonAncestorContainer)) { selectBtn.hidden = true; return; }
      const startEl = range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentElement;
      if (startEl && startEl.closest("." + NOT)) { selectBtn.hidden = true; return; }
      const quote = range.toString();
      if (!quote.trim() || quote.length > 2000) { selectBtn.hidden = true; return; }
      pendingSelection = contextOf(range);
      placePopup(range);
    }, 10);
  }

  // ---------- load ----------
  async function reload() {
    const data = await api("GET", API + "?page=" + encodeURIComponent(PAGE));
    threads = data.threads;
    if (data.tags) vocab = data.tags;
    readOnly = data.can_write === false;
    accountName = data.account ? data.you || "" : "";
    document.body.classList.toggle("fb-readonly", readOnly);
    if (selectBtn && !selectBtn.dataset.filled) fillSelectionBar();
    renderPageStrip();
    renderDock();
    drawHighlights();
    renderPanel();
  }

  function build() {
    container = document.querySelector("main");
    if (!container) return false;
    for (const node of container.querySelectorAll("nav, .fb-static, .fb-history, .fb-versionline, script, style")) node.classList.add(NOT);

    panel = el("aside", { class: "fb-panel " + NOT, "aria-label": "Comments" });
    nameBox = el("div", { class: "fb-name" });
    listEl = el("div", { class: "fb-list" });
    orphanEl = el("div", { class: "fb-orphans" });
    panel.append(
      el("div", { class: "fb-head" }, el("b", {}, "Comments"),
        el("button", { class: "fb-close", title: "Close", onclick: closePanel }, "×")),
      el("div", { class: "fb-body" }, newCommentForm(null, false), nameBox, listEl, orphanEl));   // write first, then read
    const startForm = tagging => {
      selectBtn.hidden = true;
      if (!pendingSelection) return;
      openPanel();
      const existing = panel.querySelector(".fb-new.fb-selection");
      if (existing) existing.remove();
      const form = newCommentForm(pendingSelection, tagging);
      form.classList.add("fb-selection");
      panel.querySelector(".fb-body").prepend(form);             // a comment on a selection: on top of everything
      if (!tagging) form.querySelector("textarea").focus();
    };
    selectBtn = selectionBar(startForm);
    selectBtn.hidden = true;
    dockPop = el("div", { class: "fb-select-bar fb-dock-pop " + NOT, role: "dialog" });
    dockPop.hidden = true;
    dockEl = buildDock();
    document.addEventListener("keydown", event => { if (event.key === "Escape") dockPop.hidden = true; });
    /* Esc closes the comment window, unless it closes something smaller first (the selection bar, the dock's menu)
       or a field outside the window handles Esc itself (editing a title or summary in place, the editor).
       Capture phase: the state is read before those handlers hide their popups. */
    document.addEventListener("keydown", event => {
      if (event.key !== "Escape" || !panel.classList.contains("fb-open")) return;
      const popupOpen = (selectBtn && !selectBtn.hidden) || (dockPop && !dockPop.hidden);
      const fieldOutside = event.target instanceof Element && event.target.closest("input, textarea, [contenteditable]")
        && !panel.contains(event.target);
      if (!popupOpen && !fieldOutside) closePanel();
    }, true);
    document.addEventListener("mousedown", event => {
      if (!dockPop.hidden && !dockPop.contains(event.target) && !event.target.closest(".fb-d-next, .fb-d-ms")) dockPop.hidden = true;
    });
    document.body.append(panel, dockEl, dockPop, selectBtn);

    annotator = RecogitoJS.createTextAnnotator(container, { annotatingEnabled: false, style: highlightStyle });
    annotator.on("clickAnnotation", annotation => openPanel(annotation.id));
    document.addEventListener("mouseup", onSelectionEnd);
    document.addEventListener("touchend", onSelectionEnd);
    // phones and tablets select with long-press handles: react when the selection settles
    let settle = null;
    document.addEventListener("selectionchange", () => { clearTimeout(settle); settle = setTimeout(onSelectionEnd, 600); });
    document.addEventListener("keyup", event => { if (event.shiftKey) onSelectionEnd(); });
    return true;
  }

  /* A public project read without a login: the comments stay hidden; one button leads to the sign-in. */
  function signInButton() {
    const root = new URL(BASE, location.href).pathname;       // the site root, e.g. / or /p/<name>/
    const next = "/" + location.pathname.slice(root.length) + location.search;
    const link = el("a", { class: "fb-dpill fb-d-signin", href: BASE + "login?next=" + encodeURIComponent(next || "/"),
      title: "This site is public to read; sign in to see the comments and to comment" }, "Sign in to comment");
    document.body.append(el("div", { class: "fb-dock fb-dock-anon " + NOT }, el("div", { class: "fb-dock-items" }, link)));
  }

  async function start() {
    try {
      const probe = await fetch(API + "?page=" + encodeURIComponent(PAGE), { credentials: "same-origin" });
      if (probe.status === 401) { signInButton(); return; }   // a public project, not signed in: pages only
      if (!probe.ok) return;
    } catch (error) {
      return;  // no comment server: keep the static copy
    }
    if (document.getElementById("xg")) return;   // the graph view (explore.js): comments live on the pages it opens
    if (typeof RecogitoJS === "undefined" || !build()) return;
    for (const node of document.querySelectorAll(".fb-static")) node.hidden = true;
    if (window.keaDropTab) window.keaDropTab("comments");   // live comments: the panel, not the build-time tab
    await reload();
    try {
      const probeSource = await fetch(BASE + "api/source?page=" + encodeURIComponent(PAGE), { credentials: "same-origin" });
      editable = probeSource.ok && !readOnly;
    } catch (error) { editable = false; }
    renderDock();
    if (editable) addEditButtons();
    document.body.classList.toggle("fb-can-edit", editable);
    const match = location.hash.match(/^#fb-(.+)$/);
    if (match) openPanel(match[1]);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
