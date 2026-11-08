"""The fields and checks of Kea 1.17's vocabulary review (docsite/nodes.py, render.py, context.py): a hypothesis's
prediction and criterion, analysis (confirmatory / exploratory) apart from status, a conclusion's certainty, a
caveat's kind, reasons on links (because:), and the notes on relies_on, missing premises and unreasoned links."""
from __future__ import annotations

from pathlib import Path

from kea.docsite import context, nodes, render

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
    _page(doc, "p/question/q-a.md", "id: q-a\ntype: question\ntitle: Does it?\nshort: Asks.\nparent: home\nstatus: open")
    _page(doc, "p/step/s-a.md", "id: s-a\ntype: step\ntitle: Run\nshort: Runs.\nparent: q-a\nstatus: done")
    _page(doc, "p/decision/d-a.md", "id: d-a\ntype: decision\ntitle: Pick\nshort: Picks.\nparent: home\nstatus: active")
    _page(doc, "p/result/r-a.md", "id: r-a\ntype: result\ntitle: Found\nshort: Found it.\nparent: q-a\nstatus: done\n"
          "analysis: exploratory\nsources: [x.tsv]\nrelations:\n  answers: [q-a]\n  made_by: [s-a]\n  relies_on: [d-a]")
    _page(doc, "p/result/r-b.md", "id: r-b\ntype: result\ntitle: Old\nshort: Old style.\nparent: q-a\nstatus: exploratory\n"
          "sources: [y.tsv]\nrelations:\n  answers: [q-a]")
    _page(doc, "p/conclusion/c-a.md", "id: c-a\ntype: conclusion\ntitle: So\nshort: It does.\nparent: q-a\nstatus: supported\n"
          "relations:\n  answers: [q-a]\n  supported_by:\n    - {id: r-a, because: same sign in both cohorts}\n    - r-b")
    return doc


def test_reasons_fields_and_notes(tmp_path):
    doc = _doc(tmp_path)
    tree = nodes.load_tree(doc)
    assert tree.problems == []
    conclusion = tree.nodes["p:c-a"]
    assert conclusion.relations["supported_by"] == ["p:r-a", "p:r-b"]                  # a mapping is still a link
    assert tree.reason("p:r-a", "p:c-a") == "same sign in both cohorts"                # from either side
    assert tree.reason("p:c-a", "p:r-b") == ""
    notes = "\n".join(tree.notes)
    assert "1 support link(s) of conclusions without a reason" in notes                # r-b only
    assert "conclusion(s) C1 without certainty" in notes
    assert "results but no premises" in notes
    assert "relies_on D1: a typed relation fits (decided_in)" in notes
    assert "r-b.md: status exploratory: since Kea 1.17 write analysis: exploratory" in notes
    # the old spelling and the new field read the same
    assert nodes.analysis_of(tree.nodes["p:r-a"]) == nodes.analysis_of(tree.nodes["p:r-b"]) == "exploratory"
    assert "exploratory" in render.status_pill(tree.nodes["p:r-a"]) and "done" in render.status_pill(tree.nodes["p:r-a"])
    assert render.status_pill(tree.nodes["p:r-b"]).count("class='pill") == 1                # one pill, not two
    assert render.status_row_class(tree.nodes["p:r-a"]) == "st-mid"                      # done, but exploratory
    gaps = "\n".join(context.gaps_for_question(tree, tree.nodes["p:q-a"], [], [tree.nodes["p:r-a"]], [conclusion]))
    assert "no reason for its link(s) to R2" in gaps and "no certainty" in gaps and "has no premises" in gaps


def test_bad_values_and_fixed_hypothesis_without_criterion(tmp_path):
    doc = _doc(tmp_path)
    _page(doc, "p/hypothesis/h-a.md", "id: h-a\ntype: hypothesis\ntitle: It will\nshort: Expect.\nparent: q-a\n"
          "status: planned\nfixed_before_results: true\nprediction: a rise")
    _page(doc, "p/caveat/w-a.md", "id: w-a\ntype: caveat\ntitle: Small\nshort: Few donors.\nparent: home\nstatus: open\n"
          "kind: sampling\nrelations:\n  limits: [c-a]")
    _page(doc, "p/conclusion/c-b.md", "id: c-b\ntype: conclusion\ntitle: Also\nshort: Maybe.\nparent: q-a\n"
          "status: supported\ncertainty: medium\nanalysis: post-hoc\nrelations:\n  supported_by: [{because: x}]")
    problems = "\n".join(nodes.load_tree(doc).problems)
    assert "h-a.md: hypothesis fixed before results without criterion" in problems
    assert "kind: 'sampling'" in problems and "certainty: 'medium'" in problems and "analysis: 'post-hoc'" in problems
    assert "needs id:" in problems
    _page(doc, "p/hypothesis/h-a.md", "id: h-a\ntype: hypothesis\ntitle: It will\nshort: Expect.\nparent: q-a\n"
          "status: planned\nfixed_before_results: true\nprediction: a rise\ncriterion: up in both cohorts")
    assert not any("h-a.md" in problem for problem in nodes.load_tree(doc).problems)
    _page(doc, "p/x/x.md", "id: x\ntype: dataset\ntitle: X\nshort: X.\nparent: home")
    assert any("a dataset is a resource with kind: dataset" in problem for problem in nodes.load_tree(doc).problems)
