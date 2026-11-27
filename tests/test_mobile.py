"""Phone layout guards (1.37.1): a list item that starts with several page links stays plain links (it once became
one unbreakable link that ran off a phone screen), and the menu bar keeps room for the home logo."""
from kea.docsite import render


def _tag(name: str) -> str:
    return f"<a class='tag t-question' href='x/{name}.html' title='{name} · t'>{name}</a>"


def test_an_item_with_several_page_links_is_left_alone():
    item = f"<ul><li>{_tag('Q3')} and {_tag('Q6')} and {_tag('Q7')} are named as the questions.</li></ul>"
    assert render.tagline_items(item) == item


def test_an_item_with_one_page_link_becomes_one_tagline():
    out = render.tagline_items(f"<ul><li>{_tag('Q3')}: what it asks</li></ul>")
    assert "class='tagline'" in out and "<span class='tl-text'>what it asks</span>" in out


def test_the_menu_bar_keeps_room_for_the_logo():
    assert ".topbar .trail{display:flex;align-items:center;gap:7px;min-width:28px;" in render.CSS
