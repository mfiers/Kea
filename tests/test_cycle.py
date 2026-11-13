"""Tests for the review cycle (src/feedback/cycle.py, server endpoints, CLI watch)."""
import time

import pytest
from starlette.testclient import TestClient

from kea.feedback import __main__ as cli
from kea.feedback import cycle, server, store


def test_transitions_and_cycle_numbers(tmp_path):
    log = tmp_path / "cycle.jsonl"
    assert cycle.state(log).state == "collecting" and cycle.state(log).cycle == 1
    with pytest.raises(store.FeedbackError):
        cycle.append("released", "claude", log, run="r", commit="c")      # not implementing
    with pytest.raises(store.FeedbackError):
        cycle.append("implement-requested", "Mark", log)                  # harvest first
    with pytest.raises(store.FeedbackError):
        cycle.append("frozen", "Mark", log)                               # the old Freeze is gone
    cycle.append("harvest-requested", "Mark", log)
    assert cycle.state(log).state == "harvest-requested" and not cycle.state(log).frozen
    cycle.append("cancelled", "Mark", log)
    assert cycle.state(log).state == "collecting"                         # cancel returns to where it was
    cycle.append("harvest-requested", "Mark", log)
    requested = cycle.state(log).since
    cycle.append("plan-updated", "claude", log)
    harvested = cycle.state(log)
    assert harvested.state == "harvested" and harvested.harvested_until == requested   # covers up to the request
    cycle.append("harvest-requested", "Mark", log)                        # harvest again
    cycle.append("plan-updated", "claude", log)
    cycle.append("implement-requested", "Mark", log)
    assert cycle.state(log).frozen
    cycle.append("cancelled", "Mark", log)
    assert cycle.state(log).state == "harvested"                          # cancel returns to harvested
    cycle.append("implement-requested", "Mark", log)
    cycle.append("implementing", "claude", log)
    with pytest.raises(store.FeedbackError):
        cycle.append("released", "claude", log)                           # needs run and commit
    released = cycle.append("released", "claude", log, run="2026-11-05-a", commit="abc1234")
    assert released.cycle == 2 and released.state == "collecting" and not released.plan_updated_at
    assert not released.harvested_until and released.last_release["run"] == "2026-11-05-a"
    lines = log.read_text().splitlines()
    assert len(lines) == 11                                               # append-only, refused events not written


def test_old_logs_replay(tmp_path):
    log = tmp_path / "cycle.jsonl"
    log.write_text('{"type": "implement-requested", "cycle": 1, "at": "t1", "by": "Mark"}\n'
                   '{"type": "cancelled", "cycle": 1, "at": "t2", "by": "Mark"}\n')
    assert cycle.state(log).state == "collecting"                         # requested from collecting: back there
    log.write_text('{"type": "frozen", "cycle": 1, "at": "t1", "by": "Mark"}\n'
                   '{"type": "plan-updated", "cycle": 1, "at": "t2", "by": "claude"}\n')
    assert cycle.state(log).state == "harvested"                          # before 1.18: frozen reads as harvested
    cycle.append("implement-requested", "Mark", log)
    cycle.append("cancelled", "Mark", log)
    assert cycle.state(log).state == "harvested"


def test_accepts_comments_on():
    for state in ("collecting", "harvest-requested", "harvested"):
        assert cycle.CycleState(state=state).accepts_comments_on("p:a")
    assert not cycle.CycleState(state="implementing").accepts_comments_on("plan/cycle-1")
    assert not cycle.CycleState(state="implement-requested").accepts_comments_on("p:a")


def test_needs_planning_counts_activity_after_the_harvest_request(tmp_path):
    events, log = tmp_path / "events.jsonl", tmp_path / "cycle.jsonl"
    store.append_event({"type": "create", "page": "p:a", "text": "first", "author": "Mark"}, events)
    assert len(cycle.needs_planning(store.threads(events), cycle.state(log))) == 1
    time.sleep(1.1)                                                       # timestamps have one-second resolution
    cycle.append("harvest-requested", "Mark", log)
    time.sleep(1.1)
    store.append_event({"type": "create", "page": "p:b", "text": "during", "author": "Mark"}, events)
    cycle.append("plan-updated", "claude", log)                           # Claude may not have seen "during"
    assert [thread.text for thread in cycle.needs_planning(store.threads(events), cycle.state(log))] == ["during"]
    during = [thread for thread in store.threads(events) if thread.text == "during"][0]
    time.sleep(1.1)
    store.append_event({"type": "status", "thread_id": during.thread_id, "status": "planned", "author": "claude"}, events)
    assert cycle.needs_planning(store.threads(events), cycle.state(log)) == []     # Claude took it in after all


