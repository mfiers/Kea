"""HTML building blocks of the documentation site: page shell, CSS, top bar, breadcrumbs, link rendering, Markdown.

Pure string functions (plus Markdown rendering). Every page gets the same top bar and breadcrumbs; navigation,
generated lists and anything that changes when *other* pages change carry the class ``not-annotatable`` so reader
comments stay anchored to the page's own text.
"""
from __future__ import annotations

import html
import re

import markdown

from kea.config import SETTINGS
from kea.docsite import icons
from kea.docsite.nodes import DOC, LINK_PATTERN, TYPE_LABELS, TYPE_PLURALS, Node, Tree

RUN_ID = re.compile(r"\d{4}-\d{2}-\d{2}-[\w-]+")

SITE_TITLE = SETTINGS["title"]     # the project (kea.yaml); its parts (doc/<folder>/) are experiments
SKIP_AUTOLINK_TAGS = {"a", "code", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "th", "script", "style"}

CSS = """
:root{--fg:#1d2330;--muted:#5b6475;--line:#d9dde5;--bg:#fff;--soft:#f5f7fa;--accent:#1f5fa8;--warn:#a33;
--ok:#1b7f4b;--amber:#a86b00}
*{box-sizing:border-box}
body{margin:0;font:15.5px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--fg);background:var(--bg)}
main{max-width:980px;margin:0 auto;padding:12px 18px 60px}main.wide{max-width:1440px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.topbar{background:#1d2330;color:#fff;padding:7px 18px;font-size:14px;display:flex;gap:14px;flex-wrap:nowrap;
align-items:center;position:relative}
.topbar a{color:#dfe6f2}
.topbar .trail{display:flex;align-items:center;gap:7px;min-width:0;flex:1 1 auto;white-space:nowrap;overflow:hidden}
.topbar .seg{display:inline-flex;align-items:center;gap:7px;min-width:0;flex:0 0 auto}
.topbar .seg.here{flex:1 1 auto}
.topbar .sep{color:#6f7a8e}.topbar .home{font-weight:800;color:#fff;letter-spacing:.02em;flex:0 0 auto}
.topbar .project{color:#fff;font-weight:600}
.topbar .experiment{background:#333;color:#fff;box-shadow:inset 0 0 0 1px #8a93a3;font-weight:700;border-radius:4px;padding:1px 10px;
overflow:hidden;text-overflow:ellipsis}
.topbar .experiment:hover{text-decoration:none;background:#4a5468}
.topbar .here .tag{margin:0;flex:0 0 auto}
.topbar .here-title{display:block;color:#c9d2e3;overflow:hidden;text-overflow:ellipsis;min-width:0}
.topbar .links{display:flex;gap:16px;flex:0 0 auto;white-space:nowrap}.topbar .links .off{color:#6b7488;cursor:default}.topbar .grp{display:inline-flex;align-items:center;gap:12px}.topbar .grp .sub{display:none;align-items:center;gap:12px}.topbar .grp.open>.sub{display:inline-flex;gap:2px;background:#2c3446;border-radius:6px;padding:2px 3px;box-shadow:inset 0 0 0 1px #3d475b}.topbar .grp.open>a:first-child{color:#fff;font-weight:600}.topbar .grp.open>a:first-child::after{content:' ▸';font-size:11px;color:#8a93a3}.topbar .grp .sub a,.topbar .grp .sub .off{font-size:13px;color:#c9d2e3;padding:1px 8px;border-radius:4px;line-height:1.45}.topbar .grp .sub .off{color:#6b7488}.topbar .grp .sub a:hover{background:#3d475b;color:#fff;text-decoration:none}.topbar .links .grp .sub a.cur{background:#4f5a70;color:#fff;font-weight:600;border-bottom:0}.topbar .links a.cur{color:#fff;font-weight:700;border-bottom:2px solid #fff}.topbar.folded.open .grp,.topbar.folded.open .grp .sub{display:flex;flex-direction:column;align-items:flex-start;gap:8px}.topbar.folded.open .grp .sub{padding:4px 6px;margin-left:10px}.topbar.folded.open .grp .sub::before{content:none}.topbar .nav-count{display:inline-block;margin-left:5px;min-width:18px;padding:0 6px;border-radius:9px;background:#4a5468;color:#fff;font:600 11.5px system-ui,sans-serif;line-height:17px;text-align:center}
.topbar .menu-button{background:none;border:1px solid #4a5468;color:#fff;border-radius:5px;font-size:16px;padding:0 9px;
cursor:pointer;flex:0 0 auto}
.topbar .menu-button{-webkit-tap-highlight-color:transparent}.topbar .menu-button:focus{outline:none}.topbar .menu-button:focus-visible{outline:2px solid #c9d2e3;outline-offset:1px}.topbar.open .menu-button,.topbar .menu-button:hover{background:#3d475b}
.topbar.folded .links{display:none}
.topbar.folded.open .links{display:flex;flex-direction:column;gap:8px;position:absolute;right:12px;top:100%;
background:#1d2330;padding:10px 16px;border-radius:0 0 8px 8px;z-index:2000;box-shadow:0 6px 18px rgba(0,0,0,.25)}
.topbar .page-tools{display:flex;gap:8px;flex:0 0 auto}.topbar .page-tools:empty{display:none}
.topbar .page-tools button{background:#2c3446;border:1px solid #4a5468;color:#fff;border-radius:5px;cursor:pointer;
display:inline-flex;align-items:center;gap:5px;font:600 13px system-ui,sans-serif;padding:2px 9px}
.topbar .page-tools button:hover{background:#2d3748}.topbar .page-tools .ico{width:15px;height:15px}
.topbar .home img{display:block;background:#f4f1e8;border-radius:5px;padding:1px}
.topbar .user{display:flex;align-items:center;gap:10px;flex:0 0 auto;position:relative;padding-left:14px;border-left:1px solid #4a5468;white-space:nowrap}
.topbar .user-name{background:none;border:0;color:#fff;font:inherit;font-weight:600;cursor:pointer;padding:0;max-width:180px;overflow:hidden;text-overflow:ellipsis}
.topbar .user-name::after{content:' ▾';color:#8a93a3;font-weight:400}
.topbar .user-menu{position:absolute;right:0;top:calc(100% + 9px);background:#1d2330;border:1px solid #4a5468;border-radius:0 0 7px 7px;padding:6px 0;min-width:190px;z-index:60;box-shadow:0 6px 16px #0005}
.topbar .user-menu a,.topbar .user-menu .who{display:block;padding:6px 14px;color:#dfe6f2}
.topbar .user-menu a:hover{background:#2d3748;text-decoration:none}
.topbar .user-menu .who{font-size:12.5px;color:#8a93a3;border-bottom:1px solid #2d3748;margin-bottom:4px;white-space:normal}
.topbar .user-menu .sep-line{border-top:1px solid #2d3748;margin:4px 0}.topbar .user-menu .versions{padding:4px 14px 2px;font:500 11.5px system-ui,sans-serif;color:#8a93a3;white-space:nowrap}.topbar .user-menu .versions.differs{color:#fff;font-weight:600}.topbar .user-menu .group{padding:6px 14px 2px;font:600 11px system-ui,sans-serif;letter-spacing:.06em;text-transform:uppercase;color:#8a93a3}.topbar .user-menu a.project{display:flex;justify-content:space-between;gap:14px;max-width:320px}.topbar .user-menu a.project .role{font-size:11.5px;color:#8a93a3;white-space:nowrap}
.topbar.user-open,body.has-kindbar .topbar.user-open{z-index:80}
/* the folded menu (narrow screens): one dark panel, every sub-item light on dark, the current one marked; it scrolls
   inside itself when taller than the screen */
.topbar.folded.open .links{max-height:calc(100vh - 56px);max-height:calc(100dvh - 56px);overflow-y:auto;overscroll-behavior:contain;min-width:220px;gap:2px;padding:8px 0 10px}
.topbar.folded.open .links>a,.topbar.folded.open .links>.off,.topbar.folded.open .grp>a:first-child{display:block;padding:9px 18px 5px;font-weight:600;color:#fff}
.topbar.folded.open .grp{gap:0;width:100%}
.topbar.folded.open .grp>a:first-child::after{content:none}
.topbar.folded.open .grp .sub,.topbar.folded.open .grp.open>.sub{display:flex;flex-direction:column;align-items:stretch;gap:0;width:100%;box-sizing:border-box;background:none;box-shadow:none;border-radius:0;margin:0;padding:0 0 4px}
.topbar.folded.open .grp .sub a,.topbar.folded.open .grp .sub .off{display:block;padding:7px 18px 7px 32px;font-size:14px;line-height:1.3;color:#c9d2e3;border-radius:0;border-left:3px solid transparent}
.topbar.folded.open .grp .sub .off{color:#7d879a}
.topbar.folded.open .grp .sub a:hover{background:#2d3748;color:#fff}
.topbar.folded.open .links .grp .sub a.cur{background:#2c3446;color:#fff;font-weight:700;border-left-color:#c9d2e3}
.topbar.folded.open .links>a.cur,.topbar.folded.open .grp>a.cur:first-child{color:#fff;border-bottom:0;text-decoration:underline;text-underline-offset:4px}
@media (max-width:760px){
 .topbar{position:sticky;top:0;z-index:50}body.has-kindbar .topbar{z-index:50}html{scroll-padding-top:56px}
 .topbar .user-menu{max-height:calc(100dvh - 60px);overflow-y:auto;overscroll-behavior:contain}
}
.topbar.no-project .seg.project,.topbar.no-experiment .seg.experiment-seg{display:none}
.crumbs{font-size:13px;color:var(--muted);margin:6px 0 10px}.crumbs a{color:var(--muted)}
h1{font-size:25px;line-height:1.25;margin:6px 0 8px}h2{font-size:19px;margin:28px 0 8px;border-bottom:1px solid var(--line);padding-bottom:3px}
h3{font-size:16px;margin:20px 0 6px}
.badge{display:inline-block;font-size:12px;font-weight:600;color:#fff;background:#556;border-radius:4px;padding:1px 7px;margin-right:6px;vertical-align:middle}
.kindbar{position:fixed;left:0;top:0;bottom:0;width:30px;z-index:5;display:flex;justify-content:center;align-items:flex-start;padding-top:58px;box-sizing:border-box;color:#fff}.kindbar{flex-direction:column;align-items:center!important;justify-content:flex-start!important;gap:9px}.kindbar .ico{width:18px;height:18px;flex:0 0 auto;stroke:#fff;color:#fff}.kindbar span{writing-mode:vertical-rl;transform:rotate(180deg);font:700 13px/1 system-ui,sans-serif;letter-spacing:.14em;text-transform:uppercase;white-space:nowrap;opacity:.95}body.has-kindbar{padding-left:30px}body.has-kindbar .topbar{margin-left:-30px;z-index:6}@media (max-width:760px){.kindbar{width:7px}.kindbar span,.kindbar .ico{display:none}body.has-kindbar{padding-left:7px}body.has-kindbar .topbar{margin-left:-7px}}@media print{.kindbar{display:none}body.has-kindbar{padding-left:0}body.has-kindbar .topbar{margin-left:0}}.node-content{margin:4px 0 0}.pid{font-size:12.5px;color:var(--muted);margin:2px 0 0;text-align:right}.node-data-sep{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.node-data-sep .pid{display:block;margin:0;padding:12px 0 0;border-radius:0;font:400 11.5px/1.3 system-ui,sans-serif;letter-spacing:0;text-transform:none;text-align:left;color:#7a8394;background:none}.node-data-sep .pid a{color:#7a8394;text-decoration:none;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;cursor:copy}.node-data-sep .pid a:hover{color:var(--accent);text-decoration:underline}.node-data-sep .pid a.copied{color:#1e6e3e}.node-data-sep .sep-label{margin-left:auto}.media-sep{align-items:flex-start}.node-data-sep span.media-tabs{display:flex;flex-wrap:wrap;gap:4px;line-height:0;background:none;padding:0;border-radius:0;letter-spacing:0;text-transform:none}.node-data-sep button.media-tab{display:inline-block;border:0;cursor:pointer;background:color-mix(in srgb,var(--kc,#556) 38%,#fff);color:#fff;padding:3px 10px 4px;border-radius:0 0 6px 6px;line-height:1.3;font:600 11.5px system-ui,sans-serif;letter-spacing:.02em;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.node-data-sep button.media-tab:hover{background:color-mix(in srgb,var(--kc,#556) 65%,#fff)}.node-data-sep button.media-tab.on{background:var(--kc,#556)}.media-panels{margin:10px 0 0}.media-head{margin:4px 0 6px;font-weight:600}@media print{.media-panel[hidden]{display:block!important}.media-tabs{display:none}}.obj-search{width:100%;box-sizing:border-box;font:15px system-ui,sans-serif;padding:8px 12px;border:1px solid var(--line);border-radius:7px;margin:6px 0 10px}.obj-search:focus{outline:2px solid var(--accent);outline-offset:0}.obj-chips{display:flex;flex-wrap:wrap;gap:5px;align-items:center;margin:4px 0}.obj-label{font:600 11px system-ui,sans-serif;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);width:56px}.obj-chip{border:1px solid var(--line);background:#fff;border-radius:14px;padding:2px 10px;font:600 12.5px system-ui,sans-serif;cursor:pointer;color:var(--fg)}.obj-chip .obj-count{font-weight:400;color:var(--muted)}.obj-chip.on{box-shadow:inset 0 0 0 2px #5b6475;background:#f5f7fa}.obj-chip.s-chip.on{background:#eef1f5}.obj-clear{border:0;background:none;color:var(--accent);cursor:pointer;font:13px system-ui,sans-serif;text-decoration:underline;margin-left:6px}.obj-info{font-size:13px;color:var(--muted);margin:10px 0 0}.obj-table th button{border:0;background:none;font:inherit;font-weight:700;cursor:pointer;padding:0;color:inherit}.obj-pager{display:flex;gap:8px;align-items:center;justify-content:center;margin:10px 0;font-size:13px}.obj-pager button{border:1px solid var(--line);background:#fff;border-radius:6px;padding:3px 10px;cursor:pointer}.obj-pager button:disabled{opacity:.4;cursor:default}table.nodes{display:table;width:100%;table-layout:fixed;margin:8px 0 4px}table.nodes col.c-page{width:36%}table.nodes col.c-status{width:132px}table.nodes td{vertical-align:top;white-space:normal;overflow-wrap:anywhere}table.nodes td:last-child,table.nodes th:last-child{text-align:right}table.nodes.no-status td:last-child,table.nodes.no-status th:last-child{text-align:left}table.comments-table col.c-who{width:150px}table.comments-table col.c-where{width:26%}table.comments-table col.c-status{width:180px}table.comments-table .fb-pill{display:inline-block;text-align:right}table.nodes .cell-note{font-size:12px;color:var(--muted);margin-top:3px}.m-status{display:none}@media (max-width:640px){table.nodes col.c-page{width:42%}table.nodes col.c-status{width:96px}}.kindrow{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin:6px 0 2px}.kindrow .kind{font-size:15px;font-weight:700;letter-spacing:.02em}.kindrow .kind .ico{width:15px;height:15px;vertical-align:-2px;margin-right:5px}.kindrow .kind .tag .ico{width:1.05em;height:1.05em;vertical-align:-.17em;margin-right:4px}.kindrow .pills{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:4px}.kindrow .pills .pill{font-size:11px;font-weight:400;margin:0}.node-content h1{margin-top:0}.pill.fb-pp-ok{background:#dff0e0;color:#1e5e22;border-color:#9fd3b5;font-weight:600}/* the page as written: Kea's typewriter face (IBM Plex Mono, _assets/), indented behind a rule in the type's colour */.given{margin:12px 0 0 4px;padding:2px 0 2px 22px;border-left:3px solid color-mix(in srgb,var(--kc,#556) 30%,#fff)}.given h1 .node-title,.given .short,.given article{font-family:'Kea Mono',ui-monospace,'SF Mono',Menlo,Consolas,monospace}.given h1{font-size:24px;font-weight:600;letter-spacing:-.01em;line-height:1.3}.given .short{font-size:15px;line-height:1.6;border-left-color:var(--kc);margin-left:0}.given article{font-size:15px;line-height:1.72;color:#22262e}.given article h2,.given article h3{font-family:'Kea Mono',ui-monospace,monospace;font-weight:600;letter-spacing:-.005em}.given article em{font-style:italic}.given article code{background:var(--soft);padding:0 3px;border-radius:3px}.given article table,.given article .featured,.given article figure{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}@media (max-width:640px){.given{margin-left:0;padding-left:9px;border-left-width:2px}.given h1{font-size:21px}.given .short{font-size:14px;line-height:1.5;padding-left:10px}.given article{font-size:14px;line-height:1.58}}.node-data-sep{margin:64px 0 6px;border-top:6px solid var(--kc,#556);text-align:right;line-height:0}.node-data-sep span{display:inline-block;background:var(--kc,#556);color:#fff;padding:3px 12px 4px;border-radius:0 0 6px 6px;line-height:1.3;font:700 11.5px system-ui,sans-serif;letter-spacing:.12em;text-transform:uppercase}section.about h2,section.questions h2{font-size:17px}.answer-label{display:block;font:700 11.5px system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#6b7488;margin-bottom:2px}ul.sources{margin:4px 0}.t-experiment{background:#333}.t-premise{background:#6a4c93}.t-question{background:#1f77b4}.t-hypothesis{background:#a23c9e}
.t-step{background:#2a7f62}.t-result{background:#8c564b}.t-conclusion{background:#c0392b}.t-decision{background:#757575}
.t-figure{background:#17818a}.t-artefact{background:#966d09}.t-caveat{background:#c64f00}
.t-term,.t-reference,.t-page{background:#556}.t-resource{background:#5b6b2f}.t-term{background:#5f6b7a}.t-reference{background:#3d5a80}
.badge .ico,.tag .ico{width:1.05em;height:1.05em;vertical-align:-.17em;margin-right:4px}
a.tag,span.tag{display:inline-flex;align-items:center;font-size:12px;font-weight:700;color:#fff;border-radius:11px;
padding:1px 8px 1px 6px;line-height:1.45;vertical-align:baseline;white-space:nowrap;box-shadow:0 1px 0 rgba(0,0,0,.18);
text-decoration:none}
a.tag:hover{text-decoration:none;filter:brightness(1.12);box-shadow:0 1px 3px rgba(0,0,0,.3)}
a.tagline{color:var(--fg);display:inline}a.tagline:hover{text-decoration:none;background:#eef3fb}
a.tagline .tag{margin-right:6px}a.tagline .kindword{font-weight:700;margin-right:3px}a.tagline .tl-text{border-bottom:1px dotted #8a94a6}
.qhead{display:block;line-height:1.5}
.qblock{margin:6px 0 18px}.qblock .answer{margin:4px 0 6px}.answer-basis{font:13px system-ui,sans-serif;color:var(--muted);margin:2px 0 8px}.answer-basis .tag{margin-right:3px}.project-summary{font-size:15px;color:#3b4252;border-left:3px solid #9aa3b2;padding:2px 0 2px 12px;margin:10px 0}.project-summary .answer-label{margin-bottom:2px}.answer-summary{margin-top:14px;font-family:Charter,'Bitstream Charter','Sitka Text',Cambria,Georgia,serif;font-size:16.5px;line-height:1.6;background:var(--soft);border-radius:6px;padding:4px 16px}.qblock ul{margin:4px 0}
article h2{position:relative}
h1 .kind{display:block;font-size:15px;font-weight:700;letter-spacing:.02em;margin-bottom:2px}
h1 .kind .ico{width:15px;height:15px;vertical-align:-2px;margin-right:5px}
h1 .pills,.qhead .pills{font-size:0;margin-left:8px;vertical-align:middle;white-space:normal}
h1 .pills .pill,.qhead .pills .pill{font-size:11px;font-weight:400;margin-right:4px}
.k-experiment{color:#333}.k-premise{color:#6a4c93}.k-question{color:#1f77b4}.k-hypothesis{color:#a23c9e}.k-step{color:#2a7f62}
.k-result{color:#8c564b}.k-conclusion{color:#c0392b}.k-decision{color:#6b6b6b}.k-figure{color:#17818a}
.k-artefact{color:#966d09}.k-caveat{color:#c64f00}.k-term,.k-reference,.k-page{color:#556}.k-resource{color:#5b6b2f}.k-term{color:#5f6b7a}.k-reference{color:#3d5a80}
a.fullname,span.fullname{font-weight:700;margin-right:6px;white-space:nowrap}.fullname>.ico{width:1em;height:1em;vertical-align:-.15em;margin-right:4px}
.fullname .tag{margin-left:2px}a.fullname:hover{text-decoration:none;filter:brightness(1.2)}
h1 .kind .tag .ico{width:1.05em;height:1.05em;vertical-align:-.17em;margin-right:4px}
.qblock h3{font-size:14px;margin:14px 0 4px;color:var(--fg)}
table.resource-facts{width:100%;margin:10px 0 14px}table.resource-facts th{text-align:left;padding-right:14px;color:var(--muted);font-weight:600;width:190px;background:var(--soft)}table.resource-facts td{white-space:normal}table.resource-facts td.missing{color:#aa3333}table.resource-facts code{word-break:break-all}
table.status-table{display:table;width:100%}table.status-table td{white-space:normal}
tr.st-good td:first-child{background:linear-gradient(#2e9e5b,#2e9e5b) left/4px 100% no-repeat}tr.st-bad td:first-child{background:linear-gradient(#5f2120,#5f2120) left/4px 100% no-repeat}tr.st-mid td:first-child{background:linear-gradient(#e0a030,#e0a030) left/4px 100% no-repeat}tr[class^=st-] td:first-child{padding-left:14px}
a.term{color:inherit;border-bottom:1px dotted #8a94a6}a.term:hover{text-decoration:none;background:#f1f3f7}
.pill{display:inline-block;font-size:11px;line-height:1.5;border:1px solid var(--line);border-radius:10px;padding:0 8px;color:var(--muted);vertical-align:middle}
.s-supported,.s-done,.s-answered,.s-current,.s-active{border-color:var(--ok);color:var(--ok)}
.cert-high{border-color:var(--ok);color:var(--ok)}.cert-moderate{border-color:#5b6475;color:#3b4252}.cert-low,.cert-very_low{border-color:var(--amber);color:var(--amber)}.prediction{margin:10px 0 4px;padding:8px 12px;border:1px solid var(--line);border-left:4px solid var(--kc);border-radius:4px;background:#fbfbfd}.prediction dt{font:700 11.5px system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#6b7488;margin-top:4px}.prediction dd{margin:0 0 4px 0;font-family:Charter,'Bitstream Charter','Sitka Text',Cambria,Georgia,serif;font-size:16px}.s-not_supported,.s-deprecated,.s-dropped,.s-superseded{border-color:var(--warn);color:var(--warn)}
.s-exploratory,.s-in_progress,.s-planned,.s-open,.s-inconclusive,.s-assumed,.s-questioned,.s-under_review{border-color:var(--amber);color:var(--amber)}
.s-addressed{border-color:var(--ok);color:var(--ok)}
.s-frozen,.s-implement-requested,.s-implementing{border-color:#c0392b;color:#c0392b}.s-collecting,.s-harvest-requested{border-color:var(--accent);color:var(--accent)}.s-harvested{border-color:#2e9e5b;color:#1e6e3e}.pill.s-waiting{background:#fff3c4;border-color:#b08800;color:#6b5000;font-weight:600}.pill.s-approved{border-color:#2e9e5b;color:#1e6e3e}.pill.s-recheck{background:#fdecea;border-color:#b3261e;color:#8c1d18;font-weight:600}.route{display:flex;flex-wrap:wrap;align-items:center;gap:6px 4px;margin:10px 0 14px;padding:12px 14px;background:var(--soft);border-radius:8px}.route-arrow{display:inline-flex;flex-direction:column;align-items:center;font-size:18px;color:var(--muted);line-height:1;padding:0 4px}.route-arrow span{font:600 10.5px system-ui,sans-serif;letter-spacing:.03em;color:var(--muted);margin-bottom:2px}.route-side td{white-space:normal}ol.route-steps li{margin:4px 0}
.stab-flux{border-color:#f0a020;color:#8a5a00;background:#fff7e6}.stab-steady{color:var(--muted)}
.stab-settled{border-color:var(--ok);color:var(--ok);background:#eefaf2}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin:0 6px 0 2px;vertical-align:middle;background:#c5cad3}
.dot.stab-flux{background:#f0a020}.dot.stab-settled{background:#2e9e5b}
.callout{border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:6px;padding:4px 12px;margin:12px 0;background:var(--soft)}
.callout-warning,.callout-caution,.callout-caveat{border-left-color:#c64f00;background:#fff6ef}
.callout-important,.callout-danger{border-left-color:var(--warn)}.callout-tip,.callout-success{border-left-color:var(--ok)}
.short{background:var(--soft);border-left:4px solid var(--accent);padding:8px 12px;margin:8px 0 16px;font-size:15px}
blockquote{margin:12px 0;padding:10px 14px;background:#fff8f0;border:1px solid #f0d9bf;border-radius:6px}
table{border-collapse:collapse;margin:10px 0;font-size:13.5px;display:block;overflow-x:auto;max-width:100%}
th,td{border:1px solid var(--line);padding:3px 8px;text-align:left;vertical-align:top;white-space:nowrap}
article td{white-space:normal}th{background:var(--soft)}
code{font-size:13px;background:var(--soft);padding:0 3px;border-radius:3px;overflow-wrap:anywhere}
main{overflow-wrap:break-word}
pre{background:var(--soft);padding:10px;overflow-x:auto;font-size:12.5px;line-height:1.45}
a.ref{border-bottom:1px dotted var(--accent)}a.ref:hover{text-decoration:none;background:#eef3fb}
.ref-missing{color:var(--muted);border-bottom:1px dashed var(--muted);cursor:help}
.ref-broken{color:#fff;background:var(--warn);padding:0 3px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:10px;margin:8px 0}
.card{border:1px solid var(--line);border-radius:8px;padding:9px 12px;background:#fff}
.card .ct{font-weight:600;font-size:14.5px;line-height:1.35}.card .cs{font-size:13.5px;color:var(--muted);margin-top:4px}
.rel{font-size:14px}.rel dt{font-weight:600;margin-top:6px}.rel dd{margin:2px 0 2px 16px}
.box{border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:14px 0;background:var(--soft);font-size:14px}
.help{color:var(--muted);font-size:13px}
figure{margin:12px 0}figure img{max-width:100%;border:1px solid var(--line);border-radius:4px;background:#fff}
figcaption{font-size:13.5px;color:#333;margin-top:6px}
.alias-name{color:#5a6270}
ul.chips{list-style:none;padding:0;margin:6px 0}ul.chips li{margin:4px 0}ul.chips .cell-note{display:block;margin:1px 0 0 2px}details.provenance>summary{cursor:pointer;list-style:revert}details.provenance>summary h2{display:inline;margin-right:10px}details.provenance h3{font-size:14px;margin:14px 0 4px;color:#5a6270}
.data-chip{display:inline-flex;align-items:center;gap:3px;font:500 12px/1.3 system-ui,sans-serif;padding:0 7px 0 5px;border:1px solid var(--line);border-radius:9px;background:#f6f7f9;color:#5a4a10;text-decoration:none;white-space:nowrap;vertical-align:1px}.data-chip .ico{width:12px;height:12px}
figure.featured{margin:14px 0 18px}figure.featured img{width:100%;display:block}figure.featured figcaption{font-size:14px}.fig-head{display:block;font-weight:600;color:var(--fg,#1d2330)}figure.featured details{margin-top:6px}figure.featured summary{cursor:pointer;color:#5a6270;font-size:13px}
.figure-strip{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0 16px}.strip-item{flex:0 1 220px;text-decoration:none;color:inherit;font-size:12.5px}.strip-item img{width:100%;border:1px solid var(--line);border-radius:4px;background:#fff;display:block;margin-bottom:4px}
.thumb{display:grid;grid-template-columns:minmax(0,300px) 1fr;gap:14px;align-items:start;margin:12px 0;
padding-bottom:10px;border-bottom:1px solid var(--line)}
.thumb img{width:100%;border:1px solid var(--line);border-radius:4px}.thumb figcaption{margin-top:4px}
details.tree summary{cursor:pointer}details.tree{margin-left:14px}ul.tree{list-style:none;padding-left:14px;margin:2px 0}
.diff .add{color:#116329;background:#e6ffec;display:block}.diff .del{color:#82071e;background:#ffebe9;display:block}
.diff .hunk{color:#6e7781;display:block}.diff .ctx{display:block}
.code-table td.linenos{color:#9aa1ad;text-align:right;user-select:none;padding-right:8px}
.code-table pre{margin:0;background:none;padding:0}.code-wrap{overflow-x:auto;background:var(--soft);padding:8px;border-radius:6px}
.code-table{border:0;display:table}.code-table td{border:0;padding:0 6px}
.hll{background:#fff3b0}
@media (max-width:640px){main{padding:10px 14px 50px}.thumb{grid-template-columns:1fr}h1{font-size:21px}}
/* small screens: each row of a page table becomes a card (page and status on one line, the summary under it) */
@media (max-width:640px){
table.nodes,table.nodes tbody{display:block;border:0;margin:8px 0 4px}table.nodes colgroup,table.nodes tr:has(th){display:none}
table.nodes tr{display:block;border:1px solid var(--line);border-left:4px solid var(--line);border-radius:7px;padding:7px 10px;margin:0 0 7px;background:#fff}
table.nodes td,table.nodes tr[class^=st-] td:first-child{display:block;border:0;padding:0;background:none!important;text-align:left!important}
table.nodes td:first-child .m-status{display:inline;margin-left:6px}table.nodes td:first-child .m-status .pill{margin:0 3px 0 0;vertical-align:1px}
table.nodes td:first-child .tagline,table.nodes td:first-child .tl-text{display:inline}
table.nodes td:nth-child(2){font-size:14px;color:#3b4252;margin-top:3px}table.nodes td:nth-child(2):empty{display:none}
table.nodes tr:has(.m-status) td:last-child{display:none}
table.nodes tr.st-good{border-left-color:#2e9e5b}table.nodes tr.st-bad{border-left-color:#5f2120}table.nodes tr.st-mid{border-left-color:#e0a030}}
/* the sections after a page's text as tabs hanging from the separator (pages.tab_strip, _assets/kea.js): the open
   tab in the type's colour and hanging lower, the others pale; without scripts (and in print) every panel shows */
.node-data-sep span.sep-tabs{display:flex;flex-wrap:wrap;justify-content:flex-end;align-items:flex-start;gap:3px;margin-left:auto;background:none;padding:0;border-radius:0;letter-spacing:0;text-transform:none;line-height:0}
.node-data-sep .sep-tab{border:0;cursor:pointer;margin:0;padding:3px 12px 4px;border-radius:0 0 6px 6px;font:700 11.5px/1.3 system-ui,sans-serif;letter-spacing:.12em;text-transform:uppercase;white-space:nowrap;background:color-mix(in srgb,var(--kc,#556) 13%,#fff);color:color-mix(in srgb,var(--kc,#556) 85%,#000);transition:background .12s}
.node-data-sep .sep-tab:hover{background:color-mix(in srgb,var(--kc,#556) 26%,#fff)}
.node-data-sep .sep-tab:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.node-data-sep .sep-tab.on{background:var(--kc,#556);color:#fff;padding-bottom:8px;cursor:default}
.node-data-sep .sep-tab span.tab-count{display:inline-block;margin-left:7px;padding:0 6px;border-radius:8px;font:600 10.5px/1.5 system-ui,sans-serif;letter-spacing:0;background:color-mix(in srgb,var(--kc,#556) 22%,#fff);color:inherit}
.node-data-sep .sep-tab.on span.tab-count{background:#fff3;color:#fff}
/* progress.html (pages.progress_page): what waits for whom, the route of each question, the sign-offs */
.progress-table{display:table;width:100%;border-collapse:collapse;font-size:14px;margin:6px 0 4px}.progress-table th,.progress-table td{text-align:left;vertical-align:top;padding:7px 9px;border-bottom:1px solid var(--line)}
.progress-table th{font:600 12px system-ui,sans-serif;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
.progress-table.route td.rq{min-width:220px}.progress-table .rs{display:inline-block;white-space:nowrap;font:600 12.5px system-ui,sans-serif;border-radius:10px;padding:1px 8px}
.rs-done .rs,.rs.rs-done{color:#1e5e22;background:#e3f2e5}.rs-you .rs,.rs.rs-you{color:#6d4a00;background:#fff0c7;box-shadow:inset 0 0 0 1px #e8c15a}
.rs-agent .rs,.rs.rs-agent{color:#163f73;background:#e2ecf8}.rs-running .rs,.rs.rs-running{color:#163f73;background:#cfe0f5}.rs-later .rs,.rs-closed .rs,.rs-free .rs{color:#8a93a3;background:none;font-weight:500}
.rs-pages{margin-top:4px;display:flex;flex-wrap:wrap;gap:3px}.rs-pages .tag{font-size:11.5px}
h2 .count{font:600 12px system-ui,sans-serif;color:var(--muted);background:var(--soft);border-radius:9px;padding:1px 8px;vertical-align:2px}
.progress-table th,.progress-table td{background:none}.progress-live{margin:14px 0 6px}.progress-live .fb-session{margin:0 0 8px}.progress-live table{margin-top:4px}
.route-note{margin:4px 0 8px}.scroll{overflow-x:auto;max-width:100%}.progress-table td,.progress-table td a{white-space:normal}.progress-table td.rq{width:55%}
@media (max-width:640px){.progress-table:not(.route) thead{display:none}
 .progress-table:not(.route),.progress-table:not(.route) tbody,.progress-table:not(.route) tr,.progress-table:not(.route) td{display:block;width:auto}
 .progress-table:not(.route) tr{border:1px solid var(--line);border-radius:7px;padding:6px 10px;margin:0 0 7px}
 .progress-table:not(.route) td{border:0;padding:2px 0}.progress-table:not(.route) td:empty{display:none}
 .progress-table.route td.rq{min-width:180px}}
.node-data-sep .sep-tab span.tab-long,.node-data-sep .sep-tab span.tab-short{display:inline;padding:0;background:none;border-radius:0;font:inherit;letter-spacing:inherit;color:inherit;text-transform:inherit}.node-data-sep .sep-tab span.tab-short{display:none}
@media (max-width:640px){.node-data-sep .sep-tab span.tab-long{display:none}.node-data-sep .sep-tab span.tab-short{display:inline}
 .node-data-sep .sep-tabs .sep-tab{letter-spacing:.03em;padding:3px 7px 4px;font-size:11px}.node-data-sep .sep-tabs .sep-tab.on{padding-bottom:7px}
 .node-data-sep span.sep-tabs{min-width:0;max-width:100%;overflow-x:auto;scrollbar-width:none}.node-data-sep span.sep-tabs::-webkit-scrollbar{display:none}
 .node-data-sep span.sep-tabs{flex-wrap:nowrap;gap:2px}.node-data-sep .sep-tab span.tab-count{margin-left:5px;padding:0 5px}
 .node-data-sep{margin-top:40px}}
.pid-line{display:flex;justify-content:flex-end;margin:0 0 4px}.pid-line .pid{font:400 11.5px/1.3 system-ui,sans-serif;color:#7a8394;margin:0}.pid-line .pid a{color:#7a8394;text-decoration:none;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;cursor:copy}.pid-line .pid a:hover{color:var(--accent);text-decoration:underline}.pid-line .pid a.copied{color:#1e6e3e}@media (max-width:640px){.node-data-sep .sep-tab{letter-spacing:.05em;padding:3px 8px 4px}.node-data-sep .sep-tab.on{padding-bottom:7px}}.tab-sep{margin-bottom:0}.tab-panel>.fb-static{margin-top:0;padding-top:0;border-top:0}.tab-panels{margin:12px 0 0}.js .tab-panel:not(.on){display:none}
.tab-panel>section.about:first-child h2,.tab-panel>section:first-child>h2:first-child{margin-top:6px}
.js table.nodes tr.pg-off{display:none!important}.kind-filter{margin:8px 0 2px}
@media print{.js .tab-panel:not(.on){display:block}.sep-tab:not(.on){display:none}.tab-panel:not(.on)::before{content:attr(data-label);display:block;font:700 12px system-ui,sans-serif;text-transform:uppercase;letter-spacing:.1em;border-top:3px solid var(--kc,#556);margin-top:24px;padding-top:4px}.obj-pager,.kind-filter{display:none}.js table.nodes tr.pg-off{display:table-row!important}}
"""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def prefix_for(page: str) -> str:
    """Relative prefix from a page path (relative to the site root) back to the root."""
    return "../" * page.count("/")


