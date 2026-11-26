"""pace: design (graph.py, Kea 1.33): the owner's brief, the whole design in one round, signed page by page, then
one execution round and a review that holds back only what relies on it; and the commit-order check of hypotheses
fixed before their results (graph.preregistration)."""
from __future__ import annotations

import subprocess

from kea.docsite import graph, nodes, signing

from test_graph import _doc, _page

SIGN = "\napproved: {by: Mark, date: 2026-11-26, how: chat}"


def _sign(doc, *relatives):
    for relative in relatives:
        path = doc / "p" / relative
        front, body = path.read_text().split("\n---\n", 1)
        path.write_text(front + SIGN + "\n---\n" + body)


def _plan_only(doc):
    """The fixture as a fresh design: the step planned, no result or conclusion yet."""
    _page(doc, "p/step/s-a.md", "id: s-a\ntype: step\ntitle: Run\nshort: Runs.\nparent: q-a\nstatus: planned\n"
          "relations:\n  tests: [h-a]\n  relies_on: [p-a]")
    (doc / "p/result/r-a.md").unlink()
    (doc / "p/conclusion/c-a.md").unlink()


def test_the_design_is_written_in_one_round_and_runs_only_when_signed(tmp_path):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("title: T\npace: design\n")
    _plan_only(doc)
    tree = nodes.load_tree(doc)
    assert tree.problems == []                           # questions, hypotheses and steps drafted together: fine
    assert [node.id for node in signing.sign_order(tree)] == ["home", "p-a", "q-a", "h-a", "s-a"]   # top down
    lines = graph.next_steps(tree, "p")
    assert "sign the design" in lines[0] and "Q1" in lines[1] and "H1" in lines[1] and "S1" in lines[1]
    assert graph.go_action(tree, tree.nodes["p:s-a"]) == ""        # not before the design is signed
    route = {stage["key"]: stage["state"] for stage in graph.question_route(tree, tree.nodes["p:q-a"])["stages"]}
    assert route == {"question": "you", "plan": "you", "run": "later", "results": "later", "conclusions": "later"}
    _sign(doc, "experiment/home.md", "premise/p-a.md", "question/q-a.md", "hypothesis/h-a.md", "step/s-a.md")
    tree = nodes.load_tree(doc)
    assert signing.sign_order(tree) == [] and graph.go_action(tree, tree.nodes["p:s-a"]) == "run the step"
    assert "execution round" in graph.next_steps(tree, "p")[0] and "draft the conclusions" in graph.next_steps(tree, "p")[0]


def test_a_step_that_runs_on_an_unsigned_design_is_a_problem(tmp_path):
    doc = _doc(tmp_path)                                 # S1 is done; nothing signed
    (tmp_path / "kea.yaml").write_text("title: T\npace: design\n")
    problems = "\n".join(nodes.load_tree(doc).problems)
    assert "s-a.md: step is done but its design is not signed" in problems
    for name in ("E", "P1", "Q1", "H1", "S1"):
        assert name in problems.split("s-a.md: step is done")[1].split("\n")[0], name
    assert "written under question" not in problems      # the guided rules do not apply
    assert "drawn from result(s)" not in problems         # a draft conclusion before the results' review is fine
    _sign(doc, "experiment/home.md", "premise/p-a.md", "question/q-a.md", "hypothesis/h-a.md", "step/s-a.md")
    tree = nodes.load_tree(doc)
    assert tree.problems == []
    assert [node.id for node in signing.sign_order(tree)] == ["r-a", "c-a"]   # the review: results, then conclusions
    assert "waiting for the owner to review R1, C1" in graph.next_steps(tree, "p")[0]


def test_the_review_holds_back_only_what_relies_on_it(tmp_path):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("title: T\npace: design\n")
    _sign(doc, "experiment/home.md", "premise/p-a.md", "question/q-a.md", "hypothesis/h-a.md", "step/s-a.md")
    # a second question whose step builds on C1 (not yet reviewed), and a third that does not
    _page(doc, "p/question/q-b.md", "id: q-b\ntype: question\ntitle: Then?\nshort: Next.\nparent: home\nstatus: open"
          + SIGN)
    _page(doc, "p/step/s-b.md", "id: s-b\ntype: step\ntitle: Build on C1\nshort: Uses it.\nparent: q-b\n"
          "status: planned\nrelations:\n  relies_on: [c-a]" + SIGN)
    _page(doc, "p/question/q-c.md", "id: q-c\ntype: question\ntitle: Other?\nshort: Apart.\nparent: home\n"
          "status: open" + SIGN)
    _page(doc, "p/step/s-c.md", "id: s-c\ntype: step\ntitle: Alone\nshort: Alone.\nparent: q-c\nstatus: planned" + SIGN)
    tree = nodes.load_tree(doc)
    assert graph.go_action(tree, tree.nodes["p:s-b"]) == "" and graph.go_action(tree, tree.nodes["p:s-c"]) == "run the step"
    lines = "\n".join(graph.next_steps(tree, "p"))
    assert "S2 wait for the sign-off of what they rely on: C1" in lines and "run step(s) S3" in lines
    _page(doc, "p/step/s-b.md", "id: s-b\ntype: step\ntitle: Build on C1\nshort: Uses it.\nparent: q-b\n"
          "status: in_progress\nrelations:\n  relies_on: [c-a]" + SIGN)
    assert any("s-b.md: step is in_progress but its design is not signed: C1" in problem
               for problem in nodes.load_tree(doc).problems)


