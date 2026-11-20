"""Signatures that bind to what was signed (Kea 1.29): a sign-off holds for the wording the reader saw, and only
for that wording; minor edits carry it, with a reason, and anything else makes the page wait again.

A signature is one entry of ``approved:`` (a list, one entry per person) in a page's front matter:

    approved:
      - {by: Ann, orcid: 0000-…, date: 2026-11-15, version: <page version id>, how: site, thread: t2026_…,
         content: <hash of what the page says>, minor: [{content: <hash>, because: "typo", date: …, run: …}]}

1. What is signed (:func:`content`): the page's title, summary, text and fields, without the fields that record
   progress or bookkeeping (status, answer, the signatures themselves, order, uid, rechecked, …) and without the
   links that say what the page goes on to support (supports, opposes, answers, shown_in). A step that runs, a
   hypothesis that gets its outcome, a question that gets its answer keep their signature; a changed prediction,
   criterion, method, number or link does not.

2. The state of a signature (:func:`state`): ``current`` (the page says what was signed), ``minor`` (only edits
   declared minor since), ``legacy`` (made before 1.29, without ``content:``; it counts, unbound, until
   ``kea sign --adopt`` binds it to the wording of today) or ``changed`` (the page says something else: the
   signature no longer counts, the page waits again, and the site says so). :func:`approved` is true when any
   signature (or ``confirmed:``) still holds.

3. Minor edits (:func:`minor_reasons`): the agent judges an edit minor (wording, a typo, a clearer sentence, a
   link to a page that already existed) and records it with ``kea sign <id> --minor --because "…"``. Kea checks
   the edit mechanically against the signed wording (from git) and refuses it as minor when a number, a
   negation or other meaning-bearing word (direction, quantifier, modal, causal verb), a link, a non-text field,
   a short field (certainty, analysis, …) or more than a few words changed. The signer sees each minor edit and its reason on the page and can Revise it.

4. One page per click (since 1.31.1; 1.29-1.31.0 signed a whole stage at once, with a ``Signs:`` line naming each
   page and the version seen, still read by ``kea sign``). :func:`sign_order` lists the pages that wait, top down
   through the tree; the site's "Approve & next" signs one and opens the next.

5. Who writes a signature: never the agent by hand. ``kea sign --thread <id>`` applies a reader's Approve or
   Approve & go (the thread names the reader, the page versions they saw and the bundle); ``kea sign <id> --by
   <name> --how chat`` records the owner's word in the conversation (shown as recorded by the agent).
   ``kea check`` reports a site signature whose thread is missing from the comment log or names someone else.

Input: the tree of pages, git history of doc/, data/feedback/events.jsonl. Output: :func:`approved`,
:func:`state`, :func:`sign_order`, :func:`problems_and_notes`, and the ``kea sign`` command (:func:`main`).
"""
from __future__ import annotations

import datetime as dt
import difflib
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

import yaml

# front-matter fields that record progress or bookkeeping, not what the page says
UNSIGNED_FIELDS = {"order", "confirmed", "approved", "uid", "rechecked", "link", "aliases", "status", "answer"}
# links that say what the page goes on to support: written later, by the pages that build on it
UNSIGNED_RELATIONS = {"supports", "opposes", "answers", "shown_in", "supersedes"}
# words that carry meaning beyond their length: a change of any of them is never minor
MEANING_WORDS = set("""
not no nor never none neither without cannot cant dont doesnt didnt isnt arent wasnt werent wont fail fails failed
absent lack lacks lacking increase increases increased decrease decreases decreased higher lower more less fewer
greater smaller larger up down above below positive negative all every each some only most few many any
may might could must will would should significant significantly nonsignificant causes cause caused drives drive
regulates regulate leads lead depends predicts predict supports support supported opposes oppose contradicts before
after unless except
""".split())
MINOR_WORDS_ABS, MINOR_WORDS_SHARE = 5, 0.15          # at most this many changed words (or this share of the text)
SHORT_FIELD_WORDS = 4                                  # a field this short (certainty: high) must stay as it is
NUMBER = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?%?")
LINK = re.compile(r"\[\[([^\]|#]+)")
WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


# ------------------------------------------------------------------ what is signed

