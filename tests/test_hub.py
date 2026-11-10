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
    assert client.post("/p/demo/api/cycle/harvest").json()["need_steer"] is True
    assert client.post("/p/demo/api/steer", json={"password": "nope"}).status_code == 403
    assert client.post("/p/demo/api/steer", json={"password": secrets["iteration_password"]}).status_code == 200
    assert client.post("/p/demo/api/cycle/harvest").status_code == 200
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


def test_orcid_sign_in_approval_roles_and_isolation(demo, monkeypatch):
    """Sign in at the apex with (simulated) ORCID, pending until approved, then a session per project subdomain;
    comments carry the ORCID iD; roles decide steering; writes from another origin are refused."""
    from urllib.parse import parse_qs, urlsplit

    import yaml
    from kea.feedback import accounts
    the_hub, secrets = demo
    settings = the_hub.settings()
    settings.update({"url": "https://keahub.example", "project_domain": "keahub.example"})
    (the_hub.folder / "hub.yaml").write_text(yaml.safe_dump(settings))
    the_hub.add("other")
    monkeypatch.setenv("KEA_ORCID_CLIENT_ID", "APP-TEST")
    monkeypatch.setenv("KEA_ORCID_CLIENT_SECRET", "s3cret")
    orcid = "0000-0002-1825-0097"
    monkeypatch.setattr(accounts, "exchange_code", lambda code, redirect, conf: {"orcid": orcid, "name": "Josiah Carberry"})
    app = hub.HubApp(the_hub)
    apex = TestClient(app, base_url="https://keahub.example")
    site = TestClient(app, base_url="https://demo.keahub.example")
    publish_files(apex, secrets["key"], site_with_ids("v" * 20, "---\nid: r-a\n---\ntext\n"))
    login_page = site.get("/login?next=/x/r-a.html")
    assert "Sign in with ORCID" in login_page.text
    start = apex.get("/auth/login", params={"return": "https://demo.keahub.example/x/r-a.html"}, follow_redirects=False)
    assert start.headers["location"].startswith("https://orcid.org/oauth/authorize?")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    pending = apex.get("/auth/orcid/callback", params={"code": "c1", "state": state}, follow_redirects=False)
    assert pending.status_code == 403 and "approves new readers" in pending.text
    assert accounts.Accounts(the_hub.folder).users()[orcid]["status"] == "pending"
    assert hub.main(["--dir", str(the_hub.folder), "users", "approve", orcid]) == 0      # commenter on all projects
    done = apex.get("/auth/orcid/callback", params={"code": "c2", "state": state}, follow_redirects=False)
    finish = done.headers["location"]
    assert finish.startswith("https://demo.keahub.example/auth/finish?code=") and "__Host-kea_session" in done.headers["set-cookie"]
    path_and_query = finish.split("keahub.example", 1)[1]
    entered = site.get(path_and_query, follow_redirects=False)
    assert entered.status_code == 303 and entered.headers["location"] == "/x/r-a.html"
    assert site.get(path_and_query, follow_redirects=False).status_code == 400            # a code works once
    signed_in = site.get("/api/threads").json()                                             # signed in, no password
    assert signed_in["account"] is True and signed_in["you"] == "Josiah Carberry"           # the panel asks no name
    menu = site.get("/api/status").json()                                                  # the menu bar's reader
    assert menu["signed_in"] and menu["account"] and menu["orcid"] == orcid and menu["sign_out"] == "/auth/logout"
    created = site.post("/api/threads", json={"page": "x:r-a", "text": "A question"}).json()["thread"]
    assert created["author"] == "Josiah Carberry" and created["author_id"] == orcid
    assert site.post("/api/cycle/harvest", json={}).status_code == 403                        # commenter may not steer
    assert hub.main(["--dir", str(the_hub.folder), "users", "role", orcid, "steerer", "--project", "demo"]) == 0
    assert site.post("/api/cycle/harvest", json={}).status_code == 200
    # the demo session does not open the other project; a write from another origin is refused
    other_site = TestClient(app, base_url="https://other.keahub.example")
    other_site.cookies.set(accounts.SITE_COOKIE, site.cookies.get(accounts.SITE_COOKIE))
    assert other_site.get("/api/threads").status_code == 401
    forged = site.post("/api/threads", json={"page": "x:r-a", "text": "x"}, headers={"Origin": "https://other.keahub.example"})
    assert forged.status_code == 403
    # a reader reads the comments but writes nothing (not even a tag); the sign-in itself keeps working
    assert hub.main(["--dir", str(the_hub.folder), "users", "role", orcid, "reader", "--project", "demo"]) == 0
    listed = site.get("/api/threads")
    assert listed.status_code == 200 and listed.json()["can_write"] is False and listed.json()["threads"]
    refused = site.post("/api/threads", json={"page": "x:r-a", "text": "more"})
    assert refused.status_code == 403 and refused.json()["read_only"] is True
    assert site.post("/api/cycle/harvest", json={}).status_code == 403
    assert hub.main(["--dir", str(the_hub.folder), "users", "block", orcid]) == 0
    assert site.get("/api/threads").status_code == 401


