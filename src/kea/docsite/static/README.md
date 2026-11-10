# Third-party assets copied into the site (report/site/_assets/)

- `cytoscape.min.js`: Cytoscape.js 3.30.2 (MIT licence, The Cytoscape Consortium), from
  https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.30.2/cytoscape.min.js, downloaded 2026-11-05,
  sha256 83e8c54a6bec655bfd81df07df605649c268af69aeca67a5ea2da54ea42dac81. Used by the relations pages
  (`<experiment>/relations.html`); copied so the site makes no outside requests.
- `kea-icon-64.png`, `favicon.ico`: the kea icon (made by `packages/kea/branding/make_assets.py` from an image
  generated with google/gemini-3-pro-image on OpenRouter, 2026-11-05; prompts in `branding/candidates/record.json`).
- `kea-icon-512.png`: the same icon at 512 px (from `branding/icon-512.png`), for the PDF's title page.
- Page-type icons (`src/kea/docsite/icons.py`): inline SVG line drawings in the style of Feather Icons (MIT
  licence, https://feathericons.com); several shapes follow Feather's.
- `kea-badge-512.png`, `kea-badge-96.png` (page-button dock), `kea-badge-64.png` (menu bar), `kea-badge.ico`
  (favicon, 16/32/48): the round badge, the head of the kea icon on a light disc with an olive rim, made from
  `branding/icon-512.png` by `branding/make_badge.py` (2026-11-08). A stained-glass version generated the same day
  (`branding/make_logo2.py`, `branding/make_assets2.py`, candidates in `branding/candidates/`) was not taken.
  `favicon.ico` and `kea-icon-64.png` are kept for older sites but no longer used.

- `plex-mono-latin-400-normal.woff2`, `plex-mono-latin-400-italic.woff2`, `plex-mono-latin-600-normal.woff2`: IBM Plex Mono (SIL Open Font License 1.1, IBM Corp.), Latin subset, from `@fontsource/ibm-plex-mono` 5.1.1 on cdn.jsdelivr.net, downloaded 2026-11-10; sha256 3c5a451f…, 78439db2…, c4d3deb7… respectively. Kea's typewriter face for the title, summary and text of a page (`.given`); characters outside the subset fall back to the system's monospace.
