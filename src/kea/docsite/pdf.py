"""One PDF of the whole documentation tree, typeset with Typst (`kea pdf`, and `kea build` puts it into the site).

The PDF tells each experiment as a story for a reader who is not on the site (a biologist reading on paper):

    At a glance      the experiment's summary and every conclusion's summary, with page numbers
    Key terms        the glossary's one-line definitions
    Background       the experiment's home page text
    Starting points  premises
    Methods          steps in order, each followed by the decisions taken in it
    one part per question
                     the question, its hypotheses as a table (claim, written before its test or after results,
                     outcome, tested by), then the results that answer it or test its hypotheses, each followed by
                     the figures that show it
    Conclusions, Caveats, Other pages (anything not placed above)
    Appendix         hypotheses in full (their tests and expectations as written), data files and figure files
                     (provenance), glossary, references (without abstracts)

At the end a standard chapter "About this document" explains the page types (with the site's colours), numbers,
statuses, page references and what is left out. Every link to a page carries its page number. Left out: comments,
plans, review history, change log, code listings, the relations graph and previews of data tables (so no donor-level
rows reach the PDF). In figure pages, paragraphs that only point to the caption file (``caption_file``) are dropped;
in reference pages the "Abstract" section is dropped. A figure page may set ``pdf_width: 100%`` (or e.g. ``12cm``)
to override the automatic size.

Typst is optional: without the `typst` command (or kea.yaml `typst: <path>`) the .typ source is still written and
`kea pdf` says how to get Typst. Page bodies are rendered to HTML as on the site and converted to Typst markup
here; no other dependency.

Usage: kea pdf [--out FILE.pdf] [--typ-only]
Input: doc/**, figure images and captions, artefact files (size), git tags.
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
from kea.docsite import artefacts
from kea.docsite.nodes import PROJECT_ROOT, TYPE_LABELS, TYPE_PLURALS, Node, Tree, load_tree
from kea.docsite.render import LinkContext, render_markdown

SENTINEL = "kea-pdf:/"                    # link prefix that marks a link to a page of the tree
APPENDIX_TYPES = {"term": "Glossary", "reference": "References"}
TYPE_COLOURS = {"goal": "#333333", "premise": "#6a4c93", "question": "#1f77b4", "hypothesis": "#9467bd",
                "step": "#2a7f62", "result": "#8c564b", "conclusion": "#c0392b", "decision": "#7f7f7f",
                "figure": "#17818a", "artefact": "#b8860b", "caveat": "#d35400", "term": "#555566",
                "reference": "#555566", "dataset": "#555566", "page": "#555566"}
TYPE_MEANINGS = {
    "goal": "the experiment: what it asks and what it found",
    "premise": "what is taken as given, with the reason",
    "question": "what the experiment asks",
    "hypothesis": "an expected answer, with its test and yardstick, ideally written before the test was run",
    "decision": "a choice of method, with the reason and the alternatives",
    "step": "what was done (a script or a run)",
    "result": "what a file shows: numbers with their test",
    "conclusion": "what we make of the results, always with the evidence and its limits",
    "caveat": "what limits a result or conclusion",
    "figure": "a figure with its full caption",
    "artefact": "a data file made by a step (listed in the appendix)",
    "term": "a glossary entry",
    "reference": "a paper or resource the pages rely on",
}
STATUS_COLOURS = {**{name: "#1b7f4b" for name in ("supported", "done", "answered", "current", "active", "addressed")},
                  **{name: "#aa3333" for name in ("not_supported", "deprecated", "dropped", "superseded")},
                  **{name: "#a86b00" for name in ("exploratory", "in_progress", "planned", "open", "inconclusive",
                                                  "assumed", "questioned")}}
STATUS_MEANINGS = {
    "supported": "the evidence agrees with the claim", "not_supported": "the evidence does not agree with it",
    "inconclusive": "the test could not decide", "exploratory": "the analysis was chosen after earlier results "
    "were seen: a lead to confirm in new data, not a confirmed finding", "done": "finished",
    "answered": "a question with an answer", "open": "still open", "assumed": "taken as given, not tested here",
    "questioned": "a premise in doubt", "active": "a decision in force", "superseded": "replaced by a later page",
    "deprecated": "no longer valid, kept for the record", "current": "the current version of a file", "addressed": "a caveat that a later step dealt with",
    "planned": "not done yet", "in_progress": "under way", "dropped": "abandoned",
}
CALLOUT_COLOURS = {"warning": "#d35400", "caution": "#d35400", "caveat": "#d35400", "important": "#aa3333",
                   "danger": "#aa3333", "tip": "#1b7f4b", "success": "#1b7f4b"}
MAX_FIGURE_HEIGHT_CM = 11.0             # a tall figure is narrowed so that it does not fill a whole page
TEXT_WIDTH_CM = 16.6
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
ZWSP = "\u200b"


def text(value: str, breakable: bool = False) -> str:
    """Plain text as Typst markup (every markup character escaped, whitespace collapsed). ``breakable`` allows line
    breaks after _ and / (long identifiers in narrow table columns)."""
    escaped = MARKUP_SPECIALS.sub(r"\\\1", re.sub(r"\s+", " ", str(value)))
    escaped = re.sub(r"(\d)\.", r"\1\\.", escaped)          # '1.' at a line start would start a numbered list
    return re.sub(r"(\\[_/])", r"\1" + ZWSP, escaped) if breakable else escaped


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


def drop_section(markdown_text: str, heading: str) -> str:
    """The Markdown without the section titled ``heading`` (any level; up to the next heading of that level or
    higher)."""
    lines, output, skipping_level = markdown_text.split("\n"), [], 0
    for line in lines:
        match = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if match:
            level = len(match.group(1))
            if skipping_level and level <= skipping_level:
                skipping_level = 0
            if not skipping_level and match.group(2).strip().lower() == heading.lower():
                skipping_level = level
                continue
        if not skipping_level:
            output.append(line)
    return "\n".join(output)


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
    """HTML (as rendered for the site) to Typst markup. ``urls`` maps page paths (node.url) to node keys. Links to
    pages become ``#nlink`` (with the page number), glossary links ``#tlink`` (preamble)."""

    def __init__(self, urls: dict[str, str], heading_level: int = 3):
        self.urls, self.heading_level = urls, heading_level
        self.in_table = 0

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
            return f"#heading(level: {max(level, 3)}, outlined: false)[{self.inlines(element.children).strip()}]"
        if tag in ("ul", "ol"):
            items = [child for child in element.children if isinstance(child, Element) and child.tag == "li"]
            body = ", ".join(f"[{self.blocks(item.children)}]" for item in items)
            if tag == "ol":
                start = element.attrs.get("start")
                return f"#enum({'start: ' + start + ', ' if start and start.isdigit() else ''}{body})"
            return f"#list({body})"
        if tag == "blockquote":
            return f"#claim[{self.blocks(element.children)}]"
        if tag == "div" and "callout" in css:
            kind = next((name.removeprefix("callout-") for name in css.split() if name.startswith("callout-")), "")
            colour = CALLOUT_COLOURS.get(kind, "#1f5fa8")
            return (f"#block(stroke: (left: 3pt + rgb(\"{colour}\")), fill: rgb(\"{colour}\").lighten(92%), "
                    f"inset: 8pt, radius: (right: 3pt), width: 100%)[{self.blocks(element.children)}]")
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
        self.in_table += 1
        try:
            def padded(cells: list[Element]) -> list[str]:
                return [f"[{self.blocks(cell.children)}]" for cell in cells] + ["[]"] * (width - len(cells))
            header_rows = [cells for is_header, cells in rows if is_header] if rows[0][0] else []
            body_rows = [cells for is_header, cells in rows if not is_header] if rows[0][0] else [c for _, c in rows]
            parts = (["table.header(" + ", ".join(cell for cells in header_rows for cell in padded(cells)) + ")"]
                     if header_rows else [])
            parts += [cell for cells in body_rows for cell in padded(cells)]
        finally:
            self.in_table -= 1
        return f"#datatable({width}, {size}, {1 if header_rows else 0}, " + ", ".join(parts) + ")"

    def inlines(self, children: list) -> str:
        return "".join(self.inline(child) for child in children)

    def inline(self, node) -> str:
        if isinstance(node, str):
            return text(node, breakable=bool(self.in_table))
        tag = node.tag
        if tag in ("strong", "b"):
            return f"#strong[{self.inlines(node.children)}]"
        if tag in ("em", "i"):
            return f"#emph[{self.inlines(node.children)}]"
        if tag == "code":
            if self.in_table:         # raw text cannot break; tables need it to
                return f"#mono[{text(node.text_content(), breakable=True)}]"
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
                if not key:
                    return inner
                return f"#tlink({label(key)})[{inner}]" if "term" in node.attrs.get("class", "").split() \
                    else f"#nlink({label(key)})[{inner}]"
            if href.startswith(("http://", "https://", "mailto:")):
                return f"#link({string(href)})[{inner}]"
            return inner
        if tag in BLOCK_TAGS:            # a block inside inline content (rare): keep its text
            return " " + self.blocks(node.children) + " "
        if tag in ("script", "style", "button"):
            return ""
        return self.inlines(node.children)


