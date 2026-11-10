"""Release versions (semantic, from annotated git tags) and how settled each page is.

A release is an annotated git tag: ``vX.Y.Z`` for the whole site, ``<experiment>/vX.Y.Z`` for one experiment,
each preceded by ``tag_prefix`` from kea.yaml when set (e.g. ``site/v1.0.0`` in a repository whose own ``vX.Y.Z``
tags are software releases); tags without the prefix are then ignored.
The tag message carries ``Run:``, ``Cycle:``, ``Kind:`` (major / minor / patch) and ``Reason:`` lines; the tag date
is the release time. Tags are written by ``kea cycle release --version …`` (or by hand for releases
made before 2026-11-05). Rules for the bump (doc/site_design.md "Versions"): MAJOR when a conclusion changes
direction or is withdrawn, MINOR for new results or pages, PATCH for wording only; before 1.0 a major change
counts as minor.

Stability of a page: the release in which its file last changed (whitespace ignored), whether its claim (title,
short, status) changed then, and for how many releases it has been unchanged since. Changes after the latest
release ("changing now") count as in flux.

Input: git tags and the blobs of doc/ files at each tag. Output: :func:`releases`, :class:`Stability`.
"""
from __future__ import annotations

import functools
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

from kea.config import SETTINGS
from kea.docsite.nodes import PROJECT_ROOT, _quote_plain_values, safe_yaml

SEMVER = re.compile(r"^(?:(?P<experiment>[\w.-]+)/)?v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
SETTLED_AFTER = 3        # releases without change before a page counts as settled


def tag_prefix() -> str:
    return str(SETTINGS.get("tag_prefix") or "")


def tag_name(version: str, experiment: str = "") -> str:
    """The git tag of a release: [prefix][experiment/]vX.Y.Z."""
    return f"{tag_prefix()}{experiment + '/' if experiment else ''}v{version}"


@dataclass
class Release:
    tag: str
    version: str             # "0.2.0"
    experiment: str          # "" for the whole site
    commit: str              # full sha of the tagged commit
    date: str                # ISO time of the release (tag date)
    run: str = ""
    cycle: str = ""
    kind: str = ""
    reason: str = ""

    @property
    def short(self) -> str:
        return self.commit[:7]

    @property
    def label(self) -> str:
        return f"v{self.version}"

    @property
    def key(self) -> tuple[int, int, int]:
        return tuple(int(part) for part in self.version.split("."))


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=PROJECT_ROOT)
    return result.stdout if result.returncode == 0 else ""


def releases(experiment: str | None = "") -> list[Release]:
    """Releases of the site (experiment ""), of one experiment, or all (None); oldest first."""
    output = _git("for-each-ref", "refs/tags", "--format=%(refname:short)%1f%(objectname)%1f%(*objectname)%1f"
                  "%(taggerdate:iso-strict)%1f%(contents)%1e")
    found = []
    for record in output.split("\x1e"):
        fields = record.strip("\n").split("\x1f")
        if len(fields) < 5:
            continue
        tag, objectname, target, date, message = fields
        prefix = tag_prefix()
        if prefix and not tag.startswith(prefix):
            continue
        match = SEMVER.match(tag[len(prefix):])
        if not match:
            continue
        release = Release(tag=tag, version=f"{match['major']}.{match['minor']}.{match['patch']}",
                          experiment=match["experiment"] or "", commit=target or objectname, date=date)
        for field_name in ("run", "cycle", "kind", "reason"):
            line = re.search(rf"^{field_name.capitalize()}:\s*(.+)$", message, flags=re.M)
            if line:
                setattr(release, field_name, line.group(1).strip())
        if experiment is None or release.experiment == experiment:
            found.append(release)
    return sorted(found, key=lambda release: (release.experiment, release.key))


def next_versions(current: str) -> dict[str, str]:
    """The three possible next versions of a version string."""
    major, minor, patch = (int(part) for part in current.split("."))
    return {"major": f"{major + 1}.0.0", "minor": f"{major}.{minor + 1}.0", "patch": f"{major}.{minor}.{patch + 1}"}


def _normalised(text: str | None) -> str | None:
    return None if text is None else re.sub(r"\s+", " ", text).strip()


@functools.lru_cache(maxsize=65536)
def _claim(text: str | None) -> tuple | None:
    """(title, short, status) of one version of a page (cached: the same text recurs across releases)."""
    if text is None or not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    try:
        header = safe_yaml(_quote_plain_values(text[4:end])) or {}
    except yaml.YAMLError:
        return None
    return (str(header.get("title", "")), str(header.get("short", "")), str(header.get("status", "")))


