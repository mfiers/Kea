"""Serve the static site with one shared password and a small comment API.

What it does:
    * serves report/site/ as static files (the site itself stays static);
    * serves artefact downloads under /files/<path> for the paths in report/site/_files.json only
      (written by the site build; files up to 1 GB), from the project folder;
    * asks for one shared password (SITE_PASSWORD in .env) before anything is shown; a signed
      cookie remembers it for 90 days;
    * the reader's name is a plain cookie (fb_name) set in the page; the server takes the author
      of every comment from it;
    * stores comments through feedback.store (append-only data/feedback/events.jsonl).

Review cycle (feedback.cycle): while the site is frozen for review, new comments, replies and status changes
are accepted only on the plan pages (plan/…); while implementation is requested or running, nowhere. Refusals
are HTTP 423.

API (JSON):
    GET  /api/threads?page=<path>   threads of one page (all pages without ?page=)
    POST /api/threads               {page, page_title, page_commit, quote, prefix, suffix, start, end, text}
    POST /api/threads/<id>/reply    {text}
    POST /api/threads/<id>/status   {status, note}   (readers may set resolved or open)
    GET  /api/status                cycle state, site build id, comment counts (polled by every page)
    GET  /api/source?page=<key>     the Markdown source of a documentation page (for the editor)
    POST /api/suggest               {page, page_title, text, new_text}: a suggested edit, stored as a thread with the
                                    diff; files are never written by the server
    POST /api/cycle/freeze          a reader freezes the site for review (comments only on the plan)
    POST /api/cycle/unfreeze        back to comments everywhere
    POST /api/cycle/implement       a reader asks Claude to implement the plan (only from frozen, and only when
                                    every comment is in the plan: 409 otherwise)
    POST /api/cycle/cancel          a reader withdraws that request (before Claude has started; back to frozen)

Usage: kea serve [--host <ip>] [--port <port>]   (defaults from kea.yaml)
Security: meant for the KU Leuven network only; plain http; one password for everybody.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import hmac
import html
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import quote, unquote

from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from kea.config import PROJECT_ROOT, SETTINGS, SITE_DIR
from kea.feedback import cycle, states, store

PROJECT = PROJECT_ROOT
AUTH_COOKIE = "fb_auth"
NAME_COOKIE = "fb_name"
COOKIE_DAYS = 90
READER_STATUSES = ("resolved", "open")


def auth_token(password: str) -> str:
    """Cookie value proving the password was entered; changes when the password changes."""
    salt = str(SETTINGS.get("cookie_salt") or f"kea-site:{PROJECT_ROOT.name}").encode()   # per site, kea.yaml
    return hmac.new(password.encode(), salt, hashlib.sha256).hexdigest()


def reader_name(request: Request) -> str:
    return unquote(request.cookies.get(NAME_COOKIE, "")).strip()[: store.MAX_NAME]


LOGIN_PAGE = """<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Sign in</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;background:#f6f7f9;color:#1d2330;display:grid;place-items:center;min-height:90vh;margin:0}}
form{{background:#fff;padding:28px 32px;border-radius:10px;box-shadow:0 1px 4px #0002;max-width:340px;width:100%}}
h1{{font-size:19px;margin:0 0 6px}}p{{color:#555;font-size:13.5px;margin:0 0 16px}}label{{display:block;font-size:13px;margin:10px 0 4px}}
input{{width:100%;box-sizing:border-box;padding:8px;border:1px solid #bbb;border-radius:6px;font:inherit}}
button{{margin-top:16px;padding:8px 16px;border:0;border-radius:6px;background:#1f5fa8;color:#fff;font:inherit;cursor:pointer}}
.err{{color:#a00;font-size:13px}}</style>
<form method='post' action='/login'>
<h1>{title}</h1>
<p>Internal working site. Enter the shared password. Your name is used to sign your comments.</p>
{error}
<label for='name'>Your name</label><input id='name' name='name' value='{name}' maxlength='60' autocomplete='name'>
<label for='password'>Password</label><input id='password' name='password' type='password' autofocus>
<input type='hidden' name='next' value='{next}'>
<button>Enter</button></form>"""


class PasswordGate(BaseHTTPMiddleware):
    def __init__(self, app, password: str):
        super().__init__(app)
        self.token = auth_token(password) if password else ""

    async def dispatch(self, request: Request, call_next):
        if not self.token or request.url.path in ("/login", "/favicon.ico"):
            return await call_next(request)
        if hmac.compare_digest(request.cookies.get(AUTH_COOKIE, ""), self.token):
            return await call_next(request)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": "not signed in"}, status_code=401)
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(f"/login?next={quote(target)}", status_code=303)


def make_app(site_dir: Path, events_path: Path, password: str, cycle_path: Path | None = None,
             heartbeat_path: Path | None = None) -> Starlette:
    token = auth_token(password) if password else ""

    def frozen_response(page_key: str) -> Response | None:
        current = cycle.state(cycle_path)
        if current.accepts_comments_on(page_key):
            return None
        message = ("the site is frozen for review: comments are open only on the plan"
                   if current.state == "frozen" else
                   f"comments are paused while the plan is implemented ({current.state})")
        return JSONResponse({"error": message}, status_code=423)

    def page_of_thread(thread_id: str) -> str:
        thread = store.fold(store.load_events(events_path)).get(thread_id)
        return thread.page if thread else ""

    async def status(request: Request) -> Response:
        current = cycle.state(cycle_path)
        build_file = site_dir / "_build.json"
        build = json.loads(build_file.read_text()) if build_file.exists() else {}
        threads = store.threads(events_path)
        return JSONResponse({"cycle": current.to_dict(), "build": build, "you": reader_name(request),
                             "threads": len(threads),
                             "open": sum(cycle.needs_attention(thread) for thread in threads),
                             "unplanned": len(cycle.needs_planning(threads, current)),
                             "watcher_seen_at": cycle.read_heartbeat(heartbeat_path)})

    async def cycle_action(request: Request) -> Response:
        action = request.path_params["action"]
        try:
            name = _author(request)
            kind = {"freeze": "frozen", "unfreeze": "unfrozen", "implement": "implement-requested",
                    "cancel": "cancelled"}.get(action)
            if kind is None:
                raise store.FeedbackError("unknown action")
            if kind == "implement-requested":
                waiting = cycle.needs_planning(store.threads(events_path), cycle.state(cycle_path))
                if waiting:
                    raise store.FeedbackError(f"{len(waiting)} comment(s) are not in the plan yet; "
                                              "wait until Claude has added them")
            current = cycle.append(kind, name, cycle_path)
        except store.FeedbackError as error:
            return JSONResponse({"error": str(error)}, status_code=409)
        return JSONResponse({"cycle": current.to_dict()})

    def editable_sources() -> dict[str, str]:
        listing = site_dir / "_sources.json"
        return json.loads(listing.read_text()) if listing.exists() else {}

    def source_text(page_key: str) -> tuple[str, str, str] | None:
        """(relative path, text now, commit of the last change) of an editable page, or None."""
        relative = editable_sources().get(page_key)
        if not relative:
            return None
        target = (PROJECT / relative).resolve()
        if not target.is_relative_to(PROJECT / "doc") or not target.is_file():
            return None
        commit = subprocess.run(["git", "log", "-1", "--format=%h", "--", relative], cwd=PROJECT,
                                capture_output=True, text=True).stdout.strip()
        return relative, target.read_text(encoding="utf-8"), commit

    async def get_source(request: Request) -> Response:
        found = source_text(request.query_params.get("page", ""))
        if found is None:
            return JSONResponse({"error": "this page has no editable source"}, status_code=404)
        relative, text, commit = found
        return JSONResponse({"path": relative, "text": text, "commit": commit})

    async def suggest(request: Request) -> Response:
        try:
            body = await _body(request)
            page_key = str(body.get("page") or "")
            if (blocked := frozen_response(page_key)) is not None:
                return blocked
            found = source_text(page_key)
            if found is None:
                raise store.FeedbackError("this page has no editable source")
            relative, base_text, commit = found
            new_text = str(body.get("new_text") or "")
            if new_text.replace("\r\n", "\n") == base_text:
                raise store.FeedbackError("nothing changed")
            new_text = new_text.replace("\r\n", "\n")
            diff = "".join(difflib.unified_diff(base_text.splitlines(keepends=True), new_text.splitlines(keepends=True),
                                                fromfile=f"a/{relative}", tofile=f"b/{relative}", n=2))
            event = await append(request, {
                "type": "create", "page": page_key, "page_title": body.get("page_title"), "page_commit": commit,
                "text": str(body.get("text") or "").strip() or "Suggested edit (no comment).",
                "author": _author(request),
                "suggestion": {"path": relative, "base_commit": commit, "base_text": base_text, "new_text": new_text,
                               "diff": diff}}, events_path)
        except store.FeedbackError as error:
            return JSONResponse({"error": str(error)}, status_code=400)
        return await thread_json(event["thread_id"])

    async def login(request: Request) -> Response:
        if request.method == "GET":
            next_url = request.query_params.get("next", "/")
            return HTMLResponse(LOGIN_PAGE.format(title=html.escape(SETTINGS["title"]), error="", name=html.escape(reader_name(request)),
                                                  next=html.escape(next_url)))
        form = await request.form()
        next_url = str(form.get("next") or "/")
        if not next_url.startswith("/") or next_url.startswith("//"):
            next_url = "/"
        name = str(form.get("name") or "").strip()[: store.MAX_NAME]
        if not token or not hmac.compare_digest(auth_token(str(form.get("password") or "")), token):
            return HTMLResponse(LOGIN_PAGE.format(title=html.escape(SETTINGS["title"]), error="<p class='err'>Wrong password.</p>", name=html.escape(name),
                                                  next=html.escape(next_url)), status_code=401)
        response = RedirectResponse(next_url, status_code=303)
        response.set_cookie(AUTH_COOKIE, token, max_age=COOKIE_DAYS * 86400, httponly=True, samesite="lax")
        if name:
            response.set_cookie(NAME_COOKIE, quote(name), max_age=365 * 86400, samesite="lax")
        return response

    async def list_threads(request: Request) -> Response:
        page = request.query_params.get("page")
        info = states.context()
        items = []
        for thread in store.threads(events_path):
            if page is None or thread.page == page:
                item = thread.to_dict()
                item["state"], item["state_label"] = states.state_of(thread, info)
                items.append(item)
        items.sort(key=lambda item: states.sort_key(item, info))
        return JSONResponse({"threads": items, "you": reader_name(request)})

    async def append(request: Request, event: dict, path: Path) -> dict:
        """store.append_event off the event loop (a slow fsync must not block other readers), with the
        browser's request key (X-Kea-Request) so that a submit sent twice is stored once."""
        key = request.headers.get("x-kea-request", "").strip()[:80]
        return await run_in_threadpool(store.append_event, {**event, "request_id": key} if key else event, path)

    async def thread_json(thread_id: str) -> Response:
        threads = await run_in_threadpool(lambda: store.fold(store.load_events(events_path)))
        return JSONResponse({"thread": threads[thread_id].to_dict()})

    async def _body(request: Request) -> dict:
        try:
            body = await request.json()
        except ValueError as error:
            raise store.FeedbackError("body must be JSON") from error
        if not isinstance(body, dict):
            raise store.FeedbackError("body must be a JSON object")
        return body

    def _author(request: Request) -> str:
        name = reader_name(request)
        if not name:
            raise store.FeedbackError("set your name first")
        if name.lower() == "claude":
            raise store.FeedbackError("the name 'claude' is reserved for replies written by the assistant")
        return name

    async def create_thread(request: Request) -> Response:
        try:
            body = await _body(request)
            if (blocked := frozen_response(str(body.get("page") or ""))) is not None:
                return blocked
            event = await append(request, {**{key: body.get(key) for key in (
                "page", "page_title", "page_commit", "quote", "prefix", "suffix", "start", "end", "text")},
                "type": "create", "author": _author(request)}, events_path)
        except store.FeedbackError as error:
            return JSONResponse({"error": str(error)}, status_code=400)
        return await thread_json(event["thread_id"])

    async def reply(request: Request) -> Response:
        thread_id = request.path_params["thread_id"]
        if (blocked := frozen_response(page_of_thread(thread_id))) is not None:
            return blocked
        try:
            body = await _body(request)
            await append(request, {"type": "reply", "thread_id": thread_id, "text": body.get("text"),
                                "author": _author(request)}, events_path)
        except store.FeedbackError as error:
            return JSONResponse({"error": str(error)}, status_code=400)
        return await thread_json(thread_id)

    async def set_status(request: Request) -> Response:
        thread_id = request.path_params["thread_id"]
        if (blocked := frozen_response(page_of_thread(thread_id))) is not None:
            return blocked
        try:
            body = await _body(request)
            if body.get("status") not in READER_STATUSES:
                raise store.FeedbackError(f"readers can set: {', '.join(READER_STATUSES)}")
            await append(request, {"type": "status", "thread_id": thread_id, "status": body.get("status"),
                                "note": body.get("note"), "author": _author(request)}, events_path)
        except store.FeedbackError as error:
            return JSONResponse({"error": str(error)}, status_code=400)
        return await thread_json(thread_id)

    async def download(request: Request) -> Response:
        relative = request.path_params["path"]
        allowed_file = site_dir / "_files.json"
        allowed = set(json.loads(allowed_file.read_text())) if allowed_file.exists() else set()
        if relative not in allowed:
            return JSONResponse({"error": "not a published artefact"}, status_code=404)
        target = (PROJECT / relative).resolve()
        if not target.is_relative_to(PROJECT) or not target.is_file():
            return JSONResponse({"error": "missing"}, status_code=404)
        return FileResponse(target, filename=target.name)

    routes = [
        Route("/login", login, methods=["GET", "POST"]),
        Route("/files/{path:path}", download, methods=["GET"]),
        Route("/api/status", status, methods=["GET"]),
        Route("/api/cycle/{action}", cycle_action, methods=["POST"]),
        Route("/api/source", get_source, methods=["GET"]),
        Route("/api/suggest", suggest, methods=["POST"]),
        Route("/api/threads", list_threads, methods=["GET"]),
        Route("/api/threads", create_thread, methods=["POST"]),
        Route("/api/threads/{thread_id}/reply", reply, methods=["POST"]),
        Route("/api/threads/{thread_id}/status", set_status, methods=["POST"]),
        Mount("/", StaticFiles(directory=site_dir, html=True, check_dir=False)),
    ]
    return Starlette(routes=routes, middleware=[Middleware(PasswordGate, password=password)])


def service_name() -> str:
    slug = "".join(char if char.isalnum() or char in "-_" else "-" for char in PROJECT.name.lower())
    return f"kea-{slug}.service"


def install_service(args) -> int:
    """Write ~/.config/systemd/user/kea-<project>.service running `kea serve` with this interpreter."""
    import shlex
    import subprocess
    import sys
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    log = PROJECT / str(SETTINGS["feedback_dir"]) / "server.log"
    command = " ".join(shlex.quote(part) for part in [sys.executable, "-m", "kea.cli", "serve", "--host", args.host,
                                                       "--port", str(args.port)])
    unit = (f"[Unit]\nDescription=Kea site {SETTINGS['title']} ({PROJECT})\nAfter=network-online.target\n\n"
            f"[Service]\nWorkingDirectory={PROJECT}\nEnvironment=KEA_PROJECT={PROJECT}\nExecStart={command}\n"
            f"Restart=on-failure\nRestartSec=5\nStandardOutput=append:{log}\nStandardError=append:{log}\n\n"
            "[Install]\nWantedBy=default.target\n")
    target = unit_dir / service_name()
    target.write_text(unit)
    print(f"wrote {target}")
    steps = [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", service_name()]]
    if args.enable:
        for step in steps:
            result = subprocess.run(step, capture_output=True, text=True)
            print(" ".join(step), "->", "ok" if result.returncode == 0 else result.stderr.strip())
    else:
        print("start it with:\n  " + "\n  ".join(" ".join(step) for step in steps))
    print(f"logs: {log}; status: systemctl --user status {service_name()}\n"
          "Without 'loginctl enable-linger' the service stops when you log out.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", default=str(SETTINGS["host"]))
    parser.add_argument("--port", type=int, default=int(SETTINGS["port"]))
    parser.add_argument("--site", type=Path, default=SITE_DIR)
    parser.add_argument("--events", type=Path, default=store.default_path())
    parser.add_argument("--cycle", type=Path, default=cycle.default_path())
    parser.add_argument("--no-password", action="store_true", help="serve without the password (local testing only)")
    parser.add_argument("--install-service", action="store_true",
                        help="write a systemd user unit that runs this server (survives logout and reboot)")
    parser.add_argument("--enable", action="store_true", help="with --install-service: enable and start it now")
    args = parser.parse_args(argv)
    if args.install_service:
        return install_service(args)
    load_dotenv(PROJECT / ".env")
    password = "" if args.no_password else os.environ.get("SITE_PASSWORD", "")
    if not password and not args.no_password:
        parser.error("SITE_PASSWORD is not set in .env (or pass --no-password for local testing)")
    import uvicorn

    uvicorn.run(make_app(args.site, args.events, password, args.cycle), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
