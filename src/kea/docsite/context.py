"""kea context: what the agent must take into account before working on a question (or a whole experiment).

    kea context <question-id | project:id>     the question's part of the knowledge tree
    kea context <experiment>                   the experiment: open work, open caveats, decisions in force

Printed as Markdown for the agent to read at the start of an analysis run. For a question:
    - the question and its answer so far (answer:, conclusions, results, hypotheses with when they were written);
    - the premises the experiment relies on and the decisions in force (the method as it stands);
    - every caveat that limits the question or any page of its evidence, open ones first;
    - open reader comments on any of these pages;
    - gaps: what the tree still lacks for this question (hypotheses not tested, results without sources, …).
For an experiment: every question with its state, all open caveats, the decisions in force, open comments and gaps.
Each line names the source file to read or edit. Reads only; writes nothing.
"""
from __future__ import annotations

import argparse
import sys

from kea.docsite import questions
from kea.docsite.nodes import PROJECT_ROOT, TYPE_LABELS, Node, Tree, load_tree

OPEN_CAVEAT = ("open", "questioned", None, "")         # caveat statuses that still constrain the work


def rel(path) -> str:
    """A source path relative to the project when it lies inside it."""
    if not path:
        return ""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def line(node: Node, extra: str = "") -> str:
    status = f" [{node.status}]" if node.status else ""
    path = rel(node.source)
    return f"- {node.number or TYPE_LABELS.get(node.type, node.type)} {node.title}{status}{extra} — {node.short} (`{path}`)"


def written(node: Node) -> str:
    fixed = node.header.get("fixed_before_results")
    return " (written before its test)" if fixed is True else " (written after results)" if fixed is False else \
        " (when written: not stated)"


def of_type(tree: Tree, project: str, node_type: str) -> list[Node]:
    return sorted((node for node in tree.nodes.values() if node.project == project and node.type == node_type),
                  key=questions.ORDER)


def caveats_for(tree: Tree, keys: set[str]) -> list[Node]:
    """Caveats that limit any of these pages (or the experiment as a whole: caveats without limits:)."""
    found = []
    for node in tree.nodes.values():
        if node.type != "caveat":
            continue
        limits = set(node.relations.get("limits", []))
        if limits & keys:
            found.append(node)
    return sorted(found, key=lambda node: (node.status not in OPEN_CAVEAT, questions.ORDER(node)))


def open_threads(keys: set[str]) -> list[str]:
    try:
        from kea.feedback import store
        threads = store.threads()
    except Exception:                    # no feedback folder yet
        return []
    return [f"- {thread.page} · {thread.status} · {thread.author}: {thread.text[:160]!r}"
            + (f" (on: {thread.quote[:80]!r})" if thread.quote else "")
            for thread in threads if thread.page in keys and thread.status in ("open", "planned")]


def gaps_for_question(tree: Tree, question: Node, hypotheses, results, conclusions) -> list[str]:
    gaps = []
    if conclusions and not questions.answer(question):
        gaps.append(f"{question.number} has conclusions but no `answer:` summary")
    if not hypotheses:
        gaps.append(f"{question.number} has no hypothesis: write one (fixed_before_results: true) before testing, "
                    "or label the work exploratory")
    tested = {key for result in results for key in result.relations.get("tests", [])}
    for hypothesis in hypotheses:
        if hypothesis.header.get("fixed_before_results") is None:
            gaps.append(f"{hypothesis.number}: fixed_before_results not stated")
        if hypothesis.key not in tested and hypothesis.status in (None, "", "open"):
            gaps.append(f"{hypothesis.number} is not tested yet")
    for result in results:
        if not result.header.get("sources"):
            gaps.append(f"{result.number}: no sources (every number must come from a named file)")
    for conclusion in conclusions:
        if not conclusion.relations.get("supported_by") and not conclusion.relations.get("opposed_by"):
            gaps.append(f"{conclusion.number}: no supported_by / opposed_by")
    return gaps


