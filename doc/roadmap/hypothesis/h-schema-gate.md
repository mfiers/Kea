---
id: h-schema-gate
uid: mj4a6a4xs7h5yzdex7ehewbn7e
type: hypothesis
title: Rules in the schema and a ranked list of open work can enforce the order of reasoning in about a hundred lines
short: Transition rules in _schema.yaml make kea check a gate on commits and releases, and kea next ranks open work; the agent keeps full freedom inside a step while the graph sets the order.
parent: q-enforce
status: planned
fixed_before_results: true
prediction: "With the transition rules in _schema.yaml and kea next, an agent run on a test project does not commit or release while the graph breaks a rule, and the rules plus kea next fit in about 100 lines of code."
criterion: "Supported if, on a test project with planted violations (a result without a step that tests a hypothesis, a conclusion without a supporting result, an open caveat not addressed), kea check refuses every one of them, kea next ranks the untested hypothesis first, and the code added is at most about 150 lines. Not supported if any planted violation passes the gate or the code needs more than about 300 lines; in between, inconclusive."
---
The loop becomes:

1. The agent asks `kea next` what to do.
2. It does the work and writes the pages.
3. `kea check` accepts or rejects the result.

Tested by [[s-graph-drives-agent]]. Limits: [[w-gate-editable]], [[w-form-not-substance]].
