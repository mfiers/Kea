/* Review-cycle status on every page (feedback/cycle.py, GET /api/status).
 *
 * - Polls the server every POLL_MS. Without a server (file:// or plain hosting) it does nothing.
 * - When a new site build has been released, offers a reload (and reloads by itself if nothing is being typed).
 * - Two phases (cycle 1 item 8): while collecting, comments everywhere; after "Freeze for review", comments only
 *   on the plan; then "Implement the plan" (enabled only when every comment is in the plan) or "Unfreeze".
 *   While frozen, requested or implementing, a banner shows on every page and the comment controls are hidden
 *   where comments are not accepted (the server refuses them with 423 anyway).
 * - On the plan page (#fb-plan-actions) shows the buttons and a live indicator: are all comments in the plan,
 *   and the Claude session (status.watcher, cycle.watcher_status): watching, working, ended or gone, with the time
 *   since the last heartbeat. When the session stopped unexpectedly ("gone"), readers who may steer get a banner
 *   on every page (dismissable until the next change).
 * The page's build id comes from data-build on this script tag.
 */
(function () {
  "use strict";
  const script = document.currentScript;
  const BUILD = script.dataset.build || "";
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
  }
  function hideBanner() { if (banner) banner.hidden = true; }

  // Freeze, Unfreeze, Implement and Cancel need the iteration password (a second password besides the site's);
  // the server answers 403 {need_steer: true} until it has been entered once (a cookie remembers it).
  function askSteerPassword() {
    return new Promise(resolve => {
      const input = el("input", { type: "password", autocomplete: "off", class: "fb-steer-input" });
      const error = el("p", { class: "fb-steer-error" });
      const dialog = el("dialog", { class: "fb-steer not-annotatable" },
        el("p", {}, el("strong", {}, "Iteration password")),
        el("p", { class: "fb-steer-help" }, "Starting or stopping a review round and asking Claude to implement the " +
          "plan need the iteration password (not the site password). Ask the site owner for it."),
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
    const doing = { planning: "folding new comments into the plan", implementing: "implementing the plan" }[watcher.exit] || watcher.exit;
    const parts = {
      none: ["○", "Claude's watcher has not run on this site yet."],
      watching: ["●", `Claude is watching: ${last}.` + (until ? ` Session until ${until}.` : "")],
      working: ["●", `Claude is ${doing}: the watcher paused ${duration(watcher.seconds)} ago and comes back afterwards.`],
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
    const watching = status.watcher ? status.watcher.state === "watching" : false;
    if (waiting === 0) {
      return el("div", { class: "fb-indicator fb-ok" }, el("b", {}, "All comments are in this plan."));
    }
    return el("div", { class: "fb-indicator fb-wait" },
      el("b", {}, `${waiting} comment(s) are not in the plan yet. `),
      watching ? "Claude adds them about two minutes after the last comment." : "");
  }

  function planActions(status) {
    const box = document.getElementById("fb-plan-actions");
    if (!box) return;
    const state = status.cycle.state;
    const items = Number(box.dataset.items || 0);
    const waiting = status.unplanned || 0;
    box.replaceChildren(sessionLine(status));
    if (state === "collecting") {
      box.append(indicator(status),
        el("button", { class: "fb-implement", onclick: () => post("freeze"),
          title: "Comments only on this plan until Implement or Unfreeze" }, "Freeze for review"),
        el("span", { class: "fb-help" }, " Phase 1 of 2: comments everywhere; Claude folds them into this plan. "
          + "Freeze when you are done commenting: then only this plan can be commented on."));
    } else if (state === "frozen") {
      const ready = waiting === 0 && items > 0;
      box.append(indicator(status),
        el("button", { class: "fb-implement", onclick: () => {
          if (confirm("Ask Claude to implement this plan now? No comments are possible until the new version is released.")) post("implement");
        }, ...(ready ? {} : { disabled: "disabled" }) }, "Implement the plan"),
        el("button", { class: "fb-secondary", onclick: () => post("unfreeze") }, "Unfreeze"),
        el("span", { class: "fb-help" }, ` Phase 2 of 2: frozen by ${status.cycle.by} (${when(status.cycle.since)}); comments only on this plan. `
          + (ready ? "Implement, or Unfreeze to comment everywhere again."
             : items ? "Implement is possible once every comment is in the plan." : "Nothing to implement yet.")));
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

  function apply(status) {
    const cycle = status.cycle;
    const onPlan = !!document.getElementById("fb-plan-actions");
    const commentsHere = cycle.state === "collecting" || (cycle.state === "frozen" && onPlan);
    document.body.classList.toggle("fb-frozen", !commentsHere);
    const newBuild = status.build && status.build.build_id && BUILD && status.build.build_id !== BUILD;
    if (goneBanner(status)) {
      /* shown: more urgent than the cycle banners for whoever can restart the session */
    } else if (cycle.state === "frozen") {
      showBanner("frozen", el("b", {}, "Frozen for review. "),
        `${cycle.by} froze the site (${when(cycle.since)}); comments are open only on the plan. `,
        el("a", { href: PREFIX + "plan.html" }, "Go to the plan"), ".");
    } else if (cycle.state === "implement-requested") {
      showBanner("frozen", el("b", {}, "Comments are paused. "),
        `${cycle.by} asked Claude to implement the plan (${when(cycle.since)}). `,
        el("a", { href: PREFIX + "plan.html" }, "See the plan"), ".");
    } else if (cycle.state === "implementing") {
      showBanner("frozen", el("b", {}, "Claude is implementing the plan. "),
        "Comments are paused; this page reloads when the new version is released. ",
        el("a", { href: PREFIX + "plan.html" }, "See the plan"), ".");
    } else if (newBuild) {
      if (!typing() && lastState !== null) { location.reload(); return; }
      showBanner("new", el("b", {}, "A new version of the site is available. "),
        el("button", { class: "fb-secondary", onclick: () => location.reload() }, "Reload"),
        typing() ? " (finish your comment first)" : "");
    } else {
      hideBanner();
    }
    if (newBuild && cycle.state === "frozen" && onPlan && !typing()) { location.reload(); return; }
    const pill = document.getElementById("fb-plan-state");
    if (pill && pill.textContent !== "implemented") {
      pill.textContent = cycle.state;
      pill.className = "pill s-" + cycle.state;
    }
    planActions(status);
    lastState = cycle.state;
  }

  async function poll() {
    try {
      const response = await fetch(BASE + "api/status", { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) return false;
      apply(await response.json());
      return true;
    } catch (error) {
      return false;
    }
  }

  async function start() {
    if (await poll()) setInterval(poll, POLL_MS);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
