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
from kea.docsite.nodes import LINK_PATTERN, TYPE_LABELS, Node, Tree

SITE_TITLE = SETTINGS["title"]     # the project (kea.yaml); its parts (doc/<folder>/) are experiments
SKIP_AUTOLINK_TAGS = {"a", "code", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "table", "script", "style"}

CSS = """
:root{--fg:#1d2330;--muted:#5b6475;--line:#d9dde5;--bg:#fff;--soft:#f5f7fa;--accent:#1f5fa8;--warn:#a33;
--ok:#1b7f4b;--amber:#a86b00}
*{box-sizing:border-box}
body{margin:0;font:15.5px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--fg);background:var(--bg)}
main{max-width:980px;margin:0 auto;padding:12px 18px 60px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.topbar{background:#1d2330;color:#fff;padding:7px 18px;font-size:14px;display:flex;gap:16px;flex-wrap:wrap;align-items:center}
.topbar a{color:#dfe6f2}.topbar .brand{font-weight:600;color:#fff}
.topbar .experiment{background:#f0b429;color:#1d2330;font-weight:700;border-radius:4px;padding:1px 10px}
.topbar .experiment:hover{text-decoration:none;background:#f7c948}.topbar .kind{color:#9aa6ba;font-size:12px;margin-right:-10px}
.topbar .spacer{margin-left:auto}.topbar .kea-mark img{display:block;background:#f4f1e8;border-radius:5px;padding:1px}
.crumbs{font-size:13px;color:var(--muted);margin:6px 0 10px}.crumbs a{color:var(--muted)}
h1{font-size:25px;line-height:1.25;margin:6px 0 8px}h2{font-size:19px;margin:28px 0 8px;border-bottom:1px solid var(--line);padding-bottom:3px}
h3{font-size:16px;margin:20px 0 6px}
.badge{display:inline-block;font-size:12px;font-weight:600;color:#fff;background:#556;border-radius:4px;padding:1px 7px;margin-right:6px;vertical-align:middle}
.t-goal{background:#333}.t-premise{background:#6a4c93}.t-question{background:#1f77b4}.t-hypothesis{background:#9467bd}
.t-step{background:#2a7f62}.t-result{background:#8c564b}.t-conclusion{background:#c0392b}.t-decision{background:#7f7f7f}
.t-figure{background:#17818a}.t-artefact{background:#b8860b}.t-caveat{background:#d35400}
.t-term,.t-reference,.t-dataset,.t-page{background:#556}
a.term{color:inherit;border-bottom:1px dotted #8a94a6}a.term:hover{text-decoration:none;background:#f1f3f7}
.pill{display:inline-block;font-size:12px;border:1px solid var(--line);border-radius:10px;padding:0 8px;color:var(--muted);vertical-align:middle}
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
.diff .hunk{color:#6e7781;display:block}
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
    label = TYPE_LABELS.get(node.type, node.type)
    number = f" {node.number}" if node.number else ""
    return f"<span class='badge t-{esc(node.type)}'>{esc(label)}{esc(number)}</span>"


def status_pill(node: Node) -> str:
    if not node.status:
        return ""
    return f"<span class='pill s-{esc(node.status)}'>{esc(str(node.status).replace('_', ' '))}</span>"


def node_link(node: Node, prefix: str, text: str | None = None, note: str | None = None,
              from_project: str | None = None) -> str:
    """A link to a node; the hover shows number, title and short (plus an optional note)."""
    project_part = f"{node.project}: " if from_project and node.project != from_project else ""
    label = text if text else f"{project_part}{node.number or node.title}"
    hover = f"{node.number + ' · ' if node.number else ''}{node.title} — {node.short}"
    if note:
        hover += f" | {note}"
    return f"<a class='ref' href='{esc(node_href(node, prefix))}' title='{esc(hover)}'>{esc(label)}</a>"


def card(node: Node, prefix: str) -> str:
    return (f"<div class='card'><div class='ct'>{type_badge(node)}{status_pill(node)} "
            f"<a href='{esc(node_href(node, prefix))}'>{esc(node.title)}</a></div>"
            f"<div class='cs'>{esc(node.short)}</div></div>")


def topbar(prefix: str, project: str | None = None, tree: Tree | None = None) -> str:
    """Site name and, inside an experiment, its name as a highlighted label; navigation on the right."""
    items = [f"<a class='brand' href='{prefix}index.html'>{esc(SITE_TITLE)}</a>"]
    right = []
    if project and tree and project in tree.projects:
        items.append(f"<span class='kind'>experiment</span><a class='experiment' href='{prefix}{project}/home.html' "
                     f"title='{esc(tree.projects[project].title)}'>{esc(project)}</a>")
        right += [f"<a href='{prefix}{project}/map.html'>Map</a>",
                  f"<a href='{prefix}{project}/relations.html'>Relations</a>"]
    from kea.docsite import mode
    if mode.MODE == "public":
        right += ([f"<a href='{prefix}changes/index.html'>What changed</a>"] if mode.WITH_CHANGELOG else []) + [
            f"<a href='{prefix}data.html'>Data</a>", f"<a href='{prefix}code/index.html'>Code</a>"]
    else:
        right += [f"<a href='{prefix}plan.html'>Plan</a>", f"<a href='{prefix}history.html'>History</a>",
                  f"<a href='{prefix}changes/index.html'>What changed</a>", f"<a href='{prefix}data.html'>Data</a>",
                  f"<a href='{prefix}feedback.html'>Comments</a>", f"<a href='{prefix}code/index.html'>Code</a>"]
    right[0] = right[0].replace("<a ", "<a class='spacer' ", 1)
    right.append(f"<span class='kea-mark' title='Built with kea (Knowledge, Evidence, Argument)'>"
                 f"<img src='{prefix}_assets/kea-icon-64.png' alt='kea' width='22' height='22'></span>")
    return f"<nav class='topbar not-annotatable'>{''.join(items + right)}</nav>"


def crumbs(trail: list[tuple[str, str | None]], prefix: str) -> str:
    """Breadcrumbs; every trail starts at Start (the site home)."""
    parts = [f"<a href='{prefix}index.html'>Start</a>"]
    for text, href in trail:
        parts.append(f"<a href='{esc(href)}'>{esc(text)}</a>" if href else esc(text))
    return f"<nav class='crumbs not-annotatable'>{' › '.join(parts)}</nav>"


def page(title: str, body: str, prefix: str, project: str | None = None, tree: Tree | None = None) -> str:
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(title)}</title>"
            f"<link rel='icon' href='{prefix}_assets/favicon.ico'>"
            f"<style>{CSS}</style></head><body>{topbar(prefix, project, tree)}<main>{body}</main></body></html>")


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
        for name in names:
            entries.append((len(name), re.compile(r"(?<![\w-])(" + re.escape(name) + r")(?![\w-])", re.IGNORECASE),
                            node))
    return [(pattern, node) for _, pattern, node in sorted(entries, key=lambda entry: -entry[0])]


def link_terms(html_text: str, context: LinkContext) -> str:
    """Link the first use of each term on the page (outside links, code, headings and tables)."""
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
            if node.key in context.linked_terms or node.key == context.current:
                continue
            for position, (text, is_link) in enumerate(pieces):
                if is_link:
                    continue
                found = pattern.search(text)
                if not found:
                    continue
                anchor = (f"<a class='term' href='{esc(node_href(node, context.prefix))}' "
                          f"title='{esc(node.title)}: {esc(node.short)}'>{found.group(1)}</a>")
                pieces[position:position + 1] = [(text[:found.start()], False), (anchor, True),
                                                  (text[found.end():], False)]
                context.linked_terms.add(node.key)
                break
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


def render_markdown(text: str, context: LinkContext) -> str:
    """Markdown to HTML with [[links]] resolved and the first use of each term linked to its page.
    Links inside `code spans` are left alone."""
    pieces = re.split(r"(`[^`\n]*`)", text)
    linked = "".join(piece if piece.startswith("`") else LINK_PATTERN.sub(context.replace, piece) for piece in pieces)
    return link_terms(markdown.markdown(callouts(linked), extensions=["tables", "fenced_code", "sane_lists",
                                                                     "md_in_html"]), context)