def node_href(node: Node, prefix: str) -> str:
    return f"{prefix}{node.url}"


def type_badge(node: Node) -> str:
    """The page type in full, not a link: the word in the type's colour, then the tag (icon and number)."""
    return f"<span class='fullname k-{esc(node.type)}'>{fullname_inner(node)}</span>"


def fullname_inner(node: Node) -> str:
    """'Question' as coloured text followed by the tag [icon Q1]: the tag always looks the same, with or without
    the word in front. Pages without a number show the word and the icon."""
    word = esc(TYPE_LABELS.get(node.type, node.type))
    if node.tag:
        return f"{word} <span class='tag t-{esc(node.type)}'>{icons.svg(node.type)}{esc(node.tag)}</span>"
    return f"{icons.svg(node.type)}{word}"


def status_pill(node: Node) -> str:
    """The status, and "exploratory" when the analysis was chosen after seeing earlier results (analysis:)."""
    from kea.docsite.nodes import analysis_of
    html = (f"<span class='pill s-{esc(node.status)}'>{esc(str(node.status).replace('_', ' '))}</span>"
            if node.status and node.status != "exploratory" else "")
    if analysis_of(node) == "exploratory":
        html += (" " if html else "") + ("<span class='pill s-exploratory' title='Exploratory: the analysis was chosen "
                                         "after earlier results were seen; it suggests, and needs new data to confirm'>"
                                         "exploratory</span>")
    if node.waiting:                 # pace: guided, the owner has not approved it yet (graph.py)
        html += (" " if html else "") + ("<span class='pill s-waiting' title='Waiting for approval: the next step "
                                         "builds on this page only after the owner approves it (Approve in the page "
                                         "menu)'>waiting for approval</span>")
    elif node.header.get("approved"):
        html += (" " if html else "") + "<span class='pill s-approved' title='Approved by the owner'>approved</span>"
    if node.recheck:                 # an upstream page changed; the agent has not yet rechecked this one (graph.py)
        html += (" " if html else "") + (f"<span class='pill s-recheck' title='To recheck: {esc('; '.join(node.recheck))}. "
                                         "A page it rests on changed after it was last checked; until Claude rechecks "
                                         "it, treat it as possibly affected'>recheck</span>")
    return html


