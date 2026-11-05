"""History of review cycles: per release, the comments, plan items, commits and pages that went into it.

One band per site release (newest first) plus the upcoming one (the cycle being collected or implemented). Each
band has four columns: comments → plan items → commits → pages changed, with lines between connected elements:
a comment is connected to the plan item that names its thread, a plan item to the commits whose message answers
one of its threads (``Answers-comment:``), and a commit to the documentation pages it changed.

Release ↔ cycle: the tag message's ``Cycle:`` line (see docsite.versions); the upcoming band is the current cycle.
Plan items are the ``### N. …`` headings of doc/_cycles/cycle-NNN.md, labelled ``vX.Y #N``.

Input: git tags and history, doc/_cycles/, comment threads, the tree. Output: the body of history.html.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from kea.docsite import changes, versions
from kea.docsite.nodes import DOC, PROJECT_ROOT, Tree, split_front_matter
from kea.docsite.render import esc
from kea.feedback import store

THREAD_ID = re.compile(r"\bt\d{4}_\d{2}_\d{2}_[0-9a-f]{6}\b")
ITEM_HEADING = re.compile(r"^### (\d+)\.\s+(.*)$", flags=re.M)
STATUS_COLOURS = {"open": "#d9822b", "planned": "#a86b00", "answered": "#1b7f4b", "page-changed": "#1b7f4b",
                  "resolved": "#6b7280", "wont-fix": "#a33"}


@dataclass
class PlanItem:
    number: int
    title: str
    threads: list[str]


@dataclass
class Band:
    label: str                       # "v0.2.0" or "upcoming v0.3.0"
    short_label: str                 # "v0.2" (for item labels)
    cycle: int | None
    release: versions.Release | None
    items: list[PlanItem] = field(default_factory=list)
    threads: list[store.Thread] = field(default_factory=list)
    commits: list[changes.Commit] = field(default_factory=list)
    pages: dict[str, list[str]] = field(default_factory=dict)      # commit short -> node keys


def plan_items(cycle: int) -> tuple[dict, list[PlanItem]]:
    source = DOC / "_cycles" / f"cycle-{cycle:03d}.md"
    if not source.exists():
        return {}, []
    header, body = split_front_matter(source.read_text(encoding="utf-8"), source)
    headings = list(ITEM_HEADING.finditer(body))
    items = []
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        text = body[match.start():end]
        items.append(PlanItem(int(match.group(1)), match.group(2).strip(), sorted(set(THREAD_ID.findall(text)))))
    return header, items


def short_version(version: str) -> str:
    return "v" + ".".join(version.split(".")[:2])


def cycle_version_label(cycle: int, site_releases: list[versions.Release]) -> str:
    """'v0.2' for a released cycle, the plan's planned version for the current one, else ''."""
    for release in site_releases:
        if release.cycle == str(cycle):
            return short_version(release.version)
    header, _ = plan_items(cycle)
    return short_version(str(header["version"])) if header.get("version") else ""


def _range_commits(start: str | None, end: str, by_full: dict[str, changes.Commit]) -> list[changes.Commit]:
    spec = f"{start}..{end}" if start else end
    return [by_full[full] for full in changes.git("rev-list", spec).split() if full in by_full]


def bands(tree: Tree) -> list[Band]:
    from kea.feedback import cycle as review_cycle
    site_releases = versions.releases("")
    commits = changes.all_commits()
    by_full = {commit.full: commit for commit in commits}
    threads = {thread.thread_id: thread for thread in store.threads()}
    source_to_key = {str(node.source.relative_to(PROJECT_ROOT)): node.key for node in tree.nodes.values()}
    result = []
    previous = None
    for release in site_releases:
        cycle = int(release.cycle) if release.cycle.isdigit() else None
        result.append(Band(release.label, short_version(release.version), cycle, release,
                           commits=_range_commits(previous, release.commit, by_full)))
        previous = release.commit
    current = review_cycle.state()
    header, _ = plan_items(current.cycle)
    planned = f"v{header['version']}" if header.get("version") else "next release"
    result.append(Band(f"upcoming: {planned}", short_version(str(header["version"])) if header.get("version") else "",
                       current.cycle, None, commits=_range_commits(previous, "HEAD", by_full)))
    for band in result:
        if band.cycle:
            _, band.items = plan_items(band.cycle)
        wanted = {thread_id for item in band.items for thread_id in item.threads}
        wanted |= {thread_id for commit in band.commits for thread_id in commit.answers}
        band.threads = [threads[thread_id] for thread_id in sorted(wanted) if thread_id in threads]
        for commit in band.commits:
            files = changes.git("show", "--name-only", "--format=", commit.full).split()
            band.pages[commit.short] = sorted({source_to_key[path] for path in files if path in source_to_key})
    return list(reversed(result))


