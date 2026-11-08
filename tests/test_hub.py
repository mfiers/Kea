"""Tests for the Kea hub (feedback/hub.py), the remote backend, kea publish and the one-agent lease."""
import hashlib
import io
import json
import socket
import tarfile
import threading
import time

import pytest
from starlette.testclient import TestClient

from kea.feedback import agent, backend, cycle, hub, publish, store


def make_bundle(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


SITE = {"site/index.html": "<html><body>home</body></html>",
        "site/_sources.json": json.dumps({"x:r-a": "doc/x/result/r-a.md"}),
        "site/_files.json": json.dumps(["data/small.tsv"]),
        "doc/x/result/r-a.md": "---\nid: r-a\n---\nline one\n",
        "files/data/small.tsv": "a\tb\n1\t2\n",
        "meta.json": json.dumps({"files": ["data/small.tsv"], "source_commits": {"doc/x/result/r-a.md": "abc1234"},
                                 "states": {"labels": {}, "items": {}}})}


@pytest.fixture
def demo(tmp_path):
    the_hub = hub.Hub(tmp_path / "hub")
    the_hub.init("https://kea.example.org")
    secrets = the_hub.add("demo", "Demo project")
    return the_hub, secrets


def agent_headers(key: str, name: str = "agent-a") -> dict:
    return {"Authorization": f"Bearer {key}", "X-Kea-Agent": name}


def test_hub_stores_no_clear_text_secrets(demo):
    the_hub, secrets = demo
    stored = (the_hub.project_dir("demo") / "project.json").read_text()
    for value in secrets.values():
        assert value not in stored
    with pytest.raises(ValueError):
        the_hub.project_dir("../etc")


def test_agent_api_lease_publish_and_events(demo):
    the_hub, secrets = demo
    client = TestClient(hub.HubApp(the_hub), base_url="https://testserver")
    key = secrets["key"]
    assert client.get("/p/demo/hub/lease", headers=agent_headers("wrong")).status_code == 401
    assert client.post("/p/demo/hub/lease", headers=agent_headers(key), json={"host": "h"}).status_code == 200
    refused = client.post("/p/demo/hub/lease", headers=agent_headers(key, "agent-b"), json={"host": "h2"})
    assert refused.status_code == 409 and refused.json()["holder"]["agent"] == "agent-a"
    archive = make_bundle(SITE)
    sha = hashlib.sha256(archive).hexdigest()
    assert client.post("/p/demo/hub/publish", content=archive,
                       headers={**agent_headers(key, "agent-b"), "X-Kea-Sha256": sha}).status_code == 409
    assert client.post("/p/demo/hub/publish", content=archive,
                       headers={**agent_headers(key), "X-Kea-Sha256": "0" * 64}).status_code == 400
    published = client.post("/p/demo/hub/publish", content=archive, headers={**agent_headers(key), "X-Kea-Sha256": sha})
    assert published.status_code == 200, published.text
    # readers: the site password makes a commenter
    assert client.get("/p/demo/", follow_redirects=False).headers["location"].startswith("/p/demo/login")
    login = client.post("/p/demo/login", data={"password": secrets["site_password"], "name": "Ann", "next": "/"},
                        follow_redirects=False)
    assert login.status_code == 303 and login.headers["location"] == "/p/demo/"
    assert "home" in client.get("/p/demo/").text
    assert client.get("/p/demo/api/source?page=x:r-a").json()["commit"] == "abc1234"
    assert client.get("/p/demo/files/data/small.tsv").text.startswith("a\tb")
    assert client.get("/p/demo/files/data/other.tsv").status_code == 404
    created = client.post("/p/demo/api/threads", json={"page": "x:r-a", "text": "why?"})
    assert created.status_code == 200
    thread_id = created.json()["thread"]["thread_id"]
    # cycle actions need the iteration password
    assert client.post("/p/demo/api/cycle/freeze").json()["need_steer"] is True
    assert client.post("/p/demo/api/steer", json={"password": "nope"}).status_code == 403
    assert client.post("/p/demo/api/steer", json={"password": secrets["iteration_password"]}).status_code == 200
    assert client.post("/p/demo/api/cycle/freeze").status_code == 200
    # the agent replies through the API, written as claude; readers cannot pose as claude
    reply = client.post("/p/demo/hub/events", headers=agent_headers(key),
                        json={"log": "events", "event": {"type": "reply", "thread_id": thread_id, "text": "because",
                                                         "author": "someone"}})
    assert reply.json()["event"]["author"] == "claude"
    assert client.post("/p/demo/hub/events", headers=agent_headers(key),
                       json={"log": "cycle", "kind": "frozen", "fields": {}}).status_code == 400
    log = client.get("/p/demo/hub/log", headers=agent_headers(key)).json()
    assert log["events"]["mode"] == "append" and "because" in log["events"]["text"]   # from byte 0
    # another project on the same hub knows nothing of this one
    other = the_hub.add("other")
    assert client.get("/p/other/hub/lease", headers=agent_headers(key)).status_code == 401
    assert client.get("/p/other/hub/lease", headers=agent_headers(other["key"])).json()["lease"] == {}
    assert client.get("/p/nothere/").status_code == 404


def test_bundle_with_unsafe_paths_is_refused(demo):
    the_hub, _ = demo
    with pytest.raises(ValueError):
        hub.install_release(the_hub, "demo", make_bundle({"../escape.txt": "x", **SITE}))
    with pytest.raises(ValueError):
        hub.install_release(the_hub, "demo", make_bundle({"site/x.html": "no index or meta"}))


def test_log_part_returns_only_what_is_new(tmp_path):
    path = tmp_path / "log.jsonl"
    path.write_bytes(b'{"a":1}\n{"b":2}\n')
    first = b'{"a":1}\n'
    assert hub.log_part(path, len(first), hashlib.sha256(first).hexdigest()) == \
        {"mode": "append", "text": '{"b":2}\n', "size": 16}
    assert hub.log_part(path, 16, hashlib.sha256(path.read_bytes()).hexdigest())["mode"] == "same"
    assert hub.log_part(path, 8, hashlib.sha256(b"different").hexdigest())["mode"] == "full"


@pytest.fixture
def live_hub(demo):
    import uvicorn
    the_hub, secrets = demo
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = uvicorn.Config(hub.HubApp(the_hub), host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield the_hub, secrets, f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def test_remote_backend_mirrors_the_hub_and_keeps_one_agent(live_hub, tmp_path, monkeypatch):
    the_hub, secrets, url = live_hub
    local = tmp_path / "project" / "feedback"
    local.mkdir(parents=True)
    events, log = local / "events.jsonl", local / "cycle.jsonl"
    store.append_event({"type": "create", "page": "x:r-a", "text": "old comment", "author": "Ann"}, events)
    monkeypatch.setenv("KEA_AGENT_ID", "agent-a")
    remote = backend.Remote(url, "demo", secrets["key"], events, log)
    remote.take_lease()
    with pytest.raises(backend.RemoteError):                  # the hub is empty: never truncate the local log
        remote.sync()
    assert "old comment" in events.read_text()
    remote.seed()
    remote.sync()
    thread_id = next(iter(store.fold(store.load_events(events))))
    remote.append_event({"type": "reply", "thread_id": thread_id, "text": "answered", "author": "claude"})
    assert store.fold(store.load_events(events))[thread_id].replies[-1].text == "answered"
    hub_events = (the_hub.feedback("demo") / "events.jsonl").read_bytes()
    assert events.read_bytes() == hub_events                  # an exact mirror
    remote.append_cycle("plan-updated", "claude", run="r1")
    assert cycle.state(log).plan_updated_at
    monkeypatch.setenv("KEA_AGENT_ID", "agent-b")
    second = backend.Remote(url, "demo", secrets["key"], events, log)
    with pytest.raises(agent.LeaseHeld):
        second.take_lease()
    with pytest.raises(agent.LeaseHeld):
        second.append_event({"type": "reply", "thread_id": thread_id, "text": "me too", "author": "claude"})
    assert second.take_lease(force=True)["took_over_from"] == "agent-a"


def test_remote_needs_https_except_localhost():
    with pytest.raises(backend.RemoteError):
        backend.check_url("http://kea.example.org")
    assert backend.check_url("https://kea.example.org/") == "https://kea.example.org"
    assert backend.check_url("http://127.0.0.1:8300")


def test_local_lease_one_agent(tmp_path, monkeypatch):
    path = tmp_path / "agent_lease.json"
    monkeypatch.setenv("KEA_AGENT_ID", "agent-a")
    agent.take_local(path)
    agent.take_local(path)                                    # renewing is fine
    monkeypatch.setenv("KEA_AGENT_ID", "agent-b")
    with pytest.raises(agent.LeaseHeld) as held:
        agent.take_local(path)
    assert "Only one agent" in str(held.value)
    holder = json.loads(path.read_text())
    holder["renewed_at"] = "2000-01-01T00:00:00Z"            # expired
    path.write_text(json.dumps(holder))
    assert agent.take_local(path)["agent"] == "agent-b"


def test_publish_keeps_links_and_previews_only_for_uploaded_files(tmp_path):
    page = ("<a href='../files/data/a.tsv' download>download</a> <span class='help'>(needs the site server)</span>"
            "<div class='not-annotatable kea-preview' data-file='data/a.tsv'><table><tr><td>donor1</td></tr></table>"
            "</div><!--/kea-preview--><a href='../files/data/b.tsv' download>download</a>"
            "<div class='not-annotatable kea-preview' data-file='data/b.tsv'><div>ok</div></div><!--/kea-preview-->")
    out = publish.rewrite_html(page, {"data/b.tsv"})
    assert "data/a.tsv" not in out and "donor1" not in out and "not on this server" in out
    assert "files/data/b.tsv" in out and "<div>ok</div>" in out


def test_upload_decision_flags_identifiers(tmp_path, monkeypatch):
    monkeypatch.setattr(publish, "PROJECT_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "summary.tsv").write_text("stage\tmean\n1\t0.2\n")
    (tmp_path / "data" / "donors.tsv").write_text("donor_id\tbraak\nD1\t3\n")
    (tmp_path / "data" / "big.tsv").write_text("x\n" + "1\n" * 100000)
    (tmp_path / "data" / "cells.parquet").write_bytes(b"PAR1")
    rows = {row["path"]: row for row in publish.decide(
        ["data/summary.tsv", "data/donors.tsv", "data/big.tsv", "data/cells.parquet"], {"upload_max_kb": 100})}
    assert rows["data/summary.tsv"]["upload"]
    assert not rows["data/donors.tsv"]["upload"] and "identifiers" in rows["data/donors.tsv"]["reason"]
    assert not rows["data/big.tsv"]["upload"]
    assert not rows["data/cells.parquet"]["upload"]
    rows = {row["path"]: row for row in publish.decide(["data/donors.tsv"], {"upload_include": ["data/donors.tsv"]})}
    assert rows["data/donors.tsv"]["upload"]                  # the owner named it explicitly
    assert publish.decide(["data/summary.tsv"], {})[0]["upload"] is False          # default: nothing goes up


def test_remote_lease_of_an_ended_session_on_this_host_is_taken_over(live_hub, tmp_path, monkeypatch):
    the_hub, secrets, url = live_hub
    events, log = tmp_path / "events.jsonl", tmp_path / "cycle.jsonl"
    holder = {"agent": "old-session", "host": socket.gethostname(), "pid": 2 ** 22 + 12345, "path": "x",
              "since": agent.now_iso(), "renewed_at": agent.now_iso(), "ttl": agent.TTL}
    (the_hub.feedback("demo") / "lease.json").write_text(json.dumps(holder))
    monkeypatch.setenv("KEA_AGENT_ID", "new-session")
    lease = backend.Remote(url, "demo", secrets["key"], events, log).take_lease()
    assert lease["agent"] == "new-session" and lease["took_over_from"] == "old-session"
    holder["host"] = "another-machine"
    (the_hub.feedback("demo") / "lease.json").write_text(json.dumps(holder))
    monkeypatch.setenv("KEA_AGENT_ID", "third-session")
    with pytest.raises(agent.LeaseHeld):                      # elsewhere: no way to know, so refused
        backend.Remote(url, "demo", secrets["key"], events, log).take_lease()


UID_A, UID_B = "a" * 26, "b" * 26


def site_with_ids(version: str, text: str, uid: str = UID_A) -> dict:
    files = dict(SITE)
    files["site/_ids.json"] = json.dumps({uid: {"key": "x:r-a", "url": "x/r-a.html", "type": "result", "number": "R1",
                                                "title": "A result", "short": "S.", "status": "done", "version": version,
                                                "source": "doc/x/result/r-a.md"}})
    files["doc/x/result/r-a.md"] = text
    return files


def publish_files(client, key: str, files: dict, project: str = "demo"):
    archive = make_bundle(files)
    return client.post(f"/p/{project}/hub/publish", content=archive,
                       headers={**agent_headers(key), "X-Kea-Sha256": hashlib.sha256(archive).hexdigest()})


def test_ids_are_unique_across_projects_and_versions_are_kept(demo):
    the_hub, secrets = demo
    other = the_hub.add("other")
    client = TestClient(hub.HubApp(the_hub), base_url="https://testserver")
    first = publish_files(client, secrets["key"], site_with_ids("v" * 20, "---\nid: r-a\n---\nfirst text\n"))
    assert first.status_code == 200 and first.json()["versions_stored"] == 1
    assert publish_files(client, secrets["key"], site_with_ids("w" * 20, "---\nid: r-a\n---\nsecond text\n")).status_code == 200
    stored = the_hub.versions_dir("demo") / UID_A
    assert sorted(path.name for path in stored.glob("*.md")) == ["v" * 20 + ".md", "w" * 20 + ".md"]
    assert "first text" in (stored / ("v" * 20 + ".md")).read_text()
    taken = publish_files(client, other["key"], site_with_ids("v" * 20, "---\nid: r-a\n---\ncopy\n"), project="other")
    assert taken.status_code >= 400 and "belong to another project" in taken.text
    # the apex resolver: readers are sent to the project's site; a project's agent gets the facts
    assert client.get(f"/id/{UID_A}", follow_redirects=False).headers["location"] == \
        f"https://kea.example.org/p/demo/id/{UID_A}"
    facts = client.get(f"/id/{UID_A}.json", headers=agent_headers(other["key"])).json()
    assert facts["project"] == "demo" and facts["version"] == "w" * 20
    assert client.get(f"/id/{UID_B}").status_code == 404
    # on the project site (after login): the current version redirects, an earlier one is shown from the store
    client.post("/p/demo/login", data={"password": secrets["site_password"], "name": "Ann", "next": "/"})
    assert client.get(f"/p/demo/id/{UID_A}@{'w' * 20}", follow_redirects=False).headers["location"].endswith("/x/r-a.html")
    earlier = client.get(f"/p/demo/id/{UID_A}@{'v' * 20}")
    assert earlier.status_code == 200 and "first text" in earlier.text and "not the current text" in earlier.text


def test_subdomains_reserved_names_and_redirects(demo):
    the_hub, secrets = demo
    import yaml
    settings = the_hub.settings()
    settings["project_domain"] = "keahub.example"
    (the_hub.folder / "hub.yaml").write_text(yaml.safe_dump(settings))
    for bad in ("www", "id", "demo-", "xn--abc"):
        with pytest.raises(SystemExit):
            the_hub.add(bad)
    client = TestClient(hub.HubApp(the_hub), base_url="https://keahub.example")
    publish_files(client, secrets["key"], site_with_ids("v" * 20, "---\nid: r-a\n---\ntext\n"))   # the API stays on the apex
    moved = client.get("/p/demo/x/r-a.html?a=1", follow_redirects=False)
    assert moved.status_code == 308 and moved.headers["location"] == "https://demo.keahub.example/x/r-a.html?a=1"
    sub = TestClient(hub.HubApp(the_hub), base_url="https://demo.keahub.example")
    assert sub.get("/", follow_redirects=False).headers["location"].startswith("/login")       # root path, own login
    login = sub.post("/login", data={"password": secrets["site_password"], "name": "Ann", "next": "/"}, follow_redirects=False)
    assert login.status_code == 303 and sub.get("/").status_code == 200
    assert TestClient(hub.HubApp(the_hub), base_url="https://nope.keahub.example").get("/").status_code == 404
    assert client.get(f"/id/{UID_A}", follow_redirects=False).headers["location"] == f"https://demo.keahub.example/id/{UID_A}"
