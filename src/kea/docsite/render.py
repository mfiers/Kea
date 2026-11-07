"""HTML building blocks of the documentation site: page shell, CSS, top bar, breadcrumbs, link rendering, Markdown.

Pure string functions (plus Markdown rendering). Every page gets the same top bar and breadcrumbs; navigation,
generated lists and anything that changes when *other* pages change carry the class ``not-annotatable`` so reader
comments stay anchored to the page's own text.
"""
from __future__ import annotations

import html
import re

import markdown

from kea.config import SETTINGS
from kea.docsite import icons
from kea.docsite.nodes import DOC, LINK_PATTERN, TYPE_LABELS, Node, Tree

RUN_ID = re.compile(r"\d{4}-\d{2}-\d{2}-[\w-]+")

SITE_TITLE = SETTINGS["title"]     # the project (kea.yaml); its parts (doc/<folder>/) are experiments
SKIP_AUTOLINK_TAGS = {"a", "code", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "table", "script", "style"}

CSS = """
:root{--fg:#1d2330;--muted:#5b6475;--line:#d9dde5;--bg:#fff;--soft:#f5f7fa;--accent:#1f5fa8;--warn:#a33;
--ok:#1b7f4b;--amber:#a86b00}
*{box-sizing:border-box}
body{margin:0;font:15.5px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--fg);background:var(--bg)}
main{max-width:980px;margin:0 auto;padding:12px 18px 60px}main.wide{max-width:1440px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.topbar{background:#1d2330;color:#fff;padding:7px 18px;font-size:14px;display:flex;gap:14px;flex-wrap:nowrap;
align-items:center;position:relative}
.topbar a{color:#dfe6f2}
.topbar .trail{display:flex;align-items:center;gap:7px;min-width:0;flex:1 1 auto;white-space:nowrap;overflow:hidden}
.topbar .seg{display:inline-flex;align-items:center;gap:7px;min-width:0;flex:0 0 auto}
.topbar .seg.here{flex:1 1 auto}
.topbar .sep{color:#6f7a8e}.topbar .home{font-weight:800;color:#fff;letter-spacing:.02em;flex:0 0 auto}
.topbar .project{color:#fff;font-weight:600}
.topbar .experiment{background:#f0b429;color:#1d2330;font-weight:700;border-radius:4px;padding:1px 10px;
overflow:hidden;text-overflow:ellipsis}
.topbar .experiment:hover{text-decoration:none;background:#f7c948}
.topbar .here .tag{margin:0;flex:0 0 auto}
.topbar .here-title{display:block;color:#c9d2e3;overflow:hidden;text-overflow:ellipsis;min-width:0}
.topbar .links{display:flex;gap:16px;flex:0 0 auto;white-space:nowrap}.topbar .links .off{color:#6b7488;cursor:default}
.topbar .menu-button{background:none;border:1px solid #4a5468;color:#fff;border-radius:5px;font-size:16px;padding:0 9px;
cursor:pointer;flex:0 0 auto}
.topbar.folded .links{display:none}
.topbar.folded.open .links{display:flex;flex-direction:column;gap:8px;position:absolute;right:12px;top:100%;
background:#1d2330;padding:10px 16px;border-radius:0 0 8px 8px;z-index:2000;box-shadow:0 6px 18px rgba(0,0,0,.25)}
.topbar .page-tools{display:flex;gap:8px;flex:0 0 auto}.topbar .page-tools:empty{display:none}
.topbar .page-tools button{background:#2c3446;border:1px solid #4a5468;color:#fff;border-radius:5px;cursor:pointer;
display:inline-flex;align-items:center;gap:5px;font:600 13px system-ui,sans-serif;padding:2px 9px}
.topbar .page-tools button:hover{background:#1f5fa8}.topbar .page-tools .ico{width:15px;height:15px}
.topbar .kea-mark{flex:0 0 auto;display:flex}.topbar .kea-mark img{display:block;background:#f4f1e8;border-radius:5px;padding:1px}
.topbar.no-mark .kea-mark,.topbar.no-project .seg.project,.topbar.no-experiment .seg.experiment-seg{display:none}
.crumbs{font-size:13px;color:var(--muted);margin:6px 0 10px}.crumbs a{color:var(--muted)}
h1{font-size:25px;line-height:1.25;margin:6px 0 8px}h2{font-size:19px;margin:28px 0 8px;border-bottom:1px solid var(--line);padding-bottom:3px}
h3{font-size:16px;margin:20px 0 6px}
.badge{display:inline-block;font-size:12px;font-weight:600;color:#fff;background:#556;border-radius:4px;padding:1px 7px;margin-right:6px;vertical-align:middle}
.t-goal{background:#333}.t-premise{background:#6a4c93}.t-question{background:#1f77b4}.t-hypothesis{background:#9467bd}
.t-step{background:#2a7f62}.t-result{background:#8c564b}.t-conclusion{background:#c0392b}.t-decision{background:#7f7f7f}
.t-figure{background:#17818a}.t-artefact{background:#b8860b}.t-caveat{background:#d35400}
.t-term,.t-reference,.t-dataset,.t-page{background:#556}.t-resource{background:#5b6b2f}
.badge .ico,.tag .ico{width:1.05em;height:1.05em;vertical-align:-.17em;margin-right:4px}
a.tag,span.tag{display:inline-flex;align-items:center;font-size:12px;font-weight:700;color:#fff;border-radius:11px;
padding:1px 8px 1px 6px;line-height:1.45;vertical-align:baseline;white-space:nowrap;box-shadow:0 1px 0 rgba(0,0,0,.18);
text-decoration:none}
a.tag:hover{text-decoration:none;filter:brightness(1.12);box-shadow:0 1px 3px rgba(0,0,0,.3)}
a.tagline{color:var(--fg);display:inline}a.tagline:hover{text-decoration:none;background:#eef3fb}
a.tagline .tag{margin-right:6px}a.tagline .kindword{font-weight:700;margin-right:3px}a.tagline .tl-text{border-bottom:1px dotted #8a94a6}
.qhead{display:block;line-height:1.5}
.qblock{margin:6px 0 18px}.qblock .answer{margin:4px 0 6px}.qblock ul{margin:4px 0}
article h2{position:relative}
h1 .kind{display:block;font-size:15px;font-weight:700;letter-spacing:.02em;margin-bottom:2px}
h1 .kind .ico{width:15px;height:15px;vertical-align:-2px;margin-right:5px}
h1 .pills,.qhead .pills{font-size:0;margin-left:8px;vertical-align:middle;white-space:normal}
h1 .pills .pill,.qhead .pills .pill{font-size:11px;font-weight:400;margin-right:4px}
.k-goal{color:#333}.k-premise{color:#6a4c93}.k-question{color:#1f77b4}.k-hypothesis{color:#9467bd}.k-step{color:#2a7f62}
.k-result{color:#8c564b}.k-conclusion{color:#c0392b}.k-decision{color:#6b6b6b}.k-figure{color:#17818a}
.k-artefact{color:#9a7000}.k-caveat{color:#d35400}.k-term,.k-reference,.k-dataset,.k-page{color:#556}.k-resource{color:#5b6b2f}
a.fullname,span.fullname{font-weight:700;margin-right:6px;white-space:nowrap}.fullname>.ico{width:1em;height:1em;vertical-align:-.15em;margin-right:4px}
.fullname .tag{margin-left:2px}a.fullname:hover{text-decoration:none;filter:brightness(1.2)}
h1 .kind .tag .ico{width:1.05em;height:1.05em;vertical-align:-.17em;margin-right:4px}
.qblock h3{font-size:14px;margin:14px 0 4px;color:var(--fg)}
table.resource-facts th{text-align:left;padding-right:14px;color:var(--muted);font-weight:600}table.resource-facts td.missing{color:#aa3333}table.resource-facts code{word-break:break-all}
table.status-table{display:table;width:100%}table.status-table td{white-space:normal}
tr.st-good td{background:#eaf6ef}tr.st-bad td{background:#fbeceb}tr.st-mid td{background:#fdf5e6}
a.term{color:inherit;border-bottom:1px dotted #8a94a6}a.term:hover{text-decoration:none;background:#f1f3f7}
.pill{display:inline-block;font-size:11px;line-height:1.5;border:1px solid var(--line);border-radius:10px;padding:0 8px;color:var(--muted);vertical-align:middle}
.s-supported,.s-done,.s-answered,.s-current,.s-active{border-color:var(--ok);color:var(--ok)}
.s-not_supported,.s-deprecated,.s-dropped,.s-superseded{border-color:var(--warn);color:var(--warn)}
.s-exploratory,.s-in_progress,.s-planned,.s-open,.s-inconclusive,.s-assumed,.s-questioned,.s-under_review{border-color:var(--amber);color:var(--amber)}
.s-addressed{border-color:var(--ok);color:var(--ok)}
.s-frozen,.s-implement-requested,.s-implementing{border-color:#c0392b;color:#c0392b}.s-collecting{border-color:var(--accent);color:var(--accent)}
.stab-flux{border-color:#f0a020;color:#8a5a00;background:#fff7e6}.stab-steady{color:var(--muted)}
.stab-settled{border-color:var(--ok);color:var(--ok);background:#eefaf2}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin:0 6px 0 2px;vertical-align:middle;background:#c5cad3}
.dot.stab-flux{background:#f0a020}.dot.stab-settled{background:#2e9e5b}
.callout{border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:6px;padding:4px 12px;margin:12px 0;background:var(--soft)}
.callout-warning,.callout-caution,.callout-caveat{border-left-color:#d35400;background:#fff6ef}
.callout-important,.callout-danger{border-left-color:var(--warn)}.callout-tip,.callout-success{border-left-color:var(--ok)}
.short{background:var(--soft);border-left:4px solid var(--accent);padding:8px 12px;margin:8px 0 16px;font-size:15px}
blockquote{margin:12px 0;padding:10px 14px;background:#fff8f0;border:1px solid #f0d9bf;border-radius:6px}
table{border-collapse:collapse;margin:10px 0;font-size:13.5px;display:block;overflow-x:auto;max-width:100%}
th,td{border:1px solid var(--line);padding:3px 8px;text-align:left;vertical-align:top;white-space:nowrap}
article td{white-space:normal}th{background:var(--soft)}
code{font-size:13px;background:var(--soft);padding:0 3px;border-radius:3px;overflow-wrap:anywhere}
main{overflow-wrap:break-word}
pre{background:var(--soft);padding:10px;overflow-x:auto;font-size:12.5px;line-height:1.45}
a.ref{border-bottom:1px dotted var(--accent)}a.ref:hover{text-decoration:none;background:#eef3fb}
.ref-missing{color:var(--muted);border-bottom:1px dashed var(--muted);cursor:help}
.ref-broken{color:#fff;background:var(--warn);padding:0 3px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:10px;margin:8px 0}
.card{border:1px solid var(--line);border-radius:8px;padding:9px 12px;background:#fff}
.card .ct{font-weight:600;font-size:14.5px;line-height:1.35}.card .cs{font-size:13.5px;color:var(--muted);margin-top:4px}
.rel{font-size:14px}.rel dt{font-weight:600;margin-top:6px}.rel dd{margin:2px 0 2px 16px}
.box{border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:14px 0;background:var(--soft);font-size:14px}
.help{color:var(--muted);font-size:13px}
figure{margin:12px 0}figure img{max-width:100%;border:1px solid var(--line);border-radius:4px;background:#fff}
figcaption{font-size:13.5px;color:#333;margin-top:6px}
.thumb{display:grid;grid-template-columns:minmax(0,300px) 1fr;gap:14px;align-items:start;margin:12px 0;
padding-bottom:10px;border-bottom:1px solid var(--line)}
.thumb img{width:100%;border:1px solid var(--line);border-radius:4px}.thumb figcaption{margin-top:4px}
details.tree summary{cursor:pointer}details.tree{margin-left:14px}ul.tree{list-style:none;padding-left:14px;margin:2px 0}
.diff .add{color:#116329;background:#e6ffec;display:block}.diff .del{color:#82071e;background:#ffebe9;display:block}
.diff .hunk{color:#6e7781;display:block}.diff .ctx{display:block}
.code-table td.linenos{color:#9aa1ad;text-align:right;user-select:none;padding-right:8px}
.code-table pre{margin:0;background:none;padding:0}.code-wrap{overflow-x:auto;background:var(--soft);padding:8px;border-radius:6px}
.code-table{border:0;display:table}.code-table td{border:0;padding:0 6px}
.hll{background:#fff3b0}
@media (max-width:640px){main{padding:10px 14px 50px}.thumb{grid-template-columns:1fr}h1{font-size:21px}}
"""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def prefix_for(page: str) -> str:
    """Relative prefix from a page path (relative to the site root) back to the root."""
    return "../" * page.count("/")


