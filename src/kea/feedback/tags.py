"""Tags that readers put on a text fragment or a whole page, next to (or instead of) a comment.

A tag is stored on a comment thread (store.py: ``tags`` on the create event, a ``tags`` event to change them), so it
uses the comments' anchoring, storage, hub sync and history. Groups: suggestions for the next run (review), the
reader's verdict on a whole page (verdict: confirm, reject; ``scope: page``, never on selected text; both are definitive requests that go into the
next plan, and a confirmation ends up as ``confirmed:`` in the page's front matter), and the
manuscript sections (manuscript). There are two kinds:

    task tags     ask the agent for work in the next review cycle (explain, expand, shorten, delete, challenge,
                  source; and the page verdicts confirm, unconfirm, reject); a thread with one is handled like an open comment, and
                  ``kea show`` prints the tag's instruction for the agent.
    mark tags     label text for later use and ask for no work (the manuscript sections:
                  introduction, methods, …);
                  a thread whose tags are all mark tags gets the status ``marked``: it is not open, not in a plan
                  and not counted as a comment waiting for an answer. ``kea tags`` lists marks for the manuscript.

The vocabulary is DEFAULT_TAGS plus ``tags:`` in kea.yaml (same fields; a known name replaces the default), and
``free_tags: false`` in kea.yaml turns off tags outside the vocabulary (on by default; a free tag is a task tag
without an instruction). ``kea build`` writes the vocabulary to ``_feedback/tags.json`` in the site, so the
browser and the server (also on a hub, which has no kea.yaml of the project) use the project's own list.

Input: kea.yaml settings, or a site's tags.json. Output: :func:`vocabulary`, :func:`check`, :func:`is_mark`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
MAX_TAGS = 12

GROUPS = {"review": "Suggestions for the next run", "verdict": "Your verdict on this page",
          "propose": "Propose the next step of the reasoning", "manuscript": "For the manuscript", "own": "Own tags"}


def _propose(name: str, types: list[str], label: str, help_text: str, instruction: str) -> dict:
    """A proposal: the reader writes the next step of the reasoning (a question on an experiment, a hypothesis or
    a step on a question, …), on the whole page or on selected text. The text is required; ``types`` are the page
    types whose menu offers it."""
    return {"name": name, "group": "propose", "task": True, "types": types, "label": label, "help": help_text,
            "needs_text": True,
            "instruction": "A reader proposes " + instruction + " Take it into the next plan: write it as its own "
                           "page with the right relations (or merge it into an existing page, or say why not), keep "
                           "the reader's wording where it holds, and name the reader in the reply."}


# What a reader may propose on each page type: the next step along Kea's reasoning route
# (experiment → question → hypothesis → step → result → conclusion, with premises, caveats and decisions).
PROPOSALS: list[dict] = [
    _propose("propose-question", ["experiment", "conclusion"], "a question",
             "A question this experiment should ask (or one this conclusion raises)",
             "a question (page type question, under the experiment; from a conclusion, link the conclusion in the text)."),
    _propose("propose-premise", ["experiment", "question"], "a premise",
             "Something the analysis takes as given and that a reader should be able to question",
             "a premise: something taken as given (type premise, status assumed; link the pages that rely on it)."),
    _propose("question-premise", ["premise"], "why it may not hold",
             "Why this premise may not hold, and what would show it",
             "a reason this premise may not hold. Set its status to questioned while you check it; then support it "
             "(supported_by), revise it (every page relying on it gets rechecked) or keep it with the reasons."),
    _propose("propose-hypothesis", ["question"], "a hypothesis",
             "What you expect, and what result would count for or against it",
             "a hypothesis (type hypothesis under this question, with prediction: and criterion:, and "
             "fixed_before_results: true when no result is in yet)."),
    _propose("propose-step", ["question", "hypothesis", "caveat"], "a step",
             "An analysis that would answer the question, test the hypothesis or address the caveat",
             "an analysis step (type step, status planned; tests: the hypothesis, or addressed_by: on the caveat)."),
    _propose("alternative-hypothesis", ["hypothesis"], "a competing hypothesis",
             "Another explanation that predicts something different",
             "a competing hypothesis (its own hypothesis page under the same question, with what it predicts "
             "differently, so one test can tell them apart)."),
    _propose("propose-control", ["step", "result"], "a control or check",
             "A negative control, permutation, robustness check or replication",
             "a control or check of this analysis (a planned step whose result supports or opposes this one)."),
    _propose("propose-change", ["step", "figure"], "a different method",
             "Another method, parameter or presentation, and why",
             "a change of method, parameter or presentation, with the reason. Record the choice as a decision page "
             "when it changes results; results made with the old choice get rechecked."),
    _propose("propose-conclusion", ["result"], "a conclusion",
             "What this result means, no stronger than the design allows",
             "a conclusion from this result (type conclusion, supported_by this result with because:, certainty:)."),
    _propose("propose-caveat", ["result", "conclusion", "premise", "step"], "a caveat",
             "A limit: a confounder, a bias, a small sample, a measurement that may not mean what it seems",
             "a caveat (type caveat with kind: and limits: this page)."),
    _propose("alternative-explanation", ["result", "conclusion"], "another explanation",
             "Another explanation of the same finding",
             "another explanation of this finding: write it as a caveat (kind: internal or construct) or as a "
             "competing hypothesis with a step that would tell them apart."),
    _propose("propose-certainty", ["conclusion"], "a certainty",
             "How certain this conclusion is in your view (high, moderate, low, very low), and why",
             "a certainty for this conclusion: weigh it against the evidence and caveats; change certainty: and "
             "certainty_because: or say why not."),
    _propose("propose-option", ["decision"], "another option",
             "An option this decision did not consider, with its trade-off",
             "another option for this decision, with its trade-off: add it to the decision page and say whether it "
             "changes the choice (a changed choice gets every page made with it rechecked)."),
]

DEFAULT_TAGS: list[dict] = [
    {"name": "explain", "group": "review", "task": True, "label": "explain",
     "help": "Unclear: explain it",
     "instruction": "Explain this for a reader who knows the field but not this project: define terms, say why "
                    "it matters, add an example or a figure reference."},
    {"name": "expand", "group": "review", "task": True, "label": "expand",
     "help": "Say more about this",
     "instruction": "Write more about this: the reasoning, the evidence, the alternatives. Keep every number "
                    "tied to its source."},
    {"name": "shorten", "group": "review", "task": True, "label": "shorten",
     "help": "Too long: say it in fewer words",
     "instruction": "Say the same in fewer words; keep every claim, number and caveat."},
    {"name": "delete", "group": "review", "task": True, "label": "delete",
     "help": "Delete this text",
     "instruction": "Delete this text. When it carries a claim that other pages rely on, say so in the reply "
                    "instead of deleting it."},
    {"name": "challenge", "group": "review", "task": True, "label": "challenge",
     "help": "Doubt this: have it critically re-assessed",
     "instruction": "Re-assess this claim adversarially before the next release: start a separate reviewer (a "
                    "subagent that sees the page, its sources and its caveats, not your reasoning) and ask it "
                    "whether the claim follows from the evidence, what is missing and what would refute it. Answer "
                    "the reviewer point by point; then strengthen, weaken or withdraw the claim, add a caveat, or "
                    "keep it with the reasons. Summarise the exchange in the reply."},
    {"name": "source", "group": "review", "task": True, "label": "needs source",
     "help": "Which file, result or reference supports this?",
     "instruction": "Find the source of this statement: a file in `sources:`, a result page, or a reference. Add "
                    "it, or weaken or remove the statement when there is none."},
    {"name": "confirm", "group": "verdict", "task": True, "scope": "page", "label": "confirm",
     "help": "Keep this page as it is: it goes into the next plan, and the page records your confirmation",
     "instruction": "The reader confirms this page. In the next plan, write `confirmed:` into its front matter "
                    "(`by:` the reader's name, `orcid:` their ORCID iD when the thread has one, `date:` the thread's date, "
                    "`version:` the page's version id from its About line, else the thread's page commit) and change "
                    "nothing else. From then on, change the page's claim (title, summary, status, numbers) only "
                    "through a plan item that names the confirmation. On a page that waits for approval (a proposed "
                    "question, a planned step, a new result; pace in the skill), apply it at the harvest itself: "
                    "also write `approved:` (by, orcid, date, how: site), so the next step can start."},
    {"name": "unconfirm", "group": "verdict", "task": True, "scope": "page", "label": "withdraw confirmation",
     "hidden": True, "help": "Withdraw an earlier confirmation",
     "instruction": "The reader withdraws the confirmation of this page: remove `confirmed:` from its front matter "
                    "in the next plan."},
    {"name": "approve", "group": "verdict", "task": True, "scope": "page", "label": "approve",
     "help": "Go ahead: the next step may build on this page",
     "instruction": "The reader approves this page (pace: guided): the next step may build on it. Apply it at the "
                    "harvest itself, not at Implement: write `approved:` into its front matter (`by:` the reader's "
                    "name, `orcid:` their ORCID iD when the thread has one, `date:` the thread's date, `how: site`) "
                    "and change nothing else. Then the next step is open; do it only when the owner asks."},
    {"name": "revise", "group": "verdict", "task": True, "scope": "page", "label": "revise", "needs_text": True,
     "help": "Rewrite this page (say what to change): this branch is reworked",
     "instruction": "The reader asks to revise this page; their text says what to change. A page that waits for "
                    "approval: rewrite it at the harvest itself; it waits for approval again. A settled page: make it "
                    "a plan item and rewrite it at Implement; remove `approved:` and `confirmed:` (the claim "
                    "changed; under pace: guided it waits for approval again). Every page downstream then gets a "
                    "recheck mark: work through kea recheck --list. Say in the reply what changed."},
    {"name": "drop", "group": "verdict", "task": True, "scope": "page", "label": "drop",
     "help": "Remove this page, and the pages that rest only on it",
     "instruction": "The reader drops this page and every page that rests only on it: `kea drop <id>` lists them. "
                    "A page that waits for approval: drop at the harvest itself; a settled page: a plan item, done at "
                    "Implement. Keep the record: a question gets status dropped, a step dropped, a result, "
                    "conclusion or figure deprecated (with the reason in the text), a decision superseded; delete "
                    "the other pages. Remove or update the links to them; pages that rested partly on them get a "
                    "recheck mark: recheck them. Say in the reply what was dropped."},
    {"name": "reject", "group": "verdict", "task": True, "scope": "page", "label": "reject", "hidden": True,
     "help": "This page should go (before Kea 1.19; now Drop)",
     "instruction": "The reader rejects this page; it goes in the next plan. Results, conclusions and figures are "
                    "not deleted: set their status to deprecated with the reason; other pages are deleted. Update "
                    "or remove the relations that point to it, and say in the reply what depended on it."},
    {"name": "introduction", "group": "manuscript", "task": False, "label": "introduction", "help": ""},
    {"name": "methods", "group": "manuscript", "task": False, "label": "methods", "help": ""},
    {"name": "results", "group": "manuscript", "task": False, "label": "results", "help": ""},
    {"name": "discussion", "group": "manuscript", "task": False, "label": "discussion", "help": ""},
    {"name": "conclusions", "group": "manuscript", "task": False, "label": "conclusions", "help": ""},
    {"name": "supplement", "group": "manuscript", "task": False, "label": "supplement",
     "help": "In the supplementary material"},
    {"name": "not-in-manuscript", "group": "manuscript", "task": False, "label": "not in manuscript",
     "help": "Keep this out of the manuscript"},
] + PROPOSALS


class TagError(ValueError):
    pass


def vocabulary(settings: dict | None = None) -> dict:
    """{"tags": [...], "free_tags": bool, "groups": {...}} from the defaults and kea.yaml."""
    if settings is None:
        from kea.config import SETTINGS as settings
    tags = {tag["name"]: dict(tag) for tag in DEFAULT_TAGS}
    for extra in settings.get("tags") or []:
        if not isinstance(extra, dict) or not NAME.match(str(extra.get("name", ""))):
            raise TagError(f"kea.yaml tags: each entry needs a name of lower-case letters, digits and '-' ({extra!r})")
        merged = {"group": "review", "task": True, "scope": "any", "label": extra["name"], "help": "", "instruction": "",
                  **tags.get(extra["name"], {}), **extra}
        merged["task"] = bool(merged["task"])
        tags[extra["name"]] = merged
    return {"tags": list(tags.values()), "free_tags": bool(settings.get("free_tags", True)), "groups": GROUPS}


def site_vocabulary(site_dir: Path) -> dict:
    """The vocabulary the site was built with (_feedback/tags.json), else the defaults."""
    try:
        data = json.loads((site_dir / "_feedback" / "tags.json").read_text())
        if isinstance(data, dict) and isinstance(data.get("tags"), list):
            return data
    except (OSError, ValueError):
        pass
    return vocabulary({})


def clean(names) -> list[str]:
    """Validate the form of a tag list (no vocabulary check); duplicates dropped, order kept."""
    if names is None or names == "":
        return []
    if not isinstance(names, list):
        raise TagError("tags must be a list")
    result: list[str] = []
    for name in names:
        name = str(name).strip().lower()
        if not NAME.match(name):
            raise TagError(f"tag {name!r}: use lower-case letters, digits and '-' (at most 32)")
        if name not in result:
            result.append(name)
    if len(result) > MAX_TAGS:
        raise TagError(f"at most {MAX_TAGS} tags")
    return result


def check(names, known: dict, on_text: bool = False) -> list[str]:
    """clean() plus: tags outside the vocabulary only when free tags are on; page tags (scope: page, the verdicts)
    not on a text fragment."""
    result = clean(names)
    names_known = {tag["name"]: tag for tag in known["tags"]}
    unknown = [name for name in result if name not in names_known]
    if unknown and not known.get("free_tags", True):
        raise TagError(f"unknown tag(s): {', '.join(unknown)}")
    page_only = [name for name in result if names_known.get(name, {}).get("scope") == "page"]
    if on_text and page_only:
        raise TagError(f"{', '.join(page_only)}: only for a whole page, not for selected text")
    return result


def is_mark(names: list[str], known: dict | None = None) -> bool:
    """True when there are tags and none asks for work (all are mark tags)."""
    if not names:
        return False
    known = known or vocabulary()
    marks = {tag["name"] for tag in known["tags"] if not tag.get("task", True)}
    return all(name in marks for name in names)


def describe(name: str, known: dict | None = None) -> dict:
    known = known or vocabulary()
    for tag in known["tags"]:
        if tag["name"] == name:
            return tag
    return {"name": name, "group": "own", "task": True, "label": name, "help": "",
            "instruction": "A reader's own tag: read it with the text and the comment; ask when the meaning is unclear."}
