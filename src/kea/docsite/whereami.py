"""Where am I: each page's question, and each experiment's plan for the site's question strip and corner thumbnail.

Every page of an experiment gets a home question (and, when it serves more, the others), read from the graph:

- a question is its own; hypotheses, planned steps, results and conclusions are the question's route
  (questions.evidence, graph.question_steps), and a page under a question (parent chain) belongs to it;
- every other page takes the questions of the pages it is linked with (relations in either direction, a few
  passes), never through the experiment page, a resource, a term or a reference, and never across experiments;
- the home question is the parent question, else the one it is most tied to (ties: the lowest number); a page
  tied to more than half of the questions (and to at least three) is experiment-wide and gets none.

`plan(tree, project, hrefs)` is what kea build writes to `<experiment>/_where.json` for kea.js (the thumbnail and
the `m` minimap); `strip_html` is the question strip under the breadcrumbs. Pages without a question (terms,
shared resources) show neither.
"""
from __future__ import annotations

from collections import Counter

from kea.docsite.nodes import Node, Tree, natural
from kea.docsite.render import esc, tag_inner

ROUTE = ("hypothesis", "step", "result", "figure", "conclusion")          # the thumbnail's rows, top down
BESIDE = ("caveat", "decision", "premise")                                 # the strip's "beside" part
HUBS = ("experiment", "resource", "term", "reference")                     # never carry a question further
ROUTE_WEIGHT, PARENT_WEIGHT, LINK_WEIGHT = 10, 50, 1


def _parent_question(tree: Tree, node: Node) -> Node | None:
    seen: set[str] = set()
    current = tree.nodes.get(f"{node.project}:{node.parent}") if node.parent else None
    while current is not None and current.key not in seen:
        if current.type == "question":
            return current
        seen.add(current.key)
        current = tree.nodes.get(f"{current.project}:{current.parent}") if current.parent else None
    return None


def questions_of(tree: Tree) -> dict[str, tuple[str | None, list[str]]]:
    """page key -> (home question key or None, the other questions' keys). Computed once per tree."""
    cached = getattr(tree, "_whereami", None)
    if cached is not None:
        return cached
    from kea.docsite import graph, questions
    ties: dict[str, Counter] = {}
    number = {}
    for project in tree.projects:
        for index, question in enumerate(questions.questions(tree, project)):
            number[question.key] = index
            ties.setdefault(question.key, Counter())[question.key] += 1000
            hypotheses, results, conclusions = questions.evidence(tree, question)
            for node in hypotheses + graph.question_steps(tree, question, hypotheses) + results + conclusions:
                ties.setdefault(node.key, Counter())[question.key] += ROUTE_WEIGHT
    parents = {}
    for node in tree.nodes.values():
        parent = _parent_question(tree, node)
        if parent is not None and node.type != "question":
            parents[node.key] = parent.key
            ties.setdefault(node.key, Counter())[parent.key] += PARENT_WEIGHT
    for _ in range(3):                      # pages linked to pages that have a question
        for node in tree.nodes.values():
            if node.type in ("question", "experiment") or ties.get(node.key):
                continue
            linked = Counter()
            for keys in list(node.relations.values()) + list(node.incoming.values()):
                for key in keys:
                    other = tree.nodes.get(key)
                    if other is None or other.type in HUBS or other.project != node.project:
                        continue
                    for question in ties.get(key, {}):
                        if question.split(":")[0] == node.project:
                            linked[question] += LINK_WEIGHT
            if linked:
                ties[node.key] = linked
    # hubs (resources, terms, references) take the questions of the pages that use them, without passing them on
    for node in tree.nodes.values():
        if node.type in HUBS and node.type != "experiment" and not ties.get(node.key):
            linked = Counter()
            for keys in list(node.relations.values()) + list(node.incoming.values()):
                for key in keys:
                    other = tree.nodes.get(key)
                    if other is not None and other.project == node.project and other.type not in HUBS:
                        for question in ties.get(key, {}):
                            linked[question] += LINK_WEIGHT
            if linked:
                ties[node.key] = linked
    counts = Counter(node.project for node in tree.nodes.values() if node.type == "question")
    result: dict[str, tuple[str | None, list[str]]] = {}
    for node in tree.nodes.values():
        if node.type == "experiment":
            continue
        tied = ties.get(node.key) or Counter()
        if node.type == "question":
            result[node.key] = (node.key, [])
            continue
        ranked = sorted(tied, key=lambda key: (-tied[key], number.get(key, 999)))
        if node.key in parents:
            ranked = [parents[node.key]] + [key for key in ranked if key != parents[node.key]]
        if len(ranked) >= 3 and len(ranked) > counts[node.project] / 2 and node.key not in parents:
            result[node.key] = (None, ranked)          # experiment-wide
        else:
            result[node.key] = (ranked[0] if ranked else None, ranked[1:])
    tree._whereami = result
    return result


def home_question(tree: Tree, node: Node) -> Node | None:
    home = questions_of(tree).get(node.key, (None, []))[0]
    return tree.nodes.get(home) if home else None


def also_questions(tree: Tree, node: Node) -> list[Node]:
    home, also = questions_of(tree).get(node.key, (None, []))
    return [tree.nodes[key] for key in also if key in tree.nodes] if home else []


