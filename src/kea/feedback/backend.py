"""Where the review record lives: this project's files, or a Kea hub (kea hub) that hosts the site.

Local (no `remote:` in kea.yaml): comments and cycle events are the files data/feedback/events.jsonl and
cycle.jsonl; the lease is data/feedback/agent_lease.json.

Remote (kea.yaml `remote: {url: https://hub.example.org, project: name}` and KEA_REMOTE_KEY in .env):
the hub is the authority. Readers comment on the hub; the agent
    * pulls the logs (sync): the local files become an exact mirror of the hub's (append-only, fetched as the
      bytes after the local size, checked by a hash of the local copy), so kea list / show / context work as before;
    * writes its replies, status changes and cycle events through the hub's API, then pulls again;
    * takes and renews the lease on the hub (one agent per project, across machines).
The project key is sent as a bearer token, only over https (http only to localhost, for tests).
"""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from kea.config import PROJECT_ROOT, SETTINGS
from kea.feedback import agent, cycle, store

KEY_VARIABLE = "KEA_REMOTE_KEY"


class RemoteError(Exception):
    def __init__(self, message: str, status: int = 0, detail: dict | None = None):
        super().__init__(message)
        self.status, self.detail = status, detail or {}


def remote_settings() -> dict:
    remote = SETTINGS.get("remote") or {}
    return remote if isinstance(remote, dict) and remote.get("url") and remote.get("project") else {}


def check_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")):
        return url.rstrip("/")
    raise RemoteError(f"the hub address must be https:// (got {url!r}); kea sends the project key only over https")


def remote_key() -> str:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    key = os.environ.get(KEY_VARIABLE, "").strip()
    if not key:
        raise RemoteError(f"kea.yaml names a hub but {KEY_VARIABLE} is not set in .env (the project key from "
                          "`kea hub add` on the hub)")
    return key


class Local:
    remote = False

    def __init__(self, events_path: Path | None = None, cycle_path: Path | None = None):
        self.events_path = events_path or store.default_path()
        self.cycle_path = cycle_path or cycle.default_path()

    def sync(self) -> None:
        return None

    def append_event(self, event: dict) -> dict:
        return store.append_event(event, self.events_path)

    def append_cycle(self, kind: str, by: str, **fields: str) -> cycle.CycleState:
        return cycle.append(kind, by, self.cycle_path, **fields)

    @property
    def lease_path(self) -> Path:
        return self.events_path.parent / "agent_lease.json"

    def take_lease(self, force: bool = False, watching: bool = False, extra: dict | None = None) -> dict:
        return agent.take_local(self.lease_path, force=force, watching=watching)

    def release_lease(self, force: bool = False) -> None:
        agent.release_local(self.lease_path, force=force)

    def lease(self) -> dict:
        return agent.read_local(self.lease_path)

    def heartbeat(self, extra: dict) -> None:
        agent.take_local(self.lease_path, watching=True)
        cycle.write_heartbeat(extra=extra)

    def describe(self) -> str:
        return f"local files in {self.events_path.parent}"


