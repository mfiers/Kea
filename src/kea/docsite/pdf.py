"""One PDF of the whole documentation tree, typeset with Typst (`kea pdf`, and `kea build` puts it into the site).

The PDF tells each experiment as a story for a reader who is not on the site (a biologist reading on paper):

    At a glance      the experiment's summary, every question with its answer and conclusions, open caveats
    Background       the experiment's home page text
    Starting points  premises
    one part per question
                     the question, its hypotheses as a table (claim, outcome, tested by), then the results that
                     answer it or test its hypotheses, each followed by the figures that show it
    Conclusions, Caveats, Methods (steps, each with its decisions), Other pages (anything not placed above)
    closing chapters overview of all pages (one table per kind), hypotheses in full, data and resources
                     (resources O, data files), figure files, glossary (terms T, then groups such as Genes),
                     references (numbered B in order of citation, Nature style), what changed (document)

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
from kea.docsite import artefacts, icons, questions
from kea.docsite.nodes import (PROJECT_ROOT, TYPE_LABELS, TYPE_PLURALS, Node, Tree, load_tree, natural,  # noqa: F401
                                term_group)
from kea.docsite.render import LinkContext, render_markdown

SENTINEL = "kea-pdf:/"                    # link prefix that marks a link to a page of the tree
TYPE_COLOURS = {"goal": "#333333", "premise": "#6a4c93", "question": "#1f77b4", "hypothesis": "#9467bd",
                "step": "#2a7f62", "result": "#8c564b", "conclusion": "#c0392b", "decision": "#7f7f7f",
                "figure": "#17818a", "artefact": "#b8860b", "caveat": "#d35400", "term": "#555566", "resource": "#5b6b2f",
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
    "artefact": "a data file made by a step (listed under Data and resources)",
    "resource": "what the analysis takes from outside (database, server, file), with version, date and checksum",
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
MAX_FIGURE_HEIGHT_CM = 19.0             # a taller figure is narrowed (it still leaves room for its caption)
SMALL_FIGURE_SCALE = 0.8                # printed below this share of its own size: noted in the build log
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
MARKUP_SPECIALS = re.compile(r"([\\#*_`$<>@\[\]~=\-+/'\";(])")   # ; and ( would end or continue a preceding #expr
ZWSP = "\u200b"


def text(value: str, breakable: bool = False) -> str:
    """Plain text as Typst markup (every markup character escaped, whitespace collapsed). ``breakable`` allows line
    breaks after _ and / (long identifiers in narrow table columns)."""
    escaped = MARKUP_SPECIALS.sub(r"\\\1", re.sub(r"\s+", " ", str(value)))
    escaped = re.sub(r"(\d)\.", r"\1\\.", escaped)          # '1.' at a line start would start a numbered list
    escaped = re.sub(r"^\.", r"\\.", escaped)                # '.x' after #expr would be a field access
    return re.sub(r"(\\[_/])", r"\1" + ZWSP, escaped) if breakable else escaped


def code_text(value: str) -> str:
    """Inline code as escaped text that may break after / _ . - , = (long paths in justified text)."""
    escaped = MARKUP_SPECIALS.sub(r"\\\1", re.sub(r"\s+", " ", str(value)))
    escaped = re.sub(r"(\d)\.", r"\1\\.", escaped)
    return re.sub(r"(\\[_/\-=]|[.,](?=\S))", r"\1" + ZWSP, escaped)


def string(value: str) -> str:
    """A Typst string literal."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'


def label(key: str) -> str:
    return "<" + re.sub(r"[^A-Za-z0-9_.:-]", "-", key) + ">"


def png_size(path: Path) -> tuple[int, int, float | None] | None:
    """(width px, height px, pixels per cm or None) of a PNG; None for other files."""
    try:
        data = path.open("rb").read(1 << 16)
    except OSError:
        return None
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", data[16:24])
    per_cm = None
    position = data.find(b"pHYs")
    if position > 0:
        x_per_metre, _, unit = struct.unpack(">IIB", data[position + 4:position + 13])
        if unit == 1 and x_per_metre:
            per_cm = x_per_metre / 100
    return width, height, per_cm


def figure_width(path: Path) -> tuple[str, float | None]:
    """(Typst width, scale) for an image. A PNG that records its resolution is printed at its own size (so its
    fonts keep their size), at most the text width and MAX_FIGURE_HEIGHT_CM high; scale is printed size / own size.
    Without a resolution: the text width, narrowed when it would be taller than MAX_FIGURE_HEIGHT_CM."""
    size = png_size(path)
    if not size or not size[0] or not size[1]:
        return "100%", None
    width, height, per_cm = size
    if per_cm:
        own_width, own_height = width / per_cm, height / per_cm
        scale = min(1.0, TEXT_WIDTH_CM / own_width, MAX_FIGURE_HEIGHT_CM / own_height)
        return f"{own_width * scale:.1f}cm", scale
    if TEXT_WIDTH_CM * height / width > MAX_FIGURE_HEIGHT_CM:
        return f"{MAX_FIGURE_HEIGHT_CM * width / height:.1f}cm", None
    return "100%", None


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


def section_text(markdown_text: str, heading: str) -> str:
    """The text under the section titled ``heading`` (any level), without the heading; '' when absent."""
    lines, output, level_found = markdown_text.split("\n"), [], 0
    for line in lines:
        match = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if match:
            level = len(match.group(1))
            if level_found and level <= level_found:
                break
            if not level_found and match.group(2).strip().lower() == heading.lower():
                level_found = level
                continue
        if level_found:
            output.append(line)
    return "\n".join(output).strip()


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

    def __init__(self, urls: dict[str, str], heading_level: int = 3, cite=None):
        self.urls, self.heading_level = urls, heading_level
        self.cite = cite              # key, link text -> citation markup for references (None: an ordinary link)
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
            return (f"#block(sticky: true, above: 1.3em, below: 0.7em)[#heading(level: {max(level, 3)}, outlined: false)"
                    f"[{self.inlines(element.children).strip()}]]")
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
        pieces = [self.inline(child) for child in children]
        return "".join(pieces)

    def inline(self, node) -> str:
        if isinstance(node, str):
            return text(node, breakable=bool(self.in_table))
        tag = node.tag
        if tag in ("strong", "b"):
            return f"#strong[{self.inlines(node.children)}]"
        if tag in ("em", "i"):
            return f"#emph[{self.inlines(node.children)}]"
        if tag == "code":             # not #raw: raw text cannot break, and paths stretched justified lines
            return f"#icode[{code_text(node.text_content())}]"
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
            classes = node.attrs.get("class", "").split()
            if href.startswith(SENTINEL):
                key = self.urls.get(href[len(SENTINEL):].split("#")[0])
                if not key:
                    return inner
                if self.cite:
                    cited = self.cite(key, node.text_content().strip())
                    if cited is not None:
                        return cited
                if "tag" in classes:              # the tag is the link (site's link rules)
                    kind = next((name[2:] for name in classes if name.startswith("t-")), "page")
                    return f"#nlink({label(key)})[{tag_markup(kind, node.text_content().strip())}]"
                if "tagline" in classes:          # tag and one line: the whole line is the link, page at the end
                    return f"#link({label(key)})[{inner}] #h(0.4em) #h(1fr) #pagenum({label(key)})"
                return f"#tlink({label(key)})[{inner}]" if "term" in node.attrs.get("class", "").split() \
                    else f"#nlink({label(key)})[{inner}]"
            if href.startswith(("http://", "https://", "mailto:")):
                return f"#link({string(href)})[{inner}]"
            return inner
        if tag in BLOCK_TAGS:            # a block inside inline content (rare): keep its text
            return " " + self.blocks(node.children) + " "
        if tag in ("script", "style", "button", "svg"):
            return ""
        if tag == "span" and "tag" in node.attrs.get("class", "").split():
            kind = next((name[2:] for name in node.attrs.get("class", "").split() if name.startswith("t-")), "page")
            return tag_markup(kind, node.text_content().strip()) + " "
        if tag == "span" and "kindword" in node.attrs.get("class", "").split():
            kind = next((name[2:] for name in node.attrs.get("class", "").split() if name.startswith("k-")), "page")
            return f"#kindname({string(TYPE_COLOURS.get(kind, '#555566'))})[{text(node.text_content().strip())}] "
        if tag == "span" and "tl-text" in node.attrs.get("class", "").split():
            return f"#text(fill: ink)[{self.inlines(node.children)}]"
        return self.inlines(node.children)


