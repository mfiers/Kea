/* The Current comments page (comments.html, under Plan): who commented what, on which page, in which state.
 * The rows come as JSON in <script id='comments-data'> (the comments known when the site was built: docsite/pages.py
 * comments_page); when the site is served (kea serve, a Kea hub) the live list from api/threads replaces them.
 * Filters: one button per person (with counts), and current only (open, marked, in the plan) or all. The state
 * lives in the address after '#' (e.g. #who=mark%20fiers&all=1), so a view can be linked.
 */
(function () {
  "use strict";
  const data = JSON.parse(document.getElementById("comments-data").textContent);
  const pages = data.pages;                    // page key -> href, relative to the site root
  const CURRENT = new Set(["open", "marked", "planned"]);
  const root = document.getElementById("comments-view");
  let threads = data.threads;
  let source = "as of the last build";

  function el(tag, attributes, children) {
    const node = document.createElement(tag);
    for (const [name, value] of Object.entries(attributes || {})) {
      if (value !== undefined && value !== null && value !== false) node.setAttribute(name, value);
    }
    for (const child of [].concat(children || [])) {
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }
  const personName = (thread) => (thread.author === "claude" ? "Claude" : (thread.author || "anonymous").trim());
  const personKey = (thread) => personName(thread).toLowerCase();
  function readState() {
    const params = new URLSearchParams(location.hash.slice(1));
    return { who: params.get("who") || "", all: params.get("all") === "1" };
  }
  function writeState(state) {
    const params = new URLSearchParams();
    if (state.who) params.set("who", state.who);
    if (state.all) params.set("all", "1");
    const hash = params.toString();
    history.replaceState(null, "", hash ? "#" + hash : location.pathname + location.search);
    render();
  }
  function shorten(text, length) {
    const flat = (text || "").replace(/\s+/g, " ").trim();
    return flat.length > length ? flat.slice(0, length - 1).trimEnd() + "…" : flat;
  }

  function render() {
    const state = readState();
    const shown = threads.filter((thread) => state.all || CURRENT.has(thread.status));
    const people = new Map();
    for (const thread of shown) {
      const key = personKey(thread);
      const entry = people.get(key) || { name: personName(thread), count: 0 };
      entry.count += 1;
      people.set(key, entry);
    }
    const rows = shown.filter((thread) => !state.who || personKey(thread) === state.who)
      .sort((first, second) => (second.created_at || "").localeCompare(first.created_at || ""));

    const chips = el("div", { class: "obj-chips" }, [el("span", { class: "obj-label" }, "Who")]);
    const everyone = el("button", { class: "obj-chip" + (state.who ? "" : " on") }, ["everyone ",
      el("span", { class: "obj-count" }, String(shown.length))]);
    everyone.onclick = () => writeState({ ...state, who: "" });
    chips.append(everyone);
    for (const [key, entry] of [...people.entries()].sort((first, second) => second[1].count - first[1].count)) {
      const chip = el("button", { class: "obj-chip" + (state.who === key ? " on" : "") }, [entry.name + " ",
        el("span", { class: "obj-count" }, String(entry.count))]);
      chip.onclick = () => writeState({ ...state, who: state.who === key ? "" : key });
      chips.append(chip);
    }
    const scope = el("div", { class: "obj-chips" }, [el("span", { class: "obj-label" }, "Show")]);
    for (const [label, all] of [["current (open, marked, in the plan)", false], ["all comments", true]]) {
      const chip = el("button", { class: "obj-chip" + (state.all === all ? " on" : "") }, label);
      chip.onclick = () => writeState({ ...state, all });
      scope.append(chip);
    }

    const table = el("table", { class: "nodes comments-table" }, [
      el("colgroup", {}, [el("col", { class: "c-who" }), el("col", { class: "c-where" }), el("col"),
        el("col", { class: "c-status" })]),
      el("tr", {}, ["Who", "Page", "Comment", "State"].map((label) => el("th", {}, label)))]);
    for (const thread of rows) {
      const href = pages[thread.page];
      const title = thread.page_title || thread.page;
      const page = href ? el("a", { href: href }, title) : el("span", {}, title);
      const replies = (thread.replies || []).map((reply) => (reply.author === "claude" ? "Claude" : reply.author));
      const comment = el("td", {}, [
        thread.quote ? el("div", { class: "cell-note" }, "on “" + shorten(thread.quote, 90) + "”") : "",
        el("div", {}, shorten(thread.text || (thread.suggestion ? "(a suggested edit)" : "(no text)"), 260)),
        (thread.tags || []).length ? el("div", { class: "cell-note" }, "tags: " + thread.tags.join(", ")) : "",
        replies.length ? el("div", { class: "cell-note" }, replies.length + " repl" + (replies.length === 1 ? "y" : "ies")
          + " (" + [...new Set(replies)].join(", ") + ")") : ""]);
      table.append(el("tr", {}, [
        el("td", {}, [el("b", {}, personName(thread)),
          el("div", { class: "cell-note" }, (thread.created_at || "").replace("T", " ").slice(0, 16))]),
        el("td", {}, page), comment,
        el("td", {}, el("span", { class: "fb-pill fb-state-" + (thread.state || thread.status) },
          thread.state_label || thread.status))]));
    }
    root.replaceChildren(chips, scope,
      el("p", { class: "obj-info" }, rows.length + " comment(s) shown, " + source + "."),
      rows.length ? table : el("p", { class: "help" }, "No comments here."));
  }

  render();
  fetch("api/threads", { credentials: "same-origin" })
    .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
    .then((live) => { threads = live.threads; source = "live from the comment server"; render(); })
    .catch(() => {});                          // a static copy: keep the comments known at build time
})();