# ---------------------------------------------------------------------------------------------- document
PREAMBLE = r"""#let ink = rgb("#1d2330")
#let accent = rgb("#1f5fa8")
#let amber = rgb("#f0b429")
#let muted = luma(105)
#let sans = SANS_FONTS
#set document(title: TITLE, date: auto)
#set text(font: ("Libertinus Serif", "New Computer Modern"), size: 10pt, lang: "en")
#set par(justify: true, leading: 0.62em, spacing: 0.95em)
#set heading(numbering: none)
#set page(paper: "a4", margin: (x: 2.2cm, top: 2.5cm, bottom: 2.2cm),
  header: context {
    if counter(page).get().first() > 1 {
      let here-page = here().page()
      let on-page = query(heading.where(level: 1)).filter(it => it.location().page() == here-page)
      let before = query(selector(heading.where(level: 1)).before(here()))
      let current = if on-page.len() > 0 { on-page.first().body } else if before.len() > 0 { before.last().body }
      set text(font: sans, size: 7.5pt, fill: muted)
      [TITLE_MARKUP #h(1fr) #current]
      v(-4pt); line(length: 100%, stroke: 0.4pt + luma(210))
    }
  },
  footer: context {
    if counter(page).get().first() > 1 {
      set text(font: sans, size: 7.5pt, fill: muted)
      [VERSION_MARKUP #h(1fr) #counter(page).display()]
    }
  })
#show heading: set text(font: sans, fill: ink)
#show heading.where(level: 1): set text(size: 19pt, fill: white)
#show heading.where(level: 2): it => block(sticky: true, above: 1.6em, below: 0.7em, {
  set text(size: 14pt, fill: accent); it.body; v(-6pt); line(length: 100%, stroke: 0.8pt + accent.lighten(55%)) })
#show heading.where(level: 3): set text(size: 11.5pt)
#show heading.where(level: 4): set text(size: 10.5pt)
#show heading.where(level: 5): set text(size: 10pt)
#show link: set text(fill: accent)
#show raw.where(block: false): it => box(fill: luma(242), inset: (x: 2pt), outset: (y: 2pt), radius: 2pt, text(size: 0.88em, it))
#show outline.entry.where(level: 1): set text(font: sans, weight: "bold")
#let mono(body) = text(font: "DejaVu Sans Mono", size: 0.86em, body)
#let pageref(target) = context {
  let there = locate(target).page()
  if there != here().page() { text(size: 0.72em, fill: muted)[#h(1.5pt)p.#counter(page).at(target).first()] }
}
#let nlink(target, body) = { link(target, body); pageref(target) }
#let tlink(target, body) = link(target, underline(stroke: (paint: luma(150), thickness: 0.5pt, dash: "dotted"), offset: 2pt, text(fill: ink, body)))
#let badge(colour, body) = box(fill: rgb(colour), inset: (x: 4.5pt, y: 2.2pt), outset: (y: 0.5pt), radius: 2.5pt, text(font: sans, fill: white, size: 7.5pt, weight: "bold", body))
#let pill(colour, body) = box(stroke: 0.6pt + rgb(colour), fill: rgb(colour).lighten(92%), inset: (x: 4.5pt, y: 1.8pt), outset: (y: 0.5pt), radius: 7pt, text(font: sans, size: 7.5pt, fill: rgb(colour).darken(10%), body))
#let summary(colour, body) = block(fill: rgb(colour).lighten(91%), inset: (x: 9pt, y: 7pt), radius: 3pt, width: 100%, below: 0.9em, text(size: 9.6pt, body))
#let claim(body) = block(fill: rgb("#fff8f0"), stroke: 0.5pt + rgb("#f0d9bf"), inset: 9pt, radius: 4pt, width: 100%, body)
#let meta(body) = block(above: 0.7em, text(font: sans, size: 7.8pt, fill: muted, body))
#let intro(body) = block(sticky: true, above: 0.4em, below: 0.8em, text(font: sans, size: 7.8pt, fill: muted, body))
#let node(colour, body) = block(breakable: false, stroke: (left: 3pt + rgb(colour)), inset: (left: 9pt, top: 1pt, bottom: 1pt), above: 1.5em, below: 0.6em, body)
#let datatable(columns, size, header-rows, ..cells) = block(width: 100%, {
  set text(size: size); set par(justify: false, leading: 0.45em)
  show table.cell: it => if it.y < header-rows { strong(it) } else { it }
  table(columns: columns, inset: (x: 4pt, y: 3pt), stroke: 0.4pt + luma(200), align: left,
    fill: (_, row) => if row < header-rows { luma(234) } else if calc.odd(row - header-rows) { luma(248) },
    ..cells)
})
#let chapter(name, body) = { pagebreak(weak: true); block(fill: ink, inset: (x: 14pt, y: 12pt), radius: 4pt, width: 100%, below: 1.2em, {
  if name != none { box(fill: amber, inset: (x: 6pt, y: 2.5pt), radius: 3pt, text(font: sans, size: 9pt, weight: "bold", fill: ink, name)); v(2pt) }
  body }) }
#let card(colour, head, body) = block(breakable: false, width: 100%, stroke: (left: 3pt + rgb(colour)), fill: rgb(colour).lighten(94%), inset: (x: 9pt, y: 7pt), radius: (right: 3pt), below: 0.6em, { head; v(1pt); text(size: 9.5pt, body) })
"""


