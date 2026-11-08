"""Round badge from the kea icon: the head of the bird in icon-512.png, clipped to a circle on a light disc with an
olive rim. Used as the menu-bar logo, the dock button and the favicon.

Input: icon-512.png (made by make_assets.py). Output, in ../src/kea/docsite/static/: kea-badge-512.png,
kea-badge-96.png, kea-badge-64.png and kea-badge.ico (16, 32, 48 px). Also writes badge_preview.png here (the badge at
16, 24, 46 and 96 px, on white and on the dark menu bar). Crop box and colours chosen by eye on 2026-11-08.
"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
STATIC = HERE.parent / "src" / "kea" / "docsite" / "static"
SIZE = 512                      # master size; the small sizes are resampled from it
HEAD_BOX = (150, 0, 500, 350)   # head, beak and the orange of the wing in the 512 px icon
DISC = (244, 241, 228, 255)     # warm off-white behind the head
RIM = (91, 107, 47, 255)        # olive of the bird (#5b6b2f, also the resource colour of the site)
RIM_WIDTH = 30
SUPERSAMPLE = 4

big = SIZE * SUPERSAMPLE
badge = Image.new("RGBA", (big, big), (0, 0, 0, 0))
mask = Image.new("L", (big, big), 0)
ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
disc = Image.new("RGBA", (big, big), DISC)
icon = Image.open(HERE / "icon-512.png").convert("RGBA")
head = icon.crop(HEAD_BOX)
scale = big * 0.92 / head.width                       # the bird fills the disc; the rim clips the body
head = head.resize((round(head.width * scale), round(head.height * scale)), Image.LANCZOS)
disc.alpha_composite(head, (round(big * 0.02), round(big * 0.12)))
badge.paste(disc, (0, 0), mask)
ring = Image.new("RGBA", (big, big), (0, 0, 0, 0))
ImageDraw.Draw(ring).ellipse((0, 0, big - 1, big - 1), outline=RIM, width=RIM_WIDTH * SUPERSAMPLE)
badge.alpha_composite(ring)
master = badge.resize((SIZE, SIZE), Image.LANCZOS)
master.save(STATIC / "kea-badge-512.png")
for size in (96, 64):
    master.resize((size, size), Image.LANCZOS).save(STATIC / f"kea-badge-{size}.png")
master.save(STATIC / "kea-badge.ico", sizes=[(16, 16), (32, 32), (48, 48)])

preview = Image.new("RGBA", (420, 220), (255, 255, 255, 255))
ImageDraw.Draw(preview).rectangle((0, 110, 420, 220), fill=(29, 35, 48, 255))
x = 10
for size in (16, 24, 46, 96):
    small = master.resize((size, size), Image.LANCZOS)
    preview.alpha_composite(small, (x, 55 - size // 2))
    preview.alpha_composite(small, (x, 165 - size // 2))
    x += size + 30
preview.save(HERE / "badge_preview.png")
print("wrote badge files to", STATIC)

# The head alone (no disc, no rim) for the menu bar's home link, where it sits in a light rounded rectangle drawn by
# the site's CSS: kea-head-64.png and kea-head-128.png (sharp on high-density screens), transparent background.
head_only = icon.crop(HEAD_BOX).resize((SIZE, SIZE), Image.LANCZOS)
for size in (128, 64):
    head_only.resize((size, size), Image.LANCZOS).save(STATIC / f"kea-head-{size}.png")
