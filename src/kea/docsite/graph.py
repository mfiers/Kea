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

3. Pace (kea.yaml ``pace:``). ``design`` (the default of kea init since 1.33): the owner gives a brief, the agent
   designs the whole experiment in one round (questions, hypotheses, planned steps, premises, decisions), the owner
   signs it page by page, the agent executes it in one round (results, figures, caveats, draft conclusions), and the
   owner reviews the results and conclusions; that review holds back only the pages that rely on them
   (:func:`design_rules`: a step runs only when the experiment, its question, the hypotheses it tests, what they
   rely on and the step itself are signed). ``guided`` (before 1.33): one step along the route at a time, each
   reviewed before the next builds on it (:func:`pace_rules`: a hypothesis or step under a question nobody approved;
   a step running or done without approval; a conclusion from results nobody reviewed). ``free``: no gate.
   Approval is ``approved:`` (the owner in chat, or a sign-off applied at a harvest) or ``confirmed:``.
   :func:`next_steps` says, per question, the one next step or what it waits for (kea context).
   Under every pace, :func:`preregistration` checks that a hypothesis marked fixed before its results was committed
   before them (a problem under design, a note otherwise).

Input: a loaded nodes.Tree, doc/_checks.yaml and kea.yaml (pace). Output: problems and notes on the tree; tree.compromised
{page key: reasons}; the ledger (baseline and rechecks).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import yaml

from kea.docsite.nodes import Node, Tree, analysis_of, natural

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


# ------------------------------------------------------------------ pace (kea.yaml pace: design, guided, free)

RUNNING = ("in_progress", "done")
SIGNING_PACES = ("design", "guided")        # pages wait for a sign-off; "free": nothing waits


def signs(tree: Tree) -> bool:
    """Pages wait for a sign-off under this pace (design or guided)."""
    return tree.pace in SIGNING_PACES


def approved(node: Node) -> bool:
    """A sign-off that still holds for what the page says now (signing.py): approved: (Approve on the site, or the
    owner in chat, applied with kea sign) or confirmed:. A page edited after its sign-off is not approved, unless
    every edit since was recorded as minor."""
    from kea.docsite import signing
    return signing.approved(node)


def signed_once(node: Node) -> bool:
    """Signed off at some point, even if the page changed since (the pace rules then note it; it waits again)."""
    from kea.docsite import signing
    return signing.ever_signed(node)


def pace_rules(tree: Tree) -> None:
    """One step along the route at a time, each reviewed before the next builds on it: hypotheses and steps only
    under an approved question, a step runs only when approved, conclusions only from approved results."""
    for node in tree.nodes.values():
        where = _where(node)
        parent = tree.nodes.get(f"{node.project}:{node.parent}") if node.parent else None
        if node.type == "question" and parent is not None and parent.type == "experiment" and not signed_once(parent):
            tree.problems.append(f"{where}: written under an experiment the owner has not approved yet (pace: "
                                 "guided): write the experiment's summary and scope, stop, and let it be reviewed")
        if node.type in ("hypothesis", "step") and parent is not None and parent.type == "question" \
                and not signed_once(parent):
            tree.problems.append(f"{where}: written under question {parent.label}, which the owner has not approved "
                                 "yet (pace: guided): stop after proposing the question and let it be reviewed")
        if node.type == "step" and node.status in RUNNING and not signed_once(node):
            tree.problems.append(f"{where}: step is {node.status} but was not approved (pace: guided): a planned "
                                 "step runs only after the owner approves it (Approve on its page, then a harvest, or in chat: "
                                 "approved: {by, date, how: chat})")
        if node.type == "conclusion" and node.status not in ("deprecated", "superseded"):
            unread = [item.label for item in evidence(tree, node) if item.type in EVIDENCE_TYPES and not signed_once(item)]
            if unread:
                tree.problems.append(f"{where}: drawn from result(s) {', '.join(unread)} that the owner has not "
                                     "reviewed yet (pace: guided): write the results, stop, and conclude after review")


DESIGN_TYPES = ("experiment", "question", "premise", "decision", "hypothesis", "step", "conclusion", "result")


