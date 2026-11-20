"""What an upstream change does to the sign-offs below it (Kea 1.32), and retiring a branch.

A sign-off holds for the wording signed (signing.py) *and* for what the page was built on when it was signed.

1. Built on (:func:`built_on`): a question, hypothesis, step, decision, premise or caveat is built on the page it
   sits under; every page on the pages it relies on (supported_by, opposed_by, relies_on, made_by, from_artefact,
   derived_from, decided_in, addressed_by); a step on the hypothesis it tests; a conclusion on the results that
   support or oppose it. A result is built on its step, not on the question it sits under or answers. Not on
   terms, references or resources (background wording), and not on what a page goes on to support.

2. Bound to the upstream (:func:`recorded`): `kea sign` writes ``upstream: {page: content hash}`` into each new
   signature; for a signature from before 1.32 the hashes are read from git at the commit that added it.

3. The chain (:func:`bind`), cleared top down. For a page whose own signature holds:
   - *held*: a page it is built on was signed and no longer is (it changed, or something above it did). The page
     does not count as signed and is not offered for signing; it counts again by itself once that page is signed
     again unchanged.
   - *upstream changed*: a page it is built on says something else than when this page was signed (beyond minor
     edits). The page waits for its own sign-off, and shows what changed upstream (a word diff) and why.
   So a substantive edit of a question makes its hypotheses and steps wait for a sign-off each, and everything
   below them is held until those are signed: one click per page whose direct upstream changed, never a cascade
   of pages that did not change.

4. The class of a change (:func:`record_change`, `kea change`): a signed page edited beyond a minor edit needs a
   recorded reason (``doc/_checks.yaml``, under ``changes:``) before the build passes; the downstream pages show
   it. An invalidating change is not an edit: it makes a new page (``supersedes:`` the old one) and retires the
   old branch (`kea drop <id> --apply`).

5. Retired pages (:func:`retire`): ``retired: {date, because, replaced_by}`` in their front matter. They leave the
   map, Progress, the sign order and every count (nodes.load_tree keeps them in ``tree.retired``); their page
   stays, marked retired, and is listed under Retired. Premises, decisions, resources, references and terms
   under a retired page are kept and moved to the replacing page (or the retired page's parent); an artefact
   that a live page still uses is kept too.

Input: the tree, git history of doc/. Output: node.held_by, node.upstream_changed (via :func:`bind`), the build
problems and notes, and the commands `kea change`, `kea impact` and `kea drop --apply`.
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
from pathlib import Path

BUILT_ON_OWN = ("supported_by", "opposed_by", "relies_on", "made_by", "from_artefact", "derived_from", "decided_in",
                "addressed_by")
# relations written on the *other* page that make this page built on it: (relation, this page is the target?)
BUILT_ON_FROM_TARGET = ("supports", "opposes")          # a result supports a conclusion: the conclusion is built on it
BUILT_ON_FROM_SOURCE = ("tests",)                       # a step tests a hypothesis: the step is built on it
# pages built on the page they sit under: written against its wording (a hypothesis or step against its question).
# A result is built on the step that made it, a conclusion on its results, not on the question they sit under.
BUILT_ON_PARENT = ("question", "hypothesis", "step", "decision", "premise", "caveat")
BACKGROUND_WORDING = ("term", "reference", "resource")
KEEP_ON_RETIRE = ("premise", "decision", "resource", "reference", "term")
_SIGNED_AT: dict[tuple[str, str], str] = {}


def built_on(tree) -> dict[str, set[str]]:
    """Page key -> keys of the pages it is built on (see the module docstring)."""
    found: dict[str, set[str]] = {key: set() for key in tree.nodes}
    for node in tree.nodes.values():
        if node.parent and node.id != "home" and node.type in BUILT_ON_PARENT:
            parent = f"{node.project}:{node.parent}"
            if parent in tree.nodes:
                found[node.key].add(parent)
        for relation, targets in node.relations.items():
            for target in targets:
                if target not in tree.nodes or target == node.key:
                    continue
                if relation in BUILT_ON_OWN or relation in BUILT_ON_FROM_SOURCE:
                    found[node.key].add(target)
                elif relation in BUILT_ON_FROM_TARGET:
                    found[target].add(node.key)
    for key, ups in found.items():
        found[key] = {up for up in ups if tree.nodes[up].type not in BACKGROUND_WORDING}
    return found


def _relative(path: Path) -> str:
    """The path in the git repository, '' for a page outside it (then there is no history to read)."""
    from kea.docsite.nodes import PROJECT_ROOT
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return ""


def _signed_at(node, content_hash: str) -> str:
    """The commit that first wrote this signature's content hash into the page (when it was signed), '' if none."""
    from kea.docsite.nodes import PROJECT_ROOT
    key = (str(node.source), content_hash)
    if not _relative(node.source):
        return ""
    if key not in _SIGNED_AT:
        result = subprocess.run(["git", "-C", str(PROJECT_ROOT), "log", "--format=%H", "--reverse", f"-S{content_hash}",
                                 "--", _relative(node.source)], capture_output=True, text=True)
        commits = result.stdout.split() if result.returncode == 0 else []
        _SIGNED_AT[key] = commits[0] if commits else ""
    return _SIGNED_AT[key]