def thread_href(thread: store.Thread, key_to_href: dict[str, str], prefix: str) -> str:
    """The thread opened in the comment panel of its page (#fb-<id>); the comments overview if the page is gone."""
    page = key_to_href.get(thread.page)
    if page:
        return f"{prefix}{page}#fb-{thread.thread_id}"
    return f"{prefix}feedback.html#fbs-{thread.thread_id}"


def body(tree: Tree, prefix: str, key_to_href: dict[str, str]) -> str:
    sections = []
    for band in bands(tree):
        links: list[tuple[str, str]] = []
        item_of_thread = {}
        for item in band.items:
            for thread_id in item.threads:
                item_of_thread.setdefault(thread_id, item.number)
                links.append((f"c-{thread_id}", f"i-{band.label}-{item.number}"))
        for commit in band.commits:
            for item in band.items:
                if set(item.threads) & set(commit.answers):
                    links.append((f"i-{band.label}-{item.number}", f"k-{commit.short}"))
            for key in band.pages.get(commit.short, []):
                links.append((f"k-{commit.short}", f"p-{band.label}-{key}"))
        plan_exists = bool(band.cycle) and (DOC / "_cycles" / f"cycle-{band.cycle:03d}.md").exists()
        plan_href = (f"{prefix}plan.html" if band.release is None else
                     f"{prefix}cycles/cycle-{band.cycle:03d}.html" if plan_exists else "")
        comments_html = "".join(
            f"<li id='c-{esc(thread.thread_id)}' class='hx'><span class='hdot' style='background:"
            f"{STATUS_COLOURS.get(thread.status, '#888')}' title='{esc(thread.status)}'></span>"
            f"<a href='{esc(thread_href(thread, key_to_href, prefix))}'>{esc(thread.author)}: "
            f"{esc(thread.text[:70])}{'…' if len(thread.text) > 70 else ''}</a>"
            + (f" <span class='help'>→ {esc(band.short_label)} #{item_of_thread[thread.thread_id]}</span>"
               if thread.thread_id in item_of_thread and band.short_label else "") + "</li>"
            for thread in band.threads)
        items_html = "".join(
            f"<li id='i-{esc(band.label)}-{item.number}' class='hx'><a href='{plan_href}#item-{item.number}'>"
            f"<b>{esc(band.short_label)} #{item.number}</b> {esc(item.title)}</a></li>" for item in band.items)
        commits_html = "".join(
            f"<li id='k-{esc(commit.short)}' class='hx'><a href='{prefix}commits/{esc(commit.short)}.html'>"
            f"<code>{esc(commit.short)}</code> {esc(commit.subject[:70])}{'…' if len(commit.subject) > 70 else ''}"
            f"</a></li>" for commit in band.commits)
        changed = sorted({key for keys in band.pages.values() for key in keys})
        pages_html = "".join(
            f"<li id='p-{esc(band.label)}-{esc(key)}' class='hx'><a href='{prefix}{tree.nodes[key].url}'>"
            f"{esc(tree.nodes[key].number or '')} {esc(tree.nodes[key].title[:60])}</a> "
            f"<span class='help'>{esc(tree.nodes[key].project)}</span></li>" for key in changed)
        release = band.release
        meta = (f"released {esc(release.date.replace('T', ' ')[:16])} · {esc(release.kind)} · run "
                f"<a href='{prefix}changes/{esc(release.run)}.html'>{esc(release.run)}</a> · {esc(release.reason)}"
                if release else "being collected or implemented now")
        plan_link = (f" · <a href='{plan_href}'>plan (cycle {band.cycle}"
                     f"{', no items yet' if band.release is None and not band.items else ''})</a>" if plan_href else "")
        sections.append(
            f"<section class='band'><h2>{esc(band.label)}</h2><p class='help'>{meta}{plan_link}</p>"
            f"<div class='hgrid' data-links='{esc(json.dumps(links))}'>"
            f"<div><h3>Comments ({len(band.threads)})</h3><ul>{comments_html or '<li class=help>none</li>'}</ul></div>"
            f"<div><h3>Plan items ({len(band.items)})</h3><ul>{items_html or '<li class=help>none</li>'}</ul></div>"
            f"<div><h3>Commits ({len(band.commits)})</h3><ul>{commits_html or '<li class=help>none</li>'}</ul></div>"
            f"<div><h3>Pages changed ({len(changed)})</h3><ul>{pages_html or '<li class=help>none</li>'}</ul></div>"
            "<svg class='hlines'></svg></div></section>")
    return ("<h1>History of review cycles</h1><div class='short'>Each release with what went into it: the comments, "
            "the plan items they became, the commits that implemented them and the pages that changed. Hover an "
            "element to follow its lines. Newest first.</div>" + HISTORY_STYLE + "".join(sections) + HISTORY_SCRIPT)


