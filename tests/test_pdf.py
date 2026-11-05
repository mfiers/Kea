"""Tests for the PDF export (kea.docsite.pdf): HTML-to-Typst conversion, and a full compile when Typst is present."""
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
    assert '#link("https://example.org")[web]' in markup
    assert "code" in markup and "../code" not in markup              # local site links become plain text
    assert '#list([one #raw("x[1]")], [#strong[two]])' in markup
    assert "#datatable(2, 8pt, 1, table.header([a], [b]), [1], [])" in markup   # short row padded
    assert '#raw(block: true, "for i in x:\\n    \\"quoted\\"")' in markup


@pytest.mark.skipif(pdf.typst_command() is None, reason="typst not installed")
def test_toy_tree_compiles(toy_doc, tmp_path):
    write_page(toy_doc, "proj/term/t-x.md", "id: t-x\ntype: term\ntitle: Thing\nshort: A thing.\nparent: home")
    tree = nodes.load_tree(toy_doc)
    writer = pdf.PdfWriter(tree)
    source = writer.document()
    assert "<proj:r-a>" in source and "== Glossary" in source and "<kea-about>" in source
    assert source.index("== At a glance") < source.index("<proj:q-a>") < source.index("<proj:r-a>")
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