def content_at(commit: str, node) -> str | None:
    """The content hash of the page as it was at ``commit`` (None where it did not exist then)."""
    from kea.docsite import comments, signing
    from kea.docsite.nodes import split_front_matter
    relative = _relative(node.source)
    text = comments.blob(commit, relative) if relative else None
    if text is None:
        return None
    try:
        return signing.content_of(*split_front_matter(text, node.source))
    except ValueError:
        return None


def recorded(tree, node, signature: dict, ups: set[str]) -> dict[str, str]:
    """What the page was built on when this signature was made: {page key: content hash}. Written by kea sign since
    1.32; read from git for older signatures (none for a signature without content:, from before 1.29)."""
    stored = signature.get("upstream")
    if isinstance(stored, dict):
        return {str(key): str(value) for key, value in stored.items()}
    if not signature.get("content"):
        return {}
    commit = _signed_at(node, str(signature["content"]))
    if not commit:
        return {}
    found = {}
    for up in ups:
        before = content_at(commit, tree.nodes[up])
        if before is not None:
            found[up] = before
    return found


def upstream_hashes(tree, node) -> dict[str, str]:
    """{page key: content hash} of what the page is built on now: what kea sign writes into a new signature."""
    from kea.docsite import signing
    return {up: signing.content(tree.nodes[up]) for up in sorted(built_on(tree).get(node.key, ()))}


def _same(tree, up_key: str, before: str) -> bool:
    """The upstream page still says what it said (or only minor edits recorded on a signature that holds)."""
    from kea.docsite import signing
    upstream = tree.nodes[up_key]
    if signing.content(upstream) == before:
        return True
    return any(signing.holds(item, upstream) and before in signing.valid_contents(item)
               for item in signing.signatures(upstream))


def bind(tree) -> None:
    """Set node.held_by and node.upstream_changed for every page whose own signature holds (module docstring, 3)."""
    from kea.docsite import signing
    ups = built_on(tree)
    memo: dict[str, bool] = {}

    def own(node) -> bool:
        return signing.own_approved(node)

    def counts(key: str, trail: frozenset = frozenset()) -> bool:
        """The page's sign-off counts: its own holds, nothing it was built on changed, and every signed page it is
        built on counts too (a loop of pages counts as holding where it closes)."""
        if key in memo:
            return memo[key]
        if key in trail:
            return True
        node = tree.nodes[key]
        result = own(node) and not node.upstream_changed and not held(key, trail | {key})
        memo[key] = result
        return result

    def held(key: str, trail: frozenset) -> list[str]:
        return [up for up in sorted(ups.get(key, ())) if signing.ever_signed(tree.nodes[up])
                and not counts(up, trail)]

    for node in tree.nodes.values():
        node.upstream_changed, node.held_by = [], []
        if not signing.signatures(node) or not own(node):
            continue
        holding = [item for item in signing.signatures(node) if signing.holds(item, node)]
        changed_per_signature = []
        for item in holding:
            before = recorded(tree, node, item, ups.get(node.key, set()))
            changed_per_signature.append([(up, old) for up, old in sorted(before.items())
                                          if up in tree.nodes and up in ups.get(node.key, set())
                                          and not _same(tree, up, old)])
        if changed_per_signature and all(changed_per_signature):   # no signature survives the upstream change
            node.upstream_changed = changed_per_signature[-1]
    for node in tree.nodes.values():
        if node.upstream_changed is not None and own(node):
            node.held_by = held(node.key, frozenset({node.key}))
            node.chain_ok = not node.upstream_changed and not node.held_by
        else:
            node.chain_ok = True


