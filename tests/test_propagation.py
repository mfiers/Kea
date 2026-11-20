"""Sign-offs that count only with what they were built on (docsite/propagation.py): a substantive change of a
question makes the pages written against it wait for a sign-off each, and holds everything below them until those
are signed; a recorded reason; kea impact; retiring a branch keeps the reusable pages and the links."""
from __future__ import annotations

from kea.docsite import graph, nodes, propagation, signing

from test_graph import _doc, _page


def _sign(doc, *ids):
    """Sign pages as kea sign does: bound to their wording and to what they are built on now."""
    tree = nodes.load_tree(doc)
    for page_id in ids:
        node = tree.nodes[f"p:{page_id}"]
        signing.add_signature(node, {"by": "Mark", "date": "2026-11-20", "how": "chat", "content": signing.content(node),
                                     "upstream": propagation.upstream_hashes(tree, node)})


def _guided(tmp_path):
    (tmp_path / "kea.yaml").write_text("pace: guided\n")
    doc = _doc(tmp_path)
    _sign(doc, "home", "p-a", "q-a", "h-a", "s-a", "r-a", "c-a")
    return doc


def test_a_changed_question_waits_its_children_and_holds_what_lies_below(tmp_path):
    doc = _guided(tmp_path)
    tree = nodes.load_tree(doc)
    assert all(graph.approved(node) for node in tree.nodes.values()) and tree.problems == []
    assert propagation.downstream(tree, "p:q-a") == (["p:h-a", "p:s-a"], ["p:c-a", "p:r-a"])
    path = doc / "p/question/q-a.md"
    path.write_text(path.read_text().replace("title: Does it?", "title: Does it go down?"))
    tree = nodes.load_tree(doc)
    assert any("kea change q-a" in problem for problem in tree.problems)       # the reason must be recorded
    ledger = graph.read_ledger(doc)
    propagation.record_change(ledger, tree.nodes["p:q-a"], "the direction asked was reversed")
    graph.write_ledger(doc, ledger)
    tree = nodes.load_tree(doc)
    assert tree.problems == []
    question, hypothesis, step, result = (tree.nodes[f"p:{name}"] for name in ("q-a", "h-a", "s-a", "r-a"))
    assert question.waiting and not graph.approved(question)
    # the hypothesis and step wait first for the question; the result waits for the step
    assert hypothesis.held_by == ["p:q-a"] and not hypothesis.waiting and not graph.approved(hypothesis)
    assert result.held_by == ["p:s-a"] and not graph.approved(result)
    assert [node.id for node in signing.sign_order(tree)] == ["q-a"]
    # the question is signed again: the hypothesis and step ask for their own sign-off, with the change shown
    _sign(doc, "q-a")
    tree = nodes.load_tree(doc)
    hypothesis = tree.nodes["p:h-a"]
    assert [key for key, _ in hypothesis.upstream_changed] == ["p:q-a"] and hypothesis.waiting
    notice = propagation.notice_html(tree, hypothesis, "")
    assert "has changed since this page was signed" in notice and "the direction asked was reversed" in notice
    assert "What changed on Q1" in notice              # the word diff itself needs git history (none in a tmp dir)
    assert [node.id for node in signing.sign_order(tree)][:1] == ["h-a"]
    assert tree.nodes["p:r-a"].held_by == ["p:s-a"]                         # still held: its step is not signed again
    # both signed again (unchanged): the result and conclusion count again by themselves
    _sign(doc, "h-a")
    _sign(doc, "s-a")
    tree = nodes.load_tree(doc)
    assert all(graph.approved(node) for node in tree.nodes.values()) and signing.sign_order(tree) == []


def test_a_minor_edit_upstream_changes_nothing_below(tmp_path):
    doc = _guided(tmp_path)
    tree = nodes.load_tree(doc)
    question = tree.nodes["p:q-a"]
    path = doc / "p/question/q-a.md"
    path.write_text(path.read_text().replace("short: Asks.", "short: Asks it."))
    edited = nodes.load_tree(doc).nodes["p:q-a"]
    entries = signing.signatures(edited)
    entries[0]["minor"] = [{"content": signing.content(edited), "because": "clearer"}]
    signing.write_signatures(edited.source, entries)
    tree = nodes.load_tree(doc)
    assert graph.approved(tree.nodes["p:h-a"]) and tree.nodes["p:h-a"].upstream_changed == []
    assert question.key in tree.nodes


def test_retiring_a_question_keeps_decisions_and_marks_links(tmp_path):
    doc = _guided(tmp_path)
    _page(doc, "p/decision/d-a.md", "id: d-a\ntype: decision\ntitle: Per donor\nshort: Per donor.\nparent: q-a\n"
          "status: active")
    _page(doc, "p/question/q-b.md", "id: q-b\ntype: question\ntitle: Does it, per donor?\nshort: Asks again.\n"
          "parent: home\nstatus: open\nrelations:\n  supersedes: [q-a]\n---\nRedone from [[q-a]].")
    tree = nodes.load_tree(doc)
    gone, keep = propagation.retire_plan(tree, "p:q-a", "q-b")
    assert sorted(gone) == ["p:c-a", "p:h-a", "p:q-a", "p:r-a", "p:s-a"] and keep == [("p:d-a", "q-b")]
    propagation.retire(tree, "p:q-a", "asked the wrong unit", "q-b")
    tree = nodes.load_tree(doc)
    assert sorted(tree.retired) == sorted(gone) and "p:q-a" not in tree.nodes
    assert tree.nodes["p:d-a"].parent == "q-b"
    assert tree.problems == []                                  # supersedes and a text link to a retired page are fine
    assert tree.retired["p:q-a"].header["retired"]["because"] == "asked the wrong unit"
