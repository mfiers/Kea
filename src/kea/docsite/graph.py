"""The reasoning graph as a whole (Kea 1.19): structural soundness, and pages to recheck after an upstream change.

1. Structure (:func:`structure`): rules over the whole graph, beyond the per-link type checks in nodes._validate.
   Problems (they fail `kea build --strict`, so every iteration runs them):
     - a conclusion rests on no result: none of its evidence (supports/opposes, supported_by/opposed_by), directly
       or through conclusions it rests on, is a result or a figure of this analysis;
     - circular support: conclusions that support each other in a loop;
     - a conclusion rests on a hypothesis or a question (relies_on): a claim derives from results, not from what
       was expected or asked;
     - a live conclusion rests on deprecated evidence;
     - a confirmatory conclusion whose evidence is all exploratory;
     - a hypothesis with an outcome (supported, not_supported, inconclusive) that no result tests.
   Notes: a question marked answered that no result or conclusion answers; a result made by no step and from no artefact; high certainty on exploratory evidence only, or while an
   open caveat limits the conclusion; a premise marked supported with nothing behind it.

2. Rechecks (:func:`compromised`): every page depends on the pages upstream of it (its evidence, the steps,
   artefacts, decisions and resources it was made with, what it relies on, the caveats that limit it; a
   hypothesis's outcome on the steps and results that test it, a question's answer on what answers it). The ledger ``doc/_checks.yaml`` holds, per page, the fingerprint of each
   upstream page when the page was last checked against it. When an upstream page changes in substance (title,
   summary, text, status or fields; not its order or confirmation), the page is *compromised* until the agent
   rechecks it (`kea recheck <id> --because "…"`), and so is everything downstream of it ("via"). A page without a
   ledger entry, or a link without one, is taken as checked now (the baseline is written by `kea build` and
   `kea check`), so adopting this does not flag a whole project.

3. Pace (:func:`pace_rules`, when kea.yaml says ``pace: guided``, the default of kea init): one step along the
   route at a time, each reviewed by the owner before the next builds on it. Problems: a hypothesis or step under a
   question nobody approved; a step running or done without approval; a conclusion from results nobody reviewed.
   Approval is ``approved:`` (the owner in chat, or a Confirm applied at a harvest) or ``confirmed:``.
   :func:`next_steps` says, per question, the one next step or what it waits for (kea context).

Input: a loaded nodes.Tree, doc/_checks.yaml and kea.yaml (pace). Output: problems and notes on the tree; tree.compromised
{page key: reasons}; the ledger (baseline and rechecks).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import yaml

from kea.docsite.nodes import Node, Tree, analysis_of

LEDGER_NAME = "_checks.yaml"
OUTCOMES = ("supported", "not_supported", "inconclusive")
EVIDENCE_TYPES = ("result", "figure")
# header fields that do not change what a page says
COSMETIC_FIELDS = {"order", "confirmed", "approved", "uid", "rechecked", "link", "aliases"}
# relations written on a page that make it depend on the target
DEPENDS_ON = {"supported_by", "opposed_by", "relies_on", "made_by", "from_artefact", "derived_from", "decided_in",
              "uses", "cites", "addressed_by"}
# relations written on a page that make the *target* depend on it: a question's answer on what answers it, a
# hypothesis's outcome on what tests it, a figure on the result it shows, a page on the caveats that limit it
FEEDS = {"supports", "opposes", "shown_in", "limits", "answers", "tests"}


# ------------------------------------------------------------------ structure

def evidence(tree: Tree, node: Node) -> list[Node]:
    """The pages offered for or against a claim: its supported_by/opposed_by and the supports/opposes into it."""
    keys = list(node.relations.get("supported_by", [])) + list(node.relations.get("opposed_by", []))
    keys += [other.key for other in tree.nodes.values()
             if node.key in other.relations.get("supports", []) + other.relations.get("opposes", [])]
    seen, result = set(), []
    for key in keys:
        if key in tree.nodes and key not in seen:
            seen.add(key)
            result.append(tree.nodes[key])
    return result


def _rests_on_results(tree: Tree, node: Node, path: tuple[str, ...] = ()) -> bool:
    for item in evidence(tree, node):
        if item.type in EVIDENCE_TYPES:
            return True
        if item.type == "conclusion" and item.key not in path and _rests_on_results(tree, item, path + (node.key,)):
            return True
    return False


def _support_cycle(tree: Tree, start: Node) -> list[str]:
    """A loop of conclusions supporting each other that passes through start ([] if none)."""
    stack = [(start, [start.key])]
    while stack:
        node, path = stack.pop()
        for item in evidence(tree, node):
            if item.type != "conclusion":
                continue
            if item.key == start.key:
                return path
            if item.key not in path:
                stack.append((item, path + [item.key]))
    return []


def structure(tree: Tree) -> None:
    """Add the whole-graph problems and notes to the tree (see the module docstring)."""
    reported_cycles: set[frozenset] = set()
    for node in tree.nodes.values():
        where = _where(node)
        live = node.status not in ("deprecated", "superseded", "dropped")
        if node.type == "conclusion" and live:
            items = evidence(tree, node)
            if not _rests_on_results(tree, node):
                tree.problems.append(f"{where}: conclusion rests on no result: link the results or figures it "
                                     "derives from (supported_by / opposed_by), directly or through another conclusion")
            loop = _support_cycle(tree, node)
            if loop and frozenset(loop) not in reported_cycles:
                reported_cycles.add(frozenset(loop))
                labels = " → ".join(tree.nodes[key].label for key in loop + [node.key])
                tree.problems.append(f"{where}: circular support ({labels}): a conclusion cannot rest on itself")
            for key in node.relations.get("relies_on", []):
                target = tree.nodes.get(key)
                if target is not None and target.type in ("hypothesis", "question"):
                    tree.problems.append(f"{where}: conclusion relies on {target.type} {target.label}: a conclusion "
                                         f"derives from results; link the result that tests or answers it")
            stale = [item.label for item in items if item.status in ("deprecated", "superseded")]
            if stale:
                tree.problems.append(f"{where}: rests on deprecated evidence ({', '.join(stale)}): recheck the "
                                     "conclusion, or deprecate it too")
            results = [item for item in items if item.type in EVIDENCE_TYPES]
            exploratory = results and all(analysis_of(item) == "exploratory" for item in results)
            if exploratory and analysis_of(node) == "confirmatory":
                tree.problems.append(f"{where}: confirmatory conclusion on exploratory evidence only "
                                     f"({', '.join(item.label for item in results)}); mark it exploratory or test it "
                                     "on new data")
            if node.header.get("certainty") == "high":
                if exploratory:
                    tree.notes.append(f"{where}: certainty high on exploratory evidence only")
                limiting = [other.label for other in tree.nodes.values() if other.type == "caveat"
                            and other.status == "open" and node.key in other.relations.get("limits", [])]
                if limiting:
                    tree.notes.append(f"{where}: certainty high while open caveat(s) {', '.join(limiting)} limit it")
        if node.type == "hypothesis" and node.status in OUTCOMES:
            if not _tested_by_result(tree, node):
                tree.problems.append(f"{where}: hypothesis is {node.status} but no result tests it (a result with "
                                     "tests:, or made by a step that tests it)")
        if node.type == "question" and node.status == "answered":
            if not any(node.key in other.relations.get("answers", []) for other in tree.nodes.values()):
                tree.notes.append(f"{where}: question marked answered, but no result or conclusion answers it "
                                  "(link them with answers:)")
        if node.type == "result" and live and not (node.relations.get("made_by") or node.relations.get("from_artefact")):
            tree.notes.append(f"{where}: result made by no step and from no artefact (made_by:)")
        if node.type == "premise" and node.status == "supported" and not evidence(tree, node):
            tree.notes.append(f"{where}: premise marked supported with nothing behind it (supported_by:)")


# ------------------------------------------------------------------ pace (kea.yaml pace: guided)

RUNNING = ("in_progress", "done")


def approved(node: Node) -> bool:
    """The owner (or a reader with the right) reviewed the page: approved: (in chat, or applied at a harvest) or
    confirmed: (a Confirm on the site)."""
    return bool(node.header.get("approved") or node.header.get("confirmed"))


def pace_rules(tree: Tree) -> None:
    """One step along the route at a time, each reviewed before the next builds on it: hypotheses and steps only
    under an approved question, a step runs only when approved, conclusions only from approved results."""
    for node in tree.nodes.values():
        where = _where(node)
        parent = tree.nodes.get(f"{node.project}:{node.parent}") if node.parent else None
        if node.type == "question" and parent is not None and parent.type == "experiment" and not approved(parent):
            tree.problems.append(f"{where}: written under an experiment the owner has not approved yet (pace: "
                                 "guided): write the experiment's summary and scope, stop, and let it be reviewed")
        if node.type in ("hypothesis", "step") and parent is not None and parent.type == "question" \
                and not approved(parent):
            tree.problems.append(f"{where}: written under question {parent.label}, which the owner has not approved "
                                 "yet (pace: guided): stop after proposing the question and let it be reviewed")
        if node.type == "step" and node.status in RUNNING and not approved(node):
            tree.problems.append(f"{where}: step is {node.status} but was not approved (pace: guided): a planned "
                                 "step runs only after the owner approves it (Confirm on its page, or in chat: "
                                 "approved: {by, date, how: chat})")
        if node.type == "conclusion" and node.status not in ("deprecated", "superseded"):
            unread = [item.label for item in evidence(tree, node) if item.type in EVIDENCE_TYPES and not approved(item)]
            if unread:
                tree.problems.append(f"{where}: drawn from result(s) {', '.join(unread)} that the owner has not "
                                     "reviewed yet (pace: guided): write the results, stop, and conclude after review")


WAITING_TYPES = ("experiment", "question", "hypothesis", "step", "result")


def waiting(node: Node) -> bool:
    """Under pace: guided, a page waiting for the owner's approval before the next step builds on it: a question, a
    planned hypothesis or step, or a result, without approved:/confirmed:."""
    if node.type not in WAITING_TYPES or approved(node):
        return False
    if node.type in ("hypothesis", "step"):
        return node.status == "planned"
    if node.type == "question":
        return node.status not in ("dropped", "answered")
    if node.type == "experiment":
        return node.status == "open"
    return node.status != "deprecated"                       # a result


CARRIED_BY = {"conclusion": ("supported_by",), "result": ("made_by", "from_artefact"),
              "figure": ("made_by", "from_artefact"), "artefact": ("made_by", "derived_from"), "step": ("tests",),
              "caveat": ("limits",)}
BACKGROUND = ("premise", "decision", "resource", "reference", "term", "experiment")


def carriers(tree: Tree, node: Node) -> set[str]:
    """What carries this page on the route: a conclusion its supporting evidence, a result or figure the step or
    artefact that made it, a step the hypothesis it tests, a caveat what it limits. Background (premises,
    decisions, resources, references, terms) frames a page but does not carry it."""
    found = {key for relation in CARRIED_BY.get(node.type, ()) for key in node.relations.get(relation, [])
             if key in tree.nodes}
    if node.type == "conclusion":
        found.update(other.key for other in tree.nodes.values() if node.key in other.relations.get("supports", []))
    if node.type == "figure":
        found.update(other.key for other in tree.nodes.values() if node.key in other.relations.get("shown_in", []))
    found.discard(node.key)
    return {key for key in found if tree.nodes[key].type not in BACKGROUND}


def drop_set(tree: Tree, key: str) -> list[str]:
    """The page, every page under it, and every page whose carriers (:func:`carriers`) are all dropped (keys, the
    page first)."""
    cache = tree.__dict__.get("_carriers")
    if cache is None:                               # once per tree: carriers() scans every page
        cache = tree.__dict__["_carriers"] = {
            node.key: (f"{node.project}:{node.parent}" if node.parent else "", carriers(tree, node))
            for node in tree.nodes.values() if node.id != "home" and node.type not in BACKGROUND}
    dropped = [key]
    changed = True
    while changed:
        changed = False
        for node_key, (parent, carried_by) in cache.items():
            if node_key in dropped:
                continue
            # everything under a dropped page goes with it; so does a page whose carriers all go
            if parent in dropped or (carried_by and carried_by <= set(dropped)):
                dropped.append(node_key)
                changed = True
    return dropped


def next_steps(tree: Tree, project: str) -> list[str]:
    """Where each question stands on the route, and the one next step (for kea context; pace: guided)."""
    from kea.docsite import questions
    lines = []
    found = questions.questions(tree, project)
    if not found:
        return ["Next: propose questions (and premises) for the experiment; then stop for the owner's review."]
    for question in found:
        hypotheses, results, conclusions = questions.evidence(tree, question)
        steps = [node for node in tree.nodes.values() if node.type == "step" and node.project == project
                 and (node.parent == question.id or any(key in [h.key for h in hypotheses]
                                                        for key in node.relations.get("tests", [])))]
        label = question.number or question.label
        if not approved(question):
            lines.append(f"{label}: waiting for the owner to review the question (Confirm on the site, or in chat).")
        elif not hypotheses and not steps:
            lines.append(f"{label}: next, write hypotheses (prediction, criterion, fixed_before_results) and planned "
                         "steps; then stop for review. Do not run anything.")
        elif [step for step in steps if step.status == "planned" and not approved(step)]:
            waiting = [step.number for step in steps if step.status == "planned" and not approved(step)]
            lines.append(f"{label}: waiting for the owner to approve the planned step(s) {', '.join(waiting)}.")
        elif [step for step in steps if step.status == "planned"]:
            ready = [step.number for step in steps if step.status == "planned"]
            lines.append(f"{label}: next, run the approved step(s) {', '.join(ready)} and write the results; then stop "
                         "for review. No conclusions yet.")
        elif [result for result in results if not approved(result)]:
            waiting = [result.number for result in results if not approved(result)]
            lines.append(f"{label}: waiting for the owner to review the result(s) {', '.join(waiting)}.")
        elif results and not conclusions:
            lines.append(f"{label}: next, write conclusions from the reviewed results, set the hypotheses' outcomes "
                         "and the answer; then stop for review.")
        else:
            lines.append(f"{label}: nothing waiting on the route; follow the comments and caveats.")
    return lines


def projects(tree: Tree, doc: Path) -> None:
    """Two or more experiments need the project's own summary (doc/_summary.md: the site starts at the project
    page); with one, a summary that repeats the experiment's is noted (the site starts at the experiment)."""
    from kea.docsite import questions
    summary = doc / "_summary.md"
    if len(tree.projects) >= 2 and not summary.exists():
        tree.problems.append(f"doc/_summary.md: the project has {len(tree.projects)} experiments but no summary of its "
                             "own (what the project asks across them, and what it found so far)")
    if len(tree.projects) == 1 and summary.exists():
        home = next(iter(tree.projects.values()))
        intro, _ = questions.split_intro(home.body)
        own = summary.read_text(encoding="utf-8")
        if own.startswith("---\n"):
            own = own.split("\n---", 1)[-1]
        if " ".join(own.split()) == " ".join(intro.split()):
            tree.notes.append("doc/_summary.md repeats the experiment's summary (with one experiment the site starts "
                              "at the experiment page): delete it, or say what the project is about beyond it")