CERTAINTY_TEXT = {"high": "high certainty", "moderate": "moderate certainty", "low": "low certainty",
                  "very_low": "very low certainty"}
CAVEAT_KIND_TEXT = {"internal": "internal validity", "external": "external validity (generalisation)",
                    "construct": "construct validity (what is measured)", "statistical": "statistical conclusion validity",
                    "other": "other limit"}


def detail_pills(node: Node) -> str:
    """Pills on a page's own kind row: the certainty of a conclusion, the kind of a caveat."""
    certainty = str(node.header.get("certainty") or "")
    html = ""
    if node.type == "conclusion" and certainty in CERTAINTY_TEXT:
        reason = str(node.header.get("certainty_because") or "")
        html += (f" <span class='pill cert-{esc(certainty)}' title='How sure we are of this conclusion"
                 f"{(': ' + esc(reason)) if reason else ''}'>{CERTAINTY_TEXT[certainty]}</span>")
    kind = str(node.header.get("kind") or "")
    if node.type == "caveat" and kind in CAVEAT_KIND_TEXT:
        html += f" <span class='pill' title='The kind of limit (threat to validity)'>{CAVEAT_KIND_TEXT[kind]}</span>"
    return html


def hover_text(node: Node, note: str | None = None) -> str:
    hover = f"{node.number + ' · ' if node.number else ''}{node.title} — {node.short}"
    return hover + (f" | {note}" if note else "")


