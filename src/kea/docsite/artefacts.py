"""Artefact panels: file facts, a preview of the content and a download link.

The site is behind the shared password (decision 2026-11-04), so previews may show controlled-access tables.
Downloads are served by the comment server from an allow-list (``_files.json``) of artefact paths; files larger
than ``DOWNLOAD_LIMIT`` get their path and checksum only. Checksums are cached by (size, mtime) in
data/intermediate/docsite/sha256_cache.json so a 2.7 GB file is hashed once.

Input: the artefact's file on disk (read-only).
Output: HTML for the artefact page; entries for the download allow-list.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from kea.docsite import mode
from kea.docsite.nodes import PROJECT_ROOT
from kea.docsite.render import esc

DOWNLOAD_LIMIT = 1_000_000_000
PREVIEW_ROWS = 50
CACHE = PROJECT_ROOT / "data" / "intermediate" / "docsite" / "sha256_cache.json"


def human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return str(size)


def sha256_of(path: Path) -> str:
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    stat = path.stat()
    key = f"{path}|{stat.st_size}|{stat.st_mtime_ns}"
    if key not in cache:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 24), b""):
                digest.update(block)
        cache[key] = digest.hexdigest()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        temporary = CACHE.with_suffix(".tmp")
        temporary.write_text(json.dumps(cache, indent=0))
        temporary.replace(CACHE)
    return cache[key]


def table_html(frame: pd.DataFrame) -> str:
    head = "".join(f"<th>{esc(column)}</th>" for column in frame.columns)
    rows = []
    for row in frame.itertuples(index=False):
        cells = []
        for value in row:
            if isinstance(value, float):
                text = "" if np.isnan(value) else f"{value:.4g}"
            else:
                text = str(value)
            cells.append(f"<td>{esc(text)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def preview(path: Path) -> str:
    suffix = "".join(path.suffixes[-1:]).lower()
    try:
        if suffix in (".tsv", ".csv"):
            separator = "\t" if suffix == ".tsv" else ","
            frame = pd.read_csv(path, sep=separator, nrows=PREVIEW_ROWS, index_col=False)
            with path.open() as handle:
                n_rows = sum(1 for _ in handle) - 1
            return (f"<p class='help'>{n_rows:,} rows × {frame.shape[1]} columns; first "
                    f"{min(PREVIEW_ROWS, n_rows)} rows:</p>{table_html(frame)}")
        if suffix == ".parquet":
            import pyarrow.parquet as pq
            parquet = pq.ParquetFile(path)
            frame = parquet.read_row_group(0).slice(0, PREVIEW_ROWS).to_pandas()
            schema = ", ".join(f"<code>{esc(field.name)}</code> {esc(field.type)}" for field in parquet.schema_arrow)
            return (f"<p class='help'>{parquet.metadata.num_rows:,} rows. Columns: {schema}. First "
                    f"{len(frame)} rows:</p>{table_html(frame)}")
        if suffix == ".npz":
            with np.load(path) as archive:
                rows = "".join(f"<tr><td><code>{esc(name)}</code></td><td>{esc(archive[name].shape)}</td>"
                               f"<td>{esc(archive[name].dtype)}</td></tr>" for name in archive.files)
            return f"<table><tr><th>array</th><th>shape</th><th>type</th></tr>{rows}</table>"
        if suffix == ".json":
            text = path.read_text()[:20000]
            return f"<pre>{esc(text)}</pre>"
        if suffix == ".md":
            return f"<pre>{esc(path.read_text()[:20000])}</pre>"
    except (OSError, ValueError, pd.errors.ParserError) as error:
        return f"<p class='help'>No preview: {esc(error)}</p>"
    return "<p class='help'>No preview for this file type.</p>"


def download_html(relative: str, prefix: str) -> tuple[str, str | None]:
    """(' · download' link HTML, allow-list entry or None) for a project file, following the build mode."""
    path = PROJECT_ROOT / relative
    if not path.is_file() or path.name == ".env" or not path.resolve().is_relative_to(PROJECT_ROOT):
        return "", None
    href = mode.file_href(relative, prefix)
    if href is None:
        return "", None
    if path.stat().st_size > DOWNLOAD_LIMIT:
        return " · <span class='help'>too large to download here; use the path</span>", None
    note = " <span class='help'>(needs the site server)</span>" if mode.MODE == "review" else ""
    return f" · <a href='{esc(href)}' download>download</a>{note}", relative


def file_rows(paths: list[str], prefix: str, downloads: set) -> str:
    """Table rows (path, size, sha256, download) for project files."""
    rows = []
    for relative in paths:
        path = PROJECT_ROOT / relative
        if not path.is_file():
            continue
        link, entry = download_html(relative, prefix)
        if entry:
            downloads.add(entry)
        rows.append(f"<tr><td><code>{esc(relative)}</code></td><td>{human_size(path.stat().st_size)}</td>"
                    f"<td><code>{sha256_of(path)[:12]}…</code></td><td>{link.removeprefix(' · ')}</td></tr>")
    return "".join(rows)


def artefact_panel(relative: str, prefix: str, access: str | None = None,
                   downloads: set | None = None) -> tuple[str, str | None]:
    """(HTML panel, download path or None) for an artefact at `relative` (path from the project root)."""
    downloads = downloads if downloads is not None else set()
    path = PROJECT_ROOT / relative
    if not path.exists():
        return f"<div class='box'><b>File:</b> <code>{esc(relative)}</code> — <b>missing on disk</b></div>", None
    stat = path.stat()
    modified = dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
    checksum = sha256_of(path) if path.is_file() else ""
    download, entry = download_html(relative, prefix)
    if not mode.data_links():
        download = " · <span class='help'>file not published with this site; ask the authors</span>"
    readme = path.parent / "README.md"
    readme_link = (f"<div><b>Folder manifest:</b> <code>{esc(readme.relative_to(PROJECT_ROOT))}</code></div>"
                   if readme.exists() else "")
    if mode.preview_allowed(access):
        preview_html = f"<h2>Preview</h2><div class='not-annotatable'>{preview(path)}</div>"
    else:
        mode.omit("preview", relative)
        preview_html = ("<h2>Preview</h2><p class='help not-annotatable'>Not shown in this public copy (the file "
                        "may contain controlled-access data).</p>")
    siblings = ""
    if mode.data_links() and path.is_file():
        others = sorted(str(other.relative_to(PROJECT_ROOT)) for other in path.parent.iterdir()
                        if other.is_file() and other != path and not other.name.startswith("."))
        rows = file_rows(others, prefix, downloads)
        if rows:
            siblings = (f"<details class='not-annotatable'><summary>Other files in "
                        f"<code>{esc(str(path.parent.relative_to(PROJECT_ROOT)))}</code> ({rows.count('<tr>')})</summary>"
                        f"<table><tr><th>file</th><th>size</th><th>sha256</th><th></th></tr>{rows}</table></details>")
    panel = (f"<div class='box not-annotatable'><div><b>File:</b> <code>{esc(relative)}</code>{download}</div>"
             f"<div><b>Size:</b> {human_size(stat.st_size)} · <b>modified:</b> {modified}"
             f"{' · <b>sha256:</b> <code>' + checksum[:16] + '…</code>' if checksum else ''}</div>{readme_link}"
             f"{siblings}</div>{preview_html}")
    return panel, entry
