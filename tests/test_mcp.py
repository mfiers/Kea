"""The personal MCP link on a hub (feedback/mcp.py): only a known link opens it, the link's role limits it, pages and
their links are read from the published release, and a sign-off is one approve thread bound to the version read,
sent only with confirmed=true; a read-only link has no sign or comment tool."""
import hashlib
import json

from starlette.testclient import TestClient

from kea.feedback import hub, mcp, store

from test_hub import agent_headers, make_bundle

GRAPH = {"projects": ["x:home"], "nodes": [
    {"key": "x:home", "type": "experiment", "tag": "", "title": "The experiment", "short": "All of it.",
     "href": "x/home.html", "parent": None, "signed": True, "waiting": False, "held": False, "status": "open",
     "edges": []},
    {"key": "x:q-a", "type": "question", "tag": "Q1", "title": "Does it work?", "short": "One thing.",
     "href": "x/q-a.html", "parent": "x:home", "signed": False, "waiting": True, "held": False, "status": "open",
     "edges": [["relies_on", "x:p-a"]]},
    {"key": "x:p-a", "type": "premise", "tag": "P1", "title": "Data are fine", "short": "Assumed.",
     "href": "x/p-a.html", "parent": "x:home", "signed": True, "waiting": False, "held": False, "status": "open",
     "edges": []}]}
IDS = {"uid1": {"key": "x:q-a", "version": "v1q", "source": "doc/x/question/q-a.md"},
       "uid2": {"key": "x:p-a", "version": "v1p", "source": "doc/x/premise/p-a.md"},
       "uid0": {"key": "x:home", "version": "v1h", "source": "doc/x/experiment/home.md"}}


def published(tmp_path):
    the_hub = hub.Hub(tmp_path / "hub")
    the_hub.init("https://kea.example.org")
    secrets = the_hub.add("demo", "Demo project")
    the_hub.add("other", "Other")
    client = TestClient(hub.HubApp(the_hub), base_url="https://testserver")
    archive = make_bundle({"site/index.html": "<html></html>", "site/_graph.json": json.dumps(GRAPH),
                           "site/_ids.json": json.dumps(IDS), "meta.json": "{}",
                           "doc/x/question/q-a.md": "---\nid: q-a\n---\nWe ask whether it works.\n"})
    headers = {**agent_headers(secrets["key"]), "X-Kea-Sha256": hashlib.sha256(archive).hexdigest()}
    assert client.post("/p/demo/hub/lease", headers=agent_headers(secrets["key"]), json={"host": "h"}).status_code == 200
    assert client.post("/p/demo/hub/publish", content=archive, headers=headers).status_code == 200
    return the_hub, client


def rpc(client, token, method, params=None, ident=1):
    return client.post(f"/mcp/{token}", json={"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}})


def call(client, token, tool, **arguments):
    answer = rpc(client, token, "tools/call", {"name": tool, "arguments": arguments}).json()["result"]
    return answer["content"][0]["text"], answer["isError"]


def test_a_signing_link_reads_follows_and_signs_one_page_after_a_yes(tmp_path):
    the_hub, client = published(tmp_path)
    token, _ = mcp.Links(the_hub.folder).add("phone", True, 30, name="Mark", projects=["demo"])
    assert rpc(client, "wrong", "tools/list").status_code == 404
    started = rpc(client, token, "initialize", {"protocolVersion": "2025-06-18"}).json()["result"]
    assert started["protocolVersion"] == "2025-06-18" and "voice" in started["instructions"]
    assert client.post(f"/mcp/{token}", json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202
    names = [tool["name"] for tool in rpc(client, token, "tools/list").json()["result"]["tools"]]
    assert "sign_page" in names and "comment" in names
    text, _ = call(client, token, "list_projects")
    assert "demo" in text and "other" not in text
    assert call(client, token, "overview", project="other")[1] is True
    text, _ = call(client, token, "overview", project="demo")
    assert "Q1 (question): Does it work?" in text and "Waiting for a sign-off (1)" in text
    text, _ = call(client, token, "get_page", project="demo", page="q1")
    assert "Version: v1q" in text and "We ask whether it works." in text and "relies on P1" in text
    text, _ = call(client, token, "connections", project="demo", page="P1", direction="down")
    assert "Q1" in text
    text, _ = call(client, token, "path_between", project="demo", from_page="Q1", to_page="P1")
    assert "relies on" in text
    assert call(client, token, "sign_page", project="demo", page="Q1", version="old")[1] is True
    text, failed = call(client, token, "sign_page", project="demo", page="Q1", version="v1q")
    assert not failed and "About to sign" in text and store.threads(the_hub.feedback("demo") / "events.jsonl") == []
    text, failed = call(client, token, "sign_page", project="demo", page="Q1", version="v1q", confirmed=True)
    assert not failed and "Approved" in text
    threads = store.threads(the_hub.feedback("demo") / "events.jsonl")
    assert len(threads) == 1 and threads[0].tags == ["approve"] and threads[0].page_version == "v1q"
    assert threads[0].author == "Mark" and threads[0].page == "x:q-a"
    text, _ = call(client, token, "sign_page", project="demo", page="Q1", version="v1q", confirmed=True)
    assert "already in" in text and len(store.threads(the_hub.feedback("demo") / "events.jsonl")) == 1


def test_a_read_link_cannot_sign_and_the_token_is_not_kept(tmp_path):
    the_hub, client = published(tmp_path)
    token, entry = mcp.Links(the_hub.folder).add("", False, 30, name="Ann", projects=["demo"])
    assert token not in (the_hub.folder / "mcp_links.json").read_text()
    names = [tool["name"] for tool in rpc(client, token, "tools/list").json()["result"]["tools"]]
    assert "sign_page" not in names
    text, failed = call(client, token, "sign_page", project="demo", page="Q1", version="v1q", confirmed=True)
    assert failed and "reads only" in text
    assert mcp.Links(the_hub.folder).revoke(entry["id"])
    assert rpc(client, token, "tools/list").status_code == 404
