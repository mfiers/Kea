"""Tests for the PDF export (kea.docsite.pdf): HTML-to-Typst conversion, and a full compile when Typst is present."""
import json
import shutil
import subprocess

import pytest

from kea.docsite import nodes, pdf

from test_docsite import toy_doc, write_page  # noqa: F401  (fixture)


def test_text_escapes_markup_characters():
    escaped = pdf.text("a*b_c #x [y] $z @w <v> 1. item // no comment")
    for index, character in enumerate(escaped):
        if character in "*_#[]$@<>/" or (character == "." and escaped[index - 1].isdigit()):
            assert escaped[index - 1] == "\\", (character, escaped)
    assert pdf.text("two\n  lines") == "two lines"


def test_converter_handles_links_lists_tables_and_code():
    converter = pdf.Converter({"proj/q-a.html": "proj:q-a"})
    markup = converter.convert(
        f"<p>See <a class='ref' href='{pdf.SENTINEL}proj/q-a.html'>Q1</a>, "
        "<a href='https://example.org'>web</a> and <a href='../code/x.html'>code</a>.</p>"
        "<ul><li>one <code>x[1]</code></li><li><strong>two</strong></li></ul>"
        "<table><thead><tr><th>a</th><th>b</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>"
        "<pre>for i in x:\n    \"quoted\"</pre>")
    assert "#nlink(<proj:q-a>)[Q1]" in markup
    tagged = converter.convert(f"<p><a class='tag t-question' href='{pdf.SENTINEL}proj/q-a.html'><svg><path/></svg>Q1</a></p>"
                               f"<ul><li><a class='tagline' href='{pdf.SENTINEL}proj/q-a.html'><span class='tag t-question'>"
                               f"<svg></svg>Q1</span><span class='tl-text'>the line</span></a></li></ul>")
    assert tagged.startswith('#nlink(<proj:q-a>)[#tag("#1f77b4", ')            # the tag is the link
    assert "#text(fill: ink)[the line]] #h(0.4em) #h(1fr) #pagenum(<proj:q-a>)" in tagged   # one link, page at the end
    assert '#link("https://example.org")[web]' in markup
    assert "code" in markup and "../code" not in markup              # local site links become plain text
    assert '#list([one #icode[x\\[1\\]]], [#strong[two]])' in markup      # inline code can break (no #raw)
    assert "#datatable(2, 8pt, 1, table.header([a], [b]), [1], [])" in markup   # short row padded
    assert '#raw(block: true, "for i in x:\\n    \\"quoted\\"")' in markup


