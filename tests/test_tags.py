"""Tags on text fragments and pages (feedback/tags.py): storage, the marked status, the server API, kea tags."""
from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from kea.feedback import __main__ as feedback_cli
from kea.feedback import cycle, server, store, tags


def test_vocabulary_defaults_and_overrides():
    known = tags.vocabulary({"tags": [{"name": "abstract", "group": "manuscript", "task": False},
                                      {"name": "explain", "instruction": "In one sentence."}], "free_tags": False})
    by_name = {tag["name"]: tag for tag in known["tags"]}
    assert by_name["abstract"]["task"] is False and by_name["explain"]["instruction"] == "In one sentence."
    assert by_name["explain"]["group"] == "review"                    # an override keeps the other default fields
    assert tags.is_mark(["methods", "abstract"], known) and not tags.is_mark(["methods", "challenge"], known)
    assert not tags.is_mark([], known)
    with pytest.raises(tags.TagError):
        tags.check(["my-own"], known)
    assert tags.check(["Methods", "methods"], tags.vocabulary({})) == ["methods"]
    with pytest.raises(tags.TagError):
        tags.clean(["two words"])


def test_marks_are_not_open_and_turn_open_with_a_task_tag(tmp_path):
    events = tmp_path / "events.jsonl"
    created = store.append_event({"type": "create", "page": "p:a", "quote": "x", "tags": ["methods"], "mark": True,
                                  "author": "ann"}, events)
    thread = store.threads(events)[0]
    assert thread.status == "marked" and thread.text == "" and not cycle.needs_attention(thread)
    store.append_event({"type": "tags", "thread_id": created["thread_id"], "tags": ["methods", "challenge"],
                        "mark": False, "author": "ann"}, events)
    thread = store.threads(events)[0]
    assert thread.status == "open" and thread.tags == ["methods", "challenge"] and cycle.needs_attention(thread)
    store.append_event({"type": "tags", "thread_id": created["thread_id"], "tags": ["methods"], "mark": True,
                        "author": "ann"}, events)
    assert store.threads(events)[0].status == "marked"
    with pytest.raises(store.FeedbackError):          # neither text nor tags
        store.append_event({"type": "create", "page": "p:a", "author": "ann"}, events)


def test_server_takes_tags_checks_them_and_allows_marks_while_frozen(tmp_path):
    site = tmp_path / "site"
    (site / "_feedback").mkdir(parents=True)
    (site / "index.html").write_text("<main>hi</main>")
    (site / "_feedback" / "tags.json").write_text(json.dumps(tags.vocabulary({"free_tags": False})))
    events, log = tmp_path / "events.jsonl", tmp_path / "cycle.jsonl"
    client = TestClient(server.make_app(site, events, "pw-for-tests", log))
    client.post("/login", data={"password": "pw-for-tests", "name": "ann", "next": "/"}, follow_redirects=False)
    listing = client.get("/api/threads?page=p:a").json()
    assert {tag["name"] for tag in listing["tags"]["tags"]} >= {"challenge", "methods"}
    refused = client.post("/api/threads", json={"page": "p:a", "quote": "x", "tags": ["my-own"]})
    assert refused.status_code == 400 and "unknown tag" in refused.json()["error"]
    task = client.post("/api/threads", json={"page": "p:a", "quote": "x", "tags": ["challenge"]}).json()["thread"]
    assert task["status"] == "open"
    cycle.append("frozen", "ann", log)
    mark = client.post("/api/threads", json={"page": "p:a", "quote": "y", "tags": ["results"]})
    assert mark.status_code == 200 and mark.json()["thread"]["status"] == "marked"
    assert client.post("/api/threads", json={"page": "p:a", "text": "a comment"}).status_code == 423
    retag = client.post(f"/api/threads/{mark.json()['thread']['thread_id']}/tags", json={"tags": ["discussion"]})
    assert retag.status_code == 200 and retag.json()["thread"]["tags"] == ["discussion"]
    assert client.post(f"/api/threads/{task['thread_id']}/tags", json={"tags": ["methods"]}).status_code == 423


def test_kea_tags_lists_manuscript_marks(tmp_path, capsys):
    events = tmp_path / "events.jsonl"
    store.append_event({"type": "create", "page": "p:a", "page_title": "A", "quote": "the result", "tags": ["results"],
                        "mark": True, "text": "lead with this", "author": "ann"}, events)
    store.append_event({"type": "create", "page": "p:b", "page_title": "B", "tags": ["explain"], "author": "ann"},
                       events)
    assert feedback_cli.main(["--events", str(events), "tags"]) == 0
    output = capsys.readouterr().out
    assert "## results (1)" in output and "the result" in output and "note: lead with this" in output
    assert "explain" not in output
    assert feedback_cli.main(["--events", str(events), "show", store.threads(events)[1].thread_id]) == 0
    assert "TAG explain [task]" in capsys.readouterr().out
