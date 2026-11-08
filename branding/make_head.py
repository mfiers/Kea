"""A small kea head for the site's floating page buttons, cut from the icon.

Input: icon-512.png (made by make_assets.py). Output: ../src/kea/docsite/static/kea-head-96.png (96 x 96 px,
transparent), copied by the builder into the site's _assets/. The crop box was chosen by eye on 2026-11-08.
"""
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
STATIC = HERE.parent / "src" / "kea" / "docsite" / "static"
HEAD_BOX = (262, 2, 482, 172)          # left, top, right, bottom in the 512 px icon: the head and beak

icon = Image.open(HERE / "icon-512.png").convert("RGBA")
head = icon.crop(HEAD_BOX)
side = max(head.size)
square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
square.paste(head, ((side - head.width) // 2, (side - head.height) // 2))
square.resize((96, 96), Image.LANCZOS).save(STATIC / "kea-head-96.png")
print("wrote", STATIC / "kea-head-96.png")