def test_without_questions_the_next_step_is_the_design_from_the_brief(tmp_path):
    doc = tmp_path / "doc"
    doc.mkdir()
    (doc / "_schema.yaml").write_text((graph.Path(nodes.__file__).resolve().parents[1] / "templates" /
                                       "_schema.yaml").read_text())
    (tmp_path / "kea.yaml").write_text("pace: design\n")
    _page(doc, "p/experiment/home.md", "id: home\ntype: experiment\ntitle: E\nshort: An experiment.\nstatus: open")
    line = graph.next_steps(nodes.load_tree(doc), "p")[-1]
    assert "## Brief" in line and "word for word" in line and "never its outcomes" in line


def _git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True,
                   capture_output=True)


def test_a_hypothesis_fixed_before_results_is_committed_before_them(tmp_path):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("title: T\npace: design\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "all at once")                       # hypothesis and result in one commit
    problems = "\n".join(nodes.load_tree(doc).problems)
    assert "h-a.md: fixed_before_results: true, but it was committed no earlier than result(s) R1" in problems
    (tmp_path / "kea.yaml").write_text("title: T\npace: guided\n")      # a note under the other paces
    tree = nodes.load_tree(doc)
    assert not any("fixed_before_results: true, but" in problem for problem in tree.problems)
    assert any("fixed_before_results: true, but" in note for note in tree.notes)


def test_a_hypothesis_committed_first_passes(tmp_path):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("title: T\npace: design\n")
    result = (doc / "p/result/r-a.md").read_text()
    (doc / "p/result/r-a.md").unlink()
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "the design")
    (doc / "p/result/r-a.md").write_text(result)
    assert not any("fixed_before_results" in problem for problem in nodes.load_tree(doc).problems)   # not committed yet
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "the run")
    assert not any("fixed_before_results" in problem for problem in nodes.load_tree(doc).problems)


def test_a_result_needs_a_step_that_ran_on_a_signed_design(tmp_path):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("title: T\npace: design\n")
    _plan_only(doc)                                       # S1 still planned, nothing signed
    _page(doc, "p/result/r-a.md", "id: r-a\ntype: result\ntitle: Found\nshort: Found it.\nparent: q-a\nstatus: done\n"
          "sources: [x.tsv]\nrelations:\n  made_by: [s-a]")
    _page(doc, "p/result/r-b.md", "id: r-b\ntype: result\ntitle: Loose\nshort: Loose.\nparent: q-a\nstatus: done\n"
          "sources: [y.tsv]\nrelations:\n  tests: [h-a]")
    problems = "\n".join(nodes.load_tree(doc).problems)
    assert "r-a.md: a result before its step ran on a signed design (pace: design): step S1 is still planned" in problems
    assert "r-b.md: result made by no step" in problems


def test_the_design_of_a_step_is_its_whole_question(tmp_path):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("title: T\npace: design\n")
    _plan_only(doc)
    # S1 names no hypothesis and relies on nothing; a decision under Q1 and the premise P1 still count
    _page(doc, "p/step/s-a.md", "id: s-a\ntype: step\ntitle: Run\nshort: Runs.\nparent: q-a\nstatus: planned")
    _page(doc, "p/decision/d-a.md", "id: d-a\ntype: decision\ntitle: Method\nshort: This way.\nparent: q-a\n"
          "status: decided")
    _sign(doc, "experiment/home.md", "question/q-a.md", "step/s-a.md")
    tree = nodes.load_tree(doc)
    design = {node.id for node in graph.design_of(tree, tree.nodes["p:s-a"])}
    assert {"home", "q-a", "h-a", "p-a", "d-a", "s-a"} <= design
    assert graph.go_action(tree, tree.nodes["p:s-a"]) == ""
    route = {stage["key"]: stage["state"] for stage in graph.question_route(tree, tree.nodes["p:q-a"])["stages"]}
    assert route["run"] == "later" and route["plan"] == "you"
    _sign(doc, "hypothesis/h-a.md", "premise/p-a.md", "decision/d-a.md")
    assert graph.go_action(nodes.load_tree(doc), tree.nodes["p:s-a"]) == "run the step"


