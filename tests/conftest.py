"""Keep the test suite away from any real Kea hub and from this repository's own site settings.

Kea's repository is itself a Kea project (kea.yaml at the root: the development site on a hub). The tests use the
repository as their project folder, so without this they would read that kea.yaml: its `remote:` would send
`kea watch`, `kea list` and lease calls to the live hub with the key in .env, and its tag_prefix /
changes_since would change what the docsite tests see. Every test runs with the hub settings removed and the
site settings at their defaults; tests of the hub (test_hub.py) set up their own.
"""
from __future__ import annotations

import pytest

from kea import config

NEUTRAL_SETTINGS = {"remote": None, "tag_prefix": "", "changes_since": ""}


@pytest.fixture(autouse=True)
def no_hub_and_default_site_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in NEUTRAL_SETTINGS.items():
        monkeypatch.setitem(config.SETTINGS, key, value)
    monkeypatch.delenv("KEA_REMOTE_KEY", raising=False)
    try:
        from kea.feedback import backend
    except ImportError:
        return
    monkeypatch.setattr(backend, "remote_settings", lambda: {})
