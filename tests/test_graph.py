"""The reasoning graph as a whole (docsite/graph.py): structural rules over the whole graph, and the pages to
recheck after an upstream change (fingerprints in doc/_checks.yaml, kea recheck)."""
from __future__ import annotations

from pathlib import Path

from kea.docsite import graph, nodes, render

SCHEMA = (Path(nodes.__file__).resolve().parents[1] / "templates" / "_schema.yaml").read_text()


def _page(doc: Path, relative: str, front: str, body: str = "Text.") -> None:
    path = doc / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front}\n---\n{body}\n")


def _doc(tmp_path: Path) -> Path:
    doc = tmp_path / "doc"
    doc.mkdir()
    (doc / "_schema.yaml").write_text(SCHEMA)
    _page(doc, "p/experiment/home.md", "id: home\ntype: experiment\ntitle: E\nshort: An experiment.\nstatus: open")
    _page(doc, "p/premise/p-a.md", "id: p-a\ntype: premise\ntitle: Data fine\nshort: The data are fine.\nparent: home\n"
          "status: assumed")
    _page(doc, "p/question/q-a.md", "id: q-a\ntype: question\ntitle: Does it?\nshort: Asks.\nparent: home\nstatus: open")
    _page(doc, "p/hypothesis/h-a.md", "id: h-a\ntype: hypothesis\ntitle: It will\nshort: Expect.\nparent: q-a\n"
          "status: planned\nfixed_before_results: true\nprediction: up\ncriterion: up in both")
    _page(doc, "p/step/s-a.md", "id: s-a\ntype: step\ntitle: Run\nshort: Runs.\nparent: q-a\nstatus: done\n"
          "relations:\n  tests: [h-a]\n  relies_on: [p-a]")
    _page(doc, "p/result/r-a.md", "id: r-a\ntype: result\ntitle: Found\nshort: Found it.\nparent: q-a\nstatus: done\n"
          "sources: [x.tsv]\nrelations:\n  answers: [q-a]\n  made_by: [s-a]")
    _page(doc, "p/conclusion/c-a.md", "id: c-a\ntype: conclusion\ntitle: So\nshort: It does.\nparent: q-a\n"
          "status: supported\ncertainty: low\nrelations:\n  supported_by: [{id: r-a, because: same sign}]")
    return doc


def test_a_sound_graph_has_no_structural_problems(tmp_path):
    tree = nodes.load_tree(_doc(tmp_path))
    assert tree.problems == []


def test_structural_rules(tmp_path):
    doc = _doc(tmp_path)
    # a conclusion resting on a hypothesis and on another conclusion only, in a loop
    _page(doc, "p/conclusion/c-b.md", "id: c-b\ntype: conclusion\ntitle: B\nshort: B.\nparent: q-a\nstatus: supported\n"
          "relations:\n  supported_by: [c-c]\n  relies_on: [h-a]")
    _page(doc, "p/conclusion/c-c.md", "id: c-c\ntype: conclusion\ntitle: C\nshort: C.\nparent: q-a\nstatus: supported\n"
          "relations:\n  supported_by: [c-b]")
    # an outcome without a test; confirmatory on exploratory evidence; resting on deprecated evidence
    _page(doc, "p/hypothesis/h-b.md", "id: h-b\ntype: hypothesis\ntitle: Other\nshort: Other.\nparent: q-a\n"
          "status: supported\nfixed_before_results: false")
    _page(doc, "p/result/r-b.md", "id: r-b\ntype: result\ntitle: Old\nshort: Old.\nparent: q-a\nstatus: deprecated\n"
          "analysis: exploratory\nsources: [y.tsv]\nrelations:\n  made_by: [s-a]")
    _page(doc, "p/conclusion/c-d.md", "id: c-d\ntype: conclusion\ntitle: D\nshort: D.\nparent: q-a\nstatus: supported\n"
          "analysis: confirmatory\nrelations:\n  supported_by: [r-b]")
    problems = "\n".join(nodes.load_tree(doc).problems)
    assert "c-b.md: conclusion rests on no result" in problems and "c-c.md: conclusion rests on no result" in problems
    assert problems.count("circular support") == 1                         # one loop, reported once
    assert "c-b.md: conclusion relies on hypothesis H1" in problems
    assert "h-b.md: hypothesis is supported but no result tests it" in problems
    assert "c-d.md: rests on deprecated evidence (R2)" in problems
    assert "c-d.md: confirmatory conclusion on exploratory evidence only" in problems
    assert "c-a.md" not in problems                                       # resting on a result is fine


