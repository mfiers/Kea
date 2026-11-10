"""Build Kea's web page (docs/index.html, served at https://mfiers.github.io/Kea/) from README.md.

README.md is the source of the web page, so it mirrors what GitHub shows; README's help sections are themselves
copied verbatim from src/kea/help/*.md (the text every Kea site, the hub and the PDF show). This script
- copies the help files into README.md between its `<!-- help:NAME -->` and `<!-- /help -->` markers;
- renders README.md with Python-Markdown (tables, fenced code, heading ids);
- turns the logo line into the page's hero image (docs/logo.png);
- colours the page-type table that follows the `<!-- KINDS -->` marker with Kea's own tags and icons;
- rewrites links to repository files (skill/SKILL.md, src/…) to GitHub, and links to `#…` stay on the page;
- adds a copy button to every code block.

Input: README.md, src/kea/help/*.md. Output: README.md (help sections), docs/index.html (overwritten; it is generated, never edited by hand).
Run: `make web` (or `uv run python src/build_web.py`).
"""
from __future__ import annotations

import html
import re
from pathlib import Path

import markdown

from kea import help as kea_help

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
OUT = ROOT / "docs" / "index.html"
GITHUB = "https://github.com/mfiers/Kea/blob/main/"
DESCRIPTION = ("Kea turns a data analysis into a website of small, linked, commentable pages of claims and "
               "evidence, reviewed in cycles by people and an AI agent.")

STYLE = """
:root{--fg:#1d2330;--muted:#5b6475;--line:#d9dde5;--bg:#ffffff;--soft:#f5f7fa;--accent:#4f6b1f;--accent2:#d9822b;--code:#f3f5f8}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--fg:#e6e9ef;--muted:#a3abba;--line:#323a48;--bg:#14181f;--soft:#1b212b;--accent:#a8c46a;--accent2:#f0a050;--code:#1f2632}}
:root[data-theme="dark"]{--fg:#e6e9ef;--muted:#a3abba;--line:#323a48;--bg:#14181f;--soft:#1b212b;--accent:#a8c46a;--accent2:#f0a050;--code:#1f2632}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:880px;margin:0 auto;padding:28px 16px 70px}
a{color:var(--accent)}
.hero{display:flex;justify-content:center;margin:10px 0 24px}
.hero img{width:min(420px,90%);height:auto;background:#fff;border-radius:14px;padding:14px 18px}
h1{font-size:30px;margin:10px 0 6px}
h2{font-size:22px;margin:38px 0 10px;padding-bottom:4px;border-bottom:1px solid var(--line)}
h3{font-size:17px;margin:22px 0 6px}
pre,code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13.5px}
pre{background:var(--code);border:1px solid var(--line);border-radius:8px;padding:12px 14px;overflow-x:auto;position:relative}
code{background:var(--code);padding:1px 4px;border-radius:4px}
pre code{background:none;padding:0}
.copy{position:absolute;top:8px;right:8px;font-size:12px;border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:6px;padding:2px 8px;cursor:pointer}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:14.5px}
th,td{border-bottom:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}
th{background:var(--soft)}
blockquote{border-left:4px solid var(--accent2);background:var(--soft);margin:12px 0;padding:6px 12px;border-radius:0 8px 8px 0}
.tag{display:inline-flex;align-items:center;gap:4px;color:#fff;font:700 12px system-ui,sans-serif;border-radius:11px;padding:1px 8px 1px 6px;white-space:nowrap}
.tag .ico{width:13px;height:13px}
footer{margin-top:50px;color:var(--muted);font-size:13px;text-align:center}
"""

SCRIPT = """
document.querySelectorAll("pre > code").forEach(function (code) {
  var button = document.createElement("button");
  button.className = "copy"; button.textContent = "copy";
  button.addEventListener("click", function () {
    navigator.clipboard.writeText(code.textContent).then(function () {
      button.textContent = "copied"; setTimeout(function () { button.textContent = "copy"; }, 1500);
    });
  });
  code.parentElement.appendChild(button);
});
"""


SITE_PAGES = ROOT / "doc" / "_site"          # Kea's own site pages (related work, …): also pages of the web site


def repository_links(page_html: str) -> str:
    """Relative links to doc/_site/<name>.md go to the web page <name>.html; other relative links to files in the
    repository go to GitHub; anchors and absolute URLs stay. Links to those pages on GitHub become local too."""
    page_html = re.sub(r'href="(?:https://github\.com/mfiers/Kea/blob/main/)?doc/_site/([\w-]+)\.md(#[^"]*)?"',
                       lambda match: f'href="{match.group(1)}.html{match.group(2) or ""}"', page_html)
    return re.sub(r'href="(?!https?:|mailto:|#|[\w-]+\.html[#"])([^"]+)"', lambda match: f'href="{GITHUB}{match.group(1)}"',
                  page_html)


def wrap(title: str, body: str, source: str, hero: bool) -> str:
    """A page of the web site around rendered Markdown."""
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<title>{html.escape(title)}</title>\n"
            f"<meta name=\"description\" content=\"{html.escape(DESCRIPTION)}\">\n"
            "<link rel=\"icon\" href=\"favicon.ico\">\n"
            f"<!-- Generated from {source} by src/build_web.py (make web). Do not edit by hand. -->\n"
            f"<style>{STYLE}</style>\n</head>\n<body>\n<main>\n"
            + ("<div class=\"hero\"><img src=\"logo.png\" alt=\"kea\"></div>\n" if hero else
               "<p><a href=\"index.html\">← Kea</a></p>\n")
            + f"{body}\n"
            "<footer>Kea · <a href=\"https://github.com/mfiers/Kea\">github.com/mfiers/Kea</a> · "
            f"this page is {source}</footer>\n</main>\n"
            f"<script>{SCRIPT}</script>\n</body>\n</html>\n")


def render(text: str) -> str:
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "toc"],
                             extension_configs={"toc": {"slugify": kea_help.slug}})
    return repository_links(kea_help.kinds_table(body, kea_help.plain_tag))


def build() -> str:
    """The front page (README.md) as HTML; README's help sections are refreshed first."""
    text = kea_help.readme_sync(README.read_text(encoding="utf-8"))
    if text != README.read_text(encoding="utf-8"):
        README.write_text(text, encoding="utf-8")
        print("README.md: help sections copied from src/kea/help/")
    text = re.sub(r"^<p align='center'><img src='branding/logo\.png'[^>]*></p>\s*", "", text)   # the hero instead
    return wrap("Kea", render(text), "README.md", hero=True)


def site_pages() -> dict[str, str]:
    """docs/<name>.html for each doc/_site/<name>.md (front matter title as the heading)."""
    import yaml
    pages = {}
    for source in sorted(SITE_PAGES.glob("*.md")):
        text = source.read_text(encoding="utf-8")
        header = {}
        if text.startswith("---\n"):
            front, text = text[4:].split("\n---\n", 1)
            header = yaml.safe_load(front) or {}
        title = str(header.get("title") or source.stem)
        intro = f"<p><i>{html.escape(str(header['short']))}</i></p>" if header.get("short") else ""
        pages[f"{source.stem}.html"] = wrap(f"{title} · Kea", f"<h1>{html.escape(title)}</h1>{intro}" + render(text),
                                            f"doc/_site/{source.name}", hero=False)
    return pages


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} from README.md")
    for name, page in site_pages().items():
        (OUT.parent / name).write_text(page, encoding="utf-8")
        print(f"wrote docs/{name} from doc/_site/")
