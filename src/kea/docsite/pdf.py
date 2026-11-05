"""One PDF of the whole documentation tree, typeset with Typst (`kea pdf`).

Every experiment is a chapter. Its pages follow the tree in reading order (children grouped by type as on the site):
a heading with the page's number and title, a line with type and status, the one-line summary, the figure or the
artefact's file details, the body, the sources and the connections. Terms and references form a glossary and a
reference list at the end of each chapter. [[links]], term links and data links become links inside the PDF.

Left out: comments, plans, review history, change log, site pages (doc/_site/), code pages (paths are named, not
shown) and the relations graph. Rules (``--rules``):
    public    (default) as `kea build --mode public`: no previews of tables unless the artefact declares
              `access:` public or aggregate. For a PDF that may travel.
    internal  previews of every artefact table (first rows). Only for readers allowed to see the data.

Typst is optional: without the `typst` command (or kea.yaml `typst: <path>`) the .typ source is still written and
`kea pdf` says how to get Typst. Page bodies are rendered to HTML as on the site and converted to Typst markup
here; no other dependency.

Usage: kea pdf [--rules public|internal] [--out FILE.pdf] [--typ-only]
Input: doc/**, figure images and captions, artefact files (size, checksum, previews), git tags.
Output: report/pdf/<site title>_<YYYY_MM_DD>_<site version>_<commit>.pdf and the .typ beside it (never overwritten:
a suffix _2, _3 … is added); --out names the PDF instead (refused if it exists).
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import struct
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

from kea.config import SETTINGS
from kea.docsite import artefacts, mode
from kea.docsite.nodes import FORWARD_LABELS, PROJECT_ROOT, TYPE_LABELS, TYPE_PLURALS, Node, Tree, load_tree
from kea.docsite.render import LinkContext, render_markdown

SENTINEL = "kea-pdf:/"                    # link prefix that marks a link to a page of the tree
CHILD_ORDER = ["goal", "premise", "question", "hypothesis", "decision", "step", "result", "conclusion", "figure",
               "artefact", "caveat", "dataset", "page"]
APPENDIX_TYPES = {"term": "Glossary", "reference": "References"}
TYPE_COLOURS = {"goal": "#333333", "premise": "#6a4c93", "question": "#1f77b4", "hypothesis": "#9467bd",
                "step": "#2a7f62", "result": "#8c564b", "conclusion": "#c0392b", "decision": "#7f7f7f",
                "figure": "#17818a", "artefact": "#b8860b", "caveat": "#d35400"}
CALLOUT_COLOURS = {"warning": "#d35400", "caution": "#d35400", "caveat": "#d35400", "important": "#aa3333",
                   "danger": "#aa3333", "tip": "#1b7f4b", "success": "#1b7f4b"}
MAX_FIGURE_HEIGHT_CM = 10.5             # a tall figure is narrowed so that it does not fill a whole page
TEXT_WIDTH_CM = 16.6
PREVIEW_ROWS = 10
PREVIEW_COLUMNS = 8
INSTALL_HINT = ("Typst was not found. Install it (one binary, no TeX needed): https://github.com/typst/typst/releases, "
                "or `cargo install --locked typst-cli`, `brew install typst`, `conda install -c conda-forge typst`; "
                "or set `typst: /path/to/typst` in kea.yaml.")


def typst_command() -> str | None:
    """Path of the Typst binary (kea.yaml `typst:` first, then PATH), or None when Typst is not installed."""
    configured = SETTINGS.get("typst")
    if configured:
        return str(configured) if Path(str(configured)).exists() else shutil.which(str(configured))
    return shutil.which("typst")


# ---------------------------------------------------------------------------------------------- Typst escaping
MARKUP_SPECIALS = re.compile(r"([\\#*_`$<>@\[\]~=\-+/'\"])")


def text(value: str) -> str:
    """Plain text as Typst markup (every markup character escaped, whitespace collapsed)."""
    escaped = MARKUP_SPECIALS.sub(r"\\\1", re.sub(r"\s+", " ", str(value)))
    return re.sub(r"(\d)\.", r"\1\\.", escaped)          # '1.' at a line start would start a numbered list


def string(value: str) -> str:
    """A Typst string literal."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'


