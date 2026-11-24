"""The graph view (explore.html): every page of the site as one horizontal tree that the reader scrolls and walks
with the keyboard, zooming into a page to read, comment and sign it.

`graph(tree, hrefs)` is what kea build writes to `_graph.json` for explore.js. Each page gets one *tree parent*,
so the graph can be drawn as a tree, left to right along the route of an experiment:

    experiment | question | hypothesis | step | result | figure | conclusion

A page's column is fixed by its type (a column always means a stage). Its tree parent is the page it grows from:

- a question: its parent question, else the experiment;
- a hypothesis: its question (whereami.home_question), else the experiment;
- a step: the hypothesis it tests, else its question;
- a result: the step that made it, else the hypothesis it tests, else its question;
- a figure: the result shown in it, else the step that made it, else its question;
- a conclusion: its question (the results it rests on are drawn as edges, all of them, always);

and always a page in a column to the left (lower rank), so the tree has no cycles. When several pages qualify, the
one under the same question with the lowest number wins; the others stay as edges (drawn for the selected page).

Caveats, decisions, premises and artefacts are pages *beside* the route: small chips under the page they belong to
(what a caveat limits, the step a decision is applied in, the page that relies on a premise, the step that made an
artefact). Resources, terms and references are the experiment's library: chips under the experiment.
"""
from __future__ import annotations

from kea.docsite.nodes import REVERSE_LABELS, Node, Tree, natural

ROUTE = ("experiment", "question", "hypothesis", "step", "result", "figure", "conclusion")
BESIDE = ("caveat", "decision", "premise", "artefact")
LIBRARY = ("resource", "term", "reference")
RANK = {kind: index for index, kind in enumerate(ROUTE)}


def _sort_key(node: Node) -> tuple:
    return (natural(node.number or node.id), node.id)


def _linked(tree: Tree, node: Node, outgoing: tuple[str, ...] = (), incoming: tuple[str, ...] = ()) -> list[Node]:
    """Pages linked to ``node`` by these relations (written on it, or written on the other page), same project."""
    found: list[Node] = []
    for relation in outgoing:
        found += [tree.nodes[key] for key in node.relations.get(relation, []) if key in tree.nodes]
    for relation in incoming:             # node.incoming is keyed by the reverse label ("Shows" for shown_in)
        found += [tree.nodes[key] for key in node.incoming.get(REVERSE_LABELS.get(relation, relation), [])
                  if key in tree.nodes and relation in tree.nodes[key].relations
                  and node.key in tree.nodes[key].relations[relation]]
    unique = {item.key: item for item in found if item.project == node.project and item.key != node.key}
    return list(unique.values())


def _best(candidates: list[Node], question: str | None) -> Node | None:
    """The candidate under the same question first, then by number."""
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item.key not in _MEMBERS.get(question or "", set()), _sort_key(item)))[0]


_MEMBERS: dict[str, set[str]] = {}       # question key -> keys of the pages whose home it is (filled by graph())


def tree_parent(tree: Tree, node: Node) -> tuple[str | None, bool]:
    """(the key of the page this one hangs from, whether it is a chip beside that page)."""
    from kea.docsite import whereami
    home = tree.projects.get(node.project)
    home_key = home.key if home is not None and home.key != node.key else None
    if node.type == "experiment":
        return None, False
    question = whereami.home_question(tree, node) if node.type != "question" else None
    question_key = question.key if question is not None else None
    if node.type in LIBRARY:
        return home_key, True
    if node.type == "question":
        parent = whereami._parent_question(tree, node)
        return (parent.key if parent is not None else home_key), False
    rank = RANK.get(node.type)

    def lower(candidates: list[Node]) -> list[Node]:
        return [item for item in candidates if item.type in RANK and (rank is None or RANK[item.type] < rank)]

    if node.type in ROUTE:
        if node.type == "hypothesis":
            choices: list[list[Node]] = []
        elif node.type == "step":
            choices = [_linked(tree, node, ("tests",))]
        elif node.type == "result":
            choices = [_linked(tree, node, ("made_by",)), _linked(tree, node, ("tests",))]
        elif node.type == "figure":
            choices = [_linked(tree, node, incoming=("shown_in",)), _linked(tree, node, ("made_by",))]
        else:   # conclusion: on its question (stable); explore.js draws every supports / opposes edge into it
            choices = []
        for candidates in choices:
            best = _best(lower(candidates), question_key)
            if best is not None:
                return best.key, False
        return (question_key or home_key), False
    # beside the route
    if node.type == "caveat":
        candidates = _linked(tree, node, ("limits",))
    elif node.type == "decision":
        candidates = _linked(tree, node, incoming=("decided_in",))
    elif node.type == "premise":
        candidates = _linked(tree, node, incoming=("relies_on",))
    elif node.type == "artefact":
        candidates = _linked(tree, node, ("made_by",)) or _linked(tree, node, incoming=("from_artefact",))
    else:
        candidates = []
    best = _best([item for item in candidates if item.type in RANK], question_key)
    return (best.key if best is not None else (question_key or home_key)), True