def design_of(tree: Tree, step: Node, whole: bool = True) -> list[Node]:
    """What a step's run rests on (pace: design), every page of it signed before the step runs:
    - the step and every page above it up to the experiment (its question, the hypothesis it sits under);
    - the hypotheses it tests, those its results test (a step without tests:), and every live hypothesis of its
      question (a question's design is signed as a whole);
    - the premises and decisions of the experiment itself, of its question and of any page above the step, and the
      decisions applied in the step (decided_in);
    - what any of these relies on, and for a conclusion relied on, the evidence it rests on (a step that builds on
      another question's conclusion waits for that conclusion's review: the review holds back only what depends
      on it).
    whole=False: only what the step itself names (the pages above it, the hypotheses it and its results test, what
    these rely on), without the rest of its question's hypotheses and the premises and decisions around it.
    Retired, dropped and superseded pages are left out; figures, artefacts and the library sign nothing."""
    from kea.docsite import questions
    found: dict[str, Node] = {}

    def climb(node: Node | None) -> None:
        while node is not None and node.key not in found:
            found[node.key] = node
            node = tree.nodes.get(f"{node.project}:{node.parent}") if node.parent else None
    climb(step)
    for key in step.relations.get("tests", []):
        climb(tree.nodes.get(key))
    for node in tree.nodes.values():
        if node.type == "result" and step.key in node.relations.get("made_by", []):
            for key in node.relations.get("tests", []):
                climb(tree.nodes.get(key))
    if whole:
        for question in [node for node in found.values() if node.type == "question"]:
            for hypothesis in questions.evidence(tree, question)[0]:
                if hypothesis.status not in GONE:
                    climb(hypothesis)
        above = set(found)
        for node in tree.nodes.values():
            if node.project == step.project and node.type in ("premise", "decision") and node.status not in GONE \
                    and (f"{node.project}:{node.parent}" in above or step.key in node.relations.get("decided_in", [])):
                found.setdefault(node.key, node)
    queue = list(found.values())
    while queue:
        node = queue.pop()
        following = [tree.nodes[key] for key in node.relations.get("relies_on", []) if key in tree.nodes]
        if node.type == "conclusion" and node.key != step.key:
            following += evidence(tree, node)
        for item in following:
            if item.key not in found:
                found[item.key] = item
                queue.append(item)
    return [node for node in found.values() if node.type in DESIGN_TYPES and node.status not in GONE]


def _steps_of(tree: Tree, result: Node) -> list[Node]:
    """The steps that made a result: made_by, or the step that made an artefact it comes from."""
    keys = list(result.relations.get("made_by", []))
    for key in result.relations.get("from_artefact", []):
        if key in tree.nodes:
            keys += tree.nodes[key].relations.get("made_by", [])
    return [tree.nodes[key] for key in dict.fromkeys(keys) if key in tree.nodes and tree.nodes[key].type == "step"]


def design_rules(tree: Tree) -> None:
    """pace: design: a step runs only on a signed design (:func:`design_of`), and every result comes from such a
    step. Everything else may be written ahead: the questions, hypotheses and steps of the whole experiment in one
    round, and draft conclusions in the same round as the results they rest on (their sign-off comes after the
    results', top down). A step in progress needs its design signed as it reads now; a step that is done, signed when
    it ran (a later change is caught by the sign-off and change rules, signing.py and propagation.py), against what
    it names itself and against the rest of its design that was committed before its first result (a decision
    written later, say to record a deviation, is not part of what it ran on)."""
    def unsigned_design(step: Node, holds) -> list[str]:
        return [item.label or item.number or item.id for item in design_of(tree, step) if not holds(item)]
    for node in tree.nodes.values():
        if node.type == "step" and node.status == "done":
            core = {item.key for item in design_of(tree, node, whole=False)}
            extra = [item for item in design_of(tree, node) if item.key not in core and not signed_once(item)]
            results = [item for item in tree.nodes.values() if item.type == "result" and item.source is not None
                       and node in _steps_of(tree, item)]
            if extra and results and tree.doc_root is not None:
                times = first_commits(tree.doc_root.parent, [item.source for item in extra + results
                                                             if item.source is not None], tree.doc_root.name)
                ran = [times.get(item.source.resolve()) for item in results]
                ran = min((time for time in ran if time is not None), default=None)
                extra = [item for item in extra if item.source is not None and ran is not None
                         and times.get(item.source.resolve()) is not None and times[item.source.resolve()] <= ran]
            else:
                extra = []
            missing = [item.label or item.number or item.id for item in design_of(tree, node, whole=False)
                       if not signed_once(item)] + [item.label or item.number or item.id for item in extra]
            if missing:
                tree.problems.append(f"{_where(node)}: step is done but its design is not signed: "
                                     f"{', '.join(missing)} (pace: design): a step runs only after the owner has "
                                     "signed the experiment, its question, the hypotheses and premises and decisions "
                                     "of its design, what they rely on and the step itself")
        elif node.type == "step" and node.status == "in_progress":
            missing = unsigned_design(node, approved)
            if missing:
                tree.problems.append(f"{_where(node)}: step is {node.status} but its design is not signed: "
                                     f"{', '.join(missing)} (pace: design): a step runs only after the owner has "
                                     "signed the experiment, its question, the hypotheses and premises and decisions "
                                     "of its design, what they rely on and the step itself")
        elif node.type == "result" and node.status not in GONE:
            steps = _steps_of(tree, node)
            if not steps:
                tree.problems.append(f"{_where(node)}: result made by no step (pace: design): every result comes "
                                     "from a step whose design is signed (made_by:, or from_artefact: an artefact a "
                                     "step made)")
            for step in steps:
                missing = [item.label or item.number or item.id for item in design_of(tree, step, whole=False)
                           if not signed_once(item)]
                if step.status not in RUNNING or missing:
                    why = (f"step {step.label or step.id} is still {step.status}" if step.status not in RUNNING
                           else f"the design of step {step.label or step.id} is not signed: {', '.join(missing)}")
                    tree.problems.append(f"{_where(node)}: a result before its step ran on a signed design (pace: "
                                         f"design): {why}")