def node_href(node: Node, prefix: str) -> str:
    return f"{prefix}{node.url}"


def type_badge(node: Node) -> str:
    """The page type in full, not a link: the word in the type's colour, then the tag (icon and number)."""
    return f"<span class='fullname k-{esc(node.type)}'>{fullname_inner(node)}</span>"


def fullname_inner(node: Node) -> str:
    """'Question' as coloured text followed by the tag [icon Q1]: the tag always looks the same, with or without
    the word in front. Pages without a number show the word and the icon."""
    word = esc(TYPE_LABELS.get(node.type, node.type))
    if node.number:
        return f"{word} <span class='tag t-{esc(node.type)}'>{icons.svg(node.type)}{esc(node.number)}</span>"
    return f"{icons.svg(node.type)}{word}"


def status_pill(node: Node) -> str:
    if not node.status:
        return ""
    return f"<span class='pill s-{esc(node.status)}'>{esc(str(node.status).replace('_', ' '))}</span>"


def hover_text(node: Node, note: str | None = None) -> str:
    hover = f"{node.number + ' · ' if node.number else ''}{node.title} — {node.short}"
    return hover + (f" | {note}" if note else "")


def tag_inner(node: Node, from_project: str | None = None) -> str:
    project_part = f"{node.project}: " if from_project and node.project != from_project else ""
    return f"{icons.svg(node.type)}{esc(project_part + (node.number or node.title))}"