@dataclass
class PageStability:
    created_in: str = ""          # first release with the file ("" = not released yet)
    changed_in: str = ""          # last release in which the file changed
    claim_changed_in: str = ""    # last release in which title / short / status changed
    stable_for: int = 0           # releases since changed_in
    changing_now: bool = False    # differs from the latest release
    claim_changing_now: bool = False

    @property
    def state(self) -> str:
        """'flux', 'steady' or 'settled'."""
        if self.changing_now or not self.created_in or self.stable_for == 0:
            return "flux"
        return "settled" if self.stable_for >= SETTLED_AFTER else "steady"

    @property
    def text(self) -> str:
        if not self.created_in:
            return "new, not released yet"
        if self.changing_now:
            what = "claim changing" if self.claim_changing_now else "changing"
            return f"{what} now (after {self.latest})"
        what = "claim changed" if self.claim_changed_in and self.claim_changed_in == self.changed_in else "changed"
        if self.changed_in == self.created_in:
            what = "new"
        if self.stable_for == 0:
            return f"{what} in {self.changed_in} (latest release)"
        return f"{what} in {self.changed_in} · unchanged for {self.stable_for} release{'s' if self.stable_for > 1 else ''}"

    latest: str = ""


class Stability:
    """Per-page stability against the site releases, read in one pass with ``git cat-file --batch``."""

    def __init__(self, site_releases: list[Release] | None = None):
        self.releases = site_releases if site_releases is not None else releases("")
        self._cache: dict[str, PageStability] = {}

    def _blobs(self, requests: list[str]) -> list[str | None]:
        if not requests:
            return []
        process = subprocess.run(["git", "cat-file", "--batch"], input=("\n".join(requests) + "\n").encode(),
                                 capture_output=True, cwd=PROJECT_ROOT)
        data, position, results = process.stdout, 0, []
        for _ in requests:
            header_end = data.index(b"\n", position)
            header = data[position:header_end].decode()
            position = header_end + 1
            if header.endswith("missing"):
                results.append(None)
                continue
            size = int(header.split()[-1])
            results.append(data[position:position + size].decode("utf-8", errors="replace"))
            position += size + 1
        return results

    def prepare(self, paths: list[Path]) -> None:
        relative = [str(path.relative_to(PROJECT_ROOT)) for path in paths]
        requests = [f"{release.commit}:{path}" for path in relative for release in self.releases]
        blobs = self._blobs(requests)
        count = len(self.releases)
        latest = self.releases[-1].label if self.releases else ""
        for index, path in enumerate(relative):
            versions = blobs[index * count:(index + 1) * count]
            result = PageStability(latest=latest)
            previous_text, previous_claim = None, None
            for release, text in zip(self.releases, versions):
                if text is None:
                    previous_text, previous_claim = None, None
                    continue
                if not result.created_in:
                    result.created_in = release.label
                if _normalised(text) != _normalised(previous_text):
                    result.changed_in = release.label
                if _claim(text) != previous_claim:
                    result.claim_changed_in = release.label
                previous_text, previous_claim = text, _claim(text)
            if result.created_in:
                labels = [release.label for release in self.releases]
                result.stable_for = len(labels) - 1 - labels.index(result.changed_in)
                current = (PROJECT_ROOT / path).read_text(encoding="utf-8") if (PROJECT_ROOT / path).exists() else None
                result.changing_now = _normalised(current) != _normalised(previous_text)
                result.claim_changing_now = _claim(current) != previous_claim
            self._cache[path] = result

    def of(self, path: Path) -> PageStability:
        relative = str(path.relative_to(PROJECT_ROOT))
        if relative not in self._cache:
            self.prepare([path])
        return self._cache[relative]


_COMMIT_LABELS: dict[str, str] | None = None


def commit_labels() -> dict[str, str]:
    """Short commit -> the site release it went into ('v0.2.0'), or 'after vX' for unreleased commits."""
    global _COMMIT_LABELS
    if _COMMIT_LABELS is None:
        labels: dict[str, str] = {}
        previous = None
        site = releases("")
        for release in site:
            spec = f"{previous}..{release.commit}" if previous else release.commit
            for full in _git("rev-list", spec).split():
                labels[full[:7]] = release.label
            previous = release.commit
        if site:
            for full in _git("rev-list", f"{previous}..HEAD").split():
                labels[full[:7]] = f"after {site[-1].label}"
        _COMMIT_LABELS = labels
    return _COMMIT_LABELS
