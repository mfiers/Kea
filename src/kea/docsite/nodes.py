"""Load the documentation tree (doc/<project>/<type>/<id>.md), number it and validate it against doc/_schema.yaml.

Every node is one Markdown file with YAML front matter. A node's key is ``<project>:<id>``; the key is also the
comment-thread key on the site, so threads survive moving a page between folders. Pages under ``doc/_changes/``
are run entries (see :mod:`docsite.changes`), not nodes.

Input: doc/ (Markdown with front matter), doc/_schema.yaml.
Output: a :class:`Tree` (nodes, numbering, reverse edges, problems found); nothing is written.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from kea.config import PROJECT_ROOT  # noqa: E402  (re-exported)
DOC = PROJECT_ROOT / "doc"
LINK_PATTERN = re.compile(r"\[\[([^\[\]|]+)(?:\|([^\[\]|]*))?(?:\|([^\[\]]*))?\]\]")
TYPE_LABELS = {"goal": "Goal", "premise": "Premise", "question": "Question", "hypothesis": "Hypothesis",
               "step": "Step", "result": "Result", "conclusion": "Conclusion", "decision": "Decision",
               "figure": "Figure", "artefact": "Artefact", "caveat": "Caveat", "term": "Term",
               "reference": "Reference", "resource": "Resource", "dataset": "Dataset", "page": "Page"}
TYPE_PLURALS = {"goal": "Goals", "premise": "Premises", "question": "Questions", "hypothesis": "Hypotheses",
                "step": "Steps", "result": "Results", "conclusion": "Conclusions", "decision": "Decisions",
                "figure": "Figures", "artefact": "Artefacts", "caveat": "Caveats", "term": "Terms",
                "reference": "References", "resource": "Resources", "dataset": "Datasets", "page": "Pages"}
# reverse names of relations, shown on the target page
REVERSE_LABELS = {"answers": "Answered by", "tests": "Tested by", "supports": "Supported by",
                  "opposes": "Opposed by", "supported_by": "Supports", "opposed_by": "Opposes",
                  "relies_on": "Used by", "shown_in": "Shows", "made_by": "Makes", "from_artefact": "Used in",
                  "derived_from": "Used to make", "decided_in": "Applies to", "supersedes": "Superseded by",
                  "limits": "Limited by", "addressed_by": "Addresses", "cites": "Cited by", "uses": "Used in",
                  "part_of": "Contains"}
FORWARD_LABELS = {"answers": "Answers", "tests": "Tests", "supports": "Supports", "opposes": "Opposes",
                  "supported_by": "Supported by", "opposed_by": "Opposed by", "relies_on": "Builds on",
                  "shown_in": "Shown in", "made_by": "Made by", "from_artefact": "From", "derived_from": "Made from",
                  "decided_in": "Decided in", "supersedes": "Supersedes", "limits": "Limits",
                  "addressed_by": "Addressed by", "cites": "Cites", "uses": "Uses", "part_of": "Part of"}
# merge equivalent edges written from either side, so reverse lists don't duplicate
EQUIVALENT = {"supported_by": "supports", "opposed_by": "opposes"}


def split_front_matter(text: str, path: Path) -> tuple[dict, str]:
    """(header dict, body) of a Markdown file with a leading '---' YAML block."""
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: no front matter")
    end = text.find("\n---", 4)
    if end < 0:
        raise ValueError(f"{path}: front matter not closed")
    try:
        header = yaml.safe_load(_quote_plain_values(text[4:end])) or {}
    except yaml.YAMLError as error:
        raise ValueError(f"{path}: YAML error: {error}") from error
    return header, text[end + 4:].lstrip("\n")


def _quote_plain_values(header_text: str) -> str:
    """Quote unquoted title/short values that contain ': ' (plain YAML would read them as a mapping)."""
    lines = []
    for line in header_text.splitlines():
        match = re.match(r"^(title|short): (.*)$", line)
        if match and ": " in match.group(2) and not match.group(2).startswith(("'", '"')):
            line = f"{match.group(1)}: " + "'" + match.group(2).replace("'", "''") + "'"
        lines.append(line)
    return "\n".join(lines)


@dataclass
class Node:
    """One page of the tree."""
    project: str
    id: str
    type: str
    title: str
    short: str
    body: str
    source: Path
    header: dict
    parent: str | None = None
    status: str | None = None
    order: float = 100.0
    number: str = ""
    relations: dict[str, list[str]] = field(default_factory=dict)   # relation -> keys (project:id)
    incoming: dict[str, list[str]] = field(default_factory=dict)    # relation -> keys of nodes pointing here

    @property
    def key(self) -> str:
        return f"{self.project}:{self.id}"

    @property
    def url(self) -> str:
        """Page path relative to the site root."""
        return f"{self.project}/{self.id}.html"

    @property
    def label(self) -> str:
        """Short label used in links: the number (P1, C2) or, without one, the title."""
        return self.number or self.title


@dataclass
class Tree:
    nodes: dict[str, Node]
    projects: dict[str, Node]          # project -> its home goal
    schema: dict
    problems: list[str] = field(default_factory=list)   # errors: broken links, schema violations
    notes: list[str] = field(default_factory=list)      # warnings: links to projects without pages yet

    def resolve(self, target: str, project: str) -> Node | None:
        """A node from a link target 'id' (same project) or 'project:id'."""
        key = target if ":" in target else f"{project}:{target}"
        if key in self.nodes or ":" in target:
            return self.nodes.get(key)
        matches = [node for node in self.nodes.values() if node.id == target]   # Obsidian style: a bare id
        return matches[0] if len(matches) == 1 else None                        # elsewhere, if unique on the site

    def children(self, node: Node) -> list[Node]:
        return sorted((child for child in self.nodes.values()
                       if child.project == node.project and child.parent == node.id),
                      key=lambda child: (child.order, child.number, child.id))


RRID_PATTERN = re.compile(r"RRID:[A-Za-z]+_[A-Za-z0-9_:.-]+")
RESOURCE_FIELDS = ("kind", "version", "retrieved")     # what makes a resource reproducible (sha256 for files)


def with_defaults(schema: dict) -> dict:
    """The project's schema plus what Kea's template has and the project's copy lacks (numbering prefixes,
    statuses and relations of kinds added in later Kea versions, e.g. resource O, term T). The project's own
    entries always win."""
    from kea.config import PACKAGE_DIR
    template = yaml.safe_load((PACKAGE_DIR / "templates" / "_schema.yaml").read_text()) or {}
    merged = dict(schema)
    for section in ("number_prefix", "status_values", "relations"):
        own = dict(schema.get(section) or {})
        used = set(own.values()) if section == "number_prefix" else set()
        for key, value in (template.get(section) or {}).items():
            if key not in own and not (section == "number_prefix" and value in used):
                own[key] = value
        merged[section] = own
    return merged


def _as_key(value: str, project: str) -> str:
    return value if ":" in value else f"{project}:{value}"


def load_tree(doc: Path = DOC) -> Tree:
    """Read every node of every project, number them, add reverse edges, and validate."""
    schema = with_defaults(yaml.safe_load((doc / "_schema.yaml").read_text()) or {})
    nodes: dict[str, Node] = {}
    problems: list[str] = []
    project_dirs = [path for path in doc.iterdir() if path.is_dir() and not path.name.startswith("_")
                    and (path / "goal" / "home.md").exists()]   # other folders in doc/ are plain documents
    for project_dir in sorted(project_dirs):
        for source in sorted(project_dir.rglob("*.md")):
            if source.name.startswith("_"):
                continue
            try:
                header, body = split_front_matter(source.read_text(encoding="utf-8"), source)
            except ValueError as error:
                problems.append(str(error))
                continue
            missing = [name for name in ("id", "type", "title", "short") if not header.get(name)]
            if missing:
                problems.append(f"{source.relative_to(doc)}: missing {', '.join(missing)}")
                continue
            relations = {name: [_as_key(str(item), project_dir.name) for item in (values or [])]
                         for name, values in (header.get("relations") or {}).items()}
            node = Node(project=project_dir.name, id=str(header["id"]), type=str(header["type"]),
                        title=str(header["title"]), short=str(header["short"]), body=body, source=source,
                        header=header, parent=header.get("parent"), status=header.get("status"),
                        order=float(header.get("order", 100)), relations=relations)
            if node.key in nodes:
                problems.append(f"{source.relative_to(doc)}: duplicate id {node.key}")
                continue
            nodes[node.key] = node
    projects = {node.project: node for node in nodes.values() if node.id == "home"}
    tree = Tree(nodes=nodes, projects=projects, schema=schema, problems=problems)
    _number(tree)
    _validate(tree)
    _reverse_edges(tree)
    return tree


def _number(tree: Tree) -> None:
    """P1, Q1, … per project and type, in reading order of the tree (depth first from the home page, children
    by `order` then id); nodes outside the tree come last."""
    prefixes = tree.schema.get("number_prefix", {})
    for project, home in tree.projects.items():
        reading_order: list[Node] = []
        stack = [home]
        seen: set[str] = set()
        while stack:
            node = stack.pop()
            if node.key in seen:
                continue
            seen.add(node.key)
            reading_order.append(node)
            stack.extend(reversed(tree.children(node)))
        reading_order += sorted((node for node in tree.nodes.values()
                                 if node.project == project and node.key not in seen), key=lambda node: node.id)
        terms = [node for node in reading_order if node.type == "term"]     # terms: in glossary order instead
        reading_order = [node for node in reading_order if node.type != "term"] + sorted(terms, key=glossary_order)
        counters: dict[str, int] = {}
        for node in reading_order:
            prefix = prefixes.get(node.type)
            if prefix:
                counters[node.type] = counters.get(node.type, 0) + 1
                node.number = f"{prefix}{counters[node.type]}"


GENE_SYMBOL = re.compile(r"[A-Z][A-Z0-9]*\d[A-Z0-9-]*|[A-Z][a-z0-9]*\d[a-z0-9]*")   # S100A8, CD74, Trem2


def natural(value: str) -> list:
    """Sort key that orders numbers by value: S100A2 before S100A10."""
    return [(0, int(part), "") if part.isdigit() else (1, 0, part.lower()) for part in re.split(r"(\d+)", str(value))]


def term_group(term: Node) -> str:
    """The group a term is listed in: front matter `group:` (e.g. Genes, Proteins, Cell types), else 'Genes' for
    a title that looks like a gene symbol (letters with a digit, no spaces), else '' (key terms)."""
    group = str(term.header.get("group") or "").strip()
    if group:
        return group
    return "Genes" if len(term.title) <= 12 and GENE_SYMBOL.fullmatch(term.title) else ""


def glossary_order(term: Node) -> tuple:
    """Key terms first, then each group by name; within them by title, numbers by value (T1, T2 … follow it)."""
    group = term_group(term)
    return (group != "", group.lower(), natural(term.title))


def _allowed(rule: dict, source_type: str, target_type: str) -> bool:
    return ("any" in rule["from"] or source_type in rule["from"]) and ("any" in rule["to"] or target_type in rule["to"])


def _validate(tree: Tree) -> None:
    schema_relations = tree.schema.get("relations", {})
    statuses = tree.schema.get("status_values", {})
    for node in tree.nodes.values():
        where = node.source.relative_to(DOC) if node.source.is_relative_to(DOC) else node.source
        if node.type not in TYPE_LABELS:
            tree.problems.append(f"{where}: unknown type {node.type!r}")
        if node.id != "home" and node.parent and f"{node.project}:{node.parent}" not in tree.nodes:
            tree.problems.append(f"{where}: parent {node.parent!r} does not exist")
        if node.id != "home" and not node.parent:
            tree.problems.append(f"{where}: no parent")
        if node.type in statuses and node.status not in statuses[node.type]:
            tree.problems.append(f"{where}: status {node.status!r} not in {statuses[node.type]}")
        if node.type == "hypothesis" and "fixed_before_results" not in node.header:
            tree.problems.append(f"{where}: hypothesis without fixed_before_results")
        internal = re.findall(r"\b[PQHSRCDFAWTO]\d{1,2}\b", node.short)
        if internal:
            tree.notes.append(f"{where}: summary line uses internal labels {', '.join(sorted(set(internal)))} "
                              "(write it for the reader)")
        spelled = sorted({match.group(0) for match in KIND_WITH_DIGIT.finditer(_without_code(node.body + " " + node.short))})
        if spelled:
            tree.notes.append(f"{where}: names pages as {', '.join(repr(item) for item in spelled[:3])}; link them "
                              "instead ([[c-x]] shows the tag, e.g. 'Conclusion C2'), so the kind and number match "
                              "the site")
        if len(node.short.split()) > 45:
            tree.notes.append(f"{where}: summary line has {len(node.short.split())} words (aim for at most ~40)")
        if node.type == "caveat" and not node.relations.get("limits"):
            tree.problems.append(f"{where}: caveat without limits (say what it limits)")
        if node.type == "resource":
            missing = [name for name in RESOURCE_FIELDS if not node.header.get(name)]
            if node.header.get("kind") in ("file", "dataset") and not node.header.get("sha256"):
                missing.append("sha256")
            if missing:
                tree.notes.append(f"{where}: resource without {', '.join(missing)} (needed to reproduce the analysis)")
            rrid = str(node.header.get("rrid") or "")
            if rrid and not RRID_PATTERN.fullmatch(rrid):
                tree.problems.append(f"{where}: rrid {rrid!r} is not of the form RRID:SCR_0000000")
            if not rrid and node.header.get("kind") in ("software", "database"):
                tree.notes.append(f"{where}: no rrid (look it up on scicrunch.org/resources; `kea rrid` checks it)")
        if node.type == "artefact" and not node.header.get("path"):
            tree.problems.append(f"{where}: artefact without path")
        for relation, targets in node.relations.items():
            rule = schema_relations.get(relation)
            if rule is None:
                tree.problems.append(f"{where}: unknown relation {relation!r}")
                continue
            for target in targets:
                target_node = tree.nodes.get(target)
                if target_node is None:
                    _missing(tree, where, target)
                elif not _allowed(rule, node.type, target_node.type):
                    tree.problems.append(f"{where}: {relation} from {node.type} to {target_node.type} not allowed")
        for match in LINK_PATTERN.finditer(node.body):
            target = match.group(1).strip()
            if target.startswith(("code:", "data:")):
                continue
            if tree.resolve(target, node.project) is None:
                _missing(tree, where, target if ":" in target else f"{node.project}:{target}")
    for project, home in tree.projects.items():
        if home.type != "goal":
            tree.problems.append(f"{project}/home: must be a goal")


KIND_WITH_DIGIT = re.compile(r"\b(?:[Pp]remise|[Qq]uestion|[Hh]ypothesis|[Ss]tep|[Rr]esult|[Cc]onclusion|[Dd]ecision|"
                             r"[Cc]aveat)s? \d{1,2}\b(?! ?(?:%|cells|donors|days|genes|times))")


def _without_code(text: str) -> str:
    return re.sub(r"```.*?```|`[^`\n]*`", " ", text, flags=re.S)


def _missing(tree: Tree, where, target: str) -> None:
    project = target.split(":", 1)[0]
    if project not in tree.projects:
        tree.notes.append(f"{where}: link to {target}: project {project!r} has no pages yet")
    else:
        tree.problems.append(f"{where}: link to unknown page {target}")


def _reverse_edges(tree: Tree) -> None:
    for node in tree.nodes.values():
        for relation, targets in node.relations.items():
            for target in targets:
                target_node = tree.nodes.get(target)
                if target_node is None:
                    continue
                if relation in EQUIVALENT:      # 'C supported_by R' is shown on R as 'Supports C'
                    reverse = REVERSE_LABELS[relation]
                else:
                    reverse = REVERSE_LABELS.get(relation, relation)
                bucket = target_node.incoming.setdefault(reverse, [])
                if node.key not in bucket:
                    bucket.append(node.key)
    # merge: if R lists "supports: [C]" and C lists "supported_by: [R]", show each edge once per side
    for node in tree.nodes.values():
        for relation, targets in list(node.relations.items()):
            forward = FORWARD_LABELS.get(relation, relation)
            for target in targets:
                if target in node.incoming.get(forward, []):
                    node.incoming[forward].remove(target)
        node.incoming = {name: keys for name, keys in node.incoming.items() if keys}
