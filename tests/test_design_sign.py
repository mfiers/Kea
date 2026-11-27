"""pace: design, "Sign this design" on a question's page (Kea 1.33.2): which pages one press signs
(graph.question_design), the page that shows them with the versions to sign (pages.design_sign_html), and the
signatures kea sign writes from it, each marked batch: <question> (signing.apply_thread), with kea check refusing
a batch mark that the thread does not back."""
from __future__ import annotations

import types

from kea.docsite import graph, identity, nodes, signing
from kea.docsite.pages import SiteRenderer
from kea.feedback import store

from test_design_pace import _plan_only, _sign
from test_graph import _doc, _page


def _design(tmp_path):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("title: T\npace: design\n")
    _plan_only(doc)
    return doc


def _ids(pages):
    return [node.id for node in pages]


def test_one_press_signs_the_questions_whole_design_top_down(tmp_path):
    doc = _design(tmp_path)
    tree = nodes.load_tree(doc)
    assert _ids(graph.question_design(tree, tree.nodes["p:q-a"])) == ["home", "p-a", "q-a", "h-a", "s-a"]
    _sign(doc, "experiment/home.md", "premise/p-a.md")
    tree = nodes.load_tree(doc)
    assert _ids(graph.question_design(tree, tree.nodes["p:q-a"])) == ["q-a", "h-a", "s-a"]   # signed: not again


def test_the_batch_holds_no_results_conclusions_or_other_questions(tmp_path):
    doc = _doc(tmp_path)                                    # S1 done, R1 and C1 written, nothing signed
    (tmp_path / "kea.yaml").write_text("title: T\npace: design\n")
    _page(doc, "p/question/q-b.md", "id: q-b\ntype: question\ntitle: Then?\nshort: Next.\nparent: home\nstatus: open")
    _page(doc, "p/step/s-b.md", "id: s-b\ntype: step\ntitle: Build on S1\nshort: Uses it.\nparent: q-b\n"
          "status: planned\nrelations:\n  relies_on: [s-a, c-a]")
    tree = nodes.load_tree(doc)
    first = _ids(graph.question_design(tree, tree.nodes["p:q-a"]))
    assert "r-a" not in first and "c-a" not in first and "q-b" not in first
    second = _ids(graph.question_design(tree, tree.nodes["p:q-b"]))
    assert second == ["home", "p-a", "q-b", "s-b"]          # Q1's step and conclusion: Q1's button and its review


def test_only_under_pace_design(tmp_path):
    doc = _design(tmp_path)
    (tmp_path / "kea.yaml").write_text("title: T\npace: guided\n")
    tree = nodes.load_tree(doc)
    assert graph.question_design(tree, tree.nodes["p:q-a"]) == []


def test_the_question_page_shows_every_page_in_full_with_the_versions_to_sign(tmp_path):
    doc = _design(tmp_path)
    tree = nodes.load_tree(doc)
    renderer = SiteRenderer(tree, tmp_path / "site")
    question = tree.nodes["p:q-a"]
    html = renderer.design_sign_html(question, "../", renderer.context("p", "../", question.key))
    signs = ", ".join(f"p:{name}@{identity.version_of(tree.nodes['p:' + name])}"
                      for name in ("home", "p-a", "q-a", "h-a", "s-a"))
    assert f"data-signs='{signs}'" in html and "Sign this design (5 pages)" in html
    assert "up in both" in html and "It will" in html                      # the hypothesis' criterion and title
    assert "5 pages" in renderer.design_banner(question)
    _sign(doc, "experiment/home.md", "premise/p-a.md", "question/q-a.md", "hypothesis/h-a.md", "step/s-a.md")
    tree = nodes.load_tree(doc)
    assert SiteRenderer(tree, tmp_path / "site").design_banner(tree.nodes["p:q-a"]) == ""