SANS_PREFERENCE = ("Lato", "Source Sans 3", "Source Sans Pro", "Open Sans", "Liberation Sans", "Arial", "Helvetica",
                   "DejaVu Sans")


def sans_fonts() -> str:
    """Typst array of the preferred sans-serif fonts that Typst finds here (unknown names would print warnings);
    Typst's own fonts are the fallback."""
    command = typst_command()
    available: set[str] = set()
    if command:
        try:
            listing = subprocess.run([command, "fonts"], capture_output=True, text=True, timeout=30).stdout
            available = {line.strip().lower() for line in listing.splitlines()}
        except (OSError, subprocess.SubprocessError):
            pass
    chosen = [name for name in SANS_PREFERENCE if name.lower() in available] or ["Libertinus Serif"]
    return "(" + ", ".join(string(name) for name in chosen) + ",)"


def status_pill(status: str | None) -> str:
    if not status:
        return ""
    return f"#pill({string(STATUS_COLOURS.get(str(status), '#666677'))})[{text(str(status).replace('_', ' '))}]"


def type_badge(node: Node) -> str:
    return (f"#badge({string(TYPE_COLOURS.get(node.type, '#555566'))})[{text(TYPE_LABELS.get(node.type, node.type))}"
            f"{' ' + text(node.number) if node.number else ''}]")