def signed_part(header: dict, body: str) -> tuple[dict, str]:
    """The header without unsigned fields and links, and the body with whitespace runs made one space."""
    kept = {key: value for key, value in header.items() if key not in UNSIGNED_FIELDS}
    relations = kept.get("relations")
    if isinstance(relations, dict):
        kept["relations"] = {key: value for key, value in relations.items() if key not in UNSIGNED_RELATIONS}
        if not kept["relations"]:
            del kept["relations"]
    return kept, re.sub(r"\s+", " ", body or "").strip()


def content_of(header: dict, body: str) -> str:
    """16 hex characters of the sha256 of what the page says (signed_part)."""
    kept, text = signed_part(header, body)
    blob = json.dumps(kept, sort_keys=True, ensure_ascii=False, default=str) + "\n" + text
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def content(node) -> str:
    return content_of(node.header, node.body)


def signatures(node) -> list[dict]:
    """approved: as a list of mappings (one mapping before 1.28; a bare string counts as a name)."""
    value = node.header.get("approved")
    items = value if isinstance(value, list) else [value] if value else []
    return [item if isinstance(item, dict) else {"by": str(item)} for item in items]


def valid_contents(signature: dict) -> list[str]:
    """The wordings a signature holds for: the signed one, then each minor edit after it."""
    found = [str(signature["content"])] if signature.get("content") else []
    for edit in signature.get("minor") or []:
        if isinstance(edit, dict) and edit.get("content"):
            found.append(str(edit["content"]))
    return found


def state(signature: dict, node) -> str:
    """current | minor | legacy | changed (see the module docstring)."""
    if not signature.get("content"):
        return "legacy"
    now = content(node)
    if str(signature["content"]) == now:
        return "current"
    return "minor" if now in valid_contents(signature) else "changed"


def holds(signature: dict, node) -> bool:
    return state(signature, node) != "changed"


def confirmation_holds(node) -> bool:
    confirmed = node.header.get("confirmed")
    if not confirmed:
        return False
    return not (isinstance(confirmed, dict) and confirmed.get("content")) or holds(confirmed, node)


def own_approved(node) -> bool:
    """A signature (or confirmed:) that still holds for what the page says now."""
    return confirmation_holds(node) or any(holds(item, node) for item in signatures(node))


def approved(node) -> bool:
    """The page's own sign-off holds, and so does what it was built on (propagation.bind sets node.chain_ok: false
    when a page it is built on changed since, or no longer counts as signed)."""
    return own_approved(node) and getattr(node, "chain_ok", True)


def ever_signed(node) -> bool:
    """Signed at some point, whether or not the signature still holds (the page changed after the sign-off)."""
    return bool(signatures(node) or node.header.get("confirmed"))


def stale(node) -> list[dict]:
    """The signatures that no longer hold, when none holds ([] when the page is signed or was never signed)."""
    items = signatures(node)
    if not items or approved(node):
        return []
    return [item for item in items if not holds(item, node)]


def describe(signature: dict, node) -> str:
    """One line for a tooltip or a table: who, which version, when, how, and its state."""
    how = {"chat": "recorded by the agent from the chat", "site": "on the site"}.get(str(signature.get("how") or ""), "")
    parts = [str(signature.get("by") or "?")]
    parts += [f"version {signature['version']}"] if signature.get("version") else []
    parts += [str(signature["date"])] if signature.get("date") else []
    parts += [how] if how else []
    which = state(signature, node)
    if which == "minor":
        edits = [edit for edit in signature.get("minor") or [] if isinstance(edit, dict)]
        parts.append(f"{len(edits)} minor edit(s) since: " + "; ".join(str(edit.get("because") or "") for edit in edits))
    elif which == "legacy":
        parts.append("signed before Kea 1.29, not bound to the wording")
    elif which == "changed":
        parts.append("the page has changed since; this signature no longer holds")
    return ", ".join(parts)


# ------------------------------------------------------------------ minor or not

def _words(text: str) -> list[str]:
    return [word.lower().replace("'", "") for word in WORD.findall(text or "")]


def _changed_words(old: str, new: str) -> int:
    before, after = _words(old), _words(new)
    matcher = difflib.SequenceMatcher(a=before, b=after, autojunk=False)
    return sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal")


