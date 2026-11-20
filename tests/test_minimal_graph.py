"""The build's notes for a minimal graph (docsite/nodes.py _minimal_graph_notes): one ask per question, short
titles and texts, limits kept as caveat pages."""
from __future__ import annotations

from types import SimpleNamespace

from kea.docsite import nodes


def notes_for(type_: str, title: str, body: str = "", short: str = "", limited: bool = False) -> list[str]:
    tree = SimpleNamespace(notes=[])
    node = SimpleNamespace(type=type_, title=title, body=body, short=short, key="ex:x")
    nodes._minimal_graph_notes(tree, "x.md", node, {"ex:x"} if limited else set())
    return tree.notes


def test_a_question_that_asks_two_things_is_noted():
    assert any("asks 2 things" in note for note in notes_for("question", "How does it differ by cohort, and how does it relate to QC?"))
    assert any("asks 2 things" in note for note in notes_for("question", "Does it go up?", "1. Does it go up? 2. Why does it?"))
    assert notes_for("question", "Does the value differ between cohorts?") == []


def test_long_titles_and_texts_are_noted_and_prose_only_is_counted():
    assert any("title has 17 words" in note for note in notes_for("result", " ".join(["word"] * 17)))
    table = "| a | b |\n|---|---|\n" + "| x y z | u v w |\n" * 50
    assert notes_for("question", "Does it go up?", table + "```\n" + "code " * 200 + "\n```\nShort text.") == []
    assert any("text has 100 words" in note for note in notes_for("question", "Does it go up?", "word " * 100))
    assert nodes.prose_words("See [[c-x|the conclusion]] and [[r-y]].") == 5


def test_a_limit_in_the_text_without_a_caveat_is_noted():
    body = "This result has a limitation: the cohorts differ."
    assert any("caveat page" in note for note in notes_for("result", "Counts per donor", body))
    assert notes_for("result", "Counts per donor", body, limited=True) == []
    assert notes_for("caveat", "Cohorts differ", body) == []
