---
id: w-gate-editable
type: caveat
title: The agent held by the rules can edit the rules
short: A gate in _schema.yaml is only as strong as the agent's inability to loosen it, and the same smallness that lets an agent change Kea lets it change the schema or skip a commit hook.
parent: h-schema-gate
status: open
relations:
  limits: [h-schema-gate]
---
Raised in the review of the roadmap on 7 November 2026 (Claude). A possible answer: changes to the rules go through the review cycle as plan items, and the agent cannot release while a rule change is unapproved.
