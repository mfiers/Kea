"""Second round of Kea logos (2026-11-08): a stained-glass kea built from the site's page-type colours, and a round
version for the menu bar, the page-button dock and the favicon. Generated with image models on OpenRouter (key:
OPENROUTER_API_KEY in the environment); the current icon (icon-512.png) is sent along as a shape reference.

Input: icon-512.png. Output: candidates/<name>_gemini.png and records (model, prompt, date, outcome) appended to
candidates/record.json. Usage: python make_logo2.py [names…]   (needs network access; a few cents per image)
Existing candidate files are never overwritten.
"""
import base64
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "candidates"
MODEL = "google/gemini-3-pro-image"

# the site's page-type colours (src/kea/docsite/render.py TYPE_COLOURS)
PALETTE = ("premise purple #6a4c93, question blue #1f77b4, hypothesis violet #9467bd, step green #2a7f62, "
           "result brown #8c564b, conclusion red #c0392b, figure teal #17818a, artefact gold #b8860b, "
           "caveat orange #d35400, resource olive #5b6b2f")
STYLE = ("Stained-glass style: the bird is made of many flat polygonal glass facets separated by dark charcoal "
         "lead lines (#2b2b2b) of even width, like nodes and edges of a knowledge graph. The bird stays mostly green "
         "(olive #5b6b2f and green #2a7f62 facets dominate), with orange (#d35400) and gold (#b8860b) facets under "
         "the wing and on the tail; small accent facets in exactly these colours are scattered through the body: "
         f"{PALETTE}. Flat colours only, no gradients, no shading, no glow, no text.")
CANDIDATES = {
    "kea_glass_ref": ("Redraw the kea parrot of the attached image, keeping its pose and silhouette, as a logo. "
                      + STYLE + " Only the bird, centred, plain white background, square."),
    "kea_glass_free": ("A logo: a kea (New Zealand alpine parrot) standing in side view, strong hooked beak, small dark "
                       "eye. " + STYLE + " Only the bird, centred, plain white background, square."),
    "kea_glass_graph": ("Redraw the kea parrot of the attached image, keeping its pose and silhouette, as a logo in "
                        "which the body is visibly a network: the lead lines meet at small round dark nodes, as in a "
                        "graph drawing. " + STYLE + " Only the bird, centred, plain white background, square."),
    "kea_round_head": ("A circular logo badge: the head and hooked beak of the kea from the attached image, in "
                       "profile, filling a circle. " + STYLE + " Large, simple facets (at most about 20) so that it "
                       "still reads at 16 pixels. The circle has a thick dark charcoal (#2b2b2b) rim and a white "
                       "background inside, behind the head. Outside the circle: plain white. Square image."),
    "kea_round_bird": ("A circular logo badge: the whole kea from the attached image, standing, inside a circle. "
                       + STYLE + " Large, simple facets so that it still reads at 16 pixels. Thick dark charcoal "
                       "(#2b2b2b) circle rim, white inside the circle. Outside the circle: plain white. Square image."),
    "kea_round_head_bold": ("A circular app icon: a bold kea head in profile, the hooked beak pointing right, made of "
                            "about 12 large flat stained-glass facets with thick dark lead lines, mostly green "
                            "(#5b6b2f, #2a7f62) with one orange (#d35400) facet at the cheek and one violet "
                            "(#9467bd) and one blue (#1f77b4) accent facet; the head fills the circle; thick charcoal "
                            "(#2b2b2b) rim; white behind the head; plain white outside the circle; no text, no "
                            "gradients. Must read at 16 pixels. Square image."),
}
# second batch (same day): round heads drawn from the chosen full logo, beak olive and dark as in the real bird
ROUND_FROM_GLASS = ("A circular app icon made from the head of the stained-glass kea in the attached image: the head "
                    "and long hooked beak in profile, beak pointing right, cropped at the neck, filling most of the "
                    "circle. Keep its colours: olive (#5b6b2f) and green (#2a7f62) facets, a dark charcoal beak tip, "
                    "small dark eye, one orange (#d35400) facet at the cheek and one or two small accent facets in "
                    "violet #9467bd and blue #1f77b4. About 12 to 15 large flat facets with thick dark lead lines "
                    "(#2b2b2b). ")
CANDIDATES["kea_round_glass"] = (ROUND_FROM_GLASS + "Thick charcoal (#2b2b2b) circle rim, white behind the head, "
                                 "plain white outside the circle. No text, no gradients. Must read at 16 pixels. Square image.")
CANDIDATES["kea_round_glass_fill"] = (ROUND_FROM_GLASS + "The circle behind the head is filled with a few large pale "
                                      "glass facets (very light grey #eef0f3 and white) with thin lead lines; thick "
                                      "charcoal (#2b2b2b) circle rim; plain white outside the circle. No text, no "
                                      "gradients. Must read at 16 pixels. Square image.")
WITH_REFERENCE = {"kea_glass_ref", "kea_glass_graph", "kea_round_head", "kea_round_bird"}
REFERENCES = {"kea_round_glass": "candidates/kea_glass_ref_gemini.png", "kea_round_glass_fill": "candidates/kea_glass_ref_gemini.png"}


def generate(prompt: str, reference: Path | None) -> bytes:
    content: list = [{"type": "text", "text": prompt}]
    if reference is not None:
        encoded = base64.b64encode(reference.read_bytes()).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}})
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps({"model": MODEL, "modalities": ["image", "text"],
                         "messages": [{"role": "user", "content": content}]}).encode(),
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "Content-Type": "application/json",
                 "X-Title": "kea logo"})
    with urllib.request.urlopen(request, timeout=300) as response:
        reply = json.load(response)
    images = reply["choices"][0]["message"].get("images") or []
    if not images:
        raise RuntimeError(f"no image in reply: {str(reply)[:300]}")
    return base64.b64decode(images[0]["image_url"]["url"].split(",", 1)[1])


def main() -> int:
    record = []
    for name in sys.argv[1:] or list(CANDIDATES):
        target = OUT / f"{name}_gemini.png"
        if target.exists():
            continue
        reference = (HERE / REFERENCES[name] if name in REFERENCES else
                     HERE / "icon-512.png" if name in WITH_REFERENCE else None)
        try:
            target.write_bytes(generate(CANDIDATES[name], reference))
            status = "ok"
        except Exception as error:    # report and continue with the other candidates
            status = f"failed: {error}"
        print(target.name, status)
        record.append({"file": target.name, "model": MODEL, "prompt": CANDIDATES[name],
                       "reference": reference.name if reference else None, "status": status,
                       "date": dt.datetime.now().isoformat(timespec="seconds")})
    previous = json.loads((OUT / "record.json").read_text()) if (OUT / "record.json").exists() else []
    (OUT / "record.json").write_text(json.dumps(previous + record, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
