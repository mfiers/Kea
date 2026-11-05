"""Code pages: every git-tracked source file as a page with line anchors, symbols and the pages that point to it.

Shown: git-tracked files under src/, tests/, config/, plus Makefile and pyproject.toml; never vendored files,
lock files, .env or data. Python symbols (functions, classes, methods) come from ``ast``; links
``[[code:path#symbol]]`` and ``sources: - code: path#symbol`` jump to the symbol's first line (``#L-<n>``).

Input: git ls-files, the files themselves, the tree (for "Used on pages").
Output: report/site/code/<path>.html and code/index.html (via the builder).
"""
from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.util import ClassNotFound

from kea.docsite.nodes import PROJECT_ROOT
from kea.docsite.render import esc

from kea.config import SETTINGS  # noqa: E402

SHOWN_PREFIXES = tuple(SETTINGS.get("code_paths") or ("src/", "tests/", "config/", "packages/"))   # kea.yaml
SHOWN_FILES = tuple(SETTINGS.get("code_files") or ("Makefile", "pyproject.toml", "kea.yaml"))
EXCLUDED_PARTS = ("static/recogito", "static/marked", "static/cytoscape", "__pycache__", ".env", "uv.lock")
MAX_BYTES = 400_000


@dataclass
class CodeFile:
    path: str
    text: str
    docstring: str = ""
    symbols: dict[str, int] = field(default_factory=dict)   # name or Class.method -> first line


def tracked_files(project: Path = PROJECT_ROOT) -> list[str]:
    output = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=project).stdout.split()
    shown = []
    for path in output:
        if not (path.startswith(SHOWN_PREFIXES) or path in SHOWN_FILES):
            continue
        if any(part in path for part in EXCLUDED_PARTS):
            continue
        full = project / path
        if full.is_file() and full.stat().st_size <= MAX_BYTES:
            shown.append(path)
    return sorted(shown)


def parse(path: str, project: Path = PROJECT_ROOT) -> CodeFile:
    text = (project / path).read_text(encoding="utf-8", errors="replace")
    code_file = CodeFile(path=path, text=text)
    if path.endswith(".py"):
        try:
            module = ast.parse(text)
        except SyntaxError:
            return code_file
        code_file.docstring = ast.get_docstring(module) or ""
        for item in module.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                code_file.symbols[item.name] = item.lineno
            if isinstance(item, ast.ClassDef):
                for member in item.body:
                    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        code_file.symbols[f"{item.name}.{member.name}"] = member.lineno
    elif Path(path).name == "Makefile":
        for number, line in enumerate(text.splitlines(), start=1):
            if line and not line.startswith(("\t", "#", " ", ".")) and ":" in line and "=" not in line.split(":")[0]:
                for target in line.split(":")[0].split():
                    code_file.symbols.setdefault(target, number)
    return code_file


class CodeIndex:
    def __init__(self, project: Path = PROJECT_ROOT):
        self.files = {path: parse(path, project) for path in tracked_files(project)}

    def page_of(self, path: str) -> str:
        return f"code/{path}.html"

    def href(self, target: str, prefix: str) -> str | None:
        """Link for 'path', 'path#symbol', 'path#L12' or 'make target'; None when unknown."""
        if target.startswith("make "):
            makefile = self.files.get("Makefile")
            line = makefile.symbols.get(target[5:].strip()) if makefile else None
            return f"{prefix}code/Makefile.html#L-{line}" if line else None
        path, _, anchor = target.partition("#")
        path = path.strip()
        code_file = self.files.get(path)
        if code_file is None:
            return None
        href = f"{prefix}{self.page_of(path)}"
        if anchor.startswith("L") and anchor[1:].isdigit():
            return f"{href}#L-{anchor[1:]}"
        if anchor:
            line = code_file.symbols.get(anchor)
            return f"{href}#L-{line}" if line else None
        return href


def highlighted(code_file: CodeFile) -> str:
    try:
        lexer = get_lexer_for_filename(code_file.path, stripnl=False)
    except ClassNotFound:
        lexer = TextLexer(stripnl=False)
    if Path(code_file.path).name == "Makefile":
        from pygments.lexers import MakefileLexer
        lexer = MakefileLexer(stripnl=False)
    formatter = HtmlFormatter(linenos="table", lineanchors="L", anchorlinenos=True, cssclass="code-table")
    rendered = highlight(code_file.text, lexer, formatter)
    return rendered.replace("<td class=\"linenos\">", "<td class=\"linenos not-annotatable\">")


def pygments_css() -> str:
    return HtmlFormatter(style="friendly").get_style_defs(".code-table")


def code_body(code_file: CodeFile, prefix: str, used_on: list[tuple[str, str]]) -> str:
    parts = [f"<h1><code>{esc(code_file.path)}</code></h1>"]
    if code_file.docstring:
        parts.append(f"<div class='short'><pre style='background:none;padding:0;white-space:pre-wrap'>"
                     f"{esc(code_file.docstring)}</pre></div>")
    if code_file.symbols:
        items = "".join(f"<li><a href='#L-{line}'><code>{esc(name)}</code></a> <span class='help'>line {line}</span></li>"
                        for name, line in sorted(code_file.symbols.items(), key=lambda item: item[1]))
        parts.append(f"<details class='box not-annotatable'><summary>Contents ({len(code_file.symbols)})</summary>"
                     f"<ul>{items}</ul></details>")
    if used_on:
        links = ", ".join(f"<a href='{esc(href)}'>{esc(text)}</a>" for text, href in used_on)
        parts.append(f"<div class='box not-annotatable'><b>Pages that point here:</b> {links}</div>")
    parts.append(f"<div class='code-wrap'>{highlighted(code_file)}</div>")
    return "".join(parts)


def index_body(index: CodeIndex, prefix: str) -> str:
    groups: dict[str, list[str]] = {}
    for path in index.files:
        groups.setdefault(str(Path(path).parent), []).append(path)
    parts = ["<h1>Code</h1><p class='help'>Every source file in git (data, secrets, lock files and vendored "
             "libraries excluded). Comments on code work like comments on any page.</p>"]
    for folder in sorted(groups):
        items = "".join(
            f"<li><a href='{prefix}{index.page_of(path)}'><code>{esc(Path(path).name)}</code></a>"
            f"{' <span class=help>— ' + esc(index.files[path].docstring.splitlines()[0]) + '</span>' if index.files[path].docstring else ''}</li>"
            for path in sorted(groups[folder]))
        parts.append(f"<h3><code>{esc(folder)}/</code></h3><ul>{items}</ul>")
    return "".join(parts)
