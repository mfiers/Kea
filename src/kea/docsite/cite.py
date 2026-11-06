"""Full citations for reference pages, Nature style, from Europe PMC (`kea cite`).

The PDF lists references as a journal does (numbered B1, B2 … in order of first citation). Its text comes from
the front matter field ``citation:``. This command fills that field from Europe PMC, looked up by the page's
``pmid:`` or ``doi:``, so no citation is written from memory:

    Afanador, L. et al. The Ca2+ sensor S100A1 modulates neuroinflammation, histopathology and Akt activity in the
    PSAPP Alzheimer's disease mouse model. *Cell Calcium* **56**, 68–80 (2014).

Up to five authors are named; more become "First, A. et al.". Preprints get the server's name ("bioRxiv").

Usage: kea cite [--write] [--all] [ID …]
    without --write: print what would be written; --write: insert ``citation:`` after the ``title:`` line of each
    page that has none (--all: replace existing ones too). IDs limit the run to those reference pages.
Input: doc/**/reference/*.md (pmid:, doi:). Network: www.ebi.ac.uk (Europe PMC REST API).
Output: the same files, one front-matter line added or replaced (nothing else in them changes).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from kea.docsite.nodes import DOC, load_tree

API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
MAX_AUTHORS = 5


def fetch(pmid: str = "", doi: str = "") -> dict | None:
    """The Europe PMC core record for a PubMed id or a DOI (None when not found)."""
    if pmid:
        query = f"EXT_ID:{pmid} AND SRC:MED"
    elif doi:
        query = f'DOI:"{doi}"'
    else:
        return None
    url = f"{API}?{urllib.parse.urlencode({'query': query, 'resultType': 'core', 'format': 'json', 'pageSize': 1})}"
    with urllib.request.urlopen(url, timeout=30) as response:
        results = json.load(response).get("resultList", {}).get("result", [])
    return results[0] if results else None


def author_name(author: dict) -> str:
    """'Surname, A. B.' (or a group's name)."""
    if author.get("collectiveName"):
        return str(author["collectiveName"])
    initials = " ".join(f"{letter}." for letter in str(author.get("initials", "")).replace(".", "").replace(" ", ""))
    return f"{author.get('lastName', '').strip()}, {initials}".strip(", ")


def nature(record: dict) -> str:
    """A Nature-style reference in Markdown: authors, title, *journal* **volume**, pages (year)."""
    authors = [author_name(author) for author in (record.get("authorList") or {}).get("author", [])]
    if len(authors) > MAX_AUTHORS:
        names = f"{authors[0]} et al."
    elif len(authors) > 1:
        names = ", ".join(authors[:-1]) + " & " + authors[-1]
    else:
        names = authors[0] if authors else ""
    title = re.sub(r"<[^>]+>", "", str(record.get("title", ""))).strip().rstrip(".")
    journal_info = record.get("journalInfo") or {}
    journal = (journal_info.get("journal") or {})
    journal_name = journal.get("isoabbreviation") or journal.get("medlineAbbreviation") or journal.get("title") or ""
    if not journal_name and record.get("source") == "PPR":
        journal_name = (record.get("bookOrReportDetails") or {}).get("publisher") or "Preprint"
    year = str(journal_info.get("yearOfPublication") or record.get("pubYear") or "")
    volume = str(journal_info.get("volume") or "")
    pages = str(record.get("pageInfo") or "").replace("-", "–")
    where = f"*{journal_name.rstrip('.')}*" if journal_name else ""
    if volume:
        where += f" **{volume}**"
    if pages:
        where += f", {pages}"
    parts = [part for part in (names, title + ".", f"{where} ({year})." if where else f"({year}).") if part]
    return " ".join(parts)


def set_citation(path: Path, citation: str, replace: bool) -> bool:
    """Insert (or replace) the ``citation:`` line in the front matter; True when the file changed."""
    text = path.read_text(encoding="utf-8")
    end = text.find("\n---", 4)
    header, rest = text[:end], text[end:]
    line = "citation: '" + citation.replace("'", "''") + "'"
    if re.search(r"^citation:", header, flags=re.M):
        if not replace:
            return False
        header = re.sub(r"^citation:.*$", lambda match: line, header, count=1, flags=re.M)
    elif re.search(r"^title:.*$", header, flags=re.M):
        header = re.sub(r"^(title:.*)$", lambda match: match.group(1) + "\n" + line, header, count=1, flags=re.M)
    else:
        header += "\n" + line
    path.write_text(header + rest, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kea cite", description=__doc__.split("\n")[0])
    parser.add_argument("ids", nargs="*", help="reference page ids (default: all)")
    parser.add_argument("--write", action="store_true", help="write citation: into the pages")
    parser.add_argument("--all", action="store_true", help="also replace existing citation: lines")
    args = parser.parse_args(argv)
    tree = load_tree()
    references = [node for node in tree.nodes.values() if node.type == "reference"
                  and (not args.ids or node.id in args.ids or node.key in args.ids)]
    missing = 0
    for node in sorted(references, key=lambda node: node.key):
        if node.header.get("citation") and not args.all:
            continue
        pmid, doi = str(node.header.get("pmid") or "").strip(), str(node.header.get("doi") or "").strip()
        try:
            record = fetch(pmid, "") if pmid else None
            record = record or fetch("", doi)
        except OSError as error:
            print(f"{node.key}: Europe PMC not reachable ({error})", file=sys.stderr)
            return 1
        if not record:
            print(f"{node.key}: not found in Europe PMC (pmid {pmid or '-'}, doi {doi or '-'}); write citation: by hand")
            missing += 1
            continue
        citation = nature(record)
        changed = set_citation(node.source, citation, args.all) if args.write else False
        where = node.source.relative_to(DOC) if node.source.is_relative_to(DOC) else node.source
        print(f"{'wrote' if changed else 'would write' if not args.write else 'kept'}  {where}: {citation}")
    return 0 if not missing else 3


if __name__ == "__main__":
    sys.exit(main())