@pytest.mark.skipif(pdf.typst_command() is None, reason="typst not installed")
def test_toy_tree_compiles(toy_doc, tmp_path):
    write_page(toy_doc, "proj/term/t-x.md", "id: t-x\ntype: term\ntitle: Thing\nshort: A thing.\nparent: home")
    tree = nodes.load_tree(toy_doc)
    writer = pdf.PdfWriter(tree)
    source = writer.document()
    fixed = {"version": "-", "commit": "-", "built": "-"}
    assert writer.document(fixed) == writer.document(fixed)        # repeatable (the site cache renders it twice)
    assert "<proj:r-a>" in source and "== Glossary" in source and "<kea-about>" in source
    assert "== Overview of all pages" in source and "Appendix" not in source
    assert source.index("== At a glance") < source.index("<proj:q-a>") < source.index("<proj:r-a>")
    assert "#chapter(" not in source.split("#chapter(none)")[0].split("#outline")[1]   # one experiment: no chapter page
    assert "#tag(" in source and "Document version " in source and "Site version" not in source
    logo = tmp_path / pdf.pdf_logo().lstrip("/")          # the title page's logo, inside the compile root
    logo.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf.PROJECT_ROOT / pdf.pdf_logo().lstrip("/"), logo)
    typ = tmp_path / "toy.typ"
    typ.write_text(source)
    result = subprocess.run([pdf.typst_command(), "compile", "--root", str(tmp_path), str(typ),
                             str(tmp_path / "toy.pdf")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "toy.pdf").stat().st_size > 1000


def test_typst_command_follows_settings(monkeypatch):
    monkeypatch.setitem(pdf.SETTINGS, "typst", "/nonexistent/typst")
    assert pdf.typst_command() is None
    monkeypatch.setitem(pdf.SETTINGS, "typst", "")
    assert pdf.typst_command() == shutil.which("typst")


def test_drop_section_removes_abstract_only():
    text = "Intro.\n\n## Abstract\n\nLong abstract.\n\n### Detail\n\nmore\n\n## Why it is here\n\nReason."
    kept = pdf.drop_section(text, "Abstract")
    assert "Long abstract" not in kept and "more" not in kept and "Reason." in kept and "Intro." in kept


def test_repository_url_from_settings_or_git_remote(monkeypatch):
    monkeypatch.setitem(pdf.SETTINGS, "repository", "https://example.org/x")
    assert pdf.repository_url() == "https://example.org/x"
    monkeypatch.setitem(pdf.SETTINGS, "repository", "")

    class Done:
        stdout = "git@github.com:someone/project.git\n"
    monkeypatch.setattr(pdf.subprocess, "run", lambda *args, **kwargs: Done())
    assert pdf.repository_url() == "https://github.com/someone/project"


def test_changed_inputs_names_what_changed(tmp_path):
    import json
    (tmp_path / "old.json").write_text(json.dumps({"version": "v1", "inputs": {"(typst source)": "a", "fig.png": "1"}}))
    assert pdf.changed_inputs(tmp_path, {"(typst source)": "a", "fig.png": "2"}) == "changed fig.png"
    assert pdf.changed_inputs(tmp_path / "none", {}) == "no earlier PDF in the cache"


def test_punctuation_after_markup_survives():
    """'; (' after bold, code or a link would end or continue the Typst expression and vanish."""
    converter = pdf.Converter({})
    markup = converter.convert("<p><strong>public API</strong>; the local <code>x</code>(y). <em>z</em>.w</p>")
    assert "#strong[public API]\\;" in markup and "#icode[x]\\(y)" in markup and "#emph[z]\\.w" in markup


def test_code_text_breaks_long_paths():
    assert pdf.code_text("data/final/a_b.tsv").count(pdf.ZWSP) == 4


def test_natural_sort_and_term_groups(toy_doc):
    assert sorted(["S100A10", "S100A2", "S100B", "S100A1"], key=pdf.natural) == ["S100A1", "S100A2", "S100A10", "S100B"]
    write_page(toy_doc, "proj/term/t-g.md", "id: t-g\ntype: term\ntitle: S100A8\nshort: A gene.\nparent: home")
    write_page(toy_doc, "proj/term/t-c.md", "id: t-c\ntype: term\ntitle: Microglia\nshort: Cells.\nparent: home")
    write_page(toy_doc, "proj/term/t-p.md", "id: t-p\ntype: term\ntitle: p11\nshort: A protein.\ngroup: Proteins\nparent: home")
    tree = nodes.load_tree(toy_doc)
    groups = {name: [term.title for term in terms] for name, terms in
              pdf.term_groups([node for node in tree.nodes.values() if node.type == "term"])}
    assert groups[""] == ["Microglia"] and groups["Genes"] == ["S100A8"] and groups["Proteins"] == ["p11"]


def test_figure_printed_at_its_own_size(tmp_path):
    import struct
    import zlib

    def png(path, width, height, per_metre):
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
                         + chunk(b"pHYs", struct.pack(">IIB", per_metre, per_metre, 1)) + chunk(b"IEND", b""))
    png(tmp_path / "small.png", 1181, 600, 11811)            # 10 cm wide at 300 dpi: printed at 10 cm
    assert pdf.figure_width(tmp_path / "small.png") == ("10.0cm", 1.0)
    png(tmp_path / "wide.png", 3543, 1000, 11811)            # 30 cm wide: narrowed to the text width
    width, scale = pdf.figure_width(tmp_path / "wide.png")
    assert width == f"{pdf.TEXT_WIDTH_CM:.1f}cm" and scale < 0.6


def test_nature_citation():
    from kea.docsite import cite
    record = {"authorList": {"author": [{"lastName": "Smith", "initials": "AB"}, {"lastName": "Jones", "initials": "C"}]},
              "title": "A study.", "journalInfo": {"journal": {"isoabbreviation": "Nat Med"}, "volume": "13",
                                                   "yearOfPublication": 2007}, "pageInfo": "1042-1049"}
    assert cite.nature(record) == "Smith, A. B. & Jones, C. A study. *Nat Med* **13**, 1042–1049 (2007)."
    many = dict(record, authorList={"author": [{"lastName": f"N{i}", "initials": "X"} for i in range(7)]})
    assert cite.nature(many).startswith("N0, X. et al. A study.")


def test_resource_body_reaches_the_pdf(toy_doc):
    write_page(toy_doc, "proj/resource/o-db.md", "id: o-db\ntype: resource\ntitle: Server\nshort: Data.\nparent: home\n"
               "status: current\nkind: database\nversion: '3'\nretrieved: 2026-11-06",
               "| dataset | version |\n|---|---|\n| X1 | 2 |")
    source = pdf.PdfWriter(nodes.load_tree(toy_doc)).document({"version": "-", "commit": "-", "built": "-"})
    assert "== Data and resources" in source and "[X1]" in source


