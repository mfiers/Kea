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
    progress = (site / "progress.html").read_text()                     # Plan → Progress
    assert "Route of each question" in progress and "Approve &amp; propose questions" in progress
    assert "progress.html" in (site / "first" / "home.html").read_text()


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


def test_figures_are_featured_embedded_and_provenance_folds(tmp_path):
    """A result shows its figure in full after its text, under a Figures separator (take-home once, the rest folded); ![[f-…]] places a
    figure in the text instead; a conclusion shows its results' first figures as a strip; steps fold under
    Provenance; the page history is one line per version."""
    import base64
    project = tmp_path / "example"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    run(["init", "--title", "Example", "--experiment", "first"], project)
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    (project / "report" / "figures").mkdir(parents=True)
    (project / "report" / "figures" / "a.png").write_bytes(png)
    (project / "report" / "figures" / "a.caption.md").write_text(
        "# a\n\n**The take-home line.**\n\n*Shows:* x. *Method:* y. *Statistics:* none.\n")
    pages = {
        "step/s-one.md": "id: s-one\ntype: step\ntitle: A step\nshort: It ran.\nparent: home\nstatus: done",
        "result/r-one.md": "id: r-one\ntype: result\ntitle: One\nshort: It works.\nparent: home\nstatus: done\n"
                           "relations:\n  shown_in: [f-a]\n  made_by: [s-one]",
        "result/r-two.md": "id: r-two\ntype: result\ntitle: Two\nshort: Also.\nparent: home\nstatus: done\n"
                           "relations:\n  shown_in: [f-a]\n---\nBefore.\n\n![[f-a]]\n\nAfter.\n",
        "figure/f-a.md": "id: f-a\ntype: figure\ntitle: Fig\nshort: The take-home line.\nparent: r-one\nstatus: done\n"
                         "image: report/figures/a.png\ncaption_file: report/figures/a.caption.md",
        "conclusion/c-one.md": "id: c-one\ntype: conclusion\ntitle: C\nshort: So.\nparent: home\nstatus: supported\n"
                               "certainty: low\ncertainty_because: small.\nrelations:\n  supported_by: [r-one]",
    }
    for relative, header in pages.items():
        path = project / "doc" / "first" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        header, _, body = header.partition("\n---\n")
        path.write_text(f"---\n{header}\n---\n{body}")
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "start"], cwd=project,
                   check=True)
    built = run(["build", "--no-pdf"], project)
    assert built.returncode == 0, built.stdout + built.stderr
    site = project / "report" / "site" / "first"
    one = (site / "r-one.html").read_text()
    # the page's own content first, then the figures under their own separator, then About this page
    assert one.index("</article>") < one.index(">Figures</span>") < one.index("class='featured") < one.index("About this page")
    import re
    visible = lambda html: re.sub(r"title='[^']*'", "", html)              # hover texts aside
    assert visible(one).count("The take-home line.") == 1 and "<details><summary>Shows, method and statistics" in one
    assert "class='thumb'" not in one and "details class='provenance'" in one
    two = (site / "r-two.html").read_text()
    article = two.split("<article>")[1]
    assert article.index("Before.") < article.index("class='featured") < article.index("After.")
    assert two.count("class='featured") == 1                                   # placed by the embed, not twice
    assert "class='figure-strip" in (site / "c-one.html").read_text()
    figure_page = (site / "f-a.html").read_text()
    assert visible(figure_page).count("The take-home line.") == 1        # the summary box only
    assert "class='page-versions'" in one and "<pre class='diff'>" not in one


def test_experiment_lists_questions_then_answers_and_has_no_files(tmp_path):
    """An experiment page: after its text, tabs under one separator: Questions (one line each), Answers so far (the
    answer and a link to the conclusion, not its text), About this page (its hypotheses, steps, results and
    conclusions, filtered by kind; no terms), then Changes. No Figures separator. An artefact directly under the
    experiment is a problem."""
    project = tmp_path / "example"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    run(["init", "--title", "Example", "--experiment", "first"], project)
    pages = {
        "question/q-one.md": "id: q-one\ntype: question\ntitle: Does it work?\nshort: Whether it works.\nparent: home\n"
                             "status: answered\nanswer: It does, a little.",
        "conclusion/c-one.md": "id: c-one\ntype: conclusion\ntitle: It works a little\nshort: Conclusion summary text.\n"
                               "parent: q-one\nstatus: supported\ncertainty: low\ncertainty_because: small.",
        "term/t-word.md": "id: t-word\ntype: term\ntitle: Wordy\nshort: A word.\nparent: home",
    }
    for relative, header in pages.items():
        path = project / "doc" / "first" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\n{header}\n---\n")
    subprocess.run(["git", "add", "-A"], cwd=project, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "start"], cwd=project,
                   check=True)
    built = run(["build", "--no-pdf"], project)
    assert built.returncode == 0, built.stdout + built.stderr
    home = (project / "report" / "site" / "first" / "home.html").read_text()
    import re
    tabs = re.findall(r"class='sep-tab[^']*' role='tab' data-tab='(\w+)'", home)
    assert tabs == ["questions", "answers", "about", "changes"], tabs
    assert home.count("class='node-data-sep") == 1                       # one separator, the rest are tabs
    panel = lambda key: home.split(f"role='tabpanel' data-tab='{key}'")[1].split("role='tabpanel'")[0]
    listed = re.sub(r"title='[^']*'", "", panel("questions"))           # the summary only on hover
    assert "Does it work?" in listed and "Whether it works." not in listed
    answers = re.sub(r"title='[^']*'", "", panel("answers"))
    assert "It does, a little." in answers and "c-one.html" in answers and "Conclusion summary text." not in answers
    about = panel("about")
    assert "Pages of this experiment" in about and "data-kind='conclusion'" in about and "t-word.html" not in about
    assert ">Figures" not in home
    assert "_assets/kea.js" in home and (project / "report" / "site" / "_assets" / "kea.js").exists()
    assert "objects.html#type=term'" in home                               # terms: under Map
    comments_page = (project / "report" / "site" / "comments.html").read_text()     # Plan → Current comments
    assert "id='comments-data'" in comments_page and "_assets/comments.js" in comments_page
    assert "href='../comments.html'" in home and (project / "report" / "site" / "_assets" / "comments.js").exists()
    artefact = project / "doc" / "first" / "artefact" / "a-table.md"
    artefact.parent.mkdir(parents=True, exist_ok=True)
    artefact.write_text("---\nid: a-table\ntype: artefact\ntitle: T\nshort: A table.\nparent: home\npath: data/t.tsv\n---\n")
    checked = run(["check"], project)
    assert checked.returncode != 0 and "artefact directly under the experiment" in checked.stdout
