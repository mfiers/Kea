"""Signatures bound to the wording they signed (docsite/signing.py): what is signed, when a signature stops holding,
minor edits that carry it (checked mechanically), the top-down order of sign-offs (one page per click) and the
kea sign command (which still reads the Signs: lines of 1.29-1.31.0)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from kea.docsite import graph, nodes, signing
from kea.feedback import store

from test_graph import _doc, _page

HYPOTHESIS = ("id: h-a\ntype: hypothesis\ntitle: It will\nshort: Expect.\nparent: q-a\nstatus: {status}\n"
              "fixed_before_results: true\nprediction: {prediction}\ncriterion: up in both cohorts with q below 0.05")


def _hypothesis(doc: Path, prediction: str = "the score goes up in carriers compared with non-carriers",
                status: str = "planned", signed: str = "") -> None:
    _page(doc, "p/hypothesis/h-a.md", HYPOTHESIS.format(status=status, prediction=prediction) + signed)


def _sign_all(doc: Path, *relatives: str) -> None:
    """Sign pages with a signature bound to their current wording (as kea sign does)."""
    tree = nodes.load_tree(doc)
    for node in tree.nodes.values():
        if any(str(node.source).endswith(relative) for relative in relatives):
            signing.add_signature(node, {"by": "Mark", "date": "2026-11-15", "how": "chat",
                                         "content": signing.content(node)})


def test_what_is_signed_leaves_out_progress_and_bookkeeping():
    header = {"title": "T", "status": "planned", "answer": "", "order": 3, "prediction": "up",
              "relations": {"tests": ["h"], "supports": ["c"]}}
    base = signing.content_of(header, "Text.")
    assert signing.content_of({**header, "status": "supported", "answer": "yes", "order": 9,
                               "approved": [{"by": "A"}]}, "Text.") == base
    assert signing.content_of({**header, "relations": {"tests": ["h"], "supports": ["c", "d"]}}, " Text. ") == base
    assert signing.content_of({**header, "prediction": "down"}, "Text.") != base
    assert signing.content_of({**header, "relations": {"tests": ["h", "g"]}}, "Text.") != base


def test_a_signature_holds_until_the_page_says_something_else(tmp_path):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("pace: guided\n")
    _hypothesis(doc)
    _sign_all(doc, "home.md", "q-a.md", "h-a.md", "s-a.md", "r-a.md", "c-a.md", "p-a.md")
    tree = nodes.load_tree(doc)
    assert graph.approved(tree.nodes["p:h-a"]) and not tree.nodes["p:h-a"].waiting
    assert tree.problems == []
    # the outcome is progress, not a new claim: the signature still holds
    path = doc / "p/hypothesis/h-a.md"
    path.write_text(path.read_text().replace("status: planned", "status: supported"))
    assert graph.approved(nodes.load_tree(doc).nodes["p:h-a"])
    # a changed prediction is a new claim: the page waits again, with a note (not a build problem)
    path.write_text(path.read_text().replace("goes up", "goes down"))
    tree = nodes.load_tree(doc)
    node = tree.nodes["p:h-a"]
    assert not graph.approved(node) and node.waiting and signing.stale(node)
    assert any("changed since Mark signed it" in note for note in tree.notes)
    assert tree.problems == []
    assert "no longer holds" in signing.describe(signing.signatures(node)[0], node)


def test_signatures_before_1_29_count_unbound(tmp_path):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("pace: guided\n")
    _hypothesis(doc, signed="\napproved: {by: Mark, date: 2026-11-09, how: chat}")
    tree = nodes.load_tree(doc)
    assert graph.approved(tree.nodes["p:h-a"])
    assert signing.state(signing.signatures(tree.nodes["p:h-a"])[0], tree.nodes["p:h-a"]) == "legacy"
    assert any("before Kea 1.29" in note for note in tree.notes)


def test_minor_or_not():
    old = "The score goes up in carriers compared with non-carriers in both cohorts."
    assert signing.text_reasons("text", old, old.replace("compared with", "compared to")) == []
    assert signing.text_reasons("text", old, old.replace("goes up", "goes down"))          # direction
    assert signing.text_reasons("text", old, old.replace("goes up", "does not go up"))     # negation
    assert signing.text_reasons("text", old + " q < 0.05", old + " q < 0.01")             # a number
    assert signing.text_reasons("text", old, "Carriers score higher than others, measured per donor in each set.")
    assert signing.minor_reasons({"certainty": "high"}, "", {"certainty": "moderate"}, "")  # a short field
    assert signing.minor_reasons({"relations": {"tests": ["a"]}}, "", {"relations": {"tests": ["b"]}}, "")
    assert signing.minor_reasons({"title": "A"}, "See [[r-a]].", {"title": "A"}, "See [[r-b]].")


def test_sign_order_is_top_down_one_page_each(tmp_path):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("pace: guided\n")
    _page(doc, "p/step/s-a.md", "id: s-a\ntype: step\ntitle: Run\nshort: Runs.\nparent: q-a\nstatus: planned\n"
          "relations:\n  tests: [h-a]")
    _page(doc, "p/step/s-b.md", "id: s-b\ntype: step\ntitle: Control\nshort: Permutes.\nparent: q-a\n"
          "status: planned\nrelations:\n  tests: [h-a]")
    _page(doc, "p/decision/d-a.md", "id: d-a\ntype: decision\ntitle: Per donor\nshort: Count per donor.\nparent: home")
    for relative in ("p/result/r-a.md", "p/conclusion/c-a.md"):
        (doc / relative).unlink()
    _sign_all(doc, "home.md", "q-a.md", "p-a.md")
    tree = nodes.load_tree(doc)
    order = [node.id for node in signing.sign_order(tree)]
    assert order == ["d-a", "h-a", "s-a", "s-b"]                         # the decision first, then the question's plan
    assert "q-a" not in order and len(order) == len(set(order))          # signed already: not listed


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_kea_sign_minor_and_thread(tmp_path, monkeypatch, capsys):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("pace: guided\n")
    _hypothesis(doc)
    monkeypatch.setattr(nodes, "DOC", doc)
    monkeypatch.setattr(nodes, "PROJECT_ROOT", tmp_path)
    events = tmp_path / "events.jsonl"
    monkeypatch.setattr(store, "default_path", lambda: events)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "pages")
    # the owner signs in the chat
    assert signing.main(["h-a", "--by", "Mark"]) == 0
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "signed")
    path = doc / "p/hypothesis/h-a.md"
    # a minor edit: Kea accepts it and the signature is carried
    path.write_text(path.read_text().replace("compared with", "compared to"))
    assert signing.main(["h-a", "--minor", "--because", "wording"]) == 0
    node = nodes.load_tree(doc).nodes["p:h-a"]
    assert graph.approved(node) and signing.state(signing.signatures(node)[0], node) == "minor"
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "minor")
    # not minor: Kea refuses, the page waits
    path.write_text(path.read_text().replace("goes up", "goes down"))
    assert signing.main(["h-a", "--minor", "--because", "typo"]) == 1
    assert "NOT minor" in capsys.readouterr().out
    assert nodes.load_tree(doc).nodes["p:h-a"].waiting
    # a reader's Approve, bundled: the thread names the pages and the versions seen
    from kea.docsite import identity
    tree = nodes.load_tree(doc)
    version = identity.version_of(tree.nodes["p:h-a"])
    store.append_event({"type": "create", "page": "p:q-a", "author": "Ann", "text": f"Signs: p:h-a@{version}",
                        "tags": ["approve"], "page_version": identity.version_of(tree.nodes["p:q-a"])}, events)
    thread = store.threads(events)[0]
    assert signing.main(["--thread", thread.thread_id]) == 0
    node = nodes.load_tree(doc).nodes["p:h-a"]
    assert graph.approved(node)
    entry = [item for item in signing.signatures(node) if item["by"] == "Ann"][0]
    assert entry["how"] == "site" and entry["thread"] == thread.thread_id
    assert not [problem for problem in nodes.load_tree(doc).problems if "thread" in problem]   # backed by the log
    # a signature naming a thread by someone else is a problem
    signing.add_signature(nodes.load_tree(doc).nodes["p:h-a"], {**entry, "by": "Bob"})
    assert any("does not match thread" in problem for problem in nodes.load_tree(doc).problems)


def test_context_names_waiting_premises_and_decisions(tmp_path):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("pace: guided\n")
    _hypothesis(doc)
    _sign_all(doc, "home.md", "q-a.md")
    tree = nodes.load_tree(doc)
    first = graph.next_steps(tree, "p")[0]
    assert first.startswith("Waiting for the owner to sign off on") and "(premise)" in first


def test_kea_sign_pending_applies_every_open_sign_off(tmp_path, monkeypatch, capsys):
    from kea.docsite import identity
    from kea.feedback import cycle
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("pace: guided\n")
    _hypothesis(doc)
    _page(doc, "p/step/s-a.md", "id: s-a\ntype: step\ntitle: Run\nshort: Runs.\nparent: q-a\nstatus: planned\n"
          "relations:\n  tests: [h-a]")
    _page(doc, "p/step/s-b.md", "id: s-b\ntype: step\ntitle: Control\nshort: Permutes.\nparent: q-a\n"
          "status: planned\nrelations:\n  tests: [h-a]")
    for relative in ("p/result/r-a.md", "p/conclusion/c-a.md"):
        (doc / relative).unlink()
    _sign_all(doc, "home.md", "q-a.md", "p-a.md")
    monkeypatch.setattr(nodes, "DOC", doc)
    monkeypatch.setattr(nodes, "PROJECT_ROOT", tmp_path)
    events = tmp_path / "events.jsonl"
    monkeypatch.setattr(store, "default_path", lambda: events)
    tree = nodes.load_tree(doc)
    stage = [tree.nodes[key] for key in ("p:s-b", "p:h-a", "p:s-a")]       # a stage signed at once in 1.29-1.31.0
    assert graph.stage_action(tree, stage) == "run the plan"              # two planned steps: the plan runs as one
    signs = "Signs: " + ", ".join(f"{node.key}@{identity.version_of(node)}" for node in stage)
    store.append_event({"type": "create", "page": "p:s-b", "author": "Ann", "text": signs, "tags": ["approve"],
                        "page_version": identity.version_of(tree.nodes["p:s-b"])}, events)
    store.append_event({"type": "create", "page": "p:s-a", "author": "Ann", "text": "Simpler, please",
                        "tags": ["revise"]}, events)
    assert len(cycle.sign_requests(store.threads(events))) == 1                   # the revise is a plan item
    assert signing.main(["--pending"]) == 0
    out = capsys.readouterr().out
    assert "revise" not in out and "kea reply" in out and "add the next step" in out
    tree = nodes.load_tree(doc)
    assert all(graph.approved(tree.nodes[node.key]) for node in stage)