def node_link(node: Node, prefix: str, text: str | None = None, note: str | None = None,
              from_project: str | None = None) -> str:
    """A link to a node; the hover shows number, title and short (plus an optional note).

    Link rules (the same everywhere): a numbered page is linked by its tag (a coloured button with the type's icon
    and the number, Q1, C2). Text given with the link ([[id|text]]) stays plain text, followed by the tag; only
    the tag is the link. Pages without a number (terms, references, the experiment home) are linked by their text.
    """
    if node.number:
        anchor = (f"<a class='tag t-{esc(node.type)}' href='{esc(node_href(node, prefix))}' "
                  f"title='{esc(hover_text(node, note))}'>{tag_inner(node, from_project)}</a>")
        return f"{esc(text)} {anchor}" if text else anchor
    project_part = f"{node.project}: " if from_project and node.project != from_project else ""
    label = text if text else f"{project_part}{node.title}"
    return f"<a class='ref' href='{esc(node_href(node, prefix))}' title='{esc(hover_text(node, note))}'>{esc(label)}</a>"


def full_kind(node: Node) -> str:
    """'Question Q1': the page's kind and number in full."""
    return f"{TYPE_LABELS.get(node.type, node.type)}{' ' + node.number if node.number else ''}"


def fullname_link(node: Node, prefix: str) -> str:
    """'Question Q1' in the type's colour, as a link (headings of question blocks)."""
    return (f"<a class='fullname k-{esc(node.type)}' href='{esc(node_href(node, prefix))}' "
            f"title='{esc(hover_text(node))}'>{fullname_inner(node)}</a>")


