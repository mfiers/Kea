"""Where am I (docsite/whereami.py): every page's question from the graph, the question in the breadcrumbs and the
menu bar, the question strip, and the experiment's plan for the thumbnail."""
from __future__ import annotations

from kea.docsite import nodes, whereami

from test_graph import _doc, _page


def _tree(tmp_path):
    doc = _doc(tmp_path)
    for name in ("q-b", "q-c"):
        _page(doc, f"p/question/{name}.md", f"id: {name}\ntype: question\ntitle: Q {name}\nshort: Asks.\nparent: home\nstatus: open")
        _page(doc, f"p/step/s-{name}.md", f"id: s-{name}\ntype: step\ntitle: Run {name}\nshort: Runs.\nparent: {name}\n"
              "status: planned\nrelations:\n  uses: [o-a]\n  decided_in: [d-a]")
    # beside the route, under the experiment: a caveat on q-a's result, a decision two questions follow
    _page(doc, "p/caveat/w-a.md", "id: w-a\ntype: caveat\ntitle: Small n\nshort: Few.\nparent: home\nstatus: open\n"
          "kind: statistical\nrelations:\n  limits: [r-a]")
    _page(doc, "p/decision/d-a.md", "id: d-a\ntype: decision\ntitle: Per donor\nshort: Per donor.\nparent: home\nstatus: active")
    _page(doc, "p/resource/o-a.md", "id: o-a\ntype: resource\ntitle: Data\nshort: The data.\nparent: home\nstatus: current\n"
          "kind: dataset")
    step = doc / "p/step/s-a.md"
    step.write_text(step.read_text().replace("relies_on: [p-a]", "relies_on: [p-a]\n  uses: [o-a]"))
    return nodes.load_tree(doc)


def test_every_page_gets_its_question_from_the_graph(tmp_path):
    tree = _tree(tmp_path)
    found = whereami.questions_of(tree)
    assert found["p:r-a"] == ("p:q-a", []) and found["p:s-a"][0] == "p:q-a"
    assert found["p:w-a"][0] == "p:q-a"                         # a caveat takes the question of what it limits
    assert found["p:p-a"][0] == "p:q-a"                         # a premise, of the step that relies on it
    assert found["p:d-a"][0] == "p:q-b" and found["p:d-a"][1] == ["p:q-c"]     # two questions: home and also
    assert found["p:o-a"][0] is None                            # used by all three questions: experiment-wide


def test_breadcrumbs_strip_and_plan_name_the_question(tmp_path):
    from kea.docsite import pages
    tree = _tree(tmp_path)
    caveat = tree.nodes["p:w-a"]
    trail = pages.SiteRenderer.trail(type("R", (), {"tree": tree})(), caveat, "")
    assert [text for text, _ in trail][-2:] == ["Q1 Does it?", "W1"]         # its question, then the page by its tag
    assert whereami.chip_html(tree, caveat, "").count("t-question") == 1
    strip = whereami.strip_html(tree, tree.nodes["p:r-a"], "")
    assert "st-here" in strip and ">R1<" in strip and ">W1<" in strip and "beside" in strip
    plan = whereami.plan(tree, "p", {key: key.split(":")[1] + ".html" for key in tree.nodes})
    first = plan["questions"][0]
    assert first["label"] == "Q1" and first["cells"]["result"] == ["p:r-a"]
    assert first["beside"] == ["p:w-a", "p:p-a"]                 # caveats, decisions, premises
    assert plan["pages"]["p:r-a"]["home"] == "p:q-a"
