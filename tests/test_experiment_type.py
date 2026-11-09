"""The experiment's home page has type experiment; the old name goal (before Kea 1.12) still loads, with a note."""
from __future__ import annotations

from pathlib import Path

from kea.docsite import nodes

SCHEMA = (Path(nodes.__file__).resolve().parents[1] / "templates" / "_schema.yaml").read_text()


def _page(doc: Path, relative: str, front: str) -> None:
    path = doc / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front}\n---\nText.\n")


def test_experiment_type_and_legacy_goal(tmp_path):
    doc = tmp_path / "doc"
    doc.mkdir()
    (doc / "_schema.yaml").write_text(SCHEMA)
    (doc / "_summary.md").write_text("Two experiments.\n")
    _page(doc, "new/experiment/home.md", "id: home\ntype: experiment\ntitle: New\nshort: A new one.\nstatus: open")
    _page(doc, "old/goal/home.md", "id: home\ntype: goal\ntitle: Old\nshort: An old one.\nstatus: open")
    tree = nodes.load_tree(doc)
    assert tree.problems == []
    assert {project: home.type for project, home in tree.projects.items()} == {"new": "experiment", "old": "experiment"}
    assert any("old/goal/home.md: type goal is called experiment" in note for note in tree.notes)
    assert not any(note.startswith("new/") for note in tree.notes)
