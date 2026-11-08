"""Render the site: every HTML page from the validated tree (docsite.nodes), git history (docsite.changes),
comments (feedback.store) and plans (doc/_cycles/). Rendering only: no loading, validation, serving or comment
injection (those are docsite.nodes, docsite.build and docsite.comments).

Kept separate (cycle 2, item 4) so the look of the site can be changed or replaced without touching the model or
the review machinery. HTML building blocks (page shell, CSS, links, Markdown) are in docsite.render.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from kea.config import SETTINGS
from kea.docsite import artefacts, changes, codepages, comments, history, mode, questions, versions
from kea.docsite.nodes import PROJECT_ROOT, TYPE_LABELS, TYPE_PLURALS, Node, Tree
from kea.docsite.nodes import natural  # noqa: E402
from kea.docsite.render import (ABOUT_ORDER, TYPE_COLOURS, LinkContext, linked_kinds, crumbs, esc, full_kind, fullname_inner, fullname_link, node_link, page,
                            prefix_for, render_markdown, status_pill, status_row_class, tagline, type_badge)
from kea.docsite import icons

CHILD_ORDER = ["experiment", "premise", "question", "hypothesis", "decision", "step", "result", "conclusion", "figure",
               "artefact", "resource", "caveat", "term", "reference", "dataset", "page"]
RESOURCE_LABELS = (("kind", "Kind"), ("rrid", "RRID"), ("url", "Where"), ("dataset_id", "Dataset id"), ("accession", "Accession"),
                   ("version", "Version"),
                   ("deposit", "Deposit"), ("retrieved", "Retrieved"), ("sha256", "SHA-256"), ("size", "Size"),
                   ("local", "Local copy"), ("access", "Access"), ("licence", "Licence"))


def resource_panel(node: Node) -> str:
    """The facts that make a resource reproducible, as a small table (missing ones marked)."""
    from kea.docsite.nodes import RESOURCE_FIELDS
    rows = []
    for key, label in RESOURCE_LABELS:
        value = node.header.get(key)
        if value is None or value == "":
            if key in RESOURCE_FIELDS or (key == "sha256" and node.header.get("kind") in ("file", "dataset")):
                rows.append(f"<tr><th>{label}</th><td class='missing'>not recorded</td></tr>")
            continue
        shown = esc(value)
        if key == "url" and str(value).startswith(("http://", "https://")):
            shown = f"<a href='{esc(value)}'>{esc(value)}</a>"
        elif key in ("sha256", "local"):
            shown = f"<code>{esc(value)}</code>"
        elif key == "rrid":
            shown = ("none registered" if str(value).lower() == "none" else
                     f"<a href='https://scicrunch.org/resolver/{esc(value)}'>{esc(value)}</a>")
        rows.append(f"<tr><th>{label}</th><td>{shown}</td></tr>")
    return f"<table class='resource-facts not-annotatable'>{''.join(rows)}</table>"


CAPTION_PARTS = ("*Shows:*", "*Method:*", "*Statistics:*")      # caption standard, doc/site_design.md
REVIEW_STATUSES = ("open", "planned")                           # threads that put an experiment "under review"
ASSETS = Path(__file__).resolve().parent / "static"
RELATIONS_JS = """
(function () {
  const container = document.getElementById("graph");
  const tip = document.getElementById("graph-tip");
  const cy = cytoscape({
    container, elements: GRAPH, layout: { name: "preset" }, wheelSensitivity: 0.25, minZoom: 0.15, maxZoom: 2.5,
    style: [
      { selector: "node", style: { "shape": "round-rectangle", "background-color": "data(colour)", "label": "data(label)",
          "color": "#fff", "font-size": 10, "text-wrap": "wrap", "text-max-width": 170, "text-valign": "center",
          "width": 190, "height": 46, "padding": 4 } },
      { selector: "edge", style: { "width": 1.6, "line-color": "data(colour)", "target-arrow-color": "data(colour)",
          "target-arrow-shape": "triangle", "curve-style": "bezier", "label": "data(label)", "font-size": 8,
          "color": "#555", "text-background-color": "#fff", "text-background-opacity": 0.85,
          "text-background-padding": 1, "text-rotation": "autorotate" } },
      { selector: "node[stability = 'flux']", style: { "border-width": 4, "border-color": "#f0a020" } },
      { selector: "node[stability = 'settled']", style: { "border-width": 4, "border-color": "#2e9e5b" } },
      { selector: "edge[relation = 'parent']", style: { "line-style": "dashed", "width": 1, "target-arrow-shape": "none" } },
      { selector: ".faded", style: { "opacity": 0.15 } },
      { selector: ".off", style: { "display": "none" } }
    ]
  });
  function refresh() {
    const types = new Set(Array.from(document.querySelectorAll("input[data-type]")).filter(box => box.checked).map(box => box.dataset.type));
    const relations = new Set(Array.from(document.querySelectorAll("input[data-relation]")).filter(box => box.checked).map(box => box.dataset.relation));
    cy.batch(() => {
      cy.nodes().forEach(node => node.toggleClass("off", !types.has(node.data("type"))));
      cy.edges().forEach(edge => edge.toggleClass("off", !relations.has(edge.data("relation"))
        || edge.source().hasClass("off") || edge.target().hasClass("off")));
    });
  }
  document.querySelectorAll("input[data-type], input[data-relation]").forEach(box => box.addEventListener("change", refresh));
  document.getElementById("graph-fit").addEventListener("click", () => cy.fit(cy.elements(":visible"), 30));
  cy.on("tap", "node", event => { window.location.href = event.target.data("url"); });
  cy.on("mouseover", "node", event => {
    const node = event.target;
    const near = node.closedNeighborhood();
    cy.elements().not(near).addClass("faded");
    tip.textContent = "";
    const title = document.createElement("b"); title.textContent = node.data("title");
    const text = document.createElement("div"); text.textContent = node.data("short");
    const settled = document.createElement("div"); settled.style.opacity = 0.75; settled.textContent = node.data("stability_text");
    tip.append(title, text, settled); tip.hidden = false;
  });
  cy.on("mousemove", event => {
    if (!tip.hidden && event.originalEvent) { tip.style.left = (event.originalEvent.clientX + 14) + "px"; tip.style.top = (event.originalEvent.clientY + 14) + "px"; }
  });
  cy.on("mouseout", "node", () => { cy.elements().removeClass("faded"); tip.hidden = true; });
  refresh();
  cy.fit(cy.elements(":visible"), 30);
})();
"""


class SiteRenderer:
    """Turns the validated tree (plus git, comments and plans) into HTML pages; knows nothing about serving."""

    def __init__(self, tree: Tree, site: Path):
        self.tree, self.site = tree, site
        self.under_review: dict[str, int] = {}
        self.pdf: dict | None = None             # the PDF of all pages (docsite.pdf.site_pdf), if built
        self.data_files: set[str] = set()
        self.code = codepages.CodeIndex()
        self.pages: dict[str, tuple[str, Path | None]] = {}     # page path -> (thread key, source)
        self.downloads: set[str] = set()
        self.code_used_on: dict[str, list[tuple[str, str]]] = {}
        self.broken: list[str] = []
        self.artefact_by_path = {str(node.header.get("path")).rstrip("/"): node
                                 for node in tree.nodes.values() if node.type == "artefact"}

    # ------------------------------------------------------------------ helpers
    def write(self, relative: str, html_text: str, key: str | None = None, source: Path | None = None) -> None:
        target = self.site / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html_text, encoding="utf-8")
        self.pages[relative] = (key or relative, source)

    def code_href(self, target: str, prefix: str) -> str | None:
        return self.code.href(target, prefix)

    def data_href(self, target: str, prefix: str) -> tuple[str | None, str]:
        node = self.artefact_by_path.get(target.rstrip("/"))
        return (f"{prefix}{node.url}", f"{node.number} {target}") if node else (None, target)

    def context(self, project: str, prefix: str, current: str | None = None) -> LinkContext:
        return LinkContext(self.tree, project, prefix, self.code_href, self.data_href, current)

    def review_counts(self) -> dict[str, int]:
        """Experiment -> number of its threads that are open or planned (shown as "under review")."""
        from kea.feedback import store
        counts = {project: 0 for project in self.tree.projects}
        for thread in store.threads():
            experiment = comments.experiment_of(thread.page, self.tree.projects)
            if experiment and thread.status in REVIEW_STATUSES:
                counts[experiment] += 1
        return counts

    def review_pill(self, project: str, prefix: str) -> str:
        waiting = self.under_review.get(project, 0)
        if not waiting:
            return ""
        return (f" <a class='pill s-under_review' href='{prefix}feedback.html' title='{waiting} comment(s) open or "
                f"planned; the status written in the pages is shown next to it'>under review ({waiting})</a>")

    def trail(self, node: Node, prefix: str) -> list[tuple[str, str | None]]:
        chain = []
        current = node
        while current.parent:
            parent = self.tree.nodes.get(f"{node.project}:{current.parent}")
            if parent is None or parent.key in [item.key for item in chain]:
                break
            chain.append(parent)
            current = parent
        trail = [(f"{(item.number + ' ') if item.number else ''}{item.title if item.id != 'home' else item.project}",
                  f"{prefix}{item.url}") for item in reversed(chain)]
        if node.id == "home":
            return [(node.project, None)]
        return trail + [(f"{node.number} {node.title}" if node.number else node.title, None)]

    # ------------------------------------------------------------------ node pages
    def figure_html(self, node: Node, prefix: str, context: LinkContext, full: bool) -> str:
        image = node.header.get("image")
        if not image or not (PROJECT_ROOT / image).exists():
            return f"<p class='ref-broken'>figure image missing: {esc(image)}</p>"
        copy = self.site / "figures" / Path(image).name
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / image, copy)
        caption_file = node.header.get("caption_file")
        caption = ""
        if caption_file and (PROJECT_ROOT / caption_file).exists():
            caption_text = (PROJECT_ROOT / caption_file).read_text()
            caption_text = "\n".join(line for line in caption_text.splitlines()
                                     if not line.startswith(("# ", "- source table:", "- script:", "- commit:")))
            caption = render_markdown(caption_text.strip(), context)
            missing = [part for part in CAPTION_PARTS if part not in caption_text]
            if missing:
                self.tree.notes.append(f"{node.key}: caption lacks {', '.join(missing)} (caption standard)")
        if not full:
            return (f"<div class='thumb'><a href='{prefix}{node.url}'><img src='{prefix}figures/{esc(copy.name)}' "
                    f"alt='{esc(node.title)}'></a><div><b>{tagline(node, prefix)}</b>"
                    f"<figcaption>{caption or esc(node.short)}</figcaption></div></div>")
        made = []
        if node.header.get("script"):
            href = self.code_href(node.header["script"], prefix)
            made.append(f"<b>Script:</b> <a href='{esc(href)}'><code>{esc(node.header['script'])}</code></a>"
                        if href else f"<b>Script:</b> <code>{esc(node.header['script'])}</code>")
        if node.header.get("table"):
            href, label = self.data_href(node.header["table"], prefix)
            link, entry = artefacts.download_html(str(node.header["table"]), prefix)
            if entry:
                self.downloads.add(entry)
            made.append((f"<b>Table:</b> <a href='{esc(href)}'><code>{esc(label)}</code></a>" if href else
                         f"<b>Table:</b> <code>{esc(node.header['table'])}</code>") + link)
        made.append(f"<b>Image:</b> <code>{esc(image)}</code> "
                    f"(<a href='{prefix}figures/{esc(copy.name)}'>full size</a>)")
        return (f"<figure><img src='{prefix}figures/{esc(copy.name)}' alt='{esc(node.title)}'>"
                f"<figcaption>{caption}</figcaption></figure>"
                f"<div class='box not-annotatable'>{' · '.join(made)}</div>")

    def sources_html(self, node: Node, prefix: str) -> str:
        items = []
        for entry in node.header.get("sources") or []:
            for kind, value in (entry.items() if isinstance(entry, dict) else [("data", entry)]):
                value = str(value).split("#")[0] if kind == "data" else str(value)
                if kind == "code":
                    href = self.code_href(value, prefix)
                    self.code_used_on.setdefault(value.split("#")[0], []).append(
                        (f"{node.number or node.title}", node.url))
                    items.append(f"<li>code: <a href='{esc(href)}'><code>{esc(value.replace('#', ' → '))}</code></a></li>"
                                 if href else f"<li>code: <span class='ref-broken'>{esc(value)}</span></li>")
                    if href is None:
                        self.broken.append(f"{node.key}: code source {value}")
                else:
                    href, label = self.data_href(value.strip(), prefix)
                    exists = (PROJECT_ROOT / value.strip()).exists()
                    text = f"<code>{esc(label)}</code>" + ("" if exists else " <span class='ref-broken'>missing</span>")
                    link, entry = artefacts.download_html(value.strip(), prefix)
                    if entry:
                        self.downloads.add(entry)
                    self.data_files.add(value.strip())
                    items.append((f"<li>data: <a href='{esc(href)}'>{text}</a>" if href else f"<li>data: {text}")
                                 + link + "</li>")
        return (f"<ul class='sources'>{''.join(items)}</ul>" if items else "")

    def about_html(self, node: Node, prefix: str, context: LinkContext) -> str:
        from kea.docsite.nodes import FORWARD_LABELS
        sections: list[str] = []
        shown: set[str] = {node.key}
        section = lambda title, html: sections.append(f"<section class='about not-annotatable'><h2>{esc(title)}</h2>{html}</section>")
        own = TYPE_LABELS.get(node.type, node.type).lower()
        kinds = linked_kinds
        if node.id == "home" and node.type == "experiment":
            questions_block = self.questions_html(node.project, prefix, context)
            if questions_block:
                sections.append(questions_block)
                shown.update(question.key for question in questions.questions(self.tree, node.project))
        if node.type == "question":
            hypotheses, results, conclusions = questions.evidence(self.tree, node)
            if conclusions:
                section(f"Answered by {kinds(conclusions)}", self.node_table(conclusions, prefix))
            if results:
                section(f"{'Result' if len(results) == 1 else 'Results'} for this question", self.node_table(results, prefix))
            if hypotheses:
                section(f"{'Hypothesis' if len(hypotheses) == 1 else 'Hypotheses'} for this question", self.hypothesis_table(hypotheses, prefix, heading=False))
            shown.update(member.key for member in hypotheses + results + conclusions)
        links: dict[str, list[str]] = {}
        for relation, keys in node.relations.items():
            links.setdefault(FORWARD_LABELS.get(relation, relation), []).extend(keys)
        for label, keys in node.incoming.items():
            links.setdefault(label, []).extend(keys)
        for label in sorted(links, key=lambda name: ABOUT_ORDER.index(name) if name in ABOUT_ORDER else 99):
            members = [key for key in dict.fromkeys(links[label]) if key not in shown]
            if not members:
                continue
            targets = [self.tree.nodes.get(key) for key in members]
            figures = [target for target in targets if target is not None and target.type == "figure"
                       and label in ("Shown in", "Shows")]
            missing = [key for key, target in zip(members, targets) if target is None]
            rest = [target for target in targets if target is not None and target not in figures]
            named = [target for target in targets if target is not None]
            section(f"{label} {kinds(named)}" if named else label,
                    "".join(self.figure_html(figure, prefix, context, False) for figure in figures)
                    + self.node_table(rest, prefix, missing))
            shown.update(members)
        groups: dict[str, list[Node]] = {}
        for child in self.tree.children(node):
            if child.key not in shown:
                groups.setdefault(child.type, []).append(child)
        for node_type in sorted(groups, key=lambda kind: CHILD_ORDER.index(kind) if kind in CHILD_ORDER else 99):
            members = groups[node_type]
            html = ("".join(self.figure_html(child, prefix, context, False) for child in members) if node_type == "figure"
                    else self.node_table(members, prefix))
            section(f"{TYPE_PLURALS.get(node_type, node_type)} under this {own}", html)
        sources = self.sources_html(node, prefix)
        if sources:
            section("Sources", sources)
        if node.id == "home":
            sections.append(self.project_index_html(node.project, prefix))
        return "".join(sections)

    def answer_list(self, label: str, members: list[Node], prefix: str, project: str) -> str:
        if not members:
            return ""
        return ((f"<h3>{esc(label)}</h3>" if label else "") + "<ul class='answer-list'>"
                + "".join(f"<li>{tagline(member, prefix, member.short if member.type == 'conclusion' else member.title, project, full=True)} "
                          f"{status_pill(member)}</li>" for member in members) + "</ul>")

    def node_table(self, members: list[Node], prefix: str, missing: list[str] | None = None, extra=None) -> str:
        """The standard table of pages under "About this page" and in the index: page, its summary, its status.
        Full text width with fixed column widths, so the status pills of every table line up."""
        if not members and not missing:
            return ""
        rows = [f"<tr class='{status_row_class(member)}'><td>{tagline(member, prefix)}</td><td>{esc(member.short)}</td>"
                f"<td>{status_pill(member)}{extra(member) if extra else ''}</td></tr>" for member in members]
        rows += [f"<tr><td><span class='ref-missing' title='project has no pages yet'>{esc(key)}</span></td><td></td>"
                 f"<td></td></tr>" for key in missing or []]
        return ("<table class='nodes'><colgroup><col class='c-page'><col><col class='c-status'></colgroup>"
                "<tr><th>Page</th><th>In short</th><th>Status</th></tr>" + "".join(rows) + "</table>")

    def hypothesis_table(self, hypotheses: list[Node], prefix: str, heading: bool = True) -> str:
        """Hypotheses of a question with when they were written and their outcome; rows tinted by outcome."""
        if not hypotheses:
            return ""
        rows = []
        for item in hypotheses:
            written = ("before its test" if item.header.get("fixed_before_results") is True else
                       "after results" if item.header.get("fixed_before_results") is False else "")
            tested = ", ".join(node_link(self.tree.nodes[key], prefix) for key in item.incoming.get("Tested by", [])
                               if key in self.tree.nodes)
            rows.append(f"<tr class='{status_row_class(item)}'><td>{tagline(item, prefix)}</td>"
                        f"<td>{esc(item.short)}<div class='cell-note'>written {esc(written) or '?'}"
                        f"{(' · tested by ' + tested) if tested else ''}</div></td>"
                        f"<td>{status_pill(item)}</td></tr>")
        # the same columns as node_table (page, in short, status), with when it was written and its test as a note
        return (("<h3>Hypotheses</h3>" if heading else "") + "<table class='nodes'><colgroup><col class='c-page'><col>"
                "<col class='c-status'></colgroup><tr><th>Hypothesis</th><th>Expected (in short)</th><th>Outcome</th></tr>"
                + "".join(rows) + "</table>")

    def questions_html(self, project: str, prefix: str, context: LinkContext) -> str:
        """On an experiment page: each question as a heading with its executive summary and conclusions."""
        blocks, seen = [], set()
        for question in questions.questions(self.tree, project):
            _, _, found = questions.evidence(self.tree, question)
            conclusions = [member for member in found if member.key not in seen]   # in full once, then by tag
            earlier = [member for member in found if member.key in seen]
            seen.update(member.key for member in found)
            summary = questions.answer(question)
            blocks.append(f"<div class='qblock'><h3 class='qhead'>{fullname_link(question, prefix)} "
                          f"<a href='{prefix}{question.url}'>{esc(question.title)}</a>"
                          f"<span class='pills'>{status_pill(question)}</span></h3>"
                          + (f"<div class='answer'>{render_markdown(summary, context)}</div>" if summary else "")
                          + (("<ul class='answer-list'>" + "".join(
                              f"<li>{tagline(member, prefix, member.short, project, full=True)} {status_pill(member)}</li>"
                              for member in conclusions) + "</ul>") if conclusions else "")
                          + (f"<p class='help'>Also: {' '.join(node_link(member, prefix) for member in earlier)}</p>"
                             if earlier else "") + "</div>")
        return (f"<section class='questions not-annotatable'><h2>Questions</h2>{''.join(blocks)}</section>" if blocks else "")

    def project_index_html(self, project: str, prefix: str) -> str:
        groups: dict[str, list[Node]] = {}
        for node in self.tree.nodes.values():
            if node.project == project and node.id != "home":
                groups.setdefault(node.type, []).append(node)
        parts = []
        for node_type in sorted(groups, key=lambda kind: CHILD_ORDER.index(kind) if kind in CHILD_ORDER else 99):
            members = sorted(groups[node_type], key=lambda item: (natural(item.number), natural(item.title)))
            parts.append(f"<h3>{TYPE_PLURALS.get(node_type, node_type)} ({len(members)})</h3>{self.node_table(members, prefix)}")
        if not parts:
            return (f"<section class='not-annotatable'><h2>All pages of this experiment</h2><p class='help'>No pages "
                    f"yet besides this one: add questions, premises, hypotheses and steps under "
                    f"<code>doc/{esc(project)}/</code> (types in <code>doc/_schema.yaml</code>).</p></section>")
        return (f"<section class='not-annotatable'><h2>All pages of this experiment</h2>"
                f"<p class='help'>Also as a tree: <a href='{prefix}{project}/map.html'>map</a>; as a graph of "
                f"relations: <a href='{prefix}{project}/relations.html'>relations</a>.</p>{''.join(parts)}</section>")

    def node_page(self, node: Node) -> None:
        prefix = prefix_for(node.url)
        context = self.context(node.project, prefix, node.key)
        pills = (status_pill(node)
                 + (self.review_pill(node.project, prefix) if node.id == "home" else "")
                 + self.stability_pill(node)
                 + (f" <span class='pill'>experiment {esc(self.experiment_version(node.project))}</span>"
                    if node.id == "home" and self.experiment_version(node.project) else "")
                 + (f" <span class='pill' title='The claim, test and expectation were fixed before this test was run (possibly after other results had been seen)'>written before its test{self.version_note(node)}</span>"
                    if node.header.get("fixed_before_results") is True
                    else " <span class='pill s-exploratory'>written after results</span>"
                    if node.header.get("fixed_before_results") is False else ""))
        confirmed = node.header.get("confirmed")
        if confirmed:            # written by the agent after a reader pressed Confirm (feedback/tags.py)
            by = confirmed.get("by", "") if isinstance(confirmed, dict) else str(confirmed)
            when = str(confirmed.get("date", "")) if isinstance(confirmed, dict) else ""
            pills += (f" <span class='pill fb-pp-ok' title='Confirmed by {esc(by)}{(' on ' + esc(when)) if when else ''}"
                      f"{(', version ' + esc(str(confirmed.get('version', '')))) if isinstance(confirmed, dict) and confirmed.get('version') else ''}'>"
                      f"✓ confirmed{(' by ' + esc(by)) if by else ''}</span>")
        kind_html = (f"{icons.svg(node.type)}Experiment" if node.type == "experiment" else fullname_inner(node))
        # the page's own content (title, summary, text, its figure) in a frame in the type's colour; what Kea knows
        # about the page (sources, pages below, connections, versions, comments) follows under "Metadata"
        parts = [crumbs(self.trail(node, prefix), prefix),
                 f"<div class='node-content' style='--kc:{TYPE_COLOURS.get(node.type, '#556')}'"
                 f"{' data-confirmed=1' if confirmed else ''}>",
                 f"<div class='kindrow not-annotatable'><span class='kind k-{esc(node.type)}'>{kind_html}</span>"
                 f"<span class='pills'>{pills}</span></div>"
                 f"<h1><span class='node-title'>{esc(node.title)}</span></h1>"
                 f"<div class='short'>{esc(node.short)}</div>"]
        if node.type == "figure":
            parts.append(self.figure_html(node, prefix, context, True))
        if node.type == "artefact":
            panel, download = artefacts.artefact_panel(str(node.header["path"]), prefix, node.header.get("access"),
                                                       self.downloads)
            if download:
                self.downloads.add(download)
            parts.append(panel)
        if node.type == "resource":
            parts.append(resource_panel(node))
        body_text = node.body
        if node.type == "figure":   # an Obsidian-style embed of the figure's own image: already shown above
            embeds = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", body_text)
            stale = [embed for embed in embeds if Path(embed).name != Path(str(node.header.get("image", ""))).name]
            if stale:
                self.tree.notes.append(f"{node.key}: image embed {stale[0]} differs from image: (update the embed)")
            body_text = "\n".join(line for line in body_text.split("\n")
                                   if not (line.strip().startswith("![") and Path(str(node.header.get("image", ""))).name
                                           in line))
        if node.type == "question" and questions.answer(node):
            # the question's own answer: field is its text, so it stays with the content; the evidence moves below
            parts.append(f"<div class='answer'><b class='answer-label not-annotatable'>Answer so far</b>"
                         f"{render_markdown(questions.answer(node), context)}</div>")
        elif node.type == "question" and questions.evidence(self.tree, node)[2]:
            self.tree.notes.append(f"{node.key}: no answer: summary (two or three sentences: the answer, how "
                                   "sure, the main limit; shown on the question and experiment pages and in the PDF)")
        parts.append(f"<article>{render_markdown(body_text, context)}</article>")
        colour = TYPE_COLOURS.get(node.type, '#556')
        parts.append(f"</div><div class='node-data-sep not-annotatable' style='--kc:{colour}'><span>About this page</span></div>")
        uid = str(node.header.get("uid") or "")
        if uid:
            from kea.docsite import identity
            version = identity.version_of(node)
            parts.append(f"<p class='pid not-annotatable'>Permanent identifier <a href='{prefix}id/{esc(uid)}' "
                         f"title='The page, as it is now: stays the same when it is edited, renamed or moved'>"
                         f"<code>kea:{esc(uid)}</code></a> · this version <a href='{prefix}id/{esc(uid)}@{esc(version)}' "
                         f"title='Exactly this text: cite this to point at what you read'><code>@{esc(version)}</code></a></p>")
        parts.append(self.about_html(node, prefix, context))
        self.broken += [f"{node.key}: [[{target}]]" for target in context.broken]
        title = f"{node.number} {node.title}" if node.number else node.title
        self.write(node.url, page(title, "".join(parts), prefix, node.project, self.tree, node=node), node.key,
                   node.source)

    def objects_page(self, project: str) -> None:
        """<experiment>/objects.html: every page of the experiment in one table that scales to thousands of pages:
        search, subsets by type and status, sorting and pages of 50 rows (static/objects.js; the rows are JSON in the
        page). Data and Code (site-wide) are linked from it and sit under Objects in the menu."""
        relative = f"{project}/objects.html"
        prefix = prefix_for(relative)
        members = [node for node in self.tree.nodes.values() if node.project == project and node.id != "home"]
        present = sorted({node.type for node in members}, key=lambda kind: CHILD_ORDER.index(kind) if kind in CHILD_ORDER else 99)
        data = {"prefix": prefix,
                "types": [{"key": kind, "label": TYPE_PLURALS.get(kind, kind)} for kind in present],
                "icons": {kind: icons.svg(kind) for kind in present},
                "rows": [{"id": node.id, "k": node.type, "n": node.number or "", "t": node.title, "s": node.short,
                          "st": str(node.status or ""), "h": node.url, "r": status_row_class(node)} for node in members]}
        payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        contents = " · ".join(f"<a href='#type={esc(kind)}'>{esc(TYPE_PLURALS.get(kind, kind))} "
                              f"({sum(node.type == kind for node in members)})</a>" for kind in present)
        body = (crumbs([(project, f"{prefix}{project}/home.html"), ("Objects", None)], prefix)
                + f"<h1>Objects</h1><p class='help not-annotatable'>All {len(members)} pages of this experiment: "
                f"{contents}. Also: <a href='{prefix}data.html'>data files</a> and <a href='{prefix}code/index.html'>code</a>.</p>"
                + "<div id='objects' class='not-annotatable'><noscript>This list needs JavaScript; the "
                f"<a href='{prefix}{project}/map.html'>map</a> shows the same pages as a tree.</noscript></div>"
                + f"<script type='application/json' id='objects-data'>{payload}</script>"
                + f"<script src='{prefix}_assets/objects.js'></script>")
        self.write(relative, page(f"Objects · {project}", body, prefix, project, self.tree, here="Objects"))

    def map_page(self, project: str) -> None:
        relative = f"{project}/map.html"
        prefix = prefix_for(relative)
        home = self.tree.projects[project]

        def branch(node: Node) -> str:
            children = self.tree.children(node)
            info = self.stability.of(node.source)
            line = (f"{tagline(node, prefix) if node.number else type_badge(node) + node_link(node, prefix)} "
                    f"{status_pill(node)} <span class='dot stab-{info.state}' title='{esc(info.text)}'></span>")
            if not children:
                return f"<li>{line}</li>"
            return (f"<li><details class='tree' open><summary>{line}</summary><ul class='tree'>"
                    + "".join(branch(child) for child in children) + "</ul></details></li>")
        body = (crumbs([(project, f"{prefix}{home.url}"), ("Map", None)], prefix)
                + f"<h1>Map of {esc(project)}</h1><p class='help'>Every page in its place in the tree; hover a title "
                  "for its one-line summary; the dot shows how settled a page is (amber: changed in the latest release or now, grey: "
                  "unchanged since, green: unchanged for 3 or more releases). <a href='#' onclick=\"document.querySelectorAll('details.tree')"
                  ".forEach(d=>d.open=true);return false\">expand all</a> · <a href='#' onclick=\"document"
                  ".querySelectorAll('details.tree').forEach(d=>d.open=false);return false\">collapse all</a></p>"
                + f"<ul class='tree not-annotatable'>{branch(home)}</ul>")
        self.write(relative, page(f"Map · {project}", body, prefix, project, self.tree, here="Map"))


    # columns of the relations graph, left to right (question → hypothesis → result → conclusion)
    GRAPH_COLUMNS = {"experiment": 0, "premise": 1, "question": 1, "hypothesis": 2, "decision": 2, "step": 3,
                     "artefact": 4, "resource": 4, "result": 5, "figure": 6, "caveat": 6, "conclusion": 7, "term": 8,
                     "reference": 8}
    GRAPH_HIDDEN = ("artefact", "resource", "figure", "term", "reference")        # unticked when the page opens
    TYPE_COLOURS = {"experiment": "#333333", "premise": "#6a4c93", "question": "#1f77b4", "hypothesis": "#a23c9e",
                    "step": "#2a7f62", "result": "#8c564b", "conclusion": "#c0392b", "decision": "#757575",
                    "figure": "#17818a", "artefact": "#966d09", "caveat": "#c64f00", "term": "#556677",
                    "reference": "#556677", "resource": "#5b6b2f"}
    RELATION_COLOURS = {"supports": "#1b7f4b", "supported_by": "#1b7f4b", "opposes": "#c0392b",
                        "opposed_by": "#c0392b", "limits": "#c64f00", "answers": "#1f77b4", "tests": "#a23c9e",
                        "relies_on": "#6a4c93"}

    def relations_page(self, project: str) -> None:
        """An interactive graph of the typed relations of one experiment (Cytoscape.js, copied into the site)."""
        from kea.docsite.nodes import FORWARD_LABELS
        relative = f"{project}/relations.html"
        prefix = prefix_for(relative)
        members = [node for node in self.tree.nodes.values() if node.project == project]
        columns: dict[int, list[Node]] = {}
        for node in members:
            columns.setdefault(self.GRAPH_COLUMNS.get(node.type, 8), []).append(node)
        elements, positions = [], {}
        for column, nodes in columns.items():
            nodes.sort(key=lambda item: (CHILD_ORDER.index(item.type) if item.type in CHILD_ORDER else 99,
                                         len(item.number), item.number, item.id))
            for row, node in enumerate(nodes):
                positions[node.key] = {"x": column * 230, "y": row * 64}
        for node in members:
            label = f"{node.number} {node.title}" if node.number else node.title
            elements.append({"group": "nodes", "data": {
                "id": node.key, "label": label if len(label) <= 60 else label[:57] + "…", "type": node.type,
                "colour": self.TYPE_COLOURS.get(node.type, "#556677"), "url": f"{prefix}{node.url}",
                "title": label, "short": node.short, "status": str(node.status or ""),
                "stability": self.stability.of(node.source).state,
                "stability_text": self.stability.of(node.source).text},
                "position": positions[node.key]})
        relation_names: set[str] = set()
        for node in members:
            if node.parent and f"{project}:{node.parent}" in self.tree.nodes:
                elements.append({"group": "edges", "data": {
                    "id": f"parent|{node.key}", "source": f"{project}:{node.parent}", "target": node.key,
                    "relation": "parent", "label": "", "colour": "#d0d4dc"}})
            for relation, targets in node.relations.items():
                for target in targets:
                    if target in self.tree.nodes and self.tree.nodes[target].project == project:
                        relation_names.add(relation)
                        elements.append({"group": "edges", "data": {
                            "id": f"{relation}|{node.key}|{target}", "source": node.key, "target": target,
                            "relation": relation, "label": FORWARD_LABELS.get(relation, relation).lower(),
                            "colour": self.RELATION_COLOURS.get(relation, "#8a94a6")}})
        types_present = sorted({node.type for node in members},
                               key=lambda kind: CHILD_ORDER.index(kind) if kind in CHILD_ORDER else 99)
        type_boxes = "".join(
            f"<label><input type='checkbox' data-type='{esc(kind)}'"
            f"{'' if kind in self.GRAPH_HIDDEN else ' checked'}> <span class='badge t-{esc(kind)}'>"
            f"{esc(TYPE_PLURALS.get(kind, kind))}</span></label> " for kind in types_present)
        relation_boxes = "".join(
            f"<label><input type='checkbox' data-relation='{esc(name)}' checked> "
            f"<span style='border-bottom:3px solid {self.RELATION_COLOURS.get(name, '#8a94a6')}'>"
            f"{esc(FORWARD_LABELS.get(name, name).lower())}</span></label> " for name in sorted(relation_names))
        relation_boxes += ("<label><input type='checkbox' data-relation='parent'> "
                           "<span style='border-bottom:3px solid #d0d4dc'>tree (parent)</span></label>")
        home = self.tree.projects[project]
        body = (crumbs([(project, f"{prefix}{home.url}"), ("Relations", None)], prefix)
                + f"<h1>Relations in {esc(project)}</h1>"
                "<div class='short'>Every page as a box, coloured by type, and every typed relation as an arrow "
                "(supports, opposes, answers, tests, limits, …). Left to right: questions, hypotheses, steps, "
                "results, conclusions. Hover a box for its summary, click it to open the page, drag to rearrange, "
                "scroll to zoom. Border: amber = changed in the latest release or now, green = unchanged for 3 or more releases. "
                "The tree view is the <a href='map.html'>map</a>.</div>"
                f"<div class='box not-annotatable'><b>Show page types:</b> {type_boxes}<br><b>Show relations:</b> "
                f"{relation_boxes} <button id='graph-fit'>fit</button></div>"
                "<div id='graph' class='not-annotatable' style='height:72vh;border:1px solid var(--line);"
                "border-radius:8px;background:#fff'></div><div id='graph-tip' class='graph-tip' hidden></div>"
                "<style>.graph-tip{position:fixed;max-width:380px;background:#1d2330;color:#fff;font-size:13px;"
                "padding:7px 10px;border-radius:6px;pointer-events:none;z-index:50}</style>"
                f"<script src='{prefix}_assets/cytoscape.min.js'></script>"
                f"<script>const GRAPH = {json.dumps(elements)};</script>"
                "<script>" + RELATIONS_JS + "</script>")
        self.write(relative, page(f"Relations · {project}", body, prefix, project, self.tree, here="Relations"))

    # ------------------------------------------------------------------ other pages
    def code_pages(self) -> None:
        for path, code_file in self.code.files.items():
            relative = self.code.page_of(path)
            prefix = prefix_for(relative)
            used = [(text, f"{prefix}{url}") for text, url in self.code_used_on.get(path, [])]
            body = crumbs([("Code", f"{prefix}code/index.html"), (path, None)], prefix) + \
                codepages.code_body(code_file, prefix, used)
            self.write(relative, page(path, body, prefix, None, self.tree).replace(
                "</style>", codepages.pygments_css() + "</style>", 1), f"code/{path}", PROJECT_ROOT / path)
        prefix = prefix_for("code/index.html")
        self.write("code/index.html", page("Code", crumbs([("Code", None)], prefix) +
                                           codepages.index_body(self.code, prefix), prefix, None, self.tree))

    def change_pages(self) -> list[changes.Run]:
        from kea.feedback import store
        threads = store.threads()
        commits = changes.all_commits()
        for commit in commits:
            relative = f"commits/{commit.short}.html"
            prefix = prefix_for(relative)
            body = crumbs([("History", f"{prefix}changes/index.html"), (f"commit {commit.short}", None)], prefix) \
                + changes.commit_body(commit, self.tree, threads, self.code_href, prefix)
            self.write(relative, page(f"Commit {commit.short}", body, prefix, None, self.tree, wide=True))
        runs = changes.load_runs(commits)
        for run in runs:
            relative = f"changes/{run.id}.html"
            prefix = prefix_for(relative)
            context = self.context(next(iter(self.tree.projects), ""), prefix)
            body = (crumbs([("History", f"{prefix}changes/index.html"), (run.id, None)], prefix)
                    + f"<h1>{esc(run.title)}</h1><p class='help'>Run <code>{esc(run.id)}</code> · {esc(run.date)}</p>"
                    + f"<article>{render_markdown(run.body, context)}</article>"
                    + changes.run_generated(run, self.tree, threads, self.code_href, prefix))
            self.broken += [f"run {run.id}: [[{target}]]" for target in context.broken]
            self.write(relative, page(run.title, body, prefix, None, self.tree), f"changes/{run.id}", run.source)
        prefix = prefix_for("changes/index.html")
        run_items = "".join(f"<li><a href='{run.id}.html'>{esc(run.title)}</a> <span class='help'>{esc(run.date)} · "
                            f"{len(run.commits)} commit(s)</span></li>" for run in runs)
        commit_items = "".join(f"<li><a href='../commits/{esc(commit.short)}.html'><code>{esc(commit.short)}</code></a> "
                               f"{esc(commit.date)} · {esc(commit.subject)}"
                               f"{' · run ' + esc(commit.run) if commit.run else ''}</li>" for commit in commits)
        release_rows = "".join(
            f"<tr><td><b>{esc(release.label)}</b></td><td>{esc(release.date.replace('T', ' ')[:16])}</td>"
            f"<td>{esc(release.kind)}</td><td>"
            + changes.run_link(release.run, prefix)
            + f"</td><td>{cycle_cell(release.cycle)}</td>"
            f"<td><a href='../commits/{esc(release.short)}.html'><code>{esc(release.short)}</code></a></td>"
            f"<td>{esc(release.reason)}</td></tr>"
            for release in reversed(self.site_releases))
        versions_html = ("<h2>Versions</h2><p class='help'>Semantic versions chosen at each release (MAJOR: a "
                         "conclusion changes direction or is withdrawn; MINOR: new results or pages; PATCH: wording "
                         "only; before 1.0 a major change counts as minor). Each is a git tag: <code>git checkout "
                         f"{esc(versions.tag_name('0.2.0'))} &amp;&amp; make site</code> rebuilds it."
                         + ("" if mode.MODE == "public" else " See also the <a href='../history.html'>history of review "
                            "cycles</a>.") + "</p><table class='not-annotatable'><tr><th>version</th>"
                         "<th>released</th><th>kind</th><th>run</th><th>plan</th><th>commit</th><th>why</th></tr>"
                         f"{release_rows}</table>") if self.site_releases else ""
        body = (crumbs([("History", None)], prefix) + "<h1>History: what changed</h1>"
                "<div class='short'>Each agent run writes one entry (what was asked, what changed, what was found, what "
                "was not done); the site adds its commits, the pages it changed and the comments it answered.</div>"
                + versions_html +
                f"<h2>Runs</h2><ul>{run_items or '<li class=help>none</li>'}</ul>"
                f"<h2>All commits</h2><ul class='not-annotatable'>{commit_items}</ul>")
        self.write("changes/index.html", page("History", body, prefix, None, self.tree))
        return runs

    def home_page(self, runs: list[changes.Run]) -> None:
        experiments = self.node_table(list(self.tree.projects.values()), "",
                                      extra=lambda home: self.review_pill(home.project, ""))
        latest = ""
        if runs:
            run = runs[0]
            latest = (f"<h2>Latest run</h2><table class='nodes'><colgroup><col class='c-page'><col><col class='c-status'>"
                      f"</colgroup><tr><td><a href='changes/{run.id}.html'>{esc(run.title)}</a></td>"
                      f"<td>{esc(run.date)}</td><td>{len(run.commits)} commit(s)</td></tr></table>")
        summary = questions.project_summary(self.tree)
        if not summary:
            self.tree.notes.append("site: no executive summary for the project (doc/_summary.md; with one "
                                   "experiment, the text of its home page before the first ## heading)")
        context = self.context(next(iter(self.tree.projects), ""), "")
        body = (crumbs([], "") + f"<h1>{esc(SETTINGS['heading'])}</h1>"
                + (f"<h2>Summary</h2><article>{render_markdown(summary, context)}</article>" if summary else
                   "<div class='short'>Working documentation of the project: each experiment is a tree of small "
                   "pages (questions, premises, hypotheses, steps, results, conclusions, caveats).</div>")
                + "<p class='help not-annotatable'>New here? <a href='help.html'>How to read this site</a>.</p>"
                + f"<h2>Experiments</h2><div class='not-annotatable'>{experiments}</div>{latest}"
                + ("<h2>About this site</h2><ul class='not-annotatable'>" + "".join(
                    f"<li><a href='{esc(href)}'>{esc(title)}</a> <span class='help'>{esc(short)}</span></li>"
                    for href, title, short in getattr(self, "site_listing", [])) + "</ul>"
                   if getattr(self, "site_listing", None) else ""))
        self.broken += [f"doc/_summary.md: [[{target}]]" for target in context.broken]
        # the summary's own file makes the front page editable (Edit, section and selection edits)
        summary_file = PROJECT_ROOT / "doc" / "_summary.md"
        summary_source = summary_file if summary_file.exists() else \
            next(iter(self.tree.projects.values())).source if len(self.tree.projects) == 1 and summary else None
        self.write("index.html", page(SETTINGS["title"], body, "", None, self.tree), source=summary_source)

    def help_page(self) -> None:
        """help.html: how to read the site (the menu's Help and the kea logo), with a link to Kea's own pages."""
        from kea.docsite import icons
        from kea.docsite.nodes import TYPE_LABELS
        meanings = {"experiment": "the experiment's home page: what it asks and why", "premise": "what we take as given",
                    "question": "what we ask", "hypothesis": "what we expected, and when that was written down",
                    "step": "what we did (methods)", "decision": "a choice made along the way, and why",
                    "result": "what a file shows (every number from a named file)",
                    "conclusion": "what we make of results, with the evidence for and against",
                    "figure": "a figure with its full caption", "artefact": "a data file, with download",
                    "caveat": "what limits a result or conclusion", "term": "a glossary entry",
                    "resource": "a data source, database, MCP server or file the analysis takes from outside, with its "
                                "version, date, checksum and local copy",
                    "reference": "a paper, with its abstract and why it is cited"}
        prefixes = self.tree.schema.get("number_prefix", {})

        def legend(kind: str) -> str:        # the kind as on every page: word in its colour, then the tag
            number = f"{prefixes[kind]}1" if kind in prefixes else ""
            tag = (f" <span class='tag t-{kind}'>{icons.svg(kind)}{number}</span>" if number else "")
            return f"<span class='fullname k-{kind}'>{esc(TYPE_LABELS.get(kind, kind))}{tag}</span>"
        rows = "".join(f"<tr><td>{legend(kind)}</td><td>{esc(meaning)}</td></tr>" for kind, meaning in meanings.items())
        body = (crumbs([("Help", None)], "") + "<h1>How to read this site</h1>"
                "<div class='short'>The documentation of a data analysis as a tree of small pages, one idea per page, "
                "linked by typed relations (supports, opposes, answers, tests, limits).</div>"
                "<h2>Where to start</h2><ul>"
                "<li>The home page has the project's summary; each experiment's page has its summary and every "
                "question with its answer in short. A question page leads with its conclusions and results.</li>"
                "<li>The menu bar shows where you are: <b>Kea</b> (home) / project / experiment / page. The kea logo "
                "at the right opens this page.</li>"
                "<li>Every page ends with its connections and with its version and history; "
                "<a href='changes/index.html'>History</a> lists each working session.</li></ul>"
                "<h2>Tags and colours</h2><p>Each page has a type, shown as a coloured tag with an icon and a number "
                "(Q1, R2, C3). The tag is always the link to that page; hover it for the page's one-line summary. "
                "In lists of pages the whole line is the link.</p>"
                f"<table class='not-annotatable'>{rows}</table>"
                "<p>The pill next to a tag is the page's status (green: settled or supported; amber: exploratory, "
                "open or inconclusive; red: rejected). Hypotheses say whether they were <i>written before their "
                "test</i> or <i>written after results</i>. Words with a dotted underline link to the glossary.</p>"
                "<h2>Comments and edits</h2><ul>"
                "<li>Select any text and press <b>Comment</b>; the panel at the bottom right lists the comments on "
                "the page.</li>"
                "<li>The <b>Edit</b> button in the menu bar opens the page's Markdown; the pencil next to a section "
                "heading edits just that section. An edit is saved as a suggestion, shown as a diff; the agent "
                "folds it into the plan of the review cycle.</li>"
                "<li>Review cycles: comments are collected into a <a href='plan.html'>plan</a>; a reader freezes "
                "it and presses Implement; the agent implements, answers every comment and releases a new version "
                "(<a href='history.html'>History</a>).</li></ul>"
                "<h2>About Kea</h2><p>This site is built with Kea, a tool for documenting an analysis as typed, "
                "commentable pages. More help, the page types in full and how to install it: "
                "<a href='https://mfiers.github.io/Kea/#reading'>mfiers.github.io/Kea</a>.</p>")
        if mode.MODE != "review":       # no comments, editor, plans or history without the comment server
            body = re.sub(r"<h2>Comments and edits</h2>.*?</ul>", "", body, flags=re.S)
        self.write("help.html", page("Help", body, "", None, self.tree))

    def site_pages(self) -> list[tuple[str, str, str]]:
        """Site-wide pages from doc/_site/*.md (title, short in front matter) into site/<name>.html.
        Returns (href, title, short) for the home page."""
        from kea.docsite.nodes import DOC, split_front_matter
        listed = []
        for source in sorted((DOC / "_site").glob("*.md")):
            header, text = split_front_matter(source.read_text(encoding="utf-8"), source)
            relative = f"site/{source.stem}.html"
            prefix = prefix_for(relative)
            context = self.context(next(iter(self.tree.projects), ""), prefix)
            title = str(header.get("title", source.stem))
            body = (crumbs([(title, None)], prefix) + f"<h1>{esc(title)}</h1>"
                    + (f"<div class='short'>{esc(header['short'])}</div>" if header.get("short") else "")
                    + f"<article>{render_markdown(text, context)}</article>")
            self.broken += [f"_site/{source.name}: [[{target}]]" for target in context.broken]
            self.write(relative, page(title, body, prefix, None, self.tree), f"site/{source.stem}", source)
            listed.append((relative, title, str(header.get("short", ""))))
        return listed

    def feedback_page(self) -> None:
        key_to_href = {key: relative for relative, (key, _) in self.pages.items()}
        body = crumbs([("Comments", None)], "") + comments.overview_body(key_to_href, self.tree.projects)
        self.write("feedback.html", page("Comments", body, "", None, self.tree))

    def plan_pages(self) -> None:
        """plan.html (current cycle) and cycles/<cycle>.html for every plan in doc/_cycles/."""
        from kea.feedback import cycle as review_cycle
        from kea.docsite.nodes import DOC, split_front_matter
        current = review_cycle.state()
        project = next(iter(self.tree.projects), "")
        plans = {}
        for source in sorted((DOC / "_cycles").glob("cycle-*.md")):
            header, body = split_front_matter(source.read_text(encoding="utf-8"), source)
            plans[int(header.get("cycle", source.stem.split("-")[-1]))] = (header, body, source)

        def render_plan(number: int, prefix: str, live: bool) -> str:
            if number not in plans:
                return (f"<h1>Plan for cycle {number}</h1><div class='short'>No plan yet. Claude writes one when it "
                        "goes through the comments; it lists, per comment, what will change.</div>"
                        f"<div id='fb-plan-actions' data-items='0' class='not-annotatable'></div>")
            header, body, source = plans[number]
            context = self.context(project, prefix)
            items = len(re.findall(r"^### ", body, flags=re.M))
            label = history.cycle_version_label(number, versions.releases(""))
            body = re.sub(r"^### (\d+)\.\s+(.*)$",
                          lambda match: f"<h3 id='item-{match.group(1)}'>{esc(label + ' ') if label else ''}#"
                                        f"{match.group(1)} · {esc(match.group(2))}</h3>", body, flags=re.M)
            actions = (f"<div id='fb-plan-actions' data-items='{items}' class='not-annotatable'>"
                       "<span class='help'>The Implement button appears when the comment server is running.</span></div>"
                       if live else "")
            release = ""
            if header.get("run"):
                release = (f"<div class='box not-annotatable'>Implemented in run "
                           f"{changes.run_link(str(header['run']), prefix)}.</div>")
            shown = header.get("status", "open")
            if number == current.cycle and shown != "implemented":     # the live state, not the file's
                shown = current.state
            html_body = (f"<h1>{esc(header.get('title', f'Plan for cycle {number}'))}</h1>"
                         f"<div class='not-annotatable'><span class='pill s-{esc(shown)}'"
                         f"{' id=' + chr(39) + 'fb-plan-state' + chr(39) if number == current.cycle else ''}>"
                         f"{esc(shown)}</span> <span class='help'>cycle {number} · {items} item(s)"
                         f"{' · updated ' + esc(header['updated']) if header.get('updated') else ''}</span></div>"
                         f"{actions}{release}<article>{render_markdown(body, context)}</article>")
            self.broken += [f"plan {number}: [[{target}]]" for target in context.broken]
            return html_body

        prefix = prefix_for("plan.html")
        state_text = {"collecting": "phase 1, comments everywhere; Claude folds them into this plan",
                      "frozen": "phase 2, frozen for review: comments only on this plan",
                      "implement-requested": "implementation requested",
                      "implementing": "being implemented"}.get(current.state, current.state)
        body = (crumbs([("Plan", None)], prefix)
                + f"<p class='help not-annotatable'>Review cycle {current.cycle}: {esc(state_text)}. "
                  f"Earlier plans: <a href='cycles/index.html'>all cycles</a>.</p>"
                + render_plan(current.cycle, prefix, True))
        source = plans.get(current.cycle, (None, None, None))[2]
        self.write("plan.html", page(f"Plan · cycle {current.cycle}", body, prefix, None, self.tree),
                   f"plan/cycle-{current.cycle}", source)
        for number, (_, _, source) in plans.items():
            relative = f"cycles/cycle-{number:03d}.html"
            prefix = prefix_for(relative)
            body = crumbs([("Plans", f"{prefix}cycles/index.html"), (f"cycle {number}", None)], prefix) + \
                render_plan(number, prefix, False)
            self.write(relative, page(f"Plan · cycle {number}", body, prefix, None, self.tree),
                       f"plan/cycle-{number}", source)
        prefix = prefix_for("cycles/index.html")
        items = "".join(f"<li><a href='cycle-{number:03d}.html'>{esc(header.get('title', number))}</a> "
                        f"<span class='pill s-{esc(header.get('status', ''))}'>{esc(header.get('status', ''))}</span></li>"
                        for number, (header, _, _) in sorted(plans.items(), reverse=True))
        body = (crumbs([("Plans", None)], prefix) + "<h1>Review cycles</h1><div class='short'>Each cycle has two "
                "phases. Phase 1: readers comment anywhere and Claude folds the comments into one plan for the whole "
                "site, grouped by experiment. Phase 2: a reader presses “Freeze for review”; comments are then possible "
                "only on the plan, and the plan shows whether every comment is in it. Then “Implement the plan” "
                "(Claude implements, writes the change log and releases a new version; comments reopen) or "
                "“Unfreeze”.</div>"
                f"<ul>{items or '<li class=help>no plans yet</li>'}</ul>")
        self.write("cycles/index.html", page("Review cycles", body, prefix, None, self.tree))

    # ------------------------------------------------------------------ main

    def stability_pill(self, node: Node) -> str:
        info = self.stability.of(node.source)
        return (f" <span class='pill stab-{info.state}' title='Site releases: when this page last changed. Green = "
                f"unchanged for {versions.SETTLED_AFTER}+ releases, amber = changed in the latest release or now.'>"
                f"{esc(info.text)}</span>")

    def version_note(self, node: Node) -> str:
        """' (v0.2.0)': the site release in which the page first appeared, '' before its first release."""
        created = self.stability.of(node.source).created_in
        return f" ({created})" if created else " (next release)"

    def experiment_version(self, project: str) -> str:
        own = versions.releases(project)
        return own[-1].label if own else ""

    def render_all(self) -> None:
        """Every page, in dependency order (the plan and home pages use what earlier pages collected)."""
        self.site_releases = versions.releases("")
        self.stability = versions.Stability(self.site_releases)
        self.stability.prepare([node.source for node in self.tree.nodes.values()])
        self.under_review = self.review_counts()
        for node in self.tree.nodes.values():
            self.node_page(node)
        for project in self.tree.projects:
            self.map_page(project)
            self.relations_page(project)
            self.objects_page(project)
        self.code_pages()
        runs = self.change_pages() if mode.WITH_CHANGELOG else []
        if mode.MODE != "public":
            self.plan_pages()
        self.site_listing = self.site_pages()
        self.home_page(runs)
        self.help_page()
        if mode.MODE != "public":
            self.feedback_page()
            self.history_page()
        self.data_page()

    def data_page(self) -> None:
        """Every artefact and every data file the documentation refers to, with size, checksum and download."""
        prefix = ""
        artefact_rows = []
        for node in sorted((node for node in self.tree.nodes.values() if node.type == "artefact"),
                           key=lambda item: (item.project, len(item.number), item.number)):
            relative = str(node.header.get("path", ""))
            path = PROJECT_ROOT / relative
            size = artefacts.human_size(path.stat().st_size) if path.is_file() else ("folder" if path.is_dir() else "missing")
            link, entry = artefacts.download_html(relative, prefix)
            if entry:
                self.downloads.add(entry)
            artefact_rows.append(f"<tr><td>{node_link(node, prefix)}</td><td><a href='{prefix}{node.url}'>"
                                 f"{esc(node.title)}</a></td><td><code>{esc(relative)}</code></td><td>{size}</td>"
                                 f"<td>{link.removeprefix(' · ')}</td></tr>")
        referenced = sorted(self.data_files - {str(node.header.get("path", "")) for node in self.tree.nodes.values()
                                               if node.type == "artefact"})
        other_rows = artefacts.file_rows(referenced, prefix, self.downloads)
        note = {"review": "Downloads go through the site server (files up to 1 GB).",
                "local": "Links open the files in the project folder.",
                "public": "This public copy does not include the data files; ask the authors."}[mode.MODE]
        resource_rows = "".join(
            f"<tr><td>{node_link(node, prefix)}</td><td><a href='{prefix}{node.url}'>{esc(node.title)}</a></td>"
            f"<td>{esc(node.header.get('kind', ''))}</td><td>{esc(node.header.get('rrid', ''))}</td>"
            f"<td>{esc(node.header.get('version', ''))}</td>"
            f"<td>{esc(node.header.get('retrieved', ''))}</td>"
            f"<td><code>{esc(str(node.header.get('sha256', ''))[:12])}</code></td></tr>"
            for node in sorted((node for node in self.tree.nodes.values() if node.type == "resource"),
                               key=lambda item: (item.project, natural(item.number))))
        figure_rows = "".join(
            f"<tr><td>{node_link(node, prefix)}</td><td><a href='{prefix}{node.url}'>{esc(node.title)}</a></td>"
            f"<td><code>{esc(node.header.get('image', ''))}</code></td><td><code>{esc(node.header.get('script', ''))}"
            f"</code></td><td><code>{esc(node.header.get('table', ''))}</code></td></tr>"
            for node in sorted((node for node in self.tree.nodes.values()
                                if node.type == "figure" and node.header.get("image")),
                               key=lambda item: (item.project, natural(item.number))))
        body = (crumbs([("Data", None)], prefix) + "<h1>Data</h1><div class='short'>Every file the documentation "
                f"refers to: the resources it takes from outside, the artefacts it made (each with its own page), "
                f"the figure files and the other data files named as sources. {note}</div>"
                + (f"<h2>Resources</h2><table class='not-annotatable'><tr><th></th><th>what</th><th>kind</th>"
                   f"<th>RRID</th><th>version</th><th>retrieved</th><th>sha256</th></tr>{resource_rows}</table>"
                   if resource_rows else "")
                + (f"<h2>Artefacts ({len(artefact_rows)})</h2><table class='not-annotatable'><tr><th></th><th>what</th>"
                   f"<th>path</th><th>size</th><th></th></tr>{''.join(artefact_rows)}</table>" if artefact_rows else
                   "<h2>Artefacts</h2><p class='help'>None yet: an artefact is a file the analysis made, with its own "
                   "page (type <code>artefact</code>).</p>")
                + (f"<h2>Other data files named as sources</h2><table class='not-annotatable'><tr><th>file</th>"
                   f"<th>size</th><th>sha256</th><th></th></tr>{other_rows}</table>"
                   if other_rows and mode.data_links() else "")
                + (f"<h2>Figure files</h2><table class='not-annotatable'><tr><th></th><th>figure</th><th>image</th>"
                   f"<th>script</th><th>table</th></tr>{figure_rows}</table>" if figure_rows else ""))
        self.write("data.html", page("Data", body, prefix, None, self.tree))

    def history_page(self) -> None:
        key_to_href = {key: relative for relative, (key, _) in self.pages.items()}
        body = crumbs([("History", "changes/index.html"), ("Review cycles", None)], "") + history.body(self.tree, "", key_to_href)
        self.write("history.html", page("History of review cycles", body, "", None, self.tree, wide=True))


def cycle_cell(cycle: str) -> str:
    """'cycle N' in the release table, linked to the plan page when doc/_cycles/cycle-NNN.md exists (a release can
    come from a cycle without a written plan; its page is then not built)."""
    from kea.docsite.nodes import DOC
    if not (cycle.isdigit() and int(cycle) > 0) or mode.MODE == "public":
        return ""
    if not (DOC / "_cycles" / f"cycle-{int(cycle):03d}.md").is_file():
        return f"cycle {esc(cycle)}"
    return f"<a href='../cycles/cycle-{int(cycle):03d}.html'>cycle {esc(cycle)}</a>"
