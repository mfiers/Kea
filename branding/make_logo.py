"""Generate Kea logo candidates with image models on OpenRouter (key: OPENROUTER_API_KEY in the environment).

Writes branding/candidates/<name>.png and a record of model, prompt and date in branding/candidates/record.json.
Usage: python make_logo.py   (needs network access; costs a few cents)
"""
import base64
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "candidates"
BASE = ("Logo for 'Kea', an open-source research tool that turns a scientific data analysis into a navigable "
        "website of linked claims and evidence, reviewed by people and an AI agent. ")
CANDIDATES = {
    "kea_graph": "A minimalist flat vector logo: a stylised kea (New Zealand alpine parrot: olive-green body, a flash "
                 "of orange under the wing, long curved grey beak) perched on three small connected circles that form "
                 "a tiny network graph. Geometric shapes, at most four colours, no gradients, no text, centred on a "
                 "plain white background, square, crisp edges, recognisable at 32 pixels.",
    "kea_head": "A minimalist flat vector icon of a kea parrot's head in profile, olive green with an orange accent, "
                "the strong curved beak forming the letter K negative space. Bold geometric shapes, no gradients, no "
                "text, centred on plain white, square app-icon style, readable at 16 pixels.",
    "kea_wordmark": "A clean horizontal logo: on the left a simple geometric kea parrot icon (olive green, orange "
                    "underwing, curved beak) and on the right the lowercase wordmark 'kea' in a modern sans-serif, "
                    "dark slate colour. Below the wordmark in small letters: 'Keep Evidence Attached'. Flat vector, "
                    "white background, no other text.",
}
CANDIDATES["kea_icon"] = (
    "A square app icon in a faceted low-poly origami style: a kea parrot seen from the side, olive-green facets "
    "with a few warm orange facets on the wing, a strong hooked olive beak, small dark eye. Only the bird, centred, "
    "filling most of the square, plain white background, flat colours without gradients or shadows, no text. "
    "Must stay recognisable at 32 pixels.")
CANDIDATES["kea_wordmark2"] = (
    "A clean horizontal logo: on the left a faceted low-poly origami-style kea parrot (olive-green facets, warm "
    "orange facets on the underside of the raised wing, strong hooked beak, small dark eye); on the right the "
    "lowercase wordmark 'kea' in a modern geometric sans-serif, dark slate colour; below it, small and letter-spaced, "
    "'KEEP EVIDENCE ATTACHED'. Flat colours, white background, no other text or elements.")
# GPT image model removed 2026-11-05: provider error "Complexity 'none' is not supported for this image model".
MODELS = {"gemini": "google/gemini-3-pro-image"}


def generate(model: str, prompt: str) -> bytes:
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps({"model": model, "modalities": ["image", "text"],
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "Content-Type": "application/json",
                 "X-Title": "kea logo"})
    with urllib.request.urlopen(request, timeout=300) as response:
        reply = json.load(response)
    images = reply["choices"][0]["message"].get("images") or []
    if not images:
        raise RuntimeError(f"{model}: no image in reply: {str(reply)[:300]}")
    url = images[0]["image_url"]["url"]
    return base64.b64decode(url.split(",", 1)[1])


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    record = []
    wanted = sys.argv[1:] or list(CANDIDATES)
    for name in wanted:
        for short, model in MODELS.items():
            target = OUT / f"{name}_{short}.png"
            if target.exists():
                continue
            try:
                target.write_bytes(generate(model, BASE + CANDIDATES[name]))
                status = "ok"
            except Exception as error:   # report and continue with the other candidates
                status = f"failed: {error}"
            print(target.name, status)
            record.append({"file": target.name, "model": model, "prompt": BASE + CANDIDATES[name], "status": status,
                           "date": dt.datetime.now().isoformat(timespec="seconds")})
    previous = json.loads((OUT / "record.json").read_text()) if (OUT / "record.json").exists() else []
    (OUT / "record.json").write_text(json.dumps(previous + record, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