def _thread(text: str, page: str, version: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(text=text, page=page, page_version=version, author="Mark", author_id="",
                                 created_at="2026-11-27T10:00:00Z", thread_id="t2026_11_27_abc", tags=["approve"])


def test_kea_sign_marks_each_signature_of_a_design_as_batch(tmp_path):
    doc = _design(tmp_path)
    tree = nodes.load_tree(doc)
    names = ("home", "p-a", "q-a", "h-a", "s-a")
    text = "Sign this design (5 pages)\nSigns: " + ", ".join(
        f"p:{name}@{identity.version_of(tree.nodes['p:' + name])}" for name in names)
    signing.apply_thread(tree, _thread(text, "p:q-a"), lambda label: tree.resolve(label, "p"))
    tree = nodes.load_tree(doc)
    for name in names:
        entry = signing.signatures(tree.nodes["p:" + name])[0]
        assert entry["batch"] == "p:q-a" and signing.holds(entry, tree.nodes["p:" + name]), name
        assert "signed in one go with the design of Q1" in signing.describe(entry, tree.nodes["p:" + name], tree)
    assert graph.question_design(tree, tree.nodes["p:q-a"]) == [] and graph.design_ready(tree, tree.nodes["p:s-a"])
    # one page alone (Approve): no batch mark
    _page(doc, "p/decision/d-a.md", "id: d-a\ntype: decision\ntitle: Use X\nshort: X.\nparent: q-a\nstatus: open")
    tree = nodes.load_tree(doc)
    node = tree.nodes["p:d-a"]
    signing.apply_thread(tree, _thread("", "p:d-a", identity.version_of(node)), lambda label: tree.resolve(label, "p"))
    assert "batch" not in signing.signatures(nodes.load_tree(doc).nodes["p:d-a"])[0]


def test_kea_check_refuses_a_batch_mark_the_thread_does_not_back(tmp_path):
    doc = _design(tmp_path)
    events = tmp_path / "events.jsonl"
    made = store.append_event({"type": "create", "author": "Mark", "page": "p:h-a", "tags": ["approve"]}, events)
    path = doc / "p/hypothesis/h-a.md"
    front, body = path.read_text().split("\n---\n", 1)
    path.write_text(front + f"\napproved: {{by: Mark, date: 2026-11-27, how: site, thread: {made['thread_id']}, "
                    "batch: p:q-a}\n---\n" + body)
    problems, _ = signing.problems_and_notes(nodes.load_tree(doc), events)
    assert any("says batch: p:q-a" in problem and "signed this page alone" in problem for problem in problems)


def test_signed_text_besides_a_link_is_shown(tmp_path):
    """A relation's because: is part of what is signed, so the page shows it (review, finding 1)."""
    doc = _design(tmp_path)
    _page(doc, "p/step/s-a.md", "id: s-a\ntype: step\ntitle: Run\nshort: Runs.\nparent: q-a\nstatus: planned\n"
          "relations:\n  tests: [h-a]\n  relies_on: [{id: p-a, because: the batch effect is negligible}]")
    tree = nodes.load_tree(doc)
    renderer = SiteRenderer(tree, tmp_path / "site")
    question = tree.nodes["p:q-a"]
    html = renderer.design_sign_html(question, "../", renderer.context("p", "../", question.key))
    assert "the batch effect is negligible" in html


def test_another_questions_step_and_decision_stay_on_its_own_page(tmp_path):
    """A step of Q2 that tests Q1's hypothesis, and Q2's decision, are signed on Q2's page; what Q1's steps still
    need from elsewhere is listed (review, findings 3 and 4)."""
    doc = _design(tmp_path)
    _page(doc, "p/question/q-b.md", "id: q-b\ntype: question\ntitle: Then?\nshort: Next.\nparent: home\nstatus: open")
    _page(doc, "p/decision/d-b.md", "id: d-b\ntype: decision\ntitle: Use Y\nshort: Y.\nparent: q-b\nstatus: open")
    _page(doc, "p/step/s-b.md", "id: s-b\ntype: step\ntitle: Also tests H1\nshort: Too.\nparent: q-b\n"
          "status: planned\nrelations:\n  tests: [h-a]")
    _page(doc, "p/step/s-c.md", "id: s-c\ntype: step\ntitle: Q1 step using Y\nshort: Uses Y.\nparent: q-a\n"
          "status: planned\nrelations:\n  tests: [h-a]\n  relies_on: [d-b]")
    tree = nodes.load_tree(doc)
    to_sign, needed, allowed = graph.question_design_parts(tree, tree.nodes["p:q-a"])
    assert _ids(to_sign) == ["home", "p-a", "q-a", "h-a", "s-a", "s-c"]
    assert "p:s-b" not in allowed and "p:d-b" not in allowed and _ids(needed) == ["d-b"]
    second = _ids(graph.question_design(tree, tree.nodes["p:q-b"]))
    assert second[:3] == ["home", "p-a", "q-b"] and sorted(second[3:]) == ["d-b", "s-b"]


def test_a_sub_question_does_not_sign_its_parent_question(tmp_path):
    doc = _design(tmp_path)
    _page(doc, "p/question/q-sub.md", "id: q-sub\ntype: question\ntitle: Which part?\nshort: Part.\nparent: q-a\n"
          "status: open")
    _page(doc, "p/hypothesis/h-sub.md", "id: h-sub\ntype: hypothesis\ntitle: This part\nshort: P.\nparent: q-sub\n"
          "status: planned\nfixed_before_results: true\nprediction: p\ncriterion: c")
    _page(doc, "p/step/s-sub.md", "id: s-sub\ntype: step\ntitle: Part run\nshort: R.\nparent: q-sub\nstatus: planned\n"
          "relations:\n  tests: [h-sub]")
    tree = nodes.load_tree(doc)
    to_sign, needed, _ = graph.question_design_parts(tree, tree.nodes["p:q-sub"])
    assert "q-a" not in _ids(to_sign) and "h-a" not in _ids(to_sign) and {"q-a", "h-a"} <= set(_ids(needed))


def test_kea_sign_signs_only_what_the_design_may(tmp_path, capsys):
    """kea sign enforces the batch itself, not only the button: no result or conclusion, no page outside the
    question's design; a page signed alone already stays unmarked (review, findings 2 and 5)."""
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("title: T\npace: design\n")
    _page(doc, "p/question/q-b.md", "id: q-b\ntype: question\ntitle: Then?\nshort: Next.\nparent: home\nstatus: open")
    tree = nodes.load_tree(doc)
    resolve = lambda label: tree.resolve(label, "p")
    signing.apply_thread(tree, _thread("", "p:h-a", identity.version_of(tree.nodes["p:h-a"])), resolve)
    names = ("q-a", "h-a", "r-a", "c-a", "q-b")
    text = "Sign this design\nSigns: " + ", ".join(f"p:{name}@{identity.version_of(tree.nodes['p:' + name])}" for name in names)
    assert signing.apply_thread(tree, _thread(text, "p:q-a"), resolve) == 3
    out = capsys.readouterr().out
    assert "R1: a result is reviewed one page at a time" in out and "C1: a conclusion" in out
    assert "Q2: not a page of the design of Q1" in out and "NOT SIGNED: 3 of 5" in out
    tree = nodes.load_tree(doc)
    assert signing.signatures(tree.nodes["p:q-a"])[0]["batch"] == "p:q-a"
    assert "batch" not in signing.signatures(tree.nodes["p:h-a"])[0]          # signed alone first: kept so
    for name in ("r-a", "c-a", "q-b"):
        assert signing.signatures(tree.nodes["p:" + name]) == [], name