def graph(tree: Tree, hrefs: dict[str, str]) -> dict:
    """The site's graph for explore.js: {"projects": [keys of the experiment pages, in order], "nodes": [...]}.
    Each node: key, type, tag, title, short, href, project, parent (tree parent key or null), beside (chip),
    signed, waiting, status, question (home question key or null), edges [[relation, target key], ...]
    (the typed relations written on the page, to pages on the site)."""
    from kea.docsite import graph as graph_module
    from kea.docsite import whereami
    _MEMBERS.clear()
    for key, (home, _) in whereami.questions_of(tree).items():
        if home:
            _MEMBERS.setdefault(home, set()).add(key)
    depends = graph_module.upstream(tree)          # what each page rests on (its evidence, method, premises)
    nodes = []
    for node in sorted(tree.nodes.values(), key=lambda item: (item.project, RANK.get(item.type, 9), _sort_key(item))):
        if not hrefs.get(node.key):
            continue
        parent, beside = tree_parent(tree, node)
        if parent is not None and not hrefs.get(parent):
            parent = None
        question = node if node.type == "question" else whereami.home_question(tree, node)
        nodes.append({
            "key": node.key, "type": node.type, "tag": node.tag or "", "title": node.title, "short": node.short or "",
            "href": hrefs[node.key], "project": node.project, "parent": parent, "beside": beside,
            "signed": graph_module.approved(node), "waiting": bool(node.waiting), "status": node.status or "",
            "question": question.key if question is not None else None,
            # the scientific state shown on the box: a hypothesis fixed before its test, an exploratory analysis, how
            # sure a conclusion is, and a sign-off that no longer counts because a page it rests on changed
            "fixed": node.header.get("fixed_before_results") if node.type == "hypothesis" else None,
            "analysis": str(node.header.get("analysis") or ""), "certainty": str(node.header.get("certainty") or ""),
            "held": bool(node.held_by) or not node.chain_ok or bool(node.upstream_changed),
            "up": sorted(key for key in depends.get(node.key, ()) if hrefs.get(key)),
            "edges": [[relation, target] for relation, targets in sorted(node.relations.items())
                      for target in targets if target in tree.nodes and hrefs.get(target) and target != node.key],
        })
    order = [home.key for project, home in tree.projects.items() if hrefs.get(home.key)]
    return {"projects": order, "nodes": nodes}


