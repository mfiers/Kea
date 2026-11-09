"""Tests for the site builder (kea.docsite) and the comment layer (kea.feedback)."""
import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from kea.config import PACKAGE_DIR
from kea.docsite import comments, nodes
from kea.docsite.render import LinkContext, render_markdown
from kea.feedback import server, store


def write_page(folder: Path, relative: str, header: str, body: str = "") -> None:
    path = folder / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{header}\n---\n{body}\n")


@pytest.fixture()
def toy_doc(tmp_path):
    doc = tmp_path / "doc"
    (doc).mkdir()
    (doc / "_schema.yaml").write_text((PACKAGE_DIR / "templates" / "_schema.yaml").read_text())
    write_page(doc, "proj/goal/home.md", "id: home\ntype: goal\ntitle: Goal\nshort: The goal.\nstatus: open")
    write_page(doc, "proj/question/q-a.md", "id: q-a\ntype: question\ntitle: Q\nshort: A question: with colon.\n"
               "parent: home\nstatus: open")
    write_page(doc, "proj/result/r-a.md", "id: r-a\ntype: result\ntitle: R\nshort: A result.\nparent: home\n"
               "status: done\nrelations:\n  answers: [q-a]\nsources:\n  - data: x.tsv", "See [[q-a]].")
    return doc


def test_toy_tree_numbers_and_reverse_edges(toy_doc):
    tree = nodes.load_tree(toy_doc)
    assert tree.problems == []
    question = tree.nodes["proj:q-a"]
    assert question.number == "Q1"
    assert question.short == "A question: with colon."          # plain colon in short is quoted automatically
    assert tree.nodes["proj:r-a"].number == "R1"
    assert question.incoming == {"Answered by": ["proj:r-a"]}


def test_schema_violations_are_reported(toy_doc):
    write_page(toy_doc, "proj/result/r-bad.md", "id: r-bad\ntype: result\ntitle: Bad\nshort: Bad.\nparent: home\n"
               "status: maybe\nrelations:\n  answers: [r-a]\n  frobnicates: [q-a]", "[[nowhere]] [[other:x]]")
    tree = nodes.load_tree(toy_doc)
    text = "\n".join(tree.problems)
    assert "status 'maybe'" in text
    assert "answers from result to result not allowed" in text
    assert "unknown relation 'frobnicates'" in text
    assert "unknown page proj:nowhere" in text
    assert any("project 'other' has no pages yet" in note for note in tree.notes)   # a note, not an error


def test_links_render_and_code_spans_are_left_alone(toy_doc):
    tree = nodes.load_tree(toy_doc)
    context = LinkContext(tree, "proj", "../", lambda target, prefix: None, lambda target, prefix: (None, target))
    html_text = render_markdown("See [[q-a]] and `[[q-a]]` and [[q-a|this|why]].", context)
    assert "href='../proj/q-a.html'" in html_text and ">Q1</a>" in html_text
    assert "<code>[[q-a]]</code>" in html_text
    assert "this <a class='tag t-question'" in html_text and "why" in html_text   # text plain, the tag links
    assert context.broken == []


def test_link_rules_tagline_lists_and_heading_links(toy_doc):
    tree = nodes.load_tree(toy_doc)
    context = LinkContext(tree, "proj", "", lambda target, prefix: None, lambda target, prefix: (None, target))
    listed = render_markdown("- [[q-a]] a short line\n- [[q-a]]: " + "long " * 60 + "\n", context)
    assert listed.count("class='tagline'") == 1                  # tag + one line: one link
    assert "<span class='tl-text'>a short line</span></a>" in listed
    heading = render_markdown("### [[q-a]]\n\ntext", context)
    assert "<h3><a class='tag t-question'" in heading and "Q1</a> Q</h3>" in heading      # tag + the page's title


def test_store_is_append_only_and_validates(tmp_path):
    events = tmp_path / "events.jsonl"
    created = store.append_event({"type": "create", "page": "proj:q-a", "text": "hello", "author": "me"}, events)
    first_line = events.read_text().splitlines()[0]
    store.append_event({"type": "reply", "thread_id": created["thread_id"], "text": "hi", "author": "claude"}, events)
    assert events.read_text().splitlines()[0] == first_line
    with pytest.raises(store.FeedbackError):
        store.append_event({"type": "create", "page": "../etc", "text": "x", "author": "me"}, events)
    with pytest.raises(store.FeedbackError):
        store.append_event({"type": "reply", "thread_id": "t_missing", "text": "x", "author": "me"}, events)