def roots(tree, node) -> list[tuple[str, list[str]]]:
    """For a held page: the topmost pages above it that need a new look (built on a page that changed, or their own
    wording changed since signed) and wait on nothing themselves, each with the path from this page up to it."""
    found: dict[str, list[str]] = {}
    queue, seen = [[node.key]], {node.key}
    while queue:
        path = queue.pop(0)
        current = tree.nodes[path[-1]]
        for up in getattr(current, "held_by", None) or []:
            if up in seen or up not in tree.nodes:
                continue
            seen.add(up)
            above = tree.nodes[up]
            if not above.held_by:                    # waits on nothing above it: the page to look at
                found.setdefault(up, path + [up])
            else:
                queue.append(path + [up])
    return list(found.items())


def root_reason(tree, key: str) -> str:
    """Why a root page needs a new look, in a few words."""
    from kea.docsite import signing
    node = tree.nodes[key]
    if node.upstream_changed:
        return ("built on " + ", ".join(tree.nodes[up].label for up, _ in node.upstream_changed)
                + ", changed since it was signed")
    if signing.ever_signed(node) and not signing.own_approved(node):
        return "its wording changed since it was signed"
    return "not signed"


def recheck_for(tree, node, up_key: str) -> dict:
    """The agent's recheck of this page against the current wording of ``up_key`` (doc/_checks.yaml), or {}."""
    from kea.docsite import graph
    entry = (tree.__dict__.get("ledger") or {}).get(node.key) or {}
    checked = (entry.get("upstream") or {}).get(up_key)
    if entry.get("because") and checked and up_key in tree.nodes and checked == graph.fingerprint(tree.nodes[up_key]):
        return entry
    return {}


# ------------------------------------------------------------------ change records (doc/_checks.yaml, changes:)

def changes_of(ledger: dict, key: str) -> list[dict]:
    return [item for item in (ledger.get(key) or {}).get("changes") or [] if isinstance(item, dict)]


def change_for(ledger: dict, node) -> dict | None:
    """The recorded change that produced the page's current wording."""
    from kea.docsite import signing
    now = signing.content(node)
    for item in reversed(changes_of(ledger, node.key)):
        if str(item.get("content")) == now:
            return item
    return None


def record_change(ledger: dict, node, because: str, run: str = "", cycle: str = "") -> dict:
    from kea.docsite import signing
    entry = {"content": signing.content(node), "class": "substantive", "because": because,
             "date": dt.date.today().isoformat(), **({"run": run} if run else {}), **({"cycle": cycle} if cycle else {})}
    ledger.setdefault(node.key, {}).setdefault("changes", []).append(entry)
    return entry


def problems(tree, ledger: dict) -> None:
    """Build problems: a signed page changed without a recorded change; a hypothesis whose prediction or criterion
    changed after a result tested it (that is a new, post hoc hypothesis, not an edit)."""
    from kea.docsite import signing
    for node in tree.nodes.values():
        stale = signing.stale(node)
        if not stale:
            continue
        where = node.source.name
        tested = any(node.key in other.relations.get("tests", []) and other.status in ("in_progress", "done")
                     for other in tree.nodes.values())
        if node.type == "hypothesis" and tested:
            old = signing.find_wording(node, [str(item.get("content")) for item in stale if item.get("content")])
            if old is not None:
                moved = [name for name in ("prediction", "criterion")
                         if str(old[0].get(name) or "").strip() != str(node.header.get(name) or "").strip()]
                if moved:
                    tree.problems.append(f"{node.label} ({where}): {' and '.join(moved)} changed after its test ran; "
                                         "that is a new hypothesis: write it as a new page (fixed_before_results: false, "
                                         f"supersedes: [{node.id}]) and retire this one (kea drop {node.id} --apply)")
        if change_for(ledger, node) is None:
            tree.problems.append(f"{node.label} ({where}): changed after its sign-off, beyond a minor edit, without a "
                                 f"recorded change: kea change {node.id} --because \"what changed and why\" (or kea sign "
                                 f"{node.id} --minor if it is minor; an invalidating change is a new page and kea drop --apply)")


# ------------------------------------------------------------------ impact and retiring

