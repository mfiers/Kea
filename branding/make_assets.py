"""Logo assets from the chosen candidates: white made transparent, trimmed, resized.

Chosen 2026-11-05: candidates/kea_wordmark2_gemini.png (wordmark) and candidates/kea_icon_gemini.png (icon), both
from google/gemini-3-pro-image (prompts in candidates/record.json).
Output: logo.png (wordmark, 1200 px wide), icon-512.png, icon-64.png, favicon.ico (16/32/48), and copies of
icon-64.png and favicon.ico in ../src/kea/docsite/static/ (used by the site).
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).parent
STATIC = HERE.parent / "src" / "kea" / "docsite" / "static"


def transparent(image: Image.Image) -> Image.Image:
    """Near-white -> transparent, with a soft edge (alpha from the distance to white)."""
    rgba = np.asarray(image.convert("RGBA")).astype(float)
    whiteness = rgba[..., :3].min(axis=2)                      # 255 = white; the generated background is noisy
    alpha = np.clip((225 - whiteness) / 30 * 255, 0, 255)      # transparent above 225, opaque below 195
    mask = Image.fromarray((alpha > 0).astype(np.uint8) * 255, "L")
    mask = mask.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))   # opening: drop isolated specks
    alpha = np.minimum(alpha, np.asarray(mask.filter(ImageFilter.MaxFilter(3))).astype(float))
    rgba[..., 3] = np.minimum(rgba[..., 3], alpha)
    return Image.fromarray(rgba.astype(np.uint8), "RGBA")


def trimmed(image: Image.Image, margin: int) -> Image.Image:
    box = image.getchannel("A").point(lambda value: 255 if value > 20 else 0).getbbox()
    cropped = image.crop(box)
    canvas = Image.new("RGBA", (cropped.width + 2 * margin, cropped.height + 2 * margin), (0, 0, 0, 0))
    canvas.paste(cropped, (margin, margin))
    return canvas


def square(image: Image.Image) -> Image.Image:
    side = max(image.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    return canvas


wordmark = trimmed(transparent(Image.open(HERE / "candidates" / "kea_wordmark2_gemini.png")), 24)
wordmark.resize((1200, round(1200 * wordmark.height / wordmark.width)), Image.LANCZOS).save(HERE / "logo.png")
icon = square(trimmed(transparent(Image.open(HERE / "candidates" / "kea_icon_gemini.png")), 16))
icon.resize((512, 512), Image.LANCZOS).save(HERE / "icon-512.png")
small = icon.resize((64, 64), Image.LANCZOS)
small.save(HERE / "icon-64.png")
icon.resize((256, 256), Image.LANCZOS).save(HERE / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
STATIC.mkdir(exist_ok=True)
small.save(STATIC / "kea-icon-64.png")
icon.resize((256, 256), Image.LANCZOS).save(STATIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
print("written:", ", ".join(path.name for path in sorted(HERE.glob("*.png")) + [HERE / "favicon.ico"]))