def _tested_by_result(tree: Tree, hypothesis: Node) -> bool:
    for other in tree.nodes.values():
        if hypothesis.key not in other.relations.get("tests", []):
            continue
        if other.type == "result":
            return True
        if other.type == "step" and any(other.key in result.relations.get("made_by", [])
                                        for result in tree.nodes.values() if result.type == "result"):
            return True
    return False


def _where(node: Node):
    from kea.docsite.nodes import DOC
    return node.source.relative_to(DOC) if node.source.is_relative_to(DOC) else node.source


# ------------------------------------------------------------------ rechecks

def fingerprint(node: Node) -> str:
    """What the page says: its fields (without cosmetic ones) and text; 12 hex characters."""
    header = {key: value for key, value in node.header.items() if key not in COSMETIC_FIELDS}
    text = json.dumps(header, sort_keys=True, default=str) + "\n" + node.body.strip()
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def upstream(tree: Tree) -> dict[str, set[str]]:
    """Page key -> keys of the pages it depends on."""
    depends: dict[str, set[str]] = {key: set() for key in tree.nodes}
    for node in tree.nodes.values():
        for relation, targets in node.relations.items():
            for target in targets:
                if target not in tree.nodes or target == node.key:
                    continue
                if relation in DEPENDS_ON:
                    depends[node.key].add(target)
                elif relation in FEEDS:
                    depends[target].add(node.key)
    return depends


