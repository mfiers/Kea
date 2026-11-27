"""An experiment without questions opens with "Start here: write the brief" (pages.start_box, Kea 1.33.1): the box
on its page, the brief tag (tags.py) that the box sends, and the words per pace; gone once a question exists."""
from __future__ import annotations

import json
import subprocess

from kea.docsite import nodes
from kea.docsite.pages import SiteRenderer as Pages
from kea.feedback import tags

from test_graph import SCHEMA, _doc, _page
from test_kea_example import run


def _empty(tmp_path, pace: str, body: str = "") -> nodes.Tree:
    doc = tmp_path / "doc"
    doc.mkdir(parents=True)
    (doc / "_schema.yaml").write_text(SCHEMA)
    (tmp_path / "kea.yaml").write_text(f"title: T\npace: {pace}\n")
    _page(doc, "p/experiment/home.md", "id: home\ntype: experiment\ntitle: E\nshort: An experiment.\nstatus: open")
    if body:
        path = doc / "p/experiment/home.md"
        path.write_text(path.read_text() + body)
    return nodes.load_tree(doc)


def test_the_brief_is_a_whole_page_proposal_on_experiments():
    brief = next(tag for tag in tags.vocabulary({})["tags"] if tag["name"] == "brief")
    assert brief["group"] == "propose" and brief["types"] == ["experiment"] and brief["scope"] == "page"
    assert brief["needs_text"] and "## Brief" in brief["instruction"] and "word for word" in brief["instruction"]


def test_an_empty_experiment_shows_start_here_per_pace(tmp_path):
    tree = _empty(tmp_path / "d", "design")
    html = Pages(tree, tmp_path / "site").start_box(tree.nodes["p:home"])
    assert "Start here: write the brief" in html and "data-propose='brief'" in html
    assert "<b>Design</b>" in html and "<b>Sign</b>" in html and "Write the brief" in html
    guided = _empty(tmp_path / "g", "guided")
    html = Pages(guided, tmp_path / "site").start_box(guided.nodes["p:home"])
    assert "<b>Questions</b>" in html and "<b>Design</b>" not in html
    free = _empty(tmp_path / "f", "free")
    assert "you sign" not in Pages(free, tmp_path / "site").start_box(free.nodes["p:home"])


def test_a_given_brief_says_the_design_comes_next(tmp_path):
    tree = _empty(tmp_path, "design", "\n## Brief\n\nMark, 27 Nov 2026: find out X.\n")
    html = Pages(tree, tmp_path / "site").start_box(tree.nodes["p:home"])
    assert "The brief is given: the design comes next" in html and "Add to the brief" in html


def test_the_box_goes_once_a_question_exists(tmp_path):
    tree = nodes.load_tree(_doc(tmp_path))
    assert Pages(tree, tmp_path / "site").start_box(tree.nodes["p:home"]) == ""


def test_the_built_site_starts_an_empty_experiment_with_the_brief(tmp_path):
    project = tmp_path / "example"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    run(["init", "--title", "Example", "--experiment", "first"], project)
    built = run(["build"], project)
    assert built.returncode == 0, built.stdout + built.stderr
    site = project / "report" / "site"
    page = (site / "first" / "home.html").read_text()
    assert "class='kea-start not-annotatable' data-propose='brief'" in page
    vocabulary = json.loads((site / "_feedback" / "tags.json").read_text())
    assert any(tag["name"] == "brief" for tag in vocabulary["tags"])          # the hub checks tags against this file
