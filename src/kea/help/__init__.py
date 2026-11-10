"""Kea's help for readers: one text, shown everywhere.

The Markdown files beside this module are the single source of the reader's help:

    1-why.md        why Kea exists and why a project is cut into small pages
    2-progress.md   how a project progresses and is validated (the route, approvals, checks, rechecks, versions)
    3-reading.md    reading a Kea site (types, pages, pills, menu)
    4-reviewing.md  comments and the review cycle (only on sites served with comments)

They are shown verbatim on every site's help.html (pages.help_page), on the hub's front page and /help
(feedback/landing.py), in the PDF's closing chapter (1 and 2; pdf.py), and in README.md, between
`<!-- help:NAME -->` and `<!-- /help -->` markers (src/build_web.py fills them in; the GitHub page docs/index.html is
made from README.md). Edit the files here, then run `make web`; tests check that README.md is in sync.

Two markers in the text are filled by the renderer: `<!-- ROUTE -->` (the route diagram; dropped where there is none)
and `<!-- KINDS -->` (the Markdown table after it gets the coloured tag of each page type in its first column).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import markdown

FOLDER = Path(__file__).resolve().parent
NAMES = ("1-why", "2-progress", "3-reading", "4-reviewing")
REVIEW_ONLY = {"4-reviewing"}


def text(name: str) -> str:
    """The Markdown of one help file."""
    return (FOLDER / f"{name}.md").read_text(encoding="utf-8").strip() + "\n"


def slug(value: str, separator: str = "-") -> str:
    """Heading id: lower case, every run of other characters one '-' (the same on GitHub's page and the hub)."""
    return re.sub(r"[^a-z0-9]+", separator, value.lower()).strip(separator)


def kinds_table(page_html: str, tag: Callable[[str, str], str]) -> str:
    """Replace the first cell of each row of the table after <!-- KINDS --> by tag(kind, label)."""
    from kea.docsite.nodes import TYPE_LABELS
    marker = page_html.find("<!-- KINDS -->")
    if marker < 0:
        return page_html
    start, by_label = page_html.find("<table>", marker), {label.lower(): kind for kind, label in TYPE_LABELS.items()}
    end = page_html.find("</table>", start)
    if start < 0 or end < 0:
        return page_html

    def cell(match: re.Match) -> str:
        label = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        kind = by_label.get(label.lower())
        return f"<tr>\n<td>{tag(kind, label)}</td>" if kind else match.group(0)
    table = re.sub(r"<tr>\s*<td>(.*?)</td>", cell, page_html[start:end])
    return page_html[:marker] + page_html[marker + len("<!-- KINDS -->"):start] + table + page_html[end:]


def render(names: tuple[str, ...] = NAMES, tag: Callable[[str, str], str] | None = None, route: str = "",
           shift: int = 0) -> str:
    """The help files as HTML. tag(kind, label) colours the type table; route replaces <!-- ROUTE -->; shift moves
    the headings down (1: ## becomes h3)."""
    source = "\n\n".join(text(name) for name in names)
    if shift:
        source = re.sub(r"^(#+) ", lambda match: "#" * (len(match.group(1)) + shift) + " ", source, flags=re.M)
    html_text = markdown.markdown(source, extensions=["tables", "fenced_code", "toc"],
                                  extension_configs={"toc": {"slugify": slug}})
    html_text = html_text.replace("<!-- ROUTE -->", route)
    return kinds_table(html_text, tag) if tag else html_text


def plain_tag(kind: str, label: str) -> str:
    """A type's coloured tag with its icon, for pages outside a site (the hub, GitHub's page)."""
    from kea.docsite import icons
    from kea.docsite.render import TYPE_COLOURS
    return (f"<span class='tag' style='background:{TYPE_COLOURS.get(kind, '#556677')}'>{icons.svg(kind)}"
            f"{label}</span>")


def readme_sync(readme: str) -> str:
    """README.md with every `<!-- help:NAME -->` … `<!-- /help -->` block replaced by that help file, verbatim."""
    def fill(match: re.Match) -> str:
        return f"<!-- help:{match.group(1)} -->\n\n{text(match.group(1)).strip()}\n\n<!-- /help -->"
    return re.sub(r"<!-- help:([\w-]+) -->.*?<!-- /help -->", fill, readme, flags=re.S)
