"""kea hub: one server that hosts the sites of many projects, collects their comments, and lets each project's
agent publish and harvest from anywhere over https.

On the hub machine (behind an https reverse proxy; the hub itself listens on localhost):
    kea hub init --dir /srv/kea-hub --url https://kea.example.org      once
    kea hub add <name> [--title T]          prints the project key, the site password and the iteration password
    kea hub list                            projects, last publish, lease holder
    kea hub passwords <name> [--site] [--iteration]   new password(s) (old ones stop working)
    kea hub rotate-key <name>               new project key (the old one stops working)
    kea hub public <name> [on|off]          on: the pages are readable without a login (comments, the review
                                            cycle and data files still need a sign-in); no argument: show
    kea hub remove <name>                   moves the project to <dir>/removed/ (nothing is deleted)
    kea hub serve [--host 127.0.0.1 --port 8300] [--log events|requests]
                                            --log events: one line per publish, lease change, sign-in, refused key,
                                            unknown site and reader action (comment, tag, harvest, implement);
                                            --log requests: also every request. Query strings are never logged.
The hub folder is taken from --dir, else KEA_HUB_DIR, else ~/kea-hub.

In a project (the agent's side): kea.yaml `remote: {url: …, project: <name>}`, KEA_REMOTE_KEY=<key> in .env;
then `kea publish` sends the built site and `kea watch`, `kea list`, `kea reply`, `kea cycle` work against the hub
(feedback.backend).

Readers: https://kea.example.org/p/<name>/ ; the site password makes them reviewers (any name they like), the
iteration password makes them PIs: it also lets them harvest the comments into the plan and ask Claude to implement
it. With ORCID accounts (accounts.py) each reader has a role per project: auditor, reviewer, PI or director.

The apex (https://kea.example.org/, or https://keahub.eu/) shows a landing page (feedback/landing.py): for a visitor,
what Kea and the hub are, "Sign in with ORCID" and the public projects; for a reader signed in on the hub, their
projects with their role, the ones waiting for approval, the other public projects and Sign out.

Addresses: with hub.yaml `project_domain: keahub.eu` every project is served at https://<name>.keahub.eu/ (one
wildcard certificate at the proxy); https://keahub.eu/p/<name>/<page> redirects there, the agent API stays at
https://keahub.eu/p/<name>/hub/ (also answered on the subdomain), and https://keahub.eu/id/<uid>[@<version>|.json]
resolves a page's permanent id (docsite/identity.py) to the project that holds it. Without project_domain, sites stay
under /p/<name>/.

Layout of the hub folder:
    hub.yaml                         url, created, max_upload_mb, project_domain, notify_url (both optional)
    projects/<name>/versions/<uid>/  <version>.md and .json: every page version ever published (append-only)
    projects/<name>/project.json     title, salt, key_sha256, reader_token, steer_token (no clear-text secrets)
    projects/<name>/feedback/        events.jsonl, cycle.jsonl (the authority), lease.json, heartbeat.json
    projects/<name>/releases/<id>/   site/, doc/ (Markdown for the editor), files/ (uploaded data), meta.json
    projects/<name>/blobs/           the files of the releases, by sha256 (unreferenced ones are removed)
    projects/<name>/current          symlink to the release being served (swapped atomically on publish)

Agent API (Authorization: Bearer <project key>; X-Kea-Agent: <agent id>), under /p/<name>/hub/:
    GET  lease                      the lease holder
    POST lease                      {agent, host, pid, path, force, watching, heartbeat}: take or renew (409 if held)
    POST lease/release              {agent, force}
    GET  log?events_from=&events_sha=&cycle_from=&cycle_sha=   what is new in the two logs (or the whole log)
    POST events                     {log: events, event} | {log: cycle, kind, fields}: written as "claude"
    POST seed                       {events, cycle}: the project's existing logs, only while the hub's are empty
    POST publish                    body: a .tar.gz from `kea publish` (X-Kea-Sha256: its sha256); older clients
    POST blobs/missing              {sha256: [...]}: which files the hub lacks ({missing: {sha: bytes already here}})
    POST blobs/<sha256>?offset=&total=   body: one chunk of that file, appended at offset (409 + have: resume there)
    POST release                    {manifest: {path: sha256}, meta}: a release made of stored files only
Files are stored once per project by checksum (projects/<name>/blobs/), so a publish sends only what changed.
Every write needs the lease (taken automatically when free).
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import html
import io
import json
import logging
import os
import re
import secrets
import shutil
import sys
import tarfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

from kea.feedback import accounts, agent, cycle, landing, server, store

LOGO_FILE = Path(__file__).resolve().parent.parent / "docsite" / "static" / "kea-head-128.png"

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
# names a new project may not take: they are (or may become) hub addresses on the apex or as subdomains
RESERVED = {"www", "id", "api", "hub", "admin", "mail", "static", "assets", "doi", "auth", "p", "login", "logout"}


def check_new_name(name: str) -> None:
    """A new project's name must also be a valid DNS label for its subdomain: no trailing '-', no 'xn--' (an
    internationalised name in DNS), not reserved."""
    if not NAME.match(name) or name.endswith("-") or name.startswith("xn--") or "--" in name[2:4]:
        raise SystemExit(f"{name!r}: use lower-case letters, digits and single dashes, not at the end (it becomes a "
                         "subdomain)")
    if name in RESERVED:
        raise SystemExit(f"{name!r} is reserved for the hub itself; choose another name")
KEEP_RELEASES = 3
log = logging.getLogger("kea.hub")
AGENT_CYCLE_EVENTS = ("plan-updated", "implementing", "released")
_locks: dict[str, threading.Lock] = {}


def hub_dir(value: str | None = None) -> Path:
    return Path(value or os.environ.get("KEA_HUB_DIR") or Path.home() / "kea-hub").expanduser().resolve()


def sha256_hex(text: str | bytes) -> str:
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def new_password() -> str:
    """Easy to read out and type: four groups of four letters and digits (about 80 bits)."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4))


def project_lock(name: str) -> threading.Lock:
    return _locks.setdefault(name, threading.Lock())