def design_ready(tree: Tree, step: Node) -> bool:
    """A planned step whose design holds now (every page of :func:`design_of` approved, unchanged since)."""
    return all(approved(item) for item in design_of(tree, step))


BATCH_TYPES = ("experiment", "question", "premise", "decision", "hypothesis", "step")


def owner_question(tree: Tree, node: Node) -> Node | None:
    """The question a page belongs to: itself for a question, else the nearest question above it (None for the
    experiment and the pages directly under it, which every question shares)."""
    seen: set[str] = set()
    while node is not None and node.key not in seen:
        if node.type == "question":
            return node
        seen.add(node.key)
        node = tree.nodes.get(f"{node.project}:{node.parent}") if node.parent else None
    return None


def question_design_parts(tree: Tree, question: Node) -> tuple[list[Node], list[Node], set[str]]:
    """(to sign, still needed, allowed) for "Sign this design" on a question's page (pace: design, Kea 1.33.2):
    - to sign: the pages of the question's design that still wait for a sign-off and belong to this question or
      to the whole experiment (the experiment page and its premises and decisions), top down; never results or
      conclusions (reviewed one page at a time) and never a page of another question (a parent question, or one
      whose step or decision this design relies on: that question's own button);
    - still needed: the other pages its steps wait for (another question's pages, a questioned premise, a page
      held by a change above it), so the page can say what else must be signed before the steps run;
    - allowed: every page a sign-off of this question's design may sign (kea sign refuses the rest).
    The design: :func:`design_of` of the question and of each of its own steps."""
    from kea.docsite import questions, signing
    if tree.pace != "design" or question.type != "question" or question.status in GONE:
        return [], [], set()
    hypotheses = questions.evidence(tree, question)[0]
    steps = [step for step in question_steps(tree, question, hypotheses)
             if step.status not in GONE and owner_question(tree, step) is question]
    found: dict[str, Node] = {node.key: node for node in design_of(tree, question)}
    for step in steps:
        found.update((node.key, node) for node in design_of(tree, step))
    allowed = {node.key for node in found.values() if node.type in BATCH_TYPES and node.status not in GONE
               and owner_question(tree, node) in (question, None)}
    order = {node.key: index for index, node in enumerate(signing.sign_order(tree))}
    ranked = lambda nodes: sorted(nodes, key=lambda node: (order.get(node.key, len(order)), node.key))
    # the whole experiment's pages first, then the question, then its own pages, each part in the sign order
    to_sign = sorted(ranked(found[key] for key in allowed if getattr(found[key], "waiting", False)),
                     key=lambda node: (owner_question(tree, node) is not None, node is not question))
    signing_now = {node.key for node in to_sign}
    needed = ranked(node for node in found.values() if node.key not in signing_now and node.status not in GONE
                    and node.type in WAITING_TYPES and not approved(node))
    return to_sign, needed, allowed


def question_design(tree: Tree, question: Node) -> list[Node]:
    """The pages one "Sign this design" on a question's page signs (:func:`question_design_parts`)."""
    return question_design_parts(tree, question)[0]


_HISTORY: dict[tuple, dict] = {}


def _git(root: Path, *args: str) -> str | None:
    """git's output, '' when git says nothing or fails, None when it timed out."""
    import subprocess
    try:
        return subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=root, capture_output=True, text=True,
                              timeout=60).stdout
    except subprocess.TimeoutExpired:
        return None
    except (OSError, subprocess.SubprocessError):
        return ""