def tag_inner(node: Node, from_project: str | None = None) -> str:
    project_part = f"{node.project}: " if from_project and node.project != from_project else ""
    return f"{icons.svg(node.type)}{esc(project_part + (node.tag or node.title))}"


def node_link(node: Node, prefix: str, text: str | None = None, note: str | None = None,
              from_project: str | None = None) -> str:
    """A link to a node; the hover shows number, title and short (plus an optional note).

    Link rules (the same everywhere): a numbered page is linked by its tag (a coloured button with the type's icon
    and the number, Q1, C2). Text given with the link ([[id|text]]) stays plain text, followed by the tag; only
    the tag is the link. A reference's pill holds its author and year ("Akiyama et al. 1994"), or the text given
    with the link ([[ref-x|Lloyd 2024, p.7]]). Pages without a pill (the experiment home, pages) are linked by text.
    """
    if node.type == "reference" and not node.number and text:
        project_part = f"{node.project}: " if from_project and node.project != from_project else ""
        return (f"<a class='tag t-reference' href='{esc(node_href(node, prefix))}' "
                f"title='{esc(hover_text(node, note))}'>{icons.svg(node.type)}{esc(project_part + text)}</a>")
    if node.tag:
        anchor = (f"<a class='tag t-{esc(node.type)}' href='{esc(node_href(node, prefix))}' "
                  f"title='{esc(hover_text(node, note))}'>{tag_inner(node, from_project)}</a>")
        return f"{esc(text)} {anchor}" if text else anchor
    project_part = f"{node.project}: " if from_project and node.project != from_project else ""
    label = text if text else f"{project_part}{node.title}"
    return f"<a class='ref' href='{esc(node_href(node, prefix))}' title='{esc(hover_text(node, note))}'>{esc(label)}</a>"


