"""The hub's own pages on the apex (https://<domain>/): a landing page for visitors and a page for a signed-in reader.

What it does: renders two self-contained HTML pages (no external resources; the only image is the Kea head the hub
serves at /kea-head.png) from plain data that hub.HubApp collects:

    visitor_page(hub_title, sign_in_url, public_rows)
        what Kea and the hub are, a large "Sign in with ORCID" button (when the hub has an ORCID client) and the
        public projects as a table.
    reader_page(hub_title, person, rows, public_rows, sign_out_url)
        the reader's name and ORCID iD, a table of the projects they can open (their role there and what it may do,
        public or private, last published), the projects waiting for approval, the public projects where they have
        no role, and Sign out.

A row is a dict: title, url, name, public (bool), published ('YYYY-MM-DD' or ''), role ('' or an accounts.ROLES
name), pending (bool). Every value is escaped here.
"""
from __future__ import annotations

from kea import __version__

import html

from kea.feedback import accounts

LOGO = "/kea-head.png"

STYLE = """
:root{--navy:#1d2330;--fg:#1d2330;--muted:#5a6270;--line:#e1e4ea;--bg:#f6f7f9;--accent:#1f5fa8;--orcid:#a6ce39}
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:var(--fg);background:var(--bg)}
a{color:var(--accent)}
.topbar{background:var(--navy);color:#fff;display:flex;align-items:center;gap:12px;padding:8px 18px;min-height:46px}
.topbar img{width:30px;height:30px}
.topbar .brand{font-weight:700;font-size:15px;color:#fff;text-decoration:none;display:flex;align-items:center;gap:10px}
.topbar .domain{color:#aab3c5;font-size:13px}
.topbar .version{color:#9aa3b2;font:500 11px/1 system-ui,sans-serif;border:1px solid #4a5468;border-radius:9px;padding:3px 7px;margin-left:10px;white-space:nowrap}
.topbar .right{margin-left:auto;display:flex;gap:14px;align-items:center;font-size:14px;min-width:0}
.topbar .right a{color:#fff}
.topbar .who{color:#d5dbe6;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
main{max-width:920px;margin:0 auto;padding:28px 18px 48px}
.hero{display:flex;gap:28px;align-items:center;padding:18px 0 26px;border-bottom:1px solid var(--line);margin-bottom:26px}
.hero img{width:128px;height:128px;flex:0 0 auto}
.hero h1{font-size:30px;margin:0 0 8px;letter-spacing:-.01em}
.hero p{margin:0 0 10px;max-width:60ch;color:#333a47}
.orcid-button{display:inline-flex;align-items:center;gap:12px;margin:10px 0 6px;padding:13px 22px;border-radius:9px;
background:var(--orcid);color:var(--navy);font-weight:700;font-size:17px;text-decoration:none;box-shadow:0 1px 3px #0002}
.orcid-button:hover{background:#97bd2f}
.orcid-id{display:inline-grid;place-items:center;width:26px;height:26px;border-radius:50%;background:#fff;color:var(--orcid);
font-size:12.5px;font-weight:800}
.note{font-size:13px;color:var(--muted);margin:4px 0 0}
h1.page{font-size:24px;margin:0 0 4px}
h2{font-size:17px;margin:30px 0 8px}
.person{color:var(--muted);margin:0 0 18px}
.notice{background:#fff7e0;border:1px solid #ecd48a;border-radius:8px;padding:10px 14px;margin:14px 0}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:8px;font-size:14px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);background:#fafbfc;font-weight:600}
tr:last-child td{border-bottom:0}
td .sub{display:block;font-size:12.5px;color:var(--muted);overflow-wrap:anywhere}
td.date{white-space:nowrap;color:#333a47}td .sub.date{margin-top:4px}.nowrap{white-space:nowrap}
.role{font-weight:700}
.pill{display:inline-block;font-size:12px;padding:1px 9px;border-radius:10px;border:1px solid var(--line);white-space:nowrap}
.pill.public{background:#e6f3e8;border-color:#a9d3b1;color:#1e5e22}
.pill.private{background:#eef0f4;color:#4a5160}
.pill.pending{background:#fff3cf;border-color:#ecd48a;color:#6d5300}
.empty{color:var(--muted);font-style:italic}
footer{color:var(--muted);font-size:12.5px;margin-top:36px}
@media (max-width:640px){
 .hero{flex-direction:column;align-items:flex-start;gap:14px}.hero img{width:84px;height:84px}.hero h1{font-size:25px}
 .topbar .domain{display:none}main{padding:20px 16px 40px}th,td{padding:8px 7px}table{font-size:13.5px}
 td .sub{font-size:12px}th{font-size:11px}
 .orcid-button{display:flex;justify-content:center}
}
"""


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _page(title: str, hub_title: str, domain: str, right: str, body: str) -> str:
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{_esc(title)}</title>"
            f"<link rel='icon' href='{LOGO}' type='image/png'><style>{STYLE}</style></head><body>"
            f"<header class='topbar'><a class='brand' href='/'><img src='{LOGO}' alt=''>{_esc(hub_title)}</a>"
            f"<span class='domain'>{_esc(domain)}</span><span class='version' title='This hub runs Kea {_esc(__version__)}'>"
            f"Kea {_esc(__version__)}</span><span class='right'>{right}</span></header>"
            f"<main>{body}<footer>Kea: typed, versioned documentation sites for data analyses, reviewed by comments."
            f"</footer></main></body></html>")