def test_serve_log_lines_events_and_requests(demo, caplog):
    """--log events: publishes, leases, refused keys and reader actions; --log requests adds every request; query
    strings (sign-in codes) never reach the log."""
    import logging
    the_hub, secrets = demo
    key = secrets["key"]
    archive = make_bundle(SITE)
    sha = hashlib.sha256(archive).hexdigest()
    caplog.set_level(logging.INFO, logger="kea.hub")
    client = TestClient(hub.HubApp(the_hub, "events"), base_url="https://testserver")
    client.get("/p/demo/hub/lease", headers=agent_headers("wrong"))
    client.post("/p/demo/hub/lease", headers=agent_headers(key), json={"host": "h"})
    client.post("/p/demo/hub/lease", headers=agent_headers(key), json={"host": "h"})       # a renewal: no line
    client.post("/p/demo/hub/publish", content=archive, headers={**agent_headers(key), "X-Kea-Sha256": sha})
    client.post("/p/demo/login", data={"password": secrets["site_password"], "name": "Ann", "next": "/"})
    client.get("/p/demo/?secret-code=xyz")
    text = caplog.text
    assert "demo: wrong or missing project key" in text
    assert text.count("lease taken by agent-a") == 1
    assert "demo: published release" in text and "by agent-a" in text
    assert "POST testserver/p/demo/login 303" in text                       # a reader action
    assert "GET testserver/p/demo/ " not in text and "xyz" not in text      # no GETs in events mode
    caplog.clear()
    TestClient(hub.HubApp(the_hub, "requests"), base_url="https://testserver").get("/p/demo/?code=xyz")
    assert "GET testserver/p/demo/ 303" in caplog.text and "xyz" not in caplog.text
    caplog.clear()
    TestClient(hub.HubApp(the_hub), base_url="https://testserver").get("/p/demo/hub/lease", headers=agent_headers("x"))
    assert "GET testserver" not in caplog.text                              # off: no request lines