TYPE_COLOURS = {"experiment": "#333", "premise": "#6a4c93", "question": "#1f77b4", "hypothesis": "#a23c9e", "step": "#2a7f62",
                "result": "#8c564b", "conclusion": "#c0392b", "decision": "#757575", "figure": "#17818a",
                "artefact": "#966d09", "caveat": "#c64f00", "page": "#556", "resource": "#5b6b2f",
                "term": "#5f6b7a", "reference": "#3d5a80"}   # as .t-<type> in CSS


# The kinds of link shown about a page (site: "About this page"; PDF: the lines under a section), in the order a
# reader checks a claim: evidence for and against, what limits it, how it was made, what it builds on and uses it.
ABOUT_ORDER = ["Answered by", "Answers", "Tested by", "Tests", "Supported by", "Opposed by", "Supports", "Opposes",
               "Limited by", "Limits", "Addressed by", "Addresses",
               "Made by", "Makes", "Shown in", "Shows", "From", "Used in", "Made from", "Used to make", "Uses",
               "Decided in", "Applies to",
               "Builds on", "Used by", "Supersedes", "Superseded by", "Cites", "Cited by", "Part of", "Contains"]


def linked_kinds(members: list) -> str:
    """'this step', 'these steps', 'these steps and results': what a link heading points to."""
    types = list(dict.fromkeys(member.type for member in members))
    if len(members) == 1:
        return "this " + TYPE_LABELS.get(types[0], types[0]).lower()
    words = [TYPE_PLURALS.get(kind, kind).lower() for kind in types]
    return "these " + (words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1])