# The graph view's styles (explore.html only). Type colours as on the rest of the site (render.CSS .t-<type>).
CSS = """
body:has(#xg) main{max-width:none;padding:0;margin:0}
body:has(#xg) .fb-dock,body:has(#xg) .fb-panel{display:none!important}
body.xg-zoomed .xg-tip,body.xg-zoomed .xg-mini{display:none}
.xg{position:fixed;left:0;right:0;bottom:0;top:var(--xg-top,44px);overflow:auto;background:#f6f7f9;outline:none;
 font-family:system-ui,sans-serif;overscroll-behavior:contain}
.xg.panning{cursor:grabbing;user-select:none}
.xg-size{position:relative}
.xg-world{position:absolute;left:0;top:0;transform-origin:0 0}
.xg-heads{position:sticky;top:0;height:30px;z-index:4;pointer-events:none;background:rgba(246,247,249,.96);border-bottom:1px solid #e4e7ec;
 transform-origin:0 0}
.xg-heads span{position:absolute;top:0;height:30px;font:600 11.5px/30px system-ui,sans-serif;letter-spacing:.06em;
 text-transform:uppercase;color:#5d6475;padding-left:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.xg-band{position:absolute;border-radius:10px;background:#fff;border:1px solid #e4e7ec}
.xg-band.alt{background:#fbfbfc}.xg-band.here{background:#f1f6fc;border-color:#c9dcef}
.xg-band .xg-sum{position:absolute;top:0;height:100%;display:flex;align-items:center;gap:8px;font:12.5px system-ui,sans-serif;color:#5d6475;white-space:nowrap}
.xg-band .xg-sum b{font-weight:600;color:#3a3f4b}
.xg-edges{position:absolute;left:0;top:0;overflow:visible;pointer-events:none}
.xg-edges path{fill:none;stroke:#c3c8d1;stroke-width:1.4}
.xg-edges path.support{stroke:#58a777;stroke-width:1.4}.xg-edges path.oppose{stroke:#c0392b;stroke-dasharray:5 4}
.xg-edges.focus path{opacity:.28}
.xg-edges path.up{stroke:#1f5f99;stroke-width:2.4;opacity:1}.xg-edges path.down{stroke:#c26b00;stroke-width:2.4;opacity:1}
.xg-node{position:absolute;display:flex;align-items:stretch;border:0;padding:0;margin:0;background:#fff;border-radius:7px;
 box-shadow:0 0 0 1px #d6dae1,0 1px 2px rgba(20,30,50,.06);cursor:pointer;text-align:left;font:inherit;color:#1e2230;overflow:hidden}
.xg-node:hover{box-shadow:0 0 0 1px #9aa3b2,0 2px 6px rgba(20,30,50,.12)}
.xg-node:focus{outline:none}
.xg-node.sel{box-shadow:0 0 0 3px #1e2230,0 4px 14px rgba(20,30,50,.22);z-index:2}
.xg-node.up{box-shadow:0 0 0 2px #1f5f99}.xg-node.down{box-shadow:0 0 0 2px #c26b00}
.xg-world.focus .xg-node:not(.sel):not(.up):not(.down){opacity:.72}
.xg-node .tg{flex:0 0 46px;display:flex;align-items:center;justify-content:center;color:#fff;font:700 13px/1 system-ui,sans-serif;letter-spacing:.01em}
.xg-node .bd{flex:1;min-width:0;padding:5px 8px 4px 9px;display:flex;flex-direction:column;justify-content:center;gap:2px}
.xg-node .tt{font-size:12.5px;line-height:1.28;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.xg-node .mt{font-size:10.5px;line-height:1.2;color:#6b7280;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.xg-node .mk{position:absolute;right:5px;top:4px;font:700 11px/1 system-ui,sans-serif}
.xg-node .mk.ok{color:#2e9e5b}.xg-node .mk.wait{color:#c26b00}.xg-node .mk.held{color:#8a6d00}
.xg-node.open .tg{background:#fff!important;color:var(--c);box-shadow:inset 0 0 0 2px var(--c)}
.xg-node.signing{box-shadow:0 0 0 2px #2e9e5b}
.xg-node.signing.sel{box-shadow:0 0 0 3px #1e2230,0 0 0 6px #9fd9b5}
.xg-node.gone{opacity:.5}.xg-node.gone .tt{text-decoration:line-through}
.xg-node.sub .tg{box-shadow:inset 4px 0 0 rgba(255,255,255,.55)}
.xg-node.fold .tg{background:#5d6475}
.xg-exp{position:absolute;border:0;border-radius:9px;background:#333;color:#fff;cursor:pointer;padding:0;display:flex;align-items:center;justify-content:center}
.xg-exp span{writing-mode:vertical-rl;transform:rotate(180deg);font:600 13px/1 system-ui,sans-serif;letter-spacing:.05em;white-space:nowrap;
 overflow:hidden;text-overflow:ellipsis;max-height:calc(100% - 16px)}
.xg-exp.sel{box-shadow:0 0 0 3px #fff,0 0 0 6px #1e2230}.xg-exp:focus{outline:none}
.xg-mini{position:fixed;right:14px;bottom:14px;z-index:6;opacity:.82;background:rgba(255,255,255,.94);border:1px solid #d6dae1;border-radius:8px;
 box-shadow:0 2px 10px rgba(20,30,50,.12);cursor:pointer}
.xg-mini canvas{display:block}.xg-mini:hover{opacity:1}
.xg-tip{position:fixed;left:14px;bottom:14px;z-index:6;max-width:min(560px,calc(100vw - 240px));background:#1e2230;color:#e8eaf0;
 border-radius:8px;padding:8px 12px;font:13px/1.45 system-ui,sans-serif;box-shadow:0 2px 10px rgba(20,30,50,.2)}
.xg-tip b{color:#fff}.xg-tip .k{display:inline-block;border:1px solid #59607a;border-radius:4px;padding:0 4px;margin:0 1px;font:11px/16px ui-monospace,monospace;color:#cfd3dd}
.xg-tip .why{color:#aeb4c2}
.xg-zoom-dim{position:fixed;inset:0;top:var(--xg-top,44px);background:rgba(30,34,48,.34);z-index:20;opacity:0;transition:opacity .22s}
.xg-zoom-dim.on{opacity:1}
.xg-zoom{position:fixed;z-index:21;background:#fff;border-radius:10px;box-shadow:0 12px 48px rgba(10,15,30,.35);overflow:hidden;
 display:flex;flex-direction:column;transform-origin:0 0}
.xg-zoom.anim{transition:transform .26s cubic-bezier(.2,.7,.2,1),opacity .26s}
.xg-zoom header{flex:0 0 auto;display:flex;align-items:center;gap:10px;padding:8px 12px;border-bottom:1px solid #e4e7ec;font:14px system-ui,sans-serif}
.xg-zoom header .tg{color:#fff;border-radius:5px;padding:3px 7px;font:700 13px/1 system-ui,sans-serif}
.xg-zoom header .ttl{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:600}
.xg-zoom header a,.xg-zoom header button{font:13px system-ui,sans-serif;color:#1f5f99;background:none;border:0;cursor:pointer;padding:4px 6px;white-space:nowrap}
.xg-zoom header button.back{border:1px solid #c9ced8;border-radius:6px;color:#1e2230}
.xg-zoom .wait{flex:1;padding:28px 40px;color:#5d6475;font:15px/1.5 system-ui,sans-serif}
.xg-zoom iframe{flex:1;border:0;width:100%;background:#fff;opacity:0;transition:opacity .15s}
.xg-zoom iframe.ready{opacity:1}
.xg-find{position:fixed;left:50%;top:calc(var(--xg-top,44px) + 14px);transform:translateX(-50%);z-index:30;width:min(560px,calc(100vw - 32px));
 background:#fff;border-radius:10px;box-shadow:0 10px 40px rgba(10,15,30,.3);overflow:hidden;font:14px system-ui,sans-serif}
.xg-find input{width:100%;box-sizing:border-box;border:0;border-bottom:1px solid #e4e7ec;padding:12px 14px;font:15px system-ui,sans-serif;outline:none}
.xg-find ol{list-style:none;margin:0;padding:4px 0;max-height:50vh;overflow:auto}
.xg-find li{display:flex;gap:10px;align-items:center;padding:6px 14px;cursor:pointer}
.xg-find li.on{background:#eef4fb}
.xg-find li .tg{color:#fff;border-radius:4px;padding:2px 6px;font:700 12px/1 system-ui,sans-serif;flex:0 0 auto}
.xg-find li span:last-child{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.xg-help{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);z-index:30;background:#fff;border-radius:12px;box-shadow:0 10px 40px rgba(10,15,30,.3);
 padding:18px 24px;font:14px/1.5 system-ui,sans-serif;width:min(620px,calc(100vw - 32px));max-height:80vh;overflow:auto}
.xg-help h2{margin:0 0 8px;font-size:17px}.xg-help table{border-collapse:collapse;width:100%}
.xg-help table{table-layout:auto;display:table;overflow:visible}
.xg-help td{padding:4px 10px 4px 0;vertical-align:top;white-space:normal!important;overflow:visible;border:0;border-bottom:1px solid #eef0f3}
.xg-help td:first-child{white-space:nowrap!important;width:1%}
.xg-help kbd{display:inline-block;border:1px solid #c9ced8;border-bottom-width:2px;border-radius:4px;padding:0 5px;font:12px/18px ui-monospace,monospace;margin-right:2px}
.xg-legend{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:10px;font-size:13px;color:#3a3f4b}
@media (prefers-reduced-motion:reduce){.xg-zoom.anim,.xg-zoom-dim,.xg-zoom iframe{transition:none}}
@media (max-width:700px){.xg-tip{display:none}.xg-mini{display:none}}
"""
