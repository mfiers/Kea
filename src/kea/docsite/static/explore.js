/* explore.js: the graph view (explore.html). Every page of the site as one tree, left to right along the route of an
 * experiment: questions, hypotheses, steps, results, figures, conclusions, and beside them the caveats, decisions,
 * premises and artefacts. One band per question; a column is always the same stage. Data: _graph.json (explore.py).
 *
 * Walking it follows the scientific logic: → goes to what follows from this page (a question's hypotheses, the step
 * that tests a hypothesis, the result a step made, the conclusion a result supports), ← to what it rests on, ↑ ↓ to
 * the page above or below in the same stage. The selected page lights up what it rests on (blue) and what rests on it
 * (orange). Space (or a click) zooms into the page itself, where you read, comment and sign as on the page; Esc
 * zooms back out to the same place. n goes to the next page that waits for a sign-off, top down.
 *
 * The page inside the zoom is the site's own page in an iframe; render.page marks it kea-embed (no menu bar, no
 * crumbs) and kea.js sends its Esc here (window.keaExplore.close). */
(function () {
  "use strict";
  const root = document.getElementById("xg");
  if (!root) return;

  const COLOUR = { experiment: "#333", question: "#1f77b4", hypothesis: "#a23c9e", step: "#2a7f62", result: "#8c564b",
    figure: "#17818a", conclusion: "#c0392b", caveat: "#c64f00", decision: "#757575", premise: "#6a4c93",
    artefact: "#966d09", resource: "#5b6b2f", term: "#5f6b7a", reference: "#3d5a80", fold: "#5d6475" };
  const KIND = { experiment: "experiment", question: "question", hypothesis: "hypothesis", step: "step", result: "result",
    figure: "figure", conclusion: "conclusion", caveat: "caveat", decision: "decision", premise: "premise",
    artefact: "artefact", resource: "resource", term: "term", reference: "reference" };
  const PLURAL = { hypothesis: "hypotheses", step: "steps", result: "results", figure: "figures", conclusion: "conclusions",
    caveat: "caveats", decision: "decisions", premise: "premises", artefact: "artefacts", resource: "resources",
    term: "terms", reference: "references" };
  const LETTER = { experiment: "E", question: "Q", hypothesis: "H", step: "S", result: "R", figure: "F", conclusion: "C",
    caveat: "W", decision: "D", premise: "P", artefact: "A", resource: "O", term: "T", reference: "B" };
  // the columns, left to right; beside: pages that qualify the route rather than continue it
  const COLUMNS = [["question", "Questions"], ["hypothesis", "Hypotheses"], ["step", "Steps"], ["result", "Results"],
    ["figure", "Figures"], ["conclusion", "Conclusions"], ["beside", "Beside: caveats · decisions · premises · artefacts"]];
  const BESIDE = new Set(["caveat", "decision", "premise", "artefact"]);
  const LIBRARY = new Set(["resource", "term", "reference"]);
  const GONE = new Set(["dropped", "deprecated", "superseded", "unavailable"]);
  const NODE_W = 232, NODE_H = 54, GAP_Y = 10, GAP_X = 40, EXP_W = 40, PAD = 14, BAND_GAP = 10, HEAD = 34, LEFT = 14;
  const reduced = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  let data = null, byKey = {}, incoming = {}, downMap = {}, byPath = {};
  let bands = [], pos = {}, colX = [], usedCols = [], worldW = 0, worldH = 0;
  let selected = null, scale = 1, fitted = false, zoom = null, signing = new Set(), signOrder = [];
  const lastChild = {};
  const folded = new Set(load("kea-xg-folded", null) || []);
  const unfoldedOnce = new Set(load("kea-xg-unfolded", null) || []);

  function load(name, fallback) { try { const raw = sessionStorage.getItem(name); return raw ? JSON.parse(raw) : fallback; } catch (error) { return fallback; } }
  function save(name, value) { try { sessionStorage.setItem(name, JSON.stringify(value)); } catch (error) { /* private window */ } }
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [name, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (name === "class") node.className = value;
      else if (name === "style") node.style.cssText = value;
      else if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
      else node.setAttribute(name, value === true ? "" : value);
    }
    for (const child of children.flat()) if (child !== null && child !== undefined && child !== false) node.append(child);
    return node;
  }
  const words = (text) => String(text || "").replace(/_/g, " ");
  const tagOf = (node) => {
    if (node.pseudo || (node.tag && node.tag.length <= 4)) return node.tag || LETTER[node.type] || "?";
    const year = node.type === "reference" && /(\d{2})[a-z]?$/.exec(node.tag || "");      // Akiyama et al. 1994: Aki94
    return year ? node.tag.replace(/[^A-Za-z]/g, "").slice(0, 3) + year[1] : LETTER[node.type] || "?";
  };
  const label = (node) => (node.tag ? node.tag + " " : "") + node.title;

  /* ------------------------------------------------------------------ data */
  async function start() {
    placeBelowBar();
    window.addEventListener("resize", () => { placeBelowBar(); if (fitted && world) { refit(); redraw(); } else drawMini(); });
    try {
      const response = await fetch("_graph.json", { cache: "no-store", credentials: "same-origin" });
      data = await response.json();
    } catch (error) {
      root.append(el("p", { style: "padding:24px" }, "The graph could not be loaded (_graph.json). Every page is also reachable from the ",
        el("a", { href: root.dataset.start || "start.html" }, "start page"), "."));
      return;
    }
    try {
      const build = await (await fetch("_build.json", { cache: "no-store", credentials: "same-origin" })).json();
      signOrder = (build.sign_order || []).map((item) => item.key);
    } catch (error) { signOrder = []; }
    data.nodes.forEach((node, index) => { node.ord = index; byKey[node.key] = node; });
    for (const node of data.nodes) {
      for (const [relation, target] of node.edges) (incoming[target] = incoming[target] || []).push([relation, node.key]);
      byPath[new URL(node.href, location.href).pathname] = node.key;
    }
    for (const node of data.nodes) for (const key of rests(node)) (downMap[key] = downMap[key] || []).push(node.key);
    if (!signOrder.length) signOrder = data.nodes.filter((node) => node.waiting && !node.signed).map((node) => node.key);
    buildBands();
    layout();
    render();
    const [hashKey, openIt] = fromHash();
    const first = (hashKey && byKey[hashKey] && hashKey) || (byKey[load("kea-xg-selected", "")] && load("kea-xg-selected", ""))
      || signOrder.find((key) => byKey[key]) || (bands[0] && bands[0].lead.key) || (data.nodes[0] && data.nodes[0].key);
    if (first) select(first, { instant: true, center: true });
    if (openIt && selected) openZoom(selected);
    window.addEventListener("kea-status", (event) => { live(event.detail); placeBelowBar(); });
    if (window.keaStatus) live(window.keaStatus);
    window.addEventListener("hashchange", () => {
      const [key, open] = fromHash();
      if (!key || !byKey[key]) return;
      if (key !== selected) select(key, { center: true });
      if (open && !(zoom && zoom.key === key)) openZoom(key);
    });
  }

  /* What a page rests on: the pages its relations depend on (graph.upstream) and the page it grows from, so that the
     chain reaches back to the question. */
  function rests(node) {
    const found = new Set(node.up || []);
    if (node.parent && byKey[node.parent] && byKey[node.parent].type !== "experiment" && !node.beside) found.add(node.parent);
    found.delete(node.key);
    return [...found];
  }
  /* The chain of reasoning through a page: followed along the route only (hypothesis, step, result, figure,
     conclusion). A question, a caveat, a decision, a premise or a library page is shown where the chain touches it
     but not followed further: a decision many steps apply would otherwise light up half the experiment. */
  const FOLLOW = new Set(["hypothesis", "step", "result", "figure", "conclusion"]);
  function chain(start, map) {
    const seen = new Set(), todo = [...(map(start) || [])];
    while (todo.length) {
      const key = todo.pop();
      if (seen.has(key) || key === start || !byKey[key]) continue;
      seen.add(key);
      if (FOLLOW.has(byKey[key].type)) todo.push(...(map(key) || []));
    }
    return seen;
  }
  const upOf = (key) => rests(byKey[key]);
  const downOf = (key) => downMap[key] || [];
  function supportsOf(conclusion) {            // the pages a conclusion rests on as evidence, with the direction
    const found = [];
    for (const [relation, from] of incoming[conclusion.key] || []) {
      if (relation === "supports" || relation === "opposes") found.push([from, relation]);
    }
    for (const [relation, target] of conclusion.edges) {
      if (relation === "supported_by") found.push([target, "supports"]);
      if (relation === "opposed_by") found.push([target, "opposes"]);
    }
    return found.filter(([key]) => byKey[key]);
  }

  /* ------------------------------------------------------------------ bands */
  function buildBands() {
    bands = [];
    const projects = [...data.projects];
    for (const node of data.nodes) if (node.type === "experiment" && !projects.includes(node.key)) projects.push(node.key);
    for (const projectKey of projects) {
      const experiment = byKey[projectKey];
      if (!experiment) continue;
      const project = experiment.project;
      const nodes = data.nodes.filter((node) => node.project === project && node.key !== projectKey);
      const questions = nodes.filter((node) => node.type === "question");
      const ordered = [];
      const seen = new Set();
      const visitOnce = (question, depth) => {
        if (seen.has(question.key)) return;
        seen.add(question.key); question.depth = depth; ordered.push(question);
        questions.filter((other) => other.parent === question.key && other.key !== question.key).forEach((other) => visitOnce(other, depth + 1));
      };
      questions.filter((question) => !questions.some((other) => other.key === question.parent && other.key !== question.key)).forEach((question) => visitOnce(question, 0));
      questions.forEach((question) => visitOnce(question, 0));     // a loop of parents: still every question, once
      const add = (band) => { band.project = project; band.experiment = projectKey; bands.push(band); };
      for (const question of ordered) {
        add({ id: question.key, kind: "question", lead: question,
          nodes: nodes.filter((node) => node.question === question.key && node.type !== "question" && !LIBRARY.has(node.type)) });
      }
      const across = nodes.filter((node) => node.type !== "question" && !LIBRARY.has(node.type) && (!node.question || !byKey[node.question]));
      if (across.length) {
        add({ id: project + "#across", kind: "across", nodes: across,
          lead: pseudo(project + "#across", "All", "Across questions", "Pages that serve the whole experiment, not one question") });
      }
      if (!bands.some((band) => band.experiment === projectKey) && !nodes.some((node) => LIBRARY.has(node.type))) {
        add({ id: project + "#empty", kind: "across", nodes: [],
          lead: pseudo(project + "#empty", "▶", "Start here: write the brief", "No questions yet: Space opens the experiment page, where you write the brief") });
      }
      const library = nodes.filter((node) => LIBRARY.has(node.type));
      if (library.length) {
        add({ id: project + "#library", kind: "library", nodes: library,
          lead: pseudo(project + "#library", "Lib", "Library", counts(library)) });
        if (!unfoldedOnce.has(project + "#library")) folded.add(project + "#library");     // shut until opened once
      }
    }
    bands.forEach((band, index) => { band.index = index; band.lead.band = band; for (const node of band.nodes) node.band = band; });
    for (const band of bands) byKey[band.lead.key] = band.lead;
  }
  function pseudo(key, tag, title, short) {
    return { key, tag, title, short, type: "fold", pseudo: true, edges: [], up: [], href: "" };
  }
  function counts(nodes) {
    const tally = {};
    for (const node of nodes) tally[node.type] = (tally[node.type] || 0) + 1;
    return Object.entries(tally).map(([type, count]) => `${count} ${count === 1 ? KIND[type] : PLURAL[type]}`).join(", ");
  }

  /* ------------------------------------------------------------------ layout */
  function columnOf(node) {
    if (node.pseudo || node.type === "question") return 0;
    if (BESIDE.has(node.type)) return 6;
    const index = COLUMNS.findIndex(([type]) => type === node.type);
    return index < 0 ? 6 : index;
  }
  function layout() {
    pos = {};
    const present = new Set([0]);
    for (const band of bands) for (const node of band.nodes) if (!LIBRARY.has(node.type)) present.add(columnOf(node));
    if (bands.some((band) => band.kind === "library") && present.size < 3) present.add(6);
    usedCols = [...present].sort((a, b) => a - b);
    colX = [];
    let x = LEFT + EXP_W + 16;
    for (const col of usedCols) { colX[col] = x; x += NODE_W + GAP_X; }
    worldW = x - GAP_X + LEFT + 24;
    let y = HEAD + 4;
    let lastExperiment = null;
    for (const band of bands) {
      if (band.experiment !== lastExperiment) {
        if (lastExperiment !== null) { finishExperiment(lastExperiment, y - BAND_GAP); y += 26; }
        lastExperiment = band.experiment;
        byKey[band.experiment].top = y;
      }
      band.top = y;
      band.bottom = placeBand(band, y);
      y = band.bottom + BAND_GAP;
    }
    if (lastExperiment !== null) finishExperiment(lastExperiment, y - BAND_GAP);
    worldH = y + 60;
  }
  function finishExperiment(key, bottom) {
    const node = byKey[key];
    pos[key] = { x: LEFT, y: node.top, w: EXP_W, h: Math.max(NODE_H, bottom - node.top), col: -1, exp: true };
  }
  function placeBand(band, top) {
    const inner = top + PAD;
    const put = (node, x, y, col) => { pos[node.key] = { x, y, w: NODE_W, h: NODE_H, col, band }; };
    put(band.lead, colX[0] + (band.lead.depth ? 12 : 0), inner, 0);
    if (folded.has(band.id)) return inner + NODE_H + PAD;
    let bottom = inner + NODE_H;
    if (band.kind === "library") {
      const cols = usedCols.filter((col) => col > 0);
      const list = [...band.nodes].sort((a, b) => a.ord - b.ord);
      list.forEach((node, index) => {
        const col = cols[index % cols.length], row = Math.floor(index / cols.length);
        const y = inner + row * (NODE_H + GAP_Y);
        put(node, colX[col], y, col);
        bottom = Math.max(bottom, y + NODE_H);
      });
      return bottom + PAD;
    }
    for (const col of usedCols.filter((col) => col > 0)) {
      const here = band.nodes.filter((node) => columnOf(node) === col);
      const anchor = (node) => {
        if (node.type === "conclusion") {
          const ys = supportsOf(node).map(([key]) => pos[key]).filter((place) => place && place.band === band).map((place) => place.y);
          if (ys.length) return Math.min(...ys);
        }
        const parent = node.parent && pos[node.parent];
        return parent && parent.band === band ? parent.y : Infinity;
      };
      here.forEach((node) => { node.anchorY = anchor(node); });
      here.sort((a, b) => (a.anchorY - b.anchorY) || (a.ord - b.ord));
      let cursor = inner;
      for (const node of here) {
        const y = Math.max(cursor, Number.isFinite(node.anchorY) ? node.anchorY : cursor);
        put(node, colX[col], y, col);
        cursor = y + NODE_H + GAP_Y;
        bottom = Math.max(bottom, y + NODE_H);
      }
    }
    return bottom + PAD;
  }

  /* ------------------------------------------------------------------ drawing */
  let sizer, world, heads, edgesSvg, mini, tip;
  const nodeEls = {};
  function render() {
    root.replaceChildren();
    root.tabIndex = -1;
    heads = el("div", { class: "xg-heads", "aria-hidden": "true" });
    sizer = el("div", { class: "xg-size" });
    world = el("div", { class: "xg-world" });
    edgesSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    edgesSvg.setAttribute("class", "xg-edges");
    sizer.append(world);
    root.append(heads, sizer);
    mini = el("div", { class: "xg-mini", title: "The whole graph; the frame is what you see. Click to go there." }, el("canvas"));
    tip = el("div", { class: "xg-tip", "aria-live": "polite" });
    document.body.append(mini, tip);
    mini.addEventListener("click", miniClick);
    root.addEventListener("scroll", () => { requestAnimationFrame(drawMini); syncHeads(); }, { passive: true });
    enablePan();
    redraw();
  }
  function redraw() {
    world.replaceChildren();
    for (const key of Object.keys(nodeEls)) delete nodeEls[key];
    world.style.width = worldW + "px"; world.style.height = worldH + "px";
    sizer.style.width = worldW * scale + "px"; sizer.style.height = worldH * scale + "px";
    world.style.transform = scale === 1 ? "" : `scale(${scale})`;
    heads.style.width = worldW + "px";
    heads.replaceChildren(...usedCols.map((col) => el("span", { style: `left:${colX[col]}px;width:${NODE_W}px` }, COLUMNS[col][1])));
    bands.forEach((band, index) => {
      const lastCol = usedCols[usedCols.length - 1];
      const box = el("div", { class: "xg-band" + (index % 2 ? " alt" : ""), "data-band": band.id,
        style: `left:${colX[0] - 8}px;top:${band.top}px;width:${colX[lastCol] + NODE_W + 8 - (colX[0] - 8)}px;height:${band.bottom - band.top}px` });
      if (folded.has(band.id)) box.append(el("div", { class: "xg-sum", style: `left:${colX[usedCols[1] || 0] - colX[0] + 8}px` }, summary(band)));
      band.box = box;
      world.append(box);
    });
    edgesSvg.setAttribute("width", worldW); edgesSvg.setAttribute("height", worldH);
    world.append(edgesSvg);
    for (const band of bands) {
      if (band.experiment && !nodeEls[band.experiment]) world.append(nodeEl(byKey[band.experiment]));
      world.append(nodeEl(band.lead));
      if (!folded.has(band.id)) for (const node of band.nodes) if (pos[node.key]) world.append(nodeEl(node));
    }
    syncHeads();
    drawEdges();
    if (selected) {
      mark(selected);
      if (!zoom && nodeEls[selected] && (document.activeElement === document.body || !document.activeElement)) nodeEls[selected].focus({ preventScroll: true });
    }
    drawMini();
  }
  function summary(band) {
    if (band.kind !== "question") return [el("b", {}, band.lead.title + ": "), band.lead.short, " · folded, o or Space opens it"];
    const parts = [];
    for (const [type] of COLUMNS.slice(1)) {
      const list = band.nodes.filter((node) => type === "beside" ? BESIDE.has(node.type) : node.type === type);
      if (!list.length) continue;
      const signed = list.filter((node) => node.signed).length;
      parts.push(el("span", {}, el("b", {}, type === "beside" ? "beside" : PLURAL[type]), ` ${signed}/${list.length} signed`));
    }
    parts.push(el("span", {}, "· folded, o opens it"));
    return parts;
  }
  function meta(node) {
    if (node.pseudo) return node.short;
    const parts = [KIND[node.type] || node.type];
    if (node.type === "hypothesis") {
      if (node.fixed === true) parts.push("fixed before results");
      else if (node.fixed === false) parts.push("written after results");
    }
    if (node.analysis === "exploratory" || node.status === "exploratory") parts.push("exploratory");
    else if (node.analysis === "confirmatory") parts.push("confirmatory");
    if (node.status && !["done", "current", "active", "exploratory"].includes(node.status)) parts.push(words(node.status));
    if (node.certainty) parts.push(words(node.certainty) + " certainty");
    return parts.join(" · ");
  }
  function state(node) {
    if (node.pseudo || node.type === "experiment") return "";
    if (signing.has(node.key)) return "approved on the site, written onto the page at the next Harvest";
    if (node.held) return "signed, but a page it rests on changed since: it waits for a new sign-off";
    if (node.signed) return "signed";
    if (node.waiting) return "waits for your sign-off";
    return "not signed";
  }
  function nodeEl(node) {
    const place = pos[node.key];
    const colour = COLOUR[node.type] || "#5d6475";
    const where = node.band && node.band.kind === "question" && node.type !== "question" ? ", under " + node.band.lead.tag : "";
    const aria = `${KIND[node.type] || ""} ${node.tag || ""}: ${node.title}. ${meta(node)}. ${state(node)}${where}`;
    let item;
    if (place.exp) {
      item = el("button", { class: "xg-exp", type: "button", "data-key": node.key, tabindex: "-1", "aria-label": "Experiment " + node.title,
        title: node.title + (node.short ? " · " + node.short : ""),
        style: `left:${place.x}px;top:${place.y}px;width:${place.w}px;height:${place.h}px` }, el("span", {}, node.project || node.title));
    } else {
      let markText = "", markClass = "";
      if (!node.pseudo && node.type !== "experiment") {
        if (signing.has(node.key)) { markText = "✓"; markClass = "ok"; }
        else if (node.held) { markText = "!"; markClass = "held"; }
        else if (node.signed) { markText = "✓"; markClass = "ok"; }
        else if (node.waiting) { markText = "●"; markClass = "wait"; }
      }
      const classes = ["xg-node"];
      if (!node.pseudo && !node.signed && node.type !== "experiment") classes.push("open");
      if (signing.has(node.key)) classes.push("signing");
      if (GONE.has(node.status)) classes.push("gone");
      if (node.depth) classes.push("sub");
      if (node.pseudo) classes.push("fold");
      if (node.pseudo && node.key.endsWith("#empty")) classes.push("start");
      item = el("button", { class: classes.join(" "), type: "button", "data-key": node.key, tabindex: "-1", "aria-label": aria,
        title: (node.short || node.title) + (state(node) ? "\n" + state(node) : ""),
        style: `left:${place.x}px;top:${place.y}px;width:${place.w}px;height:${place.h}px;--c:${colour}` },
        el("span", { class: "tg", style: `background:${colour}` }, tagOf(node)),
        el("span", { class: "bd" }, el("span", { class: "tt" }, node.title), el("span", { class: "mt" }, meta(node))),
        markText ? el("span", { class: "mk " + markClass, "aria-hidden": "true" }, markText) : null);
    }
    item.addEventListener("click", (event) => {
      if (panMoved) { event.preventDefault(); return; }
      select(node.key);
      activate(node.key);
    });
    nodeEls[node.key] = item;
    return item;
  }
  function edgePath(from, to) {
    const a = pos[from], b = pos[to];
    if (!a || !b) return null;
    let left = a, right = b;
    if (b.x + b.w / 2 < a.x + a.w / 2) { left = b; right = a; }
    const y1 = left.y + Math.min(left.h, NODE_H) / 2, y2 = right.y + Math.min(right.h, NODE_H) / 2;
    if (Math.abs(left.x - right.x) < 2) {             // the same column: an arc on the right
      const x = left.x + left.w;
      return `M${x},${y1} C${x + 34},${y1} ${x + 34},${y2} ${x},${y2}`;
    }
    const x1 = left.x + left.w, x2 = right.x;
    const bend = Math.max(24, (x2 - x1) / 2);
    return `M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}`;
  }
  function drawEdges() {
    const paths = [];
    const add = (from, to, cls) => { const d = edgePath(from, to); if (d) paths.push([d, cls]); };
    const shown = (key) => pos[key] && nodeEls[key];
    for (const node of data.nodes) {
      if (!shown(node.key) || node.beside || node.type === "experiment" || node.type === "question") continue;
      if (node.type === "conclusion") {
        const evidence = supportsOf(node).filter(([key]) => shown(key));
        for (const [key, relation] of evidence) add(key, node.key, relation === "opposes" ? "oppose" : "support");
        if (evidence.length) continue;
      }
      if (node.parent && shown(node.parent) && byKey[node.parent].type !== "experiment") add(node.parent, node.key, "");
    }
    let focus = "";
    if (selected && byKey[selected] && !byKey[selected].pseudo && byKey[selected].type !== "experiment") {
      const ups = chain(selected, upOf), downs = chain(selected, downOf);
      const done = new Set();
      const link = (from, to, cls) => { const id = from + ">" + to; if (done.has(id) || !shown(from) || !shown(to)) return; done.add(id); add(from, to, cls); };
      for (const key of [selected, ...ups]) for (const up of upOf(key)) if (up === selected || ups.has(up)) link(up, key, "up");
      for (const key of [selected, ...downs]) for (const down of downOf(key)) if (down === selected || downs.has(down)) link(key, down, "down");
      focus = "focus";
    }
    edgesSvg.setAttribute("class", "xg-edges " + focus);
    edgesSvg.innerHTML = paths.map(([d, cls]) => `<path d="${d}" class="${cls}"/>`).join("");
  }

  /* ------------------------------------------------------------------ selection */
  function mark(key) {
    world.querySelectorAll(".xg-node.sel, .xg-exp.sel, .xg-node.up, .xg-node.down").forEach((item) => item.classList.remove("sel", "up", "down"));
    world.querySelectorAll(".xg-band.here").forEach((item) => item.classList.remove("here"));
    const node = byKey[key];
    const item = nodeEls[key];
    if (item) { item.classList.add("sel"); item.tabIndex = 0; }
    const isPage = node && !node.pseudo && node.type !== "experiment";
    world.classList.toggle("focus", !!isPage);
    if (isPage) {
      for (const up of chain(key, upOf)) if (nodeEls[up]) nodeEls[up].classList.add("up");
      for (const down of chain(key, downOf)) if (nodeEls[down]) nodeEls[down].classList.add("down");
    }
    const band = node && (node.band || (pos[key] && pos[key].band));
    if (band && band.box) band.box.classList.add("here");
    showTip(node);
  }
  function select(key, options = {}) {
    const node = byKey[key];
    if (!node) return;
    if (node.band && folded.has(node.band.id) && node !== node.band.lead) { unfold(node.band); }
    if (selected && nodeEls[selected]) nodeEls[selected].tabIndex = -1;
    selected = key;
    if (!node.pseudo && node.parent) lastChild[node.parent] = key;
    save("kea-xg-selected", key);
    mark(key);
    drawEdges();
    const item = nodeEls[key];
    if (item && !zoom) item.focus({ preventScroll: true });
    reveal(key, options);
    if (!zoom) setHash(key, false);
    drawMini();
  }
  function setHash(key, open) {
    const hash = "#" + key + (open ? "/open" : "");
    if (location.hash !== hash) history.replaceState(null, "", hash);
  }
  function fromHash() {
    let raw = "";
    try { raw = decodeURIComponent(location.hash.slice(1)); } catch (error) { raw = ""; }   // a malformed link
    if (!raw) return [null, false];
    const open = raw.endsWith("/open");
    return [open ? raw.slice(0, -5) : raw, open];
  }
  function reveal(key, options = {}) {
    const place = pos[key];
    if (!place) return;
    const view = { w: root.clientWidth, h: root.clientHeight };
    const left = place.x * scale, top = place.y * scale, width = place.w * scale, height = Math.min(place.h, 220) * scale;
    const margin = { x: Math.min(120, view.w / 6), y: Math.min(70, view.h / 6) };
    let x = root.scrollLeft, y = root.scrollTop;
    if (options.center) { x = left + width / 2 - view.w / 2; y = top + height / 2 - view.h / 2; }
    else {
      if (left - margin.x < x) x = left - margin.x;
      else if (left + width + margin.x > x + view.w) x = left + width + margin.x - view.w;
      if (top - margin.y - 30 < y) y = top - margin.y - 30;
      else if (top + height + margin.y > y + view.h) y = top + height + margin.y - view.h;
      if (place.col === 0 || place.exp) x = Math.min(x, Math.max(0, left - margin.x - EXP_W));
    }
    x = Math.max(0, x); y = Math.max(0, y);
    if (Math.abs(x - root.scrollLeft) < 2 && Math.abs(y - root.scrollTop) < 2) return;
    root.scrollTo({ left: x, top: y, behavior: options.instant || reduced ? "auto" : "smooth" });
  }
  function showTip(node) {
    if (!node) { tip.hidden = true; return; }
    tip.hidden = false;
    const keys = (...list) => list.map((key) => el("span", { class: "k" }, key));
    if (node.type === "experiment" || node.pseudo) {
      tip.replaceChildren(el("b", {}, node.title), node.short ? " · " + node.short : "", el("br"),
        el("span", { class: "why" }, node.pseudo && node.key.endsWith("#empty") ? "Space opens the experiment page"
          : node.pseudo ? "Space or o folds and opens this band" : "Space opens the experiment page"), " ", ...keys("?"));
      return;
    }
    tip.replaceChildren(
      el("b", {}, (node.tag ? node.tag + " · " : "") + node.title), el("br"),
      el("span", { class: "why" }, [relations(node) || "no links to other pages yet", state(node)].join(" · ")), el("br"),
      ...keys("Space"), " open  ", ...keys("←"), " rests on  ", ...keys("→"), " follows  ", ...keys("n"), " next to sign  ", ...keys("?"));
  }

  /* The page's links in words, in the order of the reasoning: what it grows from, then what it bears on
     ("question Q1 · made by S1 · tests H1 · supports C1 · limited by W1"). Labels as on the pages (nodes.py). */
  const FORWARD = { answers: "answers", tests: "tests", supports: "supports", opposes: "opposes", supported_by: "supported by",
    opposed_by: "opposed by", relies_on: "builds on", shown_in: "shown in", made_by: "made by", from_artefact: "from",
    derived_from: "made from", decided_in: "decided in", supersedes: "supersedes", limits: "limits", addressed_by: "addressed by",
    cites: "cites", uses: "uses", part_of: "part of" };
  const REVERSE = { answers: "answered by", tests: "tested by", supports: "supported by", opposes: "opposed by",
    supported_by: "supports", opposed_by: "opposes", relies_on: "used by", shown_in: "shows", made_by: "makes",
    from_artefact: "used in", derived_from: "used to make", decided_in: "applies to", supersedes: "superseded by",
    limits: "limited by", addressed_by: "addresses", cites: "cited by", uses: "used in", part_of: "contains" };
  const ORDER = ["made by", "tests", "builds on", "decided in", "from", "made from", "uses", "shows", "shown in", "supports",
    "opposes", "supported by", "opposed by", "answers", "answered by", "tested by", "makes", "used by", "applies to",
    "limits", "limited by", "addresses", "addressed by", "cites", "cited by", "used in", "used to make", "supersedes",
    "superseded by", "part of", "contains"];
  function relations(node) {
    const groups = {};
    const add = (verb, key) => { if (byKey[key] && key !== node.key) (groups[verb] = groups[verb] || new Set()).add(key); };
    for (const [relation, target] of node.edges) add(FORWARD[relation] || relation, target);
    for (const [relation, from] of incoming[node.key] || []) add(REVERSE[relation] || relation, from);
    const parts = [];
    const lead = node.band && node.band.kind === "question" && node.type !== "question" ? node.band.lead : null;
    if (lead && !Object.values(groups).some((keys) => keys.has(lead.key))) parts.push("question " + (lead.tag || ""));
    const verbs = Object.keys(groups).sort((a, b) => (ORDER.indexOf(a) + 99) % 99 - (ORDER.indexOf(b) + 99) % 99);
    for (const verb of verbs) {
      const tags = [...groups[verb]].map((key) => byKey[key].tag || byKey[key].title.slice(0, 24));
      parts.push(verb + " " + (tags.length > 4 ? tags.slice(0, 4).join(", ") + ` +${tags.length - 4}` : tags.join(", ")));
    }
    return parts.slice(0, 7).join(" · ");
  }

  /* ------------------------------------------------------------------ walking */
  const visible = () => Object.keys(pos).filter((key) => nodeEls[key]);
  function nearest(keys, y) {
    let best = null, bestGap = Infinity;
    for (const key of keys) { const gap = Math.abs(pos[key].y - y); if (gap < bestGap) { best = key; bestGap = gap; } }
    return best;
  }
  function stepLeft() {
    const node = byKey[selected], place = pos[selected];
    if (!node || !place || place.exp) return null;
    if (place.col === 0) return (node.band && node.band.experiment) || null;
    if (node.type === "conclusion") {
      const evidence = supportsOf(node).map(([key]) => key).filter((key) => nodeEls[key] && pos[key].band === place.band);
      if (evidence.length) return evidence.sort((a, b) => pos[a].y - pos[b].y)[0];
    }
    if (node.parent && nodeEls[node.parent] && pos[node.parent].col < place.col && pos[node.parent].band === place.band) return node.parent;
    const candidates = visible().filter((key) => pos[key].band === place.band && pos[key].col >= 0 && pos[key].col < place.col);
    if (!candidates.length) return node.band.lead.key;
    const col = Math.max(...candidates.map((key) => pos[key].col));
    return nearest(candidates.filter((key) => pos[key].col === col), place.y);
  }
  function stepRight() {
    const node = byKey[selected], place = pos[selected];
    if (!node || !place) return null;
    if (place.exp) {
      const band = bands.find((item) => item.experiment === selected);
      return band ? band.lead.key : null;
    }
    if (node.pseudo && folded.has(node.band.id)) return null;
    const follows = visible().filter((key) => {
      const other = byKey[key];
      if (!other || other.pseudo || pos[key].col <= place.col || pos[key].band !== place.band) return false;
      if (other.parent === selected && !other.beside) return true;
      return other.type === "conclusion" && supportsOf(other).some(([from]) => from === selected);
    });
    if (follows.length) {
      const remembered = lastChild[selected];
      return follows.includes(remembered) ? remembered : follows.sort((a, b) => pos[a].col - pos[b].col || pos[a].y - pos[b].y)[0];
    }
    const candidates = visible().filter((key) => pos[key].band === place.band && pos[key].col > place.col);
    if (!candidates.length) return null;
    const col = Math.min(...candidates.map((key) => pos[key].col));
    return nearest(candidates.filter((key) => pos[key].col === col), place.y);
  }
  function stepVertical(direction) {
    const place = pos[selected];
    if (!place) return null;
    if (place.exp) {
      const experiments = [...new Set(bands.map((band) => band.experiment))];
      return experiments[experiments.indexOf(selected) + direction] || null;
    }
    const same = visible().filter((key) => key !== selected && !pos[key].exp && pos[key].col === place.col
      && (direction > 0 ? pos[key].y > place.y : pos[key].y < place.y));
    if (!same.length) return null;
    same.sort((a, b) => direction * (pos[a].y - pos[b].y) || Math.abs(pos[a].x - place.x) - Math.abs(pos[b].x - place.x));
    return same[0];
  }
  function stepBand(direction) {
    const node = byKey[selected];
    const band = node && (node.band || (pos[selected] && pos[selected].band));
    const index = band ? band.index : (direction > 0 ? -1 : bands.length);
    const next = bands[index + direction];
    return next ? next.lead.key : null;
  }
  function nextToSign(direction) {
    const list = signOrder.filter((key) => byKey[key] && !signing.has(key));
    if (!list.length) { flash("Nothing waits for a sign-off."); return null; }
    const index = list.indexOf(selected);
    if (index < 0) {                                  // from here: the first one below (or above) on the screen
      const place = pos[selected];
      const ahead = place ? list.filter((key) => pos[key] && (direction > 0 ? pos[key].y > place.y : pos[key].y < place.y)) : [];
      return direction > 0 ? (ahead[0] || list[0]) : (ahead[ahead.length - 1] || list[list.length - 1]);
    }
    return list[(index + direction + list.length) % list.length];
  }
  function activate(key) {
    const node = byKey[key];
    if (!node) return;
    if (node.pseudo && node.key.endsWith("#empty")) { openZoom(node.band.experiment); return; }   // Start here: the brief
    if (node.pseudo) { toggleFold(node.band); return; }
    openZoom(key);
  }

  /* ------------------------------------------------------------------ folding and fitting */
  function refit() {                                   // in fit mode, after folding or a resize: fit again
    if (!fitted) return;
    scale = Math.max(0.2, Math.min(1, (root.clientWidth - 24) / worldW, (root.clientHeight - 24) / worldH));
  }
  function unfold(band) {
    folded.delete(band.id);
    unfoldedOnce.add(band.id);
    save("kea-xg-folded", [...folded]); save("kea-xg-unfolded", [...unfoldedOnce]);
    layout(); refit(); redraw();
  }
  function toggleFold(band) {
    if (!band) return;
    if (folded.has(band.id)) unfold(band);
    else {
      folded.add(band.id);
      save("kea-xg-folded", [...folded]);
      layout(); refit(); redraw();
      select(band.lead.key, { instant: true });
    }
  }
  function foldOthers() {
    const node = byKey[selected];
    const mine = node && (node.band || (pos[selected] && pos[selected].band));
    const othersOpen = bands.some((band) => band !== mine && !folded.has(band.id));
    for (const band of bands) {
      if (band === mine) continue;
      if (othersOpen) folded.add(band.id); else { folded.delete(band.id); unfoldedOnce.add(band.id); }
    }
    save("kea-xg-folded", [...folded]); save("kea-xg-unfolded", [...unfoldedOnce]);
    layout(); refit(); redraw();
    if (selected) reveal(selected, { instant: true, center: true });
    flash(othersOpen ? "Only this question open: O opens all again." : "Every band open.");
  }
  function toggleFit() {
    if (!fitted) {
      const fit = Math.min(1, (root.clientWidth - 24) / worldW, (root.clientHeight - 24) / worldH);
      if (fit > 0.97) { flash("The whole graph fits already."); return; }
      scale = Math.max(0.2, fit);
    } else scale = 1;
    fitted = !fitted;
    redraw();
    if (selected) reveal(selected, { instant: true, center: true });
    flash(fitted ? "The whole graph: f again for full size; Space opens the selected page." : "Full size.");
  }

  /* ------------------------------------------------------------------ the zoom */
  function zoomRect() {
    const top = topOffset();
    const narrow = window.innerWidth < 700;
    const side = narrow ? 0 : Math.max(16, Math.round(window.innerWidth * 0.06));
    const gap = narrow ? 0 : 14;
    return { left: side, top: top + gap, width: window.innerWidth - 2 * side, height: window.innerHeight - top - 2 * gap };
  }
  function openZoom(key) {
    const node = byKey[key];
    if (!node || node.pseudo || !node.href) return;
    if (zoom) { zoom.load(key); return; }
    reveal(key, { instant: true });
    const item = nodeEls[key];
    const from = item ? item.getBoundingClientRect() : null;
    const target = zoomRect();
    const dim = el("div", { class: "xg-zoom-dim", onclick: () => closeZoom() });
    const header = el("header");
    const waiting = el("div", { class: "wait" });
    const panel = el("div", { class: "xg-zoom", role: "dialog", "aria-modal": "true", "aria-label": label(node),
      style: `left:${target.left}px;top:${target.top}px;width:${target.width}px;height:${target.height}px` }, header, waiting);
    document.body.append(dim, panel);
    let frame = null;
    zoom = { key, panel, dim, header };
    document.body.classList.add("xg-zoomed");
    zoom.load = (pageKey) => {
      const page = byKey[pageKey];
      zoom.key = pageKey;
      fillHeader(page);
      waiting.hidden = false;
      waiting.replaceChildren(el("p", {}, el("b", {}, label(page))), page.short ? el("p", {}, page.short) : "", el("p", {}, "Opening the page …"));
      if (frame) frame.remove();
      frame = el("iframe", { title: label(page), src: page.href });
      frame.addEventListener("load", () => frameLoaded(frame, waiting));
      panel.append(frame);
      zoom.frame = frame;
      setHash(pageKey, true);
    };
    zoom.load(key);
    if (from && !reduced) {
      const sx = from.width / target.width, sy = from.height / target.height;
      panel.style.transform = `translate(${from.left - target.left}px,${from.top - target.top}px) scale(${sx},${sy})`;
      panel.style.opacity = "0.6";
      panel.getBoundingClientRect();
      panel.classList.add("anim");
      panel.style.transform = ""; panel.style.opacity = "";
    }
    requestAnimationFrame(() => dim.classList.add("on"));
    header.querySelector("button.back").focus({ preventScroll: true });
  }
  function fillHeader(page) {
    const colour = COLOUR[page.type] || "#5d6475";
    zoom.header.replaceChildren(
      el("span", { class: "tg", style: `background:${colour}` }, page.tag || KIND[page.type] || ""),
      el("span", { class: "ttl", title: page.title }, page.title),
      el("a", { href: page.href, title: "This page on its own, with the menu bar" }, "Open as page ↗"),
      el("button", { class: "back", type: "button", title: "Esc · back to the graph, at this page", onclick: () => closeZoom() }, "← Graph · Esc"));
  }
  function frameLoaded(frame, waiting) {
    if (!zoom || zoom.frame !== frame) return;
    let path = "", title = "";
    try { path = frame.contentWindow.location.pathname; title = frame.contentDocument.title; } catch (error) { /* another origin */ }
    const key = byPath[path] || byPath[path.replace(/\/$/, "/index.html")];
    if (key) {                                        // Approve & next, or a link to another page: the graph follows
      if (key !== zoom.key) { zoom.key = key; select(key, { instant: true }); setHash(key, true); }
      fillHeader(byKey[key]);
    } else {                                          // a place that is not a page of the graph (Plan, a data file)
      zoom.header.querySelector(".ttl").textContent = title || path.split("/").pop() || "…";
      zoom.header.querySelector(".tg").hidden = true;
      const open = zoom.header.querySelector("a");
      if (open) open.href = path || open.href;
    }
    waiting.hidden = true;
    frame.classList.add("ready");
    let ours = false;                                  // a site page has kea.js and sends its Esc here; anything else
    try { ours = !!frame.contentDocument.querySelector("script[src*='kea.js']"); } catch (error) { ours = false; }
    if (ours) { try { frame.contentWindow.focus(); } catch (error) { /* another origin */ } }
    else zoom.header.querySelector("button.back").focus({ preventScroll: true });
  }
  function closeZoom() {
    if (!zoom) return;
    const { panel, dim, key } = zoom;
    zoom = null;
    document.body.classList.remove("xg-zoomed");
    if (byKey[key] && key !== selected) select(key, { instant: true });
    else if (selected) reveal(selected, { instant: true });
    setHash(selected, false);
    const item = nodeEls[selected];
    dim.classList.remove("on");
    const finish = () => { panel.remove(); dim.remove(); };
    if (item && !reduced) {
      const to = item.getBoundingClientRect(), from = panel.getBoundingClientRect();
      panel.classList.add("anim");
      panel.style.transform = `translate(${to.left - from.left}px,${to.top - from.top}px) scale(${to.width / from.width},${to.height / from.height})`;
      panel.style.opacity = "0";
      setTimeout(finish, 270);
    } else finish();
    if (item) item.focus({ preventScroll: true });
    if (window.keaPollStatus) window.keaPollStatus();
  }
  window.keaExplore = { close: closeZoom, select: (key) => select(key), open: (key) => { select(key); openZoom(key); },
    signStep: (direction) => {                         // n / p inside the zoomed page: the next page to sign, same panel
      const key = nextToSign(direction);
      if (!key) return;
      select(key, { instant: true });
      if (zoom) zoom.load(key); else openZoom(key);
    } };

  /* ------------------------------------------------------------------ live sign-offs (cycle.js status) */
  function live(status) {
    const now = new Set((status && status.signing) || []);
    const changed = [...now].some((key) => !signing.has(key)) || [...signing].some((key) => !now.has(key));
    signing = now;
    if (!changed || !world) return;
    redraw();
  }

  /* ------------------------------------------------------------------ find and help */
  let finder = null, help = null, goPending = 0;
  function openFind() {
    const input = el("input", { type: "search", placeholder: "Find a page: its tag (R3) or words of its title", "aria-label": "Find a page" });
    const list = el("ol");
    finder = el("div", { class: "xg-find", role: "dialog" }, input, list);
    document.body.append(finder);
    finder.addEventListener("focusout", () => setTimeout(() => { if (finder && !finder.contains(document.activeElement)) closeFind(); }, 0));
    let hits = [], at = 0;
    const draw = () => {
      list.replaceChildren(...hits.map((key, index) => {
        const node = byKey[key];
        return el("li", { class: index === at ? "on" : "", onclick: () => { closeFind(); select(key, { center: true }); } },
          el("span", { class: "tg", style: `background:${COLOUR[node.type]}` }, node.tag || LETTER[node.type]), el("span", {}, node.title));
      }));
    };
    input.addEventListener("input", () => {
      const query = input.value.trim().toLowerCase();
      const terms = query.split(/\s+/).filter(Boolean);
      hits = !terms.length ? [] : data.nodes.filter((node) => {
        const text = (node.tag + " " + node.title + " " + node.short).toLowerCase();
        return (node.tag && node.tag.toLowerCase() === query) || terms.every((term) => text.includes(term));
      }).sort((a, b) => (b.tag.toLowerCase() === query) - (a.tag.toLowerCase() === query) || a.ord - b.ord).slice(0, 12).map((node) => node.key);
      at = 0; draw();
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); closeFind(); }
      else if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); if (hits.length) { at = (at + (event.key === "ArrowDown" ? 1 : hits.length - 1)) % hits.length; draw(); } }
      else if (event.key === "Enter" && hits[at]) { event.preventDefault(); const key = hits[at]; closeFind(); select(key, { center: true }); if (event.shiftKey) openZoom(key); }
    });
    input.focus();
  }
  function closeFind() {
    if (!finder) return;
    finder.remove(); finder = null;
    if (selected && nodeEls[selected] && !zoom) nodeEls[selected].focus({ preventScroll: true });
  }
  function toggleHelp() {
    if (help) { help.remove(); help = null; return; }
    const row = (keys, text) => el("tr", {}, el("td", {}, ...keys.map((key) => el("kbd", {}, key))), el("td", {}, text));
    const legend = Object.entries(LETTER).filter(([type]) => type !== "experiment").map(([type, letter]) =>
      el("span", {}, el("span", { style: `display:inline-block;background:${COLOUR[type]};color:#fff;border-radius:4px;padding:0 5px;font-weight:700;margin-right:4px` }, letter), KIND[type]));
    help = el("div", { class: "xg-help", role: "dialog", "aria-label": "Keys of the graph" },
      el("h2", {}, "The graph: keys"),
      el("table", {},
        row(["→", "d"], "What follows from this page: a question's hypotheses, the step that tests a hypothesis, the result a step made, the conclusion a result supports"),
        row(["←", "a"], "What it rests on, back towards the question"),
        row(["↑", "w", "↓", "s"], "The page above or below in the same column (the same stage)"),
        row(["PgUp", "PgDn"], "The previous or next question"),
        row(["Space", "Enter"], "Open the page (zoom in): read, comment, sign. A click does the same"),
        row(["Esc"], "Back to the graph, at the same place"),
        row(["n", "p"], "The next or previous page that waits for a sign-off, top down"),
        row(["/"], "Find a page by its tag or title (Shift+Enter opens it)"),
        row(["o"], "Fold or open this question's band; O: only this question open (again: all open)"),
        row(["f"], "The whole graph on the screen, and back"),
        row(["g"], "Go to … the site's other places (g g comes back here)"),
        row(["?"], "This list")),
      el("p", {}, "Box: the tag in the type's colour, filled when signed, outlined when not. ",
        el("b", { style: "color:#2e9e5b" }, "✓"), " signed · ", el("b", { style: "color:#c26b00" }, "●"), " waits for your sign-off · ",
        el("b", { style: "color:#8a6d00" }, "!"), " rests on a page that changed since it was signed. With a page selected, ",
        el("b", { style: "color:#1f5f99" }, "blue"), " is what it rests on, ", el("b", { style: "color:#c26b00" }, "orange"),
        " what rests on it. Green lines: evidence for a conclusion; red dashed: evidence against."),
      el("div", { class: "xg-legend" }, legend),
      el("p", { style: "color:#5d6475;margin-bottom:0" }, "Esc or ? closes this list."));
    document.body.append(help);
  }

  /* ------------------------------------------------------------------ keys */
  window.addEventListener("keydown", (event) => {
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    if (finder && finder.contains(event.target)) return;   // the find box handles its own keys
    const typing = event.target instanceof Element && event.target.closest("input, textarea, select, [contenteditable=''], [contenteditable='true']");
    if (typing) return;
    if (document.getElementById("kea-keys")) return;   // kea.js has a menu open (g …): its keys
    if (event.key === "g") { goPending = Date.now(); return; }      // kea.js: g, then a place
    if (Date.now() - goPending < 1500) { goPending = 0; return; }   // the key after g belongs to kea.js's menu
    const stop = () => { event.preventDefault(); event.stopImmediatePropagation(); };
    if (zoom) {                                         // the page has the keys while it is open; here only Esc
      if (event.key === "Escape") { stop(); closeZoom(); }
      else if (zoom.panel.contains(event.target) && ["Enter", " ", "Tab", "Shift"].includes(event.key)) return;   // its buttons and links
      else if (!["Tab", "Shift"].includes(event.key)) stop();
      return;
    }
    if (finder) closeFind();
    // the graph's keys only when the graph (or nothing in particular) has the focus, not a link in the menu bar
    const onGraph = event.target === document.body || event.target === document.documentElement || root.contains(event.target);
    if (!onGraph && !help) return;
    if (help) { if (event.key === "Escape" || event.key === "?") { stop(); toggleHelp(); } return; }
    if (!data || !selected) return;
    let target = null, handled = true;
    switch (event.key) {
      case "ArrowRight": case "d": target = stepRight(); break;
      case "ArrowLeft": case "a": target = stepLeft(); break;
      case "ArrowDown": case "s": target = stepVertical(1); break;
      case "ArrowUp": case "w": target = stepVertical(-1); break;
      case "PageDown": target = stepBand(1); break;
      case "PageUp": target = stepBand(-1); break;
      case "Home": target = (byKey[selected].band && byKey[selected].band.experiment) || null; break;
      case " ": case "Enter": activate(selected); break;
      case "n": case "N": target = nextToSign(1); break;
      case "p": case "P": target = nextToSign(-1); break;
      case "o": toggleFold(byKey[selected].band || (pos[selected] && pos[selected].band)); break;
      case "O": foldOthers(); break;
      case "f": toggleFit(); break;
      case "/": openFind(); break;
      case "?": toggleHelp(); break;
      case "c": flash("Open a page first (Space), then c comments on it."); break;
      case "Escape": if (fitted) toggleFit(); break;
      default: handled = false;
    }
    if (!handled) return;
    stop();
    if (target) select(target);
    else if (["ArrowRight", "d", "ArrowLeft", "a", "ArrowDown", "s", "ArrowUp", "w", "PageDown", "PageUp"].includes(event.key)) bump();
  }, true);
  function bump() {                                    // nothing that way: a small shake of the selected box
    const item = nodeEls[selected];
    if (!item || reduced || !item.animate) return;
    item.animate([{ transform: "translateX(0)" }, { transform: "translateX(-3px)" }, { transform: "translateX(3px)" }, { transform: "translateX(0)" }], { duration: 160 });
  }
  let flashTimer = null;
  function flash(text) {
    let box = document.getElementById("xg-flash");
    if (!box) { box = el("div", { id: "xg-flash", class: "xg-tip", role: "status", style: "left:50%;transform:translateX(-50%);bottom:auto;top:calc(var(--xg-top,44px) + 40px);z-index:25" }); document.body.append(box); }
    box.textContent = text; box.hidden = false;
    clearTimeout(flashTimer);
    flashTimer = setTimeout(() => { box.hidden = true; }, 2600);
  }

  /* ------------------------------------------------------------------ panning, the overview, the menu bar */
  let panMoved = false;
  function enablePan() {
    let start = null;
    root.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || event.pointerType === "touch") return;
      start = { x: event.clientX, y: event.clientY, left: root.scrollLeft, top: root.scrollTop };
      panMoved = false;
    });
    window.addEventListener("pointermove", (event) => {
      if (!start) return;
      const dx = event.clientX - start.x, dy = event.clientY - start.y;
      if (!panMoved && Math.hypot(dx, dy) < 5) return;
      panMoved = true;
      root.classList.add("panning");
      root.scrollLeft = start.left - dx; root.scrollTop = start.top - dy;
    });
    window.addEventListener("pointerup", () => {
      start = null; root.classList.remove("panning");
      setTimeout(() => { panMoved = false; }, 0);
    });
  }
  let miniScale = 1;
  function drawMini() {
    if (!mini || !worldW) return;
    const canvas = mini.querySelector("canvas");
    const width = 190;
    miniScale = width / worldW;
    const height = Math.min(220, Math.max(40, worldH * miniScale));
    miniScale = Math.min(miniScale, height / worldH);
    const ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio; canvas.height = height * ratio;
    canvas.style.width = width + "px"; canvas.style.height = height + "px";
    const context = canvas.getContext("2d");
    context.scale(ratio, ratio);
    context.clearRect(0, 0, width, height);
    for (const band of bands) {
      context.fillStyle = band.box && band.box.classList.contains("here") ? "#dbe7f5" : "#eef0f3";
      context.fillRect(0, band.top * miniScale, width, Math.max(1, (band.bottom - band.top) * miniScale));
    }
    for (const [key, place] of Object.entries(pos)) {
      if (!nodeEls[key]) continue;
      const node = byKey[key];
      context.fillStyle = key === selected ? "#1e2230" : COLOUR[node.type] || "#888";
      context.fillRect(place.x * miniScale, place.y * miniScale, Math.max(2, place.w * miniScale), Math.max(2, Math.min(place.h, NODE_H) * miniScale));
    }
    context.strokeStyle = "#1e2230"; context.lineWidth = 1.5;
    context.strokeRect(root.scrollLeft / scale * miniScale, root.scrollTop / scale * miniScale,
      root.clientWidth / scale * miniScale, root.clientHeight / scale * miniScale);
  }
  function miniClick(event) {
    const box = mini.querySelector("canvas").getBoundingClientRect();
    const x = (event.clientX - box.left) / miniScale, y = (event.clientY - box.top) / miniScale;
    let best = null, bestGap = Infinity;
    for (const [key, place] of Object.entries(pos)) {
      if (!nodeEls[key]) continue;
      const gap = Math.hypot(place.x + place.w / 2 - x, place.y + NODE_H / 2 - y);
      if (gap < bestGap) { best = key; bestGap = gap; }
    }
    if (best) select(best, { center: true });
  }
  function syncHeads() { if (heads) heads.style.transform = scale === 1 ? "" : `scale(${scale})`; heads.style.transformOrigin = "0 0"; }
  function topOffset() {
    const bar = document.querySelector(".topbar");
    let bottom = bar ? bar.getBoundingClientRect().bottom : 0;
    for (const banner of document.querySelectorAll(".fb-banner, .cycle-banner")) {
      const box = banner.getBoundingClientRect();
      if (box.height && box.top <= bottom + 1) bottom = Math.max(bottom, box.bottom);
    }
    return Math.max(0, Math.round(bottom));
  }
  function placeBelowBar() { document.documentElement.style.setProperty("--xg-top", topOffset() + "px"); }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