def full_kind(node: Node) -> str:
    """'Question Q1': the page's kind and number in full."""
    return f"{TYPE_LABELS.get(node.type, node.type)}{' ' + node.number if node.number else ''}"


def fullname_link(node: Node, prefix: str) -> str:
    """'Question Q1' in the type's colour, as a link (headings of question blocks)."""
    return (f"<a class='fullname k-{esc(node.type)}' href='{esc(node_href(node, prefix))}' "
            f"title='{esc(hover_text(node))}'>{fullname_inner(node)}</a>")


GOOD_STATUSES = {"supported", "done", "answered", "current", "active", "addressed"}
BAD_STATUSES = {"not_supported", "deprecated", "dropped", "superseded"}


def status_row_class(node: Node) -> str:
    """Status bar on the left of a table row: green supported/settled, amber open or exploratory, dark red rejected
    or deprecated (darker than the conclusion red, so a conclusion is not read as rejected)."""
    from kea.docsite.nodes import analysis_of
    status = str(node.status or "")
    if status in BAD_STATUSES:
        return "st-bad"
    if node.recheck:
        return "st-mid"
    if analysis_of(node) == "exploratory":          # supported, but only by an analysis chosen after the fact
        return "st-mid"
    return "st-good" if status in GOOD_STATUSES else "st-mid" if status else ""


def tagline(node: Node, prefix: str, text: str | None = None, from_project: str | None = None,
            full: bool = False) -> str:
    """Tag plus one line (the title by default) as ONE link: for lists of pages. `full` writes the kind in front of
    the tag, in its colour ("Conclusion [C1]"); the tag itself always holds the icon and the number only."""
    words = node.tag_title if text is None else text
    if not node.tag:
        return node_link(node, prefix, words, from_project=from_project)
    kind = (f"<span class='kindword k-{esc(node.type)}'>{esc(TYPE_LABELS.get(node.type, node.type))}</span> "
            if full else "")
    return (f"<a class='tagline' href='{esc(node_href(node, prefix))}' title='{esc(hover_text(node))}'>{kind}"
            f"<span class='tag t-{esc(node.type)}'>{tag_inner(node, from_project)}</span>"
            f"<span class='tl-text'>{esc(words)}</span></a>")


def card(node: Node, prefix: str) -> str:
    return (f"<div class='card'><div class='ct'>{tagline(node, prefix)} {status_pill(node)}</div>"
            f"<div class='cs'>{esc(node.short)}</div></div>")


PDF: dict | None = None          # the PDF of all pages ({"file", "version", "commit", "built"}), set by the build


def topbar(prefix: str, project: str | None = None, tree: Tree | None = None, node: Node | None = None,
           here: str | None = None) -> str:
    """Menu bar. Left: the kea head (home) / project / experiment / [tag] page title. Right: the menu, the page
    tools, then after a bar the reader: "Help" on a static site; the signed-in name with a small menu (my comments,
    help, sign out) when the comment server knows the reader (filled in by cycle.js). When space runs out
    (TOPBAR_JS), in this order: the menu folds into a menu button, the project name goes, the experiment goes, and
    finally the page title is cut from the right; the page title is what stays longest."""
    segments = [f"<a class='home' href='{home_href(prefix)}' title='Home of this site'><img src='{prefix}_assets/kea-head-64.png' "
                f"srcset='{prefix}_assets/kea-head-128.png 2x' alt='Home' width='24' height='24'></a>",
                f"<span class='seg project'><span class='sep'>/</span><a class='project' href='{home_href(prefix)}'>"
                f"{esc(SITE_TITLE)}</a></span>"]
    right = []
    if project and tree and project in tree.projects:
        home = tree.projects[project]
        if not SOLE_PROJECT:           # one experiment: the project title is its link, no level of its own
            segments.append(f"<span class='seg experiment-seg'><span class='sep'>/</span><a class='experiment' "
                            f"href='{prefix}{project}/home.html' title='{esc(home.title)}'>{esc(project)}</a></span>")
        if node is not None and node.id != "home":
            badge = (f"<span class='tag t-{esc(node.type)}'>{tag_inner(node)}</span>" if node.tag else
                     f"<span class='tag t-{esc(node.type)}'>{icons.svg(node.type)}"
                     f"{esc(TYPE_LABELS.get(node.type, node.type))}</span>")
            segments.append(f"<span class='seg here'><span class='sep'>/</span>{badge}"
                            f"<span class='here-title' title='{esc(node.title)}'>{esc(node.tag_title)}</span></span>")
    if here:
        segments.append(f"<span class='seg here'><span class='sep'>/</span><span class='here-title'>{esc(here)}</span></span>")
    # Four entries: Map, Plan, History, PDF (Help is the kea logo). Map and History are groups whose own pages
    # unfold next to them in the bar while the reader is on one of them (TOPBAR_JS marks the current link):
    #   Map: Relations, Objects (all pages by type), Resources, Terms, References (Objects filtered), Data files, Code
    #   Plan: the plan of the current review cycle (what readers act on: harvest, implement), Current comments
    #   History: what changed per session (the group's own page), Review cycles, Comments
    # Map, Relations and Objects open the current experiment's pages, the only experiment's on a site with one.
    experiments = list(tree.projects) if tree else []
    target = project if project and tree and project in tree.projects else (experiments[0] if len(experiments) == 1
                                                                            else None)
    from kea.docsite import mode

    def link(label: str, href: str | None, title: str = "") -> str:
        return (f"<a href='{prefix}{href}'{f' title={chr(39)}{esc(title)}{chr(39)}' if title else ''}>{label}</a>" if href else
                f"<span class='off' title='Open an experiment first: each has its own {label.lower()}'>{label}</span>")

    def group(head: str, members: list[str]) -> str:
        return f"<span class='grp'>{head}<span class='sub'>{''.join(members)}</span></span>"

    def listed(kind: str, label: str, title: str) -> str:
        return link(label, f"{target}/objects.html#type={kind}" if target else None, title)

    right.append(group(link("Map", f"{target}/map.html" if target else None, "The experiment as a tree"), [
        link("Relations", f"{target}/relations.html" if target else None, "The graph of relations"),
        link("Objects", f"{target}/objects.html" if target else None, "Every page of the experiment, by type"),
        listed("resource", "Resources", "What the analysis takes from outside: data sources, databases, tools (O1, O2 …)"),
        listed("term", "Terms", "The words this experiment defines"),
        listed("reference", "References", "The literature cited"),
        link("Data files", "data.html", "Every data file the pages refer to, with size, checksum and download"),
        link("Code", "code/index.html", "The analysis code, file by file")]))
    history_members = [] if mode.MODE == "public" else [
        link("Review cycles", "history.html", "Each release with its comments, plan items and commits"),
        link("Comments", "feedback.html", "All comments on the site")]
    if mode.MODE != "public":
        waiting = 0
        if tree is not None:
            if "_waiting_count" not in tree.__dict__:
                from kea.docsite import graph
                tree.__dict__["_waiting_count"] = sum(1 for item in tree.nodes.values()
                                                      if item.waiting or graph.go_action(tree, item))
            waiting = tree.__dict__["_waiting_count"]
        right.append(link("Progress" + (f" <span class='nav-count'>{waiting}</span>" if waiting else ""),
                          "progress.html", "What waits for whom, and where each question stands"
                          + (f": {waiting} page(s) wait for a click" if waiting else "")))
        right.append(group(link("Plan", "plan.html", "The plan of the current review cycle: what the next run does"),
                           [link("Current comments", "comments.html", "Who commented what, and where: open and "
                                 "planned comments, by person")]))
    if mode.WITH_CHANGELOG or history_members:
        head = (link("History", "changes/index.html", "What changed, per working session") if mode.WITH_CHANGELOG
                else link("History", "history.html"))
        right.append(group(head, history_members if mode.WITH_CHANGELOG else history_members[1:]))
    if PDF:
        made = f"version {esc(PDF['version'])}, commit {esc(PDF['commit'])}, made {esc(PDF['built'])}"
        head = f"<a href='{prefix}{esc(PDF['file'])}' title='The analysis as one PDF to read: {made}'>PDF</a>"
        if PDF.get("complete"):
            right.append(group(head, [link("With all records", PDF["complete"], "The same PDF with the records at "
                                           "the end: overview tables, hypotheses in full, data and resources, figure "
                                           "files")]))
        else:
            right.append(head)
    return (f"<nav class='topbar not-annotatable'><div class='trail'>{''.join(segments)}</div>"
            f"<button class='menu-button' aria-label='menu' hidden>&#9776;</button>"
            f"<div class='links'>{''.join(right)}</div><span class='page-tools'></span>"
            f"<span class='user' data-help='{prefix}help.html' data-comments='{prefix}feedback.html' {version_data()}>"
            f"<a href='{prefix}help.html' title='How to read this site, and about Kea. {esc(version_words())}'>Help</a></span>"
            f"</nav><script>{TOPBAR_JS}</script>")