def test_public_project_pages_without_login(demo, capsys):
    """kea hub public <name> on: pages, PDF and assets readable without a login; comments, the review cycle and data
    files still need a sign-in; writes too. Off again: every page needs the sign-in."""
    the_hub, secrets = demo
    client = TestClient(hub.HubApp(the_hub), base_url="https://testserver")
    archive = make_bundle(SITE)
    published = client.post("/p/demo/hub/publish", content=archive,
                            headers={**agent_headers(secrets["key"]), "X-Kea-Sha256": hashlib.sha256(archive).hexdigest()})
    assert published.status_code == 200
    assert client.get("/p/demo/", follow_redirects=False).status_code == 303          # private: to the login
    assert hub.main(["--dir", str(the_hub.folder), "public", "demo", "on"]) == 0
    assert "public: anyone can read" in capsys.readouterr().out
    visitor = TestClient(hub.HubApp(the_hub), base_url="https://testserver")
    page = visitor.get("/p/demo/", follow_redirects=False)
    assert page.status_code == 200 and "home" in page.text
    assert visitor.get("/p/demo/api/threads?page=x:r-a").status_code == 401           # comments: signed in only
    assert visitor.get("/p/demo/api/status").status_code == 401
    assert visitor.get("/p/demo/files/data/small.tsv", follow_redirects=False).status_code == 303   # data files too
    assert visitor.post("/p/demo/api/threads", json={"page": "x:r-a", "text": "hi"}).status_code == 401
    assert visitor.get("/p/demo/login").status_code == 200
    hub.main(["--dir", str(the_hub.folder), "list"])
    assert "public" in capsys.readouterr().out
    assert hub.main(["--dir", str(the_hub.folder), "public", "demo", "off"]) == 0
    assert TestClient(hub.HubApp(the_hub), base_url="https://testserver").get("/p/demo/", follow_redirects=False).status_code == 303



def test_hub_notices_a_session_that_stopped(demo, monkeypatch):
    """The hub's minute check: the first look only records; a watcher that stops sending heartbeats without saying
    why becomes gone (logged, notify_url called once); its return is announced too; the site's status carries it."""
    import yaml
    import datetime
    the_hub, secrets = demo
    settings = the_hub.settings()
    settings["notify_url"] = "https://ntfy.example/kea-alerts"
    (the_hub.folder / "hub.yaml").write_text(yaml.safe_dump(settings))
    app = hub.HubApp(the_hub)
    client = TestClient(app, base_url="https://testserver")
    deadline = time.time() + 3600
    beat = {"pid": 1, "deadline": deadline, "state": "collecting", "cycle": 1, "slow_interval": 60}
    assert client.post("/p/demo/hub/lease", headers=agent_headers(secrets["key"]),
                       json={"host": "h", "watching": True, "heartbeat": beat}).status_code == 200
    assert app.check_watchers() == []                                     # first look: recorded only
    heartbeat = the_hub.feedback("demo") / "heartbeat.json"
    info = json.loads(heartbeat.read_text())
    info["at"] = datetime.datetime.fromtimestamp(time.time() - 900, datetime.timezone.utc).isoformat()
    heartbeat.write_text(json.dumps(info))                                # 15 minutes of silence
    changes = app.check_watchers()
    assert [(name, before, status["state"]) for name, before, status in changes] == [("demo", "watching", "gone")]
    assert app.check_watchers() == []                                     # announced once
    posted = []

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False
    monkeypatch.setattr(hub.urllib.request, "urlopen", lambda request, timeout: posted.append(request) or Reply())
    app.notify("demo", changes[0][2])
    assert posted[0].full_url == "https://ntfy.example/kea-alerts" and "stopped unexpectedly" in posted[0].get_header("Title")
    assert posted[0].get_header("Click").endswith("/plan.html") and b"restarts the session" in posted[0].data
    client.post("/p/demo/hub/lease", headers=agent_headers(secrets["key"]),
                json={"host": "h", "watching": True, "heartbeat": {**beat, "exit": "implementing"}})
    assert [status["state"] for _, _, status in app.check_watchers()] == ["working"]
    archive = make_bundle(SITE)
    client.post("/p/demo/hub/publish", content=archive,
                headers={**agent_headers(secrets["key"]), "X-Kea-Sha256": hashlib.sha256(archive).hexdigest()})
    client.post("/p/demo/login", data={"password": secrets["site_password"], "name": "Ann", "next": "/"})
    watcher = client.get("/p/demo/api/status").json()["watcher"]
    assert watcher["state"] == "working" and watcher["exit"] == "implementing" and watcher["seconds"] < 60


