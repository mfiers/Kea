"""Work through reader comments from the command line (used by Claude at the start of a session).

Usage:
    kea list            open threads, grouped by page, with the source file to edit
    kea list --all      every thread
    kea list --json     machine-readable
    kea show <thread>   one thread in full
    kea reply <thread> "text" [--status answered|page-changed|wont-fix] [--commit <sha>] [--note ..]
    kea status <thread> <status> [--commit <sha>] [--note ..]
    kea list --unplanned        threads with activity after the last plan update
    kea cycle status|plan-updated|start|release [--run R --commit C]
        release also needs --version X.Y.Z --kind major|minor|patch --reason "…" [--experiment NAME=X.Y.Z …]
        and writes annotated git tags (vX.Y.Z, NAME/vX.Y.Z) on the release commit
    kea watch --deadline <when> [--interval 5 --slow-interval 60 --quiet-after 3600 --settle 120 --report-every 3600]
        waits (fast polling while readers are active, slow after an hour of quiet; comments are reported once a
        burst has settled); exit 10 = comments to fold into the plan (while collecting, or on the plan while
        frozen), 20 = a reader pressed "Implement the plan", 30 = deadline reached. <when> is epoch seconds, a
        duration from now (90m, 12h, 3d) or an ISO date/time (2026-11-09T18:00, local time). Prints a status line
        every --report-every seconds and writes only its heartbeat (data/feedback/watch_heartbeat.json, shown on
        the plan page).
    kea watch --status  is a watcher running, when did it last look, what is it waiting for (exit 0 if alive, 1 if not)
    kea lease status|take|release [--force]
        one agent per project (feedback.agent): every command that writes (reply, status, cycle, watch,
        apply-suggestion, publish) takes or renews the lease; another agent is refused (exit 2). Take it at the
        start of a session; --force only when the owner says the other session is finished.

With a hub (kea.yaml `remote:`, feedback.backend) the same commands read and write the hub's record; the local
data/feedback/*.jsonl files are kept as an exact mirror.

Replies and status changes are written as author "claude" (the server refuses that name for readers).
A status of page-changed needs --commit: the commit that rewrote the page.
After replying, `make site` refreshes the static copies; the live panel shows replies at once.
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import sys
import textwrap
from pathlib import Path

import time

from kea.config import PROJECT_ROOT
from kea.feedback import agent, backend, cycle, store, tags

AUTHOR = "claude"
PROJECT = PROJECT_ROOT


def last_reader_activity(events_path: Path) -> float:
    """Epoch seconds of the newest event written by a reader (not by Claude); 0 when there is none."""
    newest = ""
    for event in store.load_events(events_path):
        if event.get("author") != AUTHOR and event.get("created_at", "") > newest:
            newest = event["created_at"]
    if not newest:
        return 0.0
    return float(calendar.timegm(time.strptime(newest, "%Y-%m-%dT%H:%M:%SZ")))


def watch(args: argparse.Namespace) -> int:
    """Wait for something to do; adaptive polling; writes nothing but its heartbeat.

    Polls every --interval seconds while a reader was active in the last --quiet-after seconds, else every
    --slow-interval. Comments to plan are reported only after --settle seconds without new reader activity,
    so a burst of comments is folded in one pass. An Implement request is reported at once.
    Exit 10 = comments to fold into the plan (also while frozen: comments on the plan), 20 = implement requested,
    30 = deadline reached. Writes only the heartbeat file (unless --no-heartbeat) and a status line every
    --report-every seconds, so whoever started it can see it is alive.
    """
    started = last_report = time.time()
    polls = 0
    client = backend.get(args.events, args.cycle_log)
    client.take_lease(watching=True)                 # refused (LeaseHeld) when another agent works on the project
    while True:
        try:
            client.sync()
        except backend.RemoteError as error:
            print(f"watching: {error}; trying again", flush=True)
        current = cycle.state(args.cycle_log)
        polls += 1
        extra = {"pid": os.getpid(), "deadline": args.deadline, "state": current.state, "cycle": current.cycle,
                 "started": started, "slow_interval": args.slow_interval}

        def leave(reason: str, code: int) -> int:
            """Stop on purpose: a last heartbeat says why, so the hub does not take the silence for a crash."""
            if args.heartbeat:
                try:
                    client.heartbeat({**extra, "exit": reason})
                except backend.RemoteError as error:
                    print(f"watching: last heartbeat not sent ({error})", flush=True)
            return code
        try:
            if args.heartbeat:
                client.heartbeat(extra)              # also renews the lease
            else:
                client.take_lease(watching=True)
        except backend.RemoteError as error:
            print(f"watching: {error}", flush=True)
        if time.time() - last_report >= args.report_every:
            last_report = time.time()
            print(f"watching: {time.strftime('%Y-%m-%d %H:%M')}, cycle {current.cycle} {current.state}, "
                  f"{len(cycle.needs_planning(store.threads(args.events), current))} thread(s) waiting to be "
                  f"planned (reported after {args.settle:.0f} s of quiet), {polls} polls so far, deadline "
                  f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(args.deadline))}", flush=True)
        if current.state == "implement-requested":
            print(f"implement requested by {current.by} at {current.since} (cycle {current.cycle})")
            return leave("implementing", 20)
        quiet_for = time.time() - last_reader_activity(args.events)
        if current.state in cycle.PLAN_OPEN_STATES and quiet_for >= args.settle:
            waiting = cycle.needs_planning(store.threads(args.events), current)
            edits = cycle.direct_edits(current.plan_updated_at) if args.cycle_log == cycle.default_path() else []
            if waiting or edits:
                print(f"{len(waiting)} thread(s) and {len(edits)} direct edit commit(s) to fold into the plan of "
                      f"cycle {current.cycle}")
                return leave("planning", 10)
        if time.time() >= args.deadline:
            print("deadline reached", flush=True)
            return leave("deadline", DEADLINE_EXIT)
        time.sleep(args.interval if quiet_for < args.quiet_after else args.slow_interval)


DEADLINE_EXIT = 30


def parse_deadline(value: str, now: float | None = None) -> float:
    """Epoch seconds from epoch seconds, a duration from now (90m, 12h, 3d, 1w) or an ISO date/time (local)."""
    import datetime as dt
    now = time.time() if now is None else now
    value = value.strip()
    duration = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([smhdw])", value)
    if duration:
        seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[duration.group(2)]
        return now + float(duration.group(1)) * seconds
    try:
        return float(value)
    except ValueError:
        pass
    try:
        return dt.datetime.fromisoformat(value).timestamp()
    except ValueError:
        raise argparse.ArgumentTypeError(f"--deadline {value!r}: give epoch seconds, a duration (90m, 12h, 3d) or "
                                         "an ISO date/time (2026-11-09T18:00)") from None


def watch_status() -> int:
    """Print what the last watcher wrote in its heartbeat; 0 if its process is alive and polled recently."""
    info = cycle.read_heartbeat_info()
    if not info:
        print("no watcher has run here (no data/feedback/watch_heartbeat.json)")
        return 1
    age = time.time() - calendar.timegm(time.strptime(info["at"], "%Y-%m-%dT%H:%M:%SZ"))
    alive = False
    if info.get("pid"):
        try:
            os.kill(int(info["pid"]), 0)
            alive = True
        except (OSError, ValueError):
            alive = False
    deadline = info.get("deadline")
    print(f"watcher pid {info.get('pid', '?')}: {'running' if alive else 'not running'}; last poll {age:.0f} s ago "
          f"({info['at']}); cycle {info.get('cycle', '?')} {info.get('state', '?')}"
          + (f"; deadline {time.strftime('%Y-%m-%d %H:%M', time.localtime(deadline))}" if deadline else ""))
    return 0 if alive and age < 600 else 1


VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def check_release(args: argparse.Namespace) -> str:
    """'' if the release arguments are complete and the version follows the latest one; else the problem."""
    if not (args.run and args.commit):
        return "release needs --run and --commit"
    if not VERSION_PATTERN.match(args.version or "") or not args.kind or not args.reason:
        return "release needs --version X.Y.Z, --kind major|minor|patch and --reason (doc/site_design.md, Versions)"
    from kea.docsite.versions import next_versions, releases
    site = releases("")
    if site:
        allowed = next_versions(site[-1].version)
        if args.version not in allowed.values():
            return f"after {site[-1].label} the next version is one of {', '.join(allowed.values())}"
        expected = allowed[args.kind] if not site[-1].version.startswith("0.") or args.kind != "major" \
            else allowed["minor"]
        if args.version != expected:
            return f"--kind {args.kind} after {site[-1].label} gives {expected} (before 1.0 major counts as minor)"
    for item in args.experiment:
        if not re.match(r"^[\w.-]+=\d+\.\d+\.\d+$", item):
            return f"--experiment {item!r}: expected NAME=X.Y.Z"
    return ""


def tag_release(args: argparse.Namespace, cycle_number: int) -> None:
    """Annotated tags vX.Y.Z (and <experiment>/vX.Y.Z), after kea.yaml's tag_prefix, on the release commit; the
    message holds the metadata."""
    import subprocess
    from kea.docsite.versions import tag_name
    message = (f"Release v{args.version}\n\nRun: {args.run}\nCycle: {cycle_number}\nKind: {args.kind}\n"
               f"Reason: {args.reason}\n")
    tags = [tag_name(args.version)] + [tag_name(version, name) for name, version in
                                       (item.split("=", 1) for item in args.experiment)]
    for tag in tags:
        result = subprocess.run(["git", "tag", "-a", tag, args.commit, "-m", message], cwd=PROJECT, capture_output=True,
                                text=True)
        print(f"tag {tag}: {'ok' if result.returncode == 0 else result.stderr.strip()}")


def page_sources() -> dict[str, str]:
    """Thread key -> file to edit: node keys (project:id) map to their Markdown file, code/<path> to the code file."""
    try:
        from kea.docsite.nodes import load_tree
    except ImportError:
        return {}
    return {key: str(node.source.relative_to(PROJECT)) for key, node in load_tree().nodes.items()}


def source_of(page: str, sources: dict[str, str]) -> str | None:
    """The file to edit for a thread: its Markdown source, the code file of a code page, or a run entry."""
    if page in sources:
        return sources[page]
    if page.startswith("code/"):
        return page[len("code/"):]
    if page.startswith("plan/cycle-"):
        return f"doc/_cycles/cycle-{int(page.rsplit('-', 1)[1]):03d}.md"
    if page.startswith("changes/"):
        return f"doc/_changes/{page[len('changes/'):]}.md"
    return None


def line_range(path: str | None, quote: str) -> str:
    """'lines 98-104' when the quoted text is found in the file now."""
    if not path or not quote or not (PROJECT / path).is_file():
        return ""
    text = (PROJECT / path).read_text(encoding="utf-8", errors="replace")
    probe = quote.strip().splitlines()[0][:120] if quote.strip() else ""
    position = text.find(probe) if probe else -1
    if position < 0:
        return " (quoted text no longer in the file)"
    first = text.count("\n", 0, position) + 1
    last = first + quote.strip().count("\n")
    return f", lines {first}-{last}" if last > first else f", line {first}"


def describe(thread: store.Thread, sources: dict[str, str]) -> str:
    source = source_of(thread.page, sources)
    made: dict[str, list[str]] = {}
    lines = [f"── {thread.thread_id}  [{thread.status}]  {thread.page}  ({thread.page_title})",
             f"   edit: {source + line_range(source, thread.quote) if source else 'generated page (no own source file)'}"
             f"   · asked on version {thread.page_commit or '?'}"]
    if made.get("code"):
        lines.append(f"   made by: {', '.join(made['code'])}")
    if made.get("inputs"):
        lines.append(f"   from: {', '.join(made['inputs'][:6])}")
    for name in thread.tags:
        info = tags.describe(name)
        kind = "task" if info.get("task", True) else "mark (no work; for the manuscript)"
        lines.append(f"   TAG {name} [{kind}]" + (f": {info['instruction']}" if info.get("instruction") else ""))
    if thread.quote:
        context = f"…{thread.prefix}⟦{thread.quote}⟧{thread.suffix}…".replace("\n", " ")
        lines.append("   on text: " + textwrap.shorten(context, 400, placeholder=" …"))
    else:
        lines.append("   on: the whole page")
    if thread.author_id:
        lines.append(f"   signed in: {thread.author} = ORCID {thread.author_id}")
    for author, text, created in [(thread.author, thread.text, thread.created_at)] + \
            [(reply.author, reply.text, reply.created_at) for reply in thread.replies]:
        if not text:
            continue
        lines.append(f"   {author} ({created}):")
        lines += ["      " + line for line in text.splitlines() or [""]]
    if thread.suggestion:
        lines.append(f"   SUGGESTED EDIT of {thread.suggestion.get('path')} (based on {thread.suggestion.get('base_commit')});"
                     f" apply with: kea apply-suggestion {thread.thread_id}")
        lines += ["      " + line for line in thread.suggestion.get("diff", "").splitlines()[2:80]]
    if thread.status != "open":
        lines.append(f"   status {thread.status} by {thread.status_by} {thread.status_at}"
                     f"{' commit ' + thread.commit if thread.commit else ''}"
                     f"{': ' + thread.status_note if thread.status_note else ''}")
    return "\n".join(lines)


needs_attention = cycle.needs_attention


def apply_suggestion(thread: store.Thread) -> int:
    """Three-way merge of a suggested edit onto the current file (git merge-file); 0 = clean, >0 = conflicts left
    in the file with markers, -1 = not a suggestion. Does not commit."""
    import subprocess
    import tempfile
    if not thread.suggestion:
        print(f"{thread.thread_id} is not a suggested edit", file=sys.stderr)
        return -1
    target = PROJECT / thread.suggestion["path"]
    with tempfile.TemporaryDirectory() as folder:
        base, new = Path(folder) / "base", Path(folder) / "suggested"
        base.write_text(thread.suggestion.get("base_text", ""), encoding="utf-8")
        new.write_text(thread.suggestion["new_text"], encoding="utf-8")
        result = subprocess.run(["git", "merge-file", "-L", "current", "-L", "base", "-L", f"suggestion {thread.author}",
                                 str(target), str(base), str(new)], capture_output=True, text=True)
    conflicts = result.returncode
    print(f"merged into {thread.suggestion['path']}: " + ("clean" if conflicts == 0 else f"{conflicts} conflict(s), "
                                                           "markers left in the file"))
    return conflicts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kea", description=__doc__.split("\n")[0])
    parser.add_argument("--events", type=Path, default=store.default_path())
    sub = parser.add_subparsers(dest="command", required=True)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--all", action="store_true")
    list_parser.add_argument("--json", action="store_true")
    list_parser.add_argument("--unplanned", action="store_true")
    apply_parser = sub.add_parser("apply-suggestion", help="merge a suggested edit into its file (no commit)")
    apply_parser.add_argument("thread_id")
    cycle_parser = sub.add_parser("cycle")
    cycle_parser.add_argument("action", choices=["status", "plan-updated", "start", "release"])
    cycle_parser.add_argument("--run", default="")
    cycle_parser.add_argument("--commit", default="")
    cycle_parser.add_argument("--cycle-log", type=Path, default=cycle.default_path())
    cycle_parser.add_argument("--version", default="", help="release: the site version X.Y.Z (required)")
    cycle_parser.add_argument("--kind", choices=["major", "minor", "patch"], help="release: size of the change")
    cycle_parser.add_argument("--reason", default="", help="release: one sentence on why this kind")
    cycle_parser.add_argument("--experiment", action="append", default=[], metavar="NAME=X.Y.Z",
                              help="release: also tag an experiment version (repeatable)")
    cycle_parser.add_argument("--no-tag", action="store_true", help="release: record only, do not create git tags")
    watch_parser = sub.add_parser("watch")
    watch_parser.add_argument("--deadline", type=parse_deadline, default=None,
                              help="epoch seconds, a duration from now (90m, 12h, 3d) or an ISO date/time")
    watch_parser.add_argument("--status", action="store_true", help="report on the running watcher and exit")
    watch_parser.add_argument("--report-every", type=float, default=3600, help="seconds between status lines")
    watch_parser.add_argument("--interval", type=float, default=5, help="poll interval while readers are active")
    watch_parser.add_argument("--slow-interval", type=float, default=60, help="poll interval after --quiet-after")
    watch_parser.add_argument("--quiet-after", type=float, default=3600, help="seconds without reader activity")
    watch_parser.add_argument("--no-heartbeat", dest="heartbeat", action="store_false",
                              help="do not write data/feedback/watch_heartbeat.json (shown on the plan page)")
    watch_parser.add_argument("--settle", type=float, default=120,
                              help="report comments only after this many seconds without new reader activity")
    watch_parser.add_argument("--cycle-log", type=Path, default=cycle.default_path())
    show_parser = sub.add_parser("show")
    show_parser.add_argument("thread_id")
    reply_parser = sub.add_parser("reply")
    reply_parser.add_argument("thread_id")
    reply_parser.add_argument("text")
    reply_parser.add_argument("--status", choices=["planned", "answered", "page-changed", "wont-fix"], default="answered")
    reply_parser.add_argument("--commit", default="")
    reply_parser.add_argument("--note", default="")
    status_parser = sub.add_parser("status")
    status_parser.add_argument("thread_id")
    status_parser.add_argument("status", choices=store.STATUSES)
    status_parser.add_argument("--commit", default="")
    status_parser.add_argument("--note", default="")
    tags_parser = sub.add_parser("tags", help="text and pages readers tagged (default: the manuscript marks)")
    tags_parser.add_argument("names", nargs="*", help="only these tags (default: all tags of the manuscript group)")
    tags_parser.add_argument("--json", action="store_true")
    lease_parser = sub.add_parser("lease", help="one agent per project: status, take or release the lease")
    lease_parser.add_argument("action", choices=["status", "take", "release"])
    lease_parser.add_argument("--force", action="store_true",
                              help="take or release a lease another agent holds (only on the owner's word)")
    args = parser.parse_args(argv)
    try:
        return run(args, parser)
    except agent.LeaseHeld as held:
        print(held, file=sys.stderr)
        return 2
    except backend.RemoteError as error:
        print(error, file=sys.stderr)
        return 1


def tags_command(args: argparse.Namespace, threads: list[store.Thread]) -> int:
    """Tagged fragments per tag, in page order: the material a manuscript is assembled from."""
    known = tags.vocabulary()
    wanted = args.names or [tag["name"] for tag in known["tags"] if tag["group"] == "manuscript"]
    chosen = [thread for thread in threads if thread.status not in ("resolved", "wont-fix")
              and any(name in wanted for name in thread.tags)]
    if args.json:
        print(json.dumps([thread.to_dict() for thread in chosen], indent=1, ensure_ascii=False))
        return 0
    sources = page_sources()
    for name in wanted:
        members = sorted((thread for thread in chosen if name in thread.tags), key=lambda item: (item.page, item.start or 0))
        if not members:
            continue
        print(f"## {name} ({len(members)})")
        for thread in members:
            source = source_of(thread.page, sources)
            where = source + line_range(source, thread.quote) if source else thread.page
            what = textwrap.shorten(thread.quote.replace("\n", " "), 300, placeholder=" …") if thread.quote else "(the whole page)"
            print(f"- {thread.thread_id}  {where}  ({thread.page_title})\n    {what}"
                  + (f"\n    note: {thread.text}" if thread.text else "")
                  + (f"\n    also: {', '.join(other for other in thread.tags if other != name)}"
                     if len(thread.tags) > 1 else ""))
        print()
    return 0


def lease_command(args: argparse.Namespace) -> int:
    client = backend.get(args.events)
    if args.action == "take":
        lease = client.take_lease(force=args.force)
        print(f"lease held by this agent ({lease['agent']}) since {lease['since']}"
              + (f"; taken over from {lease['took_over_from']}" if lease.get("took_over_from") else ""))
        return 0
    if args.action == "release":
        client.release_lease(force=args.force)
        print("lease released")
        return 0
    lease = client.lease()
    if not lease:
        print(f"no agent holds the lease ({client.describe()})")
        return 0
    mine = lease.get("agent") == agent.agent_id()
    free = agent.is_free_for(lease, agent.agent_id(), check_process=not client.remote)
    print(f"lease: {lease.get('agent')} on {lease.get('host')} ({lease.get('path')}), since {lease.get('since')}, "
          f"renewed {lease.get('renewed_at')}{', watching' if lease.get('watching') else ''} — "
          + ("this agent" if mine else "free to take (expired or ended)" if free else "ANOTHER AGENT"))
    return 0 if mine or free else 2


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command == "lease":
        return lease_command(args)
    client = backend.get(args.events, getattr(args, "cycle_log", None))
    if client.remote and args.command in ("list", "show", "cycle", "apply-suggestion", "reply", "status", "tags"):
        client.sync()

    if args.command == "cycle":
        if args.action == "status":
            print(json.dumps(cycle.state(args.cycle_log).to_dict(), indent=1))
            return 0
        client.take_lease()
        kind = {"plan-updated": "plan-updated", "start": "implementing", "release": "released"}[args.action]
        if args.action == "release":
            problem = check_release(args)
            if problem:
                print(problem, file=sys.stderr)
                return 1
        try:
            current = client.append_cycle(kind, AUTHOR, run=args.run, commit=args.commit,
                                          version=args.version if args.action == "release" else "")
        except store.FeedbackError as error:
            print(error, file=sys.stderr)
            return 1
        if args.action == "release" and not args.no_tag:
            tag_release(args, current.cycle - 1)
        print(json.dumps(current.to_dict(), indent=1))
        return 0
    if args.command == "watch":
        if args.status:
            return watch_status()
        if args.deadline is None:
            parser.error("watch needs --deadline (epoch seconds, 90m, 12h, 3d or an ISO date/time) or --status")
        return watch(args)

    all_threads = store.fold(store.load_events(args.events))
    if args.command == "tags":
        return tags_command(args, list(all_threads.values()))
    if args.command == "list":
        chosen = [thread for thread in all_threads.values() if args.all or needs_attention(thread)]
        if args.unplanned:
            chosen = cycle.needs_planning(chosen, cycle.state())
            for edit in cycle.direct_edits(cycle.state().plan_updated_at):
                print(f"── direct edit {edit['commit']} by {edit['author']} ({edit['date']}): {edit['subject']}\n"
                      f"   files: {', '.join(edit['files'])}\n")
        if args.json:
            print(json.dumps([thread.to_dict() for thread in chosen], indent=1, ensure_ascii=False))
            return 0
        sources = page_sources()
        print(f"{len(chosen)} of {len(all_threads)} threads {'(all)' if args.all else 'need attention'}\n")
        for thread in sorted(chosen, key=lambda item: (item.page, item.created_at)):
            print(describe(thread, sources) + "\n")
        return 0
    if args.thread_id not in all_threads:
        print(f"unknown thread {args.thread_id}", file=sys.stderr)
        return 1
    if args.command == "apply-suggestion":
        client.take_lease()
        outcome = apply_suggestion(all_threads[args.thread_id])
        return 1 if outcome < 0 else outcome
    if args.command == "show":
        print(describe(all_threads[args.thread_id], page_sources()))
        return 0
    status = args.status
    if status == "page-changed" and not args.commit:
        print("page-changed needs --commit <sha of the commit that rewrote the page>", file=sys.stderr)
        return 1
    client.take_lease()
    if args.command == "reply":
        client.append_event({"type": "reply", "thread_id": args.thread_id, "text": args.text, "author": AUTHOR})
    client.append_event({"type": "status", "thread_id": args.thread_id, "status": status, "note": args.note,
                         "commit": args.commit, "author": AUTHOR})
    print(describe(store.fold(store.load_events(args.events))[args.thread_id], page_sources()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
