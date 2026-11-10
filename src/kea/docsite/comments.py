"""Comment layer on the built pages (adapted from the explained-project-site skill, feedback/site.py).

For every HTML page: the version line (git commit of the page's own source, linked to its commit page), the
"Changes to this page" history with diffs of the source, a static copy of the page's comment threads (readable
without the server), and the comment panel scripts. Threads are keyed on the node key (``project:id``) for
documentation pages, on ``code/<path>`` for code pages and on the page path otherwise, so a page can move without
losing its threads. Also writes feedback.html, the list of all comments.

Input: the built site, data/feedback/events.jsonl, git history.
Output: the same pages edited in place (generated files), report/site/_feedback/ assets, feedback.html.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from pathlib import Path

from kea.docsite.nodes import PROJECT_ROOT
from kea.docsite import mode
from kea.docsite.render import esc, prefix_for
from kea.feedback import states, store, tags

STATIC = Path(__file__).resolve().parents[1] / "feedback" / "static"
RECOGITO = "recogito-text-annotator-4.3.7.umd.js"
RECOGITO_CSS = "recogito-text-annotator-4.3.7.css"
STATUS_TEXT = {"open": "open", "answered": "answered", "page-changed": "page changed",
               "wont-fix": "won't fix", "resolved": "resolved", "planned": "in the plan", "marked": "marked"}
HISTORY_LIMIT = 15


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=PROJECT_ROOT)
    return result.stdout.strip() if result.returncode == 0 else ""


_FILE_LOG: dict | None = None        # path -> commits touching it, newest first (file_log); reset per build


def reset_file_log() -> None:
    """Forget the history read by file_log (the build calls this first: commits may have been made since)."""
    global _FILE_LOG
    _FILE_LOG = None


def file_log() -> dict:
    """{"log": {path: [(short commit, date, author, subject), …] newest first, following renames like git log
    --follow}, "dirty": paths with uncommitted changes or untracked}. One `git log` and one `git status` for the
    whole repository instead of three git processes per page."""
    global _FILE_LOG
    if _FILE_LOG is not None:
        return _FILE_LOG
    raw = _git("log", "-M", "-C", "--name-status", "--format=%x1e%h%x1f%ad%x1f%an%x1f%s%x1f%H", "--date=short")
    log: dict[str, list[tuple[str, str, str, str]]] = {}
    # as `git log --follow <path>` does for each path: a path keeps the history of its own name, and where it was
    # made by a rename it follows the old name further back. Newest first: tracking[name] = the paths (by their
    # name now) whose history that name holds at this point in time.
    tracking: dict[str, set[str]] = {}
    # where a path first appears in this log (added, or a copy this log did not see): (full commit, its name then).
    # What lies before is asked of git log --follow itself (history_html), which looks harder for copies.
    origin: dict[str, tuple[str, str]] = {}

    def add(name: str, commit: tuple) -> None:
        for path in tracking.setdefault(name, {name}):
            if path in origin:
                continue
            entries = log.setdefault(path, [])
            if not entries or entries[-1][0] != commit[0]:
                entries.append(commit)
    for record in filter(None, raw.split("\x1e")):     # (_git strips: \x1e counts as whitespace)
        head, _, files = record.partition("\n")
        parts = (head.split("\x1f") + ["", "", "", "", ""])[:5]
        commit, full = tuple(parts[:4]), parts[4]
        for line in files.strip("\n").splitlines():
            fields = line.split("\t")
            if len(fields) < 2:
                continue
            add(fields[-1], commit)
            if fields[0] == "A":
                for path in tracking.get(fields[-1], set()):
                    origin.setdefault(path, (full, fields[-1]))
            if fields[0][:1] in "RC" and len(fields) == 3:     # older commits knew it as fields[1] (a copy: its source)
                old, renamed_to = fields[1], fields[2]
                if fields[0].startswith("R"):
                    add(old, commit)              # seen from the old name: the file went away here
                moved = tracking.get(renamed_to, {renamed_to})
                tracking[renamed_to] = set()       # before this commit the new name held nothing of theirs
                tracking.setdefault(old, {old}).update(moved)
    status = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], capture_output=True,
                            text=True, cwd=PROJECT_ROOT)
    dirty = set()
    parts = status.stdout.split("\0") if status.returncode == 0 else []
    index = 0
    while index < len(parts):
        entry = parts[index]
        if len(entry) > 3:
            dirty.add(entry[3:])
            if entry[0] in "RC":                 # a rename carries its old name in the next field
                index += 1
        index += 1
    _FILE_LOG = {"log": log, "dirty": dirty, "origin": origin}
    return _FILE_LOG


def source_version(source: Path | None) -> str:
    """Short commit of the last change to `source` (HEAD for generated pages); '+edited' with uncommitted changes."""
    if source is None:              # a generated page: the commit the site is built from, +edited if doc/ differs
        head = _git("rev-parse", "--short", "HEAD")
        dirty = (subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "doc"], cwd=PROJECT_ROOT).returncode != 0
                 or bool(_git("ls-files", "--others", "--exclude-standard", "--", "doc")))
        return head + ("+edited" if dirty and head else "")
    relative = str(source.relative_to(PROJECT_ROOT))
    known = file_log()
    commits = known["log"].get(relative)
    if not commits:
        return "uncommitted"
    return commits[0][0] + ("+edited" if relative in known["dirty"] else "")


def history_html(source: Path, prefix: str) -> str:
    """'Changes to this page': one line per version (the release a change went into, or 'not released yet'), with
    the date and what each change was; the diffs themselves are on the commit pages under History."""
    from kea.docsite.versions import commit_labels
    relative = str(source.relative_to(PROJECT_ROOT))
    known = file_log()
    log = known["log"].get(relative, [])[:HISTORY_LIMIT]
    if relative in known["origin"] and len(log) < HISTORY_LIMIT and log:
        # before the commit that added it: whatever git log --follow finds (a copy's source); fixed, so cached
        from kea.docsite.changes import git_fixed
        full, name = known["origin"][relative]
        older = git_fixed("log", "--follow", f"-{HISTORY_LIMIT}", "--format=%h%x09%ad%x09%an%x09%s", "--date=short",
                          full, "--", name)
        tail = [tuple((line.split("\t") + ["", "", "", ""])[:4]) for line in older.splitlines() if line]
        log = (log + [entry for entry in tail if entry[0] != log[-1][0]])[:HISTORY_LIMIT]
    if not log:
        return ""
    labels = commit_labels()
    groups: list[tuple[str, list[tuple[str, str, str]]]] = []
    for commit, date, _author, subject in log:
        release = labels.get(commit[:7], "")
        release = "" if release.startswith("after ") else release
        if not groups or groups[-1][0] != release:
            groups.append((release, []))
        groups[-1][1].append((commit, date, subject))
    items = []
    for release, commits in groups:
        dates = sorted({date for _, date, _ in commits})
        when = dates[0] if len(dates) == 1 else f"{dates[0]} to {dates[-1]}"
        what = "; ".join(dict.fromkeys(subject for _, _, subject in commits))
        links = " ".join((f"<a href='{prefix}commits/{esc(commit)}.html'><code>{esc(commit)}</code></a>"
                          if mode.WITH_CHANGELOG else f"<code>{esc(commit)}</code>") for commit, _, _ in commits)
        badge = f"<span class='pill'>{esc(release)}</span>" if release else "<span class='pill'>not released yet</span>"
        items.append(f"<li>{badge} {esc(when)} · {esc(what)} <span class='help'>{links}</span></li>")
    return ("<section class='fb-history not-annotatable' id='history'><h2>Changes to this page</h2>"
            f"<p class='help'>Newest first, one line per version (at most {HISTORY_LIMIT} changes)"
            + (", with what changed in each; the commit links show the exact text." if mode.WITH_CHANGELOG else ".")
            + f"</p><ul class='page-versions'>{''.join(items)}</ul></section>")


def thread_static_html(thread: store.Thread, prefix: str, page_href: str | None = None) -> str:
    quote = f"<blockquote class='fb-quote'>{esc(thread.quote)}</blockquote>" if thread.quote else \
        "<p class='help'>about the whole page</p>"
    messages = [(thread.author, thread.text, thread.created_at)] + [(reply.author, reply.text, reply.created_at)
                                                                    for reply in thread.replies]
    body = "".join(f"<div class='fb-msg{' fb-claude' if author == 'claude' else ''}'><div class='fb-meta'><b>"
                   f"{'Claude' if author == 'claude' else esc(author)}</b> · {esc(created.replace('T', ' ')[:16])}"
                   f"</div><div class='fb-text'>{esc(text)}</div></div>" for author, text, created in messages)
    if thread.suggestion:
        diff_lines = thread.suggestion.get("diff", "").splitlines()[2:]
        body += (f"<details class='fb-suggestion' open><summary>Suggested edit of <code>"
                 f"{esc(thread.suggestion.get('path', ''))}</code></summary><pre class='fb-diff'>" + "".join(
                     f"<span class='{'add' if line.startswith('+') else 'del' if line.startswith('-') else 'hunk' if line.startswith('@@') else 'ctx'}'>"
                     f"{esc(line) or ' '}</span>" for line in diff_lines) + "</pre></details>")
    if thread.tags:
        quote += "<div class='fb-tags'>" + "".join(f"<span class='fb-tag'>{esc(name)}</span>" for name in thread.tags) + "</div>"
    if not thread.text:
        body = body.replace("<div class='fb-text'></div>", "", 1)
    status = ""
    if thread.status not in ("open", "marked"):
        commit = (f" · commit <a href='{prefix}commits/{esc(thread.commit.split('+')[0])}.html'><code>{esc(thread.commit)}</code></a>"
                  if thread.commit else "")
        status = (f"<div class='fb-statusline'>Marked {esc(STATUS_TEXT.get(thread.status, thread.status))} by "
                  f"{'Claude' if thread.status_by == 'claude' else esc(thread.status_by)}{commit}"
                  f"{(': ' + esc(thread.status_note)) if thread.status_note else ''}</div>")
    where = (f"<div class='fb-meta'><a href='{esc(page_href)}'>{esc(thread.page_title or thread.page)}</a></div>"
             if page_href else "")
    state, label = states.state_of(thread)
    people = "|".join(sorted({author.strip().lower() for author, _, _ in messages if author}))
    return (f"<div class='fb-thread fb-thread-{state}' id='fbs-{esc(thread.thread_id)}' data-people='|{esc(people)}|'"
            f"{(' data-orcid=' + chr(39) + esc(thread.author_id) + chr(39)) if getattr(thread, 'author_id', '') else ''}>"
            f"{where}<div class='fb-thread-head'>"
            f"<span class='fb-pill fb-state-{state}'>{esc(label)}"
            f"</span></div>{quote}{body}{status}</div>")


def version_box(version: str, prefix: str, source: Path | None, has_history: bool) -> str:
    commit = version.split("+")[0]
    linked = mode.WITH_CHANGELOG and commit and commit != "uncommitted"
    commit_html = (f"<a href='{prefix}commits/{esc(commit)}.html'><code>{esc(version)}</code></a>" if linked
                   else f"<code>{esc(version)}</code>")
    source_html = ""
    if source is not None:
        relative = source.relative_to(PROJECT_ROOT).as_posix()
        source_html = f"<div><b>Source:</b> <code>{esc(relative)}</code></div>"
    history = " · <a href='#history'>changes to this page</a>" if has_history else ""
    # a page from a file shows that file's last commit; a generated page the commit the whole site is built from
    label = "Site version" if source is None else "Page version"
    meaning = ("the commit the site was built from" if source is None else
               "not committed yet" if version == "uncommitted" else "the last commit that changed this page")
    edited = " (with uncommitted changes)" if "+edited" in version else ""
    return (f"<details class='fb-made not-annotatable'><summary>{label} {commit_html}</summary>{source_html}"
            f"<div><b>{label}:</b> {commit_html}: {meaning}{edited}{history}</div>"
            f"</details>")


def inject(site_dir: Path, pages: dict[str, tuple[str, Path | None]], events_path: Path | None = None,
           build_id: str = "", with_comments: bool = True) -> dict[str, int]:
    """pages: page path (relative to site root) -> (thread key, source file or None). build_id: this build's id,
    compared by cycle.js with the server's current build to offer a reload."""
    assets = site_dir / "_feedback"
    assets.mkdir(parents=True, exist_ok=True)
    for name in ("feedback.js", "feedback.css", "cycle.js", RECOGITO, RECOGITO_CSS, "marked-12.0.2.min.js"):
        shutil.copy2(STATIC / name, assets / name)
    (assets / "tags.json").write_text(json.dumps(tags.vocabulary(), ensure_ascii=False, indent=1))
    by_key: dict[str, list[store.Thread]] = {}
    for thread in store.threads(events_path):
        by_key.setdefault(thread.page, []).append(thread)
    site_commit = source_version(None)
    counts = {"pages": 0, "with_history": 0}
    for path in sorted(site_dir.rglob("*.html")):
        relative = path.relative_to(site_dir).as_posix()
        if relative.startswith("_feedback/"):
            continue
        text = path.read_text(encoding="utf-8")
        if not re.search(r"<main[\s>]", text) or "<script id='fb-script'" in text:     # <main> or <main class=…>
            continue
        key, source = pages.get(relative, (relative, None))
        prefix = prefix_for(relative)
        version = source_version(source) if source else site_commit
        title_start, title_end = text.find("<title>"), text.find("</title>")
        title = html.unescape(text[title_start + 7:title_end]) if 0 <= title_start < title_end else relative
        history = history_html(source, prefix) if source else ""
        counts["with_history"] += bool(history)
        # the page version belongs to its history: right under "Changes to this page" (alone when there is none)
        versionline = f"<div class='fb-versionline'>{version_box(version, prefix, source, False)}</div>"
        extra = (history.replace("<h2>Changes to this page</h2>", "<h2>Changes to this page</h2>" + versionline, 1)
                 if history else versionline)
        page_threads = sorted(by_key.get(key, []), key=states.sort_key) if with_comments else []
        if page_threads:
            active = [thread for thread in page_threads if states.state_of(thread)[0] != "resolved"]
            resolved = [thread for thread in page_threads if states.state_of(thread)[0] == "resolved"]
            extra += ("<section class='fb-static not-annotatable'><h2>Comments on this page</h2>"
                      "<p class='help'>Copy made when the site was built; with the server running, live comments are in "
                      "the Comments panel. Open comments first, then those in a plan, those addressed in a version, "
                      "and the resolved ones.</p>" + "".join(thread_static_html(thread, prefix) for thread in active)
                      + (f"<details class='fb-resolved'><summary>{len(resolved)} resolved comment(s)</summary>"
                         + "".join(thread_static_html(thread, prefix) for thread in resolved) + "</details>"
                         if resolved else "") + "</section>")
        text = text.replace("</main>", f"{extra}</main>", 1)
        if with_comments:
            text = text.replace("</body>",
                                f"<link rel='stylesheet' href='{prefix}_feedback/{RECOGITO_CSS}'>"
                                f"<link rel='stylesheet' href='{prefix}_feedback/feedback.css'>"
                                f"<script src='{prefix}_feedback/{RECOGITO}'></script>"
                                f"<script id='fb-script' src='{prefix}_feedback/feedback.js' data-page='{esc(key)}' "
                                f"data-commit='{esc(version)}' data-title='{esc(title)}'></script>"
                                f"<script id='fb-cycle' src='{prefix}_feedback/cycle.js' "
                                f"data-prefix='{prefix}'></script></body>", 1)
        else:
            text = text.replace("</body>", f"<link rel='stylesheet' href='{prefix}_feedback/feedback.css'></body>", 1)
        path.write_text(text, encoding="utf-8")
        counts["pages"] += 1
    return counts