class Hub:
    def __init__(self, folder: Path):
        self.folder = folder
        self.projects_dir = folder / "projects"

    # ---- settings ----
    def settings(self) -> dict:
        import yaml
        path = self.folder / "hub.yaml"
        return (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}

    def init(self, url: str, max_upload_mb: int = 1024) -> None:
        import yaml
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.folder, 0o700)
        path = self.folder / "hub.yaml"
        if path.exists():
            raise SystemExit(f"{path} exists already")
        path.write_text(yaml.safe_dump({"url": url.rstrip("/"), "created": agent.now_iso(),
                                        "max_upload_mb": max_upload_mb}))

    def project_domain(self) -> str:
        """hub.yaml project_domain (e.g. keahub.eu): each project is served at https://<name>.<domain>/."""
        return str(self.settings().get("project_domain") or "").strip().lower().strip(".")

    def site_url(self, name: str) -> str:
        """The public address of a project's site: its subdomain, or <url>/p/<name>."""
        url = str(self.settings().get("url", "")).rstrip("/")
        domain = self.project_domain()
        if domain:
            scheme = url.split("://")[0] if "://" in url else "https"
            return f"{scheme}://{name}.{domain}"
        return f"{url}/p/{name}"

    def ids_of(self, name: str, site: Path | None = None) -> dict:
        try:
            return json.loads(((site or self.project_dir(name) / "current" / "site") / "_ids.json").read_text())
        except (OSError, ValueError):
            return {}

    def id_index(self) -> dict[str, str]:
        """uid -> project, over the current release of every project (cached until a project publishes)."""
        stamp = tuple((name, os.path.realpath(self.project_dir(name) / "current")) for name in self.names())
        if getattr(self, "_id_stamp", None) != stamp:
            index: dict[str, str] = {}
            for name in self.names():
                for uid in self.ids_of(name):
                    index.setdefault(uid, name)
            self._id_index, self._id_stamp = index, stamp
        return self._id_index

    def versions_dir(self, name: str) -> Path:
        return self.project_dir(name) / "versions"

    def store_versions(self, name: str, release: Path) -> int:
        """Keep the Markdown of every page version this release carries (versions/<uid>/<version>.md + .json), so
        kea:<uid>@<version> still shows the cited text after later publishes. Append-only: a stored version is never
        replaced or removed by a publish."""
        stored = 0
        for uid, entry in self.ids_of(name, release / "site").items():
            version, source = str(entry.get("version", "")), release / str(entry.get("source", ""))
            if not re.match(r"^[a-z2-7]{26}$", uid) or not re.match(r"^[a-z2-7]{20}$", version) or not source.is_file():
                continue
            target = self.versions_dir(name) / uid / f"{version}.md"
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            facts = {key: entry.get(key, "") for key in ("key", "type", "number", "title", "short", "status")}
            (target.with_suffix(".json")).write_text(json.dumps({**facts, "stored_at": agent.now_iso(),
                                                                 "release": release.name}, indent=1))
            stored += 1
        return stored

    # ---- projects ----
    def project_dir(self, name: str) -> Path:
        if not NAME.match(name):
            raise ValueError(f"project names are lower-case letters, digits and dashes: {name!r}")
        return self.projects_dir / name

    def config(self, name: str) -> dict | None:
        try:
            return json.loads((self.project_dir(name) / "project.json").read_text())
        except (OSError, ValueError):
            return None

    def write_config(self, name: str, config: dict) -> None:
        path = self.project_dir(name) / "project.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(config, indent=1))
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)

    def names(self) -> list[str]:
        return sorted(path.name for path in self.projects_dir.glob("*") if (path / "project.json").exists())

    def add(self, name: str, title: str = "") -> dict:
        check_new_name(name)
        folder = self.project_dir(name)
        if folder.exists():
            raise SystemExit(f"project {name!r} exists already (kea hub passwords / rotate-key to renew secrets)")
        (folder / "feedback").mkdir(parents=True)
        (folder / "releases").mkdir()
        salt = f"kea-hub:{name}:{secrets.token_hex(8)}"
        key, site_password, steer_password = "kea_" + secrets.token_urlsafe(32), new_password(), new_password()
        self.write_config(name, {"name": name, "title": title or name, "salt": salt, "created": agent.now_iso(),
                                 "key_sha256": sha256_hex(key),
                                 "reader_token": server.auth_token(site_password, salt),
                                 "steer_token": server.steer_token(steer_password, salt)})
        return {"key": key, "site_password": site_password, "iteration_password": steer_password}

    def new_passwords(self, name: str, site: bool, iteration: bool) -> dict:
        config = self.config(name) or sys.exit(f"no project {name!r}")
        out = {}
        if site:
            out["site_password"] = new_password()
            config["reader_token"] = server.auth_token(out["site_password"], config["salt"])
        if iteration:
            out["iteration_password"] = new_password()
            config["steer_token"] = server.steer_token(out["iteration_password"], config["salt"])
        self.write_config(name, config)
        return out

    def set_public(self, name: str, public: bool) -> None:
        """A public project's pages (not its comments, review cycle or data files) are readable without a login."""
        config = self.config(name) or sys.exit(f"no project {name!r}")
        config["public"] = public
        self.write_config(name, config)

    def is_public(self, name: str) -> bool:
        return bool((self.config(name) or {}).get("public"))

    def rotate_key(self, name: str) -> str:
        config = self.config(name) or sys.exit(f"no project {name!r}")
        key = "kea_" + secrets.token_urlsafe(32)
        config["key_sha256"] = sha256_hex(key)
        self.write_config(name, config)
        return key

    def remove(self, name: str) -> Path:
        folder = self.project_dir(name)
        target = self.folder / "removed" / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}"
        target.parent.mkdir(exist_ok=True)
        shutil.move(str(folder), target)
        return target

    # ---- per-project files ----
    def feedback(self, name: str) -> Path:
        return self.project_dir(name) / "feedback"

    def lease(self, name: str) -> dict:
        return agent.read_local(self.feedback(name) / "lease.json")

    def meta(self, name: str) -> dict:
        try:
            return json.loads((self.project_dir(name) / "current" / "meta.json").read_text())
        except (OSError, ValueError):
            return {}

    def published_on(self, name: str) -> str:
        """The date (UTC, YYYY-MM-DD) of the release being served; '' when the project never published."""
        stamp = str(self.meta(name).get("published_at") or "")
        if re.match(r"^\d{4}-\d{2}-\d{2}", stamp):
            return stamp[:10]
        try:                                     # a bundle without published_at: when the release was installed
            return time.strftime("%Y-%m-%d", time.gmtime((self.project_dir(name) / "current").stat().st_mtime))
        except OSError:
            return ""


# ---------------------------------------------------------------- publishing (server side)

def safe_extract(archive: bytes, target: Path) -> None:
    """Unpack a .tar.gz with regular files and folders only, every path inside target."""
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        members = bundle.getmembers()
        for member in members:
            parts = Path(member.name).parts
            if member.name.startswith("/") or ".." in parts or not (member.isfile() or member.isdir()):
                raise ValueError(f"refused bundle entry {member.name!r}")
            if not (target / member.name).resolve().is_relative_to(target.resolve()):
                raise ValueError(f"refused bundle entry {member.name!r}")
        if hasattr(tarfile, "data_filter"):
            bundle.extractall(target, members=members, filter="data")
        else:                                                    # Python < 3.11.4
            bundle.extractall(target, members=members)


BLOB_NAME = re.compile(r"^[0-9a-f]{64}$")
CHUNK_MAX = 16 * 1024 * 1024                    # one chunk of a blob upload (the client sends 4 MB)
BLOB_GRACE = 24 * 3600                          # an unreferenced or half-uploaded blob is kept this long (seconds)
RELEASE_TOPS = ("site", "doc", "files")


def blob_dir(hub: Hub, name: str) -> Path:
    return hub.project_dir(name) / "blobs"


def blob_path(hub: Hub, name: str, sha: str) -> Path:
    if not BLOB_NAME.match(sha):
        raise ValueError(f"not a sha256: {sha[:80]!r}")
    return blob_dir(hub, name) / sha[:2] / sha