HISTORY_STYLE = """<style>
.band{margin:18px 0 26px}.hgrid{position:relative;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:22px}
.hgrid ul{list-style:none;padding:0;margin:0;font-size:12.5px;line-height:1.35}.hgrid li{margin:0 0 6px;padding:3px 5px;
border-radius:4px;background:var(--soft);position:relative;z-index:1}.hgrid h3{font-size:13.5px;margin:4px 0 8px}
.hgrid li.hl{background:#fde9b8}.hdot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}
.hlines{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}
@media (max-width:760px){.hgrid{grid-template-columns:1fr}.hlines{display:none}}
</style>"""

HISTORY_SCRIPT = """<script>
(function () {
  function draw(grid) {
    const svg = grid.querySelector("svg.hlines");
    const box = grid.getBoundingClientRect();
    const links = JSON.parse(grid.dataset.links || "[]");
    svg.innerHTML = "";
    for (const [from, to] of links) {
      const a = document.getElementById(from), b = document.getElementById(to);
      if (!a || !b || !grid.contains(a) || !grid.contains(b)) continue;
      const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      const x1 = ra.right - box.left, y1 = ra.top + ra.height / 2 - box.top;
      const x2 = rb.left - box.left, y2 = rb.top + rb.height / 2 - box.top;
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      const mid = (x1 + x2) / 2;
      path.setAttribute("d", `M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`);
      path.setAttribute("fill", "none"); path.setAttribute("stroke", "#9aa6ba"); path.setAttribute("stroke-width", "1");
      path.dataset.from = from; path.dataset.to = to;
      svg.appendChild(path);
    }
  }
  function chain(grid, id) {
    const links = JSON.parse(grid.dataset.links || "[]");
    const down = new Set([id]), up = new Set([id]);
    let changed = true;
    while (changed) { changed = false;
      for (const [a, b] of links) {
        if (down.has(a) && !down.has(b)) { down.add(b); changed = true; }
        if (up.has(b) && !up.has(a)) { up.add(a); changed = true; }
      }
    }
    return new Set([...down, ...up]);
  }
  document.querySelectorAll(".hgrid").forEach(grid => {
    draw(grid);
    grid.querySelectorAll("li.hx").forEach(item => {
      item.addEventListener("mouseenter", () => {
        const on = chain(grid, item.id);
        grid.querySelectorAll("li.hx").forEach(other => other.classList.toggle("hl", on.has(other.id)));
        grid.querySelectorAll("path").forEach(path => {
          const lit = on.has(path.dataset.from) && on.has(path.dataset.to);
          path.setAttribute("stroke", lit ? "#d38b00" : "#d5dae3"); path.setAttribute("stroke-width", lit ? "2" : "1");
        });
      });
      item.addEventListener("mouseleave", () => {
        grid.querySelectorAll("li.hx").forEach(other => other.classList.remove("hl"));
        grid.querySelectorAll("path").forEach(path => { path.setAttribute("stroke", "#9aa6ba"); path.setAttribute("stroke-width", "1"); });
      });
    });
  });
  window.addEventListener("resize", () => document.querySelectorAll(".hgrid").forEach(draw));
})();
</script>"""
