/* Review-cycle status on every page (feedback/cycle.py, GET /api/status).
 *
 * - Polls the server every POLL_MS. Without a server (file:// or plain hosting) it does nothing.
 * - When a new site build has been released, offers a reload (and reloads by itself if nothing is being typed).
 * - The cycle (feedback/cycle.py, since 1.18): comments everywhere; a PI presses "Harvest comments" and
 *   Claude folds them into the plan, which then stands until the next harvest; the plan page counts the comments
 *   made since; "Implement the plan" (after a harvest) pauses comments until the release (a banner on every page,
 *   comment controls hidden; the server refuses them with 423 anyway).
 * - The round has four steps (since 1.31, again): Review (readers comment and sign off; Claude does nothing),
 *   Harvest (Claude records the sign-offs and writes the plan), Implement (Claude does what the plan lists),
 *   Release. The menu bar names the step for every reader (a button for PIs); the Progress and plan pages mark it
 *   on their four-step strip (#round-steps); Progress also shows Claude's session (#progress-live).
 *   A "kea-status" event hands each status to feedback.js (pages signed with their stage elsewhere).
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
        el("p", { class: "fb-steer-help" }, "Harvesting the comments into the plan and asking Claude to implement it " +
          "need the iteration password (not the site password). Ask the site owner for it."),
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

  async function post(action, retried) {
    // the server records who asked: a reader without a name (no account, no comment yet) gives it first, as for a
    // comment (the same fb_name cookie as feedback.js)
    const named = window.keaStatus && (window.keaStatus.you || window.keaStatus.account);
    if (!named && !/(?:^|; )fb_name=[^;]/.test(document.cookie)) {
      const name = (prompt("Your name (shown with your comments and requests):") || "").trim();
      if (!name) return;
      document.cookie = "fb_name=" + encodeURIComponent(name) + "; max-age=" + 365 * 86400 + "; path=/; samesite=lax";
    }
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
    const doing = watcher.doing || { planning: "harvesting the comments into the plan", implementing: "implementing the plan" }[watcher.exit] || watcher.exit;
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

  /* The step of the round in the menu bar, for every reader: PIs (status.can_steer: a PI or director account on a
     hub, the iteration password, or a site without one) get the button that moves the round on (Harvest · N while
     comments and sign-offs wait; ▶ Implement once the plan stands), other readers the same words as a link to
     Progress. While Claude works it says so. The plan page keeps the full controls (Harvest again, Cancel). */
  function menuCycle(status) {
    const bar = document.querySelector(".topbar");
    if (!bar) return;
    let slot = bar.querySelector(".cycle-tool");
    if (!slot) {
      slot = el("span", { class: "cycle-tool" });
      bar.insertBefore(slot, bar.querySelector(".page-tools") || bar.querySelector(".user"));
    }
    const cycle = status.cycle, waiting = status.unplanned || 0, steer = !!status.can_steer;
    const known = status.build && status.build.plan_items;
    const items = known ? Number(known[String(cycle.cycle)] || 0) : null;      // null: a build before 1.29.3
    const button = (cls, label, title, onclick) => el("button", { class: cls, title, onclick }, label);
    const toProgress = () => { location.href = PREFIX + "progress.html"; };
    const toPlan = () => { location.href = PREFIX + "plan.html"; };
    let content = null;
    if (cycle.state === "collecting") {
      if (waiting && steer) content = button("ct-harvest", `⇣ Harvest · ${waiting}`, `Review round: ${waiting} comment(s) and sign-off(s) wait. `
        + "Harvest: Claude records the sign-offs and writes the plan; nothing runs until Implement", () => post("harvest"));
      else if (waiting) content = button("ct-busy", `Review · ${waiting} for the plan`, "Review round: Claude does nothing until a PI presses Harvest", toProgress);
    } else if (cycle.state === "harvest-requested") {
      content = button("ct-busy", "⟳ Claude is writing the plan", `Harvest asked by ${cycle.by} (${when(cycle.since)}); Claude records the sign-offs and folds the comments into the plan. It runs nothing.`, toPlan);
    } else if (cycle.state === "harvested") {
      const planned = items === null || items > 0;
      // comments made after the plan: the round is back in Review; Harvest again takes them in (it rewrites the plan)
      const again = steer && waiting ? button("ct-harvest", `⇣ Harvest again · ${waiting}`, `${waiting} comment(s) or sign-off(s) came in after the plan `
        + "was written. Harvest again: Claude takes them into the plan too; nothing runs until Implement", () => post("harvest")) : null;
      const implement = steer && planned ? button(again ? "ct-implement ct-minor" : "ct-implement", "▶ Implement", "The plan is ready. Implement: Claude does what the plan lists, nothing more (comments pause until the release)" +
          (waiting ? `; the ${waiting} comment(s) made after the harvest are not in it and stay for the next round` : ""), () => {
            const left = waiting ? `\n\n${waiting} comment(s) made after the harvest are not in this plan; they stay for the next round. To take them in first, press Harvest again.` : "";
            if (confirm("Ask Claude to implement the plan now? Claude does what the plan lists, nothing more. Comments are paused until the new version is released." + left)) post("implement");
          }) : null;
      if (again || implement) content = [again, implement].filter(Boolean);
      else if (waiting) content = button("ct-busy", `Review · ${waiting} since the plan`, "Comments came in after the plan; a PI can harvest again", toProgress);
      else if (planned) content = button("ct-busy", "Plan ready", "Claude has written the plan; it runs when a PI presses Implement", toPlan);
    } else if (cycle.state === "implement-requested") {
      content = button("ct-busy", "▶ Implement asked", `Asked by ${cycle.by} (${when(cycle.since)}); Claude has not started yet`, toPlan);
    } else if (cycle.state === "implementing") {
      content = button("ct-busy", "⟳ Claude is working", `Claude is implementing the plan (since ${when(cycle.since)}); comments pause until the release`, toPlan);
    }
    const shown = content ? [].concat(content) : [];
    const label = shown.map(node => node.textContent + "|" + node.title).join("||");
    if (slot.dataset.label === label) return;          // unchanged: keep the buttons (and any focus on them)
    slot.dataset.label = label;
    slot.replaceChildren(...shown);
    slot.hidden = !content;
    window.dispatchEvent(new Event("resize"));          // the menu bar fits itself again (render.TOPBAR_JS)
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

  /* The four-step strip (pages.ROUND_STEPS, on Progress and the plan page): mark the step the round is in. When
     comments came in after the harvest, the round is back in Review and Harvest says the plan is out of date. */
  function roundSteps(status) {
    const strip = document.getElementById("round-steps");
    if (!strip) return;
    const state = status.cycle.state, comments = status.unplanned || 0;
    const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;
    // a harvest done while readers go on commenting: the round is back in Review, and the plan misses those comments
    const reopened = state === "harvested" && comments > 0;
    const [step, word] = reopened ? ["review", `again: ${plural(comments, "comment")} since the plan`]
      : { "collecting": ["review", "now"], "harvest-requested": ["harvest", "now"],
      "harvested": ["harvest", "done: plan ready"], "implement-requested": ["implement", "asked"],
      "implementing": ["implement", "now"] }[state] || ["", ""];
    for (const item of strip.querySelectorAll("li")) {
      item.classList.toggle("now", item.dataset.step === step);
      const warn = reopened && item.dataset.step === "harvest";
      item.classList.toggle("warn", warn);
      item.querySelector("b").dataset.now = item.dataset.step === step ? word : warn ? "plan out of date" : "";
      item.title = warn ? `A plan was written, but ${plural(comments, "comment")} came in after it and ${comments === 1 ? "is" : "are"} not in it. `
        + "A PI can press Harvest again to take them in; or they wait for the next round." : item.dataset.help || "";
    }
  }
  function progressLive(status) {
    const box = document.getElementById("progress-live");
    if (!box) return;
    box.replaceChildren(sessionLine(status));
    /* Pages signed on the site (an Approve; before 1.31.1 also every page on its Signs: line): the sign-off waits
       for the harvest (or is being harvested). */
    const state = status.cycle.state;
    const signing = new Set(status.signing || []);
    const harvesting = state === "harvest-requested";
    for (const row of document.querySelectorAll(".progress-table tr[data-page]")) {
      const cell = row.querySelector(".live-cell");
      const key = row.dataset.page;
      const stands = row.querySelector(".rs-you, .rs-live");
      const signed = signing.has(key);
      if (stands && !stands.dataset.was) { stands.dataset.was = stands.textContent; stands.dataset.cls = stands.className; }
      if (stands) {
        stands.textContent = !signed ? stands.dataset.was : harvesting ? "✓ signed · being harvested" : "✓ signed · waits for Harvest";
        stands.className = !signed ? stands.dataset.cls : "rs rs-live rs-done";
      }
      if (cell) cell.textContent = !signed ? "" : harvesting ? "Claude is writing it on and planning the next step" : "";
      row.classList.toggle("signed-live", signed);
    }
    // "Start signing at the top": the first page in the order that is still unsigned
    const start = document.getElementById("sign-start");
    const first = ((status.build || {}).sign_order || []).find(item => !signing.has(item.key) && item.href);
    if (start) { start.hidden = !first; if (first) start.href = PREFIX + first.href; }
    // the count of "Needs your sign-off": the rows still waiting for a click
    const count = document.querySelector("h2 .count");
    if (count) count.textContent = document.querySelectorAll(".progress-table tr[data-page]:not(.signed-live)").length;
    // Claude's next steps: when they run
    const when_ = { "collecting": "next Harvest → plan; runs at Implement", "harvest-requested": "being planned now",
      "harvested": "in the plan (see Plan); runs at Implement", "implement-requested": "Implement asked",
      "implementing": "Claude is implementing the plan" }[state];
    for (const td of document.querySelectorAll("td.next-when")) if (when_) td.textContent = when_;
    // the route's "waiting for you" cells: every page they wait on is signed now (links → keys: data-pages)
    let byHref = {};
    try { byHref = Object.fromEntries(Object.entries(JSON.parse(box.dataset.pages || "{}")).map(([key, href]) => [href, key])); }
    catch (error) { /* no map: the route cells stay as built */ }
    for (const td of document.querySelectorAll("td.rs-cell.rs-you")) {
      const keys = Array.from(td.querySelectorAll(".rs-pages a")).map(link => byHref[link.getAttribute("href")]).filter(Boolean);
      const mark = td.querySelector(".rs");
      if (!mark.dataset.was) mark.dataset.was = mark.textContent;
      const all = keys.length && keys.every(key => signing.has(key));
      if (!mark.dataset.cls) mark.dataset.cls = mark.className;
      mark.textContent = all ? "✓ signed · waits for Harvest" : mark.dataset.was;
      mark.className = all ? "rs rs-done" : mark.dataset.cls;
    }
  }

  /* Progress in the menu bar: the pages that wait for a sign-off (render.py: data-waiting), less those signed on
     the site since the build. */
  function navCount(status) {
    const signing = new Set(status.signing || []);
    for (const count of document.querySelectorAll(".nav-count[data-waiting]")) {
      let keys = [];
      try { keys = JSON.parse(count.dataset.waiting); } catch (error) { continue; }
      const left = keys.filter(key => !signing.has(key)).length;
      count.textContent = left;
      count.hidden = !left;
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
    menuCycle(status);
    progressLive(status);
    roundSteps(status);
    navCount(status);
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

  async function start() {
    if (!await poll()) return;
    const next = () => setTimeout(async () => { await poll(); next(); }, POLL_MS);
    next();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
