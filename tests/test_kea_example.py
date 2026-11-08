"""An example project from scratch: kea init, one page, kea build (in a subprocess, its own project root)."""
import os
import subprocess
import sys
from pathlib import Path


def run(arguments, cwd, **extra):
    environment = {**os.environ, "KEA_PROJECT": str(cwd), **extra}
    return subprocess.run([sys.executable, "-m", "kea.cli", *arguments], cwd=cwd, env=environment,
                          capture_output=True, text=True, timeout=120)


def test_init_and_build_example_project(tmp_path):
    project = tmp_path / "example"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    result = run(["init", "--title", "Example", "--experiment", "first", "--question", "Does it work?"], project)
    assert result.returncode == 0, result.stderr
    for created in ("kea.yaml", "doc/_schema.yaml", "doc/first/experiment/home.md", ".env", "CLAUDE.md", "Makefile"):
        assert (project / created).exists(), created
    assert "SITE_PASSWORD=" in (project / ".env").read_text()
    again = run(["init", "--title", "Example"], project)                   # idempotent, never overwrites
    assert "kept" in again.stdout and (project / "CLAUDE.md").read_text().count("kea:start") == 1
    (project / "doc" / "first" / "result").mkdir()
    (project / "doc" / "first" / "result" / "r-one.md").write_text(
        "---\nid: r-one\ntype: result\ntitle: One result\nshort: It works.\nparent: home\nstatus: done\n"
        "sources:\n  - data: data/x.tsv\n---\nSee [[home]].\n")
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "start"], cwd=project,
                   check=True)
    built = run(["build", "--strict"], project)
    assert built.returncode == 0, built.stdout + built.stderr
    site = project / "report" / "site"
    for page in ("index.html", "first/home.html", "first/r-one.html", "first/relations.html", "plan.html",
                 "history.html", "feedback.html"):
        assert (site / page).exists(), page
    assert "Example" in (site / "index.html").read_text()


def test_build_modes(tmp_path):
    project = tmp_path / "example"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    run(["init", "--title", "Example", "--experiment", "first"], project)
    (project / "data").mkdir(exist_ok=True)
    (project / "data" / "table.tsv").write_text("donor\tvalue\ndonor-zx81\t3\n")
    (project / "doc" / "first" / "result").mkdir()
    (project / "doc" / "first" / "artefact").mkdir()
    (project / "doc" / "first" / "step").mkdir()
    (project / "doc" / "first" / "step" / "s-one.md").write_text(
        "---\nid: s-one\ntype: step\ntitle: A step\nshort: It ran.\nparent: home\nstatus: done\n---\n")
    (project / "doc" / "first" / "artefact" / "a-table.md").write_text(
        "---\nid: a-table\ntype: artefact\ntitle: The table\nshort: Per-donor values.\nparent: s-one\n"
        "status: current\npath: data/table.tsv\nformat: tsv\naccess: controlled\nrelations:\n  made_by: [s-one]\n---\n")
    (project / "doc" / "first" / "result" / "r-one.md").write_text(
        "---\nid: r-one\ntype: result\ntitle: One result\nshort: It works.\nparent: home\nstatus: done\n"
        "sources:\n  - data: data/table.tsv\n---\nSee [[a-table]].\n")
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "start"], cwd=project,
                   check=True)
    assert run(["build", "--mode", "local"], project).returncode == 0
    local = (project / "report" / "site-local" / "first" / "r-one.html").read_text()
    assert "../../../data/table.tsv" in local and "fb-script" not in local
    outside = tmp_path / "public-copy"
    assert run(["build", "--mode", "public", "--out", str(outside)], project).returncode == 0
    pages = "".join(path.read_text() for path in outside.rglob("*.html"))
    assert "data/table.tsv' download" not in pages and "/files/" not in pages and "fb-script" not in pages
    assert "donor-zx81" not in pages                                          # controlled preview left out
    assert not (outside / "plan.html").exists() and not (outside / "feedback.html").exists()
    assert (outside / "_public_report.json").exists()
    refused = run(["build", "--mode", "local", "--out", str(outside)], project)
    assert refused.returncode != 0                                            # local must stay inside the project
    refused = run(["build", "--mode", "public", "--out", str(project / "data" / "site")], project)
    assert refused.returncode != 0                                            # never into data/