def _history(root: Path, folder: str) -> dict:
    """Once per HEAD: each commit's place in the history (parents before children) and the commit that added each
    file under the folder. {state: ok | none (no git, no commits) | shallow | timeout, place, added}."""
    head = (_git(root, "rev-parse", "HEAD") or "").strip()
    if not head:
        return {"state": "none"}
    key = (str(root), head, folder)
    if key in _HISTORY:
        return _HISTORY[key]
    if (_git(root, "rev-parse", "--is-shallow-repository") or "").strip() == "true":
        found = {"state": "shallow"}
    else:
        listing = _git(root, "log", "--reverse", "--topo-order", "--format=%H")
        adds = _git(root, "log", "--topo-order", "--diff-filter=A", "--relative", "--format=@%H", "--name-only", "--",
                    folder)
        if listing is None or adds is None:
            found = {"state": "timeout"}
        else:
            place = {commit: index for index, commit in enumerate(listing.split())}
            added: dict[Path, int] = {}
            commit = ""
            for line in adds.splitlines():
                if line.startswith("@"):
                    commit = line[1:]
                elif line.strip() and commit in place:
                    added[(root / line.strip()).resolve()] = place[commit]   # newest first: the last seen is the first
            found = {"state": "ok", "place": place, "added": added}
    _HISTORY[key] = found
    return found


def first_commits(root: Path, paths: list[Path], folder: str = "doc", follow: bool = False) -> dict[Path, int | None]:
    """The commit that added each file, as its place in the history (0 = the first commit, so a smaller number is
    earlier; the same number is the same commit); None when the file is not committed. With follow (or for a file
    the folder's log does not show as added), git log --follow through renames and moves. {} when the history is
    not there to read (no git, shallow clone, timeout: see :func:`_history`)."""
    history = _history(root, folder)
    if history["state"] != "ok":
        return {}
    place, added = history["place"], history["added"]
    found: dict[Path, int | None] = {}
    for path in (path.resolve() for path in paths):
        if path in added and not follow:
            found[path] = added[path]
            continue
        output = _git(root, "log", "--follow", "--diff-filter=AR", "--format=%H", "--", str(path)) or ""
        commits = [place[item] for item in output.split() if item in place]
        found[path] = min(commits) if commits else None
    return found


def preregistration(tree: Tree, doc: Path) -> None:
    """A hypothesis marked fixed_before_results: true must be committed before any result that tests it (a result
    made by a step that tests it, or one that tests it directly). The commit is the record: the same commit or a
    later one is not before. A problem under pace: design (the gate it rests on), a note under the other paces.
    A move or rename of the files is followed before anything is reported; a shallow clone or a git that times out
    gives a note that the check did not run."""
    tested: dict[str, list[Node]] = {}
    for node in tree.nodes.values():
        if node.type != "result" or node.status == "deprecated" or node.source is None:
            continue
        hypotheses = set(node.relations.get("tests", []))
        for step in _steps_of(tree, node):
            hypotheses.update(step.relations.get("tests", []))
        for key in hypotheses:
            if key in tree.nodes and tree.nodes[key].type == "hypothesis":
                tested.setdefault(key, []).append(node)
    fixed = [tree.nodes[key] for key in tested if tree.nodes[key].header.get("fixed_before_results") is True
             and tree.nodes[key].source is not None]
    if not fixed:
        return
    root = doc.parent
    history = _history(root, doc.name)
    if history["state"] in ("shallow", "timeout"):
        tree.notes.append(f"{doc.name}: the commit order of hypotheses fixed before their results was not checked: "
                          + ("this is a shallow clone (fetch the full history)" if history["state"] == "shallow"
                             else "git took too long"))
        return

    def early(hypothesis: Node, times: dict) -> list[str]:
        fixed_at = times.get(hypothesis.source.resolve())
        return [result.label or result.id for result in tested[hypothesis.key]
                if times.get(result.source.resolve()) is not None
                and (fixed_at is None or times[result.source.resolve()] <= fixed_at)]
    times = first_commits(root, [node.source for node in fixed] +
                          [result.source for node in fixed for result in tested[node.key]], doc.name)
    if not times:
        return
    report = tree.problems if tree.pace == "design" else tree.notes
    for hypothesis in fixed:
        if not early(hypothesis, times):
            continue
        followed = first_commits(root, [hypothesis.source] + [result.source for result in tested[hypothesis.key]],
                                 doc.name, follow=True)            # a move out of doc/ and back is not a new page
        names = early(hypothesis, followed)
        if names:
            fixed_at = followed.get(hypothesis.source.resolve())
            when = "is not committed yet" if fixed_at is None else "was committed no earlier than"
            report.append(f"{_where(hypothesis)}: fixed_before_results: true, but it {when} result(s) "
                          f"{', '.join(names)} that test it: commit a hypothesis before its test runs; if it was not "
                          "fixed before, set fixed_before_results: false and label what rests on it exploratory")


