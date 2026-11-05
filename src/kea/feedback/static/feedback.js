/* Reader comments on the site: select text -> "Comment", or comment on the whole page.
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
  const API = "/api/threads";
  const ASSET_BASE = script.src.replace(/[^/]*$/, "");      // .../_feedback/
  let editable = false;
  const CONTEXT = 40;
  const NOT = "not-annotatable";
  const STATUS_TEXT = {
    "open": "open", "answered": "answered", "page-changed": "page changed",
    "wont-fix": "won't fix", "resolved": "resolved", "planned": "in the plan"
  };

  let threads = [];
  let annotator = null;
  let container = null;
  let panel, listEl, orphanEl, toggleBtn, selectBtn, nameBox;
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
  function getName() {
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
  async function api(method, url, body) {
    const response = await fetch(url, {
      method, credentials: "same-origin",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined
    });
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
  function highlightStyle(annotation) {
    const thread = threads.find(item => item.thread_id === annotation.id);
    const status = thread ? thread.status : "open";
    if (status === "open") return { fill: "#ffd54f", fillOpacity: 0.45, underlineColor: "#e0a800", underlineThickness: 2 };
    if (status === "resolved" || status === "wont-fix") return { fill: "#bdbdbd", fillOpacity: 0.25 };
    return { fill: "#81c784", fillOpacity: 0.35, underlineColor: "#2e7d32", underlineThickness: 2 };
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

  // ---------- panel ----------
  function statusPill(status) {
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
      class: line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : line.startsWith("@@") ? "hunk" : "" }, line + "\n")));
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
  async function openEditor() {
    let source;
    try { source = await api("GET", "/api/source?page=" + encodeURIComponent(PAGE)); }
    catch (error) { alert(error.message); return; }
    await loadMarked().catch(() => null);
    const area = el("textarea", { class: "fb-editor-text", spellcheck: "true" });
    area.value = source.text;
    const preview = el("div", { class: "fb-editor-preview" });
    const why = el("textarea", { rows: "2", placeholder: "Why this change? (optional)" });
    const status = el("span", { class: "fb-help" });
    function refresh() {
      const [front, body] = splitFrontMatter(area.value);
      const linked = body.replace(/\[\[([^\]|]+)(?:\|([^\]|]*))?(?:\|[^\]]*)?\]\]/g, (all, target, text) => `[${text || target}](#)`);
      preview.innerHTML = (front ? "<pre class='fb-front'>" + front.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]) + "</pre>" : "")
        + (window.marked ? window.marked.parse(linked) : "<pre>" + linked.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]) + "</pre>");
      status.textContent = area.value === source.text ? "No changes yet." : "Changed (not saved).";
    }
    let timer = null;
    area.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(refresh, 250); });
    const overlay = el("div", { class: "fb-editor " + NOT },
      el("div", { class: "fb-editor-box" },
        el("div", { class: "fb-editor-head" }, el("b", {}, "Suggest an edit"), " ",
          el("code", {}, source.path), el("span", { class: "fb-help" }, " · version " + source.commit)),
        el("p", { class: "fb-help" }, "Your edit is saved as a comment with the changes shown as a diff; the page itself is "
          + "not changed. Claude takes it into the plan of the review cycle, merges it, checks every number against its "
          + "source file and commits it with you as co-author."),
        el("div", { class: "fb-editor-panes" }, area, preview),
        why,
        el("div", { class: "fb-actions" },
          el("button", { onclick: async () => {
            if (area.value === source.text) { status.textContent = "Nothing changed."; return; }
            try {
              await api("POST", "/api/suggest", { page: PAGE, page_title: TITLE, text: why.value, new_text: area.value });
              overlay.remove(); await reload(); openPanel();
            } catch (error) { status.textContent = error.message; }
          } }, "Save as suggestion"),
          el("button", { class: "fb-secondary", onclick: () => {
            if (area.value !== source.text && !confirm("Discard your changes?")) return;
            overlay.remove();
          } }, "Cancel"), status)));
    document.body.append(overlay);
    refresh();
    area.focus();
  }

  function threadView(thread) {
    const box = el("div", { class: "fb-thread", id: "fb-" + thread.thread_id });
    const head = el("div", { class: "fb-thread-head" }, statusPill(thread.status));
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
    box.append(messageView(thread.author, thread.text, thread.created_at, true));
    if (thread.suggestion) box.append(diffView(thread.suggestion));
    for (const reply of thread.replies) box.append(messageView(reply.author, reply.text, reply.created_at));
    if (thread.status !== "open" && thread.status_by) {
      const commitLink = sha => el("a", { href: "/commits/" + sha.split("+")[0] + ".html" }, sha);
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
        "Asked on version ", el("a", { href: "/commits/" + thread.page_commit.split("+")[0] + ".html" }, thread.page_commit),
        "; this page is now version ", el("a", { href: "/commits/" + COMMIT.split("+")[0] + ".html" }, COMMIT), "."));
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
    box.append(textarea, actions);
    return box;
  }
  function renderPanel() {
    listEl.replaceChildren();
    orphanEl.replaceChildren();
    const anchored = threads.filter(thread => !thread.quote || thread._anchored);
    const orphaned = threads.filter(thread => thread.quote && !thread._anchored);
    if (!threads.length) listEl.append(el("p", { class: "fb-empty" },
      "No comments on this page yet. Select any text to ask about it, or write about the whole page below."));
    for (const thread of anchored) listEl.append(threadView(thread));
    if (orphaned.length) {
      orphanEl.append(el("h3", {}, "Comments on earlier wording"),
        el("p", { class: "fb-help" }, "The text these comments point at is no longer on the page, usually because the page was rewritten after the comment."));
      for (const thread of orphaned) orphanEl.append(threadView(thread));
    }
    const open = threads.filter(thread => thread.status === "open").length;
    toggleBtn.textContent = "Comments" + (threads.length ? " (" + threads.length + (open ? ", " + open + " open" : "") + ")" : "");
    renderName();
  }
  function renderName() {
    const name = getName();
    nameBox.replaceChildren();
    if (name) {
      nameBox.append("You comment as ", el("b", {}, name), " · ",
        el("a", { href: "#", onclick: event => { event.preventDefault(); setName(""); renderName(); } }, "change"));
    } else {
      const input = el("input", { placeholder: "Your name", maxlength: "60" });
      nameBox.append(el("label", {}, "Your name (shown with your comments): "), input,
        el("button", { onclick: () => { if (input.value.trim()) { setName(input.value.trim()); renderName(); } } }, "Save"));
    }
  }
  async function send(action) {
    if (!getName()) { openPanel(); alertIn("Set your name first."); return null; }
    try {
      await action();
      await reload();
      return true;
    } catch (error) {
      alertIn("Could not save: " + error.message);
      return null;
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
  function newCommentForm(selection) {
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
      const rect = range.getBoundingClientRect();
      selectBtn.style.top = (window.scrollY + rect.bottom + 6) + "px";
      selectBtn.style.left = Math.max(8, window.scrollX + rect.left + rect.width / 2 - 45) + "px";
      selectBtn.hidden = false;
    }, 10);
  }

  // ---------- load ----------
  async function reload() {
    const data = await api("GET", API + "?page=" + encodeURIComponent(PAGE));
    threads = data.threads;
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
      el("div", { class: "fb-head" }, el("b", {}, "Comments on this page"),
        el("a", { href: "/feedback.html", class: "fb-all" }, "all comments"),
        el("button", { class: "fb-edit-btn fb-secondary", hidden: "hidden", onclick: openEditor,
          title: "Edit the Markdown of this page; saved as a suggestion" }, "Suggest an edit"),
        el("button", { class: "fb-close", title: "Close", onclick: closePanel }, "×")),
      el("div", { class: "fb-body" }, nameBox,
        el("p", { class: "fb-help" }, "Select any text on the page and press “Comment” to ask about that sentence. Claude reads the open comments in the next working session and answers here or rewrites the page."),
        listEl, orphanEl, newCommentForm(null)));
    toggleBtn = el("button", { class: "fb-toggle " + NOT, onclick: () =>
      panel.classList.contains("fb-open") ? closePanel() : openPanel() }, "Comments");
    selectBtn = el("button", { class: "fb-select " + NOT, onmousedown: event => event.preventDefault(), onclick: () => {
      selectBtn.hidden = true;
      if (!pendingSelection) return;
      openPanel();
      const existing = panel.querySelector(".fb-new.fb-selection");
      if (existing) existing.remove();
      const form = newCommentForm(pendingSelection);
      form.classList.add("fb-selection");
      panel.querySelector(".fb-body").insertBefore(form, listEl);
      form.querySelector("textarea").focus();
    } }, "Comment");
    selectBtn.hidden = true;
    document.body.append(panel, toggleBtn, selectBtn);

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

  async function start() {
    try {
      const probe = await fetch(API + "?page=" + encodeURIComponent(PAGE), { credentials: "same-origin" });
      if (!probe.ok) return;
    } catch (error) {
      return;  // no comment server: keep the static copy
    }
    if (typeof RecogitoJS === "undefined" || !build()) return;
    for (const node of document.querySelectorAll(".fb-static")) node.hidden = true;
    await reload();
    try {
      const probeSource = await fetch("/api/source?page=" + encodeURIComponent(PAGE), { credentials: "same-origin" });
      editable = probeSource.ok;
    } catch (error) { editable = false; }
    const editButton = panel.querySelector(".fb-edit-btn");
    if (editable && editButton) editButton.hidden = false;
    const match = location.hash.match(/^#fb-(.+)$/);
    if (match) openPanel(match[1]);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
