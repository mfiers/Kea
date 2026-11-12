"""Tests for the site fixes of 2026-11-07: generated-link check, diff layout, release lines without empty fields,
run links only to run pages that exist, tag_prefix, changes_since and the template-placeholder note."""
from __future__ import annotations

import subprocess
from pathlib import Path

from kea import config
from kea.config import PACKAGE_DIR
from kea.docsite import changes, history, linkcheck, nodes, versions


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_linkcheck_reports_missing_pages_only(tmp_path):
    write(tmp_path / "index.html", "<a href='a.html'>a</a><a href='gone.html#x'>gone</a><a href='https://x.org'>x</a>"
                                   "<a href='#top'>top</a><a href='dir/'>dir</a><img src='_feedback/x.css'>")
    write(tmp_path / "a.html", "<a href='../outside.html'>out</a>")
    write(tmp_path / "dir" / "index.html", "")
    # link-like text in highlighted code is text, not a tag
    write(tmp_path / "code.html", "<pre><span class='s'>&lt;a href='</span>{prefix}missing.html'&gt;</pre>")
    problems = linkcheck.broken_links(tmp_path)
    assert problems == ["a.html: link to ../outside.html (no such file in the site)",
                        "index.html: link to gone.html#x (no such file in the site)"]


def test_diff_lines_are_blocks_without_newlines_between():
    html = changes.diff_html("diff --git a/x b/x\n@@ -1 +1 @@\n-old\n+new\n context\n")
    assert "\n" not in html
    assert "<span class='del'>-old</span><span class='add'>+new</span><span class='ctx'> context</span>" in html


def test_run_link_only_when_the_run_page_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(changes, "DOC", tmp_path)
    write(tmp_path / "_changes" / "2026-11-07-a.md", "---\ntitle: a run\n---\n")
    assert changes.run_link("2026-11-07-a", "../") == "<a href='../changes/2026-11-07-a.html'>2026-11-07-a</a>"
    assert changes.run_link("2026-11-06-i", "../") == "2026-11-06-i"


def test_release_line_leaves_out_missing_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(changes, "DOC", tmp_path)
    bare = versions.Release(tag="v1.0.0", version="1.0.0", experiment="", commit="a" * 40, date="")
    assert history.release_meta(bare, "") == "released"
    full = versions.Release(tag="v1.1.0", version="1.1.0", experiment="", commit="b" * 40,
                            date="2026-11-07T10:00:00+01:00", run="r1", kind="minor", reason="new results")
    assert history.release_meta(full, "") == "released 2026-11-07 10:00 · minor · run r1 · new results"


def _git(repository: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repository, capture_output=True, text=True, check=True).stdout


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "test@example.org")
    _git(repository, "config", "user.name", "Test")
    for number in range(3):
        write(repository / f"file{number}.txt", str(number))
        _git(repository, "add", ".")
        _git(repository, "commit", "-q", "-m", f"commit {number}")
    return repository


def test_tag_prefix_separates_site_releases_from_software_tags(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    _git(repository, "tag", "-a", "v1.10.1", "-m", "software release")
    _git(repository, "tag", "-a", "site/v0.1.0", "-m", "Release v0.1.0\n\nRun: r1\nKind: minor\n")
    _git(repository, "tag", "-a", "site/roadmap/v0.1.0", "-m", "Release v0.1.0\n")
    monkeypatch.setattr(versions, "PROJECT_ROOT", repository)
    monkeypatch.setitem(config.SETTINGS, "tag_prefix", "")
    assert [release.tag for release in versions.releases("")] == ["v1.10.1"]
    monkeypatch.setitem(config.SETTINGS, "tag_prefix", "site/")
    site = versions.releases("")
    assert [(release.tag, release.label, release.run) for release in site] == [("site/v0.1.0", "v0.1.0", "r1")]
    assert [release.experiment for release in versions.releases(None)] == ["", "roadmap"]
    assert versions.tag_name("0.2.0") == "site/v0.2.0"
    assert versions.tag_name("0.2.0", "roadmap") == "site/roadmap/v0.2.0"


def test_changes_since_limits_commit_pages(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    first = _git(repository, "rev-list", "--max-parents=0", "HEAD").strip()
    monkeypatch.setattr(changes, "PROJECT_ROOT", repository)
    assert [commit.subject for commit in changes.all_commits()] == ["commit 2", "commit 1", "commit 0"]
    monkeypatch.setitem(config.SETTINGS, "changes_since", first)
    assert [commit.subject for commit in changes.all_commits()] == ["commit 2", "commit 1"]


def test_placeholder_phrases_are_still_in_the_template():
    """The note fires on kea init's own sentences; if the template is reworded, this list must follow."""
    template = " ".join((PACKAGE_DIR / "templates" / "home.md").read_text().split())
    for phrase in nodes.TEMPLATE_PLACEHOLDERS:
        assert phrase in template


def test_linkcheck_accepts_data_links(tmp_path):
    """Review mode links data as files/<path> (served by kea serve or the hub); local mode links the project file."""
    site = tmp_path / "site"
    write(site / "index.html", "<a href='files/data/x.tsv'>x</a>")
    write(site / "result" / "r.html", "<a href='../files/data/x.tsv'>x</a><a href='../../data/y.tsv'>y</a>"
                                      "<a href='../../data/missing.tsv'>m</a>")
    write(tmp_path / "data" / "y.tsv", "a\n")
    assert linkcheck.broken_links(site) == ["result/r.html: link to ../../data/missing.tsv (no such file in the site)"]


def test_no_links_to_commits_before_changes_since(tmp_path, monkeypatch):
    """Commits at or before changes_since have no page, so a page's version box shows them unlinked."""
    from kea.docsite import comments, mode
    repository = _repository(tmp_path)
    first = _git(repository, "rev-list", "--max-parents=0", "HEAD").strip()
    monkeypatch.setattr(changes, "PROJECT_ROOT", repository)
    monkeypatch.setitem(config.SETTINGS, "changes_since", first)
    monkeypatch.setattr(mode, "WITH_CHANGELOG", True)
    changes.commit_page_shorts.cache_clear()
    try:
        old = _git(repository, "rev-parse", "--short", first).strip()
        new = _git(repository, "rev-parse", "--short", "HEAD").strip()
        assert "commits/" not in comments.version_box(old, "", None, False)
        assert f"commits/{new}.html" in comments.version_box(new, "", None, False)
    finally:
        changes.commit_page_shorts.cache_clear()