def question_context(tree: Tree, question: Node) -> str:
    hypotheses, results, conclusions = questions.evidence(tree, question)
    project = question.project
    keys = {question.key} | {node.key for node in hypotheses + results + conclusions}
    premises = of_type(tree, project, "premise")
    decisions = [node for node in of_type(tree, project, "decision") if node.status not in ("superseded", "dropped")]
    caveats = caveats_for(tree, keys | {node.key for node in premises + decisions})     # the method's limits count too
    out = [f"# Context for {question.number} {question.title}", "",
           f"Experiment `{project}` · status {question.status or '–'} · `{rel(question.source)}`", "",
           f"Answer so far: {questions.answer(question) or '(no answer: yet)'}", ""]
    sections = [
        ("Conclusions", [line(node) for node in conclusions]),
        ("Results", [line(node) for node in results]),
        ("Hypotheses", [line(node, written(node)) for node in hypotheses]),
        ("Premises the experiment relies on (take as given, or question explicitly)", [line(node) for node in premises]),
        ("Decisions in force (the method as it stands; change one only with a new decision page)",
         [line(node) for node in decisions]),
        ("Caveats on this question's pages, its premises and decisions (open ones first: address them, or say how "
         "they limit the new result)",
         [line(node, " limits " + ", ".join(tree.nodes[key].number or key for key in node.relations.get("limits", [])
                                             if key in tree.nodes)) for node in caveats]),
        ("Open reader comments on these pages", open_threads(keys | {node.key for node in caveats})),
        ("Gaps", [f"- {gap}" for gap in gaps_for_question(tree, question, hypotheses, results, conclusions)]),
    ]
    for heading, lines in sections:
        out += [f"## {heading}", ""] + (lines or ["- none"]) + [""]
    return "\n".join(out)


def experiment_context(tree: Tree, project: str) -> str:
    home = tree.projects[project]
    intro, _ = questions.split_intro(home.body)
    out = [f"# Context for experiment {project}: {home.title}", "",
           f"Summary: {' '.join(intro.split()) or '(no summary before the first ## heading)'}", "", "## Questions", ""]
    gaps = []
    for question in questions.questions(tree, project):
        hypotheses, results, conclusions = questions.evidence(tree, question)
        out.append(line(question, f" · {len(hypotheses)} hypotheses, {len(results)} results, "
                                  f"{len(conclusions)} conclusions"))
        gaps += gaps_for_question(tree, question, hypotheses, results, conclusions)
    all_caveats = of_type(tree, project, "caveat")
    caveats = [node for node in all_caveats if node.status in OPEN_CAVEAT]
    handled = [node for node in all_caveats if node.status not in OPEN_CAVEAT]
    decisions = [node for node in of_type(tree, project, "decision") if node.status not in ("superseded", "dropped")]
    keys = {node.key for node in tree.nodes.values() if node.project == project}
    for heading, lines in [("Open caveats", [line(node) for node in caveats]),
                           ("Addressed caveats (dealt with once; check that new work does not reopen them)",
                            [line(node) for node in handled]),
                           ("Decisions in force", [line(node) for node in decisions]),
                           ("Premises", [line(node) for node in of_type(tree, project, "premise")]),
                           ("Open reader comments", open_threads(keys)),
                           ("Gaps", [f"- {gap}" for gap in gaps])]:
        out += ["", f"## {heading}", ""] + (lines or ["- none"])
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kea context", description=__doc__.split("\n")[0])
    parser.add_argument("target", help="a question id (q-x or experiment:q-x) or an experiment name")
    args = parser.parse_args(argv)
    tree = load_tree()
    if args.target in tree.projects:
        print(experiment_context(tree, args.target))
        return 0
    node = tree.resolve(args.target, next(iter(tree.projects), ""))
    if node is None:
        print(f"unknown page or experiment {args.target!r}", file=sys.stderr)
        return 1
    if node.type == "question":
        print(question_context(tree, node))
        return 0
    if node.id == "home":
        print(experiment_context(tree, node.project))
        return 0
    owners = [question for question in questions.questions(tree, node.project)
              if node.key in {item.key for group in questions.evidence(tree, question) for item in group}]
    if not owners:
        print(f"{args.target} belongs to no question; showing its experiment", file=sys.stderr)
        print(experiment_context(tree, node.project))
        return 0
    for question in owners:
        print(question_context(tree, question))
    return 0