def partial_path(hub: Hub, name: str, sha: str) -> Path:
    blob_path(hub, name, sha)
    return blob_dir(hub, name) / "partial" / sha


def missing_blobs(hub: Hub, name: str, shas: list) -> dict:
    """The checksums the hub does not hold yet, each with the bytes of it already received (to resume there)."""
    missing = {}
    for sha in dict.fromkeys(str(item) for item in shas):
        if blob_path(hub, name, sha).is_file():
            continue
        partial = partial_path(hub, name, sha)
        missing[sha] = partial.stat().st_size if partial.is_file() else 0
    return missing


def receive_chunk(hub: Hub, name: str, sha: str, offset: int, total: int, data: bytes) -> dict:
    """Append one chunk to a blob being uploaded; the blob is stored once it is complete and its checksum matches.
    Raises OffsetMismatch when the chunk does not start where the stored part ends (the client resumes there)."""
    final = blob_path(hub, name, sha)
    if final.is_file():
        return {"have": final.stat().st_size, "stored": True}
    partial = partial_path(hub, name, sha)
    have = partial.stat().st_size if partial.is_file() else 0
    if offset != have:
        raise OffsetMismatch(have)
    if have + len(data) > total:
        raise ValueError("chunk runs past the declared total")
    partial.parent.mkdir(parents=True, exist_ok=True)
    with partial.open("ab") as handle:
        handle.write(data)
    have += len(data)
    if have < total:
        return {"have": have, "stored": False}
    digest = hashlib.sha256()
    with partial.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != sha:
        partial.unlink(missing_ok=True)
        raise ValueError("the uploaded file does not match its sha256: send it again")
    final.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(partial, 0o644)
    os.replace(partial, final)
    return {"have": have, "stored": True}


class OffsetMismatch(Exception):
    def __init__(self, have: int):
        super().__init__(f"the hub holds {have} bytes of this file: resume there")
        self.have = have


def release_path(entry: str) -> Path:
    path = Path(entry)
    if entry.startswith("/") or "\\" in entry or not path.parts or ".." in path.parts or path.parts[0] not in RELEASE_TOPS \
            or entry != path.as_posix():
        raise ValueError(f"refused release entry {entry[:120]!r}")
    return path


def install_release(hub: Hub, name: str, archive: bytes) -> dict:
    """Install a release sent as one .tar.gz (clients before 1.21)."""
    return install(hub, name, lambda staging: safe_extract(archive, staging))


def install_manifest(hub: Hub, name: str, manifest: dict, meta: dict) -> dict:
    """Install a release made of stored blobs: {path in the release: sha256} plus meta.json."""
    if not isinstance(manifest, dict) or not isinstance(meta, dict):
        raise ValueError("a release needs manifest: {path: sha256} and meta: {...}")
    paths = {release_path(str(entry)): str(sha) for entry, sha in manifest.items()}
    lacking = sorted(sha for sha in set(paths.values()) if not blob_path(hub, name, sha).is_file())
    if lacking:
        raise ValueError(f"{len(lacking)} file(s) of this release were never uploaded ({', '.join(lacking[:2])} …)")

    def fill(staging: Path) -> None:
        for relative, sha in paths.items():
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(blob_path(hub, name, sha), target)        # same disk: no copy
            except OSError:
                shutil.copyfile(blob_path(hub, name, sha), target)
        (staging / "meta.json").write_text(json.dumps(meta, indent=1))
        (staging / "manifest.json").write_text(json.dumps({path.as_posix(): sha for path, sha in paths.items()}))

    return install(hub, name, fill)


def install(hub: Hub, name: str, fill) -> dict:
    releases = hub.project_dir(name) / "releases"
    release_id = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    staging = releases / (release_id + ".partial")
    staging.mkdir(parents=True)
    try:
        fill(staging)
        if not (staging / "site" / "index.html").is_file() or not (staging / "meta.json").is_file():
            raise ValueError("a bundle needs site/index.html and meta.json")
        owners = hub.id_index()
        taken = sorted(uid for uid in hub.ids_of(name, staging / "site") if owners.get(uid, name) != name)
        if taken:
            raise ValueError(f"{len(taken)} page id(s) belong to another project on this hub ({', '.join(taken[:3])}"
                             f"{' …' if len(taken) > 3 else ''}): a copied page needs its own uid (delete the uid: "
                             "line and run kea check --fix)")
        os.chmod(staging, 0o755)
        final = releases / release_id
        staging.rename(final)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    link = hub.project_dir(name) / "current"
    temporary = link.with_name("current.new")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(Path("releases") / release_id)
    os.replace(temporary, link)
    stored = hub.store_versions(name, final)
    kept = sorted(path for path in releases.iterdir() if path.is_dir() and not path.name.endswith(".partial"))
    for old in kept[:-KEEP_RELEASES]:
        shutil.rmtree(old, ignore_errors=True)
    prune_blobs(hub, name, kept[-KEEP_RELEASES:])
    return {"release": release_id, "files": len(json.loads((final / "meta.json").read_text()).get("files", [])),
            "versions_stored": stored, "site_url": hub.site_url(name)}


def prune_blobs(hub: Hub, name: str, kept: list[Path]) -> None:
    """Remove stored blobs that no kept release uses, and stale half-uploads (both after BLOB_GRACE, so a publish
    that is still uploading keeps its files)."""
    folder = blob_dir(hub, name)
    if not folder.is_dir():
        return
    used = set()
    for release in kept:
        try:
            used |= set(json.loads((release / "manifest.json").read_text()).values())
        except (OSError, ValueError):
            pass
    cutoff = time.time() - BLOB_GRACE
    for path in folder.glob("*/*"):
        try:
            if path.is_file() and path.name not in used and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


def log_part(path: Path, start: int, local_sha: str) -> dict:
    data = path.read_bytes() if path.exists() else b""
    if 0 <= start <= len(data) and hmac.compare_digest(sha256_hex(data[:start]), local_sha or sha256_hex(b"")):
        if start == len(data):
            return {"mode": "same", "size": len(data)}
        return {"mode": "append", "text": data[start:].decode("utf-8"), "size": len(data)}
    return {"mode": "full", "text": data.decode("utf-8"), "size": len(data)}


# ---------------------------------------------------------------- the ASGI app