def test_one_orcid_sign_in_for_every_project_and_one_sign_out(demo, monkeypatch):
    """Signed in on one project's site, the reader opens another project's site without a click (the site asks the
    hub, /auth/check); a reader without a hub session gets the login page once, not a loop. Sign out on any site
    ends every session, on the hub and on all sites."""
    import yaml
    from kea.feedback import accounts
    the_hub, secrets = demo
    settings = the_hub.settings()
    settings.update({"url": "https://keahub.example", "project_domain": "keahub.example"})
    (the_hub.folder / "hub.yaml").write_text(yaml.safe_dump(settings))
    other = the_hub.add("other")
    monkeypatch.setenv("KEA_ORCID_CLIENT_ID", "APP-TEST")
    monkeypatch.setenv("KEA_ORCID_CLIENT_SECRET", "s3cret")
    orcid = "0000-0002-1825-0097"
    monkeypatch.setattr(accounts, "exchange_code", lambda code, redirect, conf: {"orcid": orcid, "name": "Josiah Carberry"})
    accounts.Accounts(the_hub.folder).approve(orcid)                    # commenter on every project
    app = hub.HubApp(the_hub)
    browser = TestClient(app, base_url="https://keahub.example")      # one cookie jar, every host
    for name, key in (("demo", secrets["key"]), ("other", other["key"])):
        archive = make_bundle(SITE)
        browser.post(f"/p/{name}/hub/publish", content=archive,
                     headers={**agent_headers(key), "X-Kea-Sha256": hashlib.sha256(archive).hexdigest()})

    def visit(url: str, hops: int = 8):
        """Follow redirects across hosts like a browser; returns the last response and the hosts passed."""
        path = []
        for _ in range(hops):
            response = browser.get(url, follow_redirects=False)
            path.append(url.split("/")[2])
            if response.status_code not in (302, 303, 307, 308):
                return response, path
            location = response.headers["location"]
            url = location if location.startswith("https://") else f"https://{url.split('/')[2]}{location}"
        raise AssertionError(f"redirect loop: {path}")

    first, path = visit("https://demo.keahub.example/")                # no hub session: asked once, then login
    assert "keahub.example" in path and first.status_code == 200 and "Sign in with ORCID" in first.text
    start = browser.get("https://keahub.example/auth/login",
                        params={"return": "https://demo.keahub.example/"}, follow_redirects=False)
    state = start.headers["location"].split("state=")[1].split("&")[0]
    signed, _ = visit(f"https://keahub.example/auth/orcid/callback?code=c1&state={state}")
    assert signed.status_code == 200 and "home" in signed.text           # signed in on demo
    page, path = visit("https://other.keahub.example/")                # the other project: no click, no login page
    assert page.status_code == 200 and "home" in page.text and path.count("keahub.example") == 1
    assert browser.get("https://other.keahub.example/api/status").json()["you"] == "Josiah Carberry"
    out, _ = visit("https://other.keahub.example/auth/logout")         # sign out on one site ...
    assert browser.get("https://demo.keahub.example/api/status").status_code == 401   # ... ends them all
    assert browser.get("https://other.keahub.example/api/status").status_code == 401


