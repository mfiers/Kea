"""Check the RRIDs of resource pages against the SciCrunch resolver (`kea rrid`).

A Research Resource Identifier (RRID, e.g. RRID:SCR_008633 for NumPy) names a tool, database or other research
resource in a way journals ask for. Resource pages carry it as ``rrid:``. RRIDs are found by searching
https://scicrunch.org/resources (by hand or by an agent); this command only checks that each one resolves and
prints the name SciCrunch gives it, so a wrong or mistyped RRID is caught before it reaches a paper.

Usage: kea rrid
Input: doc/**/resource/*.md (rrid:). Network: scicrunch.org (resolver).
Output: one line per resource with an RRID: ok and the registered name, or not found. Exit 1 when any is not
found. Nothing is written.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

from kea.docsite.nodes import load_tree

RESOLVER = "https://scicrunch.org/resolver/{rrid}.json"


def resolve(rrid: str) -> str | None:
    """The registered name of an RRID, or None when SciCrunch does not know it."""
    try:
        with urllib.request.urlopen(RESOLVER.format(rrid=rrid), timeout=30) as response:
            hits = json.load(response).get("hits", {}).get("hits", [])
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    return str(hits[0]["_source"]["item"].get("name", "")) if hits else None


def main(argv: list[str] | None = None) -> int:
    tree = load_tree()
    failed = 0
    for node in sorted((node for node in tree.nodes.values() if node.type == "resource"), key=lambda node: node.key):
        rrid = str(node.header.get("rrid") or "").strip()
        if not rrid:
            continue
        try:
            name = resolve(rrid)
        except OSError as error:
            print(f"SciCrunch not reachable ({error})", file=sys.stderr)
            return 2
        if name is None:
            failed += 1
            print(f"NOT FOUND  {node.number or node.id}  {rrid}  ({node.title})")
        else:
            print(f"ok         {node.number or node.id}  {rrid}  = {name}  ({node.title})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