def test_server_harvest_implement_and_status(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "_build.json").write_text('{"build_id": "b1"}')
    events, log = tmp_path / "events.jsonl", tmp_path / "cycle.jsonl"
    client = TestClient(server.make_app(site, events, "pw-for-tests", log, tmp_path / "heartbeat.json"))
    client.post("/login", data={"password": "pw-for-tests", "name": "Mark", "next": "/"}, follow_redirects=False)
    created = client.post("/api/threads", json={"page": "p:a", "text": "hello"})
    assert created.status_code == 200
    status = client.get("/api/status").json()
    assert status["build"]["build_id"] == "b1" and status["open"] == 1 and status["unplanned"] == 1
    assert client.post("/api/cycle/implement").status_code == 409                 # no harvest yet
    assert client.post("/api/cycle/freeze").status_code == 409                    # gone since 1.18
    time.sleep(1.1)                                                               # one-second timestamps
    assert client.post("/api/cycle/harvest").status_code == 200
    assert client.get("/api/status").json()["cycle"]["state"] == "harvest-requested"
    time.sleep(1.1)
    assert client.post("/api/threads", json={"page": "p:a", "text": "more"}).status_code == 200   # still open
    cycle.append("plan-updated", "claude", log)
    time.sleep(1.1)
    late = client.post("/api/threads", json={"page": "p:b", "text": "after the harvest"})
    assert late.status_code == 200
    status = client.get("/api/status").json()
    assert status["cycle"]["state"] == "harvested" and status["unplanned"] == 2   # made during and after the harvest
    assert client.post("/api/cycle/implement").status_code == 200                 # left-over comments do not block
    thread_id = created.json()["thread"]["thread_id"]
    assert client.post("/api/threads", json={"page": "p:a", "text": "x"}).status_code == 423
    assert client.post(f"/api/threads/{thread_id}/reply", json={"text": "x"}).status_code == 423
    assert client.post("/api/cycle/cancel").status_code == 200
    assert client.get("/api/status").json()["cycle"]["state"] == "harvested"
    assert client.post("/api/threads", json={"page": "p:a", "text": "more"}).status_code == 200
    assert client.post("/api/cycle/frobnicate").status_code == 409


def test_watch_wakes_only_on_harvest_or_implement(tmp_path, capsys):
    events, log = tmp_path / "events.jsonl", tmp_path / "cycle.jsonl"
    common = ["--events", str(events), "watch", "--interval", "0.05", "--no-heartbeat", "--cycle-log", str(log)]
    assert cli.main(common + ["--deadline", str(time.time() - 1)]) == 30
    store.append_event({"type": "create", "page": "p:a", "text": "x", "author": "Mark"}, events)
    assert cli.main(common + ["--deadline", str(time.time() + 0.5)]) == 30       # a comment alone: no wake-up
    cycle.append("harvest-requested", "Mark", log)
    assert cli.main(common + ["--deadline", str(time.time() + 5)]) == 10
    assert "harvest requested by Mark" in capsys.readouterr().out
    cycle.append("plan-updated", "claude", log)
    assert cli.main(common + ["--deadline", str(time.time() + 0.5)]) == 30       # harvested: waits again
    cycle.append("implement-requested", "Mark", log)
    assert cli.main(common + ["--deadline", str(time.time() + 5)]) == 20


def test_release_arguments_are_checked(monkeypatch):
    import argparse
    from kea.docsite import versions
    monkeypatch.setattr(versions, "releases", lambda experiment="": [versions.Release(
        tag="v0.2.0", version="0.2.0", experiment="", commit="abc", date="")])
    def args(**kw):
        base = dict(run="r", commit="c", version="0.3.0", kind="minor", reason="why", experiment=[])
        base.update(kw)
        return argparse.Namespace(**base)
    assert cli.check_release(args()) == ""
    assert "next version" in cli.check_release(args(version="0.5.0"))
    assert "gives 0.2.1" in cli.check_release(args(version="0.3.0", kind="patch"))
    assert cli.check_release(args(version="0.3.0", kind="major")) == ""          # before 1.0 major -> minor
    assert "--version" in cli.check_release(args(version="", kind="minor"))
    assert "NAME=X.Y.Z" in cli.check_release(args(experiment=["x"]))