def test_a_changed_premise_compromises_everything_downstream(tmp_path):
    doc = _doc(tmp_path)
    tree = nodes.load_tree(doc, baseline=True)                             # first build: the baseline
    assert (doc / "_checks.yaml").exists() and tree.compromised == {}
    _page(doc, "p/premise/p-a.md", "id: p-a\ntype: premise\ntitle: Data fine\nshort: The data are fine, mostly.\n"
          "parent: home\nstatus: questioned")
    tree = nodes.load_tree(doc, baseline=True)
    assert tree.compromised["p:s-a"] == ["P1 changed"]
    assert tree.compromised["p:r-a"] == ["via S1"] and tree.compromised["p:c-a"] == ["via R1"]
    assert tree.compromised["p:h-a"] == ["via S1"]                         # its outcome rests on the test
    assert tree.compromised["p:q-a"] == ["via R1"]                         # its answer rests on R1
    assert "recheck" in render.status_pill(tree.nodes["p:c-a"]) and render.status_row_class(tree.nodes["p:c-a"]) == "st-mid"
    assert any("page(s) to recheck" in note for note in tree.notes)
    # the agent checks the step: unaffected; everything downstream clears with it
    ledger = graph.read_ledger(doc)
    graph.recheck(tree, ledger, "p:s-a", "unaffected: the change concerns batch 3, not used here")
    graph.write_ledger(doc, ledger)
    assert nodes.load_tree(doc).compromised == {}
    # a cosmetic change (order) compromises nothing
    _page(doc, "p/premise/p-a.md", "id: p-a\ntype: premise\ntitle: Data fine\nshort: The data are fine, mostly.\n"
          "parent: home\nstatus: questioned\norder: 5")
    assert nodes.load_tree(doc).compromised == {}


def test_kea_recheck_cli(tmp_path, monkeypatch, capsys):
    doc = _doc(tmp_path)
    nodes.load_tree(doc, baseline=True)
    _page(doc, "p/result/r-a.md", "id: r-a\ntype: result\ntitle: Found\nshort: Found it, smaller.\nparent: q-a\n"
          "status: done\nsources: [x.tsv]\nrelations:\n  answers: [q-a]\n  made_by: [s-a]")
    monkeypatch.setattr(nodes, "DOC", doc)
    assert graph.main(["--list"]) == 0
    assert "R1 changed" in capsys.readouterr().out
    assert graph.main(["c-a", "--because", "updated: smaller effect, certainty stays low"]) == 0
    assert "c-a" not in str(nodes.load_tree(doc).compromised)


def test_guided_pace_one_reviewed_step_at_a_time(tmp_path):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("title: T\npace: guided\n")
    problems = "\n".join(nodes.load_tree(doc).problems)
    assert "h-a.md: written under question Q1, which the owner has not approved" in problems
    assert "s-a.md: step is done but was not approved" in problems
    assert "c-a.md: drawn from result(s) R1 that the owner has not reviewed" in problems
    approve = "\napproved: {by: Mark, date: 2026-11-09, how: chat}"
    for relative in ("experiment/home.md", "question/q-a.md", "step/s-a.md", "result/r-a.md"):
        path = doc / "p" / relative
        front, body = path.read_text().split("\n---\n", 1)
        path.write_text(front + approve + "\n---\n" + body)
    assert nodes.load_tree(doc).problems == []
    (tmp_path / "kea.yaml").write_text("title: T\n")                      # pace free: no gate
    assert graph.next_steps(nodes.load_tree(doc), "p")                     # (still computable)


