"""Permanent page identifiers (docsite/identity.py): minting, checks, kea check --fix, _ids.json and /id/<uid>."""
from __future__ import annotations

import json
from pathlib import Path

from starlette.testclient import TestClient

from kea.docsite import identity, nodes
from kea.feedback import server

SCHEMA = (Path(nodes.__file__).resolve().parents[1] / "templates" / "_schema.yaml").read_text()


def _page(doc: Path, relative: str, front: str) -> Path:
    path = doc / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front}\n---\nText.\n")
    return path


def _doc(tmp_path: Path) -> Path:
    doc = tmp_path / "doc"
    doc.mkdir()
    (doc / "_schema.yaml").write_text(SCHEMA)
    _page(doc, "p/experiment/home.md", "id: home\ntype: experiment\ntitle: E\nshort: An experiment.\nstatus: open")
    _page(doc, "p/premise/p-a.md", "id: p-a\ntype: premise\ntitle: A\nshort: Given.\nparent: home\nstatus: assumed")
    return doc


def test_new_uids_are_well_formed_and_distinct():
    uids = {identity.new_uid() for _ in range(1000)}
    assert len(uids) == 1000 and all(identity.UID_PATTERN.match(uid) for uid in uids)


def test_fix_writes_one_line_after_id_and_check_reports_problems(tmp_path):
    doc = _doc(tmp_path)
    tree = nodes.load_tree(doc)
    assert any("2 page(s) without a permanent id" in note for note in tree.notes)
    before = (doc / "p/premise/p-a.md").read_text()
    changed = identity.add_missing(tree)
    assert len(changed) == 2
    after = (doc / "p/premise/p-a.md").read_text()
    lines = after.split("\n")
    assert lines[1] == "id: p-a" and lines[2].startswith("uid: ") and identity.UID_PATTERN.match(lines[2][5:])
    assert after.replace(lines[2] + "\n", "") == before          # nothing else changed
    tree = nodes.load_tree(doc)
    assert tree.problems == [] and not any("without a permanent id" in note for note in tree.notes)
    assert identity.add_missing(tree) == []                       # a uid is minted once
    # a copied page keeps the uid of the original: reported
    copy = (doc / "p/premise/p-a.md").read_text().replace("id: p-a", "id: p-b")
    (doc / "p/premise/p-b.md").write_text(copy)
    (doc / "p/premise/p-c.md").write_text("---\nid: p-c\nuid: NOT-VALID\ntype: premise\ntitle: C\nshort: C.\n"
                                          "parent: home\nstatus: assumed\n---\n")
    problems = nodes.load_tree(doc).problems
    assert any("is also the uid of" in problem for problem in problems)
    assert any("p-c: uid 'NOT-VALID'" in problem for problem in problems)


def test_resolver_redirects_and_answers_json(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<main>hi</main>")
    uid = identity.new_uid()
    (site / "_ids.json").write_text(json.dumps({uid: {"key": "p:p-a", "url": "p/p-a.html", "type": "premise",
                                                      "number": "P1", "title": "A", "short": "Given.", "status": "assumed"}}))
    client = TestClient(server.make_app(site, tmp_path / "events.jsonl", "pw-for-tests", tmp_path / "cycle.jsonl"))
    client.post("/login", data={"password": "pw-for-tests", "name": "ann", "next": "/"}, follow_redirects=False)
    redirect = client.get(f"/id/{uid}", follow_redirects=False)
    assert redirect.status_code == 303 and redirect.headers["location"].endswith("/p/p-a.html")
    facts = client.get(f"/id/{uid}.json").json()
    assert facts["id"] == f"kea:{uid}" and facts["number"] == "P1" and facts["url"].endswith("/p/p-a.html")
    assert client.get("/id/" + "a" * 26).status_code == 404