WAITING_TYPES = ("experiment", "question", "premise", "decision", "hypothesis", "step", "result", "conclusion")
GONE = ("deprecated", "superseded", "dropped")


def waiting(node: Node) -> bool:
    """Under pace: design or guided, a page waiting for a sign-off before the next step builds on it: a question, a premise,
    a decision, a planned hypothesis or step, a result or a conclusion without a signature that holds; and any page
    of these types edited (beyond minor edits) after its sign-off. One Approve signs one page; the site walks
    them top down (signing.sign_order)."""
    from kea.docsite import signing
    if node.type not in WAITING_TYPES or approved(node) or node.status in GONE:
        return False
    if node.held_by:                                         # a signed page above it waits first (propagation.py)
        return False
    if node.upstream_changed:                                # what it was built on changed since its sign-off
        return True
    if signing.stale(node):                                  # signed, then changed: the signature no longer holds
        return True
    if node.type in ("hypothesis", "step"):
        return node.status == "planned"
    if node.type == "question":
        return node.status not in ("dropped", "answered")
    if node.type == "experiment":
        return node.status == "open"
    if node.type == "premise":
        return node.status != "questioned"                   # a questioned premise is being checked
    return True                                              # a result, a decision, a conclusion


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


def signatures(node: Node) -> list[dict]:
    """Who signed the page off: approved: as one mapping (before 1.28) or a list of them ({by, orcid, date,
    version, how, thread, content, minor}); a bare string counts as a name."""
    from kea.docsite import signing
    return signing.signatures(node)


def question_steps(tree: Tree, question: Node, hypotheses: list[Node]) -> list[Node]:
    keys = {hypothesis.key for hypothesis in hypotheses}
    return sorted((node for node in tree.nodes.values() if node.type == "step" and node.project == question.project
                   and (node.parent == question.id or keys & set(node.relations.get("tests", [])))),
                  key=lambda node: node.number or node.id)


STAGES = (("question", "Approved"), ("plan", "Plan"), ("run", "Run"), ("results", "Results"),
          ("conclusions", "Conclusions"))