def test_suggested_edit_is_stored_as_thread_and_merges(tmp_path, monkeypatch):
    import json as json_module
    project = tmp_path / "project"
    (project / "doc" / "x" / "result").mkdir(parents=True)
    page_file = project / "doc" / "x" / "result" / "r-a.md"
    page_file.write_text("---\nid: r-a\n---\nline one\nline two\nkeep\nkeep\nkeep\nline three\n")
    site = tmp_path / "site"
    site.mkdir()
    (site / "_sources.json").write_text(json_module.dumps({"x:r-a": "doc/x/result/r-a.md"}))
    monkeypatch.setattr(server, "PROJECT", project)
    events, log = tmp_path / "events.jsonl", tmp_path / "cycle.jsonl"
    client = TestClient(server.make_app(site, events, "pw-for-tests", log, tmp_path / "heartbeat.json"))
    client.post("/login", data={"password": "pw-for-tests", "name": "Mark", "next": "/"}, follow_redirects=False)
    assert client.get("/api/source?page=x:r-a").json()["text"].endswith("line three\n")
    assert client.get("/api/source?page=x:other").status_code == 404
    new_text = page_file.read_text().replace("line two", "line 2")
    assert client.post("/api/suggest", json={"page": "x:r-a", "new_text": page_file.read_text()}).status_code == 400
    created = client.post("/api/suggest", json={"page": "x:r-a", "text": "shorter", "new_text": new_text})
    assert created.status_code == 200
    thread = created.json()["thread"]
    assert "-line two" in thread["suggestion"]["diff"] and "+line 2" in thread["suggestion"]["diff"]
    assert page_file.read_text().count("line two") == 1                       # the server never writes the file
    page_file.write_text(page_file.read_text().replace("line three", "line 3"))  # meanwhile another change
    monkeypatch.setattr(cli, "PROJECT", project)
    assert cli.apply_suggestion(store.fold(store.load_events(events))[thread["thread_id"]]) == 0
    assert page_file.read_text().endswith("line one\nline 2\nkeep\nkeep\nkeep\nline 3\n")   # both changes kept
    cycle.append("harvest-requested", "Mark", log)
    cycle.append("plan-updated", "claude", log)
    cycle.append("implement-requested", "Mark", log)
    assert client.post("/api/suggest", json={"page": "x:r-a", "new_text": "other"}).status_code == 423


def test_deadline_accepts_durations_and_dates():
    assert cli.parse_deadline("3d", now=1000.0) == 1000.0 + 3 * 86400
    assert cli.parse_deadline("90m", now=0.0) == 5400.0
    assert cli.parse_deadline("1762000000") == 1762000000.0
    assert abs(cli.parse_deadline("2026-11-09T18:00") - __import__("datetime").datetime(2026, 11, 9, 18).timestamp()) < 1
    with __import__("pytest").raises(Exception):
        cli.parse_deadline("soon")


def test_watch_reports_and_status(tmp_path, capsys, monkeypatch):
    events, log = tmp_path / "events.jsonl", tmp_path / "cycle.jsonl"
    monkeypatch.setattr(cycle, "heartbeat_path", lambda: tmp_path / "heartbeat.json")
    assert cli.main(["--events", str(events), "watch", "--status"]) == 1          # no watcher yet
    assert cli.main(["--events", str(events), "watch", "--interval", "0.05", "--slow-interval", "0.05", "--report-every", "0", "--cycle-log",
                     str(log), "--deadline", str(time.time() + 0.2)]) == 30
    out = capsys.readouterr().out
    assert "watching:" in out and "deadline reached" in out                      # a status line, then the end
    info = cycle.read_heartbeat_info()
    assert info["pid"] and info["deadline"] and info["state"] == "collecting"
    assert info["exit"] == "deadline"                                            # the last heartbeat says why