GOOD_STATUSES = {"supported", "done", "answered", "current", "active", "addressed"}
BAD_STATUSES = {"not_supported", "deprecated", "dropped", "superseded"}


def status_row_class(node: Node) -> str:
    """Row tint for tables of pages: green supported/settled, red rejected, amber open or exploratory."""
    status = str(node.status or "")
    return "st-good" if status in GOOD_STATUSES else "st-bad" if status in BAD_STATUSES else "st-mid" if status else ""


def tagline(node: Node, prefix: str, text: str | None = None, from_project: str | None = None,
            full: bool = False) -> str:
    """Tag plus one line (the title by default) as ONE link: for lists of pages. `full` writes the kind in front of
    the tag, in its colour ("Conclusion [C1]"); the tag itself always holds the icon and the number only."""
    words = node.title if text is None else text
    if not node.number:
        return node_link(node, prefix, words, from_project=from_project)
    kind = (f"<span class='kindword k-{esc(node.type)}'>{esc(TYPE_LABELS.get(node.type, node.type))}</span> "
            if full else "")
    return (f"<a class='tagline' href='{esc(node_href(node, prefix))}' title='{esc(hover_text(node))}'>{kind}"
            f"<span class='tag t-{esc(node.type)}'>{tag_inner(node, from_project)}</span>"
            f"<span class='tl-text'>{esc(words)}</span></a>")


