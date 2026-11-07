---
id: h-schema-gate
type: hypothesis
title: Rules in the schema and a ranked list of open work can enforce the order of reasoning in about a hundred lines
short: Transition rules in _schema.yaml make kea check a gate on commits and releases, and kea next ranks open work; the agent keeps full freedom inside a step while the graph sets the order.
parent: q-enforce
status: planned
fixed_before_results: true
---
The loop becomes:

1. The agent asks `kea next` what to do.
2. It does the work and writes the pages.
3. `kea check` accepts or rejects the result.

Tested by [[s-graph-drives-agent]]. Limits: [[w-gate-editable]], [[w-form-not-substance]].