def written_pill(node: Node) -> str:
    """Whether a hypothesis (or other page) was written before its test. The text says "before its test", not
    "before the results": a hypothesis added after earlier results but before its own test is not pre-registered."""
    if node.header.get("fixed_before_results") is True:
        return f"#pill(\"#1b7f4b\")[written before its test]"
    if node.header.get("fixed_before_results") is False:
        return f"#pill(\"#a86b00\")[written after results]"
    return ""


class PdfWriter:
    def __init__(self, tree: Tree):
        self.tree = tree
        self.urls = {node.url: node.key for node in tree.nodes.values()}
        self.artefact_by_path = {str(node.header.get("path", "")).rstrip("/"): node
                                 for node in tree.nodes.values() if node.type == "artefact"}
        self.placed: set[str] = set()

    # ------------------------------------------------------------------ helpers
    def markdown(self, node: Node, source: str, level: int) -> str:
        context = LinkContext(self.tree, node.project, SENTINEL, lambda target, prefix: None,
                              self.data_href, node.key)
        return Converter(self.urls, heading_level=level).convert(render_markdown(source, context))

    def data_href(self, target: str, prefix: str) -> tuple[str | None, str]:
        node = self.artefact_by_path.get(target.rstrip("/"))
        return (f"{prefix}{node.url}", f"{node.number} {target}") if node else (None, target)

    def link(self, node: Node) -> str:
        return f"#nlink({label(node.key)})[{text(node.number or node.title)}]"

    def links(self, keys: list[str]) -> str:
        return ", ".join(self.link(self.tree.nodes[key]) for key in keys if key in self.tree.nodes)

    def of_type(self, project: str, node_type: str) -> list[Node]:
        return sorted((node for node in self.tree.nodes.values() if node.project == project and node.type == node_type),
                      key=lambda node: (len(node.number), node.number, node.order, node.id))

    def body(self, node: Node, level: int) -> str:
        source = node.body
        if node.type == "figure":
            image_name = Path(str(node.header.get("image", ""))).name
            paragraphs = [paragraph for paragraph in re.split(r"\n\s*\n", source)
                          if "caption_file" not in paragraph
                          and not (paragraph.strip().startswith("![") and image_name and image_name in paragraph)]
            source = "\n\n".join(paragraphs)
        if node.type == "reference":
            source = drop_section(source, "Abstract")
        return self.markdown(node, source, level + 1) if source.strip() else ""

    def head(self, node: Node, level: int, extra: str = "") -> str:
        """The heading block: stripe in the type's colour, heading with label, badge and pills, summary."""
        heading = f"{node.number} {node.title}" if node.number else node.title
        colour = TYPE_COLOURS.get(node.type, "#555566")
        pills = " ".join(part for part in (type_badge(node), status_pill(node.status), written_pill(node), extra) if part)
        return (f"#node({string(colour)})[\n{'=' * level} {text(heading)} {label(node.key)}\n\n{pills}\n\n"
                f"#summary({string(colour)})[{text(node.short)}]]")

    def section(self, node: Node, level: int) -> str:
        """One page of the tree as a section (heading block, figure, body, a few connection lines)."""
        self.placed.add(node.key)
        parts = [self.head(node, level)]
        if node.type == "figure":
            parts.append(self.figure(node, level))
        parts.append(self.body(node, level))
        lines = []
        data = [self.artefact_by_path[path] for path in self.source_paths(node) if path in self.artefact_by_path]
        if data:
            lines.append(f"#strong[Data:] {', '.join(self.link(item) for item in data)}")
        if node.type == "hypothesis" and node.incoming.get("Tested by"):
            lines.append(f"#strong[Tested by:] {self.links(node.incoming['Tested by'])}")
        if node.incoming.get("Limited by"):
            lines.append(f"#strong[Limited by:] {self.links(node.incoming['Limited by'])}")
        if node.type == "caveat" and node.relations.get("limits"):
            lines.append(f"#strong[Limits:] {self.links(node.relations['limits'])}")
        if lines:
            parts.append(f"#meta[{' #h(0.6em)·#h(0.6em) '.join(lines)}]")
        return "\n\n".join(part for part in parts if part.strip())

    @staticmethod
    def source_paths(node: Node) -> list[str]:
        paths = []
        for entry in node.header.get("sources") or []:
            for kind, value in (entry.items() if isinstance(entry, dict) else [("data", entry)]):
                if kind == "data":
                    paths.append(str(value).split("#")[0].strip().rstrip("/"))
        return paths

    def figure(self, node: Node, level: int) -> str:
        image = str(node.header.get("image", ""))
        if not image or not (PROJECT_ROOT / image).is_file():
            return f"#emph[Figure image missing: {text(image)}]"
        width = str(node.header.get("pdf_width") or figure_width(PROJECT_ROOT / image))
        if not re.fullmatch(r"\d+(\.\d+)?(cm|mm|%)", width):
            width = "100%"
        parts = [f"#align(center, image({string('/' + image)}, width: {width}))"]
        caption_file = node.header.get("caption_file")
        if caption_file and (PROJECT_ROOT / caption_file).is_file():
            caption = "\n".join(line for line in (PROJECT_ROOT / caption_file).read_text().splitlines()
                                if not line.startswith(("# ", "- source table:", "- script:", "- commit:")))
            parts.append(f"#block(inset: (x: 4pt), above: 0.8em)[#set text(size: 9pt)\n"
                         f"{self.markdown(node, caption.strip(), level + 1)}]")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------ chapter parts
    def question_of(self, hypothesis: Node) -> str | None:
        parent = self.tree.nodes.get(f"{hypothesis.project}:{hypothesis.parent}") if hypothesis.parent else None
        if parent and parent.type == "question":
            return parent.key
        answers = hypothesis.relations.get("answers") or []
        return answers[0] if answers else None

    def hypothesis_table(self, hypotheses: list[Node]) -> str:
        cells = []
        for hypothesis in hypotheses:
            written = ("before its test" if hypothesis.header.get("fixed_before_results") is True else
                       "after results" if hypothesis.header.get("fixed_before_results") is False else "")
            cells += [f"[{self.link(hypothesis)}]", f"[{text(hypothesis.short)}]", f"[{text(written)}]",
                      f"[{status_pill(hypothesis.status)}]", f"[{self.links(hypothesis.incoming.get('Tested by', []))}]"]
        header = ["[Hypothesis]", "[Expected (in short)]", "[Written]", "[Outcome]", "[Tested by]"]
        return (f"#block(width: 100%)[#set text(size: 8.5pt); #set par(justify: false)\n"
                f"#table(columns: (auto, 1fr, auto, auto, auto), inset: (x: 4pt, y: 4pt), stroke: 0.4pt + luma(205), "
                f"align: (left, left, left, left, left), fill: (_, row) => if row == 0 {{ rgb(\"#9467bd\").lighten(85%) }}, "
                f"table.header(..({', '.join(header)}).map(strong)), {', '.join(cells)})]\n\n"
                f"#meta[The full text of each hypothesis (its test, its yardstick and what was expected) is in the "
                f"appendix; the results below test them.]")

    def results_with_figures(self, results: list[Node], level: int) -> list[str]:
        parts = []
        for result in results:
            if result.key in self.placed:
                continue
            parts.append(self.section(result, level))
            figures = [self.tree.nodes[key] for key in result.relations.get("shown_in", []) if key in self.tree.nodes]
            figures += [child for child in self.tree.children(result) if child.type == "figure"]
            for figure in figures:
                if figure.key not in self.placed:
                    parts.append(self.section(figure, level + 1))
        return parts

    def at_a_glance(self, project: str, home: Node) -> list[str]:
        parts = ["== At a glance", f"#summary(\"#333333\")[{text(home.short)}]"]
        conclusions = self.of_type(project, "conclusion")
        if conclusions:
            parts.append("#intro[What the experiment concludes. Each conclusion lists its evidence and its limits on "
                         "the page given.]")
            for conclusion in conclusions:
                parts.append(f"#card({string(TYPE_COLOURS['conclusion'])}, [{type_badge(conclusion)} "
                             f"{status_pill(conclusion.status)} #h(4pt) #strong[{text(conclusion.title)}] "
                             f"{'#h(1fr) ' + self.link(conclusion)}], [{text(conclusion.short)}])")
        caveats = [caveat for caveat in self.of_type(project, "caveat") if caveat.status != "addressed"]
        if caveats:
            parts.append("#meta[Open caveats: " + ", ".join(f"{self.link(caveat)} {text(caveat.title)}"
                                                            for caveat in caveats) + "]")
        terms = self.of_type(project, "term")
        if terms:
            entries = ", ".join(f"[#strong[{text(term.title)}]: {text(term.short)}]"
                                for term in sorted(terms, key=lambda term: term.title.lower()))
            parts += ["== Key terms",
                      "#intro[Short definitions; the glossary in the appendix has the full entries.]",
                      f"#block[#set text(size: 8.6pt); #set par(justify: false)\n"
                      f"#grid(columns: (1fr, 1fr), column-gutter: 14pt, row-gutter: 7pt, {entries})]"]
        return parts

    def chapter(self, project: str) -> str:
        from kea.docsite import versions
        home = self.tree.projects[project]
        self.placed.add(home.key)
        own = versions.releases(project)
        pills = " ".join(part for part in ([f"#pill(\"#f0b429\")[{text(own[-1].label)}]"] if own else []) +
                         [status_pill(home.status)] if part)
        parts = [f"#chapter({string(project)})[\n= {text(home.title)} {label(home.key)}\n]",
                 pills.replace("#pill(", "#pill(") if pills else ""]
        parts += self.at_a_glance(project, home)
        if home.body.strip():
            parts += ["== Background", self.markdown(home, home.body, 3)]
        premises = self.of_type(project, "premise")
        if premises:
            parts += ["== Starting points",
                      "#intro[What the analysis takes as given, and why.]"] + [self.section(node, 3) for node in premises]
        steps, decisions = self.of_type(project, "step"), self.of_type(project, "decision")
        if steps or decisions:
            parts += ["== Methods", "#intro[What was done, in order; each step is followed by the method decisions "
                                    "taken in it (what was chosen, why, and the alternatives).]"]
            for step in steps:
                parts.append(self.section(step, 3))
                for key in step.relations.get("decided_in", []):
                    decision = self.tree.nodes.get(key)
                    if decision and decision.key not in self.placed:
                        parts.append(self.section(decision, 4))
            for decision in decisions:
                if decision.key not in self.placed:
                    parts.append(self.section(decision, 3))
        hypotheses = self.of_type(project, "hypothesis")
        results = self.of_type(project, "result")
        for question in self.of_type(project, "question"):
            parts.append(self.head(question, 2))
            self.placed.add(question.key)
            parts.append(self.body(question, 2))
            own_hypotheses = [hypothesis for hypothesis in hypotheses if self.question_of(hypothesis) == question.key]
            if own_hypotheses:
                parts.append(self.hypothesis_table(own_hypotheses))
            hypothesis_keys = {hypothesis.key for hypothesis in own_hypotheses}
            answering = [result for result in results
                         if question.key in result.relations.get("answers", [])
                         or hypothesis_keys & set(result.relations.get("tests", []))]
            parts += self.results_with_figures(answering, 3)
        leftover_results = [result for result in results if result.key not in self.placed]
        if leftover_results:
            parts += ["== Other results"] + self.results_with_figures(leftover_results, 3)
        conclusions = self.of_type(project, "conclusion")
        if conclusions:
            parts += ["== Conclusions"] + [self.section(node, 3) for node in conclusions]
        caveats = self.of_type(project, "caveat")
        if caveats:
            parts += ["== Caveats", "#intro[What limits the results and conclusions above.]"] + \
                     [self.section(node, 3) for node in caveats]
        excluded = {"hypothesis", "artefact", "term", "reference"}
        others = sorted((node for node in self.tree.nodes.values() if node.project == project
                         and node.key not in self.placed and node.type not in excluded),
                        key=lambda node: (node.type, node.number, node.id))
        if others:
            parts += ["== Other pages"] + [self.section(node, 3) for node in others]
        parts += self.appendix(project, hypotheses)
        return "\n\n".join(part for part in parts if part.strip())

    def appendix(self, project: str, hypotheses: list[Node]) -> list[str]:
        parts = []
        if hypotheses:
            parts += [f"== Appendix: hypotheses in full",
                      "#intro[As written, with the test and the expectation. Whether each was written before its test "
                      "is shown on its pill.]"] + [self.section(node, 3) for node in hypotheses]
        data = self.of_type(project, "artefact")
        if data:
            cells = []
            for item in data:
                path = PROJECT_ROOT / str(item.header.get("path", ""))
                size = artefacts.human_size(path.stat().st_size) if path.is_file() else "missing" if not path.exists() else "folder"
                made_by = self.tree.nodes.get(f"{project}:{item.parent}") if item.parent else None
                cells += [f"[#text(fill: rgb(\"#b8860b\"), weight: \"bold\")[{text(item.number)}] {label(item.key)}]",
                          f"[{text(item.title)}]",
                          f"[#mono[{text(str(item.header.get('path', '')), breakable=True)}]]",
                          f"[{text(str(item.header.get('format', '')))}]", f"[{text(size)}]",
                          f"[{self.link(made_by) if made_by else ''}]"]
                self.placed.add(item.key)
            parts += ["== Appendix: data files",
                      "#intro[Files made by the steps, as paths in the project folder. Their contents are not printed "
                      "here (they may hold controlled-access, donor-level data).]",
                      f"#datatable(6, 7.5pt, 1, table.header([File], [What it holds], [Path], [Format], [Size], [Made by]), "
                      + ", ".join(cells) + ")"]
        figures = [node for node in self.of_type(project, "figure") if node.header.get("image")]
        if figures:
            cells = []
            for figure in figures:
                cells += [f"[{self.link(figure)}]",
                          f"[#mono[{text(str(figure.header.get('image', '')), breakable=True)}]]",
                          f"[#mono[{text(str(figure.header.get('script', '')), breakable=True)}]]",
                          f"[#mono[{text(str(figure.header.get('table', '')), breakable=True)}]]"]
            parts += ["== Appendix: figure files",
                      "#intro[Each figure is made by a script from a saved table; the image, script and table are "
                      "kept in the project folder.]",
                      f"#datatable(4, 7.5pt, 1, table.header([Figure], [Image], [Script], [Table]), " + ", ".join(cells) + ")"]
        for node_type, heading in APPENDIX_TYPES.items():
            members = sorted(self.of_type(project, node_type), key=lambda node: node.title.lower())
            if members:
                parts.append(f"== {text(heading)}")
                for member in members:
                    self.placed.add(member.key)
                    entry = [f"=== {text(member.title)} {label(member.key)}", f"#emph[{text(member.short)}]",
                             self.body(member, 3)]
                    parts.append("\n\n".join(part for part in entry if part))
        return parts

    # ------------------------------------------------------------------ whole document
    def about(self, version: str, commit: str, today: str) -> str:
        used_types = [node_type for node_type in TYPE_MEANINGS
                      if any(node.type == node_type for node in self.tree.nodes.values())]
        type_rows = ", ".join(f"[#badge({string(TYPE_COLOURS[node_type])})[{text(TYPE_LABELS[node_type])}]], "
                              f"[{text(TYPE_MEANINGS[node_type])}]" for node_type in used_types)
        used_statuses = sorted({str(node.status) for node in self.tree.nodes.values() if node.status},
                               key=lambda status: (STATUS_COLOURS.get(status, "z"), status))
        status_rows = ", ".join(f"[{status_pill(status)}], [{text(STATUS_MEANINGS.get(status, ''))}]"
                                for status in used_statuses)
        prefixes = sorted({(node.number[:1], node.type) for node in self.tree.nodes.values()
                           if node.number and node.number[:1].isalpha()})
        numbering = ", ".join(f"{prefix} = {TYPE_LABELS.get(node_type, node_type).lower()}" for prefix, node_type in prefixes)
        return f"""#chapter(none)[
= About this document <kea-about>
]

== What this document is

This is a printed copy of the project's documentation site, made by Kea on {text(today)} from site version
{text(version)} (commit #raw({string(commit)})). The site is the working record of the analysis: every claim sits on
its own small page, linked to the evidence behind it. This document holds the same pages, ordered as a story. The
site and this document are written from the same source files, so they say the same thing; when the site has moved
on, the site is the newer one.

== How each chapter is ordered

Each experiment is one chapter: #emph[At a glance] (the conclusions in one line each), #emph[Key terms],
#emph[Background], #emph[Starting points] (premises), #emph[Methods] (steps and the decisions taken in them), then
one part per #emph[question]: the question, a table of its hypotheses, and the results that answer it, each followed
by its figures. #emph[Conclusions] and #emph[Caveats] close the chapter. The appendix holds the hypotheses in full,
the data and figure files, the glossary and the references. To read quickly: At a glance, then the conclusions; to
check a claim, follow its evidence.

== Kinds of page

Every page has a coloured badge that says what kind of page it is; the same colours mark the stripe beside its
heading.

#block[#set par(justify: false)
#grid(columns: (auto, 1fr), column-gutter: 10pt, row-gutter: 6pt, {type_rows})]

== Numbers, links and page references

Pages are numbered per experiment and kind ({text(numbering)}); the numbers are the same as on the site. A link
such as #text(fill: accent)[R3]#text(size: 0.72em, fill: muted)[#h(1.5pt)p.12] leads to that page, and the small
number gives the page of this document (left out when it is the same page). #tlink(<kea-about>)[Words with a dotted
underline] are glossary terms: the link leads to their definition.

== Status

#block[#set par(justify: false)
#grid(columns: (auto, 1fr), column-gutter: 10pt, row-gutter: 6pt, {status_rows})]

A hypothesis also says when it was written. #pill("#1b7f4b")[written before its test]: the claim, the test and
the expectation were fixed before that test was run, though possibly after other results of the same experiment
had been seen. #pill("#a86b00")[written after results]: it was written with its result already known, so it
describes rather than predicts. An analysis marked #emph[exploratory] suggests; it needs new data to confirm.

== What is left out

The comments of readers, the review plans and the history of the pages (all on the site); the code (named by its
file); the relations graph; and the contents of data files, which may hold controlled-access, donor-level data.
Numbers in the text come from those files; the appendix lists them.

#meta[Made with Kea (github.com/mfiers/Kea), a tool that turns an analysis into a site of linked claims and
evidence, reviewed in cycles by readers and an AI agent.]
"""

    def document(self) -> str:
        from kea.docsite import comments, versions
        title = str(SETTINGS.get("title") or PROJECT_ROOT.name)
        heading = str(SETTINGS.get("heading") or "")
        releases = versions.releases("")
        version = releases[-1].label if releases else "unreleased"
        commit = comments.source_version(None)
        today = dt.date.today().isoformat()
        chapters = [self.chapter(project) for project in sorted(self.tree.projects)]
        self.content = "\n\n".join(chapters)            # what the site cache keys on (not the date or commit)
        self.stamp = {"version": version, "commit": commit, "built": today}
        experiments = "".join(
            f"#card(\"#333333\", [#box(fill: amber, inset: (x: 5pt, y: 2pt), radius: 3pt, text(font: sans, size: 8pt, "
            f"weight: \"bold\", fill: ink)[{text(project)}]) #h(4pt) #strong[{text(home.title)}] #h(1fr) "
            f"#link({label(home.key)})[page #context counter(page).at({label(home.key)}).first()]], [{text(home.short)}])\n"
            for project, home in sorted(self.tree.projects.items()))
        front = f"""#page(margin: 0pt, header: none, footer: none)[
#block(fill: ink, width: 100%, inset: (x: 2.2cm, top: 3.2cm, bottom: 1.4cm))[
  #text(font: sans, size: 30pt, weight: "bold", fill: white)[{text(title)}]
  {f'#v(4pt) #text(font: sans, size: 13pt, fill: rgb("#c9d2e3"))[{text(heading)}]' if heading and heading != title else ''}
  #v(10pt)
  #box(fill: amber, inset: (x: 7pt, y: 3pt), radius: 3pt, text(font: sans, size: 9pt, weight: "bold", fill: ink)[Site version {text(version)}])
  #h(6pt) #text(font: sans, size: 9pt, fill: rgb("#c9d2e3"))[commit {text(commit)} · {text(today)}]
]
#pad(x: 2.2cm, top: 1cm)[
  #text(font: sans, size: 12pt, weight: "bold", fill: ink)[Experiments]
  #v(4pt)
  {experiments}
  #v(10pt)
  #text(size: 9.5pt)[The whole documentation of the project, ordered for reading: for each experiment its conclusions
  first, then the methods, the questions with their results and figures, and the caveats. How to read it, and what
  the colours, numbers and labels mean: #link(<kea-about>)[About this document], page
  #context counter(page).at(<kea-about>).first().]
]]

#set page(numbering: "1")
#counter(page).update(1)
#text(font: sans, size: 19pt, weight: "bold", fill: ink)[Contents]
#v(6pt)
#outline(title: none, depth: 2, indent: auto)
"""
        preamble = (PREAMBLE.replace("SANS_FONTS", sans_fonts()).replace("TITLE_MARKUP", text(title)).replace("TITLE", string(title))
                    .replace("VERSION_MARKUP", text(f"{title} · {version} · {commit}")))
        return preamble + "\n" + front + "\n\n" + "\n\n".join(chapters) + "\n\n" + \
            self.about(version, commit, today) + "\n"


CACHE_KEEP = 6


def site_pdf(tree: Tree, site: Path) -> dict | None:
    """The PDF for a site build (`kea build`), or None when Typst is not installed or the compile fails.

    The same PDF for every build mode: it prints no data-file contents. It is compiled only when its content
    changed: compiled files are kept in report/pdf/_cache/<content hash>.pdf (the last CACHE_KEEP), so a reused PDF
    carries the version and commit of the build that compiled it. Returns {"file", "version", "commit", "built",
    "reused"}; the PDF is copied to <site>/<file>.
    """
    import hashlib
    import json
    command = typst_command()
    if command is None:
        return None
    writer = PdfWriter(tree)
    source = writer.document()
    digest = hashlib.sha256((writer.content + PREAMBLE + (writer.about("", "", ""))).encode()).hexdigest()[:16]
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
        meta_path.write_text(json.dumps(writer.stamp))
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
    parser.add_argument("--out", type=Path, default=None, help="PDF file (default: report/pdf/<title>_<date>_"
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
    writer = PdfWriter(tree)
    typ_path.parent.mkdir(parents=True, exist_ok=True)
    typ_path.write_text(writer.document(), encoding="utf-8")
    print(f"wrote {typ_path.relative_to(PROJECT_ROOT)}")
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