def label(key: str) -> str:
    return "<" + re.sub(r"[^A-Za-z0-9_.:-]", "-", key) + ">"


def figure_width(path: Path) -> str:
    """Typst width for an image: the text width, or narrower when the image would be taller than
    MAX_FIGURE_HEIGHT_CM (PNG only; other formats get the full width)."""
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
        if header[:8] == b"\x89PNG\r\n\x1a\n":
            width, height = struct.unpack(">II", header[16:24])
            if width and height and TEXT_WIDTH_CM * height / width > MAX_FIGURE_HEIGHT_CM:
                return f"{MAX_FIGURE_HEIGHT_CM * width / height:.1f}cm"
    except OSError:
        pass
    return "100%"


# ---------------------------------------------------------------------------------------------- HTML to Typst
class Element:
    def __init__(self, tag: str, attrs: dict[str, str]):
        self.tag, self.attrs, self.children = tag, attrs, []

    def text_content(self) -> str:
        return "".join(child if isinstance(child, str) else child.text_content() for child in self.children)


VOID = {"img", "br", "hr", "meta", "input", "link", "col", "source", "wbr"}


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        element = Element(tag, {name: value or "" for name, value in attrs})
        self.stack[-1].children.append(element)
        if tag not in VOID:
            self.stack.append(element)

    def handle_endtag(self, tag):
        for depth in range(len(self.stack) - 1, 0, -1):     # tolerate unclosed tags (e.g. <p> before a <div>)
            if self.stack[depth].tag == tag:
                del self.stack[depth:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


BLOCK_TAGS = {"p", "div", "section", "article", "ul", "ol", "li", "blockquote", "pre", "table", "figure",
              "h1", "h2", "h3", "h4", "h5", "h6", "hr", "details", "dl", "dt", "dd", "figcaption"}


class Converter:
    """HTML (as rendered for the site) to Typst markup. ``urls`` maps page paths (node.url) to node keys."""

    def __init__(self, urls: dict[str, str], heading_level: int = 3):
        self.urls, self.heading_level = urls, heading_level

    def convert(self, html_text: str) -> str:
        builder = TreeBuilder()
        builder.feed(html_text)
        builder.close()
        return self.blocks(builder.root.children).strip()

    # block level: a list of children where text and inline elements are gathered into paragraphs
    def blocks(self, children: list) -> str:
        output, inline = [], []

        def flush():
            paragraph = "".join(inline).strip()
            if paragraph:
                output.append(paragraph)
            inline.clear()
        for child in children:
            if isinstance(child, Element) and child.tag in BLOCK_TAGS:
                flush()
                rendered = self.block(child)
                if rendered.strip():
                    output.append(rendered.strip())
            else:
                inline.append(self.inline(child))
        flush()
        return "\n\n".join(output)

    def block(self, element: Element) -> str:
        tag, css = element.tag, element.attrs.get("class", "")
        if tag == "p":
            return self.inlines(element.children).strip()
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = min(self.heading_level + int(tag[1]) - 2, 6)
            return f"#heading(level: {max(level, 2)}, outlined: false)[{self.inlines(element.children).strip()}]"
        if tag in ("ul", "ol"):
            items = [child for child in element.children if isinstance(child, Element) and child.tag == "li"]
            body = ", ".join(f"[{self.blocks(item.children)}]" for item in items)
            if tag == "ol":
                start = element.attrs.get("start")
                return f"#enum({'start: ' + start + ', ' if start and start.isdigit() else ''}{body})"
            return f"#list({body})"
        if tag == "blockquote":
            return (f"#block(fill: rgb(\"#fff8f0\"), stroke: 0.5pt + rgb(\"#f0d9bf\"), inset: 8pt, radius: 4pt, "
                    f"width: 100%)[{self.blocks(element.children)}]")
        if tag == "div" and "callout" in css:
            kind = next((name.removeprefix("callout-") for name in css.split() if name.startswith("callout-")), "")
            colour = CALLOUT_COLOURS.get(kind, "#1f5fa8")
            return (f"#block(stroke: (left: 3pt + rgb(\"{colour}\")), fill: luma(246), inset: 8pt, width: 100%)"
                    f"[{self.blocks(element.children)}]")
        if tag == "pre":
            return f"#block(fill: luma(246), inset: 6pt, width: 100%)[#text(size: 8pt)[#raw(block: true, " \
                   f"{string(element.text_content().rstrip())})]]"
        if tag == "table":
            return self.table(element)
        if tag == "hr":
            return "#line(length: 100%, stroke: 0.5pt + luma(200))"
        if tag == "dl":
            rows = []
            for child in element.children:
                if isinstance(child, Element) and child.tag == "dt":
                    rows.append(f"#strong[{self.inlines(child.children).strip()}]")
                elif isinstance(child, Element) and child.tag == "dd":
                    rows.append(f"#pad(left: 1em)[{self.blocks(child.children)}]")
            return "\n\n".join(rows)
        if tag == "details":         # summary first, then the rest
            return self.blocks(element.children)
        return self.blocks(element.children)

    def table(self, element: Element) -> str:
        rows: list[tuple[bool, list[Element]]] = []

        def collect(node: Element, header: bool):
            for child in node.children:
                if not isinstance(child, Element):
                    continue
                if child.tag == "tr":
                    cells = [cell for cell in child.children if isinstance(cell, Element) and cell.tag in ("td", "th")]
                    rows.append((header or all(cell.tag == "th" for cell in cells), cells))
                elif child.tag in ("thead", "tbody", "tfoot"):
                    collect(child, child.tag == "thead")
        collect(element, False)
        if not rows:
            return ""
        width = max(len(cells) for _, cells in rows)
        size = "8pt" if width <= 6 else "7pt" if width <= 9 else "6pt"
        parts = []
        header_rows = [cells for is_header, cells in rows if is_header]
        body_rows = [cells for is_header, cells in rows if not is_header]

        def cell_markup(cell: Element, bold: bool) -> str:
            content = self.blocks(cell.children)
            return f"[#strong[{content}]]" if bold else f"[{content}]"

        def padded(cells: list[Element], bold: bool) -> list[str]:
            return [cell_markup(cell, bold) for cell in cells] + ["[]"] * (width - len(cells))
        if header_rows and rows[0][0]:
            parts.append("table.header(" + ", ".join(cell for cells in header_rows for cell in padded(cells, True)) + ")")
        else:
            body_rows = [cells for _, cells in rows]
        parts += [cell for cells in body_rows for cell in padded(cells, False)]
        return (f"#block(width: 100%)[#set text(size: {size}); #set par(justify: false); "
                f"#table(columns: {width}, inset: 3pt, stroke: 0.4pt + luma(190), align: left, "
                + ", ".join(parts) + ")]")

    def inlines(self, children: list) -> str:
        return "".join(self.inline(child) for child in children)

    def inline(self, node) -> str:
        if isinstance(node, str):
            return text(node)
        tag, inner = node.tag, None
        if tag in ("strong", "b"):
            return f"#strong[{self.inlines(node.children)}]"
        if tag in ("em", "i"):
            return f"#emph[{self.inlines(node.children)}]"
        if tag == "code":
            return f"#raw({string(node.text_content())})"
        if tag == "sup":
            return f"#super[{self.inlines(node.children)}]"
        if tag == "sub":
            return f"#sub[{self.inlines(node.children)}]"
        if tag == "br":
            return " #linebreak() "
        if tag == "img":
            source = node.attrs.get("src", "")
            path = (PROJECT_ROOT / source).resolve()
            if source and path.is_file() and path.is_relative_to(PROJECT_ROOT):
                return f"#image({string('/' + str(path.relative_to(PROJECT_ROOT)))}, width: 80%)"
            return ""
        if tag == "a":
            inner = self.inlines(node.children)
            href = node.attrs.get("href", "")
            if href.startswith(SENTINEL):
                key = self.urls.get(href[len(SENTINEL):].split("#")[0])
                return f"#link({label(key)})[{inner}]" if key else inner
            if href.startswith(("http://", "https://", "mailto:")):
                return f"#link({string(href)})[{inner}]"
            return inner
        if tag in BLOCK_TAGS:            # a block inside inline content (rare): keep its text
            return " " + self.blocks(node.children) + " "
        if tag in ("script", "style", "button", "summary") and tag != "summary":
            return ""
        return self.inlines(node.children)


# ---------------------------------------------------------------------------------------------- document
PREAMBLE = """#set document(title: {title}, date: auto)
#set page(paper: "a4", margin: (x: 2.2cm, top: 2.4cm, bottom: 2.2cm), numbering: "1",
  header: context {{ if counter(page).get().first() > 1 [#set text(size: 8pt, fill: luma(120)); {title_markup} #h(1fr) {version_markup}] }})
#set text(size: 10pt, lang: "en")
#set par(justify: true, leading: 0.6em, spacing: 0.9em)
#set heading(numbering: none)
#show heading.where(level: 1): it => {{ pagebreak(weak: true); set text(size: 20pt); it; v(0.4em) }}
#show heading.where(level: 2): set text(size: 14pt)
#show heading.where(level: 3): set text(size: 12pt)
#show heading.where(level: 4): set text(size: 10.5pt)
#show link: it => if type(it.dest) == str {{ text(fill: rgb("#1f5fa8"), it) }} else {{ text(fill: rgb("#1f5fa8"), it) }}
#show raw.where(block: false): it => box(fill: luma(242), inset: (x: 2pt), outset: (y: 2pt), radius: 2pt, text(size: 0.9em, it))
#let badge(colour, body) = box(fill: rgb(colour), inset: (x: 4pt, y: 2pt), radius: 2pt, text(fill: white, size: 8pt, weight: "bold", body))
#let pill(body) = box(stroke: 0.5pt + luma(150), inset: (x: 4pt, y: 1.5pt), radius: 6pt, text(size: 8pt, fill: luma(80), body))
#let short(body) = block(fill: rgb("#f5f7fa"), stroke: (left: 3pt + rgb("#1f5fa8")), inset: 8pt, width: 100%, body)
#let meta(body) = block(text(size: 8.5pt, fill: luma(70), body))
"""


class PdfWriter:
    def __init__(self, tree: Tree, rules: str):
        self.tree, self.rules = tree, rules
        self.urls = {node.url: node.key for node in tree.nodes.values()}
        self.omitted_previews: list[str] = []

    def converter(self, level: int) -> Converter:
        return Converter(self.urls, heading_level=level)

    def markdown(self, node: Node, source: str, level: int) -> str:
        context = LinkContext(self.tree, node.project, SENTINEL, lambda target, prefix: None,
                              self.data_href, node.key)
        return self.converter(level).convert(render_markdown(source, context))

    def data_href(self, target: str, prefix: str) -> tuple[str | None, str]:
        for node in self.tree.nodes.values():
            if node.type == "artefact" and str(node.header.get("path", "")).rstrip("/") == target.rstrip("/"):
                return f"{prefix}{node.url}", f"{node.number} {target}"
        return None, target

    def link(self, node: Node) -> str:
        return f"#link({label(node.key)})[{text(node.number or node.title)}]"

    def reading_order(self, project: str) -> list[tuple[Node, int]]:
        """(node, depth) depth first from the home page; children grouped by type like the site."""
        home = self.tree.projects[project]
        ordered, seen = [], set()

        def visit(node: Node, depth: int):
            if node.key in seen:
                return
            seen.add(node.key)
            ordered.append((node, depth))
            children = [child for child in self.tree.children(node) if child.type not in APPENDIX_TYPES]
            children.sort(key=lambda child: (CHILD_ORDER.index(child.type) if child.type in CHILD_ORDER else 99,
                                             child.order, child.number, child.id))
            for child in children:
                visit(child, depth + 1)
        visit(home, 0)
        rest = sorted((node for node in self.tree.nodes.values() if node.project == project
                       and node.key not in seen and node.type not in APPENDIX_TYPES), key=lambda node: node.id)
        return ordered + [(node, 1) for node in rest]

    def section(self, node: Node, level: int) -> str:
        heading = f"{node.number} {node.title}" if node.number else node.title
        parts = [f"{'=' * level} {text(heading)} {label(node.key)}"]
        if node.type in APPENDIX_TYPES:            # glossary and reference entries: compact
            parts.append(f"#emph[{text(node.short)}]")
            if node.body.strip():
                parts.append(self.markdown(node, node.body, level + 1))
            parts.append(self.connections(node))
            return "\n\n".join(part for part in parts if part.strip())
        status = [f"#badge({string(TYPE_COLOURS.get(node.type, '#555566'))})[{text(TYPE_LABELS.get(node.type, node.type))}"
                  f"{' ' + text(node.number) if node.number else ''}]"]
        if node.status:
            status.append(f"#pill[{text(str(node.status).replace('_', ' '))}]")
        if node.header.get("fixed_before_results") is True:
            status.append("#pill[fixed before results]")
        elif node.header.get("fixed_before_results") is False:
            status.append("#pill[written after results]")
        # kept together with the heading (headings stick to the next block)
        parts.append(f"#block(breakable: false)[{' '.join(status)} #v(0.2em) #short[{text(node.short)}]]")
        if node.type == "figure":
            parts.append(self.figure(node, level))
        if node.type == "artefact":
            parts.append(self.artefact(node, level))
        body = node.body
        if node.type == "figure":       # the figure's own image embed is shown above
            image_name = Path(str(node.header.get("image", ""))).name
            body = "\n".join(line for line in body.split("\n")
                             if not (line.strip().startswith("![") and image_name and image_name in line))
        if body.strip():
            parts.append(self.markdown(node, body, level + 1))
        parts.append(self.sources(node))
        parts.append(self.connections(node))
        return "\n\n".join(part for part in parts if part.strip())

    def figure(self, node: Node, level: int) -> str:
        image = str(node.header.get("image", ""))
        if not image or not (PROJECT_ROOT / image).is_file():
            return f"#emph[Figure image missing: {text(image)}]"
        width = figure_width(PROJECT_ROOT / image)
        parts = [f"#figure(image({string('/' + image)}, width: {width}), caption: none)"]
        caption_file = node.header.get("caption_file")
        if caption_file and (PROJECT_ROOT / caption_file).is_file():
            caption = "\n".join(line for line in (PROJECT_ROOT / caption_file).read_text().splitlines()
                                if not line.startswith(("# ", "- source table:", "- script:", "- commit:")))
            parts.append(f"#block(inset: (x: 4pt))[#set text(size: 9pt)\n{self.markdown(node, caption.strip(), level + 1)}]")
        made = [f"Image: #raw({string(image)})"]
        if node.header.get("script"):
            made.append(f"script: #raw({string(node.header['script'])})")
        if node.header.get("table"):
            made.append(f"table: #raw({string(node.header['table'])})")
        parts.append(f"#meta[{' · '.join(made)}]")
        return "\n\n".join(parts)

    def artefact(self, node: Node, level: int) -> str:
        relative = str(node.header.get("path", ""))
        path = PROJECT_ROOT / relative
        if not path.exists():
            return f"#meta[File: #raw({string(relative)}) — missing on disk]"
        details = [f"File: #raw({string(relative)})", f"size {text(artefacts.human_size(path.stat().st_size))}"]
        if path.is_file():
            details.append(f"sha256 #raw({string(artefacts.sha256_of(path)[:16] + '…')})")
        if node.header.get("format"):
            details.append(f"format {text(node.header['format'])}")
        parts = [f"#meta[{' · '.join(details)}]"]
        if path.is_file() and mode.preview_allowed(node.header.get("access")):
            preview = artefacts.preview(path)
            preview = self.trim_preview(preview)
            parts.append(f"#block[#set text(size: 8.5pt)\n{self.converter(level + 1).convert(preview)}]")
        elif path.is_file():
            self.omitted_previews.append(relative)
            parts.append("#meta[#emph[Preview not shown under the public rules (the file may contain "
                         "controlled-access data).]]")
        return "\n\n".join(parts)

    @staticmethod
    def trim_preview(preview_html: str) -> str:
        """At most PREVIEW_ROWS rows and PREVIEW_COLUMNS columns of a preview table (a PDF page is narrow)."""
        rows = re.findall(r"<tr>.*?</tr>", preview_html, flags=re.S)
        if not rows:
            return preview_html
        kept = []
        for row in rows[:PREVIEW_ROWS + 1]:
            cells = re.findall(r"<t[hd]>.*?</t[hd]>", row, flags=re.S)
            extra = len(cells) - PREVIEW_COLUMNS
            cells = cells[:PREVIEW_COLUMNS] + ([f"<t{'h' if row is rows[0] else 'd'}>+{extra} more</t{'h' if row is rows[0] else 'd'}>"]
                                               if extra > 0 else [])
            kept.append("<tr>" + "".join(cells) + "</tr>")
        before = preview_html.split("<table", 1)[0]
        before = re.sub(r"[Ff]irst \d+ rows", f"first {len(kept) - 1} rows", before)
        return f"{before}<table><thead>{kept[0]}</thead><tbody>{''.join(kept[1:])}</tbody></table>"

    def sources(self, node: Node) -> str:
        items = []
        for entry in node.header.get("sources") or []:
            for kind, value in (entry.items() if isinstance(entry, dict) else [("data", entry)]):
                value = str(value)
                if kind == "data":
                    href, _ = self.data_href(value.split("#")[0].strip(), SENTINEL)
                    key = self.urls.get(href[len(SENTINEL):]) if href else None
                    shown = f"#raw({string(value.split('#')[0].strip())})"
                    items.append(f"data: {shown}" + (f" ({self.link(self.tree.nodes[key])})" if key else ""))
                else:
                    items.append(f"{text(kind)}: #raw({string(value.replace('#', ' → '))})")
        return f"#meta[#strong[Sources:] {'; '.join(items)}]" if items else ""

    def connections(self, node: Node) -> str:
        rows = []
        for relation, keys in node.relations.items():
            links = [self.link(self.tree.nodes[key]) for key in keys if key in self.tree.nodes]
            if links:
                rows.append(f"#strong[{text(FORWARD_LABELS.get(relation, relation))}:] {', '.join(links)}")
        for relation_label, keys in sorted(node.incoming.items()):
            links = [self.link(self.tree.nodes[key]) for key in keys if key in self.tree.nodes]
            if links:
                rows.append(f"#strong[{text(relation_label)}:] {', '.join(links)}")
        return f"#meta[{' · '.join(rows)}]" if rows else ""

    def chapter(self, project: str) -> str:
        from kea.docsite import versions
        home = self.tree.projects[project]
        own = versions.releases(project)
        parts = []
        for node, depth in self.reading_order(project):
            if node.id == "home":
                parts.append(f"= {text(project)}: {text(home.title)} {label(home.key)}")
                parts.append(" ".join([f"#badge({string('#333333')})[Experiment]"]
                                      + ([f"#pill[{text(own[-1].label)}]"] if own else [])
                                      + ([f"#pill[{text(str(home.status).replace('_', ' '))}]"] if home.status else [])))
                parts.append(f"#short[{text(home.short)}]")
                if home.body.strip():
                    parts.append(self.markdown(home, home.body, 2))
                parts.append(self.connections(home))
                continue
            parts.append(self.section(node, min(depth + 1, 4)))
        for node_type, heading in APPENDIX_TYPES.items():
            members = sorted((node for node in self.tree.nodes.values()
                              if node.project == project and node.type == node_type), key=lambda node: node.title.lower())
            if members:
                parts.append(f"== {text(heading)}")
                parts += [self.section(member, 4) for member in members]
        return "\n\n".join(part for part in parts if part.strip())

    def document(self) -> str:
        from kea.docsite import comments, versions
        title = str(SETTINGS.get("title") or PROJECT_ROOT.name)
        releases = versions.releases("")
        version = releases[-1].label if releases else "unreleased"
        commit = comments.source_version(None)
        today = dt.date.today().isoformat()
        chapters = [self.chapter(project) for project in sorted(self.tree.projects)]
        self.content = "\n\n".join(chapters) + f"|{self.rules}|{len(self.omitted_previews)}"   # what the cache keys on
        self.stamp = {"version": version, "commit": commit, "built": today}
        rules_note = ("Public rules: previews of data tables appear only for files declared public or aggregate."
                      if self.rules == "public" else
                      "Internal rules: previews of all data tables are included. Do not pass this PDF to readers "
                      "who may not see the data.")
        omitted = (f" Previews left out: {len(self.omitted_previews)}." if self.omitted_previews else "")
        front = [
            f"#align(center)[#v(4cm)#text(size: 26pt, weight: \"bold\")[{text(title)}]#v(0.6cm)"
            f"#text(size: 12pt, fill: luma(80))[Site version {text(version)} · commit #raw({string(commit)}) · "
            f"built {text(today)}]]",
            f"#v(1fr)#block(inset: 10pt, stroke: 0.5pt + luma(200), radius: 4pt, width: 100%)[#set text(size: 9pt)\n"
            f"This PDF holds every page of the documentation site: questions, premises, hypotheses, steps, results, "
            f"conclusions, caveats, figures, data files, terms and references, in the order of the site's tree. "
            f"Numbers such as R3 or C2 are the page numbers used on the site. It leaves out comments, review plans, "
            f"the review history, the change log, code listings and the relations graph. {text(rules_note)}"
            f"{text(omitted)} Made with Kea.]",
            "#pagebreak()",
            "#outline(depth: 2, indent: auto)",
        ]
        preamble = PREAMBLE.format(title=string(title), title_markup=text(title),
                                   version_markup=text(f"{version} · {commit}"))
        return preamble + "\n" + "\n\n".join(front + chapters) + "\n"


CACHE_KEEP = 6


def site_pdf(tree: Tree, site: Path) -> dict | None:
    """The PDF for a site build (`kea build`), or None when Typst is not installed or the compile fails.

    Rules follow the build mode set by `mode.configure`: public builds get public rules, review and local builds
    (password-protected or on disk, already showing previews) internal rules. The PDF is compiled only when its
    content changed: compiled files are kept in report/pdf/_cache/<content hash>.pdf (the last CACHE_KEEP), so a
    reused PDF carries the version and commit of the build that compiled it. Returns {"file", "version",
    "commit", "built", "rules", "reused"}; the PDF is copied to <site>/<file>.
    """
    import hashlib
    import json
    command = typst_command()
    if command is None:
        return None
    rules = "public" if mode.MODE == "public" else "internal"
    writer = PdfWriter(tree, rules)
    source = writer.document()
    digest = hashlib.sha256(writer.content.encode()).hexdigest()[:16]
    cache = PROJECT_ROOT / "report" / "pdf" / "_cache"
    cache.mkdir(parents=True, exist_ok=True)
    cached, meta_path = cache / f"{digest}.pdf", cache / f"{digest}.json"
    reused = cached.exists() and meta_path.exists()
    if not reused:
        typ_path = cache / f"{digest}.typ"
        typ_path.write_text(source, encoding="utf-8")
        result = subprocess.run([command, "compile", "--root", str(PROJECT_ROOT), str(typ_path), str(cached)],
                                capture_output=True, text=True)
        if result.returncode != 0:
            print(f"note    PDF not built (typst failed; source {typ_path.relative_to(PROJECT_ROOT)}):\n"
                  f"{result.stderr.strip()[:2000]}", file=sys.stderr)
            return None
        meta_path.write_text(json.dumps({**writer.stamp, "rules": rules}))
        for old in sorted(cache.glob("*.pdf"), key=lambda path: path.stat().st_mtime)[:-CACHE_KEEP]:
            for suffix in (".pdf", ".json", ".typ"):
                old.with_suffix(suffix).unlink(missing_ok=True)
    meta = json.loads(meta_path.read_text())
    title = re.sub(r"[^a-z0-9]+", "-", str(SETTINGS.get("title") or PROJECT_ROOT.name).lower()).strip("-")
    name = f"{title}-{meta['version']}.pdf"
    shutil.copy2(cached, site / name)
    return {"file": name, **meta, "reused": reused}


def default_output() -> Path:
    from kea.docsite import comments, versions
    releases = versions.releases("")
    version = releases[-1].label if releases else "unreleased"
    name = str(SETTINGS.get("title") or PROJECT_ROOT.name).lower()
    stem = f"{name}_{dt.date.today().strftime('%Y_%m_%d')}_{version}_{comments.source_version(None)}"
    stem = re.sub(r"[^A-Za-z0-9_.+-]", "-", stem)
    folder = PROJECT_ROOT / "report" / "pdf"
    candidate, counter = folder / f"{stem}.pdf", 2
    while candidate.exists() or candidate.with_suffix(".typ").exists():
        candidate, counter = folder / f"{stem}_{counter}.pdf", counter + 1
    return candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kea pdf", description=__doc__.split("\n")[0])
    parser.add_argument("--rules", choices=("public", "internal"), default="public",
                        help="public (default): previews only of tables declared public or aggregate; internal: "
                             "previews of every table")
    parser.add_argument("--out", type=Path, default=None, help="PDF file (default: report/pdf/<project>_<date>_"
                                                               "<version>_<commit>.pdf, never overwritten)")
    parser.add_argument("--typ-only", action="store_true", help="write the Typst source only, do not compile")
    args = parser.parse_args(argv)
    output = (args.out.resolve() if args.out else default_output())
    if output.exists():
        parser.error(f"{output} exists; choose another --out (files are not overwritten)")
    if output.is_relative_to(PROJECT_ROOT / "data"):
        parser.error("refusing to write into data/")
    typ_path = output.with_suffix(".typ") if output.is_relative_to(PROJECT_ROOT) else \
        PROJECT_ROOT / "report" / "pdf" / (output.stem + ".typ")
    tree = load_tree()
    for problem in tree.problems:
        print(f"PROBLEM {problem}")
    mode.configure("public" if args.rules == "public" else "local", typ_path.parent)
    writer = PdfWriter(tree, args.rules)
    typ_path.parent.mkdir(parents=True, exist_ok=True)
    typ_path.write_text(writer.document(), encoding="utf-8")
    print(f"wrote {typ_path.relative_to(PROJECT_ROOT)}")
    if writer.omitted_previews:
        print(f"previews left out (public rules): {len(writer.omitted_previews)}")
    if args.typ_only:
        return 0
    command = typst_command()
    if command is None:
        print(INSTALL_HINT, file=sys.stderr)
        return 3
    output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([command, "compile", "--root", str(PROJECT_ROOT), str(typ_path), str(output)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        print(f"typst failed; the source is {typ_path}", file=sys.stderr)
        return 1
    if result.stderr.strip():
        print(result.stderr.strip())
    print(f"wrote {output.relative_to(PROJECT_ROOT) if output.is_relative_to(PROJECT_ROOT) else output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
