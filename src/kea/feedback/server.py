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

Review cycle (feedback.cycle): comments everywhere until a PI asks Claude to implement the plan; while
implementation is requested or running, new comments, replies and status changes are refused (HTTP 423).

API (JSON):
    GET  /api/threads?page=<path>   threads of one page (all pages without ?page=)
    POST /api/threads               {page, page_title, page_commit, quote, prefix, suffix, start, end, text, tags}
                                    (text optional with tags; tags checked against the site's _feedback/tags.json)
    POST /api/threads/<id>/reply    {text}
    POST /api/threads/<id>/tags     {tags}: replace the thread's tags (marks may change while comments are paused)
    GET  /id/<uid>                  redirect to the page with that permanent id (/id/<uid>.json: its public facts)
    POST /api/threads/<id>/status   {status, note}   (readers may set resolved or open)
    GET  /api/status                cycle state, site build id, comment counts (polled by every page)
    GET  /api/source?page=<key>     the Markdown source of a documentation page (for the editor)
    POST /api/suggest               {page, page_title, text, new_text}: a suggested edit, stored as a thread with the
                                    diff; files are never written by the server
    POST /api/cycle/harvest         a PI asks Claude to fold the comments not yet in the plan into it
    POST /api/cycle/implement       a PI asks Claude to implement the plan (only after a harvest; comments
                                    made since stay for the next cycle)
    POST /api/cycle/cancel          a PI withdraws a request Claude has not started on
    POST /api/steer                 {password}: the iteration password; when one is set (SITE_STEER_PASSWORD, or the
                                    hub's per-project one) the four cycle actions need it (403 {need_steer} without)

Two passwords: the site password makes a reader a reviewer; the iteration password (optional locally, always on
the hub) makes them a PI: it also lets them harvest the comments into the plan, ask Claude to implement it, or
cancel a request. On a hub with ORCID accounts the role comes from the account instead (accounts.ROLES: auditor,
reviewer, PI, director); the login page then offers ORCID first and folds the password form away.
All paths are relative to the site root, so the same app serves a project under a prefix (kea hub: /p/<name>/).

Usage: kea serve [--host <ip>] [--port <port>]   (defaults from kea.yaml)
Security: `kea serve` is meant for a trusted network (plain http); `kea hub serve` runs behind an https proxy.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import hmac
import html
import re
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
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
from kea import __version__
from kea.feedback import cycle, states, store, tags

PROJECT = PROJECT_ROOT
AUTH_COOKIE = "fb_auth"
SSO_COOKIE = "kea_sso_tried"             # the hub was asked for a session in the last hour (no loop, no repeat)
STEER_COOKIE = "fb_steer"
NAME_COOKIE = "fb_name"
COOKIE_DAYS = 90
READER_STATUSES = ("resolved", "open")


def default_salt() -> str:
    return str(SETTINGS.get("cookie_salt") or f"kea-site:{PROJECT_ROOT.name}")          # per site, kea.yaml


def auth_token(password: str, salt: str | None = None) -> str:
    """Cookie value proving the password was entered; changes when the password changes."""
    salt_bytes = (salt if salt is not None else default_salt()).encode()
    return hmac.new(password.encode(), salt_bytes, hashlib.sha256).hexdigest()


def steer_token(password: str, salt: str | None = None) -> str:
    """Cookie value proving the iteration password was entered (a different value from the site password's)."""
    return auth_token(password, (salt if salt is not None else default_salt()) + ":steer")


def site_root(request: Request) -> str:
    """The prefix this site is served under ('' for kea serve, '/p/<name>' on a hub)."""
    return str(request.scope.get("root_path", "")).rstrip("/")


def local_path(request: Request) -> str:
    """The request path relative to the site root ('/login', '/api/status', …)."""
    root, path = site_root(request), request.url.path
    return path[len(root):] or "/" if root and path.startswith(root) else path


class LoginThrottle:
    """At most LIMIT wrong passwords per client address per WINDOW seconds (in memory; resets on restart)."""
    LIMIT, WINDOW = 10, 600

    def __init__(self):
        self.failures: dict[str, list[float]] = {}

    def blocked(self, client: str) -> bool:
        recent = [moment for moment in self.failures.get(client, []) if moment > time.time() - self.WINDOW]
        self.failures[client] = recent
        return len(recent) >= self.LIMIT

    def failed(self, client: str) -> None:
        self.failures.setdefault(client, []).append(time.time())


def reader_name(request: Request) -> str:
    account = request.scope.get("kea_account")
    if account:                                   # signed in with ORCID (kea hub): the verified name
        return str(account.get("name") or account.get("orcid"))[: store.MAX_NAME]
    return unquote(request.cookies.get(NAME_COOKIE, "")).strip()[: store.MAX_NAME]


LOGIN_PAGE = """<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Sign in</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;background:#f6f7f9;color:#1d2330;display:grid;place-items:center;min-height:90vh;margin:0;padding:0 14px}}
.card{{background:#fff;padding:28px 32px;border-radius:10px;box-shadow:0 1px 4px #0002;max-width:360px;width:100%;box-sizing:border-box}}
h1{{font-size:19px;margin:0 0 6px}}p{{color:#555;font-size:13.5px;margin:0 0 16px}}label{{display:block;font-size:13px;margin:10px 0 4px}}
input{{width:100%;box-sizing:border-box;padding:8px;border:1px solid #bbb;border-radius:6px;font:inherit}}
button{{margin-top:16px;padding:8px 16px;border:0;border-radius:6px;background:#1f5fa8;color:#fff;font:inherit;cursor:pointer}}
.err{{color:#a00;font-size:13px}}
.orcid-button{{display:flex;align-items:center;justify-content:center;gap:10px;margin:18px 0 10px;padding:13px 16px;
border-radius:8px;background:#a6ce39;color:#1d2330;font-weight:700;font-size:16px;text-decoration:none}}
.orcid-button:hover{{background:#97bd2f}}
.orcid-id{{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:50%;background:#fff;color:#a6ce39;
font-size:12px;font-weight:800}}
details{{margin-top:18px;border-top:1px solid #e3e5ea;padding-top:10px}}
summary{{cursor:pointer;color:#5a6270;font-size:13px}}details form{{margin-top:12px}}details p{{margin-bottom:6px}}</style>
<main class='card'>
<h1>{title}</h1>
{body}
</main>"""
PASSWORD_FORM = """<form method='post' action='{action}'>
<p>Internal working site. Enter the shared password. Your name is used to sign your comments.</p>
{error}
<label for='name'>Your name</label><input id='name' name='name' value='{name}' maxlength='60' autocomplete='name'>
<label for='password'>Password</label><input id='password' name='password' type='password'{autofocus}>
<input type='hidden' name='next' value='{next}'>
<button>Enter</button></form>"""
ORCID_SIGN_IN = """<p>Sign in with your ORCID iD. One sign-in opens every project on this hub you have access to.</p>
<a class='orcid-button' href='{href}'><span class='orcid-id' aria-hidden='true'>iD</span>Sign in with ORCID</a>
<details{open}><summary>Sign in with a project password</summary>
{form}
</details>"""


class PasswordGate(BaseHTTPMiddleware):
    """Lets a request through with the site password's cookie or a signed-in account (kea hub, ORCID). Refuses a
    write whose Origin is another host: project sites on sibling subdomains are 'same site' for the browser, so
    without this a page of one project could post to another project's API with the reader's cookie."""

    def __init__(self, app, token: str, account=None, public=None, sso_url=None):
        super().__init__(app)
        self.token = token
        self.account = account
        self.public = public or (lambda: False)
        self.sso_url = sso_url                   # kea hub: where to ask for an existing hub session (or None)

    async def dispatch(self, request: Request, call_next):
        path = local_path(request)
        origin = request.headers.get("origin", "")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin != "null" \
                and origin.split("://")[-1].lower() != request.headers.get("host", "").lower():
            return JSONResponse({"error": "cross-site request refused"}, status_code=403)
        writing = request.method not in ("GET", "HEAD", "OPTIONS")
        account = self.account(request) if self.account else None
        if account:
            request.scope["kea_account"] = account
            if writing and account.get("role") == "auditor" and path != "/login":
                return JSONResponse({"error": "you can read this site but not comment (your role is auditor; the "
                                              "hub's administrator can make you a reviewer)", "read_only": True},
                                    status_code=403)
            return await call_next(request)
        if not self.token or path in ("/login", "/logout", "/favicon.ico"):
            return await call_next(request)
        if hmac.compare_digest(request.cookies.get(AUTH_COOKIE, ""), self.token):
            return await call_next(request)
        target = path + (f"?{request.url.query}" if request.url.query else "")
        page_visit = not writing and not path.startswith(("/api/", "/files/", "/_")) and path not in ("/login", "/logout")
        if page_visit and self.sso_url and not request.cookies.get(SSO_COOKIE):
            check = self.sso_url(request, target)   # signed in on the hub already? then in without a click
            if check:
                response = RedirectResponse(check, status_code=303)
                response.set_cookie(SSO_COOKIE, "1", max_age=3600, httponly=True, samesite="lax",
                                    secure=request.url.scheme == "https", path=site_root(request) + "/")
                return response
        if not writing and self.public() and is_public_path(path):
            return await call_next(request)      # a public project: its pages without a login
        if path.startswith("/api/"):
            return JSONResponse({"error": "not signed in"}, status_code=401)
        return RedirectResponse(f"{site_root(request)}/login?next={quote(target)}", status_code=303)


def is_public_path(path: str) -> bool:
    """What a public project shows without a login: the pages, the PDF, the assets and /id/ links. Not the comments
    and the review cycle (/api/), and not the uploaded data files (/files/): those still need a sign-in."""
    return not (path.startswith("/api/") or path.startswith("/files/"))


@dataclass
class SiteSpec:
    """Everything one hosted site needs (kea serve: this project; kea hub: one project's current release)."""
    site_dir: Path
    events_path: Path
    cycle_path: Path | None = None
    heartbeat_path: Path | None = None
    reader_token: str = ""                 # auth_token(site password); '' = no password (local testing)
    steer_token: str = ""                  # steer_token(iteration password); '' = any signed-in reader may steer
    title: str = ""
    salt: str | None = None                # cookie salt; None = kea.yaml's (kea serve)
    source_root: Path = PROJECT_ROOT       # where the doc/*.md of _sources.json live
    files_root: Path = PROJECT_ROOT        # where the downloads of _files.json live
    source_commit: Callable[[str], str] = field(default=lambda relative: "")
    states_context: Callable[[], dict] = field(default=lambda: states.context())
    versions_dir: Path | None = None       # kea hub: stored page versions (versions/<uid>/<version>.md)
    account: Callable[[Request], dict | None] | None = None      # kea hub: signed-in reader {orcid, name, role}
    login_url: Callable[[Request, str], str | None] | None = None  # kea hub: "Sign in with ORCID" for this next
    public: Callable[[], bool] | None = None   # kea hub: True = pages readable without a login (kea hub public)
    sso_url: Callable[[Request, str], str | None] | None = None   # kea hub: ask the hub for its ORCID session
    hub_menu: Callable[[dict | None], dict] | None = None   # kea hub: {home, projects} for the reader's name menu


def make_app(site_dir: Path, events_path: Path, password: str, cycle_path: Path | None = None,
             heartbeat_path: Path | None = None, steer_password: str = "") -> Starlette:
    """The app of `kea serve`: this project, passwords from .env."""
    return make_site_app(SiteSpec(site_dir=site_dir, events_path=events_path, cycle_path=cycle_path,
                                  heartbeat_path=heartbeat_path, title=str(SETTINGS["title"]),
                                  reader_token=auth_token(password) if password else "",
                                  steer_token=steer_token(steer_password) if steer_password else "",
                                  source_root=PROJECT, files_root=PROJECT, source_commit=git_commit_of))


def git_commit_of(relative: str) -> str:
    """Commit of the last change of a project file (kea serve; the hub takes it from the published bundle)."""
    return subprocess.run(["git", "log", "-1", "--format=%h", "--", relative], cwd=PROJECT, capture_output=True,
                          text=True).stdout.strip()


def make_site_app(spec: SiteSpec) -> Starlette:
    site_dir, events_path, cycle_path, heartbeat_path = (spec.site_dir, spec.events_path, spec.cycle_path,
                                                         spec.heartbeat_path)
    token = spec.reader_token
    throttle = LoginThrottle()

    def auth_token_for(password: str) -> str:
        return auth_token(password, spec.salt)

    def steer_token_for(password: str) -> str:
        return steer_token(password, spec.salt)

    def secure(request: Request) -> bool:
        return request.url.scheme == "https"

    def frozen_response(page_key: str) -> Response | None:
        current = cycle.state(cycle_path)
        if current.accepts_comments_on(page_key):
            return None
        message = f"comments are paused while the plan is implemented ({current.state})"
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
                             "watcher_seen_at": cycle.read_heartbeat(heartbeat_path),
                             "watcher": cycle.watcher_status(cycle.read_heartbeat_info(heartbeat_path)),
                             "can_steer": may_steer(request), **signed_in(request),
                             "hub": spec.hub_menu(request.scope.get("kea_account")) if spec.hub_menu else None,
                             "server_version": __version__, "on_hub": spec.hub_menu is not None})

    def signed_in(request: Request) -> dict:
        """Who the reader is for the menu bar: signed in (account or site password) and where to sign out."""
        account = request.scope.get("kea_account")
        if account:
            return {"signed_in": True, "account": True, "orcid": account.get("orcid", ""),
                    "sign_out": site_root(request) + "/auth/logout"}
        with_password = bool(token) and hmac.compare_digest(request.cookies.get(AUTH_COOKIE, ""), token)
        return {"signed_in": with_password, "account": False, "orcid": "",
                "sign_out": site_root(request) + "/logout" if with_password else ""}

    async def logout(request: Request) -> Response:
        """Sign out of the site password: forget the password and steering cookies (the name stays, for next time)."""
        root = site_root(request)
        response = RedirectResponse(root + "/login", status_code=303)
        for name in (AUTH_COOKIE, STEER_COOKIE):
            response.delete_cookie(name, path=root + "/")
        return response

    def may_steer(request: Request) -> bool:
        account = request.scope.get("kea_account")
        if account and account.get("role") in ("pi", "director"):        # accounts.ROLES
            return True
        return not spec.steer_token or hmac.compare_digest(request.cookies.get(STEER_COOKIE, ""), spec.steer_token)

    async def steer(request: Request) -> Response:
        client = request.client.host if request.client else "?"
        if throttle.blocked(client):
            return JSONResponse({"error": "too many wrong passwords; try again in ten minutes"}, status_code=429)
        try:
            body = await _body(request)
        except store.FeedbackError as error:
            return JSONResponse({"error": str(error)}, status_code=400)
        if not spec.steer_token:
            return JSONResponse({"ok": True, "note": "this site has no iteration password"})
        if not hmac.compare_digest(steer_token_for(str(body.get("password") or "")), spec.steer_token):
            throttle.failed(client)
            return JSONResponse({"error": "wrong iteration password"}, status_code=403)
        response = JSONResponse({"ok": True})
        response.set_cookie(STEER_COOKIE, spec.steer_token, max_age=COOKIE_DAYS * 86400, httponly=True,
                            samesite="lax", secure=secure(request), path=site_root(request) + "/")
        return response

    async def cycle_action(request: Request) -> Response:
        action = request.path_params["action"]
        if not may_steer(request):
            return JSONResponse({"error": "this needs the iteration password", "need_steer": True}, status_code=403)
        try:
            name = _author(request)
            kind = {"harvest": "harvest-requested", "implement": "implement-requested",
                    "cancel": "cancelled"}.get(action)
            if kind is None:
                raise store.FeedbackError("unknown action")
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
        root = spec.source_root.resolve()
        target = (root / relative).resolve()
        if not target.is_relative_to(root / "doc") or not target.is_file():
            return None
        return relative, target.read_text(encoding="utf-8"), spec.source_commit(relative)

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

    def login_page(request: Request, error: str, name: str, next_url: str, status: int = 200) -> HTMLResponse:
        orcid = spec.login_url(request, next_url) if spec.login_url else None
        form = PASSWORD_FORM.format(error=error, name=html.escape(name), next=html.escape(next_url),
                                    action=html.escape(site_root(request) + "/login"),
                                    autofocus="" if orcid and not error else " autofocus")
        if orcid:            # kea hub with ORCID: the account first and large; the shared password folded away
            body = ORCID_SIGN_IN.format(href=html.escape(orcid), open=" open" if error else "", form=form)
        else:
            body = form
        page = LOGIN_PAGE.format(title=html.escape(spec.title or "Kea site"), body=body)
        return HTMLResponse(page, status_code=status)

    async def login(request: Request) -> Response:
        root = site_root(request)
        if request.method == "GET":
            return login_page(request, "", reader_name(request), request.query_params.get("next", "/"))
        form = await request.form()
        next_url = str(form.get("next") or "/")
        if not next_url.startswith("/") or next_url.startswith("//"):
            next_url = "/"
        name = str(form.get("name") or "").strip()[: store.MAX_NAME]
        client = request.client.host if request.client else "?"
        if throttle.blocked(client):
            return login_page(request, "<p class='err'>Too many wrong passwords; try again in ten minutes.</p>", name,
                              next_url, 429)
        if not token or not hmac.compare_digest(auth_token_for(str(form.get("password") or "")), token):
            throttle.failed(client)
            return login_page(request, "<p class='err'>Wrong password.</p>", name, next_url, 401)
        response = RedirectResponse(root + next_url, status_code=303)
        response.set_cookie(AUTH_COOKIE, token, max_age=COOKIE_DAYS * 86400, httponly=True, samesite="lax",
                            secure=secure(request), path=root + "/")
        if name:
            response.set_cookie(NAME_COOKIE, quote(name), max_age=365 * 86400, samesite="lax", secure=secure(request),
                                path=root + "/")
        return response

    async def list_threads(request: Request) -> Response:
        page = request.query_params.get("page")
        info = spec.states_context()
        items = []
        for thread in store.threads(events_path):
            if page is None or thread.page == page:
                item = thread.to_dict()
                item["state"], item["state_label"] = states.state_of(thread, info)
                items.append(item)
        items.sort(key=lambda item: states.sort_key(item, info))
        account = request.scope.get("kea_account") or {}
        return JSONResponse({"threads": items, "you": reader_name(request), "tags": tags.site_vocabulary(site_dir),
                             "can_write": account.get("role") != "auditor", "account": bool(account)})

    def tag_fields(body: dict, on_text: bool = False, new: bool = False) -> dict:
        """The tags of a request, checked against the site's tag list, and whether they are all mark tags. A new
        thread with a proposal (needs_text) needs its text: the proposal itself."""
        try:
            known = tags.site_vocabulary(site_dir)
            names = tags.check(body.get("tags"), known, on_text)
            if new and not str(body.get("text") or "").strip():
                wordless = [tag["label"] for tag in known["tags"] if tag["name"] in names and tag.get("needs_text")]
                if wordless:
                    raise tags.TagError(f"write your proposal ({', '.join(wordless)})")
        except tags.TagError as error:
            raise store.FeedbackError(str(error)) from error
        return {"tags": names, "mark": tags.is_mark(names, known)}

    async def append(request: Request, event: dict, path: Path) -> dict:
        """store.append_event off the event loop (a slow fsync must not block other readers), with the
        browser's request key (X-Kea-Request) so that a submit sent twice is stored once."""
        key = request.headers.get("x-kea-request", "").strip()[:80]
        account = request.scope.get("kea_account")
        if account and event.get("author") != "claude":
            event = {**event, "author_id": account.get("orcid", "")}    # the verified ORCID iD of the writer
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
            fields = tag_fields(body, on_text=bool(str(body.get("quote") or "").strip()), new=True)
            # marks (manuscript tags) ask for no work, so they are taken also while comments are paused
            if not fields["mark"] and (blocked := frozen_response(str(body.get("page") or ""))) is not None:
                return blocked
            event = await append(request, {**{key: body.get(key) for key in (
                "page", "page_title", "page_commit", "quote", "prefix", "suffix", "start", "end", "text")},
                **fields, "type": "create", "author": _author(request)}, events_path)
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

    async def set_tags(request: Request) -> Response:
        thread_id = request.path_params["thread_id"]
        try:
            body = await _body(request)
            thread = store.fold(store.load_events(events_path)).get(thread_id)
            fields = tag_fields(body, on_text=bool(thread and thread.quote))
            only_marks = fields["mark"] or not fields["tags"]
            if not (only_marks and thread is not None and thread.status == "marked") and \
                    (blocked := frozen_response(page_of_thread(thread_id))) is not None:
                return blocked
            await append(request, {"type": "tags", "thread_id": thread_id, **fields,
                                   "author": _author(request)}, events_path)
            if not fields["tags"] and thread is not None and not thread.text and not thread.replies \
                    and thread.status != "resolved":
                # the last tag of a tag-only thread taken off: nothing is left to answer
                key = request.headers.get("x-kea-request", "").strip()[:70]
                await run_in_threadpool(store.append_event, {
                    "type": "status", "thread_id": thread_id, "status": "resolved", "note": "tags removed",
                    "author": _author(request), **({"request_id": key + "-resolve"} if key else {})}, events_path)
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

    async def resolve_id(request: Request) -> Response:
        """/id/<uid>: redirect to the page with that permanent id; /id/<uid>.json: its public facts (_ids.json)."""
        name = request.path_params["uid"]
        as_json = name.endswith(".json")
        uid, _, version = (name[:-5] if as_json else name).partition("@")
        try:
            known = json.loads((site_dir / "_ids.json").read_text())
        except (OSError, ValueError):
            known = {}
        entry = known.get(uid)
        if entry is None:
            return JSONResponse({"error": f"no page with id {uid}"}, status_code=404)
        if version and version != entry.get("version"):
            return stored_version(request, uid, version, entry, as_json)
        if as_json:
            return JSONResponse({"id": f"kea:{uid}", **entry, "url": site_root(request) + "/" + entry["url"]})
        return RedirectResponse(site_root(request) + "/" + entry["url"], status_code=303)

    def stored_version(request: Request, uid: str, version: str, entry: dict, as_json: bool) -> Response:
        """An earlier version of a page, from the hub's version store, with a pointer to the current page."""
        folder = spec.versions_dir
        if folder is None or not re.match(r"^[a-z2-7]{20}$", version) or not (folder / uid / f"{version}.md").is_file():
            return JSONResponse({"error": f"version {version} of kea:{uid} is not stored here (the current version is "
                                          f"{entry.get('version', '?')})"}, status_code=404)
        text = (folder / uid / f"{version}.md").read_text(encoding="utf-8")
        facts = json.loads((folder / uid / f"{version}.json").read_text())
        current = site_root(request) + "/" + entry["url"]
        if as_json:
            return JSONResponse({"id": f"kea:{uid}@{version}", **facts, "current_version": entry.get("version"),
                                 "current_url": current, "markdown": text})
        return HTMLResponse(
            f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
            f"initial-scale=1'><title>{html.escape(facts.get('title', uid))} (earlier version)</title><style>"
            "body{font:15.5px/1.6 system-ui,sans-serif;color:#1d2330;max-width:900px;margin:30px auto;padding:0 18px}"
            ".note{background:#fff3c4;border-left:4px solid #e0a030;padding:8px 12px;margin:0 0 16px}"
            "pre{white-space:pre-wrap;background:#f5f7fa;padding:12px;border-radius:6px;font:13px/1.5 ui-monospace,monospace}"
            "</style></head><body>"
            f"<div class='note'>Version <code>{html.escape(version)}</code> of <code>kea:{html.escape(uid)}</code>, "
            f"stored {html.escape(facts.get('stored_at', '')[:10])}. This is not the current text: "
            f"<a href='{html.escape(current)}'>the page as it is now</a>.</div>"
            f"<h1>{html.escape(facts.get('number', ''))} {html.escape(facts.get('title', ''))}</h1>"
            f"<pre>{html.escape(text)}</pre></body></html>")

    async def download(request: Request) -> Response:
        relative = request.path_params["path"]
        allowed_file = site_dir / "_files.json"
        allowed = set(json.loads(allowed_file.read_text())) if allowed_file.exists() else set()
        if relative not in allowed:
            return JSONResponse({"error": "not a published artefact"}, status_code=404)
        root = spec.files_root.resolve()
        target = (root / relative).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            return JSONResponse({"error": "missing"}, status_code=404)
        return FileResponse(target, filename=target.name)

    routes = [
        Route("/login", login, methods=["GET", "POST"]),
        Route("/logout", logout, methods=["GET"]),
        Route("/files/{path:path}", download, methods=["GET"]),
        Route("/id/{uid}", resolve_id, methods=["GET"]),
        Route("/api/status", status, methods=["GET"]),
        Route("/api/cycle/{action}", cycle_action, methods=["POST"]),
        Route("/api/steer", steer, methods=["POST"]),
        Route("/api/source", get_source, methods=["GET"]),
        Route("/api/suggest", suggest, methods=["POST"]),
        Route("/api/threads", list_threads, methods=["GET"]),
        Route("/api/threads", create_thread, methods=["POST"]),
        Route("/api/threads/{thread_id}/reply", reply, methods=["POST"]),
        Route("/api/threads/{thread_id}/status", set_status, methods=["POST"]),
        Route("/api/threads/{thread_id}/tags", set_tags, methods=["POST"]),
        Mount("/", StaticFiles(directory=site_dir, html=True, check_dir=False)),
    ]
    return Starlette(routes=routes, middleware=[Middleware(PasswordGate, token=token, account=spec.account,
                                                                  public=spec.public, sso_url=spec.sso_url)])


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

    steer = "" if args.no_password else os.environ.get("SITE_STEER_PASSWORD", "")
    if not steer and not args.no_password:
        print("note: no SITE_STEER_PASSWORD in .env: every signed-in reader is a PI and may harvest comments and ask Claude to "
              "implement the plan")
    uvicorn.run(make_app(args.site, args.events, password, args.cycle, steer_password=steer), host=args.host,
                port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