def experiment_of(page_key: str, experiments) -> str:
    """The experiment a thread belongs to ('' = whole site): node keys 'experiment:id' and pages
    'experiment/…html' (map, relations) belong to that experiment; plan, home, changes, code to the whole site."""
    if ":" in page_key and page_key.split(":", 1)[0] in experiments:
        return page_key.split(":", 1)[0]
    first = page_key.split("/", 1)[0]
    return first if "/" in page_key and first in experiments else ""


def overview_body(key_to_href: dict[str, str], experiments=(), events_path: Path | None = None) -> str:
    threads = store.threads(events_path)
    order = {"open": 0, "planned": 0.5, "answered": 1, "page-changed": 1, "wont-fix": 2, "resolved": 3}
    counts: dict[str, int] = {}
    for thread in threads:
        counts[thread.status] = counts.get(thread.status, 0) + 1
    summary = ", ".join(f"{count} {STATUS_TEXT.get(status, status)}" for status, count in
                        sorted(counts.items(), key=lambda item: order.get(item[0], 9))) or "none yet"
    groups: dict[str, list] = {}
    for thread in threads:
        groups.setdefault(experiment_of(thread.page, experiments), []).append(thread)
    sections = []
    for experiment in sorted(groups, key=lambda name: (name == "", name)):
        members = sorted(groups[experiment], key=states.sort_key)
        open_count = sum(thread.status in ("open", "planned") for thread in members)
        heading = (f"Experiment <a href='{esc(experiment)}/home.html'>{esc(experiment)}</a>" if experiment
                   else "Whole site (plan, home, change log, code)")
        sections.append(f"<h2>{heading} <span class='help'>{len(members)} comment(s), {open_count} open or "
                        f"planned</span></h2>"
                        + "".join(thread_static_html(thread, "", key_to_href.get(thread.page, thread.page))
                                  for thread in members))
    return ("<h1>Comments and questions</h1>"
            "<div class='short'>Every comment left on the site, grouped by experiment, open ones first. Select text on "
            "any page and press “Comment”, or use the Comments button at the bottom right. Claude folds new comments "
            "into the plan of the current review cycle and implements them when a reader presses “Implement the "
            "plan”; each answer names the commit that changed the page.</div>"
            f"<p>Comments so far: {esc(summary)}.</p><div class='not-annotatable'>"
            + ("".join(sections) or "<p class='help'>No comments yet.</p>") + "</div>")