def question_route(tree: Tree, question: Node) -> dict:
    """Where a question stands on the route, stage by stage (pace: guided): each stage is done, you (pages wait
    for a sign-off), agent (the agent's turn: it goes into the plan at the next harvest and runs at Implement), later, or running.
    {question, stages: [{key, label, state, pages, note}], hypotheses, steps, results, conclusions}."""
    from kea.docsite import questions
    hypotheses, results, conclusions = questions.evidence(tree, question)
    steps = question_steps(tree, question, hypotheses)
    guided = signs(tree)                                                   # design or guided: pages wait
    design = tree.pace == "design"          # the design is written and signed in one round; the run waits for it
    approved = globals()["approved"] if guided else (lambda node: True)    # pace: free: nothing waits for a sign-off
    live_results = [node for node in results if node.status != "deprecated"]
    planned = [node for node in hypotheses + steps if node.status == "planned"]
    stages = []

    def add(key: str, state: str, pages: list[Node] = (), note: str = "") -> None:
        stages.append({"key": key, "label": dict(STAGES)[key], "state": state, "pages": list(pages), "note": note})
    closed = question.status in ("dropped", "answered")
    if not guided:
        add("question", "free", [], "pace: free: no sign-off needed")
    else:
        add("question", "done" if approved(question) or closed else "you", [] if approved(question) else [question],
            "" if approved(question) else "sign off on the question")
    if not approved(question) and not design:
        state = "later"
        add("plan", state); add("run", state); add("results", state); add("conclusions", state)
        return {"question": question, "stages": stages, "hypotheses": hypotheses, "steps": steps,
                "results": live_results, "conclusions": conclusions}
    unsigned_plan = [node for node in planned if not approved(node)]
    if not hypotheses and not steps:
        add("plan", "agent", [question], "the agent writes hypotheses and planned steps")
    elif unsigned_plan:
        add("plan", "you", unsigned_plan, "sign off on the design: the planned hypotheses and steps" if design else
            "sign off on the planned hypotheses and steps")
    else:
        add("plan", "done", [])
    ready = [node for node in steps if node.status == "planned" and approved(node)
             and (not design or design_ready(tree, node))]
    running = [node for node in steps if node.status == "in_progress"]
    unsigned_design = design and (not approved(question) or stages[-1]["state"] != "done")
    blocked = [node for node in steps if design and node.status == "planned" and node not in ready]
    if (stages[-1]["state"] != "done" or unsigned_design) and not running and not [n for n in steps if n.status == "done"]:
        add("run", "later")
    elif running:
        add("run", "running", running, "steps in progress")
    elif ready:
        add("run", "agent", ready, "approved steps wait to be run")
    elif blocked and not unsigned_design:          # design: signed, but resting on a page still under review
        waiting_on = {item.key: item for step in blocked for item in design_of(tree, step) if not approved(item)}
        add("run", "you", list(waiting_on.values()), "the steps wait for the sign-off of what they rely on")
    elif steps:
        add("run", "done", [])
    else:
        add("run", "later")
    unread = [node for node in live_results if not approved(node)]
    if unread:
        add("results", "you", unread, "review the results")
    elif live_results:
        add("results", "done", [])
    else:
        add("results", "later")
    unsigned = [node for node in conclusions if node.status not in GONE and not approved(node)]
    if live_results and (design or not unread) and not conclusions:      # design: drafted with the results
        add("conclusions", "agent", live_results[-1:], "the agent draws conclusions")
    elif unsigned:
        add("conclusions", "you", unsigned, "sign off on the conclusions (and the answer)")
    elif conclusions:
        add("conclusions", "done", [])
    else:
        add("conclusions", "later")
    if question.status in ("answered", "dropped"):           # a closed question: nothing more is asked of anyone
        for stage in stages:
            if stage["key"] == "conclusions" and stage["state"] == "you":
                continue                                     # the conclusions behind the answer still need a sign-off
            if stage["state"] in ("you", "agent", "running", "later"):
                stage.update(state="closed", pages=[], note=f"the question is {question.status}")
    return {"question": question, "stages": stages, "hypotheses": hypotheses, "steps": steps,
            "results": live_results, "conclusions": conclusions}


def go_action(tree: Tree, node: Node) -> str:
    """The agent's next step after this page, when that step is the agent's turn ('' when
    there is none): an experiment without questions → propose questions; an open question without hypotheses or
    steps → write the plan; a planned hypothesis no step tests → plan its steps; a planned step → run the step; the
    last unreviewed result of a question without conclusions → draw conclusions. Signed off already or not: the
    button signs the page off (again, for another reader) and asks for the step."""
    from kea.docsite import questions
    members = [other for other in tree.nodes.values() if other.project == node.project]
    if node.type == "experiment" and node.id == "home":
        return "" if any(other.type == "question" for other in members) else "propose questions"
    if node.type == "question":
        if node.status in ("answered", "dropped"):
            return ""
        hypotheses, _, _ = questions.evidence(tree, node)
        return "" if hypotheses or question_steps(tree, node, hypotheses) else "write the plan"
    if node.type == "step":
        if node.status != "planned" or (tree.pace == "design" and not design_ready(tree, node)):
            return ""
        return "run the step"
    if node.type == "hypothesis":
        if node.status != "planned":
            return ""
        tested = any(node.key in other.relations.get("tests", []) for other in members if other.type == "step")
        return "" if tested else "plan its steps"
    if node.type == "result" and node.status != "deprecated":
        for question in questions.questions(tree, node.project):
            _, results, conclusions = questions.evidence(tree, question)
            if node in results:
                if question.status in ("answered", "dropped") or conclusions:
                    return ""
                live = [item for item in results if item.status != "deprecated"]
                if tree.pace == "guided" and any(not approved(item) for item in live if item is not node):
                    return ""                                     # the other results still wait for their sign-off
                newest = max(live, key=lambda item: (natural(item.number or item.id)))
                return "draw conclusions" if newest is node else ""
    return ""


def stage_action(tree: Tree, pages: list[Node]) -> str:
    """The agent's next step once every page in a stage is signed (a plan item at the next harvest) ('' when nothing): the
    plan with two or more planned steps → run the plan (every planned step of the question, then the results); a
    stage of results of a question without conclusions → draw conclusions; else the first page's own go_action in
    route order (propose questions, write the plan, plan its steps, run the step)."""
    from kea.docsite import questions
    if not pages:
        return ""
    planned = [node for node in pages if node.type == "step" and node.status == "planned"
               and (tree.pace != "design" or design_ready(tree, node))]
    if len(planned) > 1:
        return "run the plan"
    results = [node for node in pages if node.type == "result" and node.status != "deprecated"]
    if results:
        for question in questions.questions(tree, results[0].project):
            _, found, conclusions = questions.evidence(tree, question)
            if results[0] in found:
                return "" if question.status in ("answered", "dropped") or conclusions else "draw conclusions"
    for node in pages:
        action = go_action(tree, node)
        if action:
            return action
    return ""