def downstream(tree, key: str) -> tuple[list[str], list[str]]:
    """(pages that would wait for their own sign-off, pages that would be held) if ``key`` changed substantively:
    signed pages directly built on it, and signed pages further down."""
    from kea.docsite import signing
    ups = built_on(tree)
    below: dict[str, set[str]] = {}
    for page, sources in ups.items():
        for source in sources:
            below.setdefault(source, set()).add(page)
    direct = sorted(page for page in below.get(key, ()) if signing.ever_signed(tree.nodes[page]))
    deeper, queue, seen = [], list(below.get(key, ())), {key}
    while queue:
        page = queue.pop()
        if page in seen:
            continue
        seen.add(page)
        if page not in direct and signing.ever_signed(tree.nodes[page]):
            deeper.append(page)
        queue.extend(below.get(page, ()))
    return direct, sorted(deeper)


def retire_plan(tree, key: str, replaced_by: str = "") -> tuple[list[str], list[tuple[str, str]]]:
    """(pages to retire, [(page kept, new parent id)]) for `kea drop <id> --apply` (graph.drop_set, minus what is
    reusable: premises, decisions, resources, references, terms, and artefacts a live page still uses)."""
    from kea.docsite import graph
    node = tree.nodes[key]
    gone = [page for page in graph.drop_set(tree, key) if tree.nodes[page].type not in KEEP_ON_RETIRE]
    used = set()
    for other in tree.nodes.values():
        if other.key in gone:
            continue
        for relation, targets in other.relations.items():
            used.update(targets)
    gone = [page for page in gone if not (tree.nodes[page].type == "artefact" and page in used)]
    home_id = replaced_by or node.parent or "home"
    keep = [(other.key, home_id) for other in tree.nodes.values()
            if other.key not in gone and other.parent and f"{other.project}:{other.parent}" in gone]
    return gone, keep


def _set_header_line(path: Path, name: str, value: str) -> None:
    """Set one top-level front-matter field to a flow value (replacing it, or added before the closing ---)."""
    text = path.read_text(encoding="utf-8")
    head_end = text.index("\n---", 3)
    head, rest = text[:head_end], text[head_end:]
    pattern = re.compile(rf"^{re.escape(name)}:.*(?:\n[ \t]+.*)*", re.M)
    line = f"{name}: {value}"
    head = pattern.sub(line, head, count=1) if pattern.search(head) else head + "\n" + line
    path.write_text(head + rest, encoding="utf-8")


def retire(tree, key: str, because: str, replaced_by: str = "", run: str = "") -> tuple[list[str], list[tuple[str, str]]]:
    import json
    gone, keep = retire_plan(tree, key, replaced_by)
    stamp = {"date": dt.date.today().isoformat(), "because": because, "root": tree.nodes[key].id,
             **({"replaced_by": replaced_by} if replaced_by else {}), **({"run": run} if run else {})}
    flow = "{" + ", ".join(f"{name}: {json.dumps(value, ensure_ascii=False)}" for name, value in stamp.items()) + "}"
    for page in gone:
        _set_header_line(tree.nodes[page].source, "retired", flow)
    for page, parent in keep:
        _set_header_line(tree.nodes[page].source, "parent", parent)
    return gone, keep


# ------------------------------------------------------------------ commands

def _tree_and_ledger():
    from kea.docsite import graph, nodes
    tree = nodes.load_tree(nodes.DOC)
    return tree, graph.read_ledger(nodes.DOC)


def _find(tree, name: str):
    node = tree.resolve(name, next(iter(tree.projects), ""))
    if node is None:
        raise SystemExit(f"no page {name!r}")
    return node


def change_main(argv: list[str]) -> int:
    """kea change <id> --because "…" [--run R] [--cycle N]: record why a signed page changed beyond a minor edit
    (its downstream sign-offs then show the reason)."""
    import argparse
    from kea.docsite import graph, nodes, signing
    parser = argparse.ArgumentParser(prog="kea change", description=change_main.__doc__)
    parser.add_argument("page")
    parser.add_argument("--because", required=True)
    parser.add_argument("--run", default="")
    parser.add_argument("--cycle", default="")
    args = parser.parse_args(argv)
    tree, ledger = _tree_and_ledger()
    node = _find(tree, args.page)
    if not signing.stale(node):
        print(f"{node.label}: no sign-off lapsed by this edit (not signed, or a minor edit): nothing to record")
        return 1
    record_change(ledger, node, args.because, args.run, args.cycle)
    graph.write_ledger(nodes.DOC, ledger)
    direct, deeper = downstream(tree, node.key)
    print(f"{node.label}: change recorded. Waits for its own sign-off; "
          f"{len(direct)} page(s) built on it wait too ({', '.join(tree.nodes[key].label for key in direct) or 'none'}), "
          f"{len(deeper)} further down are held until those are signed.")
    return 0


