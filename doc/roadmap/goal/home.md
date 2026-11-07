---
id: home
type: goal
title: "Where should Kea go next, and in what order?"
short: Kea makes an agent structure an analysis around questions, premises, hypotheses, results and caveats, but only implicitly; this experiment decides which additions would enforce or extend that structure without losing a small kernel.
status: open
---
Kea is less a documentation tool than a scaffold that makes an agent structure a data analysis around questions,
premises, hypotheses, results, conclusions and caveats. Pages are typed Markdown with typed relations, checked against
a schema. Readers comment on the built site, and an agent folds comments into a plan, implements it and releases a
semantic version. A hub hosts many projects' sites and comments while each agent works locally.

Nothing forces the structure yet ([[q-enforce]]). Nine ideas, plus Lean as an optional checker, are on the table
([[q-order]]); the working proposal is structure through constraints in the schema rather than orchestration code
([[h-schema-gate]]). Every idea should keep the small kernel ([[p-small-kernel]]).

Source: Mark Fiers, "Kea: where it could go", 6 November 2026.

## Scope

In: additions to Kea itself (schema, command line, hub, optional plugins). Out: changes to how individual projects
write their pages. Exploratory: this is a roadmap, not an analysis of data; no hypothesis here has been tested yet.
