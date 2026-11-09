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
  // One key per submit (this page load + what is sent): a submit sent again (double click, retry after a slow
  // server) carries the same key, and the server stores it once.
  const LOAD_ID = Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
  function requestKey(method, url, payload) {
    let hash = 2166136261;                       // FNV-1a over method, url and body
    const text = method + " " + url + " " + payload;
    for (let i = 0; i < text.length; i++) { hash ^= text.charCodeAt(i); hash = Math.imul(hash, 16777619) >>> 0; }
    return LOAD_ID + "-" + hash.toString(36);
  }
  async function api(method, url, body) {
    const payload = body ? JSON.stringify(body) : undefined;
    const headers = body ? { "Content-Type": "application/json" } : {};
    if (method !== "GET") headers["X-Kea-Request"] = requestKey(method, url, payload || "");
    const response = await fetch(url, { method, credentials: "same-origin", headers, body: payload });
    let data = {};
    try { data = await response.json(); } catch (error) { /* not JSON */ }
    if (!response.ok) throw new Error(data.error || ("HTTP " + response.status));
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
  const pageType = () => { const node = container && container.querySelector(".node-content"); return node ? node.dataset.type || "" : ""; };
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
      text: text || "", tags: names, ...(selection || {}) }));
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
          onmousedown: event => event.preventDefault(), onclick: () => startForm(false) }, "💬 Comment"),
        el("button", { class: "fb-sel-btn fb-sel-edit", title: "Suggest new wording for the paragraph(s) with this text",
          onmousedown: event => event.preventDefault(), onclick: () => {
            bar.hidden = true;
            if (pendingSelection) openEditor({ selection: pendingSelection.quote });
          } }, "✎ Edit")),
      el("div", { class: "fb-sel-group" }, el("div", { class: "fb-sel-label" }, "Next run"),
        el("div", { class: "fb-sel-row fb-sel-next" })),
      el("div", { class: "fb-sel-group fb-sel-propose" }, el("div", { class: "fb-sel-label" }, "Propose"),
        el("div", { class: "fb-sel-row fb-pr-row" })),
      el("div", { class: "fb-sel-group" }, el("div", { class: "fb-sel-label" }, "Manuscript"),
        el("div", { class: "fb-sel-row fb-ms-row" })),
      el("div", { class: "fb-sel-hint" }, "One click saves a tag · Esc closes"));
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
  }
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
    if (openThread("confirm")) add("fb-pp-ok", "✓ confirm · next plan", "A reader confirmed this page; it is recorded in the next plan");
    if (openThread("unconfirm")) add("fb-pp-stale", "confirmation withdrawn · next plan");
    const rejected = openThread("drop") || openThread("reject");
    if (rejected) add("fb-pp-remove", "✕ drop asked", "Asked by " + rejected.author + (rejected.text ? ": " + rejected.text : ""));
    const approval = openThread("approve");
    if (approval) add("fb-pp-ok", "✓ approve · next harvest", "Approved by " + approval.author);
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
     across the site). Comment · Edit | Approve or Confirm · Revise ▸ · Drop · Propose ▸ | Next run ▸ · Manuscript ▸. The verdicts are definitive
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
      const confirm = pill("fb-d-confirm", "✓ Confirm", "", () => {});
      const revise = pill("fb-d-revise", "↻ Revise ▸", "Rewrite this page: say what to change; this branch is reworked", () => toggleDockPop(revise, "revise"));
      const reject = pill("fb-d-reject", "✕ Drop", "", () => {});
      const next = pill("fb-d-next", "Next run ▸", "Ask for work on the whole page in the next run", () => toggleDockPop(next, "review"));
      const manuscript = pill("fb-d-ms", "Manuscript ▸", "Which part of the manuscript the whole page belongs in", () => toggleDockPop(manuscript, "manuscript"));
      const propose = pill("fb-d-propose", "Propose ▸", "Propose the next step of the reasoning: a question, hypothesis, step, conclusion, caveat …", () => toggleDockPop(propose, "propose"));
      items.append(el("span", { class: "fb-dock-gap" }), confirm, revise, reject, propose, el("span", { class: "fb-dock-gap" }), next, manuscript);
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
    if (!confirm) return;
    const content = container && container.querySelector(".node-content");
    const waitingPage = !!(content && content.dataset.waiting);           // pace: guided, not yet approved
    const dropAlso = content ? content.dataset.drop || "" : "";
    const asked = openThread(waitingPage ? "approve" : "confirm"), unasked = openThread("unconfirm");
    const dropped = openThread("drop") || openThread("reject"), revising = openThread("revise");
    const done = !waitingPage && pageConfirmed();
    const when = waitingPage ? "at the next harvest" : "in the next plan";
    const word = waitingPage ? "Approve" : "Confirm";
    confirm.className = "fb-dpill fb-d-confirm" + (done && !unasked ? " fb-active" : asked ? " fb-pending" : unasked ? " fb-pending-off" : "");
    confirm.textContent = asked ? `✓ ${word} · ${waitingPage ? "next harvest" : "next plan"}` : unasked ? "✓ Withdrawal · next plan" : done ? "✓ Confirmed" : "✓ " + word;
    confirm.title = asked ? `Goes in ${when}; click to take it back`
      : unasked ? "The confirmation is withdrawn in the next plan; click to keep it"
      : done ? "This page is confirmed; click to withdraw the confirmation (in the next plan)"
      : waitingPage ? "Go ahead: the next step may build on this page (applied at the next harvest)"
      : "Your stamp of approval: keep this page as it is (recorded on the page in the next plan)";
    confirm.onclick = async () => {
      if (asked) return withdraw(asked, (waitingPage ? "approval" : "confirmation") + " taken back");
      if (unasked) return withdraw(unasked, "withdrawal taken back");
      if (done) { if (confirm_("Withdraw the confirmation of this page? This goes into the next plan.")) await tagThread(null, ["unconfirm"]); return; }
      if (dropped) await withdraw(dropped, "drop replaced by " + word.toLowerCase());
      await tagThread(null, [waitingPage ? "approve" : "confirm"]);
    };
    const revise = dockEl.querySelector(".fb-d-revise");
    revise.className = "fb-dpill fb-d-revise" + (revising ? " fb-pending" : "");
    revise.textContent = revising ? "↻ Revise · " + (waitingPage ? "next harvest" : "next plan") : "↻ Revise ▸";
    reject.className = "fb-dpill fb-d-reject" + (dropped ? " fb-pending" : "");
    reject.textContent = dropped ? "✕ Drop · " + (waitingPage ? "next harvest" : "next plan") : "✕ Drop";
    reject.title = dropped ? "This page is dropped " + when + "; click to take it back"
      : "Remove this page" + (dropAlso ? " and the pages that rest only on it (" + dropAlso + ")" : "") + "; done " + when;
    reject.onclick = async () => {
      if (dropped) return withdraw(dropped, "drop taken back");
      const also = dropAlso ? `\n\nThis also removes the pages that rest only on it: ${dropAlso}.` : "";
      const why = prompt(`Drop this page? It is removed ${when}.${also}\n\nWhy (optional):`);
      if (why === null) return;
      if (asked) await withdraw(asked, (waitingPage ? "approval" : "confirmation") + " replaced by a drop");
      await tagThread(null, ["drop"], why.trim());
    };
    const nextCount = new Set(pageLevel().filter(thread => thread.status !== "marked").flatMap(thread => thread.tags)
      .filter(name => tagInfo(name).group === "review")).size;
    dockEl.querySelector(".fb-d-next").textContent = "Next run" + (nextCount ? " · " + nextCount : "") + " ▸";
    const section = pageSection();
    dockEl.querySelector(".fb-d-ms").textContent = "Manuscript" + (section ? ": " + tagInfo(section.tags[0]).label : "") + " ▸";
    if (!dockPop.hidden) fillDockPop();
  }
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
      const rect = dockPopAnchor.getBoundingClientRect();
      const dockLeft = dockEl.querySelector(".fb-dock-items").getBoundingClientRect().left;
      dockPop.style.right = (document.documentElement.clientWidth - dockLeft + 10) + "px";
      dockPop.style.bottom = Math.max(8, window.innerHeight - rect.bottom) + "px";
      return;
    }
    if (dockPopGroup === "propose") {
      const place = () => {
        const rect = dockPopAnchor.getBoundingClientRect();
        const dockLeft = dockEl.querySelector(".fb-dock-items").getBoundingClientRect().left;
        dockPop.style.right = (document.documentElement.clientWidth - dockLeft + 10) + "px";
        dockPop.style.bottom = Math.max(8, window.innerHeight - rect.bottom) + "px";
      };
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
    const rect = dockPopAnchor.getBoundingClientRect();
    const dockLeft = dockEl.querySelector(".fb-dock-items").getBoundingClientRect().left;
    dockPop.style.right = (document.documentElement.clientWidth - dockLeft + 10) + "px";
    dockPop.style.bottom = Math.max(8, window.innerHeight - rect.bottom) + "px";
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
    const textarea = el("textarea", { rows: "2", placeholder: "Reply…" });
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
  function closePanel() {
    panel.classList.remove("fb-open");
    document.documentElement.classList.remove("fb-panel-open");
  }
  function newCommentForm(selection, tagging) {
    const form = el("div", { class: "fb-new" });
    form.append(el("h3", {}, selection ? "Comment on the selected text" : "Comment on the whole page"));
    if (selection) form.append(el("blockquote", { class: "fb-quote" }, selection.quote));
    const textarea = el("textarea", { rows: "4", placeholder: selection
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
    if (typeof RecogitoJS === "undefined" || !build()) return;
    for (const node of document.querySelectorAll(".fb-static")) node.hidden = true;
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