BRIEF_STEP = ("Next (design round): from the owner's brief (said in chat, or a comment tagged brief from the "
              "Start here box on the experiment page, or a Propose ▸ an experiment comment), "
              "put the brief word for word under ## Brief on the experiment page (who, date), then write the design of "
              "the whole experiment: questions, premises, decisions, hypotheses (prediction, criterion, "
              "fixed_before_results: true) and planned steps; read the data's description and structure, never its "
              "outcomes; commit; then stop for the owner's sign-off. Without a brief, ask the owner for one.")


def design_next_steps(tree: Tree, project: str) -> list[str]:
    """pace: design: per question, what the next round does or what waits for the owner (kea context)."""
    from kea.docsite import questions
    lines = []
    standing = [node for node in tree.nodes.values() if node.project == project and getattr(node, "waiting", False)
                and node.type in ("experiment", "premise", "decision")]
    if standing:
        names = ", ".join(f"{node.number or node.label or node.id} ({node.type})" for node in standing)
        lines.append(f"Waiting for the owner to sign the design: {names} (Sign this design on a question's page, "
                     "Approve page by page, or in chat).")
    found = questions.questions(tree, project)
    if not found:
        return lines + [BRIEF_STEP]

    def names(nodes: list[Node]) -> str:
        return ", ".join(node.number or node.label or node.id for node in nodes)
    for question in found:
        label = question.number or question.label
        if question.status in ("answered", "dropped"):
            unsigned = [node for node in questions.evidence(tree, question)[2]
                        if node.status not in GONE and not approved(node)]
            lines.append(f"{label}: {question.status}" + (f"; waiting for the owner to sign off on {names(unsigned)}."
                                                          if unsigned else "."))
            continue
        hypotheses, results, conclusions = questions.evidence(tree, question)
        steps = question_steps(tree, question, hypotheses)
        planned = [node for node in hypotheses + steps if node.status == "planned"]
        unsigned_design = ([question] if not approved(question) else []) + [node for node in planned if not approved(node)]
        ready = [step for step in steps if step.status == "planned" and design_ready(tree, step)]
        blocked = [step for step in steps if step.status == "planned" and step not in ready]
        unread = [node for node in results if node.status != "deprecated" and not approved(node)]
        unsigned = [node for node in conclusions if node.status not in GONE and not approved(node)]
        if not hypotheses and not steps:
            lines.append(f"{label}: next (design round), write its hypotheses (prediction, criterion, "
                         "fixed_before_results: true) and planned steps with the rest of the design; commit; then stop "
                         "for the owner's sign-off. Do not look at outcome data or run anything.")
        elif unsigned_design:
            lines.append(f"{label}: waiting for the owner to sign the design: {names(unsigned_design)} (Sign this "
                         "design on the question's page, Approve page by page, or in chat). A step runs only once its "
                         "whole design is signed.")
        elif ready:
            lines.append(f"{label}: next (execution round, at Implement), run step(s) {names(ready)} reproducibly and "
                         "write the results, figures and caveats, then draft the conclusions, the hypotheses' outcomes "
                         "and the answer; then stop for review. A step that fails or has to deviate from its signed "
                         "plan stops this question only: say why, and write the change for a new sign-off.")
        elif blocked:
            waiting_on = {node.key: node for step in blocked for node in design_of(tree, step) if not approved(node)}
            lines.append(f"{label}: step(s) {names(blocked)} wait for the sign-off of what they rely on: "
                         f"{names(list(waiting_on.values()))}.")
        elif results and not conclusions:
            lines.append(f"{label}: next, draft the conclusions from the results, the hypotheses' outcomes and the "
                         "answer; then stop for review.")
        elif unread or unsigned:
            lines.append(f"{label}: waiting for the owner to review {names(unread + unsigned)} (this holds back only "
                         "the pages that rely on them).")
        else:
            lines.append(f"{label}: nothing waiting on the route; follow the comments and caveats.")
    return lines