def text_reasons(name: str, old: str, new: str) -> list[str]:
    """Why a change of one text is not minor ([] when it is)."""
    reasons = []
    if Counter(NUMBER.findall(old)) != Counter(NUMBER.findall(new)):
        gone = sorted(set(NUMBER.findall(old)) - set(NUMBER.findall(new)))
        came = sorted(set(NUMBER.findall(new)) - set(NUMBER.findall(old)))
        reasons.append(f"{name}: numbers changed ({', '.join(gone) or '–'} → {', '.join(came) or '–'})")
    meaning_old = Counter(word for word in _words(old) if word in MEANING_WORDS)
    meaning_new = Counter(word for word in _words(new) if word in MEANING_WORDS)
    if meaning_old != meaning_new:
        changed = sorted(set((meaning_old - meaning_new) + (meaning_new - meaning_old)))
        reasons.append(f"{name}: words that carry meaning changed ({', '.join(changed)})")
    if set(LINK.findall(old)) != set(LINK.findall(new)):
        reasons.append(f"{name}: links changed")
    count = len(_words(old))
    changed = _changed_words(old, new)
    if changed > max(MINOR_WORDS_ABS, MINOR_WORDS_SHARE * count):
        reasons.append(f"{name}: {changed} of {count} words changed (minor allows {max(MINOR_WORDS_ABS, int(MINOR_WORDS_SHARE * count))})")
    return reasons


def minor_reasons(old_header: dict, old_body: str, new_header: dict, new_body: str) -> list[str]:
    """Why the edit from the signed wording to the new one is not minor ([] when it is)."""
    old, old_text = signed_part(old_header, old_body)
    new, new_text = signed_part(new_header, new_body)
    reasons = []
    for key in sorted(set(old) | set(new)):
        before, after = old.get(key), new.get(key)
        if before == after:
            continue
        if isinstance(before, str) and isinstance(after, str) and len(_words(before)) >= SHORT_FIELD_WORDS:
            reasons += text_reasons(key, before, after)
        else:
            reasons.append(f"{key}: changed ({json.dumps(before, default=str, ensure_ascii=False)[:60]} → "
                           f"{json.dumps(after, default=str, ensure_ascii=False)[:60]})")
    if old_text != new_text:
        reasons += text_reasons("text", old_text, new_text)
    return reasons


# ------------------------------------------------------------------ the order of sign-offs: one page per click

def sign_order(tree) -> list:
    """Every page that waits for a sign-off (pace: guided), in the order a reader should read and sign them: top
    down through the tree. Per experiment: the experiment, its premises and decisions; then each question in turn
    with its hypotheses, planned steps, results and conclusions (the route's order); a page that fits nowhere comes
    right after its parent, else at the end. One Approve signs one page (since 1.31.1); the site's "Approve & next"
    walks this list."""
    from kea.docsite import graph, questions
    from kea.docsite.nodes import natural
    rank = {"experiment": 0, "premise": 1, "decision": 2, "question": 3, "hypothesis": 4, "step": 5, "result": 6,
            "figure": 7, "conclusion": 8}
    order: list = []

    def add(node) -> None:
        if node.waiting and node not in order:
            order.append(node)
    for project, home in tree.projects.items():
        add(home)
        top = [node for node in tree.nodes.values() if node.project == project and node.type in ("premise", "decision")
               and node.parent in (None, "home")]
        for node in sorted(top, key=lambda node: (rank[node.type], natural(node.number or node.id))):
            add(node)
        for question in questions.questions(tree, project):
            add(question)
            for stage in graph.question_route(tree, question)["stages"]:
                for node in sorted(stage["pages"], key=lambda node: (rank.get(node.type, 9), natural(node.number or node.id))):
                    add(node)
    rest = sorted((node for node in tree.nodes.values() if node.waiting and node not in order),
                  key=lambda node: (node.project, rank.get(node.type, 9), natural(node.number or node.id)))
    for node in rest:                              # after its parent (and the parent's earlier children), if listed
        parent = tree.nodes.get(f"{node.project}:{node.parent}") if node.parent else None
        if parent in order:
            index = order.index(parent) + 1
            while index < len(order) and order[index].parent == node.parent and order[index].project == node.project:
                index += 1
            order.insert(index, node)
        else:
            order.append(node)
    return order