def test_a_record_from_a_source_is_its_own_resource(toy_doc):
    write_page(toy_doc, "proj/reference/ref-study.md", "id: ref-study\ntype: reference\ntitle: Smith 2020\n"
               "short: The study.\nparent: home")
    write_page(toy_doc, "proj/resource/o-gwas.md", "id: o-gwas\ntype: resource\ntitle: GWAS Catalog\nshort: Catalog.\n"
               "parent: home\nstatus: current\nkind: database\nversion: '2026-10'\nretrieved: 2026-11-06")
    write_page(toy_doc, "proj/resource/o-gcst.md", "id: o-gcst\ntype: resource\ntitle: A GWAS study\nshort: Study.\n"
               "parent: home\nstatus: current\nkind: dataset\naccession: GCST90027158\nversion: '1'\n"
               "retrieved: 2026-11-06\nsha256: abc\nrelations:\n  part_of: [o-gwas]\n  cites: [ref-study]")
    tree = nodes.load_tree(toy_doc)
    assert tree.problems == [] and tree.nodes["proj:o-gwas"].incoming["Contains"] == ["proj:o-gcst"]
    source = pdf.PdfWriter(tree).document({"version": "-", "commit": "-", "built": "-"})
    assert "GCST90027158" in source and "[Part of]" in source and "[Paper]" in source and "[Contains]" in source


def test_crossref_fallback_shapes_a_record(monkeypatch):
    import io
    import json
    from kea.docsite import cite
    work = {"message": {"author": [{"family": "Storey", "given": "John D."}], "title": ["A direct approach"],
                        "short-container-title": ["J R Stat Soc B"], "volume": "64", "page": "479-498",
                        "issued": {"date-parts": [[2002, 8]]}}}
    monkeypatch.setattr(cite.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(json.dumps(work).encode()))
    assert cite.nature(cite.fetch_crossref("10.1/x")) == "Storey, J. D. A direct approach. *J R Stat Soc B* **64**, 479–498 (2002)."


def test_citations_are_inline_tags_not_superscript(toy_doc):
    write_page(toy_doc, "proj/reference/ref-a.md", "id: ref-a\ntype: reference\ntitle: Smith 2020\nshort: A paper.\n"
               "parent: home")
    write_page(toy_doc, "proj/result/r-c.md", "id: r-c\ntype: result\ntitle: R\nshort: A result.\nparent: home\n"
               "status: done\nsources:\n  - data: x.tsv", "As shown before ([[ref-a]]).")
    source = pdf.PdfWriter(nodes.load_tree(toy_doc)).document({"version": "-", "commit": "-", "built": "-"})
    assert "#nlink(<proj:ref-a>)[#tag(" in source and "#cite(" not in source and "baseline: -0.42em" not in source


def test_methods_steps_name_their_questions_results_and_conclusions(toy_doc):
    write_page(toy_doc, "proj/step/s-a.md", "id: s-a\ntype: step\ntitle: Do it\nshort: A step.\nparent: home\nstatus: done")
    write_page(toy_doc, "proj/result/r-s.md", "id: r-s\ntype: result\ntitle: Out\nshort: A result.\nparent: s-a\n"
               "status: done\nrelations:\n  answers: [q-a]\nsources:\n  - data: x.tsv")
    write_page(toy_doc, "proj/conclusion/c-s.md", "id: c-s\ntype: conclusion\ntitle: So\nshort: Hence.\nparent: home\n"
               "status: supported\nrelations:\n  supported_by: [r-s]")
    writer = pdf.PdfWriter(nodes.load_tree(toy_doc))
    source = writer.document({"version": "-", "commit": "-", "built": "-"})
    methods = source.split("== Methods")[1]
    assert "#strong[Used for:]" in methods and "#strong[Leads to results:]" in methods \
        and "#strong[Leads to conclusions:]" in methods


def test_no_pdf_build_keeps_the_last_built_pdf(tmp_path, monkeypatch):
    """`kea build --no-pdf` puts the PDF of the last full build on the site instead of dropping it."""
    monkeypatch.setattr(pdf, "PROJECT_ROOT", tmp_path)
    monkeypatch.setitem(pdf.SETTINGS, "title", "My Project")
    site = tmp_path / "site"
    site.mkdir()
    assert pdf.last_pdf(site) is None                       # nothing built yet
    cache = tmp_path / "report" / "pdf" / "_cache"
    cache.mkdir(parents=True)
    for key, version in (("older", "v0.1.0"), ("served", "v0.2.0")):
        (cache / f"{key}.pdf").write_bytes(b"%PDF " + version.encode())
        (cache / f"{key}.json").write_text(json.dumps({"version": version, "commit": "abc", "built": "x",
                                                        "inputs": {}}))
    (cache / pdf.LAST).write_text(json.dumps({"key": "served"}))
    kept = pdf.last_pdf(site)
    assert kept["file"] == "my-project-v0.2.0.pdf" and kept["reused"]
    assert (site / "my-project-v0.2.0.pdf").read_bytes() == b"%PDF v0.2.0"