def test_server_password_reserved_name_and_downloads(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<main>hi</main>")
    (site / "_files.json").write_text(json.dumps(["pyproject.toml"]))
    events = tmp_path / "events.jsonl"
    client = TestClient(server.make_app(site, events, "secret-password", tmp_path / "cycle.jsonl"))
    assert client.get("/index.html", follow_redirects=False).status_code == 303
    assert client.get("/api/threads").status_code == 401
    assert client.post("/login", data={"password": "wrong", "name": "x", "next": "/"}).status_code == 401
    client.post("/login", data={"password": "secret-password", "name": "claude", "next": "/"}, follow_redirects=False)
    assert client.get("/index.html").status_code == 200
    refused = client.post("/api/threads", json={"page": "proj:q-a", "text": "x"})
    assert refused.status_code == 400 and "reserved" in refused.json()["error"]
    assert client.get("/files/pyproject.toml").status_code == 200
    assert client.get("/files/.env").status_code == 404
    assert client.get("/files/uv.lock").status_code == 404


def test_inject_is_idempotent_and_escapes(tmp_path):
    site = tmp_path / "site"
    (site / "proj").mkdir(parents=True)
    page_path = site / "proj" / "q-a.html"
    page_path.write_text("<html><head><title>T</title></head><body><main>text</main></body></html>")
    events = tmp_path / "events.jsonl"
    store.append_event({"type": "create", "page": "proj:q-a", "text": "<script>alert(1)</script>", "author": "me"},
                       events)
    comments.inject(site, {"proj/q-a.html": ("proj:q-a", None)}, events)
    once = page_path.read_text()
    comments.inject(site, {"proj/q-a.html": ("proj:q-a", None)}, events)
    assert page_path.read_text() == once
    assert once.count("<script id='fb-script'") == 1
    assert "data-page='proj:q-a'" in once
    assert "<script>alert(1)</script>" not in once and "&lt;script&gt;alert(1)&lt;/script&gt;" in once


def test_callouts_render_as_boxes():
    from kea.docsite.render import callouts
    out = callouts("before\n> [!warning] Mind this\n> body line\nafter")
    assert "<div class='callout callout-warning' markdown='1'>" in out and "**Mind this**" in out
    assert "body line" in out and out.strip().endswith("after")


def test_context_lists_evidence_caveats_and_gaps(toy_doc):
    from kea.docsite import context
    write_page(toy_doc, "proj/caveat/w-a.md", "id: w-a\ntype: caveat\ntitle: A limit\nshort: Limits R.\nparent: home\n"
               "status: open\nrelations:\n  limits: [r-a]")
    tree = nodes.load_tree(toy_doc)
    text = context.question_context(tree, tree.nodes["proj:q-a"])
    assert "## Results" in text and "R1 R" in text                      # the result that answers it
    assert "W1 A limit [open] limits R1" in text                        # its caveat, with what it limits
    assert "has no hypothesis" in text                                  # a gap
    overview = context.experiment_context(tree, "proj")
    assert "## Open caveats" in overview and "W1 A limit" in overview


def test_lists_without_blank_line_and_full_names(toy_doc):
    from kea.docsite.render import fullname_link, separate_lists, type_badge
    assert separate_lists("three checks:\n- a\n- b") == "three checks:\n\n- a\n- b"
    assert separate_lists("- a\n  more\n- b") == "- a\n  more\n- b"                 # inside a list: unchanged
    assert separate_lists("```\nx:\n- y\n```") == "```\nx:\n- y\n```"              # code fences: unchanged
    tree = nodes.load_tree(toy_doc)
    context = LinkContext(tree, "proj", "", lambda target, prefix: None, lambda target, prefix: (None, target))
    assert "<li>" in render_markdown("Three checks:\n- one\n- two", context)
    full = fullname_link(tree.nodes["proj:q-a"], "")
    assert ">Question <span class='tag t-question'>" in full and "Q1</span></a>" in full   # word, then the tag
    assert "Question <span class='tag" in type_badge(tree.nodes["proj:q-a"])


def test_spelled_out_page_numbers_are_noted(toy_doc):
    write_page(toy_doc, "proj/result/r-b.md", "id: r-b\ntype: result\ntitle: R2\nshort: Other.\nparent: home\n"
               "status: done", "As conclusion 2 says, in 40 cells.")
    tree = nodes.load_tree(toy_doc)
    assert any("'conclusion 2'" in note for note in tree.notes)


def test_resources_and_terms_are_numbered_with_schema_defaults(toy_doc):
    import yaml
    schema = yaml.safe_load((toy_doc / "_schema.yaml").read_text())
    for section in ("number_prefix", "status_values", "relations"):      # an older project's schema
        for kind in ("term", "resource", "uses"):
            schema.get(section, {}).pop(kind, None)
    (toy_doc / "_schema.yaml").write_text(yaml.safe_dump(schema))
    write_page(toy_doc, "proj/term/t-x.md", "id: t-x\ntype: term\ntitle: Thing\nshort: A thing.\nparent: home")
    write_page(toy_doc, "proj/resource/o-db.md", "id: o-db\ntype: resource\ntitle: A database\nshort: Where data "
               "came from.\nparent: home\nstatus: current\nkind: file\nversion: '2'")
    write_page(toy_doc, "proj/step/s-a.md", "id: s-a\ntype: step\ntitle: S\nshort: A step.\nparent: home\n"
               "status: done\nrelations:\n  uses: [o-db]")
    tree = nodes.load_tree(toy_doc)
    assert tree.problems == []
    assert tree.nodes["proj:t-x"].number == "T1" and tree.nodes["proj:o-db"].number == "O1"
    assert tree.nodes["proj:o-db"].incoming == {"Used in": ["proj:s-a"]}
    assert any("resource without retrieved, sha256" in note for note in tree.notes)


def test_a_submit_sent_twice_is_stored_once(tmp_path):
    """The browser sends one key per submit (X-Kea-Request); a repeat (double click, retry after a stalled disk)
    returns the stored event instead of writing it again."""
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<main>hi</main>")
    events = tmp_path / "events.jsonl"
    client = TestClient(server.make_app(site, events, "secret-password", tmp_path / "cycle.jsonl"))
    client.post("/login", data={"password": "secret-password", "name": "reader", "next": "/"}, follow_redirects=False)
    created = client.post("/api/threads", json={"page": "proj/q-a.html", "text": "why?"},
                          headers={"X-Kea-Request": "load1-a"})
    again = client.post("/api/threads", json={"page": "proj/q-a.html", "text": "why?"},
                        headers={"X-Kea-Request": "load1-a"})
    assert created.json()["thread"]["thread_id"] == again.json()["thread"]["thread_id"]
    thread_id = created.json()["thread"]["thread_id"]
    for _ in range(3):
        client.post(f"/api/threads/{thread_id}/reply", json={"text": "more"}, headers={"X-Kea-Request": "load1-b"})
    client.post(f"/api/threads/{thread_id}/reply", json={"text": "more"}, headers={"X-Kea-Request": "load2-b"})
    replies = [event for event in store.load_events(events) if event["type"] == "reply"]
    assert len(store.load_events(events)) == 3 and len(replies) == 2   # one create, the reply once per key


def test_rrid_is_checked_for_form_and_missing_on_software(toy_doc):
    write_page(toy_doc, "proj/resource/o-np.md", "id: o-np\ntype: resource\ntitle: NumPy\nshort: Arrays.\nparent: home\n"
               "status: current\nkind: software\nversion: '2.4'\nretrieved: 2026-11-06\nrrid: RRID:SCR_008633")
    write_page(toy_doc, "proj/resource/o-x.md", "id: o-x\ntype: resource\ntitle: X\nshort: A tool.\nparent: home\n"
               "status: current\nkind: software\nversion: '1'\nretrieved: 2026-11-06")
    write_page(toy_doc, "proj/resource/o-bad.md", "id: o-bad\ntype: resource\ntitle: Bad\nshort: A tool.\nparent: home\n"
               "status: current\nkind: software\nversion: '1'\nretrieved: 2026-11-06\nrrid: SCR-1")
    tree = nodes.load_tree(toy_doc)
    assert any("o-bad.md: rrid 'SCR-1'" in problem for problem in tree.problems)
    assert any("o-x.md: no rrid" in note for note in tree.notes)
    assert not any("o-np.md" in item for item in tree.notes + tree.problems)


def test_rrid_resolver(monkeypatch):
    import io
    from kea.docsite import rrid
    found = {"hits": {"hits": [{"_source": {"item": {"name": "NumPy"}}}]}}
    monkeypatch.setattr(rrid.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(json.dumps(found).encode()))
    assert rrid.resolve("RRID:SCR_008633") == "NumPy"
    monkeypatch.setattr(rrid.urllib.request, "urlopen",
                        lambda *args, **kwargs: io.BytesIO(json.dumps({"hits": {"hits": []}}).encode()))
    assert rrid.resolve("RRID:SCR_000000") is None


def test_rrid_none_means_searched(toy_doc):
    write_page(toy_doc, "proj/resource/o-f.md", "id: o-f\ntype: resource\ntitle: F\nshort: A tool.\nparent: home\n"
               "status: current\nkind: software\nversion: '1'\nretrieved: 2026-11-06\nrrid: none")
    tree = nodes.load_tree(toy_doc)
    assert not any("o-f.md" in item for item in tree.notes + tree.problems)


def test_term_with_link_every_is_linked_at_every_use(toy_doc):
    write_page(toy_doc, "proj/term/t-gene.md", "id: t-gene\ntype: term\ntitle: APP\nshort: A gene.\nparent: home\n"
               "link: every")
    write_page(toy_doc, "proj/term/t-once.md", "id: t-once\ntype: term\ntitle: Thing\nshort: Once.\nparent: home")
    tree = nodes.load_tree(toy_doc)
    assert not tree.problems
    context = LinkContext(tree, "proj", "", lambda target, prefix: None, lambda target, prefix: (None, target))
    html = render_markdown("APP and Thing; again APP, Thing and an app.\n\nAPP once more. `APP` in code.", context)
    assert html.count("class='term'") == 4                       # APP three times, Thing once
    assert html.count(">APP</a>") == 3 and html.count(">Thing</a>") == 1 and ">app</a>" not in html
    assert "<code>APP</code>" in html
    on_own_page = LinkContext(tree, "proj", "", lambda target, prefix: None, lambda target, prefix: (None, target),
                              current="proj:t-gene")
    assert ">APP</a>" not in render_markdown("APP here.", on_own_page)
    write_page(toy_doc, "proj/term/t-bad.md", "id: t-bad\ntype: term\ntitle: Bad\nshort: B.\nparent: home\n"
               "link: always")
    assert any("link: 'always'" in problem for problem in nodes.load_tree(toy_doc).problems)


def test_inject_reaches_wide_pages(tmp_path):
    """Pages rendered with <main class='wide'> (commit pages, history) get the comment layer too."""
    site = tmp_path / "site"
    (site / "commits").mkdir(parents=True)
    page_path = site / "commits" / "abc.html"
    page_path.write_text("<html><head><title>T</title></head><body><main class='wide'>diff</main></body></html>")
    counts = comments.inject(site, {}, tmp_path / "events.jsonl")
    assert counts["pages"] == 1 and "<script id='fb-script'" in page_path.read_text()


def test_release_table_links_only_written_plans(tmp_path, monkeypatch):
    from kea.docsite import pages
    monkeypatch.setattr(nodes, "DOC", tmp_path)
    (tmp_path / "_cycles").mkdir()
    (tmp_path / "_cycles" / "cycle-002.md").write_text("---\ncycle: 2\n---\n")
    assert pages.cycle_cell("2") == "<a href='../cycles/cycle-002.html'>cycle 2</a>"
    assert pages.cycle_cell("5") == "cycle 5"                     # released without a written plan: no page
    assert pages.cycle_cell("0") == ""


def test_references_get_an_author_year_pill_and_terms_link_in_tables_and_per_section(toy_doc):
    write_page(toy_doc, "proj/reference/ref-ak.md", "id: ref-ak\ntype: reference\ntitle: \"Akiyama et al. 1994, J "
               "Neuroimmunol: MRP14 in microglia\"\nshort: Staining.\nparent: home")
    write_page(toy_doc, "proj/reference/ref-solo.md", "id: ref-solo\ntype: reference\ntitle: A paper\nshort: S.\n"
               "parent: home\ncitation: 'Smith, J. A title. J Thing 3, 1 (2001).'")
    write_page(toy_doc, "proj/term/t-acc.md", "id: t-acc\ntype: term\ntitle: ACC\nshort: \"ACC: anterior cingulate "
               "cortex.\"\nparent: home", "<!-- generated -->\n**ACC**: anterior cingulate cortex.\n\nMore.")
    write_page(toy_doc, "proj/resource/o-ds.md", "id: o-ds\ntype: resource\ntitle: Dataset G23\nshort: Data.\n"
               "parent: home\naliases: [G23/MIC]")
    tree = nodes.load_tree(toy_doc)
    reference = tree.nodes["proj:ref-ak"]
    assert reference.tag == "Akiyama et al. 1994" and reference.tag_title == "J Neuroimmunol: MRP14 in microglia"
    assert tree.nodes["proj:ref-solo"].tag == "Smith 2001"
    context = LinkContext(tree, "proj", "", lambda target, prefix: None, lambda target, prefix: (None, target))
    html = render_markdown("As shown ([[ref-ak]]; [[ref-ak|Akiyama 1994, p.3]]).", context)
    assert html.count("class='tag t-reference'") == 2 and ">Akiyama et al. 1994</a>" in html
    assert ">Akiyama 1994, p.3</a>" in html and "MRP14" not in html.split("title=")[0]
    table = "ACC in text.\n\n| ACC | n |\n|---|---|\n| ACC | G23/MIC |\n\n## Next\n\nACC again."
    html = render_markdown(table, LinkContext(tree, "proj", "", lambda target, prefix: None,
                                              lambda target, prefix: (None, target)))
    assert html.count(">ACC</a>") == 2                      # first use, then once more after the ## heading
    assert "<th>ACC</th>" in html                           # never in a table header
    assert "term-resource" in html and ">G23/MIC</a>" in html  # a resource alias, linked in a table cell
    from kea.docsite.pages import repeats_body
    assert repeats_body(tree.nodes["proj:t-acc"]) and not repeats_body(tree.nodes["proj:r-a"])