def members(tree: Tree, question: Node) -> dict[str, list[Node]]:
    """type -> the pages whose home is this question, in number order."""
    home = questions_of(tree)
    found: dict[str, list[Node]] = {}
    for node in tree.nodes.values():
        if node.project == question.project and node.key != question.key and home.get(node.key, (None,))[0] == question.key:
            found.setdefault(node.type, []).append(node)
    for nodes in found.values():
        nodes.sort(key=lambda node: natural(node.number or node.id))
    return found


def plan(tree: Tree, project: str, hrefs: dict[str, str]) -> dict:
    """The experiment's plan for kea.js: its questions in order, per question the route pages by stage, and every
    page with its home question (hrefs: page key -> path from the site root)."""
    from kea.docsite import graph, questions
    rows = [kind for kind in ROUTE if any(node.project == project and node.type == kind for node in tree.nodes.values())]
    entries, pages = [], {}

    def page_entry(node: Node) -> dict:
        return {"label": node.tag or node.title, "title": node.title, "type": node.type, "href": hrefs.get(node.key, ""),
                "signed": graph.approved(node)}
    for question in questions.questions(tree, project):
        mine = members(tree, question)
        entries.append({"key": question.key, "label": question.number, "title": question.title,
                        "href": hrefs.get(question.key, ""), "signed": graph.approved(question),
                        "cells": {kind: [node.key for node in mine.get(kind, [])] for kind in rows},
                        "beside": [node.key for kind in BESIDE for node in mine.get(kind, [])]})
        pages[question.key] = {**page_entry(question), "home": question.key}
        for kind_nodes in mine.values():
            for node in kind_nodes:
                pages[node.key] = {**page_entry(node), "home": question.key}
    return {"project": project, "rows": rows, "questions": entries, "pages": pages}


def chip_html(tree: Tree, node: Node, prefix: str) -> str:
    """The menu bar's question chip (tag only, the question on hover), '+n' when the page serves more."""
    if node.type in ("question", "experiment"):
        return ""
    question = home_question(tree, node)
    if question is None:
        return ""
    more = also_questions(tree, node)
    extra = (f"<span class='q-more' title='Also: {esc(', '.join(item.number + ' ' + item.title for item in more))}'>"
             f"+{len(more)}</span>") if more else ""
    return (f"<span class='seg qseg'><span class='sep'>/</span><a class='tag t-question' href='{prefix}{question.url}' "
            f"title='{esc(question.number + ' · ' + question.title)}'>{tag_inner(question)}</a>{extra}</span>")


def strip_html(tree: Tree, node: Node, prefix: str) -> str:
    """The question strip under the breadcrumbs: the question's route (hypotheses, steps, results, figures,
    conclusions) and what sits beside it (caveats, decisions, premises), each page a tag, filled when signed,
    outlined when not, ringed for this page; a kind with more than eight pages folds to a count."""
    from kea.docsite import graph
    question = node if node.type == "question" else home_question(tree, node)
    if question is None:
        return ""
    mine = members(tree, question)

    def chip(item: Node) -> str:
        state = ("" if graph.approved(item) else " st-open") + (" st-here" if item.key == node.key else "")
        return (f"<a class='st t-{esc(item.type)}{state}' data-key='{esc(item.key)}' href='{prefix}{item.url}' "
                f"title='{esc(item.tag + ' · ' + item.title + (' · signed' if graph.approved(item) else ' · not signed'))}'>"
                f"{esc(item.tag)}</a>")

    def group(kind: str, items: list[Node]) -> str:
        if not items:
            return ""
        signed = sum(graph.approved(item) for item in items)
        letter = items[0].tag[:1] if items[0].tag else kind[:1].upper()
        count = (f"<span class='st st-count t-{esc(kind)}{'' if signed == len(items) else ' st-open'}' title='{signed} of {len(items)} signed'>"
                 f"{esc(letter)} {signed}/{len(items)}</span>")
        here = [item for item in items if item.key == node.key]
        if len(items) > 8:
            return f"<span class='st-group st-folded'>{count}{''.join(chip(item) for item in here)}</span>"
        return f"<span class='st-group'><span class='st-all'>{''.join(chip(item) for item in items)}</span>{count}</span>"
    route = [group(kind, mine.get(kind, [])) for kind in ROUTE]
    beside = [group(kind, mine.get(kind, [])) for kind in BESIDE]
    on_route = [item for kind in ROUTE for item in mine.get(kind, [])]
    total = len(on_route)
    waiting = sum(not graph.approved(item) for item in on_route)
    if node in on_route:
        where = f"{esc(node.tag)} · {on_route.index(node) + 1} of {total}"
    elif node.type == "question":
        where = f"{total} page{'s' if total != 1 else ''}"
    else:
        where = f"{esc(node.tag or node.title)} · beside {esc(question.number)}"
    where += f" · {waiting} not signed" if waiting else " · all signed"
    sep = "<span class='st-dot'>·</span>"
    parts = [f"<a class='st t-question{'' if graph.approved(question) else ' st-open'}{' st-here' if question.key == node.key else ''}' "
             f"href='{prefix}{question.url}' title='{esc(question.number + ' · ' + question.title)}'>{esc(question.number)}</a>"]
    parts += [sep + item for item in route if item]
    if any(beside):
        parts.append("<span class='st-beside'>beside</span>" + "".join(item for item in beside if item))
    return (f"<div class='qstrip not-annotatable' data-question='{esc(question.key)}'>{''.join(parts)}"
            f"<span class='st-where'>{where}</span></div>")