def _question_waits(question) -> bool:
    """A question waits as a question (to be approved before its plan), not for its plan or results."""
    return question.waiting and not signatures(question)


# ------------------------------------------------------------------ checks (kea build / kea check)

def problems_and_notes(tree, events_path: Path | None = None) -> tuple[list[str], list[str]]:
    """Site signatures not backed by the comment log (problems); pages whose signature no longer holds, and
    signatures made before 1.29 (notes)."""
    from kea.feedback import store
    problems, notes = [], []
    path = events_path or store.default_path()
    threads = {}
    if path.exists():
        try:
            threads = {thread.thread_id: thread for thread in store.threads(path)}
        except (OSError, ValueError):
            threads = {}
    legacy = 0
    for node in tree.nodes.values():
        for signature in signatures(node):
            if not signature.get("content"):
                legacy += 1
            thread_id = str(signature.get("thread") or "")
            if thread_id and threads:
                thread = threads.get(thread_id)
                if thread is None:                       # a note: the local log may lag behind a hub
                    notes.append(f"{node.key}: signature of {signature.get('by')} names thread {thread_id}, which "
                                    "is not in the comment log (a signature is applied with kea sign --thread)")
                elif not ({"approve", "go"} & set(thread.tags)) or thread.author != signature.get("by") \
                        or (thread.page != node.key and node.key not in _signed_labels(thread)):
                    problems.append(f"{node.key}: signature of {signature.get('by')} does not match thread "
                                    f"{thread_id} (by {thread.author} on {thread.page}, tags {thread.tags})")
        gone = stale(node)
        if gone:
            names = ", ".join(dict.fromkeys(str(item.get("by") or "?") for item in gone))
            notes.append(f"{node.key}: changed since {names} signed it: it waits for a new sign-off (or, when the "
                         f"edit is minor, kea sign {node.id} --minor --because \"…\")")
    if legacy:
        notes.append(f"{legacy} signature(s) made before Kea 1.29 are not bound to the wording they signed; kea sign "
                     "--adopt binds them to the wording of today")
    return problems, notes


def _signed_labels(thread) -> list[str]:
    return [label for label, _ in parse_signs(thread.text)]


SIGNS = re.compile(r"^Signs:\s*(.+)$", re.M)


def parse_signs(text: str) -> list[tuple[str, str]]:
    """[(page key, version)] from a thread's 'Signs: exp:q-a@ver, exp:h-b@ver' line ([] without one)."""
    found = SIGNS.search(text or "")
    if not found:
        return []
    items = []
    for part in found.group(1).split(","):
        label, _, version = part.strip().partition("@")
        if label:
            items.append((label.strip(), version.strip()))
    return items


# ------------------------------------------------------------------ git: the wording that was signed