def version_words() -> str:
    """'Built with Kea X; site version Y': on the Help link's hover, and in the reader's menu (cycle.js)."""
    from kea import __version__
    return f"Built with Kea {__version__}" + (f"; site version {PDF['version']}" if PDF and PDF.get("version") else "")


def version_data() -> str:
    """The versions as data on the reader's slot in the menu bar: cycle.js shows them in the reader's menu, with the
    comment server's or hub's Kea from /api/status (not in the bar itself: rarely needed)."""
    from kea import __version__
    site = PDF.get("version", "") if PDF else ""
    return f"data-kea='{esc(__version__)}'" + (f" data-site-version='{esc(site)}'" if site else "")


# Fold in steps until the page title has room: 1 menu into the button, 2 project, 3 experiment; the title
# is then cut with an ellipsis. A title counts as cramped when it is cut and narrower than ROOM pixels (so a very
# long title on a wide screen does not fold everything); pages without a title fold when the trail overflows.
TOPBAR_JS = """(function(){var nav=document.currentScript.previousElementSibling;var button=nav.querySelector('.menu-button');
var STEPS=['folded','no-project','no-experiment'];var ROOM=[520,380,380];
function cramped(step){var trail=nav.querySelector('.trail');var title=nav.querySelector('.here-title');
if(title){return title.scrollWidth>title.clientWidth+1&&title.clientWidth<ROOM[Math.min(step,2)];}
return trail.scrollWidth>trail.clientWidth+1;}
function fit(){nav.classList.remove('open');STEPS.forEach(function(name){nav.classList.remove(name);});button.hidden=true;
var links=nav.querySelector('.links');var step=0;
while(step<STEPS.length&&(cramped(step)||(step===0&&links.scrollWidth>links.clientWidth+1))){
nav.classList.add(STEPS[step]);if(step===0){button.hidden=false;}step++;}}
button.addEventListener('click',function(){nav.classList.toggle('open');});
document.addEventListener('click',function(event){if(nav.classList.contains('open')&&!nav.querySelector('.links').contains(event.target)&&!button.contains(event.target))nav.classList.remove('open');});
document.addEventListener('click',function(event){var tab=event.target.closest&&event.target.closest('button.media-tab');if(tab){var sep=tab.closest('.media-sep');var panels=sep.nextElementSibling;sep.querySelectorAll('.media-tab').forEach(function(b){b.classList.toggle('on',b===tab)});panels.querySelectorAll('.media-panel').forEach(function(panel){panel.hidden=panel.dataset.tab!==tab.dataset.tab});}});
document.addEventListener('click',function(event){var link=event.target.closest&&event.target.closest('a.pid-copy');
if(!link||event.ctrlKey||event.metaKey||event.shiftKey||event.button!==0)return;event.preventDefault();
var url=link.href,shown=link.textContent;function done(){link.classList.add('copied');link.textContent='copied';
setTimeout(function(){link.textContent=shown;link.classList.remove('copied');},1200);}
function fallback(){var box=document.createElement('textarea');box.value=url;box.style.position='fixed';box.style.opacity='0';
document.body.appendChild(box);box.select();try{document.execCommand('copy');done();}catch(error){}box.remove();}
if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(url).then(done,fallback);}else{fallback();}});
function mark(){var here=location.href.split('#')[0].split('?')[0];var links=[].slice.call(nav.querySelectorAll('.links a'));
links.forEach(function(a){a.classList.remove('cur');});
var exact=links.filter(function(a){return a.href.indexOf('#')>0&&a.href===here+location.hash;});
(exact.length?exact:links.filter(function(a){return a.href.indexOf('#')<0&&a.href.split('?')[0]===here;})).forEach(function(a){a.classList.add('cur');
for(var g=a.parentElement;g&&g!==nav;g=g.parentElement){if(g.classList.contains('grp'))g.classList.add('open');}});}
mark();window.addEventListener('hashchange',mark);
window.addEventListener('resize',fit);if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',fit);}else{fit();}
window.keaFitTopbar=fit;})();"""


SOLE_PROJECT = ""      # the experiment, when the project has only one: the site starts at its page (pages.py)


def home_href(prefix: str) -> str:
    """The site's start: the project page, or with one experiment that experiment's page."""
    return f"{prefix}{SOLE_PROJECT}/home.html" if SOLE_PROJECT else f"{prefix}index.html"


def crumbs(trail: list[tuple[str, str | None]], prefix: str) -> str:
    """Breadcrumbs; every trail starts at Start (the site home)."""
    parts = [f"<a href='{home_href(prefix)}'>Start</a>"]
    for text, href in trail:
        parts.append(f"<a href='{esc(href)}'>{esc(text)}</a>" if href else esc(text))
    return f"<nav class='crumbs not-annotatable'>{' › '.join(parts)}</nav>"


def font_faces(prefix: str) -> str:
    """@font-face rules for Kea's typewriter face (IBM Plex Mono, SIL OFL, in _assets/: the site makes no outside
    requests); relative to the page, so the CSS itself stays the same on every page."""
    faces = (("400-normal", 400, "normal"), ("400-italic", 400, "italic"), ("600-normal", 600, "normal"))
    return "".join(f"@font-face{{font-family:'Kea Mono';src:url('{prefix}_assets/plex-mono-latin-{name}.woff2') "
                   f"format('woff2');font-weight:{weight};font-style:{style};font-display:swap}}"
                   for name, weight, style in faces)


def page(title: str, body: str, prefix: str, project: str | None = None, tree: Tree | None = None,
         node: Node | None = None, here: str | None = None, wide: bool = False) -> str:
    """A whole HTML page. ``wide``: a wider column for tables and grids (history, commit diffs)."""
    main = "<main class='wide'>" if wide else "<main>"
    # a page of the graph gets a fat bar in its type's colour along the left edge, with the kind written in it
    kind_label = full_kind(node) if node is not None else ""
    kindbar = (f"<div class='kindbar t-{esc(node.type)}' aria-hidden='true'>{icons.svg(node.type)}<span>{esc(kind_label)}</span></div>"
               if node is not None else "")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(title)}</title>"
            f"<link rel='icon' href='{prefix}_assets/kea-badge.ico'>"
            f"<style>{font_faces(prefix)}{CSS}</style><script defer src='{prefix}_assets/kea.js'></script>"
            f"<script>document.documentElement.classList.add('js')</script></head><body{' class=has-kindbar' if kindbar else ''}>{kindbar}"
            f"{topbar(prefix, project, tree, node, here)}{main}{body}</main></body></html>")


class LinkContext:
    """What link rendering needs: the tree, the current project and page prefix, code and data resolvers."""

    def __init__(self, tree: Tree, project: str, prefix: str, code_href, data_href, current: str | None = None):
        self.tree, self.project, self.prefix = tree, project, prefix
        self.code_href, self.data_href = code_href, data_href
        self.current = current                 # key of the page being rendered (no term links to itself)
        self.broken: list[str] = []
        self.linked_terms: set[str] = set()    # terms already linked on this page (first use only)
        self.expanded: set[str] = set()        # resources whose alias was already followed by their name
        self.terms = term_patterns(tree, project)

    def replace(self, match: re.Match) -> str:
        target, text, note = (group.strip() if group else None for group in match.groups())
        if target.startswith("code:"):
            href = self.code_href(target[5:], self.prefix)
            label = text or target[5:].replace("#", " → ")
            if href is None:
                self.broken.append(target)
                return f"<span class='ref-broken' title='code not found'>{esc(label)}</span>"
            return f"<a class='ref' href='{esc(href)}' title='{esc(note or target[5:])}'><code>{esc(label)}</code></a>"
        if target.startswith("data:"):
            # in running text a short chip (the text given, or the file name, shortened); the path on hover
            path = target[5:]
            href, label = self.data_href(path, self.prefix)
            name = text or path.rstrip("/").split("/")[-1].split("#")[0]
            name = name if len(name) <= 32 else name[:30] + "…"
            chip = f"{icons.svg('artefact')}{esc(name)}"
            return (f"<a class='data-chip' href='{esc(href)}' title='{esc(note or path)}'>{chip}</a>" if href
                    else f"<span class='data-chip' title='{esc(note or path)}'>{chip}</span>")
        node = self.tree.resolve(target, self.project)
        if node is None and RUN_ID.fullmatch(target) and (DOC / "_changes" / f"{target}.md").exists():
            from kea.docsite import mode        # a run entry ([[2026-11-05-a]]): its change-log page
            if mode.WITH_CHANGELOG:
                return (f"<a class='ref' href='{esc(self.prefix)}changes/{esc(target)}.html' "
                        f"title='{esc(note or 'run ' + target)}'>{esc(text or 'run ' + target)}</a>")
            return f"<code>{esc(text or target)}</code>"
        if node is None:
            project = target.split(":", 1)[0] if ":" in target else self.project
            if project not in self.tree.projects:
                return (f"<span class='ref-missing' title='{esc(project)} has no pages yet'>"
                        f"{esc(text or target)}</span>")
            self.broken.append(target)
            return f"<span class='ref-broken' title='unknown page'>{esc(text or target)}</span>"
        return node_link(node, self.prefix, text, note, from_project=self.project)