def test_watcher_status_reads_the_silence():
    """watching / working / ended / gone from the heartbeat alone; a crash sends nothing, so gone is inferred."""
    import datetime as dt
    now = 1_800_000_000.0
    at = lambda seconds_ago: dt.datetime.fromtimestamp(now - seconds_ago, dt.timezone.utc).isoformat()
    later = now + 3600
    status = lambda info: cycle.watcher_status(info, now)
    assert status({})["state"] == "none"
    assert status({"at": at(30), "deadline": later})["state"] == "watching"
    gone = status({"at": at(600), "deadline": later})
    assert gone["state"] == "gone" and gone["seconds"] == 600 and "10 min" in gone["text"]
    assert status({"at": at(600), "deadline": later, "slow_interval": 300})["state"] == "watching"   # a slow watcher
    assert status({"at": at(600), "deadline": later, "exit": "implementing"})["state"] == "working"
    assert status({"at": at(5 * 3600), "deadline": now + 9 * 3600, "exit": "implementing"})["state"] == "gone"
    assert status({"at": at(40 * 60), "deadline": later, "exit": "planning"})["state"] == "gone"
    assert status({"at": at(600), "deadline": now - 1})["state"] == "ended"                       # deadline passed
    assert status({"at": at(5), "deadline": later, "exit": "deadline"})["state"] == "ended"


def test_status_names_the_reader_and_logout_forgets_the_password(tmp_path):
    """The menu bar's reader slot: /api/status says who is signed in and where to sign out; /logout drops the
    password (and steering) cookies and leads back to the login."""
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<main>hi</main>")
    client = TestClient(server.make_app(site, tmp_path / "events.jsonl", "pw-for-tests", tmp_path / "cycle.jsonl",
                                        tmp_path / "heartbeat.json"))
    client.post("/login", data={"password": "pw-for-tests", "name": "Ann", "next": "/"}, follow_redirects=False)
    status = client.get("/api/status").json()
    assert status["signed_in"] is True and status["account"] is False and status["sign_out"] == "/logout"
    assert status["you"] == "Ann"
    out = client.get("/logout", follow_redirects=False)
    assert out.status_code == 303 and out.headers["location"] == "/login"
    assert client.get("/api/status").status_code == 401                      # signed out


def test_approve_and_go_needs_steering_wakes_the_watcher_and_reports_progress(tmp_path, capsys):
    """Approve & go: the server asks for the iteration password, the status lists the request, kea watch stops with
    exit 40, and kea progress puts the agent's words in the status (watcher.doing)."""
    site = tmp_path / "site"
    site.mkdir()
    events, log, heartbeat = tmp_path / "events.jsonl", tmp_path / "cycle.jsonl", tmp_path / "heartbeat.json"
    client = TestClient(server.make_app(site, events, "pw-for-tests", log, heartbeat, steer_password="steer-pw"))
    client.post("/login", data={"password": "pw-for-tests", "name": "Ann", "next": "/"}, follow_redirects=False)
    body = {"page": "p:s-a", "page_title": "S1 Run", "page_version": "v7", "text": "Approve & run the step", "tags": ["go"]}
    refused = client.post("/api/threads", json=body)
    assert refused.status_code == 403 and refused.json()["need_steer"]
    signed = client.post("/api/threads", json={**body, "text": "", "tags": ["approve"]})   # a plain sign-off: no steering
    assert signed.status_code == 200 and signed.json()["thread"]["page_version"] == "v7"
    assert client.post("/api/steer", json={"password": "steer-pw"}).status_code == 200
    assert client.post("/api/threads", json=body).status_code == 200
    status = client.get("/api/status").json()
    assert [item["text"] for item in status["goes"]] == ["Approve & run the step"] and status["signing"] == ["p:s-a"]
    common = ["--events", str(events), "watch", "--interval", "0.05", "--no-heartbeat", "--cycle-log", str(log)]
    assert cli.main(common + ["--deadline", str(time.time() + 5)]) == 40
    assert "approve & go: 1 request(s)" in capsys.readouterr().out
    cycle.write_heartbeat(heartbeat, {"exit": "going", "doing": "running S1: 3 of 8 donors", "page": "p:s-a"})
    watcher = client.get("/api/status").json()["watcher"]
    assert watcher["state"] == "working" and watcher["doing"] == "running S1: 3 of 8 donors" and watcher["page"] == "p:s-a"
    thread = store.threads(events)[-1]
    store.append_event({"type": "status", "thread_id": thread.thread_id, "status": "page-changed", "commit": "abc1234",
                        "author": "claude"}, events)
    assert client.get("/api/status").json()["goes"] == []                     # answered: no longer open
    assert cli.main(common + ["--deadline", str(time.time() + 0.3)]) == 30