def ledger_path(doc: Path) -> Path:
    return doc / LEDGER_NAME


def read_ledger(doc: Path) -> dict:
    path = ledger_path(doc)
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def write_ledger(doc: Path, ledger: dict) -> None:
    head = ("# Kea's recheck ledger (docsite/graph.py): per page, the fingerprint of each page upstream of it when it\n"
            "# was last checked against it. Written by kea build / kea check (baseline) and kea recheck; commit it.\n")
    ledger_path(doc).write_text(head + yaml.safe_dump(ledger, sort_keys=True, allow_unicode=True, width=120),
                                encoding="utf-8")


def compromised(tree: Tree, ledger: dict) -> dict[str, list[str]]:
    """Page key -> why it needs a recheck ("P2 changed", "via R3"), for every page with a changed page upstream
    and every page downstream of one."""
    depends = upstream(tree)
    prints = {key: fingerprint(node) for key, node in tree.nodes.items()}
    reasons: dict[str, list[str]] = {}
    for key, sources in depends.items():
        checked = (ledger.get(key) or {}).get("upstream") or {}
        changed = [tree.nodes[source].label for source in sorted(sources)
                   if source in checked and checked[source] != prints[source]]
        if changed:
            reasons[key] = [f"{label} changed" for label in changed]
    downstream: dict[str, set[str]] = {}
    for key, sources in depends.items():
        for source in sources:
            downstream.setdefault(source, set()).add(key)
    queue = list(reasons)
    while queue:
        key = queue.pop()
        for child in sorted(downstream.get(key, ())):
            via = f"via {tree.nodes[key].label}"
            if via not in reasons.setdefault(child, []):
                reasons[child].append(via)
                queue.append(child)
    return reasons


