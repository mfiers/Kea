"""Executive summaries: what each question's answer is and which pages carry it (shared by the site and the PDF).

A question's executive summary is its front-matter field ``answer:`` (two or three plain sentences: the answer,
how sure, the main limit), followed by the conclusions and results that answer it. An experiment's executive
summary is the text of its home page before the first ``##`` heading; the project's is ``doc/_summary.md``
(or, with a single experiment, that experiment's).
"""
from __future__ import annotations

import re

from kea.docsite.nodes import DOC, Node, Tree, split_front_matter

ORDER = lambda node: (len(node.number), node.number, node.id)      # noqa: E731  (Q2 before Q10)


def questions(tree: Tree, project: str) -> list[Node]:
    return sorted((node for node in tree.nodes.values() if node.project == project and node.type == "question"),
                  key=ORDER)


def evidence(tree: Tree, question: Node) -> tuple[list[Node], list[Node], list[Node]]:
    """(hypotheses, results, conclusions) that belong to a question.

    Hypotheses: its children, or pages that answer it. Results: its children, results that answer it or test one of
    its hypotheses. Conclusions: its children, conclusions that answer it or are supported or opposed by one of its
    results.
    """
    members = [node for node in tree.nodes.values() if node.project == question.project]

    def points_to(node: Node, relations: tuple[str, ...], targets: set[str]) -> bool:
        return any(target in targets for relation in relations for target in node.relations.get(relation, []))

    def is_child(node: Node) -> bool:
        return node.parent == question.id

    own = {question.key}
    hypotheses = [node for node in members if node.type == "hypothesis"
                  and (is_child(node) or points_to(node, ("answers",), own))]
    tested = own | {node.key for node in hypotheses}
    results = [node for node in members if node.type == "result"
               and (is_child(node) or points_to(node, ("answers", "tests"), tested))]
    found = {node.key for node in results}
    conclusions = [node for node in members if node.type == "conclusion"
                   and (is_child(node) or points_to(node, ("answers",), own)
                        or points_to(node, ("supported_by", "opposed_by"), found))]
    return sorted(hypotheses, key=ORDER), sorted(results, key=ORDER), sorted(conclusions, key=ORDER)


def answer(question: Node) -> str:
    return str(question.header.get("answer") or "").strip()


def split_intro(body: str) -> tuple[str, str]:
    """(text before the first ## heading, the rest): the intro of an experiment home page is its summary."""
    match = re.search(r"^## ", body, flags=re.M)
    if not match:
        return body.strip(), ""
    return body[:match.start()].strip(), body[match.start():]


def project_summary(tree: Tree) -> str:
    """The project's executive summary (Markdown): doc/_summary.md, else the only experiment's summary, else ''."""
    source = DOC / "_summary.md"
    if source.exists():
        _, text = split_front_matter(source.read_text(encoding="utf-8"), source)
        return text.strip()
    if len(tree.projects) == 1:
        home = next(iter(tree.projects.values()))
        return split_intro(home.body)[0]
    return ""