def card(node: Node, prefix: str) -> str:
    return (f"<div class='card'><div class='ct'>{tagline(node, prefix)} {status_pill(node)}</div>"
            f"<div class='cs'>{esc(node.short)}</div></div>")


PDF: dict | None = None          # the PDF of all pages ({"file", "version", "commit", "built"}), set by the build


def topbar(prefix: str, project: str | None = None, tree: Tree | None = None, node: Node | None = None,
           here: str | None = None) -> str:
    """Menu bar. Left: "Kea" (home) / project / experiment / [tag] page title. Right: the menu, the page tools
    (filled in by the comment script: edit) and the kea logo (help). When space runs out (TOPBAR_JS), in this
    order: the menu folds into a menu button, the logo goes, the project name goes, the experiment goes, and
    finally the page title is cut from the right; the page title is what stays longest."""
    segments = [f"<a class='home' href='{prefix}index.html' title='Home of this site'>Kea</a>",
                f"<span class='seg project'><span class='sep'>/</span><a class='project' href='{prefix}index.html'>"
                f"{esc(SITE_TITLE)}</a></span>"]
    right = []
    if project and tree and project in tree.projects:
        home = tree.projects[project]
        segments.append(f"<span class='seg experiment-seg'><span class='sep'>/</span><a class='experiment' "
                        f"href='{prefix}{project}/home.html' title='{esc(home.title)}'>{esc(project)}</a></span>")
        if node is not None and node.id != "home":
            badge = (f"<span class='tag t-{esc(node.type)}'>{tag_inner(node)}</span>" if node.number else
                     f"<span class='tag t-{esc(node.type)}'>{icons.svg(node.type)}"
                     f"{esc(TYPE_LABELS.get(node.type, node.type))}</span>")
            segments.append(f"<span class='seg here'><span class='sep'>/</span>{badge}"
                            f"<span class='here-title' title='{esc(node.title)}'>{esc(node.title)}</span></span>")
    if here:
        segments.append(f"<span class='seg here'><span class='sep'>/</span><span class='here-title'>{esc(here)}</span></span>")
    # Map and Relations always hold their place, so the menu does not shift between pages: they open the current
    # experiment's, the only experiment's on a site with one, and are greyed out otherwise.
    experiments = list(tree.projects) if tree else []
    target = project if project and tree and project in tree.projects else (experiments[0] if len(experiments) == 1
                                                                            else None)
    for label, file in (("Map", "map.html"), ("Relations", "relations.html")):
        right.append(f"<a href='{prefix}{target}/{file}'>{label}</a>" if target else
                     f"<span class='off' title='Open an experiment first: each has its own {label.lower()}'>{label}</span>")
    from kea.docsite import mode
    if mode.MODE == "public":
        right += ([f"<a href='{prefix}changes/index.html'>What changed</a>"] if mode.WITH_CHANGELOG else []) + [
            f"<a href='{prefix}data.html'>Data</a>", f"<a href='{prefix}code/index.html'>Code</a>"]
    else:
        right += [f"<a href='{prefix}plan.html'>Plan</a>", f"<a href='{prefix}history.html'>History</a>",
                  f"<a href='{prefix}changes/index.html'>What changed</a>", f"<a href='{prefix}data.html'>Data</a>",
                  f"<a href='{prefix}feedback.html'>Comments</a>", f"<a href='{prefix}code/index.html'>Code</a>"]
    if PDF:
        right.append(f"<a href='{prefix}{esc(PDF['file'])}' title='All pages as one PDF: version "
                     f"{esc(PDF['version'])}, commit {esc(PDF['commit'])}, made {esc(PDF['built'])}'>PDF</a>")
    right.append(f"<a href='{prefix}help.html'>Help</a>")
    return (f"<nav class='topbar not-annotatable'><div class='trail'>{''.join(segments)}</div>"
            f"<button class='menu-button' aria-label='menu' hidden>&#9776;</button>"
            f"<div class='links'>{''.join(right)}</div><span class='page-tools'></span>"
            f"<a class='kea-mark' href='{prefix}help.html' title='Help: how to read this site, and about Kea'>"
            f"<img src='{prefix}_assets/kea-icon-64.png' alt='Kea' width='22' height='22'></a>"
            f"</nav><script>{TOPBAR_JS}</script>")