def baseline(tree: Tree, ledger: dict) -> bool:
    """Record the current fingerprints for pages and links not yet in the ledger; True if anything was added."""
    depends = upstream(tree)
    added = False
    for key, sources in depends.items():
        if not sources:
            continue
        entry = ledger.setdefault(key, {})
        checked = entry.setdefault("upstream", {})
        for source in sources:
            if source not in checked:
                checked[source] = fingerprint(tree.nodes[source])
                added = True
        for gone in [source for source in checked if source not in sources]:
            del checked[gone]
            added = True
    return added


def recheck(tree: Tree, ledger: dict, key: str, because: str, run: str = "") -> None:
    """The agent checked the page against everything upstream of it: record the current fingerprints."""
    sources = upstream(tree).get(key, set())
    ledger[key] = {"upstream": {source: fingerprint(tree.nodes[source]) for source in sorted(sources)},
                   "checked": dt.date.today().isoformat(), "because": because, **({"run": run} if run else {})}


def apply(tree: Tree, doc: Path, write_baseline: bool) -> None:
    """Structure checks, the baseline (when asked) and the compromised pages, all on the tree."""
    structure(tree)
    projects(tree, doc)
    from kea.config import load_settings
    tree.pace = str(load_settings(doc.parent).get("pace") or "free")
    if tree.pace == "guided":
        pace_rules(tree)
        for node in tree.nodes.values():
            node.waiting = waiting(node)
    ledger = read_ledger(doc)
    if write_baseline and baseline(tree, ledger):
        write_ledger(doc, ledger)
    tree.compromised = compromised(tree, ledger)
    for key, why in tree.compromised.items():
        tree.nodes[key].recheck = why
    if tree.compromised:
        direct = sorted(tree.nodes[key].label for key, why in tree.compromised.items()
                        if any(not reason.startswith("via ") for reason in why))
        tree.notes.append(f"{len(tree.compromised)} page(s) to recheck after an upstream change (directly: "
                          f"{', '.join(direct[:12])}); kea recheck --list, then kea recheck <id> --because \"…\"")


