/* Review-cycle status on every page (feedback/cycle.py, GET /api/status).
 *
 * - Polls the server every POLL_MS. Without a server (file:// or plain hosting) it does nothing.
 * - When a new site build has been released, offers a reload (and reloads by itself if nothing is being typed).
 * - The cycle (feedback/cycle.py, since 1.18): comments everywhere; a PI presses "Harvest comments" and
 *   Claude folds them into the plan, which then stands until the next harvest; the plan page counts the comments
 *   made since; "Implement the plan" (after a harvest) pauses comments until the release (a banner on every page,
 *   comment controls hidden; the server refuses them with 423 anyway).
 * - Approve & go (since 1.28): while a request waits or the agent works on it, a line on every page says so (what,
 *   for which page, by whom, the agent's last word from `kea progress`), polling every FAST_MS; the Progress page
 *   (#progress-live) lists the requests; a "kea-status" event hands each status to feedback.js (the page's buttons).
 * - On the plan page (#fb-plan-actions) shows the buttons and a live indicator: are all comments in the plan,
 *   and the Claude session (status.watcher, cycle.watcher_status): watching, working, ended or gone, with the time
 *   since the last heartbeat. When the session stopped unexpectedly ("gone"), readers who may steer get a banner
 *   on every page (dismissable until the next change).
 * The page's build id: data-build on this script tag on sites built before 1.26; since then the build id the
 * server reports at the first poll after the page loaded (pages then stay byte-identical across builds, so a
 * publish sends only the pages that changed).
 */