def _orcid_button(url: str) -> str:
    return (f"<a class='orcid-button' href='{_esc(url)}'><span class='orcid-id' aria-hidden='true'>iD</span>"
            "Sign in with ORCID</a>")


def _access(row: dict) -> str:
    return "<span class='pill public'>public</span>" if row.get("public") else "<span class='pill private'>private</span>"


def _published(row: dict) -> str:
    return _esc(row["published"]) if row.get("published") else "<span class='empty'>not yet</span>"


def _project_cell(row: dict) -> str:
    return (f"<a href='{_esc(row['url'])}'>{_esc(row.get('title') or row['name'])}</a>"
            f"<span class='sub'>{_esc(row['url'].split('://', 1)[-1].rstrip('/'))}</span>")


def public_table(rows: list[dict], note: str = "") -> str:
    if not rows:
        return "<p class='empty'>No public projects on this hub.</p>"
    body = "".join(f"<tr><td>{_project_cell(row)}</td><td class='date'>{_published(row)}</td></tr>" for row in rows)
    return (f"{note}<div class='scroll'><table><thead><tr><th>Project</th><th>Last published</th></tr></thead>"
            f"<tbody>{body}</tbody></table></div>")


def visitor_page(hub_title: str, domain: str, sign_in_url: str | None, public_rows: list[dict]) -> str:
    """The apex for a visitor who is not signed in."""
    if sign_in_url:
        sign_in = (f"{_orcid_button(sign_in_url)}<p class='note'>One sign-in opens every project on this hub you "
                   "have a role in. A new ORCID iD waits for approval by the hub's administrator before it opens a "
                   "private project.</p>")
        right = f"<a href='{_esc(sign_in_url)}'>Sign in</a>"
    else:
        sign_in = ("<p class='note'>This hub has no ORCID sign-in; every project asks for its own password. Open "
                   "the link to your project.</p>")
        right = ""
    body = (f"<section class='hero'><img src='{LOGO}' alt='Kea, a mountain parrot'><div>"
            f"<h1>{_esc(hub_title)}</h1>"
            "<p>Kea turns a data analysis into a documentation site: questions, premises, hypotheses, results and "
            "conclusions as typed, versioned pages, each linked to the code and data behind it.</p>"
            "<p>This hub hosts the sites of several research projects. Readers comment on any sentence; the project's "
            "agent folds the comments into a plan and works through it in review cycles.</p>"
            f"{sign_in}</div></section>"
            "<h2>Public projects</h2>" + public_table(public_rows))
    return _page(hub_title, hub_title, domain, right, body)


def reader_page(hub_title: str, domain: str, person: dict, rows: list[dict], public_rows: list[dict],
                sign_out_url: str) -> str:
    """The apex for a signed-in reader. person: {orcid, name, status}."""
    orcid = person.get("orcid", "")
    name = person.get("name") or orcid
    status = person.get("status", "")
    right = (f"<span class='who'>{_esc(name)}</span><a href='{_esc(sign_out_url)}'>Sign out</a>")
    parts = [f"<h1 class='page'>{_esc(name)}</h1>",
             f"<p class='person'>ORCID iD <a href='https://orcid.org/{_esc(orcid)}'>{_esc(orcid)}</a>"
             f" · <a href='{_esc(sign_out_url)}'>Sign out</a> (of this hub and every project site)</p>"]
    if status == "blocked":
        parts.append("<p class='notice'>This ORCID iD may not use this hub. Public projects stay readable.</p>")
    elif status != "approved":
        parts.append("<p class='notice'>Your sign-in waits for approval by the hub's administrator. Once approved, "
                     "your projects appear here.</p>")
    parts.append("<h2>Your projects</h2>")
    if rows:
        body = []
        for row in rows:
            if row.get("pending"):
                role = ("<span class='pill pending'>pending approval</span><span class='sub'>you asked to open this "
                        "project; the hub's administrator has not given you a role yet</span>")
            else:
                role = (f"<span class='role'>{_esc(accounts.role_label(row['role']))}</span>"
                        f"<span class='sub'>{_esc(accounts.ROLE_TEXT.get(row['role'], ''))}</span>")
            body.append(f"<tr><td>{_project_cell(row)}</td><td>{role}</td><td>{_access(row)}"
                        + (f"<span class='sub date'>published <span class='nowrap'>{_esc(row['published'])}</span></span>"
                           if row.get("published")
                           else "<span class='sub date'>not published yet</span>") + "</td></tr>")
        parts.append("<div class='scroll'><table><thead><tr><th>Project</th><th>Your role</th>"
                     "<th>Access</th></tr></thead>"
                     f"<tbody>{''.join(body)}</tbody></table></div>")
    else:
        parts.append("<p class='empty'>No project gives you a role yet.</p>")
    if public_rows:
        parts.append("<h2>Other public projects</h2>")
        parts.append(public_table(public_rows, "<p class='note' style='margin-bottom:8px'>Readable without a role; "
                                               "to comment, ask the hub's administrator for one.</p>"))
    return _page(f"{name} · {hub_title}", hub_title, domain, right, "".join(parts))