def term_patterns(tree: Tree, project: str) -> list[tuple[re.Pattern, Node]]:
    """(pattern, node) for every title and alias of the experiment's term pages, and every alias of its resource
    pages (a dataset id such as G23/MIC), longest first."""
    entries = []
    for node in tree.nodes.values():
        if node.type not in ("term", "resource") or node.project != project:
            continue
        aliases = [str(alias) for alias in node.header.get("aliases") or [] if str(alias).strip()]
        names = ([node.title] if node.type == "term" else []) + aliases
        every = str(node.header.get("link") or "first").strip().lower() == "every"
        for name in names:      # link: every matches the case as written, so a gene APP does not link "app"
            entries.append((len(name), re.compile(r"(?<![\w-])(" + re.escape(name) + r")(?![\w-])",
                                                  0 if every else re.IGNORECASE), node))
    return [(pattern, node) for _, pattern, node in sorted(entries, key=lambda entry: -entry[0])]


def link_terms(html_text: str, context: LinkContext) -> str:
    """Link the first use of each term in each section of the page (a ## heading starts a new one), in prose and in
    table cells (not in links, code, headings or table headers); a term with ``link: every`` in its front matter
    (gene names, say) is linked at every use. Resources with aliases: are linked the same way, and the first mention
    of a resource in the page's prose (not in a table) is followed by its title: G23/MIC (Dataset G23, …)."""
    if not context.terms:
        return html_text
    tokens = re.split(r"(<[^>]+>)", html_text)
    skip_depth = table_depth = 0
    for index, token in enumerate(tokens):
        if token.startswith("<"):
            match = re.match(r"<(/?)([a-zA-Z0-9]+)", token)
            if match and match.group(2).lower() == "table":
                table_depth = max(table_depth + (-1 if match.group(1) else 1), 0)
            if match and not match.group(1) and match.group(2).lower() in ("h1", "h2"):
                context.linked_terms.clear()                     # a new section: link each term once more
            if match and match.group(2).lower() in SKIP_AUTOLINK_TAGS and not token.endswith("/>"):
                skip_depth += -1 if match.group(1) else 1
                skip_depth = max(skip_depth, 0)
            continue
        if skip_depth or not token.strip():
            continue
        pieces: list[tuple[str, bool]] = [(token, False)]     # (text, already a link)
        for pattern, node in context.terms:
            every = str(node.header.get("link") or "first").strip().lower() == "every"
            if node.key == context.current or (node.key in context.linked_terms and not every):
                continue
            anchor_start = (f"<a class='term{' term-resource' if node.type == 'resource' else ''}' "
                            f"href='{esc(node_href(node, context.prefix))}' "
                            f"title='{esc(node.title)}: {esc(node.short)}'>")
            position = 0
            while position < len(pieces):
                text, is_link = pieces[position]
                found = None if is_link else pattern.search(text)
                if not found:
                    position += 1
                    continue
                expand = ""            # a dataset id: its name after the first mention in the page's prose
                if node.type == "resource" and not table_depth and node.key not in context.expanded:
                    context.expanded.add(node.key)
                    named = re.match(rf"^.*?{re.escape(found.group(1))}\s*:\s*(.+)$", node.title, flags=re.I)
                    name = named.group(1) if named else node.title
                    if named or not node.title.lower().startswith(found.group(1).lower()):
                        expand = f"<span class='alias-name'> ({esc(name)})</span>"
                pieces[position:position + 1] = [(text[:found.start()], False),
                                                  (anchor_start + found.group(1) + "</a>" + expand, True),
                                                  (text[found.end():], False)]
                if not every:
                    context.linked_terms.add(node.key)
                    break
                position += 2                                    # go on in the text after this link
        tokens[index] = "".join(text for text, _ in pieces)
    return "".join(tokens)


CALLOUT_START = re.compile(r"^>\s*\[!(\w+)\][+-]?\s*(.*)$")


def callouts(text: str) -> str:
    """Obsidian / GitHub callouts (``> [!warning] Title`` followed by ``> body``) to boxes."""
    lines, output, index = text.split("\n"), [], 0
    while index < len(lines):
        match = CALLOUT_START.match(lines[index])
        if not match:
            output.append(lines[index])
            index += 1
            continue
        kind, title = match.group(1).lower(), match.group(2).strip()
        body = []
        index += 1
        while index < len(lines) and lines[index].startswith(">"):
            body.append(lines[index][1:].removeprefix(" "))
            index += 1
        heading = f"**{title or kind.capitalize()}**"
        output += ["", f"<div class='callout callout-{kind}' markdown='1'>", "", heading, ""] + body + ["", "</div>", ""]
    return "\n".join(output)


HEADING_LINK = re.compile(r"^(#{2,6})[ \t]+\[\[([^\]|]+)\]\][ \t]*:?[ \t]*$", re.M)
TAGLINE_ITEM = re.compile(r"<li><a class='tag (t-[\w-]+)' href='([^']*)' title='([^']*)'>(.*?)</a>"
                          r"((?:(?!</?(?:a|ul|ol|li|p)\b)[^<]|<(?!/?(?:a|ul|ol|li|p)\b)[^>]*>)*)</li>")
TAGLINE_MAX = 220      # characters of text after the tag: longer items are summaries, where only the tag links


def heading_links(text: str, context: LinkContext) -> str:
    """A heading that is only a link (``### [[q-x]]``) shows the tag and the page's title."""
    def expand(match: re.Match) -> str:
        node = context.tree.resolve(match.group(2).strip(), context.project)
        if node is None:
            return match.group(0)
        return f"{match.group(1)} [[{match.group(2).strip()}]] {esc(node.title)}"
    return HEADING_LINK.sub(expand, text)


def tagline_items(html_text: str) -> str:
    """List items made of a tag and one line ("- [[r-x]] what it shows") become one link, tag and text."""
    def join(match: re.Match) -> str:
        type_class, href, title, inner, rest = match.groups()
        plain = re.sub(r"<[^>]+>", "", rest)
        if not plain.strip() or len(plain) > TAGLINE_MAX:
            return match.group(0)
        rest = re.sub(r"^\s*(?:[:\u2014\u2013-]\s*)?", "", rest)
        return (f"<li><a class='tagline' href='{href}' title='{title}'><span class='tag {type_class}'>{inner}</span>"
                f"<span class='tl-text'>{rest}</span></a></li>")
    return TAGLINE_ITEM.sub(join, html_text)


LIST_ITEM = re.compile(r"^ {0,3}(?:[-*+]|\d{1,3}[.)])\s+\S")
FENCE = re.compile(r"^ {0,3}(```|~~~)")


def separate_lists(text: str) -> str:
    """Insert a blank line before a list that directly follows a paragraph line (Markdown would otherwise run the
    list into the sentence: "three checks: - one - two"). Code fences and lines inside a list are left alone."""
    output, in_fence, in_list, previous = [], False, False, ""
    for line in text.split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            if LIST_ITEM.match(line):
                if previous.strip() and not in_list and not previous.lstrip().startswith(("|", "#", ">", "<")):
                    output.append("")
                in_list = True
            elif line.strip() and not line.startswith((" ", "\t")) and not previous.strip():
                in_list = False          # a new paragraph after a blank line ends the list
        output.append(line)
        previous = line
    return "\n".join(output)


def render_markdown(text: str, context: LinkContext) -> str:
    """Markdown to HTML with [[links]] resolved and the first use of each term linked to its page.
    Links inside `code spans` are left alone. Link rules: see node_link and tagline_items."""
    text = heading_links(separate_lists(text), context)
    pieces = re.split(r"(`[^`\n]*`)", text)
    linked = "".join(piece if piece.startswith("`") else LINK_PATTERN.sub(context.replace, piece) for piece in pieces)
    html_text = markdown.markdown(callouts(linked), extensions=["tables", "fenced_code", "sane_lists", "md_in_html"])
    return link_terms(tagline_items(html_text), context)