class HubApp:
    """Routes /p/<name>/hub/… to the agent API and /p/<name>/… to that project's site."""

    def __init__(self, hub: Hub, log_level: str = "off"):
        self.hub = hub
        self.sites: dict[str, tuple[float, object]] = {}
        self.accounts = accounts.Accounts(hub.folder)
        self.log_level = log_level                 # off | events | requests
        self.watch_states: dict[str, str] = {}     # project -> last watcher state seen by monitor()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or self.log_level == "off":
            await self.route(scope, receive, send)
            return
        started, status = time.monotonic(), [0]

        async def watched_send(message):
            if message["type"] == "http.response.start":
                status[0] = message["status"]
            await send(message)
        try:
            await self.route(scope, receive, watched_send)
        finally:
            method = scope.get("method", "")
            path = scope.get("path", "")
            if self.log_level == "requests" or (method not in ("GET", "HEAD") and "/hub/" not in path):
                host = Request(scope).headers.get("host", "").split(":")[0]
                client = (scope.get("client") or ("?",))[0]
                log.info("%s %s%s %s %dms %s", method, host, path, status[0] or "-",
                         round((time.monotonic() - started) * 1000), client)

    def site_app(self, name: str):
        config_path = self.hub.project_dir(name) / "project.json"
        stamp = config_path.stat().st_mtime
        cached = self.sites.get(name)
        if cached and cached[0] == stamp:
            return cached[1]
        config = self.hub.config(name)
        current = self.hub.project_dir(name) / "current"
        feedback = self.hub.feedback(name)
        hub = self.hub
        spec = server.SiteSpec(
            site_dir=current / "site", events_path=feedback / "events.jsonl", cycle_path=feedback / "cycle.jsonl",
            heartbeat_path=feedback / "heartbeat.json", reader_token=config["reader_token"],
            steer_token=config["steer_token"], title=config.get("title", name), salt=config["salt"],
            source_root=current, files_root=current / "files",
            source_commit=lambda relative: str(hub.meta(name).get("source_commits", {}).get(relative, "")),
            versions_dir=hub.versions_dir(name),
            account=lambda request: self.accounts.account(request.cookies.get(accounts.SITE_COOKIE, ""), name),
            login_url=lambda request, next_url: self.login_url(name, next_url),
            public=lambda: hub.is_public(name),
            sso_url=lambda request, next_url: self.check_url(name, next_url),
            hub_menu=lambda account: self.hub_menu(name, account),
            states_context=lambda: hub.meta(name).get("states") or {"labels": {}, "items": {}})
        app = server.make_site_app(spec)
        self.sites[name] = (stamp, app)
        return app

    async def route(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    self.monitor_task = asyncio.create_task(self.monitor())
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    if getattr(self, "monitor_task", None):
                        self.monitor_task.cancel()
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return
        path = scope["path"]
        domain = self.hub.project_domain()
        host = Request(scope).headers.get("host", "").split(":")[0].lower().rstrip(".")
        if domain and host.endswith("." + domain) and host not in ("www." + domain,):
            name = host[:-len(domain) - 1]           # <name>.<domain>: that project's site at the root
            if not NAME.match(name) or self.hub.config(name) is None:
                log.info("unknown site %s (%s)", host, (scope.get("client") or ("?",))[0])
                await PlainTextResponse("no such site", status_code=404)(scope, receive, send)
                return
            if path.startswith("/hub/"):
                response = await self.agent_api(name, path[len("/hub/"):], Request(scope, receive))
                await response(scope, receive, send)
                return
            if path in ("/auth/finish", "/auth/logout"):
                await self.site_auth(name, path, Request(scope, receive), "/")(scope, receive, send)
                return
            await self.site_app(name)(scope, receive, send)
            return
        if path in ("/auth/login", "/auth/orcid/callback", "/auth/check", "/auth/logout"):
            await (await self.apex_auth(path, Request(scope, receive)))(scope, receive, send)
            return
        if path.startswith("/id/"):
            response = await self.resolve_id(path[len("/id/"):], Request(scope, receive))
            await response(scope, receive, send)
            return
        if path == "/":
            await self.landing(Request(scope, receive))(scope, receive, send)
            return
        if path in (landing.LOGO, "/favicon.ico"):
            await FileResponse(LOGO_FILE, media_type="image/png",
                               headers={"Cache-Control": "public, max-age=86400"})(scope, receive, send)
            return
        match = re.match(r"^/p/([^/]+)(/.*)?$", path)
        if not match:
            text = "ok" if path == "/healthz" else "Kea hub. Open the link to your project's site."
            await PlainTextResponse(text, status_code=200 if path == "/healthz" else 404)(scope, receive, send)
            return
        name, rest = match.group(1), match.group(2)
        if not NAME.match(name) or self.hub.config(name) is None:
            await PlainTextResponse("no such site", status_code=404)(scope, receive, send)
            return
        if rest in ("/auth/finish", "/auth/logout") and not domain:
            await self.site_auth(name, rest, Request(scope, receive), f"/p/{name}/")(scope, receive, send)
            return
        if rest is not None and rest.startswith("/hub/"):       # the agent API stays on the apex
            response = await self.agent_api(name, rest[len("/hub/"):], Request(scope, receive))
            await response(scope, receive, send)
            return
        if domain and scope.get("method") in ("GET", "HEAD"):   # reader pages moved to the project's subdomain
            query = scope.get("query_string", b"").decode()
            target = self.hub.site_url(name) + (rest or "/") + (f"?{query}" if query else "")
            await RedirectResponse(target, status_code=308)(scope, receive, send)
            return
        if rest is None:
            await RedirectResponse(f"/p/{name}/", status_code=308)(scope, receive, send)
            return
        inner = dict(scope, root_path=scope.get("root_path", "") + f"/p/{name}")
        await self.site_app(name)(inner, receive, send)

    # ---- is each project's agent still there? (cycle.watcher_status) ----
    def check_watchers(self) -> list[tuple[str, str, dict]]:
        """Compare every project's watcher state with the last check; returns the changes (project, before, now).
        The first check after a start only records the states (no alarm for what happened while the hub was down)."""
        changes = []
        for name in self.hub.names():
            status = cycle.watcher_status(cycle.read_heartbeat_info(self.hub.feedback(name) / "heartbeat.json"))
            before = self.watch_states.get(name)
            self.watch_states[name] = status["state"]
            if before is not None and before != status["state"]:
                changes.append((name, before, status))
        return changes

    async def monitor(self) -> None:
        """Once a minute: log changes of the agents' sessions; a session that stopped unexpectedly (and its return)
        also goes to hub.yaml notify_url (a POST with a plain-text body and Title/Click headers: works with ntfy.sh;
        any webhook receives the text)."""
        while True:
            try:
                for name, before, status in self.check_watchers():
                    level = logging.WARNING if status["state"] == "gone" else logging.INFO
                    log.log(level, "%s: Claude session %s -> %s (%s)", name, before, status["state"], status["text"])
                    if status["state"] == "gone" or (before == "gone" and status["state"] in ("watching", "working")):
                        await asyncio.to_thread(self.notify, name, status)
            except Exception as error:                           # the monitor never takes the hub down
                log.warning("watcher check failed: %s", error)
            await asyncio.sleep(60)

    def notify(self, name: str, status: dict) -> None:
        url = str(self.hub.settings().get("notify_url") or "")
        if not url:
            return
        gone = status["state"] == "gone"
        title = f"Kea {name}: the Claude session {'stopped unexpectedly' if gone else 'is back'}"
        body = (f"{title}. {status['text'][0].upper()}{status['text'][1:]}. "
                + ("Comments wait until someone restarts the session." if gone else ""))
        request = urllib.request.Request(url, data=body.encode(), method="POST", headers={
            "Title": title, "Click": f"{self.hub.site_url(name)}/plan.html", "Tags": "warning" if gone else "white_check_mark",
            "Content-Type": "text/plain; charset=utf-8"})
        try:
            with urllib.request.urlopen(request, timeout=15):
                pass
        except Exception as error:
            log.warning("%s: notify_url refused the message (%s)", name, error)

    # ---- sign-in with ORCID (feedback/accounts.py) ----
    def apex_url(self) -> str:
        return str(self.hub.settings().get("url", "")).rstrip("/")

    def login_url(self, name: str, next_url: str) -> str | None:
        """Where "Sign in with ORCID" on a project's login page leads (None without an ORCID client)."""
        if not accounts.orcid_settings():
            return None
        target = self.hub.site_url(name) + (next_url if next_url.startswith("/") else "/")
        return f"{self.apex_url()}/auth/login?return={urllib.parse.quote(target, safe='')}"

    def check_url(self, name: str, next_url: str) -> str | None:
        """Where a project site asks whether the reader is signed in on the hub (None without an ORCID client)."""
        if not accounts.orcid_settings():
            return None
        target = self.hub.site_url(name) + (next_url if next_url.startswith("/") else "/")
        return f"{self.apex_url()}/auth/check?return={urllib.parse.quote(target, safe='')}"

    def project_of(self, url: str) -> tuple[str, str] | None:
        """(project, path) of a return address on one of this hub's project sites."""
        for name in self.hub.names():
            base = self.hub.site_url(name)
            if url == base or url.startswith(base + "/"):
                path = url[len(base):] or "/"
                return (name, path) if path.startswith("/") and not path.startswith("//") else None
        return None

    def finish_redirect(self, orcid: str, name: str, path: str) -> RedirectResponse:
        code = self.accounts.token("code", accounts.CODE_SECONDS, orcid=orcid, project=name,
                                   nonce=secrets.token_hex(12))
        return RedirectResponse(f"{self.hub.site_url(name)}/auth/finish?code={urllib.parse.quote(code)}"
                                f"&next={urllib.parse.quote(path)}", status_code=303)

    # ---- the apex's own pages (feedback/landing.py) ----
    def apex_session(self, request: Request) -> dict | None:
        return self.accounts.current(self.accounts.verify(request.cookies.get(accounts.APEX_COOKIE, ""), "apex"))

    def project_row(self, name: str, role: str = "", pending: bool = False) -> dict:
        config = self.hub.config(name) or {}
        return {"name": name, "title": config.get("title") or name, "url": self.hub.site_url(name) + "/",
                "public": bool(config.get("public")), "published": self.hub.published_on(name), "role": role,
                "pending": pending}

    def hub_menu(self, current: str, account: dict | None) -> dict:
        """For the name menu on a project site: the hub's front page and the reader's other projects (an ORCID
        account: those with a role; anyone: the public ones)."""
        projects = []
        for name in self.hub.names():
            if name == current:
                continue
            role = self.accounts.role(str(account["orcid"]), name) if account else ""
            if accounts.rank(role) >= accounts.rank("auditor") or self.hub.is_public(name):
                row = self.project_row(name, role)
                projects.append({"title": row["title"], "url": row["url"], "role": accounts.role_label(role) if role else ""})
        return {"home": self.apex_url().rstrip("/") + "/", "projects": projects}

    def landing(self, request: Request) -> HTMLResponse:
        """https://<domain>/: the reader's projects when signed in on the hub, else the page for visitors."""
        settings = self.hub.settings()
        title = str(settings.get("title") or "Kea hub")
        domain = self.hub.project_domain() or urllib.parse.urlsplit(self.apex_url()).netloc
        names = self.hub.names()
        session = self.apex_session(request) if accounts.orcid_settings() else None
        headers = {"Cache-Control": "no-store"}
        if not session:
            sign_in = "/auth/login" if accounts.orcid_settings() else None
            public = [self.project_row(name) for name in names if self.hub.is_public(name)]
            return HTMLResponse(landing.visitor_page(title, domain, sign_in, public), headers=headers)
        orcid = str(session["orcid"])
        user = self.accounts.users().get(orcid) or {}
        requested = set(user.get("requested") or [])
        rows, public = [], []
        for name in names:
            role = self.accounts.role(orcid, name)
            if accounts.rank(role) >= accounts.rank("auditor"):
                rows.append(self.project_row(name, role))
            elif name in requested and user.get("status") != "blocked":
                rows.append(self.project_row(name, pending=True))
            elif self.hub.is_public(name):
                public.append(self.project_row(name))
        person = {"orcid": orcid, "name": user.get("name", ""), "status": user.get("status", "")}
        return HTMLResponse(landing.reader_page(title, domain, person, rows, public, "/auth/logout"), headers=headers)

    async def apex_auth(self, path: str, request: Request):
        settings = accounts.orcid_settings()
        if not settings:
            return PlainTextResponse("ORCID sign-in is not set up on this hub", status_code=404)
        callback = f"{self.apex_url()}/auth/orcid/callback"
        session = self.apex_session(request)
        if path == "/auth/check":                    # a project site asks: signed in here? in, or back without
            target = request.query_params.get("return", "")
            place = self.project_of(target)
            if place is None:
                return PlainTextResponse("unknown return address", status_code=400)
            if session and accounts.rank(self.accounts.role(session["orcid"], place[0])) >= accounts.rank("auditor"):
                log.info("sign-in %s -> %s (hub session, no click)", session["orcid"], place[0])
                return self.finish_redirect(session["orcid"], *place)
            return RedirectResponse(target, status_code=303)
        if path == "/auth/logout":                   # sign out everywhere, then back to where the reader was
            if session:
                self.accounts.sign_out(session["orcid"])
                log.info("sign-out %s (hub and every project site)", session["orcid"])
            target = request.query_params.get("return", "")
            response = RedirectResponse(target if self.project_of(target) else self.apex_url() + "/", status_code=303)
            response.delete_cookie(accounts.APEX_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
            return response
        if path == "/auth/login":
            target = request.query_params.get("return", "")
            if target in ("", self.apex_url(), self.apex_url() + "/"):    # sign in on the hub's own page
                if session:
                    return RedirectResponse(self.apex_url() + "/", status_code=303)
                place = ("", "/")
            else:
                place = self.project_of(target)
                if place is None:
                    return PlainTextResponse("unknown return address", status_code=400)
                if session and accounts.rank(self.accounts.role(session["orcid"], place[0])) >= accounts.rank("auditor"):
                    log.info("sign-in %s -> %s (hub session)", session["orcid"], place[0])
                    return self.finish_redirect(session["orcid"], *place)
            log.info("sign-in for %s: sent to ORCID", place[0] or "the hub")
            state = self.accounts.token("state", 600, project=place[0], path=place[1])
            query = urllib.parse.urlencode({"client_id": settings["client_id"], "response_type": "code",
                                            "scope": "openid", "redirect_uri": callback, "state": state})
            return RedirectResponse(f"{settings['base']}/oauth/authorize?{query}", status_code=303)
        state = self.accounts.verify(request.query_params.get("state", ""), "state")
        code = request.query_params.get("code", "")
        if not state or not code:
            return PlainTextResponse("sign-in expired or not valid; start again from the site", status_code=400)
        try:
            person = await asyncio.to_thread(accounts.exchange_code, code, callback, settings)
        except Exception as error:                  # ORCID down or the code refused
            log.warning("sign-in: ORCID refused the code (%s: %s)", type(error).__name__, error)
            return PlainTextResponse(f"ORCID did not confirm the sign-in ({type(error).__name__}); try again",
                                     status_code=502)
        orcid = person.get("orcid", "")
        if not accounts.ORCID_ID.match(orcid):
            return PlainTextResponse("ORCID returned no iD", status_code=502)
        user = self.accounts.seen(orcid, person.get("name", ""))
        if user.get("status") == "blocked":
            log.info("sign-in %s (%s): blocked", orcid, user.get("name", ""))
            return PlainTextResponse("This ORCID iD may not use this hub.", status_code=403)
        project = str(state.get("project") or "")
        if not project:                              # signed in on the hub's own page (pending or not)
            log.info("sign-in %s (%s) -> the hub (%s)", orcid, user.get("name", ""), user.get("status", "?"))
            response = RedirectResponse(self.apex_url() + "/", status_code=303)
        elif accounts.rank(self.accounts.role(orcid, project)) < accounts.rank("auditor"):
            self.accounts.request(orcid, project)
            log.info("sign-in %s (%s) for %s: waiting for approval (kea hub users approve %s --project %s)", orcid,
                     user.get("name", ""), project, orcid, project)
            response = HTMLResponse(
                "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<title>Waiting for approval</title><body style='font:15px/1.5 system-ui;max-width:560px;margin:60px "
                "auto;padding:0 18px'><h1>Thank you</h1><p>You signed in as "
                f"<b>{html.escape(user.get('name', ''))}</b> (ORCID <code>{html.escape(orcid)}</code>). The hub's "
                "administrator approves new readers; you can sign in again once that is done.</p>"
                f"<p><a href='{html.escape(self.apex_url())}/'>Your page on this hub</a> shows which projects you can "
                "open and which wait for approval.</p>", status_code=403)
        else:
            log.info("sign-in %s (%s) -> %s as %s", orcid, user.get("name", ""), project,
                     self.accounts.role(orcid, project))
            response = self.finish_redirect(orcid, project, state["path"])
        response.set_cookie(accounts.APEX_COOKIE, self.accounts.token("apex", accounts.SESSION_DAYS * 86400, orcid=orcid),
                            max_age=accounts.SESSION_DAYS * 86400, httponly=True, secure=True, samesite="lax", path="/")
        return response

    def site_auth(self, name: str, path: str, request: Request, cookie_path: str):
        """On a project's site: turn a one-time code from the apex into the project's own session; or sign out."""
        if path == "/auth/logout":                   # this site, then the hub (which signs out everywhere)
            payload = self.accounts.verify(request.cookies.get(accounts.SITE_COOKIE, ""), "site")
            if payload:
                self.accounts.sign_out(str(payload.get("orcid")))
            back = self.hub.site_url(name) + "/"
            target = (f"{self.apex_url()}/auth/logout?return={urllib.parse.quote(back, safe='')}"
                      if accounts.orcid_settings() else cookie_path)
            response = RedirectResponse(target, status_code=303)
            response.delete_cookie(accounts.SITE_COOKIE, path=cookie_path)
            return response
        payload = self.accounts.verify(request.query_params.get("code", ""), "code")
        if not payload or payload.get("project") != name or not self.accounts.use_code(str(payload.get("nonce"))):
            log.info("sign-in code for %s refused (expired, used or for another site)", name)
            return PlainTextResponse("sign-in code expired or already used; start again", status_code=400)
        next_path = request.query_params.get("next", "/")
        next_path = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/"
        response = RedirectResponse(cookie_path.rstrip("/") + next_path, status_code=303)
        response.set_cookie(accounts.SITE_COOKIE,
                            self.accounts.token("site", accounts.SESSION_DAYS * 86400, orcid=payload["orcid"], project=name),
                            max_age=accounts.SESSION_DAYS * 86400, httponly=True, secure=True, samesite="lax",
                            path=cookie_path)
        return response

    async def resolve_id(self, rest: str, request: Request):
        """/id/<uid>[.json|@<version>] on the hub: find the project that holds the page, then let that project's
        site answer (it applies the project's login). A project's agent (Bearer project key) gets the facts as JSON
        directly: that is how one project reads the state of a page it builds on in another."""
        uid = re.split(r"[.@]", rest, maxsplit=1)[0]
        name = self.hub.id_index().get(uid)
        if name is None:
            return JSONResponse({"error": f"no page with id kea:{uid} on this hub"}, status_code=404)
        header = request.headers.get("authorization", "")
        key = header[len("Bearer "):].strip() if header.startswith("Bearer ") else ""
        if key and rest.endswith(".json") and any(hmac.compare_digest(sha256_hex(key), (self.hub.config(other) or {})
                                                                     .get("key_sha256", "")) for other in self.hub.names()):
            entry = self.hub.ids_of(name).get(uid, {})
            return JSONResponse({"id": f"kea:{uid}", "project": name, **entry,
                                 "url": f"{self.hub.site_url(name)}/{entry.get('url', '')}"})
        return RedirectResponse(f"{self.hub.site_url(name)}/id/{rest}", status_code=308)

    # ---- agent API ----
    def authorised(self, name: str, request: Request) -> bool:
        header = request.headers.get("authorization", "")
        key = header[len("Bearer "):].strip() if header.startswith("Bearer ") else ""
        config = self.hub.config(name) or {}
        return bool(key) and hmac.compare_digest(sha256_hex(key), config.get("key_sha256", ""))

    def take_lease(self, name: str, info: dict, force: bool = False, watching: bool = False,
                   heartbeat: dict | None = None) -> dict:
        path = self.hub.feedback(name) / "lease.json"
        lease = agent.take_local(path, force=force, watching=watching, info=info, check_process=False)
        if heartbeat is not None and watching:
            cycle.write_heartbeat(self.hub.feedback(name) / "heartbeat.json", extra=heartbeat)
        return lease

    async def agent_api(self, name: str, action: str, request: Request):
        if not self.authorised(name, request):
            log.warning("%s: wrong or missing project key (%s %s from %s)", name, request.method, action,
                        request.client.host if request.client else "?")
            return JSONResponse({"error": "wrong or missing project key"}, status_code=401)
        agent_name = request.headers.get("x-kea-agent", "").strip()[:120]
        if not agent_name:
            return JSONResponse({"error": "X-Kea-Agent header missing"}, status_code=400)
        feedback = self.hub.feedback(name)
        method = request.method
        try:
            if action == "lease" and method == "GET":
                return JSONResponse({"lease": self.hub.lease(name)})
            if action == "log" and method == "GET":
                query = request.query_params
                return JSONResponse({
                    "events": log_part(feedback / "events.jsonl", int(query.get("events_from", 0)),
                                       query.get("events_sha", "")),
                    "cycle": log_part(feedback / "cycle.jsonl", int(query.get("cycle_from", 0)),
                                      query.get("cycle_sha", "")),
                    "lease": self.hub.lease(name)})
            if method != "POST":
                return JSONResponse({"error": "not found"}, status_code=404)
            if action == "publish":
                return await self.publish(name, agent_name, request)
            if action.startswith("blobs/") and action != "blobs/missing":
                return await self.upload_chunk(name, agent_name, action[len("blobs/"):], request)
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("body must be a JSON object")
            info = {"agent": agent_name, "host": str(body.get("host", ""))[:120],
                    "pid": body.get("pid") if isinstance(body.get("pid"), int) else 0,
                    "path": str(body.get("path", ""))[:300]}
            with project_lock(name):
                if action == "lease":
                    before = self.hub.lease(name).get("agent")
                    lease = self.take_lease(name, info, force=bool(body.get("force")),
                                            watching=bool(body.get("watching")),
                                            heartbeat=body.get("heartbeat") if isinstance(body.get("heartbeat"), dict)
                                            else None)
                    if before != agent_name:
                        log.info("%s: lease taken by %s (%s)%s", name, agent_name, info["host"],
                                 f", was {before}" if before else "")
                    return JSONResponse({"lease": lease})
                if action == "lease/release":
                    holder = self.hub.lease(name)
                    if holder and holder.get("agent") != agent_name and not body.get("force"):
                        raise agent.LeaseHeld(holder)
                    (feedback / "lease.json").unlink(missing_ok=True)
                    log.info("%s: lease released by %s", name, agent_name)
                    return JSONResponse({"released": True})
                holder = self.hub.lease(name)
                same = holder.get("agent") == agent_name
                self.take_lease(name, {key: holder.get(key) for key in ("agent", "host", "pid", "path")} if same
                                else info, watching=same and bool(holder.get("watching")))
                if action == "events":
                    if body.get("log") == "events":
                        event = dict(body.get("event") or {}, author=store_author())
                        log.info("%s: agent %s wrote %s %s", name, agent_name, event.get("type", "event"),
                                 event.get("thread_id", ""))
                        return JSONResponse({"event": store.append_event(event, feedback / "events.jsonl")})
                    if body.get("log") == "cycle":
                        kind = str(body.get("kind", ""))
                        if kind not in AGENT_CYCLE_EVENTS:
                            raise ValueError(f"the agent may record only {', '.join(AGENT_CYCLE_EVENTS)}")
                        fields = {key: str(value) for key, value in (body.get("fields") or {}).items()}
                        state = cycle.append(kind, store_author(), feedback / "cycle.jsonl", **fields)
                        log.info("%s: cycle %s by %s", name, kind, agent_name)
                        return JSONResponse({"cycle": state.to_dict()})
                    raise ValueError("log must be events or cycle")
                if action == "blobs/missing":
                    shas = body.get("sha256")
                    if not isinstance(shas, list):
                        raise ValueError("blobs/missing needs sha256: [...]")
                    return JSONResponse({"missing": missing_blobs(self.hub, name, shas)})
                if action == "release":
                    result = install_manifest(self.hub, name, body.get("manifest"), body.get("meta"))
                    log.info("%s: published release %s by %s (%d files, %d new page version(s))", name,
                             result["release"], agent_name, len(body["manifest"]), result["versions_stored"])
                    return JSONResponse(result)
                if action == "seed":
                    seeded = self.seed(name, body)
                    log.info("%s: logs seeded by %s: %s", name, agent_name, seeded["seeded"])
                    return JSONResponse(seeded)
        except agent.LeaseHeld as held:
            log.info("%s: %s refused, lease held by %s", name, agent_name, held.holder.get("agent"))
            return JSONResponse({"error": str(held), "holder": held.holder}, status_code=409)
        except (store.FeedbackError, ValueError, KeyError, TypeError, OSError) as error:
            log.info("%s: %s %s refused: %s", name, method, action, error)
            return JSONResponse({"error": str(error)}, status_code=400)
        return JSONResponse({"error": "not found"}, status_code=404)

    def seed(self, name: str, body: dict) -> dict:
        written = {}
        for log in ("events", "cycle"):
            path = self.hub.feedback(name) / f"{log}.jsonl"
            text = str(body.get(log) or "")
            if path.exists() and path.stat().st_size:
                written[log] = "kept (the hub's log is not empty)"
                continue
            for line in text.splitlines():
                if line.strip():
                    json.loads(line)                         # every line must be JSON
            path.write_text(text if text.endswith("\n") or not text else text + "\n", encoding="utf-8")
            written[log] = f"{sum(1 for line in text.splitlines() if line.strip())} events"
        return {"seeded": written}

    async def upload_chunk(self, name: str, agent_name: str, sha: str, request: Request):
        query = request.query_params
        try:
            offset, total = int(query.get("offset", "")), int(query.get("total", ""))
            blob_path(self.hub, name, sha)
        except ValueError as error:
            return JSONResponse({"error": f"blob upload needs a sha256, offset= and total= ({error})"},
                                status_code=400)
        limit = int(self.hub.settings().get("max_upload_mb", 1024)) * 1024 * 1024
        if total > limit or total < 0 or offset < 0:
            return JSONResponse({"error": f"file larger than {limit // 1048576} MB (hub.yaml max_upload_mb)"},
                                status_code=413)
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > CHUNK_MAX:
                return JSONResponse({"error": f"chunk larger than {CHUNK_MAX // 1048576} MB"}, status_code=413)
            chunks.append(chunk)
        with project_lock(name):
            holder = self.hub.lease(name)
            if not agent.is_free_for(holder, agent_name, check_process=False):
                return JSONResponse({"error": agent.describe_refusal(holder), "holder": holder}, status_code=409)
            try:
                return JSONResponse(receive_chunk(self.hub, name, sha, offset, total, b"".join(chunks)))
            except OffsetMismatch as mismatch:
                return JSONResponse({"error": str(mismatch), "have": mismatch.have}, status_code=409)
            except (ValueError, OSError) as error:
                log.warning("%s: blob upload by %s refused: %s", name, agent_name, error)
                return JSONResponse({"error": str(error)}, status_code=400)

    async def publish(self, name: str, agent_name: str, request: Request):
        limit = int(self.hub.settings().get("max_upload_mb", 1024)) * 1024 * 1024
        declared = request.headers.get("x-kea-sha256", "")
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                log.warning("%s: publish by %s refused: larger than %d MB", name, agent_name, limit // 1048576)
                return JSONResponse({"error": f"bundle larger than {limit // 1048576} MB (hub.yaml max_upload_mb)"},
                                    status_code=413)
            chunks.append(chunk)
        archive = b"".join(chunks)
        if not declared or not hmac.compare_digest(sha256_hex(archive), declared):
            log.warning("%s: publish by %s refused: checksum does not match", name, agent_name)
            return JSONResponse({"error": "checksum does not match (X-Kea-Sha256)"}, status_code=400)
        with project_lock(name):
            holder = self.hub.lease(name)
            if not agent.is_free_for(holder, agent_name, check_process=False):
                log.info("%s: publish by %s refused, lease held by %s", name, agent_name, holder.get("agent"))
                return JSONResponse({"error": agent.describe_refusal(holder), "holder": holder}, status_code=409)
            try:
                result = install_release(self.hub, name, archive)
            except (ValueError, tarfile.TarError, OSError) as error:
                log.warning("%s: publish by %s refused: %s", name, agent_name, error)
                return JSONResponse({"error": f"bundle refused: {error}"}, status_code=400)
        log.info("%s: published release %s by %s (%.1f MB, %d new page version(s), %d data file(s))", name,
                 result["release"], agent_name, len(archive) / 1048576, result["versions_stored"], result["files"])
        return JSONResponse(result)


def store_author() -> str:
    from kea.feedback.__main__ import AUTHOR
    return AUTHOR


# ---------------------------------------------------------------- command line

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kea hub", description=__doc__.split("\n")[0])
    parser.add_argument("--dir", default=None, help="hub folder (default: KEA_HUB_DIR or ~/kea-hub)")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--url", required=True, help="the https address readers and agents use")
    init.add_argument("--max-upload-mb", type=int, default=1024)
    add = sub.add_parser("add")
    add.add_argument("name")
    add.add_argument("--title", default="")
    sub.add_parser("list")
    passwords = sub.add_parser("passwords")
    passwords.add_argument("name")
    passwords.add_argument("--site", action="store_true")
    passwords.add_argument("--iteration", action="store_true")
    public = sub.add_parser("public", help="make a project's pages readable without a login (on) or not (off)")
    public.add_argument("name")
    public.add_argument("switch", nargs="?", choices=["on", "off"])
    rotate = sub.add_parser("rotate-key")
    rotate.add_argument("name")
    remove = sub.add_parser("remove")
    remove.add_argument("name")
    users = sub.add_parser("users", help="ORCID accounts: list, approve, role, block")
    users.add_argument("action", nargs="?", default="list", choices=["list", "approve", "role", "block"])
    users.add_argument("orcid", nargs="?", default="")
    users.add_argument("role", nargs="?", default="reviewer", type=accounts.normalise_role,
                       choices=list(accounts.ROLES),
                       help="auditor (reads), reviewer (comments), pi (also harvest, implement), director; the old "
                            "names reader, commenter, steerer, owner still work")
    users.add_argument("--project", default="*", help="a project name, or * for all projects")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8300)
    serve.add_argument("--trusted-proxy", default="127.0.0.1",
                       help="address(es) of the reverse proxy whose X-Forwarded-* headers are trusted")
    serve.add_argument("--log", choices=["off", "events", "requests"], default="off",
                       help="events: publishes, leases, sign-ins, refusals and reader actions; requests: also every "
                            "request (to stderr; query strings are never logged)")
    args = parser.parse_args(argv)
    hub = Hub(hub_dir(args.dir))
    if args.command == "init":
        hub.init(args.url, args.max_upload_mb)
        print(f"hub folder {hub.folder}; address {args.url}\nnext: kea hub add <project>, then kea hub serve behind "
              "an https reverse proxy (see the README, 'Hosting on a Kea hub')")
        return 0
    if not (hub.folder / "hub.yaml").exists():
        print(f"no hub in {hub.folder} (kea hub init --url https://… first)", file=sys.stderr)
        return 1
    url = hub.settings().get("url", "https://<hub>")
    if args.command == "add":
        secrets_out = hub.add(args.name, args.title)
        print(f"project {args.name}: {url}/p/{args.name}/\n\n"
              f"  project key (for the project's .env, KEA_REMOTE_KEY=…; shown once):\n    {secrets_out['key']}\n"
              f"  site password (reviewers; they comment under any name):\n    {secrets_out['site_password']}\n"
              f"  iteration password (PIs: also harvest / implement):\n    {secrets_out['iteration_password']}\n\n"
              f"In the project's kea.yaml:\n  remote:\n    url: {url}\n    project: {args.name}\n"
              "The hub stores only hashes: write these down now.")
        return 0
    if args.command == "list":
        for name in hub.names():
            current = hub.project_dir(name) / "current"
            release = os.readlink(current) if current.is_symlink() else "not published"
            holder = hub.lease(name)
            watcher = cycle.watcher_status(cycle.read_heartbeat_info(hub.feedback(name) / "heartbeat.json"))
            print(f"{name:24} {'public ' if hub.is_public(name) else 'private'} {release:40} "
                  f"lease: {holder.get('agent', 'free')} {holder.get('renewed_at', '')}  "
                  f"Claude: {watcher['text'] or 'never watched'}")
        return 0
    if args.command == "users":
        book = accounts.Accounts(hub.folder)
        if args.action == "list":
            entries = sorted(book.users().items(), key=lambda item: (item[1].get("status") != "pending", item[0]))
            for orcid, user in entries:
                roles = ", ".join(f"{project}: {accounts.role_label(role)}"
                                  for project, role in sorted((user.get("roles") or {}).items()))
                waiting = ", ".join(user.get("requested") or [])
                print(f"{orcid}  {user.get('status', '?'):9} {user.get('name', ''):30} {roles}"
                      + (f"  (asked for: {waiting})" if waiting else ""))
            print(f"{len(entries)} user(s); ORCID sign-in {'on' if accounts.orcid_settings() else 'off (no client in the environment)'}")
            return 0
        if not args.orcid:
            parser.error("give the ORCID iD")
        if args.action == "block":
            book.block(args.orcid)
        else:
            if args.project != "*" and hub.config(args.project) is None:
                parser.error(f"no project {args.project!r}")
            book.approve(args.orcid, args.role, args.project, by=store_author())
        print(json.dumps({args.orcid: book.users()[args.orcid]}, indent=1))
        return 0
    if args.command == "passwords":
        if not (args.site or args.iteration):
            args.site = args.iteration = True
        for label, value in hub.new_passwords(args.name, args.site, args.iteration).items():
            print(f"{label.replace('_', ' ')}: {value}")
        return 0
    if args.command == "public":
        if hub.config(args.name) is None:
            parser.error(f"no project {args.name!r}")
        if args.switch:
            hub.set_public(args.name, args.switch == "on")
        state = "public: anyone can read the pages; comments, the review cycle and data files need a sign-in" \
            if hub.is_public(args.name) else "not public: every page needs a sign-in"
        print(f"{args.name} ({hub.site_url(args.name)}/): {state}")
        return 0
    if args.command == "rotate-key":
        print(f"new project key (KEA_REMOTE_KEY in the project's .env; shown once):\n  {hub.rotate_key(args.name)}")
        return 0
    if args.command == "remove":
        print(f"moved to {hub.remove(args.name)}")
        return 0
    if args.command == "serve":
        import uvicorn
        if args.log != "off":
            logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname).1s %(message)s",
                                datefmt="%Y-%m-%d %H:%M:%S", stream=sys.stderr)
            domain = hub.project_domain()
            log.info("kea hub %s: %s on %s:%d, %d project(s): %s; ORCID sign-in %s; log %s", _version(), hub.folder,
                     args.host, args.port, len(hub.names()), ", ".join(hub.names()),
                     "on" if accounts.orcid_settings() else "off", args.log)
            log.info("readers at %s", f"https://<project>.{domain}/" if domain else f"{url}/p/<project>/")
        uvicorn.run(HubApp(hub, args.log), host=args.host, port=args.port, log_level="warning", proxy_headers=True,
                    forwarded_allow_ips=args.trusted_proxy)
        return 0
    return 1


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("kea")
    except Exception:
        return "?"


if __name__ == "__main__":
    raise SystemExit(main())