def impact_main(argv: list[str]) -> int:
    """kea impact <id>: what a substantive change of the page does (pages that wait, pages held) and what retiring
    it removes and keeps. Writes nothing; for the plan."""
    import argparse
    parser = argparse.ArgumentParser(prog="kea impact", description=impact_main.__doc__)
    parser.add_argument("page")
    args = parser.parse_args(argv)
    tree, _ = _tree_and_ledger()
    node = _find(tree, args.page)
    label = lambda key: f"{tree.nodes[key].label} {tree.nodes[key].title}"  # noqa: E731
    direct, deeper = downstream(tree, node.key)
    print(f"If {node.label} changes substantively:")
    print(f"  wait for their own sign-off ({len(direct)}):" + "".join(f"\n    {label(key)}" for key in direct))
    print(f"  held until those are signed ({len(deeper)}):" + "".join(f"\n    {label(key)}" for key in deeper))
    gone, keep = retire_plan(tree, node.key)
    print(f"If {node.label} is retired (kea drop {node.id} --apply):")
    print(f"  retired ({len(gone)}):" + "".join(f"\n    {label(key)}" for key in gone))
    print(f"  kept, moved up ({len(keep)}):" + "".join(f"\n    {label(key)}" for key, _ in keep))
    return 0


# ------------------------------------------------------------------ what the reader sees

def notice_html(tree, node, prefix: str) -> str:
    """The box on a page whose sign-off no longer counts because of a page above it: which page changed, the
    recorded reason, and a word diff of that change since this page was signed; or which page waits first."""
    from kea.docsite import comments, signing
    from kea.docsite.render import esc, node_link
    if node.upstream_changed and not node.held_by:
        parts = []
        for up_key, before in node.upstream_changed:
            upstream = tree.nodes[up_key]
            old = signing.find_wording(upstream, [before])
            change = change_for(tree.__dict__.get("ledger") or {}, upstream)
            why = (f" Recorded reason: {esc(str(change.get('because', '')))}"
                   + (f" (run {esc(str(change['run']))})" if change.get("run") else "") + ".") if change else ""
            if old is None:
                diff = "<p class='help'>The earlier wording is not in git, so the change cannot be shown.</p>"
            else:
                before_text = f"{old[0].get('title', '')}\n{old[0].get('short', '')}\n{old[1].strip()}"
                after_text = f"{upstream.title}\n{upstream.short}\n{upstream.body.strip()}"
                diff = comments.text_diff_html(before_text, after_text) or "<p class='help'>Only fields changed.</p>"
            check = recheck_for(tree, node, up_key)
            agent = (f" The agent last rechecked this page on {esc(str(check.get('checked', '')))}, after this change, "
                     f"and noted: &ldquo;{esc(str(check.get('because', '')))}&rdquo; (the agent's reading, not a sign-off)."
                     if check else "")
            parts.append(f"<p>{node_link(upstream, prefix)} has changed since this page was signed.{why}{agent} "
                         "Read this page against it: Approve if it still holds, Revise if not.</p>"
                         f"<details class='page-diff'><summary>What changed on {esc(upstream.label)}</summary>{diff}</details>")
        return ("<div class='upstream-notice not-annotatable'><b>Sign-off needed again: built on a page that changed.</b>"
                + "".join(parts) + "</div>")
    if node.held_by:
        found = roots(tree, node)
        items = []
        here = node.project
        for key, path in found:
            route = " ← ".join(node_link(tree.nodes[step], prefix, from_project=here) for step in path)
            items.append(f"<li>{node_link(tree.nodes[key], prefix, from_project=here)} needs a new look: "
                         f"{esc(root_reason(tree, key))}. <span class='help'>Path: {route}</span></li>")
        names = ", ".join(node_link(tree.nodes[key], prefix, from_project=here) for key, _ in found) or "a page above it"
        return ("<div class='upstream-notice held not-annotatable'><b>Held: still signed, but waits for "
                f"{names}.</b> "
                + ("A page it is built on also changed: once the pages above are signed, this page asks for its own "
                   "sign-off, with the change shown. " if node.upstream_changed else
                   "Nothing this page is built on changed its wording, so it needs no click of its own. Its sign-off "
                   f"counts again once {'that page is' if len(found) == 1 else 'those pages are'} signed again.")
                + (f"<ul>{''.join(items)}</ul>" if items else "") + "</div>")
    return ""
