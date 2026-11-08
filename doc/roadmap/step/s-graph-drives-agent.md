---
id: s-graph-drives-agent
uid: zz5ofwtf3sf52cvhu2xaunyzhu
type: step
title: "Graph drives the agent: schema rules gate commits; kea next picks the next item"
short: "Transition rules in _schema.yaml turn kea check into a gate; kea next ranks open work, such as the untested hypothesis whose resolution would change the most conclusions."
parent: q-order
status: planned
order: 1
relations:
  tests: [h-schema-gate]
---
**Transition rules in `_schema.yaml`.** For example: a result must link to a step that tests a hypothesis; a conclusion needs at least one supporting result and must address every open caveat. `kea check` becomes a gate, so the agent cannot commit or release while the graph breaks a rule. Projects can loosen or tighten the rules.

**`kea next`.** Ranks open work, such as the untested hypothesis whose resolution would change the most conclusions.