(function () {
  "use strict";
  const script = document.currentScript;
  let BUILD = script.dataset.build || "";
  const PREFIX = script.dataset.prefix || "";
  const BASE = script.src.replace(/_feedback\/[^/]*$/, "");   // the site root (also under a hub prefix)
  const POLL_MS = 20000;
  let banner = null;
  let lastState = null;

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (key === "class") node.className = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value);
    }
    for (const child of children) if (child !== null && child !== undefined)
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    return node;
  }
  function when(iso) {
    return iso ? new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
  }
  function typing() {
    return Array.from(document.querySelectorAll(".fb-panel textarea")).some(area => area.value.trim());
  }
  function showBanner(kind, ...content) {
    if (!banner) {
      banner = el("div", { class: "fb-banner not-annotatable" });
      document.body.prepend(banner);
    }
    banner.className = "fb-banner not-annotatable fb-banner-" + kind;
    banner.replaceChildren(...content);
    banner.hidden = false;
    bannerOffset();
  }
  function hideBanner() { if (banner) banner.hidden = true; bannerOffset(); }
  /* The comment panel and the type bar are fixed to the top of the window: they start below the banner. */
  function bannerOffset() {
    const height = banner && !banner.hidden ? banner.offsetHeight : 0;
    document.documentElement.style.setProperty("--fb-banner-h", height + "px");
  }
  window.addEventListener("resize", bannerOffset);

  // Harvest, Implement and Cancel need the iteration password (a second password besides the site's);
  // the server answers 403 {need_steer: true} until it has been entered once (a cookie remembers it).
  function askSteerPassword() {
    return new Promise(resolve => {
      const input = el("input", { type: "password", autocomplete: "off", class: "fb-steer-input" });
      const error = el("p", { class: "fb-steer-error" });
      const dialog = el("dialog", { class: "fb-steer not-annotatable" },
        el("p", {}, el("strong", {}, "Iteration password")),
        el("p", { class: "fb-steer-help" }, "Harvesting the comments into the plan, asking Claude to implement it, and " +
          "Approve & go need the iteration password (not the site password). Ask the site owner for it."),
        input, error,
        el("div", { class: "fb-steer-buttons" },
          el("button", { class: "fb-secondary", onclick: () => { dialog.close(); resolve(false); } }, "Cancel"),
          el("button", { onclick: submit }, "Unlock")));
      async function submit() {
        const response = await fetch(BASE + "api/steer", { method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: input.value }) });
        if (response.ok) { dialog.close(); dialog.remove(); resolve(true); return; }
        const data = await response.json().catch(() => ({}));
        error.textContent = data.error || ("HTTP " + response.status);
      }
      input.addEventListener("keydown", event => { if (event.key === "Enter") submit(); });
      document.body.append(dialog);
      dialog.showModal();
      input.focus();
    });
  }

  window.keaAskSteer = askSteerPassword;            // feedback.js: Approve & go

  async function post(action, retried) {
    const response = await fetch(BASE + "api/cycle/" + action, { method: "POST", credentials: "same-origin" });
    const data = await response.json().catch(() => ({}));
    if (response.status === 403 && data.need_steer && !retried) {
      if (await askSteerPassword()) return post(action, true);
      return;
    }
    if (!response.ok) alert(data.error || ("HTTP " + response.status));
    poll();
  }

  function duration(seconds) {
    if (seconds < 90) return seconds + " s";
    if (seconds < 5400) return Math.round(seconds / 60) + " min";
    if (seconds < 172800) return (seconds / 3600).toFixed(1) + " h";
    return (seconds / 86400).toFixed(1) + " days";
  }
  function deadlineText(watcher) {
    return watcher.deadline ? when(new Date(watcher.deadline * 1000).toISOString()) : "";
  }
  /* One line about the Claude session, from its heartbeats (cycle.watcher_status on the server). */
  function sessionLine(status) {
    const watcher = status.watcher || { state: "none" };
    const last = watcher.seen_at ? `last heartbeat ${duration(watcher.seconds)} ago (${when(watcher.seen_at)})` : "";
    const until = deadlineText(watcher);
    const doing = watcher.doing || { planning: "harvesting the comments into the plan", implementing: "implementing the plan",
      going: "taking the next step a reader asked for" }[watcher.exit] || watcher.exit;
    const parts = {
      none: ["○", "Claude's watcher has not run on this site yet."],
      watching: ["●", `Claude is watching: ${last}.` + (until ? ` Session until ${until}.` : "")],
      working: ["●", watcher.doing ? `Claude is working: ${watcher.doing} (last word ${duration(watcher.seconds)} ago).`
        : `Claude is ${doing}: the watcher paused ${duration(watcher.seconds)} ago and comes back afterwards.`],
      ended: ["○", `No Claude session at the moment: the last one ended (${last}). Comments wait until the next session.`],
      gone: ["⚠", watcher.exit && watcher.exit !== "deadline"
        ? `The Claude session seems to have stopped: it has been ${doing} for ${duration(watcher.seconds)}, longer than expected. Comments wait until someone restarts it.`
        : `The Claude session stopped unexpectedly: ${last}` + (until ? `, while its deadline is ${until}` : "") + ". Comments wait until someone restarts it."],
    }[watcher.state] || ["○", ""];
    return el("div", { class: "fb-session fb-session-" + watcher.state, title: "From the watcher's heartbeats (kea watch)" },
      el("span", { class: "fb-session-dot" }, parts[0]), " ", parts[1]);
  }

  function indicator(status) {
    const waiting = status.unplanned || 0;
    const harvested = !!status.cycle.plan_updated_at;
    if (waiting === 0) {
      return el("div", { class: "fb-indicator fb-ok" }, el("b", {}, harvested ? "Every comment is in this plan." : "No comments yet."));
    }
    return el("div", { class: "fb-indicator fb-wait" },
      el("b", {}, `${waiting} comment(s) not in the plan. `),
      harvested ? `Made after the harvest of ${when(status.cycle.harvested_until || status.cycle.plan_updated_at)}: Harvest again to add them, or they stay for the next cycle.`
        : "Claude adds them when someone presses Harvest.");
  }

  function planActions(status) {
    const box = document.getElementById("fb-plan-actions");
    if (!box) return;
    const state = status.cycle.state;
    const items = Number(box.dataset.items || 0);
    const waiting = status.unplanned || 0;
    const watching = status.watcher && ["watching", "working"].includes(status.watcher.state);
    const harvest = (label, title, main) => el("button", { class: main ? "fb-implement" : "fb-secondary",
      onclick: () => post("harvest"), title }, label);
    box.replaceChildren(sessionLine(status));
    if (state === "collecting") {
      box.append(indicator(status),
        harvest("Harvest comments", "Claude folds every comment not yet in the plan into it", waiting > 0),
        el("span", { class: "fb-help" }, " Comment anywhere; Claude reads nothing until someone presses Harvest. "
          + "After the harvest the plan stands, and you can Implement it." + (watching ? "" : " No Claude session is watching now: the harvest waits for the next one.")));
    } else if (state === "harvest-requested") {
      box.append(indicator(status),
        el("button", { class: "fb-secondary", onclick: () => post("cancel") }, "Cancel the harvest"),
        el("span", { class: "fb-help" }, ` Harvest asked by ${status.cycle.by} (${when(status.cycle.since)}); Claude is folding the comments into this plan.`
          + (watching ? "" : " No Claude session is watching now: the harvest waits for the next one.")));
    } else if (state === "harvested") {
      box.append(indicator(status),
        el("button", { class: "fb-implement", onclick: () => {
          const left = waiting ? `\n\n${waiting} comment(s) made after the harvest are not in this plan; they stay for the next cycle.` : "";
          if (confirm("Ask Claude to implement this plan now? Comments are paused until the new version is released." + left)) post("implement");
        }, ...(items ? {} : { disabled: "disabled" }) }, "Implement the plan"),
        harvest(waiting ? `Harvest again (${waiting})` : "Harvest again", "Fold the comments made since the last harvest into the plan"),
        el("span", { class: "fb-help" }, ` Harvested ${when(status.cycle.plan_updated_at)}; the plan stands until the next harvest. `
          + (items ? "" : "Nothing to implement yet.")));
    } else if (state === "implement-requested") {
      box.append(el("button", { class: "fb-secondary", onclick: () => post("cancel") }, "Cancel the request"),
        el("span", { class: "fb-help" }, ` Requested by ${status.cycle.by} (${when(status.cycle.since)}); Claude has not started yet.`));
    } else if (state === "implementing") {
      box.append(el("span", { class: "fb-help" }, `Claude is implementing this plan (since ${when(status.cycle.since)}).`));
    }
  }

  function goneBanner(status) {
    const watcher = status.watcher || {};
    if (!status.can_steer || watcher.state !== "gone") return false;
    let dismissed = "";
    try { dismissed = sessionStorage.getItem("kea-gone-dismissed") || ""; } catch (error) { /* storage blocked */ }
    if (dismissed === watcher.seen_at) return false;
    showBanner("gone", el("b", {}, "The Claude session stopped unexpectedly. "),
      `Last heartbeat ${duration(watcher.seconds)} ago (${when(watcher.seen_at)}); comments and plan requests wait until someone restarts it. `,
      el("a", { href: PREFIX + "plan.html" }, "Details on the plan page"), ".",
      el("button", { class: "fb-secondary", onclick: () => {
        try { sessionStorage.setItem("kea-gone-dismissed", watcher.seen_at); } catch (error) { /* storage blocked */ }
        hideBanner();
      } }, "Dismiss"));
    return true;
  }

  /* Approve & go (feedback/tags.py go): the request, then the agent's work on it, said on every page so a click is
     never followed by silence; the Progress page lists them (#progress-live). */
  function pageTitle(item) { return item.title || item.page; }
  function goBanner(status) {
    const goes = status.goes || [], watcher = status.watcher || {};
    const working = watcher.state === "working" && watcher.exit === "going";
    if (!goes.length && !working) return false;
    const progress = el("a", { href: PREFIX + "progress.html" }, "Progress");
    if (working) {
      showBanner("go", el("b", {}, "Claude is working: "), watcher.doing || "the next step a reader asked for",
        ` (last word ${duration(watcher.seconds)} ago)` + (goes.length > 1 ? `; ${goes.length - 1} more request(s) waiting` : "") + ". ",
        progress, ".");
      return true;
    }
    const first = goes[0];
    const watching = watcher.state === "watching";
    const label = (first.text || "").replace(/^(Approve & |Go: )/i, "") || "the next step";
    showBanner("go", el("b", {}, `${/^Approve & /i.test(first.text || "") ? "Approve & " + label : label[0].toUpperCase() + label.slice(1)}: `),
      `${pageTitle(first)}, asked by ${first.by} ${when(first.at)}. `,
      watching ? "Claude picks it up within a minute. " : "No Claude session is watching now: the request waits until one starts. ",
      goes.length > 1 ? `${goes.length - 1} more waiting. ` : "", progress, ".");
    return true;
  }
  function progressLive(status) {
    const box = document.getElementById("progress-live");
    if (!box) return;
    const goes = status.goes || [], watcher = status.watcher || {};
    const pages = JSON.parse(box.dataset.pages || "{}");
    const parts = [sessionLine(status)];
    if (goes.length) {
      const rows = goes.map((item, index) => {
        const busy = index === 0 && watcher.state === "working" && watcher.exit === "going";
        const href = pages[item.page];
        return el("tr", {}, el("td", {}, href ? el("a", { href: PREFIX + href }, pageTitle(item)) : pageTitle(item)),
          el("td", {}, item.text || "the next step"), el("td", {}, `${item.by}, ${when(item.at)}`),
          el("td", {}, el("span", { class: "rs " + (busy ? "rs-running" : "rs-agent") },
            busy ? "⟳ " + (watcher.doing || "working") : index === 0 && watcher.state === "watching" ? "▶ being picked up"
              : "▶ waiting for the agent")));
      });
      parts.push(el("table", { class: "progress-table" }, el("thead", {}, el("tr", {}, el("th", {}, "Approve & go on"),
        el("th", {}, "Asked for"), el("th", {}, "By"), el("th", {}, "State"))), el("tbody", {}, ...rows)));
    } else {
      parts.push(el("p", { class: "help" }, "No Approve & go request is open."));
    }
    box.replaceChildren(...parts);
    const signing = new Set(status.signing || []), going = new Set(goes.map(item => item.page));
    for (const row of document.querySelectorAll(".progress-table tr[data-page]")) {
      const cell = row.querySelector(".live-cell");
      const key = row.dataset.page;
      if (cell) cell.textContent = going.has(key) ? "asked: see the top of the page" : signing.has(key) ? "signed on the site; written onto the page at the next harvest" : "";
    }
  }

  function apply(status) {
    const cycle = status.cycle;
    const onPlan = !!document.getElementById("fb-plan-actions");
    const commentsHere = !["implement-requested", "implementing"].includes(cycle.state);
    document.body.classList.toggle("fb-frozen", !commentsHere);
    if (!BUILD && status.build && status.build.build_id) BUILD = status.build.build_id;   // the build this page came with
    const newBuild = status.build && status.build.build_id && BUILD && status.build.build_id !== BUILD;
    if (goneBanner(status)) {
      /* shown: more urgent than the cycle banners for whoever can restart the session */
    } else if (cycle.state === "implement-requested") {
      showBanner("frozen", el("b", {}, "Comments are paused. "),
        `${cycle.by} asked Claude to implement the plan (${when(cycle.since)}). `,
        el("a", { href: PREFIX + "plan.html" }, "See the plan"), ".");
    } else if (cycle.state === "implementing") {
      showBanner("frozen", el("b", {}, "Claude is implementing the plan. "),
        "Comments are paused; this page reloads when the new version is released. ",
        el("a", { href: PREFIX + "plan.html" }, "See the plan"), ".");
    } else if (newBuild && !typing() && lastState !== null) {
      location.reload(); return;
    } else if (goBanner(status)) {
      /* shown: an Approve & go is waiting or being worked on */
    } else if (newBuild) {
      if (!typing() && lastState !== null) { location.reload(); return; }
      showBanner("new", el("b", {}, "A new version of the site is available. "),
        el("button", { class: "fb-secondary", onclick: () => location.reload() }, "Reload"),
        typing() ? " (finish your comment first)" : "");
    } else {
      hideBanner();
    }
    const pill = document.getElementById("fb-plan-state");
    if (pill && pill.textContent !== "implemented") {
      pill.textContent = cycle.state;
      pill.className = "pill s-" + cycle.state;
    }
    planActions(status);
    progressLive(status);
    lastState = cycle.state;
    window.keaStatus = status;
    window.dispatchEvent(new CustomEvent("kea-status", { detail: status }));
  }

  /* The reader in the menu bar (render.py: <span class='user'>): the signed-in name opens a small menu with the
     reader's comments, help and sign out; a public site read without a login shows Help and Sign in. */
  let userKey = null;
  /* The versions, at the foot of the reader's menu (render.py puts data-kea and data-site-version on the slot): the
     Kea that built the site, the site's own version, and the Kea of the comment server or hub, marked when the two
     differ (some features may then not work). */
  function versionLine(slot, status) {
    const built = slot.dataset.kea, server = status && status.server_version;
    const where = status && status.on_hub ? "hub" : "server";
    const parts = [`Kea ${built}`];
    if (slot.dataset.siteVersion) parts.push(`site ${slot.dataset.siteVersion}`);
    if (server) parts.push(server === built ? `${where} the same` : `${where} Kea ${server}`);
    return el("div", { class: "versions" + (server && server !== built ? " differs" : ""),
      title: server && server !== built ? `The site was built with Kea ${built}; the ${status.on_hub ? "Kea hub" : "comment server"} `
        + `runs Kea ${server}: some features may not work until both match.` : "" }, parts.join(" · "));
  }

  function renderUser(status) {
    const slot = document.querySelector(".topbar .user");
    if (!slot) return;
    const name = status && status.signed_in ? (status.you || (status.account ? status.orcid : "") || "Signed in") : "";
    const hub = status && status.hub;                 // on a Kea hub: its front page and the reader's other projects
    const key = status === null ? "anonymous" : name + "|" + (status && status.sign_out) + "|" + JSON.stringify(hub || null)
      + "|" + (status && status.server_version);
    if (key === userKey) return;
    userKey = key;
    const help = el("a", { href: slot.dataset.help, title: "How to read this site, and about Kea" }, "Help");
    if (status === null) {                       // public site, not signed in
      const next = "/" + location.pathname.slice(new URL(BASE, location.href).pathname.length) + location.search;
      slot.replaceChildren(help, el("a", { href: BASE + "login?next=" + encodeURIComponent(next) }, "Sign in"));
      return;
    }
    if (!name) { slot.replaceChildren(help); return; }
    const menu = el("div", { class: "user-menu", role: "menu", hidden: "" },
      el("div", { class: "who" }, status.account ? `Signed in with ORCID ${status.orcid}` : "Signed in with the site password"),
      el("a", { href: slot.dataset.comments + "?mine=1", role: "menuitem" }, "My comments"),
      el("a", { href: slot.dataset.help, role: "menuitem" }, "Help"),
      ...(hub ? [el("div", { class: "sep-line" }),
        el("a", { href: hub.home, role: "menuitem", title: "The hub's front page: your projects and roles" }, "Kea hub"),
        ...(hub.projects.length ? [el("div", { class: "group" }, "Other projects")] : []),
        ...hub.projects.map(project => el("a", { href: project.url, role: "menuitem", class: "project",
          title: project.role ? "Your role: " + project.role : "Public project" },
          project.title, project.role ? el("span", { class: "role" }, project.role) : null))] : []),
      status.sign_out ? el("div", { class: "sep-line" }) : null,
      status.sign_out ? el("a", { href: status.sign_out, role: "menuitem" }, "Sign out") : null,
      el("div", { class: "sep-line" }), versionLine(slot, status));
    const button = el("button", { class: "user-name", type: "button", title: name, "aria-haspopup": "true",
      "aria-expanded": "false", onclick: event => {
        event.stopPropagation();
        menu.hidden = !menu.hidden;
        button.setAttribute("aria-expanded", String(!menu.hidden));
        slot.closest(".topbar").classList.toggle("user-open", !menu.hidden);   // above the page buttons
      } }, name);
    slot.replaceChildren(button, menu);
    const close = () => { menu.hidden = true; button.setAttribute("aria-expanded", "false"); slot.closest(".topbar").classList.remove("user-open"); };
    document.addEventListener("click", event => { if (!slot.contains(event.target)) close(); });
    document.addEventListener("keydown", event => { if (event.key === "Escape") close(); });
    if (window.keaFitTopbar) window.keaFitTopbar();
    mineFilter(status, name);
  }
  /* feedback.html?mine=1: only the threads the reader started or answered (comments.py: data-people, data-orcid). */
  function mineFilter(status, name) {
    if (!/[?&]mine=1\b/.test(location.search)) return;
    const threads = document.querySelectorAll(".fb-thread[data-people]");
    if (!threads.length) return;
    const who = "|" + name.trim().toLowerCase() + "|";
    let shown = 0;
    for (const thread of threads) {
      const mine = thread.dataset.people.includes(who) || (status.orcid && thread.dataset.orcid === status.orcid);
      thread.hidden = !mine;
      shown += mine ? 1 : 0;
    }
    const heading = document.querySelector("main h1");
    if (heading && !document.querySelector(".fb-mine-note")) {
      heading.after(el("p", { class: "fb-mine-note help" }, `Your comments (${name}): ${shown}. `,
        el("a", { href: location.pathname }, "Show all comments")));
    }
  }

  async function poll() {
    try {
      const response = await fetch(BASE + "api/status", { credentials: "same-origin", cache: "no-store" });
      if (response.status === 401) { renderUser(null); return false; }
      if (!response.ok) return false;
      const status = await response.json();
      renderUser(status);
      apply(status);
      return true;
    } catch (error) {
      return false;
    }
  }

  /* every POLL_MS; every FAST_MS while an Approve & go waits or runs (the reader who clicked sees it move) */
  const FAST_MS = 6000;
  function busy() {
    const status = window.keaStatus;
    return !!(status && ((status.goes || []).length || (status.watcher && status.watcher.exit === "going"
      && status.watcher.state === "working")));
  }
  async function start() {
    if (!await poll()) return;
    const next = () => setTimeout(async () => { await poll(); next(); }, busy() ? FAST_MS : POLL_MS);
    next();
    window.keaPollNow = poll;                        // feedback.js: right after an Approve & go
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
