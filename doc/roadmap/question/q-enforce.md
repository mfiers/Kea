---
id: q-enforce
uid: woi5wmcwjitvlhak4akyv23bmi
type: question
title: How should Kea enforce the structure of an analysis without losing its smallness?
short: An orchestration layer in the style of LangChain could enforce the structure but risks over-engineering; constraints in the schema might do it in about a hundred lines.
parent: home
status: open
order: 1
relations:
  relies_on: [p-small-kernel, p-structure-implicit]
---
A LangChain-like orchestration layer could enforce the structure, but it risks over-engineering and would cost the smallness that lets an agent change Kea on the spot ([[p-small-kernel]]). The middle path proposed in [[h-schema-gate]]: structure through constraints in the schema, not through orchestration code.
