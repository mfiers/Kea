"""'What changed' pages: one page per agent run, one page per commit.

A run is a Markdown file ``doc/_changes/<run id>.md`` (written by the agent at the end of the run: asked,
changed, findings, not done). Its commits are those whose message carries the trailer ``Run: <run id>``.
Generated per run: the commits; documentation pages added, changed or removed (with the Markdown diff);
status changes of pages (front matter before the run vs after it); comment threads answered by the run's commits.

A commit answers a comment thread when a status event of that thread names the commit, or the commit message has
``Answers-comment: <thread id>``.

Input: doc/_changes/*.md, git history, comment threads (feedback.store).
Output: HTML bodies for changes/<run>.html, changes/index.html, commits/<sha>.html (written by the builder).
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from kea.docsite.nodes import DOC, PROJECT_ROOT, Node, Tree, safe_yaml, split_front_matter
from kea.docsite.render import esc, tagline
from kea.feedback import store

DIFF_LINE_LIMIT = 500


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=PROJECT_ROOT)
    return result.stdout if result.returncode == 0 else ""


GIT_CACHE = PROJECT_ROOT / "report" / ".cache" / "git"
FULL_SHA = re.compile(r"[0-9a-f]{40}")
_SOURCES: dict[int, dict[Path, Node]] = {}


def reset_caches() -> None:
    _SOURCES.clear()


def git_fixed(*args: str) -> str:
    """git for output that cannot change: every revision named by its full id (show, diff between two commits).
    Kept in report/.cache/git/ between builds, so a build after a small commit runs git only for the new commits."""
    before_paths = list(args[1:args.index("--")] if "--" in args else args[1:])
    revisions = [arg for arg in before_paths if not arg.startswith("-")]
    fixed = lambda arg: bool(FULL_SHA.fullmatch(arg) or re.fullmatch(r"[0-9a-f]{40}:.+", arg))   # noqa: E731
    if not revisions or not all(fixed(arg) for arg in revisions):
        return git(*args)
    key = hashlib.sha256("\x1f".join(args).encode()).hexdigest()
    cached = GIT_CACHE / key[:2] / key
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    output = git(*args)
    if output:
        cached.parent.mkdir(parents=True, exist_ok=True)
        ignore = GIT_CACHE.parent / ".gitignore"          # the cache ignores itself, also in projects made before 1.26
        if not ignore.exists():
            ignore.write_text("*\n")
        temporary = cached.with_suffix(".tmp")
        temporary.write_text(output, encoding="utf-8")
        temporary.replace(cached)
    return output


@dataclass
class Commit:
    short: str
    full: str
    date: str
    author: str
    subject: str
    body: str
    run: str = ""
    answers: list[str] = field(default_factory=list)


def all_commits() -> list[Commit]:
    """Every commit, newest first; only those after kea.yaml's ``changes_since`` commit when it is set (for a
    repository whose early history belongs to something else)."""
    from kea.config import SETTINGS
    since = str(SETTINGS.get("changes_since") or "")
    revision_range = [f"{since}..HEAD"] if since else []
    log = git("log", "--format=%h%x1f%H%x1f%ad%x1f%an%x1f%s%x1f%b%x1e", "--date=format:%Y-%m-%d %H:%M",
              *revision_range)
    commits = []
    for record in log.split("\x1e"):
        fields = record.strip("\n").split("\x1f")
        if len(fields) < 6:
            continue
        commit = Commit(*fields[:6])
        run = re.search(r"^Run:\s*(\S+)", commit.body, flags=re.M)
        commit.run = run.group(1) if run else ""
        commit.answers = re.findall(r"^Answers-comment:\s*(\S+)", commit.body, flags=re.M)
        commits.append(commit)
    return commits


def run_link(run_id: str, prefix: str) -> str:
    """A run id, linked to its 'What changed' page only when doc/_changes/<run>.md exists (else plain text)."""
    if run_id and (DOC / "_changes" / f"{run_id}.md").exists():
        return f"<a href='{prefix}changes/{esc(run_id)}.html'>{esc(run_id)}</a>"
    return esc(run_id)


def threads_answered(commit: Commit, threads: list[store.Thread]) -> list[store.Thread]:
    from kea.docsite import mode
    if mode.MODE == "public":                      # comment threads never leave in a public copy
        return []
    return [thread for thread in threads
            if thread.thread_id in commit.answers
            or (thread.commit and thread.commit.split("+")[0] in (commit.short, commit.full))]


def diff_html(diff: str) -> str:
    lines = diff.splitlines()
    shown = []
    for line in lines[:DIFF_LINE_LIMIT]:
        if line.startswith(("index ", "new file", "similarity", "rename", "deleted file")):
            continue
        css = ("add" if line.startswith("+") and not line.startswith("+++") else
               "del" if line.startswith("-") and not line.startswith("---") else
               "hunk" if line.startswith(("@@", "diff --git", "+++", "---")) else "")
        shown.append(f"<span class='{css or 'ctx'}'>{esc(line) or ' '}</span>")
    if len(lines) > DIFF_LINE_LIMIT:
        shown.append(f"<span class='hunk'>… {len(lines) - DIFF_LINE_LIMIT} more lines</span>")
    return f"<pre class='diff'>{''.join(shown)}</pre>"      # every span is display:block (render.py CSS)


def file_link(path: str, tree: Tree, code_href, prefix: str) -> str:
    """A changed file, linked to the page readers see (doc node) or its code page."""
    sources = _SOURCES.get(id(tree))
    if sources is None:                  # resolved once per build, not once per file per commit
        sources = _SOURCES[id(tree)] = {node.source.resolve(): node for node in tree.nodes.values()}
    node = sources.get((PROJECT_ROOT / path).resolve())
    if node is not None:
        return tagline(node, prefix)
    href = code_href(path, prefix)
    return f"<a href='{esc(href)}'><code>{esc(path)}</code></a>" if href else f"<code>{esc(path)}</code>"


def commit_body(commit: Commit, tree: Tree, threads: list[store.Thread], code_href, prefix: str) -> str:
    files = git_fixed("show", "--format=", "--name-status", commit.full).strip().splitlines()
    file_items = "".join(f"<li><code>{esc(line.split(chr(9))[0])}</code> "
                         f"{file_link(line.split(chr(9))[-1], tree, code_href, prefix)}</li>" for line in files)
    answered = threads_answered(commit, threads)
    answered_html = ("".join(f"<li><a href='{prefix}feedback.html#fbs-{esc(thread.thread_id)}'>{esc(thread.thread_id)}</a>"
                             f" on {esc(thread.page_title or thread.page)}: {esc(thread.text[:160])}</li>"
                             for thread in answered))
    run_html = (f"<div><b>Run:</b> {run_link(commit.run, prefix)}</div>" if commit.run else "")
    from kea.config import SETTINGS
    from kea.docsite import mode
    excluded = [":(exclude)uv.lock"]
    if mode.MODE == "public":                      # data files (and the comment logs) are never shown in a public copy
        excluded += [":(exclude)data", f":(exclude){SETTINGS['feedback_dir']}", ":(exclude)doc/_cycles"]
    diff = git_fixed("show", "--format=", "--unified=2", commit.full, "--", ".", *excluded)
    return (f"<h1>Commit <code>{esc(commit.short)}</code></h1><div class='short'>{esc(commit.subject)}</div>"
            f"<div class='box'><div><b>Date:</b> {esc(commit.date)} · <b>author:</b> {esc(commit.author)}</div>"
            f"{run_html}<div><b>Full id:</b> <code>{esc(commit.full)}</code></div></div>"
            + (f"<pre>{esc(commit.body.strip())}</pre>" if commit.body.strip() else "")
            + (f"<h2>Comments this commit answered</h2><ul>{answered_html}</ul>" if answered else "")
            + f"<h2>Files</h2><ul>{file_items}</ul><h2>Diff</h2><div class='not-annotatable'>{diff_html(diff)}</div>")


@dataclass
class Run:
    id: str
    title: str
    date: str
    body: str
    source: Path
    commits: list[Commit] = field(default_factory=list)


def load_runs(commits: list[Commit]) -> list[Run]:
    runs = []
    for source in sorted((DOC / "_changes").glob("*.md")):
        header, body = split_front_matter(source.read_text(encoding="utf-8"), source)
        run_id = source.stem
        runs.append(Run(id=run_id, title=str(header.get("title", run_id)), date=str(header.get("date", "")),
                        body=body, source=source, commits=[commit for commit in commits if commit.run == run_id]))
    return sorted(runs, key=lambda run: (run.date, run.id), reverse=True)


def _status_at(revision: str, path: str) -> str | None:
    text = git_fixed("show", f"{revision}:{path}")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 4)
    try:
        return (safe_yaml(text[4:end]) or {}).get("status")
    except yaml.YAMLError:
        return None


def run_generated(run: Run, tree: Tree, threads: list[store.Thread], code_href, prefix: str) -> str:
    """Commits, documentation pages changed (with diffs), status changes and answered comments of one run."""
    if not run.commits:
        return "<p class='help'>No commits carry this run's trailer yet (uncommitted run).</p>"
    oldest, newest = run.commits[-1], run.commits[0]
    base = git("rev-parse", "--verify", "--quiet", f"{oldest.full}^").strip()
    commit_items = "".join(f"<li><a href='{prefix}commits/{esc(commit.short)}.html'><code>{esc(commit.short)}</code></a> "
                           f"{esc(commit.date)} · {esc(commit.subject)}</li>" for commit in run.commits)
    if base:
        changed = git_fixed("diff", "--name-status", base, newest.full, "--", "doc/").strip()
    else:
        changed = git_fixed("show", "--format=", "--name-status", newest.full, "--", "doc/").strip()
    sections: dict[str, list[str]] = {"A": [], "M": [], "D": []}
    status_rows = []
    for line in changed.splitlines():
        kind, path = line.split("\t")[0][0], line.split("\t")[-1]
        diff = git_fixed("diff", base, newest.full, "--", path) if base else git_fixed("show", "--format=", newest.full, "--", path)
        item = (f"<li>{file_link(path, tree, code_href, prefix)}"
                f"<details><summary class='help'>show the change</summary>{diff_html(diff)}</details></li>")
        sections.setdefault(kind, []).append(item)
        if path.endswith(".md") and kind == "M":
            before, after = _status_at(base, path), _status_at(newest.full, path)
            if before != after:
                status_rows.append(f"<tr><td>{file_link(path, tree, code_href, prefix)}</td><td>{esc(before)}</td>"
                                   f"<td>{esc(after)}</td></tr>")
    names = {"A": "Pages added", "M": "Pages changed", "D": "Pages removed"}

    def sort_key(item: str) -> tuple:
        match = re.search(r">([A-Z])(\d+)</a>", item)
        return (0, match.group(1), int(match.group(2))) if match else (1, item, 0)
    pages_html = ""
    for kind, items in sections.items():
        if not items:
            continue
        listing = f"<ul>{''.join(sorted(items, key=sort_key))}</ul>"
        if len(items) > 12:
            listing = f"<details><summary>show all {len(items)}</summary>{listing}</details>"
        pages_html += f"<h3>{names.get(kind, kind)} ({len(items)})</h3>{listing}"
    answered = {thread.thread_id: thread for commit in run.commits for thread in threads_answered(commit, threads)}
    answered_html = "".join(f"<li><a href='{prefix}feedback.html#fbs-{esc(thread_id)}'>{esc(thread_id)}</a>: "
                            f"{esc(thread.text[:200])} <span class='pill s-{esc(thread.status)}'>{esc(thread.status)}</span></li>"
                            for thread_id, thread in answered.items())
    return ("<div class='not-annotatable'>"
            f"<h2>Commits ({len(run.commits)})</h2><ul>{commit_items}</ul>"
            + (f"<h2>Status changes</h2><table><tr><th>page</th><th>before</th><th>after</th></tr>{''.join(status_rows)}</table>"
               if status_rows else "")
            + f"<h2>Documentation changes</h2>{pages_html or '<p class=help>none</p>'}"
            + f"<h2>Comments answered</h2>{'<ul>' + answered_html + '</ul>' if answered_html else '<p class=help>none</p>'}"
            + "</div>")