def drop_main(argv: list[str]) -> int:
    """kea drop <id>: list the page and every page that rests only on it (what a Drop removes); writes nothing."""
    from kea.docsite.nodes import DOC, load_tree
    if len(argv) != 1:
        print("usage: kea drop <id>   (lists what a Drop of that page removes; changes nothing)")
        return 2
    tree = load_tree(DOC)
    node = tree.resolve(argv[0], next(iter(tree.projects), ""))
    if node is None:
        print(f"no page {argv[0]!r}")
        return 1
    keys = drop_set(tree, node.key)
    for key in keys:
        item = tree.nodes[key]
        print(f"{item.project}:{item.id}  {item.label}  {item.type}  {item.title}")
    kept = sorted({tree.nodes[other].label for other in tree.nodes for key in keys
                   if other not in keys and key in upstream(tree).get(other, set())})
    print(f"{len(keys)} page(s) dropped; still resting partly on them (recheck): {', '.join(kept) or 'none'}")
    return 0


def main(argv: list[str]) -> int:
    """kea recheck --list | kea recheck <id> [<id> …] --because "…" [--run R]"""
    import argparse
    from kea.docsite.nodes import DOC, load_tree
    parser = argparse.ArgumentParser(prog="kea recheck", description="pages to recheck after an upstream change")
    parser.add_argument("ids", nargs="*")
    parser.add_argument("--list", action="store_true", help="the pages to recheck and why")
    parser.add_argument("--because", default="", help="what the check found (required with ids)")
    parser.add_argument("--run", default="")
    args = parser.parse_args(argv)
    tree = load_tree(DOC)
    ledger = read_ledger(DOC)
    if args.list or not args.ids:
        found = compromised(tree, ledger)
        for key in sorted(found, key=lambda item: (tree.nodes[item].project, tree.nodes[item].label)):
            node = tree.nodes[key]
            print(f"{node.project}:{node.id}  {node.label}  {node.title}  — {'; '.join(found[key])}")
        print(f"{len(found)} page(s) to recheck")
        return 0
    if not args.because.strip():
        parser.error("say what the check found: --because \"unaffected: …\" or \"updated: …\"")
    for item in args.ids:
        node = tree.resolve(item, next(iter(tree.projects), ""))
        if node is None:
            print(f"no page {item!r}", file=__import__("sys").stderr)
            return 1
        recheck(tree, ledger, node.key, args.because.strip(), args.run)
        print(f"rechecked {node.label} ({node.key})")
    write_ledger(DOC, ledger)
    left = compromised(tree, ledger)
    print(f"{len(left)} page(s) still to recheck")
    return 0