def test_role_names_academic_and_old_names_still_work(demo, capsys):
    """Roles are auditor < reviewer < PI < director; the names before 1.19 (reader, commenter, steerer, owner) are
    read from an existing users.json and accepted on the command line, and the new names are written."""
    from kea.feedback import accounts
    the_hub, _ = demo
    folder = the_hub.folder
    assert accounts.ROLES == ("auditor", "reviewer", "pi", "director")
    assert [accounts.normalise_role(name) for name in ("reader", "commenter", "steerer", "owner", "PI", "Director")] \
        == ["auditor", "reviewer", "pi", "director", "pi", "director"]
    assert accounts.role_label("steerer") == "PI" and accounts.role_label("auditor") == "Auditor"
    assert accounts.rank("steerer") == accounts.rank("pi") > accounts.rank("commenter") > accounts.rank("reader") >= 0
    old = "0000-0002-1825-0097"
    (folder / "users.json").write_text(json.dumps({old: {"status": "approved", "name": "Old Timer",
                                                          "roles": {"*": "commenter", "demo": "steerer"}}}))
    book = accounts.Accounts(folder)
    assert book.role(old, "demo") == "pi" and book.role(old, "elsewhere") == "reviewer"
    assert hub.main(["--dir", str(folder), "users", "role", old, "owner", "--project", "demo"]) == 0
    stored = json.loads((folder / "users.json").read_text())[old]["roles"]
    assert stored == {"*": "reviewer", "demo": "director"}                        # written with the new names
    assert hub.main(["--dir", str(folder), "users", "role", old, "steerer", "--project", "demo"]) == 0
    assert json.loads((folder / "users.json").read_text())[old]["roles"]["demo"] == "pi"
    assert hub.main(["--dir", str(folder), "users", "role", old, "PI", "--project", "demo"]) == 0
    new = "0000-0001-5109-3700"
    assert hub.main(["--dir", str(folder), "users", "approve", new]) == 0         # default: reviewer everywhere
    assert book.role(new, "demo") == "reviewer"
    capsys.readouterr()
    hub.main(["--dir", str(folder), "users"])
    listing = capsys.readouterr().out
    assert "demo: PI" in listing and "*: Reviewer" in listing
    with pytest.raises(SystemExit):
        hub.main(["--dir", str(folder), "users", "role", new, "boss"])
    with pytest.raises(SystemExit):
        book.approve(new, "boss")


def hub_with_orcid(demo, monkeypatch, orcid: str = "0000-0002-1825-0097"):
    """The demo hub on keahub.example with an ORCID client (simulated), a private demo and a public project."""
    import yaml
    from kea.feedback import accounts
    the_hub, secrets = demo
    settings = the_hub.settings()
    settings.update({"url": "https://keahub.example", "project_domain": "keahub.example"})
    (the_hub.folder / "hub.yaml").write_text(yaml.safe_dump(settings))
    opened = the_hub.add("open-atlas", "Open atlas")
    the_hub.set_public("open-atlas", True)
    monkeypatch.setenv("KEA_ORCID_CLIENT_ID", "APP-TEST")
    monkeypatch.setenv("KEA_ORCID_CLIENT_SECRET", "s3cret")
    monkeypatch.setattr(accounts, "exchange_code", lambda code, redirect, conf: {"orcid": orcid, "name": "Josiah Carberry"})
    app = hub.HubApp(the_hub)
    apex = TestClient(app, base_url="https://keahub.example")
    files = dict(SITE, **{"meta.json": json.dumps({"files": ["data/small.tsv"], "published_at": "2026-11-02T10:00:00Z"})})
    assert publish_files(apex, secrets["key"], files).status_code == 200
    assert publish_files(apex, opened["key"], SITE, project="open-atlas").status_code == 200
    return the_hub, app, apex


def test_apex_landing_page_for_visitors(demo, monkeypatch):
    """https://<domain>/ without a hub session: what Kea is, Sign in with ORCID, the public projects only; the logo is
    served by the hub; without an ORCID client the page says so and shows no button."""
    the_hub, app, apex = hub_with_orcid(demo, monkeypatch)
    page = apex.get("/")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    text = page.text
    assert "Sign in with ORCID" in text and "href='/auth/login'" in text and "Break a data analysis into small, linked nodes" in text and "What is Kea?" in text
    assert "Open atlas" in text and "https://open-atlas.keahub.example/" in text
    assert "Demo project" not in text                                    # private projects stay unlisted
    assert "<script" not in text and "src='http" not in text and "href='http" not in text.replace(
        "href='https://open-atlas.keahub.example/'", "").replace("href='https://github.com/mfiers/Kea", "")
    # nothing loaded from elsewhere; links to Kea on GitHub; the reader's help, verbatim, readable without an account
    assert "href='https://github.com/mfiers/Kea'" in text and "id='help'" in text
    assert "Why small pages" in text and "class='tag'" in text and "Comments and the review cycle" in text
    alone = apex.get("/help")
    assert alone.status_code == 200 and "What is Kea?" in alone.text and "How a project progresses" in alone.text and "Sign out" not in alone.text
    logo = apex.get("/kea-head.png")
    assert logo.status_code == 200 and logo.headers["content-type"] == "image/png" and logo.content[:4] == b"\x89PNG"
    assert apex.get("/healthz").text == "ok" and apex.get("/nothing-here").status_code == 404
    monkeypatch.delenv("KEA_ORCID_CLIENT_ID")
    plain = apex.get("/")
    assert plain.status_code == 200 and "Sign in with ORCID" not in plain.text and "no ORCID sign-in" in plain.text