def test_a_conclusion_relied_on_brings_its_results(tmp_path):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("title: T\npace: design\n")
    _sign(doc, "experiment/home.md", "premise/p-a.md", "question/q-a.md", "hypothesis/h-a.md", "step/s-a.md",
          "conclusion/c-a.md")                            # C1 signed, its result R1 not
    _page(doc, "p/question/q-b.md", "id: q-b\ntype: question\ntitle: Then?\nshort: Next.\nparent: home\nstatus: open"
          + SIGN)
    _page(doc, "p/step/s-b.md", "id: s-b\ntype: step\ntitle: Build on C1\nshort: Uses it.\nparent: q-b\n"
          "status: planned\nrelations:\n  relies_on: [c-a]" + SIGN)
    _page(doc, "p/step/s-c.md", "id: s-c\ntype: step\ntitle: Also\nshort: Also.\nparent: q-b\n"
          "status: planned\nrelations:\n  relies_on: [c-a]" + SIGN)
    tree = nodes.load_tree(doc)
    assert "p:r-a" in {node.key for node in graph.design_of(tree, tree.nodes["p:s-b"])}
    assert graph.go_action(tree, tree.nodes["p:s-b"]) == ""
    route = {stage["key"]: stage for stage in graph.question_route(tree, tree.nodes["p:q-b"])["stages"]}
    assert route["run"]["state"] == "you" and [node.id for node in route["run"]["pages"]] == ["r-a"]
    assert graph.stage_action(tree, [tree.nodes["p:s-b"], tree.nodes["p:s-c"]]) == ""   # no plan item for blocked steps


def test_a_decision_written_after_the_run_does_not_fault_the_step(tmp_path):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("title: T\npace: design\n")
    _sign(doc, "experiment/home.md", "premise/p-a.md", "question/q-a.md", "hypothesis/h-a.md", "step/s-a.md")
    _git(tmp_path, "init", "-q")
    result = (doc / "p/result/r-a.md").read_text()
    (doc / "p/result/r-a.md").unlink()
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "the design")
    (doc / "p/result/r-a.md").write_text(result)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "the run")
    _page(doc, "p/decision/d-a.md", "id: d-a\ntype: decision\ntitle: Deviation\nshort: Changed.\nparent: q-a\n"
          "status: decided")                              # recorded after the run, not yet signed
    assert not any("s-a.md" in problem for problem in nodes.load_tree(doc).problems)


def test_a_shallow_clone_skips_the_commit_order_with_a_note(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    doc = _doc(origin)
    (origin / "kea.yaml").write_text("title: T\npace: design\n")
    result = (doc / "p/result/r-a.md").read_text()
    (doc / "p/result/r-a.md").unlink()
    _git(origin, "init", "-q")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-qm", "the design")
    (doc / "p/result/r-a.md").write_text(result)
    _git(origin, "add", "-A")
    _git(origin, "commit", "-qm", "the run")
    _git(tmp_path, "clone", "-q", "--depth", "1", f"file://{origin}", "shallow")
    tree = nodes.load_tree(tmp_path / "shallow" / "doc")
    assert not any("fixed_before_results: true, but" in problem for problem in tree.problems)
    assert any("shallow clone" in note for note in tree.notes)


def test_a_move_out_of_doc_and_back_is_not_a_new_hypothesis(tmp_path):
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("title: T\npace: design\n")
    result = (doc / "p/result/r-a.md").read_text()
    (doc / "p/result/r-a.md").unlink()
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "the design")
    (doc / "p/result/r-a.md").write_text(result)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "the run")
    (tmp_path / "attic").mkdir()
    _git(tmp_path, "mv", "doc/p/hypothesis/h-a.md", "attic/h-a.md")
    _git(tmp_path, "commit", "-qm", "out")
    _git(tmp_path, "mv", "attic/h-a.md", "doc/p/hypothesis/h-a.md")
    _git(tmp_path, "commit", "-qm", "back")
    assert not any("fixed_before_results: true, but" in problem for problem in nodes.load_tree(doc).problems)


def test_unreviewed_conclusions_read_as_drafts(tmp_path):
    from kea.docsite import render
    doc = _doc(tmp_path)
    (tmp_path / "kea.yaml").write_text("title: T\npace: design\n")
    _sign(doc, "experiment/home.md", "premise/p-a.md", "question/q-a.md", "hypothesis/h-a.md", "step/s-a.md")
    tree = nodes.load_tree(doc)
    assert "draft · not reviewed" in render.status_pill(tree.nodes["p:c-a"])
    assert "draft" not in render.status_pill(tree.nodes["p:r-a"])            # a result waits as before
    _sign(doc, "result/r-a.md", "conclusion/c-a.md")
    assert "draft" not in render.status_pill(nodes.load_tree(doc).nodes["p:c-a"])
