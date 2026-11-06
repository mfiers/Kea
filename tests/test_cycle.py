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
        cycle.append("implement-requested", "Mark", log)                  # must freeze first
    cycle.append("plan-updated", "claude", log)
    assert cycle.state(log).plan_updated_at
    cycle.append("frozen", "Mark", log)
    assert cycle.state(log).frozen and cycle.state(log).state == "frozen"
    cycle.append("unfrozen", "Mark", log)
    assert cycle.state(log).state == "collecting"
    cycle.append("frozen", "Mark", log)
    cycle.append("plan-updated", "claude", log)                           # plan comments folded while frozen
    cycle.append("implement-requested", "Mark", log)
    cycle.append("cancelled", "Mark", log)
    assert cycle.state(log).state == "frozen"                             # cancel returns to frozen
    cycle.append("implement-requested", "Mark", log)
    cycle.append("implementing", "claude", log)
    with pytest.raises(store.FeedbackError):
        cycle.append("released", "claude", log)                           # needs run and commit
    released = cycle.append("released", "claude", log, run="2026-11-05-a", commit="abc1234")
    assert released.cycle == 2 and released.state == "collecting" and not released.plan_updated_at
    assert released.last_release["run"] == "2026-11-05-a"
    lines = log.read_text().splitlines()
    assert len(lines) == 10                                               # append-only, refused events not written


def test_old_logs_replay(tmp_path):
    log = tmp_path / "cycle.jsonl"
    log.write_text('{"type": "implement-requested", "cycle": 1, "at": "t1", "by": "Mark"}\n'
                   '{"type": "cancelled", "cycle": 1, "at": "t2", "by": "Mark"}\n')
    assert cycle.state(log).state == "collecting"                         # requested from collecting: back there


def test_accepts_comments_on():
    state = cycle.CycleState(state="frozen")
    assert state.accepts_comments_on("plan/cycle-1") and not state.accepts_comments_on("p:a")
    assert cycle.CycleState().accepts_comments_on("p:a")
    assert not cycle.CycleState(state="implementing").accepts_comments_on("plan/cycle-1")


def test_needs_planning_uses_activity_after_plan_update(tmp_path):
    events, log = tmp_path / "events.jsonl", tmp_path / "cycle.jsonl"
    store.append_event({"type": "create", "page": "p:a", "text": "first", "author": "Mark"}, events)
    assert len(cycle.needs_planning(store.threads(events), cycle.state(log))) == 1
    time.sleep(1.1)                                                       # timestamps have one-second resolution
    cycle.append("plan-updated", "claude", log)
    assert cycle.needs_planning(store.threads(events), cycle.state(log)) == []
    time.sleep(1.1)
    store.append_event({"type": "create", "page": "p:b", "text": "second", "author": "Mark"}, events)
    assert [thread.text for thread in cycle.needs_planning(store.threads(events), cycle.state(log))] == ["second"]


def test_server_freezes_comments_and_reports_status(tmp_path):
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
    assert client.post("/api/cycle/implement").status_code == 409                 # not frozen yet
    assert client.post("/api/cycle/freeze").status_code == 200
    assert client.get("/api/status").json()["cycle"]["frozen"] is True
    assert client.post("/api/threads", json={"page": "p:a", "text": "more"}).status_code == 423
    thread_id = created.json()["thread"]["thread_id"]
    assert client.post(f"/api/threads/{thread_id}/reply", json={"text": "x"}).status_code == 423
    assert client.post("/api/threads", json={"page": "plan/cycle-1", "text": "on the plan"}).status_code == 200
    refused = client.post("/api/cycle/implement")
    assert refused.status_code == 409 and "not in the plan" in refused.json()["error"]   # 2 comments unplanned
    cycle.append("plan-updated", "claude", log)
    time.sleep(1.1)
    assert client.post("/api/cycle/implement").status_code == 200
    assert client.post("/api/threads", json={"page": "plan/cycle-1", "text": "late"}).status_code == 423
    assert client.post("/api/cycle/cancel").status_code == 200
    assert client.get("/api/status").json()["cycle"]["state"] == "frozen"
    assert client.post("/api/cycle/unfreeze").status_code == 200
    assert client.post("/api/threads", json={"page": "p:a", "text": "more"}).status_code == 200
    assert client.post("/api/cycle/frobnicate").status_code == 409


def test_watch_exit_codes(tmp_path, capsys):
    events, log = tmp_path / "events.jsonl", tmp_path / "cycle.jsonl"
    common = ["--events", str(events), "watch", "--interval", "0.05", "--no-heartbeat", "--cycle-log", str(log), "--settle", "0"]
    assert cli.main(common + ["--deadline", str(time.time() - 1)]) == 30
    store.append_event({"type": "create", "page": "p:a", "text": "x", "author": "Mark"}, events)
    assert cli.main(common + ["--deadline", str(time.time() + 5)]) == 10
    cycle.append("frozen", "Mark", log)
    cycle.append("implement-requested", "Mark", log)
    assert cli.main(common + ["--deadline", str(time.time() + 5)]) == 20


def test_watch_waits_for_a_burst_to_settle(tmp_path):
    events, log = tmp_path / "events.jsonl", tmp_path / "cycle.jsonl"
    store.append_event({"type": "create", "page": "p:a", "text": "x", "author": "Mark"}, events)
    common = ["--events", str(events), "watch", "--interval", "0.05", "--no-heartbeat", "--cycle-log", str(log)]
    assert cli.main(common + ["--settle", "60", "--deadline", str(time.time() + 0.5)]) == 30   # still typing
    assert cli.main(common + ["--settle", "0", "--deadline", str(time.time() + 5)]) == 10
    cycle.append("frozen", "Mark", log)
    cycle.append("implement-requested", "Mark", log)
    assert cli.main(common + ["--settle", "60", "--deadline", str(time.time() + 5)]) == 20   # not delayed


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
    cycle.append("frozen", "Mark", log)
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