def test_apex_landing_page_for_a_signed_in_reader(demo, monkeypatch):
    """Sign in on the hub itself (no project): a pending reader sees that they wait; a project they asked for shows
    as pending approval; once approved, their projects with role, what it may do, private/public and last
    published; public projects without a role apart; Sign out returns to the visitor page."""
    from urllib.parse import parse_qs, urlsplit
    orcid = "0000-0002-1825-0097"
    the_hub, app, apex = hub_with_orcid(demo, monkeypatch, orcid)
    start = apex.get("/auth/login", follow_redirects=False)                # no return address: the hub's own page
    assert start.status_code == 303 and start.headers["location"].startswith("https://orcid.org/oauth/authorize?")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    back = apex.get("/auth/orcid/callback", params={"code": "c1", "state": state}, follow_redirects=False)
    assert back.status_code == 303 and back.headers["location"] == "https://keahub.example/"
    assert "__Host-kea_session" in back.headers["set-cookie"]
    waiting = apex.get("/")
    assert waiting.status_code == 200 and "Josiah Carberry" in waiting.text and orcid in waiting.text
    assert "waits for approval" in waiting.text and "Sign out" in waiting.text
    assert waiting.headers["cache-control"] == "no-store"
    assert apex.get("/auth/login", follow_redirects=False).headers["location"] == "https://keahub.example/"
    # asking for the demo project while pending: recorded, shown as pending
    ask = apex.get("/auth/login", params={"return": "https://demo.keahub.example/"}, follow_redirects=False)
    project_state = parse_qs(urlsplit(ask.headers["location"]).query)["state"][0]
    refused = apex.get("/auth/orcid/callback", params={"code": "c2", "state": project_state}, follow_redirects=False)
    assert refused.status_code == 403 and "approves new readers" in refused.text
    pending = apex.get("/").text
    assert "Demo project" in pending and "pending approval" in pending
    # approved as PI on demo (old role name on the command line): role, what it may do, private, publish date
    assert hub.main(["--dir", str(the_hub.folder), "users", "approve", orcid, "steerer", "--project", "demo"]) == 0
    mine = apex.get("/").text
    assert "pending approval" not in mine and "waits for approval" not in mine
    assert "<span class='role'>PI</span>" in mine and "harvests the comments into the plan" in mine
    assert "pill private" in mine and "2026-11-02" in mine and "https://demo.keahub.example/" in mine
    assert "Other public projects" in mine and "Open atlas" in mine
    assert mine.index("Demo project") < mine.index("Other public projects") < mine.index("Open atlas")
    # sign out: the visitor page again
    out = apex.get("/auth/logout", follow_redirects=False)
    assert out.status_code == 303 and out.headers["location"] == "https://keahub.example/"
    after = apex.get("/").text
    assert "Sign in with ORCID" in after and "Josiah Carberry" not in after


