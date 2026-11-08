---
id: s-lean-checker
type: step
title: "Lean as a checker of supports and limits edges (optional plugin)"
short: "Each supports or limits edge becomes a proof obligation, so a hidden assumption shows up as a proof that will not close; a lighter first step formalises only the statistical layer."
parent: q-order
status: planned
order: 10
---
Lean cannot prove a result is true; that is empirical. It could prove that a conclusion follows from its premises, results and stated assumptions. A lighter first step: formalise only the statistical layer, for example "this test assumes independence and a later step breaks it". To keep Kea small, this would be an optional plugin, not part of the core.