class Remote(Local):
    remote = True

    def __init__(self, url: str, project: str, key: str, events_path: Path | None = None,
                 cycle_path: Path | None = None, timeout: float = 30):
        super().__init__(events_path, cycle_path)
        self.url, self.project, self.key, self.timeout = check_url(url), project, key, timeout

    # ---- HTTP ----
    def endpoint(self, path: str) -> str:
        return f"{self.url}/p/{urllib.parse.quote(self.project)}/hub/{path}"

    def request(self, method: str, path: str, body: dict | bytes | None = None, headers: dict | None = None,
                query: dict | None = None, timeout: float | None = None) -> dict:
        url = self.endpoint(path) + (f"?{urllib.parse.urlencode(query)}" if query else "")
        data = body if isinstance(body, bytes) or body is None else json.dumps(body).encode()
        all_headers = {"Authorization": f"Bearer {self.key}", "X-Kea-Agent": agent.agent_id(),
                       "User-Agent": "kea-client"}
        if body is not None and not isinstance(body, bytes):
            all_headers["Content-Type"] = "application/json"
        all_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, method=method, headers=all_headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout, context=ssl.create_default_context()) as reply:
                return json.loads(reply.read() or b"{}")
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read() or b"{}")
            except ValueError:
                detail = {}
            if error.code == 409 and detail.get("holder"):
                raise agent.LeaseHeld(detail["holder"]) from None
            raise RemoteError(f"hub {method} {path}: HTTP {error.code} {detail.get('error', error.reason)}",
                              error.code, detail) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise RemoteError(f"hub {self.url} not reachable: {error}") from None

    # ---- logs ----
    @staticmethod
    def _local_state(path: Path) -> tuple[int, str]:
        data = path.read_bytes() if path.exists() else b""
        return len(data), hashlib.sha256(data).hexdigest()

    def sync(self) -> None:
        """Make the local logs an exact copy of the hub's (fetching only what is new)."""
        sizes = {name: self._local_state(path) for name, path in (("events", self.events_path),
                                                                     ("cycle", self.cycle_path))}
        reply = self.request("GET", "log", query={"events_from": sizes["events"][0], "events_sha": sizes["events"][1],
                                                  "cycle_from": sizes["cycle"][0], "cycle_sha": sizes["cycle"][1]})
        for name, path in (("events", self.events_path), ("cycle", self.cycle_path)):
            part = reply[name]
            path.parent.mkdir(parents=True, exist_ok=True)
            if part["mode"] == "same":
                continue
            if part["mode"] == "full" and sizes[name][0]:
                if part["size"] == 0:
                    raise RemoteError(f"the hub has no {name} log yet but this project has one: run `kea publish` "
                                      "(it sends the project's history first); the local log is left as it is")
                backup = path.with_name(f"{path.name}.before-sync-{time.strftime('%Y%m%d-%H%M%S')}")
                backup.write_bytes(path.read_bytes())         # the local copy differed from the hub's: keep it
            data = part["text"].encode("utf-8")
            if part["mode"] == "append":
                data = (path.read_bytes() if path.exists() else b"") + data
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_bytes(data)
            os.replace(temporary, path)

    def seed(self) -> dict:
        """Send this project's existing logs to a hub whose logs are still empty (once, at the first publish)."""
        texts = {name: path.read_text(encoding="utf-8") if path.exists() else ""
                 for name, path in (("events", self.events_path), ("cycle", self.cycle_path))}
        return self.request("POST", "seed", texts)

    def append_event(self, event: dict) -> dict:
        reply = self.request("POST", "events", {"log": "events", "event": event})
        self.sync()
        return reply["event"]

    def append_cycle(self, kind: str, by: str, **fields: str) -> cycle.CycleState:
        self.request("POST", "events", {"log": "cycle", "kind": kind, "fields": fields})
        self.sync()
        return cycle.state(self.cycle_path)

    # ---- lease ----
    def take_lease(self, force: bool = False, watching: bool = False, extra: dict | None = None) -> dict:
        body = {**agent.agent_info(), "force": force, "watching": watching, "heartbeat": extra or {}}
        try:
            return self.request("POST", "lease", body)["lease"]
        except agent.LeaseHeld as held:
            # the holder ran on this machine and its session has ended: no other agent is working, take over
            if not force and agent.holder_ended_here(held.holder):
                return self.request("POST", "lease", {**body, "force": True})["lease"]
            raise

    def release_lease(self, force: bool = False) -> None:
        self.request("POST", "lease/release", {"agent": agent.agent_id(), "force": force})

    def lease(self) -> dict:
        return self.request("GET", "lease").get("lease") or {}

    def heartbeat(self, extra: dict) -> None:
        self.take_lease(watching=True, extra=extra)

    def describe(self) -> str:
        return f"hub {self.url}/p/{self.project}/ (local mirror in {self.events_path.parent})"


def get(events_path: Path | None = None, cycle_path: Path | None = None) -> Local:
    remote = remote_settings()
    if not remote:
        return Local(events_path, cycle_path)
    return Remote(remote["url"], str(remote["project"]), remote_key(), events_path, cycle_path)