def test_site_login_folds_the_password_under_orcid(demo, monkeypatch):
    """With ORCID on the hub, a project's login page leads with a large ORCID button and folds the shared-password
    form into 'Sign in with a project password' (opened after a wrong password); without ORCID the form is as it
    was and the password still signs in."""
    the_hub, app, apex = hub_with_orcid(demo, monkeypatch)
    _, secrets = demo
    site = TestClient(app, base_url="https://demo.keahub.example")
    page = site.get("/login?next=/x/r-a.html")
    assert page.status_code == 200
    text = page.text
    assert "Sign in with ORCID" in text and "<details><summary>Sign in with a project password</summary>" in text
    assert text.index("Sign in with ORCID") < text.index("<details") < text.index("name='password'")
    assert " autofocus" not in text                                     # the focus stays off the folded form
    wrong = site.post("/login", data={"password": "nope", "name": "Ann", "next": "/"})
    assert wrong.status_code == 401 and "<details open>" in wrong.text and "Wrong password." in wrong.text
    monkeypatch.delenv("KEA_ORCID_CLIENT_ID")
    plain = TestClient(hub.HubApp(the_hub), base_url="https://demo.keahub.example")
    without = plain.get("/login").text
    assert "Sign in with ORCID" not in without and "<details" not in without
    assert "name='password' type='password' autofocus" in without
    entered = plain.post("/login", data={"password": secrets["site_password"], "name": "Ann", "next": "/"},
                         follow_redirects=False)
    assert entered.status_code == 303


def test_status_gives_the_name_menu_the_hub_and_other_projects(demo):
    the_hub, secrets = demo
    the_hub.add("second", "Second")
    the_hub.add("third", "Third")
    the_hub.set_public("third", True)
    client = TestClient(hub.HubApp(the_hub), base_url="https://testserver")
    archive = make_bundle(SITE)
    assert client.post("/p/demo/hub/publish", content=archive, headers={**agent_headers(secrets["key"]),
                       "X-Kea-Sha256": hashlib.sha256(archive).hexdigest()}).status_code == 200
    client.post("/p/demo/login", data={"password": secrets["site_password"], "name": "ann", "next": "/"},
                follow_redirects=False)
    menu = client.get("/p/demo/api/status").json()["hub"]
    assert menu["home"].startswith("https://kea.example.org")
    assert [project["title"] for project in menu["projects"]] == ["Third"]      # password sign-in: public ones only
    assert all("demo" not in project["url"] for project in menu["projects"])     # not the project you are on


def test_publish_and_seed_never_shrink_the_hubs_comment_logs(demo):
    """Comments readers made on the hub survive every later publish and any seed (the hub's log is the authority;
    a seed only fills an empty log)."""
    the_hub, secrets = demo
    client = TestClient(hub.HubApp(the_hub), base_url="https://testserver")
    archive = make_bundle(SITE)
    publish = lambda: client.post("/p/demo/hub/publish", content=archive, headers={
        **agent_headers(secrets["key"]), "X-Kea-Sha256": hashlib.sha256(archive).hexdigest()})
    assert publish().status_code == 200
    client.post("/p/demo/login", data={"password": secrets["site_password"], "name": "ann", "next": "/"},
                follow_redirects=False)
    assert client.post("/p/demo/api/threads", json={"page": "x:r-a", "text": "keep me"}).status_code == 200
    log = the_hub.feedback("demo") / "events.jsonl"
    before = log.read_bytes()
    seeded = client.post("/p/demo/hub/seed", headers=agent_headers(secrets["key"]), json={"events": "", "cycle": ""})
    assert "kept" in seeded.json()["seeded"]["events"]
    assert publish().status_code == 200 and publish().status_code == 200
    assert log.read_bytes().startswith(before) and b"keep me" in log.read_bytes()


def test_versions_are_shown(demo):
    from kea import __version__
    from kea.docsite import render
    the_hub, secrets = demo
    client = TestClient(hub.HubApp(the_hub), base_url="https://testserver")
    archive = make_bundle(SITE)
    client.post("/p/demo/hub/publish", content=archive, headers={**agent_headers(secrets["key"]),
                "X-Kea-Sha256": hashlib.sha256(archive).hexdigest()})
    client.post("/p/demo/login", data={"password": secrets["site_password"], "name": "ann", "next": "/"},
                follow_redirects=False)
    status = client.get("/p/demo/api/status").json()
    assert status["server_version"] == __version__ and status["on_hub"] is True
    assert f"Kea {__version__}" in render.version_pill()
    apex = TestClient(hub.HubApp(the_hub), base_url="https://kea.example.org")
    assert f"Kea {__version__}" in apex.get("/").text