# ---------------------------------------------------------------------------------------------- document
PREAMBLE = r"""#let ink = rgb("#1d2330")
#let accent = rgb("#1f5fa8")
#let amber = rgb("#f0b429")
#let muted = luma(105)
#let sans = SANS_FONTS
#set document(title: TITLE, date: auto)
#set text(font: ("Libertinus Serif", "New Computer Modern"), size: 10pt, lang: "en")
#set par(justify: true, leading: 0.72em, spacing: 1.25em)
#set list(spacing: 0.9em, indent: 4pt)
#set enum(spacing: 0.9em)
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
#show heading.where(level: 2): it => block(sticky: true, above: 1.6em, below: 1em, {
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
#let tag(colour, icon, body) = box(fill: rgb(colour), inset: (x: 2.6pt), outset: (y: 1.6pt), radius: 4pt,
  text(font: sans, fill: white, size: 6.6pt, weight: "bold", top-edge: "cap-height", bottom-edge: "baseline",
    { box(height: 0.92em, baseline: 0.02em, image(bytes(icon), format: "svg")); h(1.4pt); body }))
#let kindname(colour, word) = text(font: sans, weight: "bold", fill: rgb(colour), word)
#let pagenum(target) = context {
  if locate(target).page() != here().page() { text(font: sans, size: 7pt, fill: muted)[p.#counter(page).at(target).first()] }
}
#let entry(target, head, body, status) = grid(columns: (1fr, auto), column-gutter: 0.6em,
  link(target, { head; h(0.35em); text(fill: ink, body) }),
  align(right + top, box({ status; h(3pt); pagenum(target) })))
#let icode(body) = { h(1.2pt); highlight(fill: luma(240), extent: 0.6pt, text(font: "DejaVu Sans Mono", size: 0.84em, body)); h(1.2pt) }
#let badge(colour, body) = box(fill: rgb(colour), inset: (x: 4.5pt, y: 2.2pt), outset: (y: 0.5pt), radius: 2.5pt, text(font: sans, fill: white, size: 7.5pt, weight: "bold", body))
#let pill(colour, body) = box(stroke: 0.6pt + rgb(colour), fill: rgb(colour).lighten(92%), inset: (x: 4.5pt, y: 1.8pt), outset: (y: 0.5pt), radius: 7pt, text(font: sans, size: 7.5pt, fill: rgb(colour).darken(10%), body))
#let summary(colour, body) = block(fill: rgb(colour).lighten(91%), inset: (x: 10pt, y: 8pt), radius: 3pt, width: 100%, above: 0.6em, below: 0.4em, text(size: 9.8pt, body))
#let claim(body) = block(fill: rgb("#fff8f0"), stroke: 0.5pt + rgb("#f0d9bf"), inset: 9pt, radius: 4pt, width: 100%, body)
#let meta(body) = block(above: 1em, below: 1em, text(font: sans, size: 7.8pt, fill: muted, body))
#let intro(body) = block(sticky: true, above: 1em, below: 1.2em, text(font: sans, size: 8pt, fill: muted, body))
#let node(colour, body) = block(breakable: false, sticky: true, stroke: (left: 3pt + rgb(colour)), inset: (left: 10pt, top: 3pt, bottom: 3pt), above: 2.4em, below: 1em, body)
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


def icon_bytes(kind: str) -> str:
    """The type's icon as a Typst string holding an SVG, drawn in white."""
    return string(icons.standalone(kind if kind in icons.PATHS else "page", "#ffffff"))


def tag_markup(kind: str, label_text: str) -> str:
    """A tag as on the site: the type's colour, its icon and the number (Q1, C2)."""
    return f"#tag({string(TYPE_COLOURS.get(kind, '#555566'))}, {icon_bytes(kind)})[{text(label_text)}]"


def fullname_markup(kind: str, number: str) -> str:
    """'Question' as coloured text, then the tag [icon Q1] (the tag looks the same with or without the word)."""
    colour = string(TYPE_COLOURS.get(kind, "#555566"))
    word = f"#kindname({colour})[{text(TYPE_LABELS.get(kind, kind))}]"
    return f"{word} #h(1pt){tag_markup(kind, number)}" if number else word


def type_badge(node: Node) -> str:
    return (f"#badge({string(TYPE_COLOURS.get(node.type, '#555566'))})[#box(height: 0.95em, baseline: 0.12em, "
            f"image(bytes({icon_bytes(node.type)}), format: \"svg\")) #h(1pt){text(TYPE_LABELS.get(node.type, node.type))}"
            f"{' ' + text(node.number) if node.number else ''}]")


def written_pill(node: Node) -> str:
    """Whether a hypothesis (or other page) was written before its test. The text says "before its test", not
    "before the results": a hypothesis added after earlier results but before its own test is not pre-registered."""
    if node.header.get("fixed_before_results") is True:
        return f"#pill(\"#1b7f4b\")[written before its test]"
    if node.header.get("fixed_before_results") is False:
        return f"#pill(\"#a86b00\")[written after results]"
    return ""


def term_groups(terms: list[Node]) -> list[tuple[str, list[Node]]]:
    """Terms by group (key terms first, then the other groups by name), each sorted naturally (S100A2 < S100A10)."""
    groups: dict[str, list[Node]] = {}
    for term in terms:
        groups.setdefault(term_group(term), []).append(term)
    return [(name, sorted(groups[name], key=lambda term: natural(term.title)))
            for name in sorted(groups, key=lambda name: (name != "", name.lower()))]


BREAK_BEFORE: tuple[str, ...] = ()     # questions and closing chapters start a page; other parts follow on
REFERENCE_PREFIX = "B"          # citation numbers in the PDF (B for bibliography; R is taken by results)
OVERVIEW_TYPES = ("question", "hypothesis", "premise", "step", "decision", "result", "figure", "conclusion",
                  "caveat", "artefact", "resource")


