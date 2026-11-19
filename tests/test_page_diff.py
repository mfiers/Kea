"""The per-page diff in 'Changes to this page' (comments.text_diff_html): changed lines only, as word diffs."""
from kea.docsite.comments import text_diff_html


def test_word_diff_marks_only_the_changed_words():
    old = "---\ntitle: It goes up\ncriterion: q below 0.05\n---\nSame paragraph.\n"
    new = "---\ntitle: It goes up\ncriterion: q below 0.01\n---\nSame paragraph.\n\nA new paragraph.\n"
    shown = text_diff_html(old, new)
    assert "<del>0.05</del><ins>0.01</ins>" in shown
    assert "title: It goes up" not in shown and "Same paragraph" not in shown    # unchanged lines are left out
    assert "<ins>A new paragraph.</ins>" in shown


def test_no_change_gives_nothing_and_text_is_escaped():
    assert text_diff_html("a\nb\n", "a\nb\n") == ""
    assert "&lt;b&gt;" in text_diff_html("x\n", "<b>\n")
