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
    for created in ("kea.yaml", "doc/_schema.yaml", "doc/first/goal/home.md", ".env", "CLAUDE.md", "Makefile"):
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
