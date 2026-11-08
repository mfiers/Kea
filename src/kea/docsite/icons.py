"""Monochrome icons for the page types (tags on the site and in the PDF).

Line drawings on a 24 x 24 grid, drawn with the current colour (stroke, no fill), in the style of Feather Icons
(MIT licence, https://feathericons.com); some shapes follow Feather's. One icon per page type; unknown types get
the plain page icon.
"""
from __future__ import annotations

PATHS = {
    "experiment": "<circle cx='12' cy='12' r='9.5'/><circle cx='12' cy='12' r='5.5'/><circle cx='12' cy='12' r='1.6'/>",
    "premise": "<path d='M12 2 2 7l10 5 10-5-10-5z'/><path d='M2 17l10 5 10-5'/><path d='M2 12l10 5 10-5'/>",
    "question": "<circle cx='12' cy='12' r='10'/><path d='M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3'/>"
                "<path d='M12 17h.01'/>",
    "hypothesis": "<path d='M9 18h6'/><path d='M10 22h4'/>"
                  "<path d='M12 2a7 7 0 0 0-4 12.7V16h8v-1.3A7 7 0 0 0 12 2z'/>",
    "step": "<circle cx='12' cy='12' r='10'/><path d='M7 12h10'/><path d='M13 8l4 4-4 4'/>",
    "result": "<path d='M3 21h18'/><path d='M6 21v-7'/><path d='M11 21V7'/><path d='M16 21v-11'/>"
              "<path d='M21 21V4'/>",
    "conclusion": "<circle cx='12' cy='12' r='10'/><path d='M7.5 12.5l3 3 6-7'/>",
    "decision": "<circle cx='6' cy='19' r='2.5'/><circle cx='18' cy='6' r='2.5'/><path d='M6 3v13.5'/>"
                "<path d='M18 8.5a9 9 0 0 1-9 9'/>",
    "figure": "<rect x='3' y='3' width='18' height='18' rx='2'/><circle cx='8.5' cy='8.5' r='1.6'/>"
              "<path d='M21 15l-5-5L5 21'/>",
    "artefact": "<ellipse cx='12' cy='5' rx='9' ry='3'/><path d='M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5'/>"
                "<path d='M3 12c0 1.7 4 3 9 3s9-1.3 9-3'/>",
    "caveat": "<path d='M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z'/>"
              "<path d='M12 9v4'/><path d='M12 17h.01'/>",
    "term": "<path d='M4 19.5A2.5 2.5 0 0 1 6.5 17H20'/>"
            "<path d='M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z'/>",
    "resource": "<path d='M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z'/>"
                "<path d='M3.3 7 12 12l8.7-5'/><path d='M12 22V12'/>",
    "reference": "<path d='M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z'/>",
    "page": "<path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/><path d='M14 2v6h6'/>",
    "edit": "<path d='M12 20h9'/><path d='M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z'/>",
}


def svg(kind: str, colour: str = "currentColor", size: int | None = None, css_class: str = "ico") -> str:
    """Inline SVG of the icon for a page type (or 'edit'); `colour` is the stroke colour."""
    paths = PATHS.get(kind, PATHS["page"])
    dimensions = f" width='{size}' height='{size}'" if size else ""
    return (f"<svg class='{css_class}' viewBox='0 0 24 24'{dimensions} fill='none' stroke='{colour}' "
            f"stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'>{paths}</svg>")


def standalone(kind: str, colour: str) -> str:
    """A self-contained SVG document (for Typst's image(bytes(...)))."""
    return svg(kind, colour, 24, "").replace("<svg class='' ", "<svg xmlns='http://www.w3.org/2000/svg' ", 1)
