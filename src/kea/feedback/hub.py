"""kea hub: one server that hosts the sites of many projects, collects their comments, and lets each project's
agent publish and harvest from anywhere over https.

On the hub machine (behind an https reverse proxy; the hub itself listens on localhost):
    kea hub init --dir /srv/kea-hub --url https://kea.example.org      once
    kea hub add <name> [--title T]          prints the project key, the site password and the iteration password
    kea hub list                            projects, last publish, lease holder
    kea hub passwords <name> [--site] [--iteration]   new password(s) (old ones stop working)
    kea hub rotate-key <name>               new project key (the old one stops working)
    kea hub remove <name>                   moves the project to <dir>/removed/ (nothing is deleted)
    kea hub serve [--host 127.0.0.1 --port 8300]
The hub folder is taken from --dir, else KEA_HUB_DIR, else ~/kea-hub.

In a project (the agent's side): kea.yaml `remote: {url: …, project: <name>}`, KEA_REMOTE_KEY=<key> in .env;
then `kea publish` sends the built site and `kea watch`, `kea list`, `kea reply`, `kea cycle` work against the hub
(feedback.backend).

Readers: https://kea.example.org/p/<name>/ ; the site password makes them commenters (any name they like), the
iteration password also lets them freeze the site, unfreeze it, and ask Claude to implement the plan.

Layout of the hub folder:
    hub.yaml                         url, created, max_upload_mb
    projects/<name>/project.json     title, salt, key_sha256, reader_token, steer_token (no clear-text secrets)
    projects/<name>/feedback/        events.jsonl, cycle.jsonl (the authority), lease.json, heartbeat.json
    projects/<name>/releases/<id>/   site/, doc/ (Markdown for the editor), files/ (uploaded data), meta.json
    projects/<name>/current          symlink to the release being served (swapped atomically on publish)

Agent API (Authorization: Bearer <project key>; X-Kea-Agent: <agent id>), under /p/<name>/hub/:
    GET  lease                      the lease holder
    POST lease                      {agent, host, pid, path, force, watching, heartbeat}: take or renew (409 if held)
    POST lease/release              {agent, force}
    GET  log?events_from=&events_sha=&cycle_from=&cycle_sha=   what is new in the two logs (or the whole log)
    POST events                     {log: events, event} | {log: cycle, kind, fields}: written as "claude"
    POST seed                       {events, cycle}: the project's existing logs, only while the hub's are empty
    POST publish                    body: a .tar.gz from `kea publish` (X-Kea-Sha256: its sha256)
Every write needs the lease (taken automatically when free).
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import sys
import tarfile
import threading
import time
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

from kea.feedback import agent, cycle, server, store

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
KEEP_RELEASES = 3
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


def install_release(hub: Hub, name: str, archive: bytes) -> dict:
    releases = hub.project_dir(name) / "releases"
    release_id = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    staging = releases / (release_id + ".partial")
    staging.mkdir(parents=True)
    try:
        safe_extract(archive, staging)
        if not (staging / "site" / "index.html").is_file() or not (staging / "meta.json").is_file():
            raise ValueError("a bundle needs site/index.html and meta.json")
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
    kept = sorted(path for path in releases.iterdir() if path.is_dir() and not path.name.endswith(".partial"))
    for old in kept[:-KEEP_RELEASES]:
        shutil.rmtree(old, ignore_errors=True)
    return {"release": release_id, "files": len(json.loads((final / "meta.json").read_text()).get("files", []))}


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

    def __init__(self, hub: Hub):
        self.hub = hub
        self.sites: dict[str, tuple[float, object]] = {}

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
            states_context=lambda: hub.meta(name).get("states") or {"labels": {}, "items": {}})
        app = server.make_site_app(spec)
        self.sites[name] = (stamp, app)
        return app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return
        path = scope["path"]
        match = re.match(r"^/p/([^/]+)(/.*)?$", path)
        if not match:
            text = "ok" if path == "/healthz" else "Kea hub. Open the link to your project's site."
            await PlainTextResponse(text, status_code=200 if path in ("/", "/healthz") else 404)(scope, receive, send)
            return
        name, rest = match.group(1), match.group(2)
        if not NAME.match(name) or self.hub.config(name) is None:
            await PlainTextResponse("no such site", status_code=404)(scope, receive, send)
            return
        if rest is None:
            await RedirectResponse(f"/p/{name}/", status_code=308)(scope, receive, send)
            return
        if rest.startswith("/hub/"):
            response = await self.agent_api(name, rest[len("/hub/"):], Request(scope, receive))
            await response(scope, receive, send)
            return
        inner = dict(scope, root_path=scope.get("root_path", "") + f"/p/{name}")
        await self.site_app(name)(inner, receive, send)

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
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("body must be a JSON object")
            info = {"agent": agent_name, "host": str(body.get("host", ""))[:120],
                    "pid": body.get("pid") if isinstance(body.get("pid"), int) else 0,
                    "path": str(body.get("path", ""))[:300]}
            with project_lock(name):
                if action == "lease":
                    lease = self.take_lease(name, info, force=bool(body.get("force")),
                                            watching=bool(body.get("watching")),
                                            heartbeat=body.get("heartbeat") if isinstance(body.get("heartbeat"), dict)
                                            else None)
                    return JSONResponse({"lease": lease})
                if action == "lease/release":
                    holder = self.hub.lease(name)
                    if holder and holder.get("agent") != agent_name and not body.get("force"):
                        raise agent.LeaseHeld(holder)
                    (feedback / "lease.json").unlink(missing_ok=True)
                    return JSONResponse({"released": True})
                holder = self.hub.lease(name)
                same = holder.get("agent") == agent_name
                self.take_lease(name, {key: holder.get(key) for key in ("agent", "host", "pid", "path")} if same
                                else info, watching=same and bool(holder.get("watching")))
                if action == "events":
                    if body.get("log") == "events":
                        event = dict(body.get("event") or {}, author=store_author())
                        return JSONResponse({"event": store.append_event(event, feedback / "events.jsonl")})
                    if body.get("log") == "cycle":
                        kind = str(body.get("kind", ""))
                        if kind not in AGENT_CYCLE_EVENTS:
                            raise ValueError(f"the agent may record only {', '.join(AGENT_CYCLE_EVENTS)}")
                        fields = {key: str(value) for key, value in (body.get("fields") or {}).items()}
                        state = cycle.append(kind, store_author(), feedback / "cycle.jsonl", **fields)
                        return JSONResponse({"cycle": state.to_dict()})
                    raise ValueError("log must be events or cycle")
                if action == "seed":
                    return JSONResponse(self.seed(name, body))
        except agent.LeaseHeld as held:
            return JSONResponse({"error": str(held), "holder": held.holder}, status_code=409)
        except (store.FeedbackError, ValueError, KeyError, TypeError) as error:
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

    async def publish(self, name: str, agent_name: str, request: Request):
        limit = int(self.hub.settings().get("max_upload_mb", 1024)) * 1024 * 1024
        declared = request.headers.get("x-kea-sha256", "")
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                return JSONResponse({"error": f"bundle larger than {limit // 1048576} MB (hub.yaml max_upload_mb)"},
                                    status_code=413)
            chunks.append(chunk)
        archive = b"".join(chunks)
        if not declared or not hmac.compare_digest(sha256_hex(archive), declared):
            return JSONResponse({"error": "checksum does not match (X-Kea-Sha256)"}, status_code=400)
        with project_lock(name):
            holder = self.hub.lease(name)
            if not agent.is_free_for(holder, agent_name, check_process=False):
                return JSONResponse({"error": agent.describe_refusal(holder), "holder": holder}, status_code=409)
            try:
                result = install_release(self.hub, name, archive)
            except (ValueError, tarfile.TarError, OSError) as error:
                return JSONResponse({"error": f"bundle refused: {error}"}, status_code=400)
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
    rotate = sub.add_parser("rotate-key")
    rotate.add_argument("name")
    remove = sub.add_parser("remove")
    remove.add_argument("name")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8300)
    serve.add_argument("--trusted-proxy", default="127.0.0.1",
                       help="address(es) of the reverse proxy whose X-Forwarded-* headers are trusted")
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
              f"  site password (readers; they comment under any name):\n    {secrets_out['site_password']}\n"
              f"  iteration password (also freeze / implement):\n    {secrets_out['iteration_password']}\n\n"
              f"In the project's kea.yaml:\n  remote:\n    url: {url}\n    project: {args.name}\n"
              "The hub stores only hashes: write these down now.")
        return 0
    if args.command == "list":
        for name in hub.names():
            current = hub.project_dir(name) / "current"
            release = os.readlink(current) if current.is_symlink() else "not published"
            holder = hub.lease(name)
            print(f"{name:24} {release:40} lease: {holder.get('agent', 'free')} {holder.get('renewed_at', '')}")
        return 0
    if args.command == "passwords":
        if not (args.site or args.iteration):
            args.site = args.iteration = True
        for label, value in hub.new_passwords(args.name, args.site, args.iteration).items():
            print(f"{label.replace('_', ' ')}: {value}")
        return 0
    if args.command == "rotate-key":
        print(f"new project key (KEA_REMOTE_KEY in the project's .env; shown once):\n  {hub.rotate_key(args.name)}")
        return 0
    if args.command == "remove":
        print(f"moved to {hub.remove(args.name)}")
        return 0
    if args.command == "serve":
        import uvicorn
        uvicorn.run(HubApp(hub), host=args.host, port=args.port, log_level="warning", proxy_headers=True,
                    forwarded_allow_ips=args.trusted_proxy)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