# Fold in steps until the page title has room: 1 menu into the button, 2 logo, 3 project, 4 experiment; the title
# is then cut with an ellipsis. A title counts as cramped when it is cut and narrower than ROOM pixels (so a very
# long title on a wide screen does not fold everything); pages without a title fold when the trail overflows.
TOPBAR_JS = """(function(){var nav=document.currentScript.previousElementSibling;var button=nav.querySelector('.menu-button');
var STEPS=['folded','no-mark','no-project','no-experiment'];var ROOM=[520,380,380,380];
function cramped(step){var trail=nav.querySelector('.trail');var title=nav.querySelector('.here-title');
if(title){return title.scrollWidth>title.clientWidth+1&&title.clientWidth<ROOM[Math.min(step,3)];}
return trail.scrollWidth>trail.clientWidth+1;}
function fit(){nav.classList.remove('open');STEPS.forEach(function(name){nav.classList.remove(name);});button.hidden=true;
var links=nav.querySelector('.links');var step=0;
while(step<STEPS.length&&(cramped(step)||(step===0&&links.scrollWidth>links.clientWidth+1))){
nav.classList.add(STEPS[step]);if(step===0){button.hidden=false;}step++;}}
button.addEventListener('click',function(){nav.classList.toggle('open');});
window.addEventListener('resize',fit);if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',fit);}else{fit();}
window.keaFitTopbar=fit;})();"""


def crumbs(trail: list[tuple[str, str | None]], prefix: str) -> str:
    """Breadcrumbs; every trail starts at Start (the site home)."""
    parts = [f"<a href='{prefix}index.html'>Start</a>"]
    for text, href in trail:
        parts.append(f"<a href='{esc(href)}'>{esc(text)}</a>" if href else esc(text))
    return f"<nav class='crumbs not-annotatable'>{' › '.join(parts)}</nav>"


def page(title: str, body: str, prefix: str, project: str | None = None, tree: Tree | None = None,
         node: Node | None = None, here: str | None = None, wide: bool = False) -> str:
    """A whole HTML page. ``wide``: a wider column for tables and grids (history, commit diffs)."""
    main = "<main class='wide'>" if wide else "<main>"
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(title)}</title>"
            f"<link rel='icon' href='{prefix}_assets/favicon.ico'>"
            f"<style>{CSS}</style></head><body>{topbar(prefix, project, tree, node, here)}{main}{body}</main></body></html>")