def next_steps(tree: Tree, project: str) -> list[str]:
    """Where each question stands on the route, and the one next step (for kea context; pace: design or guided)."""
    from kea.docsite import questions
    if tree.pace == "design":
        return design_next_steps(tree, project)
    lines = []
    # the experiment, premises and decisions wait for a sign-off too (pace: guided), outside any question's route
    standing = [node for node in tree.nodes.values() if node.project == project and getattr(node, "waiting", False)
                and node.type in ("experiment", "premise", "decision")]
    if standing:
        names = ", ".join(f"{node.number or node.label or node.id} ({node.type})" for node in standing)
        lines.append(f"Waiting for the owner to sign off on {names} (Approve on the site, or in chat).")
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
            lines.append(f"{label}: waiting for the owner to sign off on the question (Approve on the site, or in chat).")
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
        elif [item for item in conclusions if item.status not in GONE and not approved(item)]:
            waiting = [item.number for item in conclusions if item.status not in GONE and not approved(item)]
            lines.append(f"{label}: waiting for the owner to sign off on the conclusion(s) {', '.join(waiting)} "
                         "and the answer.")
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


def upstream(tree: Tree, parents: bool = False) -> dict[str, set[str]]:
    """Page key -> keys of the pages it depends on. With ``parents``, also the page it sits under (a step on its
    question; not terms, references, resources): a change of the parent itself flags its children, but nothing is
    passed on "via" a parent (a question also depends on its results, for its answer)."""
    depends: dict[str, set[str]] = {key: set() for key in tree.nodes}
    for node in tree.nodes.values():
        parent = f"{node.project}:{node.parent}" if node.parent and node.id != "home" else ""
        if parents and parent in tree.nodes and node.type not in ("term", "reference", "resource"):
            depends[node.key].add(parent)
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
    for key, sources in upstream(tree, parents=True).items():
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
    depends = upstream(tree, parents=True)
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
    sources = upstream(tree, parents=True).get(key, set())
    changes = (ledger.get(key) or {}).get("changes")
    ledger[key] = {**({"changes": changes} if changes else {}),
                   "upstream": {source: fingerprint(tree.nodes[source]) for source in sorted(sources)},
                   "checked": dt.date.today().isoformat(), "because": because, **({"run": run} if run else {})}


def apply(tree: Tree, doc: Path, write_baseline: bool) -> None:
    """Structure checks, the baseline (when asked) and the compromised pages, all on the tree."""
    structure(tree)
    projects(tree, doc)
    from kea.config import load_settings
    tree.pace = str(load_settings(doc.parent).get("pace") or "free")
    from kea.docsite import propagation
    propagation.bind(tree)                  # sign-offs count only with what they were built on (Kea 1.32)
    tree.doc_root = doc
    if tree.pace == "guided":
        pace_rules(tree)
    elif tree.pace == "design":
        design_rules(tree)
    if signs(tree):
        for node in tree.nodes.values():
            node.waiting = waiting(node)
    preregistration(tree, doc)
    from kea.docsite import signing
    sign_problems, sign_notes = signing.problems_and_notes(tree)
    tree.problems.extend(sign_problems)
    tree.notes.extend(sign_notes)
    ledger = read_ledger(doc)
    tree.__dict__["ledger"] = ledger                    # change records, for the pages built on a changed page
    propagation.problems(tree, ledger)
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
    """kea drop <id>: list the page and every page that rests only on it (what a Drop removes); writes nothing.
    kea drop <id> --apply --because "…" [--replaced-by <id>] [--run R]: retire them (propagation.retire)."""
    from kea.docsite.nodes import DOC, load_tree
    if "--apply" in argv:
        import argparse
        from kea.docsite import propagation
        parser = argparse.ArgumentParser(prog="kea drop")
        parser.add_argument("page")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--because", required=True)
        parser.add_argument("--replaced-by", default="")
        parser.add_argument("--run", default="")
        args = parser.parse_args(argv)
        tree = load_tree(DOC)
        node = tree.resolve(args.page, next(iter(tree.projects), ""))
        if node is None:
            print(f"no page {args.page!r}")
            return 1
        if args.replaced_by and tree.resolve(args.replaced_by, node.project) is None:
            print(f"no page {args.replaced_by!r} to replace it (write the new page first, with supersedes: [{node.id}])")
            return 1
        gone, keep = propagation.retire(tree, node.key, args.because, args.replaced_by, args.run)
        print(f"retired {len(gone)} page(s): {', '.join(tree.nodes[key].label for key in gone)}")
        if keep:
            print(f"kept and moved under {keep[0][1]}: {', '.join(tree.nodes[key].label for key, _ in keep)}")
        print("then: make site (links from live pages to retired ones are problems; fix them), and commit")
        return 0
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
