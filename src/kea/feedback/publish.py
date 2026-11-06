"""kea publish: send the built site to the project's Kea hub (kea.yaml `remote:`), with the Markdown sources for the
editor and only the data files the owner chose to share.

    kea publish --files      list the data files the site links to, with size and whether they would be uploaded
                             (and why not); uploads nothing. Run this first and let the owner decide.
    kea publish              upload: the site (report/site, built in review mode), doc/*.md of the editable pages,
                             the chosen data files, and meta.json (commit of each source, review-state labels)

Which data files go up (kea.yaml):
    remote:
      url: https://kea.example.org
      project: trajectories
      upload_max_kb: 100            # data files up to this size go up, unless flagged (default 0: none)
      upload_include: [data/final/summary.tsv, "data/final/*.png"]   # always (also flagged or larger ones)
      upload_exclude: ["data/intermediate/*"]                        # never
A file is flagged when it looks like it may hold identifiers (a column or key named like donor, subject,
patient, individual, participant, sample, specimen, projid, barcode) or is a format kea cannot inspect
(h5ad, parquet, …); flagged files go up only when named in upload_include.

On the hub the site links only to uploaded files: a file that stays home keeps its facts (path, size, checksum)
but its download link and its preview are replaced by "not on this server". Nothing is uploaded silently: the
command prints every file it sends.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import time
from pathlib import Path

from kea.config import PROJECT_ROOT, SETTINGS, SITE_DIR
from kea.feedback import agent, backend

IDENTIFIER = re.compile(r"(donor|subject|patient|individual|participant|sample|specimen|projid|barcode|"
                        r"person|case_?id|record_?id)", re.I)
TEXT_TABLES = (".tsv", ".csv", ".txt", ".json", ".md", ".yaml", ".yml")
SAFE_KINDS = (".png", ".svg", ".pdf", ".jpg", ".jpeg")        # figures: never identifiers in a column header
DOWNLOAD_LINK = re.compile(r"<a href='(?P<prefix>/|(?:\.\./)*)files/(?P<path>[^']+)' download>download</a>"
                           r"(?P<note> <span class='help'>\(needs the site server\)</span>)?")
PREVIEW = re.compile(r"<div class='not-annotatable kea-preview' data-file='(?P<path>[^']+)'>.*?</div><!--/kea-preview-->",
                     re.S)


def unescape(text: str) -> str:
    import html
    return html.unescape(text)


def identifier_hint(path: Path) -> str:
    """Why a file may hold identifiers ('' when nothing suggests it)."""
    suffix = path.suffix.lower()
    if suffix in SAFE_KINDS:
        return ""
    if suffix not in TEXT_TABLES:
        return f"{suffix or 'no extension'}: kea cannot look inside"
    try:
        head = path.open(encoding="utf-8", errors="replace").read(65536)
    except OSError as error:
        return f"unreadable: {error}"
    if suffix == ".json":
        keys = set(re.findall(r'"([^"]{1,60})"\s*:', head))
        found = sorted(key for key in keys if IDENTIFIER.search(key))
    else:
        first = head.splitlines()[0] if head else ""
        found = sorted({cell.strip() for cell in re.split(r"[\t,;|]", first) if IDENTIFIER.search(cell)})
        if suffix in (".md", ".txt", ".yaml", ".yml"):
            found = sorted({match.group(0) for match in IDENTIFIER.finditer(head)})[:5] if not found else found
    return f"may hold identifiers ({', '.join(found[:5])})" if found else ""


def decide(paths: list[str], remote: dict) -> list[dict]:
    """One row per linked data file: path, size, upload (bool) and the reason."""
    max_bytes = float(remote.get("upload_max_kb", 0) or 0) * 1024
    include = [str(item) for item in remote.get("upload_include", []) or []]
    exclude = [str(item) for item in remote.get("upload_exclude", []) or []]
    rows = []
    for relative in paths:
        path = PROJECT_ROOT / relative
        if not path.is_file():
            continue
        size = path.stat().st_size
        hint = identifier_hint(path)
        if any(fnmatch.fnmatch(relative, pattern) for pattern in exclude):
            upload, reason = False, "upload_exclude"
        elif any(fnmatch.fnmatch(relative, pattern) for pattern in include):
            upload, reason = True, "upload_include" + (f" (note: {hint})" if hint else "")
        elif hint:
            upload, reason = False, hint
        elif size <= max_bytes:
            upload, reason = True, f"≤ {max_bytes / 1024:.0f} kB"
        else:
            upload, reason = False, ("larger than upload_max_kb" if max_bytes else "upload_max_kb not set (0)")
        rows.append({"path": relative, "size": size, "upload": upload, "reason": reason})
    return rows


def source_commits(paths: list[str]) -> dict[str, str]:
    """path -> short commit of its last change, in one pass over git log."""
    wanted, found = set(paths), {}
    output = subprocess.run(["git", "log", "--format=@%h", "--name-only", "--", "doc"], cwd=PROJECT_ROOT,
                            capture_output=True, text=True).stdout
    commit = ""
    for line in output.splitlines():
        if line.startswith("@"):
            commit = line[1:]
        elif line in wanted and line not in found:
            found[line] = commit
    return found


def rewrite_html(text: str, uploaded: set[str]) -> str:
    def link(match: re.Match) -> str:
        if unescape(match.group("path")) in uploaded:
            return f"<a href='{match.group('prefix')}files/{match.group('path')}' download>download</a>"
        return "<span class='help'>download not on this server</span>"

    def preview(match: re.Match) -> str:
        if unescape(match.group("path")) in uploaded:
            return match.group(0)
        return "<p class='help not-annotatable'>Preview not on this server (the file was not uploaded).</p>"

    return PREVIEW.sub(preview, DOWNLOAD_LINK.sub(link, text))


def bundle(site: Path, rows: list[dict]) -> tuple[bytes, dict]:
    uploaded = {row["path"] for row in rows if row["upload"]}
    sources = json.loads((site / "_sources.json").read_text()) if (site / "_sources.json").exists() else {}
    source_paths = sorted(set(sources.values()))
    from kea.feedback import states
    context = states.context()
    meta = {"published_at": agent.now_iso(), "kea_version": kea_version(),
            "build": json.loads((site / "_build.json").read_text()) if (site / "_build.json").exists() else {},
            "files": sorted(uploaded), "source_commits": source_commits(source_paths),
            "states": {"labels": context.get("labels", {}), "items": context.get("items", {})}}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz", compresslevel=6) as archive:
        def add_bytes(name: str, data: bytes) -> None:
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(data), int(time.time()), 0o644
            archive.addfile(info, io.BytesIO(data))

        for path in sorted(site.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(site).as_posix()
            if relative == "_files.json":
                add_bytes("site/_files.json", json.dumps(sorted(uploaded), indent=1).encode())
            elif path.suffix == ".html":
                add_bytes(f"site/{relative}", rewrite_html(path.read_text(encoding="utf-8"), uploaded).encode())
            else:
                archive.add(path, f"site/{relative}", recursive=False)
        for relative in source_paths:
            path = PROJECT_ROOT / relative
            if path.is_file() and path.resolve().is_relative_to((PROJECT_ROOT / "doc").resolve()):
                archive.add(path, f"{relative}", recursive=False)
        for relative in sorted(uploaded):
            archive.add(PROJECT_ROOT / relative, f"files/{relative}", recursive=False)
        add_bytes("meta.json", json.dumps(meta, indent=1).encode())
    return buffer.getvalue(), meta


def kea_version() -> str:
    from kea import __version__
    return __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kea publish", description=__doc__.split("\n")[0])
    parser.add_argument("--files", action="store_true", help="list the data files and the upload decision; no upload")
    parser.add_argument("--site", type=Path, default=SITE_DIR)
    args = parser.parse_args(argv)
    remote = backend.remote_settings()
    if not remote:
        print("kea.yaml has no `remote: {url: …, project: …}`; see `kea hub --help`", file=sys.stderr)
        return 1
    site = args.site
    if not (site / "index.html").is_file():
        print(f"no built site in {site}: run kea build first", file=sys.stderr)
        return 1
    if not (site / "_feedback").is_dir():
        print("the site was not built in review mode (no comment layer): kea build --mode review", file=sys.stderr)
        return 1
    build_info = json.loads((site / "_build.json").read_text()) if (site / "_build.json").exists() else {}
    if not build_info.get("previews_marked"):
        print("the site was built by an older kea that does not mark data previews, so kea publish cannot keep "
              "previews of files that stay home off the hub: run kea build again first", file=sys.stderr)
        return 1
    linked = json.loads((site / "_files.json").read_text()) if (site / "_files.json").exists() else []
    rows = decide(linked, remote)
    going = [row for row in rows if row["upload"]]
    if args.files:
        width = max((len(row["path"]) for row in rows), default=10)
        for row in rows:
            print(f"{'UPLOAD' if row['upload'] else 'keep  '}  {row['path']:{width}}  {row['size'] / 1024:9.1f} kB  "
                  f"{row['reason']}")
        print(f"\n{len(going)} of {len(rows)} linked data files would be uploaded "
              f"({sum(row['size'] for row in going) / 1024:.0f} kB); decide with upload_max_kb / upload_include / "
              "upload_exclude under remote: in kea.yaml")
        return 0
    try:
        client = backend.get()
        client.take_lease()
        empty = hashlib.sha256(b"").hexdigest()
        reply = client.request("GET", "log", query={"events_from": 0, "events_sha": empty, "cycle_from": 0,
                                                    "cycle_sha": empty})
        if reply["events"]["size"] == 0 and reply["cycle"]["size"] == 0:
            print("hub logs are empty: sending this project's comments and cycle history first:",
                  client.seed()["seeded"])
        client.sync()
        archive, meta = bundle(site, rows)
        result = client.request("POST", "publish", archive,
                                headers={"Content-Type": "application/gzip",
                                         "X-Kea-Sha256": hashlib.sha256(archive).hexdigest()})
        client.sync()
    except agent.LeaseHeld as held:
        print(held, file=sys.stderr)
        return 2
    except backend.RemoteError as error:
        print(error, file=sys.stderr)
        return 1
    for row in going:
        print(f"uploaded {row['path']} ({row['size'] / 1024:.1f} kB; {row['reason']})")
    print(f"published release {result['release']} to {remote['url'].rstrip('/')}/p/{remote['project']}/ "
          f"({len(archive) / 1048576:.1f} MB bundle, {len(going)} data file(s), "
          f"{len(meta['source_commits'])} editable pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
