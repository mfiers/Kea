"""Hub accounts: readers sign in with ORCID; the hub owner approves them; roles per project.

Why: a shared password per project means a second login for every project a reader follows a link into, and a
comment or a Confirm signed with whatever name was typed. With accounts a reader signs in once, and every comment,
tag and verdict carries a verified ORCID iD (``author_id`` in the event log).

Flow (hub.yaml ``project_domain`` set, each project on its own subdomain; all cookies host-only):
    <project>.<domain>/login             "Sign in with ORCID" links to the apex
    <domain>/auth/login?return=<url>     with a valid apex session: straight to the code below; else to ORCID
    orcid.org /oauth/authorize           the reader signs in at ORCID (scope openid)
    <domain>/auth/orcid/callback         the code is exchanged at ORCID for the reader's iD and name; a new iD is
                                         recorded as pending; an approved one gets the apex session cookie
                                         (__Host-kea_session) and a one-time code for the project
    <project>.<domain>/auth/finish       the code (signed, 60 s, single use, bound to that host) becomes the
                                         project's own session cookie (kea_account)
Without project_domain the same works under /p/<project>/ (cookie path /p/<project>/).

Roles: reader < commenter < steerer (freeze, implement) < owner. A user's role in a project is roles[<project>],
else roles["*"]; approving gives roles["*"] = commenter unless told otherwise. The project passwords keep working
next to accounts.

Users live in <hub>/users.json (no secrets); the signing secret in <hub>/secret.key (0600). The ORCID client comes
from the environment: KEA_ORCID_CLIENT_ID, KEA_ORCID_CLIENT_SECRET (and KEA_ORCID_BASE, default https://orcid.org,
https://sandbox.orcid.org for testing). Without a client the hub has no ORCID sign-in and works as before.

    kea hub users                          list (pending first)
    kea hub users approve <orcid> [--role commenter] [--project <name>|*]
    kea hub users role <orcid> <role> [--project <name>|*]
    kea hub users block <orcid>
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

ORCID_ID = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
ROLES = ("reader", "commenter", "steerer", "owner")
APEX_COOKIE = "__Host-kea_session"        # host-only on the apex: Secure, Path=/, no Domain (browser-enforced)
SITE_COOKIE = "kea_account"               # host-only on a project subdomain (or path /p/<name>/)
SESSION_DAYS = 30
CODE_SECONDS = 60
_lock = threading.Lock()


def rank(role: str) -> int:
    return ROLES.index(role) if role in ROLES else -1


def orcid_settings() -> dict:
    """The ORCID client from the environment; {} when not configured."""
    client_id = os.environ.get("KEA_ORCID_CLIENT_ID", "").strip()
    secret = os.environ.get("KEA_ORCID_CLIENT_SECRET", "").strip()
    if not (client_id and secret):
        return {}
    return {"client_id": client_id, "secret": secret,
            "base": os.environ.get("KEA_ORCID_BASE", "https://orcid.org").rstrip("/")}


def exchange_code(code: str, redirect_uri: str, settings: dict) -> dict:
    """ORCID's token endpoint: the authorisation code -> {"orcid": iD, "name": name}. Server to server over https,
    so the answer is trusted as is (no id_token signature check needed)."""
    data = urllib.parse.urlencode({"client_id": settings["client_id"], "client_secret": settings["secret"],
                                   "grant_type": "authorization_code", "code": code,
                                   "redirect_uri": redirect_uri}).encode()
    request = urllib.request.Request(settings["base"] + "/oauth/token", data=data,
                                     headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        answer = json.loads(response.read())
    return {"orcid": str(answer.get("orcid", "")), "name": str(answer.get("name") or "")}


class Accounts:
    def __init__(self, folder: Path):
        self.folder = folder
        self.path = folder / "users.json"
        self.used_codes: dict[str, float] = {}

    # ---- signing ----
    def secret(self) -> bytes:
        path = self.folder / "secret.key"
        if not path.exists():
            with _lock:
                if not path.exists():
                    temporary = path.with_suffix(".tmp")
                    temporary.write_text(secrets.token_hex(32))
                    os.chmod(temporary, 0o600)
                    os.replace(temporary, path)
        return path.read_text().strip().encode()

    def sign(self, payload: dict) -> str:
        body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
        mac = hmac.new(self.secret(), body.encode(), hashlib.sha256).hexdigest()[:40]
        return f"{body}.{mac}"

    def verify(self, token: str, kind: str) -> dict | None:
        """The payload of a token this hub signed, if the signature, kind and expiry hold."""
        body, _, mac = (token or "").partition(".")
        if not body or not hmac.compare_digest(hmac.new(self.secret(), body.encode(), hashlib.sha256).hexdigest()[:40], mac):
            return None
        try:
            payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        except ValueError:
            return None
        if payload.get("kind") != kind or float(payload.get("exp", 0)) < time.time():
            return None
        return payload

    def token(self, kind: str, seconds: float, **fields) -> str:
        return self.sign({"kind": kind, "exp": time.time() + seconds, **fields})

    def use_code(self, nonce: str) -> bool:
        """A one-time code is accepted once (remembered in memory for its lifetime)."""
        now = time.time()
        with _lock:
            self.used_codes = {key: until for key, until in self.used_codes.items() if until > now}
            if nonce in self.used_codes:
                return False
            self.used_codes[nonce] = now + CODE_SECONDS + 5
            return True

    # ---- users ----
    def users(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def save(self, users: dict) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(users, indent=1, sort_keys=True))
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)

    def seen(self, orcid: str, name: str) -> dict:
        """Record a sign-in: a new iD becomes pending; the name is kept up to date."""
        with _lock:
            users = self.users()
            user = users.setdefault(orcid, {"status": "pending", "roles": {}, "requested_at": _now()})
            user["name"] = name or user.get("name", "")
            user["last_seen"] = _now()
            self.save(users)
            return user

    def approve(self, orcid: str, role: str = "commenter", project: str = "*", by: str = "") -> dict:
        if not ORCID_ID.match(orcid):
            raise SystemExit(f"{orcid!r} is not an ORCID iD (0000-0000-0000-000X)")
        if role not in ROLES:
            raise SystemExit(f"role must be one of {', '.join(ROLES)}")
        with _lock:
            users = self.users()
            user = users.setdefault(orcid, {"name": "", "roles": {}, "requested_at": _now()})
            user["status"] = "approved"
            user["roles"][project] = role
            user["approved_at"], user["approved_by"] = _now(), by
            self.save(users)
            return user

    def block(self, orcid: str) -> None:
        with _lock:
            users = self.users()
            if orcid not in users:
                raise SystemExit(f"no user {orcid}")
            users[orcid]["status"] = "blocked"
            self.save(users)

    def role(self, orcid: str, project: str) -> str:
        """The user's role in a project ('' when not approved or blocked)."""
        user = self.users().get(orcid) or {}
        if user.get("status") != "approved":
            return ""
        roles = user.get("roles") or {}
        return roles.get(project) or roles.get("*") or ""

    def account(self, cookie: str, project: str) -> dict | None:
        """The signed-in reader of a project site from its session cookie: {orcid, name, role} or None."""
        payload = self.verify(cookie, "site")
        if not payload or payload.get("project") != project:
            return None
        role = self.role(str(payload.get("orcid")), project)
        if rank(role) < rank("reader"):
            return None
        name = (self.users().get(payload["orcid"]) or {}).get("name") or payload["orcid"]
        return {"orcid": payload["orcid"], "name": name, "role": role}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
