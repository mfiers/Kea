"""The graph view (docsite/explore.py): one tree parent per page along the route, pages beside the route as chips of
the page they qualify, the scientific state on each box, and the page shell's embed mode and Graph link."""
from __future__ import annotations

from kea.docsite import explore, nodes, render

from test_graph import _doc, _page


def _graph(tmp_path):
    doc = _doc(tmp_path)
    _page(doc, "p/figure/f-a.md", "id: f-a\ntype: figure\ntitle: Plot\nshort: A plot.\nparent: q-a\nstatus: done")
    result = doc / "p/result/r-a.md"
    result.write_text(result.read_text().replace("made_by: [s-a]", "made_by: [s-a]\n  shown_in: [f-a]"))
    _page(doc, "p/caveat/w-a.md", "id: w-a\ntype: caveat\ntitle: Small n\nshort: Few.\nparent: home\nstatus: open\n"
          "kind: statistical\nrelations:\n  limits: [r-a]")
    _page(doc, "p/resource/o-a.md", "id: o-a\ntype: resource\ntitle: Data\nshort: The data.\nparent: home\n"
          "status: current\nkind: dataset")
    tree = nodes.load_tree(doc)
    data = explore.graph(tree, {key: key.split(":")[1] + ".html" for key in tree.nodes})
    return tree, data, {node["key"]: node for node in data["nodes"]}


def test_each_page_hangs_from_the_page_it_grows_from(tmp_path):
    _, data, by_key = _graph(tmp_path)
    assert data["projects"] == ["p:home"]
    assert by_key["p:q-a"]["parent"] == "p:home"
    assert by_key["p:h-a"]["parent"] == "p:q-a"                 # a hypothesis: its question
    assert by_key["p:s-a"]["parent"] == "p:h-a"                 # a step: the hypothesis it tests
    assert by_key["p:r-a"]["parent"] == "p:s-a"                 # a result: the step that made it
    assert by_key["p:f-a"]["parent"] == "p:r-a"                 # a figure: the result shown in it
    assert by_key["p:c-a"]["parent"] == "p:q-a"                 # a conclusion: its question (its evidence as edges)
    assert ["supported_by", "p:r-a"] in by_key["p:c-a"]["edges"]
    assert (by_key["p:w-a"]["parent"], by_key["p:w-a"]["beside"]) == ("p:r-a", True)    # a caveat: what it limits
    assert (by_key["p:p-a"]["parent"], by_key["p:p-a"]["beside"]) == ("p:s-a", True)    # a premise: what relies on it
    assert (by_key["p:o-a"]["parent"], by_key["p:o-a"]["beside"]) == ("p:home", True)   # the library: the experiment
    assert by_key["p:r-a"]["question"] == "p:q-a" and by_key["p:home"]["parent"] is None


def test_boxes_carry_the_scientific_state(tmp_path):
    _, _, by_key = _graph(tmp_path)
    assert by_key["p:h-a"]["fixed"] is True                     # fixed before results
    assert by_key["p:c-a"]["certainty"] == "low"
    assert "p:s-a" in by_key["p:r-a"]["up"]                     # a result rests on the step that made it
    assert "p:r-a" in by_key["p:c-a"]["up"]                     # a conclusion on its evidence
    assert by_key["p:r-a"]["held"] is False and by_key["p:r-a"]["signed"] is False


def test_the_tree_parent_is_always_to_the_left(tmp_path):
    doc = _doc(tmp_path)
    # a result that "tests" nothing and is made by a conclusion-ranked page cannot hang from it
    _page(doc, "p/result/r-b.md", "id: r-b\ntype: result\ntitle: Other\nshort: Other.\nparent: q-a\nstatus: done\n"
          "sources: [y.tsv]\nrelations:\n  answers: [q-a]")
    tree = nodes.load_tree(doc)
    data = explore.graph(tree, {key: key.split(":")[1] + ".html" for key in tree.nodes})
    by_key = {node["key"]: node for node in data["nodes"]}
    for node in data["nodes"]:
        parent = by_key.get(node["parent"]) if node["parent"] else None
        if parent and not node["beside"] and node["type"] in explore.RANK and parent["type"] in explore.RANK:
            assert explore.RANK[parent["type"]] < explore.RANK[node["type"]], node["key"]
    assert by_key["p:r-b"]["parent"] == "p:q-a"


def test_page_shell_marks_embedded_pages_and_links_the_graph(tmp_path):
    tree = nodes.load_tree(_doc(tmp_path))
    node = tree.nodes["p:r-a"]
    html = render.page("R1", "<p>x</p>", "../", "p", tree, node)
    assert "parent.keaExplore" in html and "kea-embed" in html          # inside the graph's zoom: no menu bar
    assert "explore.html#p:r-a" in html and "class='graph-link'" in html  # the menu bar's Graph opens at this page
    assert ".kea-embed .topbar" in render.CSS


def test_a_question_that_names_itself_as_parent_still_hangs_from_the_experiment(tmp_path):
    doc = _doc(tmp_path)
    question = doc / "p/question/q-a.md"
    question.write_text(question.read_text().replace("parent: home", "parent: q-a"))
    hypothesis = doc / "p/hypothesis/h-a.md"
    hypothesis.write_text(hypothesis.read_text().replace("fixed_before_results: true", "fixed_before_results: 'yes'"))
    tree = nodes.load_tree(doc)
    by_key = {node["key"]: node for node in explore.graph(tree, {key: "x.html" for key in tree.nodes})["nodes"]}
    assert by_key["p:q-a"]["parent"] == "p:home"
    assert by_key["p:h-a"]["fixed"] is None                     # not a yes/no: shown as neither