def test_next_steps_say_what_waits(tmp_path):
    doc = tmp_path / "doc"
    doc.mkdir()
    (doc / "_schema.yaml").write_text(SCHEMA)
    (tmp_path / "kea.yaml").write_text("pace: guided\n")
    _page(doc, "p/experiment/home.md", "id: home\ntype: experiment\ntitle: E\nshort: An experiment.\nstatus: open")
    tree = nodes.load_tree(doc)
    assert graph.next_steps(tree, "p")[0].startswith("Next: propose questions")
    _page(doc, "p/question/q-a.md", "id: q-a\ntype: question\ntitle: Does it?\nshort: Asks.\nparent: home\nstatus: open")
    assert "waiting for the owner to review the question" in graph.next_steps(nodes.load_tree(doc), "p")[0]
    _page(doc, "p/question/q-a.md", "id: q-a\ntype: question\ntitle: Does it?\nshort: Asks.\nparent: home\nstatus: open\n"
          "approved: {by: Mark, date: 2026-11-09}")
    assert "write hypotheses" in graph.next_steps(nodes.load_tree(doc), "p")[0]
    _page(doc, "p/step/s-a.md", "id: s-a\ntype: step\ntitle: Run\nshort: Runs.\nparent: q-a\nstatus: planned")
    assert "approve the planned step(s) S1" in graph.next_steps(nodes.load_tree(doc), "p")[0]
    _page(doc, "p/step/s-a.md", "id: s-a\ntype: step\ntitle: Run\nshort: Runs.\nparent: q-a\nstatus: planned\n"
          "approved: {by: Mark, date: 2026-11-09}")
    line = graph.next_steps(nodes.load_tree(doc), "p")[0]
    assert "run the approved step(s) S1" in line and "No conclusions yet" in line


def test_drop_takes_what_rests_only_on_the_page(tmp_path):
    doc = _doc(tmp_path)
    _page(doc, "p/result/r-b.md", "id: r-b\ntype: result\ntitle: Other\nshort: Other.\nparent: home\nstatus: done\n"
          "sources: [y.tsv]")
    _page(doc, "p/conclusion/c-b.md", "id: c-b\ntype: conclusion\ntitle: Both\nshort: Both.\nparent: home\n"
          "status: supported\nrelations:\n  supported_by: [r-a, r-b]")
    tree = nodes.load_tree(doc)
    keys = graph.drop_set(tree, "p:q-a")
    assert keys[0] == "p:q-a" and set(keys) == {"p:q-a", "p:h-a", "p:s-a", "p:r-a", "p:c-a"}   # c-b also rests on r-b
    assert graph.drop_set(tree, "p:r-a") == ["p:r-a", "p:c-a"]
    assert graph.drop_set(tree, "p:p-a") == ["p:p-a"]                         # S1 relies on P1 but sits under Q1


def test_waiting_pages_under_guided_pace(tmp_path):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("pace: guided\n")
    tree = nodes.load_tree(doc)
    assert tree.nodes["p:q-a"].waiting and tree.nodes["p:h-a"].waiting and tree.nodes["p:r-a"].waiting
    assert not tree.nodes["p:s-a"].waiting                                  # done, not planned (a problem instead)
    assert not tree.nodes["p:c-a"].waiting and "waiting for approval" in render.status_pill(tree.nodes["p:q-a"])
    (tmp_path / "kea.yaml").write_text("pace: free\n")
    assert not nodes.load_tree(doc).nodes["p:q-a"].waiting


def test_page_verdicts_approve_revise_drop():
    from kea.feedback import tags
    known = {tag["name"]: tag for tag in tags.vocabulary({})["tags"]}
    assert known["approve"]["scope"] == known["revise"]["scope"] == known["drop"]["scope"] == "page"
    assert known["revise"].get("needs_text") and "harvest itself" in known["approve"]["instruction"]
    assert "kea drop" in known["drop"]["instruction"] and known["reject"].get("hidden")


def test_one_or_more_experiments_and_the_project_summary(tmp_path):
    doc = _doc(tmp_path)
    (doc / "_summary.md").write_text("Text.\n")                             # the same as the experiment's summary
    assert any("repeats the experiment's summary" in note for note in nodes.load_tree(doc).notes)
    _page(doc, "q/experiment/home.md", "id: home\ntype: experiment\ntitle: Second\nshort: Another.\nstatus: open")
    (doc / "_summary.md").unlink()
    assert any("2 experiments but no summary" in problem for problem in nodes.load_tree(doc).problems)
