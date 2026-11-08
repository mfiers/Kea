"""Site assets from the 2026-11-08 stained-glass candidates (make_logo2.py), in the exact page-type colours.

Chosen: candidates/kea_glass_ref_gemini.png (full bird) and candidates/kea_round_glass_gemini.png (round head).
Each facet (a region between the charcoal lead lines) is set to the PALETTE colour nearest its mean colour (the site's
TYPE_COLOURS in src/kea/docsite/render.py, plus the charcoal lead and white), so the facets use exactly the site's
colours; see facets(). White that touches the image border becomes transparent (the white inside the round badge
stays). Then trimmed and resized.

Output (branding/): icon-glass-512.png, round-512.png. Copies in ../src/kea/docsite/static/ (used by the site):
kea-glass-512.png, kea-round-96.png (page-button dock), kea-round-64.png (menu bar), kea-favicon.ico (16/32/48).
"""
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).parent
STATIC = HERE.parent / "src" / "kea" / "docsite" / "static"
PALETTE = {"premise": "#6a4c93", "question": "#1f77b4", "hypothesis": "#9467bd", "step": "#2a7f62",
           "result": "#8c564b", "conclusion": "#c0392b", "figure": "#17818a", "artefact": "#b8860b",
           "caveat": "#d35400", "resource": "#5b6b2f", "lead": "#2b2b2b", "white": "#ffffff"}
COLOURS = np.array([[int(value[i:i + 2], 16) for i in (1, 3, 5)] for value in PALETTE.values()])
NAMES = list(PALETTE)
WHITE, LEAD = NAMES.index("white"), NAMES.index("lead")
ARTEFACT, RESOURCE = NAMES.index("artefact"), NAMES.index("resource")


def facets(path: Path, keep_enclosed_white: bool) -> Image.Image:
    """RGBA in exact palette colours: the lead lines (pixels nearest the charcoal) stay lead; every region between
    them (a facet) gets the palette colour nearest to its mean colour, so a facet is one flat colour without speckle.
    Light olive (yellow-green, which the palette lacks) goes to resource olive, not to artefact gold. Regions that
    touch the image border and are white become transparent; enclosed white stays only with keep_enclosed_white
    (the inside of the round badge; between the legs of the full bird it is a hole)."""
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(int)
    nearest = ((rgb[:, :, None, :] - COLOURS[None, None, :, :]) ** 2).sum(axis=3).argmin(axis=2)
    lead = nearest == LEAD
    labels, count = ndimage.label(~lead)
    sums = np.stack([ndimage.sum(rgb[:, :, channel], labels, range(1, count + 1)) for channel in range(3)], axis=1)
    sizes = ndimage.sum(np.ones(labels.shape), labels, range(1, count + 1))
    means = sums / np.maximum(sizes, 1)[:, None]
    choice = ((means[:, None, :] - COLOURS[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
    olive_like = (choice == ARTEFACT) & (means[:, 1] >= means[:, 0] - 8)
    choice[olive_like] = RESOURCE
    border = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))) - {0}
    out = np.zeros(labels.shape + (4,), dtype=np.uint8)
    out[lead] = [*COLOURS[LEAD], 255]
    for region in range(1, count + 1):
        colour = choice[region - 1]
        transparent = colour == WHITE and (region in border or not keep_enclosed_white)
        out[labels == region] = [*COLOURS[colour], 0 if transparent else 255]
    return Image.fromarray(out, "RGBA")


def trimmed(image: Image.Image, margin: int) -> Image.Image:
    box = image.getchannel("A").getbbox()
    image = image.crop(box)
    side = max(image.size) + 2 * margin
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    return square


def main() -> int:
    full = trimmed(facets(HERE / "candidates" / "kea_glass_ref_gemini.png", False), 8)
    full.resize((512, 512), Image.LANCZOS).save(HERE / "icon-glass-512.png")
    full.resize((512, 512), Image.LANCZOS).save(STATIC / "kea-glass-512.png")
    round_logo = trimmed(facets(HERE / "candidates" / "kea_round_glass_gemini.png", True), 2)
    round_logo.resize((512, 512), Image.LANCZOS).save(HERE / "round-512.png")
    for size in (96, 64):
        round_logo.resize((size, size), Image.LANCZOS).save(STATIC / f"kea-round-{size}.png")
    round_logo.resize((256, 256), Image.LANCZOS).save(STATIC / "kea-favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print("wrote icon-glass-512.png, round-512.png and the site copies in", STATIC)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