class PdfWriter:
    def __init__(self, tree: Tree):
        self.tree = tree
        self.urls = {node.url: node.key for node in tree.nodes.values()}
        self.artefact_by_path = {str(node.header.get("path", "")).rstrip("/"): node
                                 for node in tree.nodes.values() if node.type == "artefact"}
        self.placed: set[str] = set()
        self.single = len(tree.projects) == 1        # one experiment: read as a single-experiment document
        self.reference_numbers: dict[str, str] = {}  # reference key -> "B1", in order of first citation
        self.notes: list[str] = []                   # problems worth a line in the build log (small figures)

    # ------------------------------------------------------------------ helpers
    def markdown(self, node: Node, source: str, level: int) -> str:
        context = LinkContext(self.tree, node.project, SENTINEL, lambda target, prefix: None,
                              self.data_href, node.key)
        return Converter(self.urls, heading_level=level, cite=self.cite).convert(render_markdown(source, context))

    def reference_number(self, key: str) -> str:
        if key not in self.reference_numbers:
            self.reference_numbers[key] = f"{REFERENCE_PREFIX}{len(self.reference_numbers) + 1}"
        return self.reference_numbers[key]

    def cite(self, key: str, link_text: str) -> str | None:
        """A link to a reference page as an ordinary tag in the line ([B1], the same size as every other tag, with
        the page number), numbered in order of first citation; text given with the link ([[ref-x|Smith 2020]])
        stays in front of the tag."""
        node = self.tree.nodes.get(key)
        if node is None or node.type != "reference":
            return None
        mark = f"#nlink({label(key)})[{tag_markup('reference', self.reference_number(key))}]"
        return mark if not link_text or link_text == node.title else f"{text(link_text)} {mark}"

    def data_href(self, target: str, prefix: str) -> tuple[str | None, str]:
        node = self.artefact_by_path.get(target.rstrip("/"))
        return (f"{prefix}{node.url}", f"{node.number} {target}") if node else (None, target)

    def link(self, node: Node) -> str:
        """The tag is the link (as on the site); references by their citation number (B1); other pages without a
        number by their title."""
        if node.type == "reference":
            return f"#nlink({label(node.key)})[{tag_markup('reference', self.reference_number(node.key))}]"
        if node.number:
            return f"#nlink({label(node.key)})[{tag_markup(node.type, node.number)}]"
        return f"#nlink({label(node.key)})[{text(node.title)}]"

    def tagline(self, node: Node, words: str | None = None) -> str:
        """Tag and one line as ONE link (lists of pages)."""
        return (f"#nlink({label(node.key)})[{tag_markup(node.type, node.number) if node.number else ''} "
                f"#text(fill: ink)[{text(node.title if words is None else words)}]]")

    def answer_block(self, question: Node, with_question: bool) -> str:
        """A question's executive summary: (the question,) its answer: text, its conclusions as tag + line."""
        _, _, conclusions = questions.evidence(self.tree, question)
        parts = []
        if with_question:
            parts.append(f"#block(sticky: true, above: 1.8em, below: 0.7em)[{self.entry(question, question.title, True)}]")
        summary = questions.answer(question)
        if summary:
            parts.append(self.markdown(question, summary, 4))
        if conclusions and with_question:          # at a glance: each conclusion in full once, then by its tag
            new = [item for item in conclusions if item.key not in self.glance_seen]
            seen = [item for item in conclusions if item.key in self.glance_seen]
            self.glance_seen.update(item.key for item in conclusions)
            if new:
                parts.append(self.conclusion_list(new, True))
            if seen:
                parts.append(f"#block(above: 0.5em, inset: (left: 12pt))[#text(font: sans, size: 8pt, fill: muted)"
                             f"[Also: ] {self.links([item.key for item in seen])}]")
        elif conclusions:                         # a question part: in full once, later by tag
            new = [item for item in conclusions if item.key not in self.part_seen]
            seen = [item for item in conclusions if item.key in self.part_seen]
            self.part_seen.update(item.key for item in conclusions)
            if new:
                parts.append(self.conclusion_list(new, False))
            if seen:
                parts.append(f"#block(above: 0.6em, below: 1em)[#text(font: sans, size: 8.5pt, fill: muted)"
                             f"[{'Conclusions' if len(seen) > 1 else 'Conclusion'} given above: ] {self.links([item.key for item in seen])}]")
        return "\n\n".join(parts)

    def full_name(self, node: Node) -> str:
        """'Conclusion' in the type's colour and the tag [icon C1] (not a link by itself)."""
        return fullname_markup(node.type, node.number)

    def entry(self, node: Node, words: str, bold: bool = False) -> str:
        """Full name and a line of text as one link; status and page number right-aligned at the end of the line."""
        body = f"#text(font: sans, weight: \"bold\")[{text(words)}]" if bold else text(words)
        return f"#entry({label(node.key)}, [{self.full_name(node)}], [{body}], [{status_pill(node.status)}])"

    def conclusion_list(self, conclusions: list[Node], compact: bool) -> str:
        """The conclusions of a question under their own small heading, each named in full."""
        items = "\n".join(f"#block(above: 0.55em, below: 0.55em, inset: (left: 10pt), stroke: (left: 2pt + "
                          f"rgb({string(TYPE_COLOURS['conclusion'])}).lighten(40%)))[{self.entry(item, item.short)}]"
                          for item in conclusions)
        title = "" if compact else ("#block(sticky: true, above: 1.2em, below: 0.5em)[#text(font: sans, size: 10.5pt, "
                                    "weight: \"bold\", fill: ink)[Conclusions]]\n")
        return title + items + "\n#v(0.6em)"

    def tag_cell(self, node: Node) -> str:
        return f"#link({label(node.key)})[{tag_markup(node.type, node.number)}]"

    def title_cell(self, node: Node, words: str) -> str:
        """Table cell: the text as the link, the page number at the end of the line."""
        return f"#link({label(node.key)})[#text(fill: ink)[{text(words)}]] #h(0.4em) #h(1fr) #pagenum({label(node.key)})"

    def links(self, keys: list[str]) -> str:
        found = sorted((self.tree.nodes[key] for key in keys if key in self.tree.nodes), key=self.number_order)
        return ", ".join(self.link(node) for node in found)

    @staticmethod
    def number_order(node: Node) -> tuple:
        return (list(TYPE_COLOURS).index(node.type) if node.type in TYPE_COLOURS else 99, natural(node.number),
                natural(node.title))

    def of_type(self, project: str, node_type: str) -> list[Node]:
        return sorted((node for node in self.tree.nodes.values() if node.project == project and node.type == node_type),
                      key=lambda node: (natural(node.number), node.order, node.id))

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
        colour = TYPE_COLOURS.get(node.type, "#555566")
        heading = f"{fullname_markup(node.type, node.number)} #h(0.3em) {text(node.title)}"
        pills = " ".join(part for part in (status_pill(node.status), written_pill(node), extra) if part)
        return ((f"#pagebreak(weak: true)\n" if level <= 2 else "")
                + f"#node({string(colour)})[\n{'=' * level} {heading} {label(node.key)}\n\n"
                + (f"#block(above: 0.5em, below: 0.7em)[{pills}]\n\n" if pills else "")
                + f"#summary({string(colour)})[{text(node.short)}]]")

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
        if node.type == "step":                  # methods: what the step served and what follows from it
            used_for, results, conclusions = self.step_outcomes(node)
            tools = [self.tree.nodes[key] for key in node.relations.get("uses", []) if key in self.tree.nodes]
            if tools:
                lines.append("#strong[Uses:] " + ", ".join(
                    f"{self.link(tool)} {text(tool.title)}" + (f" ({text(str(tool.header['rrid']))})"
                                                              if tool.header.get("rrid") else "") for tool in tools))
            for name, keys in (("Used for", used_for), ("Results", results), ("Conclusions", conclusions)):
                if keys:
                    lines.append(f"#strong[{name}:] {self.links(keys)}")
        if lines:
            parts.append(f"#meta[{' #h(0.6em)·#h(0.6em) '.join(lines)}]")
        return "\n\n".join(part for part in parts if part.strip())

    def step_outcomes(self, step: Node) -> tuple[list[str], list[str], list[str]]:
        """(questions, results, conclusions) of a step: results it made (children, made_by), that test the
        hypotheses it tests, or that read files it made (directly or through files made from them); the questions
        those results and hypotheses belong to; conclusions resting on them."""
        tested = set(step.relations.get("tests", []))
        members = [node for node in self.tree.nodes.values() if node.project == step.project]

        def made_here(node: Node) -> bool:
            return node.parent == step.id or step.key in node.relations.get("made_by", [])
        files = {node.key for node in members if node.type == "artefact" and made_here(node)}
        while True:                              # files made from this step's files, and so on
            more = {node.key for node in members if node.type == "artefact" and node.key not in files
                    and files & set(node.relations.get("derived_from", []))}
            if not more:
                break
            files |= more
        results = [node.key for node in members if node.type == "result"
                   and (made_here(node) or tested & set(node.relations.get("tests", []))
                        or files & set(node.relations.get("from_artefact", [])))]
        owners = self.owners_cache.setdefault(step.project, self.question_keys(step.project))
        questions_of = [key for item in results + sorted(tested) for key in owners.get(item, [])]
        for hypothesis in tested:
            parent = self.tree.nodes.get(hypothesis)
            if parent and parent.parent and self.tree.nodes.get(f"{parent.project}:{parent.parent}", parent).type == "question":
                questions_of.append(f"{parent.project}:{parent.parent}")
        found = set(results)
        conclusions = [node.key for node in self.tree.nodes.values() if node.type == "conclusion"
                       and found & set(self.supporting(node) + self.opposing(node))]
        return list(dict.fromkeys(questions_of)), results, conclusions

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
        automatic, scale = figure_width(PROJECT_ROOT / image)
        width = str(node.header.get("pdf_width") or automatic)
        if scale is not None and scale < SMALL_FIGURE_SCALE and not node.header.get("pdf_width"):
            self.notes.append(f"{node.number or node.id}: printed at {scale:.0%} of its own size ({image}); make it "
                              f"at most {TEXT_WIDTH_CM:.0f} cm wide and {MAX_FIGURE_HEIGHT_CM:.0f} cm high so its "
                              "text keeps its size")
        if not re.fullmatch(r"\d+(\.\d+)?(cm|mm|%)", width):
            width = "100%"
        parts = [f"#align(center, image({string('/' + image)}, width: {width}))"]
        caption_file = node.header.get("caption_file")
        if caption_file and (PROJECT_ROOT / caption_file).is_file():
            caption = "\n".join(line for line in (PROJECT_ROOT / caption_file).read_text().splitlines()
                                if not line.startswith(("# ", "- source table:", "- script:", "- commit:")))
            parts.append(f"#block(inset: (x: 4pt), above: 0.8em)[#set text(size: 9pt)\n"
                         f"{self.markdown(node, caption.strip(), level + 1)}]")
            if len(caption) < 1800:        # a short caption stays with its image (a long one may run on)
                return f"#block(breakable: false)[\n{chr(10).join(parts)}\n]"
        return "\n\n".join(parts)

    # ------------------------------------------------------------------ chapter parts
    def question_of(self, hypothesis: Node) -> str | None:
        parent = self.tree.nodes.get(f"{hypothesis.project}:{hypothesis.parent}") if hypothesis.parent else None
        if parent and parent.type == "question":
            return parent.key
        answers = hypothesis.relations.get("answers") or []
        return answers[0] if answers else None

    @staticmethod
    def status_fill(nodes: list[Node]) -> str:
        """A table fill: the header row tinted, each row tinted by its page's status (green / red / amber)."""
        tints = ", ".join(string(STATUS_COLOURS.get(str(node.status), "#ffffff")) for node in nodes)
        return (f"fill: (_, row) => if row == 0 {{ luma(232) }} else {{ rgb(({tints},).at(row - 1)).lighten(90%) }}")

    def status_table(self, nodes: list[Node], columns: str, header: list[str], rows: list[list[str]],
                     note: str = "") -> str:
        return (f"#block(width: 100%, above: 0.9em, below: 1.1em)[#set text(size: 8.5pt); #set par(justify: false, leading: 0.5em)\n"
                f"#table(columns: {columns}, inset: (x: 5pt, y: 5pt), stroke: 0.4pt + luma(205), align: left, "
                f"{self.status_fill(nodes)}, table.header(..({', '.join(header)},).map(strong)), "
                + ", ".join(cell for row in rows for cell in row) + ")]"
                + (f"\n\n#meta[{note}]" if note else ""))

    def conclusions_table(self, conclusions: list[Node]) -> str:
        columns = [("[Conclusion]", "auto", lambda item: self.tag_cell(item)),
                   ("[In short]", "2.2fr", lambda item: self.title_cell(item, item.title)),
                   ("[Status]", "auto", lambda item: status_pill(item.status)),
                   ("[Supported by]", "1.3fr", lambda item: self.links(self.supporting(item))),
                   ("[Opposed by]", "0.8fr", lambda item: self.links(self.opposing(item))),
                   ("[Limited by]", "1fr", lambda item: self.links(item.incoming.get("Limited by", [])))]
        cells = [[render(item) for _, _, render in columns] for item in conclusions]
        keep = [index for index in range(len(columns)) if index < 3 or any(row[index] for row in cells)]
        return self.status_table(conclusions, "(" + ", ".join(columns[index][1] for index in keep) + ")",
                                 [columns[index][0] for index in keep],
                                 [[f"[{row[index]}]" for index in keep] for row in cells])

    @staticmethod
    def supporting(node: Node) -> list[str]:
        return list(dict.fromkeys(node.relations.get("supported_by", []) + node.incoming.get("Supported by", [])))

    @staticmethod
    def opposing(node: Node) -> list[str]:
        return list(dict.fromkeys(node.relations.get("opposed_by", []) + node.incoming.get("Opposed by", [])))

    def caveats_table(self, caveats: list[Node]) -> str:
        rows = [[f"[{self.tag_cell(item)}]", f"[{self.title_cell(item, item.title)}]", f"[{status_pill(item.status)}]",
                 f"[{self.links(item.relations.get('limits', []))}]"] for item in caveats]
        return self.status_table(caveats, "(auto, 2.5fr, auto, 1.2fr)", ["[Caveat]", "[What it says]", "[Status]",
                                                                       "[Limits]"], rows,
                                 "Open: still limits the pages listed. Addressed: a later step dealt with it.")

    def hypothesis_table(self, hypotheses: list[Node]) -> str:
        def written(hypothesis: Node) -> str:
            return ("before its test" if hypothesis.header.get("fixed_before_results") is True else
                    "after results" if hypothesis.header.get("fixed_before_results") is False else "")
        uniform = len({written(hypothesis) for hypothesis in hypotheses}) == 1
        cells = []
        for hypothesis in hypotheses:
            cells += [f"[{self.tag_cell(hypothesis)}]", f"[{self.title_cell(hypothesis, hypothesis.short)}]"]
            cells += [] if uniform else [f"[{text(written(hypothesis))}]"]
            cells += [f"[{status_pill(hypothesis.status)}]", f"[{self.links(hypothesis.incoming.get('Tested by', []))}]"]
        header = ["[Hypothesis]", "[Expected (in short)]"] + ([] if uniform else ["[Written]"]) + ["[Outcome]", "[Tested by]"]
        columns = "(auto, 1fr, auto, auto)" if uniform else "(auto, 1fr, auto, auto, auto)"
        when = written(hypotheses[0])
        note = (f" All of them were written {when}." if uniform and when else "")
        return (f"#block(width: 100%, above: 1.2em)[#set text(size: 8.5pt); #set par(justify: false)\n"
                f"#table(columns: {columns}, inset: (x: 5pt, y: 5pt), stroke: 0.4pt + luma(205), "
                f"align: left, {self.status_fill(hypotheses)}, "
                f"table.header(..({', '.join(header)}).map(strong)), {', '.join(cells)})]\n\n"
                f"#meta[The full text of each hypothesis (its test, its yardstick and what was expected) is in the "
                f"chapter Hypotheses in full; the results below test them.{note}]")

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
        """The experiment's executive summary (unless it is already on the title page), then every question with
        its answer in short and its conclusions; open caveats; key terms."""
        parts = ["== At a glance"]
        intro, _ = questions.split_intro(home.body)
        if not self.single:
            parts.append(f"#summary(\"#333333\")[{text(home.short)}]")
            if intro:
                parts.append(self.markdown(home, intro, 3))
        question_list = questions.questions(self.tree, project)
        if question_list:
            parts.append("#intro[Each question with its answer in short and the conclusions that give it; the "
                         "conclusions list their evidence and limits on the page given.]")
            parts += [self.answer_block(question, True) for question in question_list]
        else:
            conclusions = self.of_type(project, "conclusion")
            if conclusions:
                parts.append("#list(" + ", ".join(f"[{self.tagline(item, item.short)}]" for item in conclusions) + ")")
        caveats = [caveat for caveat in self.of_type(project, "caveat") if caveat.status != "addressed"]
        if caveats:
            parts.append("#block(sticky: true, above: 1.6em, below: 0.5em)[#text(font: sans, size: 10.5pt, weight: "
                         "\"bold\", fill: ink)[Open caveats]]")
            parts.append("#block[#set text(size: 9pt)\n" + "\n".join(
                f"#block(above: 0.45em, below: 0.45em, inset: (left: 10pt), stroke: (left: 2pt + "
                f"rgb({string(TYPE_COLOURS['caveat'])}).lighten(40%)))[{self.entry(caveat, caveat.title)}]"
                for caveat in caveats) + "]")
        return parts

    def chapter(self, project: str) -> str:
        from kea.docsite import versions
        home = self.tree.projects[project]
        self.placed.add(home.key)
        own = versions.releases(project)
        pills = " ".join(part for part in ([f"#pill(\"#f0b429\")[{text(own[-1].label)}]"] if own else []) +
                         [status_pill(home.status)] if part)
        if self.single:      # one experiment: the document is that experiment; no chapter page of its own
            parts = [f"#pagebreak(weak: true)\n#metadata(none) {label(home.key)}"]
        else:
            parts = [f"#chapter({string(project)})[\n= {text(home.title)} {label(home.key)}\n]", pills]
        parts += self.at_a_glance(project, home)
        _, rest = questions.split_intro(home.body)
        if rest.strip():
            first = re.match(r"\s*#{1,6}\s+(.+)", rest)
            if first and first.group(1).strip().lower() == "background":
                rest = rest.strip().split("\n", 1)[1] if "\n" in rest.strip() else ""
            parts += ["== Background", self.markdown(home, rest, 3)]
        premises = self.of_type(project, "premise")
        if premises:
            parts += ["== Starting points",
                      "#intro[What the analysis takes as given, and why.]"] + [self.section(node, 3) for node in premises]
        hypotheses = self.of_type(project, "hypothesis")
        results = self.of_type(project, "result")
        for question in self.of_type(project, "question"):
            parts.append(self.head(question, 2))
            self.placed.add(question.key)
            parts.append(self.answer_block(question, False))
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
            parts += ["== Conclusions", self.conclusions_table(conclusions)] + [self.section(node, 3) for node in conclusions]
        caveats = self.of_type(project, "caveat")
        if caveats:
            parts += ["== Caveats", "#intro[What limits the results and conclusions above.]", self.caveats_table(caveats)] + \
                     [self.section(node, 3) for node in caveats]
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
        excluded = {"hypothesis", "artefact", "term", "reference", "resource"}
        others = sorted((node for node in self.tree.nodes.values() if node.project == project
                         and node.key not in self.placed and node.type not in excluded),
                        key=lambda node: (node.type, node.number, node.id))
        if others:
            parts += ["== Other pages"] + [self.section(node, 3) for node in others]
        main_names = [part[3:].split("\n")[0] for part in parts if part.startswith("== ")]
        closing = self.closing_chapters(project, hypotheses)
        closing_names = [part[3:].split("\n")[0] for part in closing if part.startswith("== ")]
        # closing chapters each start a page; in the main part only questions do (short parts would leave gaps)
        parts += [f"#pagebreak(weak: true)\n{part}" if part.startswith("== ") else part for part in closing]
        self.section_names += main_names
        self.closing_names += closing_names
        return "\n\n".join(part for part in parts if part.strip())

    def closing_chapters(self, project: str, hypotheses: list[Node]) -> list[str]:
        """The chapters at the end: overview of all pages, hypotheses in full, data and resources, glossary,
        references."""
        parts = self.overview(project)
        if hypotheses:
            parts += [f"== Hypotheses in full",
                      "#intro[As written, with the test and the expectation. Whether each was written before its test "
                      "is shown on its pill.]"] + [self.section(node, 3) for node in hypotheses]
        data_parts, figure_parts = self.resources_table(project), []
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
            data_parts += ["=== Data files made by the steps",
                      "#intro[Paths in the project folder. Their contents are not printed here (they may hold "
                      "controlled-access, donor-level data).]",
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
            figure_parts += ["== Figure files",
                      "#intro[Each figure is made by a script from a saved table; the image, script and table are "
                      "kept in the project folder.]",
                      f"#datatable(4, 7.5pt, 1, table.header([Figure], [Image], [Script], [Table]), " + ", ".join(cells) + ")"]
        if data_parts:
            parts += ["== Data and resources",
                      "#intro[What the analysis takes from outside (resources: sources such as databases and servers, "
                      "and each dataset, study or file taken from them, with the version, date and checksum needed to "
                      "get the same input again), then the data files it made. The figure files have a chapter of "
                      "their own.]"] + data_parts
        parts += figure_parts
        parts += self.glossary(project)
        parts += self.bibliography(project)
        return parts

    def resources_table(self, project: str) -> list[str]:
        """Each resource as a small block: tag, name and what it is, then the facts needed to get the same input
        again (kind, where, version, retrieved, SHA-256 in full, local copy, access, licence)."""
        resources = self.of_type(project, "resource")
        if not resources:
            return []
        fields = (("kind", "Kind"), ("rrid", "RRID"), ("url", "Where"), ("dataset_id", "Dataset id"),
                  ("accession", "Accession"),
                  ("version", "Version"),
                  ("deposit", "Deposit"), ("retrieved", "Retrieved"), ("sha256", "SHA-256"), ("size", "Size"),
                  ("local", "Local copy"), ("access", "Access"), ("licence", "Licence"))
        blocks = []
        for item in resources:
            self.placed.add(item.key)
            cells = []
            for key, name in fields:
                value = str(item.header.get(key) or "").strip()
                if not value and key not in ("kind", "version", "retrieved"):
                    continue
                if not value:
                    shown = "#text(fill: rgb(\"#aa3333\"))[not recorded]"
                elif key == "url" and value.startswith(("http://", "https://")):
                    shown = f"#link({string(value)})[#mono[{text(value, breakable=True)}]]"
                elif key in ("sha256", "local"):
                    shown = f"#mono[{text(value, breakable=True)}]"
                else:
                    shown = text(value)
                cells += [f"[#text(fill: muted)[{name}]]", f"[{shown}]"]
            for relation, name in (("part_of", "Part of"), ("cites", "Paper")):
                linked = [key for key in item.relations.get(relation, []) if key in self.tree.nodes]
                if linked:
                    cells += [f"[#text(fill: muted)[{name}]]", f"[{self.links(linked)}]"]
            contains = item.incoming.get("Contains", [])
            if contains:
                cells += ["[#text(fill: muted)[Contains]]", f"[{self.links(contains)}]"]
            blocks.append(f"#block(breakable: false, stroke: (left: 3pt + rgb({string(TYPE_COLOURS['resource'])})), "
                          f"inset: (left: 9pt, y: 4pt), above: 1em)[{self.full_name(item)} #h(0.3em) "
                          f"#strong[{text(item.title)}] {label(item.key)} #h(1fr) {status_pill(item.status)}\n\n"
                          f"#text(size: 9pt)[{text(item.short)}]\n\n"
                          f"#block[#set text(size: 8.5pt); #set par(justify: false)\n#grid(columns: (auto, 1fr), "
                          f"column-gutter: 10pt, row-gutter: 5pt, {', '.join(cells)})]]")
            body = self.body(item, 4)            # the page's own text (e.g. a table of the datasets used)
            if body.strip():
                blocks.append(f"#block(inset: (left: 12pt), above: 0.6em)[#set text(size: 9pt)\n{body}]")
        return ["=== Resources",
                "#intro[What the analysis takes from outside, with what is needed to get the same input again; the "
                "website has a page for each.]"] + blocks

    def glossary(self, project: str) -> list[str]:
        """One glossary at the end: key terms first, then each group (Genes, Proteins …) under its own heading."""
        groups = term_groups(self.of_type(project, "term"))
        if not groups:
            return []
        parts = ["== Glossary",
                 "#intro[Words with a dotted underline in the text link here. "
                 + ("Entities (" + ", ".join(text(name.lower()) for name, _ in groups if name) + ") follow the key "
                    "terms. " if any(name for name, _ in groups) else "") + "]"]
        for group, terms in groups:
            if len(groups) > 1:
                parts.append(f"=== {text(group or 'Key terms')}")
            for member in terms:
                self.placed.add(member.key)
                heading = (f"==== {fullname_markup('term', member.number) if member.number else ''} #h(0.3em) "
                           f"{text(member.title)} {label(member.key)}")
                entry = [heading, f"#emph[{text(member.short)}]", self.body(member, 4)]
                joined = "\n\n".join(part for part in entry if part)
                parts.append(f"#block(breakable: false)[\n{joined}\n]" if len(member.body) < 1500 else joined)
        return parts

    # ------------------------------------------------------------------ overview tables
    def question_keys(self, project: str) -> dict[str, list[str]]:
        """page key -> keys of the questions it belongs to (hypotheses, results and conclusions through
        questions.evidence; figures through the results they show; caveats through what they limit)."""
        owners: dict[str, list[str]] = {}
        for question in questions.questions(self.tree, project):
            for group in questions.evidence(self.tree, question):
                for member in group:
                    owners.setdefault(member.key, []).append(question.key)
        for node in list(self.tree.nodes.values()):
            if node.project != project:
                continue
            if node.type == "result":
                for figure in node.relations.get("shown_in", []):
                    owners.setdefault(figure, []).extend(owners.get(node.key, []))
            if node.type == "figure":
                for result in node.incoming.get("Shows", []):
                    owners.setdefault(node.key, []).extend(owners.get(result, []))
                if node.parent and f"{project}:{node.parent}" in owners:
                    owners.setdefault(node.key, []).extend(owners[f"{project}:{node.parent}"])
        for node in self.tree.nodes.values():
            if node.project == project and node.type == "caveat":
                for target in node.relations.get("limits", []):
                    limited = self.tree.nodes.get(target)
                    owners.setdefault(node.key, []).extend(
                        owners.get(target, []) + ([target] if limited and limited.type == "question" else []))
        return {key: list(dict.fromkeys(values)) for key, values in owners.items()}

    def related(self, node: Node) -> list[Node]:
        """Every numbered page linked to this one, in either direction (parent and children included)."""
        keys = [key for values in node.relations.values() for key in values]
        keys += [key for values in node.incoming.values() for key in values]
        if node.parent:
            keys.append(f"{node.project}:{node.parent}")
        keys += [child.key for child in self.tree.children(node)]
        found = {key: self.tree.nodes[key] for key in keys if key in self.tree.nodes and key != node.key}
        return sorted((item for item in found.values() if item.number), key=self.number_order)

    def tag_links(self, nodes: list[Node]) -> str:
        """Tags only (no page numbers), grouped by kind: compact cells of the overview tables."""
        groups: dict[str, list[str]] = {}
        for item in nodes:
            groups.setdefault(item.type, []).append(f"#link({label(item.key)})[{tag_markup(item.type, item.number)}]")
        return " #h(5pt) ".join(" ".join(tags) for tags in groups.values())

    def overview(self, project: str) -> list[str]:
        """Supplementary tables: one per kind of page, one row per page (tag, one line, status, the questions it
        belongs to and the other pages it links to). A flat, printed version of the site's map."""
        owners = self.question_keys(project)
        tables = []
        for node_type in OVERVIEW_TYPES:
            members = self.of_type(project, node_type)
            if not members:
                continue
            with_status = any(member.status for member in members)
            with_question = node_type != "question" and any(owners.get(member.key) for member in members)
            header = [f"[{text(TYPE_LABELS[node_type])}]", "[In short]"] + (["[Status]"] if with_status else []) + \
                (["[Question]"] if with_question else []) + ["[Linked to]"]
            with_links = any(item.key not in set(owners.get(member.key, [])) for member in members
                             for item in self.related(member))
            if not with_links:
                header = header[:-1]
            widths = ["auto", "2.4fr"] + (["auto"] if with_status else []) + (["auto"] if with_question else []) + \
                (["1.6fr"] if with_links else [])
            rows = []
            for member in members:
                questions_of = [self.tree.nodes[key] for key in owners.get(member.key, []) if key in self.tree.nodes]
                others = [item for item in self.related(member) if item.key not in {q.key for q in questions_of}]
                row = [f"[{self.tag_cell(member)}]", f"[{self.title_cell(member, member.title)}]"]
                row += [f"[{status_pill(member.status)}]"] if with_status else []
                row += [f"[{self.tag_links(sorted(questions_of, key=self.number_order))}]"] if with_question else []
                row += [f"[{self.tag_links(others)}]"] if with_links else []
                rows.append(row)
            tables.append(f"=== {fullname_markup(node_type, '')} #h(2pt) "
                          f"#text(font: sans, size: 9pt, weight: \"regular\", fill: muted)[{len(members)}]")
            tables.append(self.status_table(members, "(" + ", ".join(widths) + ")", header, rows))
        if not tables:
            return []
        return ["== Overview of all pages",
                "#intro[One table per kind of page: its number, what it says in one line, its status, the questions it "
                "belongs to and the other pages it links to (in either direction), grouped by kind. Tags are links.]"
                ] + tables

    # ------------------------------------------------------------------ references
    def citation_markup(self, node: Node) -> str:
        """A reference as in a journal's reference list: `citation:` from the front matter (written by
        `kea cite`, Nature style) or the title, then DOI and PubMed links."""
        citation = str(node.header.get("citation") or "").strip()
        body = self.markdown(node, citation, 4) if citation else text(node.title)
        extras = []
        doi = str(node.header.get("doi") or "").strip()
        if doi:
            extras.append(f"#link({string('https://doi.org/' + doi)})[doi:{text(doi)}]")
        pmid = str(node.header.get("pmid") or "").strip()
        if pmid:
            extras.append(f"#link({string('https://pubmed.ncbi.nlm.nih.gov/' + pmid + '/')})[PMID {text(pmid)}]")
        return body + (" " + " · ".join(extras) if extras else "")

    def bibliography(self, project: str) -> list[str]:
        references = self.of_type(project, "reference")
        if not references:
            return []
        for node in sorted((node for node in references if node.key not in self.reference_numbers),
                           key=lambda node: natural(node.title)):
            self.reference_number(node.key)            # pages never cited get the numbers after the cited ones
        ordered = sorted(references, key=lambda node: natural(self.reference_numbers[node.key]))
        cells = []
        for node in ordered:
            self.placed.add(node.key)
            cells += [f"[{tag_markup('reference', self.reference_numbers[node.key])} {label(node.key)}]",
                      f"[{self.citation_markup(node)} #linebreak() #text(size: 8pt, fill: muted)[{text(node.short)}]]"]
        return ["== References",
                "#intro[Numbered in the order they are first cited; the tags in the text "
                "(" + tag_markup("reference", REFERENCE_PREFIX + "1") + ") point here. Under each: why the paper "
                "is cited.]",
                "#block[#set text(size: 9pt); #set par(justify: false)\n#grid(columns: (auto, 1fr), column-gutter: "
                "8pt, row-gutter: 9pt, " + ", ".join(cells) + ")]"]

    # ------------------------------------------------------------------ change history
    def what_changed(self) -> str:
        """Once for the document, after the chapters: each release (version, date, kind, plan, commit, run, why)
        and each agent run (date, plan, release kind, commits, what it did; doc/_changes, newest first)."""
        from kea.docsite import changes, versions
        parts = []
        plans = review_plans()
        releases = versions.releases(None)
        merged: dict[tuple, list] = {}              # the site and the experiment released together: one row
        for release in releases:
            merged.setdefault((release.key, release.commit), []).append(release)
        kind_of_run: dict[str, str] = {}
        if merged:
            rows = []
            for (_, _), group in sorted(merged.items(), reverse=True):
                release = group[0]
                kind_of_run.setdefault(release.run, f"{release.kind} → {release.label}" if release.kind else release.label)
                scope = ", ".join(sorted("whole site" if not item.experiment else item.experiment for item in group))
                plan = plan_label(release.cycle, plans) or plans.get(f"run:{release.run}", "")
                rows.append([f"[#strong[{text(release.label)}]]", f"[{text(release.date[:10])}]", f"[{text(scope)}]",
                             f"[{text(release.kind)}]", f"[{text(plan)}]", f"[#mono[{text(release.short)}]]",
                             f"[{text(release.run)}]", f"[{text(release.reason)}]"])
            parts.append("=== Versions")
            parts.append("#datatable(8, 7.2pt, 1, table.header([Version], [Date], [Of], [Kind], [Plan], [Commit], "
                         "[Run], [Why]), " + ", ".join(cell for row in rows for cell in row) + ")")
        try:
            runs = changes.load_runs(changes.all_commits())
        except (OSError, ValueError):
            runs = []
        if runs:
            cells = []
            for run in runs:
                commits = [commit.short for commit in run.commits]
                shown = " ".join(commits[:4]) + (f" +{len(commits) - 4}" if len(commits) > 4 else "")
                cells += [f"[{text(run.id)}]", f"[{text(run.date)}]", f"[{text(plans.get('run:' + run.id, ''))}]",
                          f"[{text(kind_of_run.get(run.id, ''))}]", f"[#mono[{text(shown or '—', breakable=True)}]]",
                          f"[{text(RUN_PREFIX.sub('', run.title))}]"]
            parts.append("=== Runs")
            parts.append("#datatable(6, 7.2pt, 1, table.header([Run], [Date], [Plan], [Release], [Commits], "
                         "[What it did]), " + ", ".join(cells) + ")")
        if not parts:
            return ""
        self.closing_names.append("What changed")
        return "\n\n".join(["#pagebreak(weak: true)\n== What changed",
                             "#intro[Each released version (its kind: major when a conclusion changes direction, minor "
                             "for new results or pages, patch for wording), the review plan it carried out and the "
                             "commit it was made from; then each agent run, newest first, with its commits. The website "
                             "has every run in full, with the changed text of every page.]"] + parts)

    def written_text(self) -> str:
        """The About text on 'written before its test' / 'written after results', for the pills this PDF has."""
        values = {node.header.get("fixed_before_results") for node in self.tree.nodes.values() if node.type == "hypothesis"}
        parts = []
        if True in values:
            parts.append("#pill(\"#1b7f4b\")[written before its test]: the claim, the test and the expectation were "
                         "fixed before that test was run, though possibly after other results of the same experiment "
                         "had been seen.")
        if False in values:
            parts.append("#pill(\"#a86b00\")[written after results]: it was written with its result already known, "
                         "so it describes rather than predicts.")
        return ("A hypothesis also says when it was written. " + " ".join(parts) + " ") if parts else ""

    def example_number(self, node_type: str) -> str:
        numbered = [node.number for node in self.tree.nodes.values() if node.type == node_type and node.number]
        return sorted(numbered, key=natural)[0] if numbered else ""

    # ------------------------------------------------------------------ whole document
    def about(self, version: str, commit: str, today: str) -> str:
        used_types = [node_type for node_type in TYPE_MEANINGS if node_type != "goal"
                      and any(node.type == node_type for node in self.tree.nodes.values())]
        type_rows = ", ".join(f"[{fullname_markup(node_type, REFERENCE_PREFIX + '1' if node_type == 'reference' else self.example_number(node_type))}], "
                              f"[{text(TYPE_MEANINGS[node_type])}]" for node_type in used_types)
        used_statuses = sorted({str(node.status) for node in self.tree.nodes.values() if node.status},
                               key=lambda status: (STATUS_COLOURS.get(status, "z"), status))
        status_rows = ", ".join(f"[{status_pill(status)}], [{text(STATUS_MEANINGS.get(status, ''))}]"
                                for status in used_statuses)
        prefixes = sorted({(node.number[:1], node.type) for node in self.tree.nodes.values()
                           if node.number and node.number[:1].isalpha()})
        numbering = ", ".join(f"{prefix} = {TYPE_LABELS.get(node_type, node_type).lower()}" for prefix, node_type in prefixes)
        if self.reference_numbers:
            numbering += f", {REFERENCE_PREFIX} = reference (in this document only, in order of citation)"
        main = list(dict.fromkeys(self.section_names))
        appendix = list(dict.fromkeys(self.closing_names))

        def listed(items: list[str]) -> str:
            items = [f"#emph[{text(item)}]" for item in items]
            return ", ".join(items[:-1]) + (" and " if len(items) > 1 else "") + (items[-1] if items else "")
        has_questions = any(node.type == "question" for node in self.tree.nodes.values())
        has_hypotheses = any(node.type == "hypothesis" for node in self.tree.nodes.values())
        question_text = ("Each #emph[question] has a part of its own: the question and its answer in short"
                         + (", a table of its hypotheses" if has_hypotheses else "")
                         + ", and the results that answer it, each followed by its figures. ") if has_questions else ""
        return f"""#chapter(none)[
= About this document <kea-about>
]

== What this document is

The project is a set of small linked pages, one claim per page, each tied to the evidence behind it. Its version
({text(version)}, commit #raw({string(commit)})) is the version of that set of pages: it changes when a claim, a
result or a page changes. The website and this document are two views of the same version, written from the same
source files on {text(today)}; the website also carries the comments and the review history. When the website shows a
newer version, that one replaces this document.

== How it is ordered

{'The document is one experiment, in these parts' if self.single else 'Each experiment is one chapter, in these parts'}: {listed(main)}.
{question_text}{('Chapters at the end: ' + listed(appendix) + '.') if appendix else ''} To read quickly: {'the summary on the title page and ' if getattr(self, 'has_summary', False) else ''}#emph[At a glance]; to check a claim, follow its evidence.

== Kinds of page

Every page has a kind, shown as a coloured tag with an icon and its number (for example
{tag_markup("question", "Q1")} or {tag_markup("conclusion", "C2")}); in headings the kind is written out in front of
the tag ({fullname_markup("conclusion", "C2")}), and the same colour marks the stripe beside the heading.

#block[#set par(justify: false)
#grid(columns: (auto, 1fr), column-gutter: 10pt, row-gutter: 8pt, {type_rows})]

== Numbers, links and page references

Pages are numbered per experiment and kind ({text(numbering)}); apart from the references, the numbers are the
same as on the website. The tag is the link: {tag_markup("result", "R3")}#text(size: 0.72em, fill: muted)[#h(1.5pt)p.12]
leads to that page, and the small number gives the page of this document (left out when it is the same page). In
lists of pages the whole line is the link, with the status and the page number at the end of the line.
#tlink(<kea-about>)[Words with a dotted underline] are glossary terms: the link leads to their definition.

== Status

#block[#set par(justify: false)
#grid(columns: (auto, 1fr), column-gutter: 10pt, row-gutter: 8pt, {status_rows})]

{self.written_text()}An analysis marked #emph[exploratory] suggests; it needs new data to confirm.

== What is left out

The comments of readers, the review plans and the changed text of each page (all on the site); the code (named by
its file); the relations graph (the overview tables at the end are its printed form); and the contents of data
files, which may hold controlled-access, donor-level data. Numbers in the text come from those files; Data and resources
lists them.

#meta[Made with Kea (github.com/mfiers/Kea), a tool that turns an analysis into a site of linked claims and
evidence, reviewed in cycles by readers and an AI agent.]
"""

    def document(self, stamp: dict | None = None) -> str:
        """The whole Typst source. `stamp` ({"version", "commit", "built"}) replaces the release, commit and date
        (the site cache hashes a source made with a fixed stamp, so only real content changes count)."""
        from kea.docsite import comments, versions
        self.placed = set()                      # document() may run twice (the site cache hashes a fixed-stamp copy)
        self.reference_numbers, self.glance_seen, self.section_names, self.notes = {}, set(), [], []
        self.closing_names: list[str] = []
        self.owners_cache: dict[str, dict[str, list[str]]] = {}
        self.part_seen: set[str] = set()
        title = str(SETTINGS.get("title") or PROJECT_ROOT.name)
        heading = str(SETTINGS.get("heading") or "")
        if stamp is None:
            releases = versions.releases("")
            version = releases[-1].label if releases else "unreleased"
            commit = comments.source_version(None)
            today = dt.date.today().isoformat()
        else:
            version, commit, today = stamp["version"], stamp["commit"], stamp["built"]
        summary = questions.project_summary(self.tree)      # first, so its citations are numbered first
        summary_markup = ""
        if summary:
            home = next(iter(self.tree.projects.values()))
            summary_markup = self.markdown(home, summary, 3)
        chapters = [self.chapter(project) for project in sorted(self.tree.projects)]
        self.has_summary = bool(summary_markup)
        self.content = "\n\n".join(chapters)            # what the site cache keys on (not the date or commit)
        self.stamp = {"version": version, "commit": commit, "built": today}
        author = str(SETTINGS.get("author") or "").strip()
        repository = repository_url()
        logo = pdf_logo()
        light = 'rgb("#c9d2e3")'
        lines = [f"#box(fill: amber, inset: (x: 7pt, y: 3pt), radius: 3pt, text(font: sans, size: 9pt, weight: "
                 f"\"bold\", fill: ink)[Document version {text(version)}])",
                 f"#text(font: sans, size: 9pt, fill: {light})[Commit {text(commit)} · {text(today)}]"]
        if repository:
            lines.append(f"#text(font: sans, size: 9pt, fill: {light})[#link({string(repository)})"
                         f"[{text(repository.removeprefix('https://'))}]]")
        lines.append(f"#text(font: sans, size: 9pt, fill: {light})[Made with #link(\"{KEA_URL}\")[Kea] · "
                     f"#link(<kea-about>)[about this document, p.#context counter(page).at(<kea-about>).first()]]")
        front = f"""#page(margin: 0pt, header: none, footer: none)[
#block(fill: ink, width: 100%, inset: (x: 2.2cm, top: 2.6cm, bottom: 1.3cm))[
  #set par(justify: false)
  #show link: set text(fill: rgb("#9cc3f0"))
  {f'#place(top + right, dy: -1.2cm, link("{KEA_URL}", box(fill: rgb("#f4f1e8"), radius: 6pt, inset: 3pt, image("{logo}", width: 1.5cm))))' if logo else ''}
  #pad(right: {'2.4cm' if logo else '0cm'})[#text(font: sans, size: 30pt, weight: "bold", fill: white)[{text(title)}]]
  {f'#v(4pt) #pad(right: 2.4cm)[#text(font: sans, size: 13pt, fill: rgb("#c9d2e3"))[{text(heading)}]]' if heading and heading != title else ''}
  {f'#v(8pt) #text(font: sans, size: 11pt, fill: white)[{text(author)}]' if author else ''}
  #v(10pt)
  #stack(spacing: 7pt, {', '.join('[' + line + ']' for line in lines)})
]
#pad(x: 2.2cm, top: 0.9cm, bottom: 1.2cm)[
  {'#text(font: sans, size: 12pt, weight: "bold", fill: ink)[Summary]' if summary_markup else ''}
  #v(2pt)
  #set text(size: 10.5pt)
  {summary_markup}
]]
"""
        if not self.single:
            cards = []
            for project, home in sorted(self.tree.projects.items()):
                intro, _ = questions.split_intro(home.body)
                body = self.markdown(home, intro, 4) if intro else text(home.short)
                cards.append(f"#card(\"#333333\", [#box(fill: amber, inset: (x: 5pt, y: 2pt), radius: 3pt, "
                             f"text(font: sans, size: 8pt, weight: \"bold\", fill: ink)[{text(project)}]) #h(4pt) "
                             f"#strong[{text(home.title)}] #h(1fr) #link({label(home.key)})[page #context "
                             f"counter(page).at({label(home.key)}).first()]], [{body}])")
            front += ("#page(header: none, footer: none)[#text(font: sans, size: 19pt, weight: \"bold\", fill: ink)"
                      "[Experiments]\n#v(6pt)\n" + "\n".join(cards) + "]\n")
        front += """
#set page(numbering: "1")
#counter(page).update(1)
#text(font: sans, size: 19pt, weight: "bold", fill: ink)[Contents]
#v(6pt)
#outline(title: none, depth: 2, indent: OUTLINE_INDENT)
"""
        front = front.replace("OUTLINE_INDENT", "0pt" if self.single else "auto")
        preamble = (PREAMBLE.replace("SANS_FONTS", sans_fonts()).replace("TITLE_MARKUP", text(title)).replace("TITLE", string(title))
                    .replace("VERSION_MARKUP", text(f"{title} · {version} · {commit}")))
        changed = self.what_changed()
        return preamble + "\n" + front + "\n\n" + "\n\n".join(chapters) + "\n\n" + changed + "\n\n" + \
            self.about(version, commit, today) + "\n"


CACHE_KEEP = 6
KEA_URL = "https://mfiers.github.io/Kea/"


RUN_PREFIX = re.compile(r"^Run [0-9a-z-]+:\s*")      # "Run 2026-11-06-d: " at the start of a run title


def review_plans() -> dict[str, str]:
    """Review plans (doc/_cycles/cycle-NNN.md): {"cycle:<n>": "plan v0.5 (cycle 4)", "run:<run id>": same}."""
    from kea.docsite.nodes import DOC, split_front_matter
    plans: dict[str, str] = {}
    for path in sorted((DOC / "_cycles").glob("cycle-*.md")):
        try:
            header, _ = split_front_matter(path.read_text(encoding="utf-8"), path)
        except ValueError:
            continue
        number = str(header.get("cycle") or path.stem.removeprefix("cycle-").lstrip("0"))
        name = f"plan {('v' + str(header['version'])) if header.get('version') else ''} (cycle {number})".replace("  ", " ")
        plans[f"cycle:{number}"] = name
        if header.get("run"):
            plans[f"run:{header['run']}"] = name
    return plans


def plan_label(cycle: str, plans: dict[str, str]) -> str:
    number = re.sub(r"\D", "", str(cycle or "")).lstrip("0")
    return plans.get(f"cycle:{number}", f"cycle {number}" if number else "")


def repository_url() -> str:
    """The project's repository for the title page: `repository:` in kea.yaml, else the git remote `origin` as an
    https address ('' when there is none)."""
    configured = str(SETTINGS.get("repository") or "").strip()
    if configured:
        return configured
    try:
        remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=PROJECT_ROOT, capture_output=True,
                                text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    match = re.match(r"^(?:git@|ssh://git@)([^:/]+)[:/](.+?)(?:\.git)?$", remote)
    if match:
        return f"https://{match.group(1)}/{match.group(2)}"
    return remote.removesuffix(".git") if remote.startswith("https://") else ""


def pdf_logo() -> str:
    """Copy the kea icon next to the PDFs (Typst reads files only inside the project) and return its path."""
    from kea.config import PACKAGE_DIR
    source = PACKAGE_DIR / "docsite" / "static" / "kea-icon-512.png"
    target = PROJECT_ROOT / "report" / "pdf" / "_assets" / "kea-icon.png"
    if not source.is_file():
        return ""
    if not target.is_file() or target.stat().st_size != source.stat().st_size:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return "/" + str(target.relative_to(PROJECT_ROOT))


def site_pdf(tree: Tree, site: Path) -> dict | None:
    """The PDF for a site build (`kea build`), or None when Typst is not installed or the compile fails.

    The same PDF for every build mode: it prints no data-file contents. It is compiled only when an input changed.
    The cache key covers everything that reaches the PDF: the whole Typst source (made with a fixed stamp, so the
    date and commit do not count), the bytes of every image it includes, the Kea version and the Typst version.
    Compiled files are kept in report/pdf/_cache/<key>.pdf (the last CACHE_KEEP) with a manifest of the inputs; a
    reused PDF carries the version and commit of the build that compiled it. The build prints why the PDF was
    reused or rebuilt. Returns {"file", "version", "commit", "built", "reused", "reason"}; the PDF is copied to
    <site>/<file>.
    """
    import hashlib
    import json
    import kea
    command = typst_command()
    if command is None:
        return None
    writer = PdfWriter(tree)
    fixed = writer.document({"version": "-", "commit": "-", "built": "-"})
    source = writer.document()                  # second, so writer.stamp holds the real version and commit
    typst_version = subprocess.run([command, "--version"], capture_output=True, text=True).stdout.strip()
    inputs = {"(typst source)": hashlib.sha256(fixed.encode()).hexdigest()[:16],
              "(kea)": kea.__version__, "(typst)": typst_version}
    for image in sorted(set(re.findall(r'image\("/([^"]+)"', fixed))):
        path = PROJECT_ROOT / image
        inputs[image] = hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else "missing"
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:16]
    cache = PROJECT_ROOT / "report" / "pdf" / "_cache"
    cache.mkdir(parents=True, exist_ok=True)
    cached, meta_path = cache / f"{digest}.pdf", cache / f"{digest}.json"
    reused = cached.exists() and meta_path.exists()
    if reused:
        reason = f"reused: none of its {len(inputs) - 3} image(s), its source, Kea or Typst changed (key {digest})"
    else:
        reason = "rebuilt: " + changed_inputs(cache, inputs)
        typ_path = cache / f"{digest}.typ"
        typ_path.write_text(source, encoding="utf-8")
        result = subprocess.run([command, "compile", "--root", str(PROJECT_ROOT), str(typ_path), str(cached)],
                                capture_output=True, text=True)
        if result.returncode != 0:
            print(f"note    PDF not built (typst failed; source {typ_path.relative_to(PROJECT_ROOT)}):\n"
                  f"{result.stderr.strip()[:2000]}", file=sys.stderr)
            return None
        meta_path.write_text(json.dumps({**writer.stamp, "inputs": inputs}))
        for note in writer.notes:
            print(f"note    PDF {note}")
        for old in sorted(cache.glob("*.pdf"), key=lambda path: path.stat().st_mtime)[:-CACHE_KEEP]:
            for suffix in (".pdf", ".json", ".typ"):
                old.with_suffix(suffix).unlink(missing_ok=True)
    meta = json.loads(meta_path.read_text())
    meta.pop("inputs", None)
    title = re.sub(r"[^a-z0-9]+", "-", str(SETTINGS.get("title") or PROJECT_ROOT.name).lower()).strip("-")
    name = f"{title}-{meta['version']}.pdf"
    shutil.copy2(cached, site / name)
    print(f"pdf     {name} {reason}")
    return {"file": name, **meta, "reused": reused, "reason": reason}


def changed_inputs(cache: Path, inputs: dict[str, str]) -> str:
    """What differs from the newest cached PDF's inputs, in a few words (for the build's log)."""
    import json
    manifests = sorted(cache.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    previous = {}
    for manifest in manifests:
        previous = json.loads(manifest.read_text()).get("inputs") or {}
        if previous:
            break
    if not previous:
        return "no earlier PDF in the cache"
    changed = [name for name in inputs if previous.get(name) != inputs[name]]
    removed = [name for name in previous if name not in inputs]
    words = changed[:4] + [f"{name} (gone)" for name in removed[:2]]
    more = len(changed) + len(removed) - len(words)
    return "changed " + ", ".join(words) + (f" and {more} more" if more > 0 else "")


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
    for note in writer.notes:
        print(f"note    {note}")
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