class LinkContext:
    """What link rendering needs: the tree, the current project and page prefix, code and data resolvers."""

    def __init__(self, tree: Tree, project: str, prefix: str, code_href, data_href, current: str | None = None):
        self.tree, self.project, self.prefix = tree, project, prefix
        self.code_href, self.data_href = code_href, data_href
        self.current = current                 # key of the page being rendered (no term links to itself)
        self.broken: list[str] = []
        self.linked_terms: set[str] = set()    # terms already linked on this page (first use only)
        self.terms = term_patterns(tree, project)

    def replace(self, match: re.Match) -> str:
        target, text, note = (group.strip() if group else None for group in match.groups())
        if target.startswith("code:"):
            href = self.code_href(target[5:], self.prefix)
            label = text or target[5:].replace("#", " → ")
            if href is None:
                self.broken.append(target)
                return f"<span class='ref-broken' title='code not found'>{esc(label)}</span>"
            return f"<a class='ref' href='{esc(href)}' title='{esc(note or target[5:])}'><code>{esc(label)}</code></a>"
        if target.startswith("data:"):
            href, label = self.data_href(target[5:], self.prefix)
            return (f"<a class='ref' href='{esc(href)}'><code>{esc(text or label)}</code></a>" if href
                    else f"<code>{esc(text or target[5:])}</code>")
        node = self.tree.resolve(target, self.project)
        if node is None and RUN_ID.fullmatch(target) and (DOC / "_changes" / f"{target}.md").exists():
            from kea.docsite import mode        # a run entry ([[2026-11-05-a]]): its change-log page
            if mode.WITH_CHANGELOG:
                return (f"<a class='ref' href='{esc(self.prefix)}changes/{esc(target)}.html' "
                        f"title='{esc(note or 'run ' + target)}'>{esc(text or 'run ' + target)}</a>")
            return f"<code>{esc(text or target)}</code>"
        if node is None:
            project = target.split(":", 1)[0] if ":" in target else self.project
            if project not in self.tree.projects:
                return (f"<span class='ref-missing' title='{esc(project)} has no pages yet'>"
                        f"{esc(text or target)}</span>")
            self.broken.append(target)
            return f"<span class='ref-broken' title='unknown page'>{esc(text or target)}</span>"
        return node_link(node, self.prefix, text, note, from_project=self.project)


def term_patterns(tree: Tree, project: str) -> list[tuple[re.Pattern, Node]]:
    """(pattern, term node) for every title and alias of the experiment's term pages, longest first."""
    entries = []
    for node in tree.nodes.values():
        if node.type != "term" or node.project != project:
            continue
        names = [node.title] + [str(alias) for alias in node.header.get("aliases") or []]
        every = str(node.header.get("link") or "first").strip().lower() == "every"
        for name in names:      # link: every matches the case as written, so a gene APP does not link "app"
            entries.append((len(name), re.compile(r"(?<![\w-])(" + re.escape(name) + r")(?![\w-])",
                                                  0 if every else re.IGNORECASE), node))
    return [(pattern, node) for _, pattern, node in sorted(entries, key=lambda entry: -entry[0])]


def link_terms(html_text: str, context: LinkContext) -> str:
    """Link the first use of each term on the page (outside links, code, headings and tables); a term with
    ``link: every`` in its front matter (gene names, say) is linked at every use."""
    if not context.terms:
        return html_text
    tokens = re.split(r"(<[^>]+>)", html_text)
    skip_depth = 0
    for index, token in enumerate(tokens):
        if token.startswith("<"):
            match = re.match(r"<(/?)([a-zA-Z0-9]+)", token)
            if match and match.group(2).lower() in SKIP_AUTOLINK_TAGS and not token.endswith("/>"):
                skip_depth += -1 if match.group(1) else 1
                skip_depth = max(skip_depth, 0)
            continue
        if skip_depth or not token.strip():
            continue
        pieces: list[tuple[str, bool]] = [(token, False)]     # (text, already a link)
        for pattern, node in context.terms:
            every = str(node.header.get("link") or "first").strip().lower() == "every"
            if node.key == context.current or (node.key in context.linked_terms and not every):
                continue
            anchor_start = (f"<a class='term' href='{esc(node_href(node, context.prefix))}' "
                            f"title='{esc(node.title)}: {esc(node.short)}'>")
            position = 0
            while position < len(pieces):
                text, is_link = pieces[position]
                found = None if is_link else pattern.search(text)
                if not found:
                    position += 1
                    continue
                pieces[position:position + 1] = [(text[:found.start()], False),
                                                  (anchor_start + found.group(1) + "</a>", True),
                                                  (text[found.end():], False)]
                if not every:
                    context.linked_terms.add(node.key)
                    break
                position += 2                                    # go on in the text after this link
        tokens[index] = "".join(text for text, _ in pieces)
    return "".join(tokens)


CALLOUT_START = re.compile(r"^>\s*\[!(\w+)\][+-]?\s*(.*)$")