def _git(*args: str) -> str:
    from kea.docsite.nodes import PROJECT_ROOT
    result = subprocess.run(["git", "-C", str(PROJECT_ROOT), *args], capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""


def history(path: Path, limit: int = 200):
    """(commit, header, body) of the file at each commit that changed it, newest first."""
    from kea.docsite.nodes import PROJECT_ROOT, split_front_matter
    try:
        relative = path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:                      # a page outside the repository: no history
        return
    for commit in _git("log", f"-n{limit}", "--format=%H", "--", relative).split():
        text = _git("show", f"{commit}:{relative}")
        if not text:
            continue
        try:
            header, body = split_front_matter(text, path)
        except ValueError:
            continue
        yield commit, header, body


def find_wording(node, contents: list[str] | None = None, version: str = ""):
    """(header, body) of the page as it was when it said one of ``contents`` (or had page ``version``): the
    working copy first, then git history. None when not found."""
    from kea.docsite import identity

    def matches(header, body) -> bool:
        if version:
            probe = type("Probe", (), {"header": header, "body": body})()
            return identity.version_of(probe) == version
        return content_of(header, body) in (contents or [])
    if matches(node.header, node.body):
        return node.header, node.body
    for _, header, body in history(node.source):
        if matches(header, body):
            return header, body
    return None


# ------------------------------------------------------------------ writing approved:

def _flow(entry: dict) -> str:
    return yaml.safe_dump(entry, default_flow_style=True, allow_unicode=True, width=100000, sort_keys=False).strip()


def write_signatures(source: Path, entries: list[dict]) -> None:
    """Replace the page's approved: block with ``entries`` (one flow mapping per line); nothing else changes."""
    text = source.read_text(encoding="utf-8")
    lines = text.split("\n")
    end = lines.index("---", 1)
    head, rest = lines[1:end], lines[end:]
    kept, skipping = [], False
    for line in head:
        if re.match(r"^approved:", line):
            skipping = True
            continue
        if skipping and (line.startswith((" ", "\t", "-")) or not line.strip()):
            continue
        skipping = False
        kept.append(line)
    if entries:
        kept.append("approved:")
        kept += [f"  - {_flow(entry)}" for entry in entries]
    source.write_text("\n".join(["---"] + kept + rest), encoding="utf-8")


def _upstream_field(tree, node) -> dict:
    """{"upstream": {page: hash}} of what the page is built on now (propagation.py), {} when it is built on nothing."""
    from kea.docsite import propagation
    found = propagation.upstream_hashes(tree, node)
    return {"upstream": found} if found else {}


def add_signature(node, entry: dict) -> None:
    """Add (or replace, for the same person) a signature on the page."""
    entries = [item for item in signatures(node) if item.get("by") != entry.get("by")] + [entry]
    write_signatures(node.source, entries)


# ------------------------------------------------------------------ kea sign

def apply_thread(tree, thread, resolve) -> None:
    """Write the signatures of one site sign-off (an Approve, or an Approve & go): every page on its 'Signs:' line,
    else the thread's page, each bound to the version the reader saw (from git when the page changed since)."""
    from kea.docsite import identity
    items = parse_signs(thread.text) or [(thread.page, thread.page_version)]
    for label, version in items:
        node = tree.nodes.get(label) or resolve(label)
        if version and identity.version_of(node) != version:
            old = find_wording(node, version=version)
            if old is None:
                print(f"{node.label}: the version {version} the reader saw is not in git; not signed (ask again)")
                continue
            signed = content_of(*old)
        else:
            signed = content(node)
        entry = {"by": thread.author, **({"orcid": thread.author_id} if thread.author_id else {}),
                 "date": thread.created_at[:10], **({"version": version} if version else {}), "how": "site",
                 "thread": thread.thread_id, "content": signed, **_upstream_field(tree, node)}
        add_signature(node, entry)
        print(f"{node.label}: signed by {thread.author}" + ("" if signed == content(node) else
                                                              " (an earlier wording: the page waits again)"))


def main(argv: list[str]) -> int:
    """kea sign: record sign-offs and minor edits (see the module docstring)."""
    import argparse
    from kea.docsite import identity
    from kea.docsite.nodes import DOC, load_tree
    parser = argparse.ArgumentParser(
        prog="kea sign", description="Record a sign-off bound to the page's wording, or a minor edit that keeps it.",
        epilog="kea sign --thread T: apply a reader's Approve (or Approve & go), with every page on its Signs: line (1.29-1.31.0).  "
               "kea sign ID… --by NAME --how chat: the owner signed off in the conversation.  "
               "kea sign ID --minor --because \"…\": an edit that changes no meaning keeps the signatures.  "
               "kea sign --adopt: bind signatures made before 1.29 to today's wording.  kea sign --list: every "
               "signature and whether it holds.")
    parser.add_argument("ids", nargs="*")
    parser.add_argument("--thread", default="", help="apply the Approve / Approve & go of this comment thread")
    parser.add_argument("--pending", action="store_true",
                        help="apply every open Approve given on the site (at the harvest)")
    parser.add_argument("--by", default="", help="the person who signed off (with --how chat)")
    parser.add_argument("--orcid", default="")
    parser.add_argument("--how", default="chat", choices=["chat"], help="only chat: site sign-offs come with --thread")
    parser.add_argument("--date", default="")
    parser.add_argument("--minor", action="store_true", help="the edit since the signature is minor")
    parser.add_argument("--because", default="", help="with --minor: what changed and why it changes no meaning")
    parser.add_argument("--run", default="")
    parser.add_argument("--adopt", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    tree = load_tree(DOC)
    project = next(iter(tree.projects), "")
    today = dt.date.today().isoformat()

    def resolve(item: str):
        node = tree.resolve(item, project)
        if node is None:
            raise SystemExit(f"no page {item!r}")
        return node

    if args.list:
        for node in sorted(tree.nodes.values(), key=lambda item: (item.project, item.label)):
            for signature in signatures(node):
                print(f"{node.key}  {node.label}  {state(signature, node):8}  {describe(signature, node)}")
        return 0

    if args.adopt:
        count = 0
        for node in tree.nodes.values():
            entries = signatures(node)
            if any(not item.get("content") for item in entries):
                now = content(node)
                write_signatures(node.source, [item if item.get("content") else {**item, "content": now}
                                               for item in entries])
                count += sum(not item.get("content") for item in entries)
        print(f"bound {count} signature(s) to the wording of today")
        return 0

    if args.minor:
        if not args.because.strip():
            parser.error("--minor needs --because: what changed, and why it changes no meaning")
        if not args.ids:
            parser.error("--minor needs the page id(s)")
        failed = 0
        for item in args.ids:
            node = resolve(item)
            gone = [entry for entry in signatures(node) if state(entry, node) == "changed"]
            if not gone:
                print(f"{node.label}: no signature waits on a change (nothing to carry)")
                continue
            now = content(node)
            entries, refused = [], []
            for entry in signatures(node):
                if entry in gone:
                    old = find_wording(node, valid_contents(entry))
                    if old is None:
                        refused.append(f"{entry.get('by')}: the signed wording is not in git (commit the signed page "
                                       "before editing it); ask for a new sign-off")
                    else:
                        reasons = minor_reasons(old[0], old[1], node.header, node.body)
                        if reasons:
                            refused += reasons
                        else:
                            entry = {**entry, "minor": list(entry.get("minor") or []) + [
                                {"content": now, "because": args.because.strip(), "date": today,
                                 **({"run": args.run} if args.run else {})}]}
                entries.append(entry)
            if refused:
                failed += 1
                print(f"{node.label}: NOT minor; the page waits for a new sign-off:\n  " + "\n  ".join(dict.fromkeys(refused)))
                continue
            write_signatures(node.source, entries)
            print(f"{node.label}: minor edit recorded; {len(gone)} signature(s) carried")
        return 1 if failed else 0

    if args.thread or args.pending:
        from kea.feedback import backend, cycle, store
        client = backend.get()
        if client.remote:
            client.sync()
        threads = store.threads(client.events_path)
        if args.pending:
            chosen = cycle.sign_requests(threads)
            if not chosen:
                print("no open sign-off on the site")
            for thread in chosen:
                print(f"thread {thread.thread_id} by {thread.author} on {thread.page}:")
                apply_thread(tree, thread, resolve)
            if chosen:
                print("next: commit, answer each thread with the commit ("
                      + "; ".join(f"kea reply {thread.thread_id} \"Signed off in <commit>\" --status answered"
                                  for thread in chosen)
                      + "), and add the next step of every stage this completes to the plan (kea context names it); "
                        "it runs at Implement")
            return 0
        found = {thread.thread_id: thread for thread in threads}
        thread = found.get(args.thread)
        if thread is None:
            raise SystemExit(f"no thread {args.thread!r} in the comment log")
        if not {"approve", "go"} & set(thread.tags):
            raise SystemExit(f"thread {args.thread} is not an Approve or Approve & go (tags {thread.tags})")
        if "go" in thread.tags and thread.text.startswith("Go:"):
            print("a Go: on a page signed off already: it adds no signature")
            return 0
        apply_thread(tree, thread, resolve)
        return 0

    if not args.ids or not args.by.strip():
        parser.error("name the page(s) and --by (the owner who signed off in the chat), or use --thread")
    for item in args.ids:
        node = resolve(item)
        entry = {"by": args.by.strip(), **({"orcid": args.orcid} if args.orcid else {}), "date": args.date or today,
                 "version": identity.version_of(node), "how": "chat", "content": content(node),
                 **_upstream_field(tree, node)}
        add_signature(node, entry)
        print(f"{node.label}: signed by {entry['by']} (from the chat)")
    return 0