def site_entries(page: str, big: bytes) -> dict:
    return {"site/index.html": f"<html><body>{page}</body></html>".encode(), "site/report.pdf": big,
            "site/_files.json": b"[]", "doc/x/result/r-a.md": b"---\nid: r-a\n---\ntext\n"}


def test_incremental_publish_sends_only_new_files_and_resumes(live_hub, tmp_path, monkeypatch):
    the_hub, secrets, url = live_hub
    monkeypatch.setenv("KEA_AGENT_ID", "agent-a")
    monkeypatch.setattr(publish, "CHUNK", 1000)                 # several chunks per file
    client = backend.Remote(url, "demo", secrets["key"], tmp_path / "events.jsonl", tmp_path / "cycle.jsonl")
    client.take_lease()
    big = bytes(range(256)) * 20                                # 5120 bytes: six chunks
    meta = {"files": [], "source_commits": {}}
    first, sent, reused = publish.send_incremental(client, site_entries("one", big), meta)
    assert sent == sum(len(value) for value in site_entries("one", big).values()) and reused == 0
    current = the_hub.project_dir("demo") / "current"
    assert (current / "site" / "report.pdf").read_bytes() == big and (current / "meta.json").is_file()
    second, sent, reused = publish.send_incremental(client, site_entries("two", big), meta)
    assert sent == len(b"<html><body>two</body></html>") and reused == len(big) + 2 + len(b"---\nid: r-a\n---\ntext\n")
    assert "two" in (current / "site" / "index.html").read_text() and second["release"] != first["release"]
    # a broken upload resumes where the hub's copy ends, and a wrong offset is answered with that point
    other = bytes(reversed(big))
    sha = hashlib.sha256(other).hexdigest()
    hub.receive_chunk(the_hub, "demo", sha, 0, len(other), other[:1500])
    assert client.request("POST", "blobs/missing", {"sha256": [sha]})["missing"] == {sha: 1500}
    with pytest.raises(backend.RemoteError) as refused:
        client.request("POST", f"blobs/{sha}", other[:1000], query={"offset": 0, "total": len(other)})
    assert refused.value.status == 409 and refused.value.detail["have"] == 1500
    publish.upload_blob(client, sha, other, len(other), 0)       # starts at 0, is told 1500, finishes
    assert hub.blob_path(the_hub, "demo", sha).read_bytes() == other


def test_manifest_release_refuses_unsafe_paths_and_wrong_checksums(demo):
    the_hub, secrets = demo
    data = b"<html>x</html>"
    sha = hashlib.sha256(data).hexdigest()
    hub.receive_chunk(the_hub, "demo", sha, 0, len(data), data)
    for path in ("../x", "/etc/passwd", "other/x.html", "site/../../x"):
        with pytest.raises(ValueError):
            hub.install_manifest(the_hub, "demo", {"site/index.html": sha, path: sha}, {"files": []})
    with pytest.raises(ValueError, match="never uploaded"):
        hub.install_manifest(the_hub, "demo", {"site/index.html": "0" * 64}, {"files": []})
    wrong = "f" * 64
    with pytest.raises(ValueError, match="does not match"):
        hub.receive_chunk(the_hub, "demo", wrong, 0, len(data), data)
    assert not hub.blob_path(the_hub, "demo", wrong).exists()
    result = hub.install_manifest(the_hub, "demo", {"site/index.html": sha}, {"files": []})
    assert (the_hub.project_dir("demo") / "releases" / result["release"] / "site" / "index.html").read_bytes() == data