def callouts(text: str) -> str:
    """Obsidian / GitHub callouts (``> [!warning] Title`` followed by ``> body``) to boxes."""
    lines, output, index = text.split("\n"), [], 0
    while index < len(lines):
        match = CALLOUT_START.match(lines[index])
        if not match:
            output.append(lines[index])
            index += 1
            continue
        kind, title = match.group(1).lower(), match.group(2).strip()
        body = []
        index += 1
        while index < len(lines) and lines[index].startswith(">"):
            body.append(lines[index][1:].removeprefix(" "))
            index += 1
        heading = f"**{title or kind.capitalize()}**"
        output += ["", f"<div class='callout callout-{kind}' markdown='1'>", "", heading, ""] + body + ["", "</div>", ""]
    return "\n".join(output)


HEADING_LINK = re.compile(r"^(#{2,6})[ \t]+\[\[([^\]|]+)\]\][ \t]*:?[ \t]*$", re.M)
TAGLINE_ITEM = re.compile(r"<li><a class='tag (t-[\w-]+)' href='([^']*)' title='([^']*)'>(.*?)</a>"
                          r"((?:(?!</?(?:a|ul|ol|li|p)\b)[^<]|<(?!/?(?:a|ul|ol|li|p)\b)[^>]*>)*)</li>")
TAGLINE_MAX = 220      # characters of text after the tag: longer items are summaries, where only the tag links


def heading_links(text: str, context: LinkContext) -> str:
    """A heading that is only a link (``### [[q-x]]``) shows the tag and the page's title."""
    def expand(match: re.Match) -> str:
        node = context.tree.resolve(match.group(2).strip(), context.project)
        if node is None:
            return match.group(0)
        return f"{match.group(1)} [[{match.group(2).strip()}]] {esc(node.title)}"
    return HEADING_LINK.sub(expand, text)


def tagline_items(html_text: str) -> str:
    """List items made of a tag and one line ("- [[r-x]] what it shows") become one link, tag and text."""
    def join(match: re.Match) -> str:
        type_class, href, title, inner, rest = match.groups()
        plain = re.sub(r"<[^>]+>", "", rest)
        if not plain.strip() or len(plain) > TAGLINE_MAX:
            return match.group(0)
        rest = re.sub(r"^\s*(?:[:\u2014\u2013-]\s*)?", "", rest)
        return (f"<li><a class='tagline' href='{href}' title='{title}'><span class='tag {type_class}'>{inner}</span>"
                f"<span class='tl-text'>{rest}</span></a></li>")
    return TAGLINE_ITEM.sub(join, html_text)


LIST_ITEM = re.compile(r"^ {0,3}(?:[-*+]|\d{1,3}[.)])\s+\S")
FENCE = re.compile(r"^ {0,3}(```|~~~)")


def separate_lists(text: str) -> str:
    """Insert a blank line before a list that directly follows a paragraph line (Markdown would otherwise run the
    list into the sentence: "three checks: - one - two"). Code fences and lines inside a list are left alone."""
    output, in_fence, in_list, previous = [], False, False, ""
    for line in text.split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            if LIST_ITEM.match(line):
                if previous.strip() and not in_list and not previous.lstrip().startswith(("|", "#", ">", "<")):
                    output.append("")
                in_list = True
            elif line.strip() and not line.startswith((" ", "\t")) and not previous.strip():
                in_list = False          # a new paragraph after a blank line ends the list
        output.append(line)
        previous = line
    return "\n".join(output)


def render_markdown(text: str, context: LinkContext) -> str:
    """Markdown to HTML with [[links]] resolved and the first use of each term linked to its page.
    Links inside `code spans` are left alone. Link rules: see node_link and tagline_items."""
    text = heading_links(separate_lists(text), context)
    pieces = re.split(r"(`[^`\n]*`)", text)
    linked = "".join(piece if piece.startswith("`") else LINK_PATTERN.sub(context.replace, piece) for piece in pieces)
    html_text = markdown.markdown(callouts(linked), extensions=["tables", "fenced_code", "sane_lists", "md_in_html"])
    return link_terms(tagline_items(html_text), context)
