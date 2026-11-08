---
id: q-vocabulary
uid: onynuocoe33kyf6ovskdtnh2tq
type: question
title: Are Kea's page types and relations sufficient, complete and not too many?
short: A reading of the literature on structured argument and scientific discourse against Kea's schema, and of how the one real analysis so far uses it.
parent: home
status: answered
order: 3
answer: "Sufficient: the six types that carry the argument (question, premise, hypothesis, result, conclusion, caveat) match the roles in Toulmin, IBIS, discourse graphs and micropublications one to one; the other types are provenance and glossary, which those models leave out on purpose. Incomplete in what pages and links record, not in types: what counts as support for a hypothesis, why a link holds, how certain a conclusion is, exploratory work as a property separate from status, and the kind of a caveat; these became fields in Kea 1.17. Slightly too much: an unused dataset type (removed) and the untyped relies_on where a typed relation fits (now noted). The main limit: one project of use (S100), which used none of the argument core, so whether the fields will be used is open."
---
## How the roles compare

| Role | In the literature | In Kea |
| --- | --- | --- |
| The issue | Question (discourse graphs), Issue (IBIS; Kunz and Rittel 1970), Research question (SWAN) | question |
| A claim before evidence | Hypothesis (SWAN, EXPO, CoreSC) | hypothesis |
| A claim after evidence | Claim (Toulmin 1958; discourse graphs; micropublications, Clark et al. 2014) | conclusion |
| What is taken as given | Warrant and backing (Toulmin) | premise |
| The observation | Data (Toulmin), Evidence (discourse graphs), Observation and Result (CoreSC) | result |
| Exception or limit | Rebuttal (Toulmin), challenge (micropublications), qualifies (CiTO) | caveat with limits |
| The work | Method and Experiment (CoreSC), planned process (OBI), Activity (PROV) | step |
| A choice | Position or Option (IBIS; QOC, MacLean et al. 1991) | decision |
| Support and attack | supports, opposes (discourse graphs); supports, challenges (micropublications); supports, disputes (CiTO) | supports, opposes |

## What was missing, and what Kea 1.17 adds

- **What counts as support** (preregistration practice; Nosek et al. 2018): `prediction:` and `criterion:` on a hypothesis, required when `fixed_before_results: true`. Before, fixing a hypothesis froze its wording but not what result would count for or against it, so an unclear outcome could still be read either way.
- **Exploratory work as its own property:** `analysis: confirmatory | exploratory` on results, conclusions, steps and figures. Before, `exploratory` was one of the statuses, mixed with the life of a page (done, deprecated) and its outcome (supported), so a page could not be both exploratory and supported. The old spelling still works and gets a note.
- **Why a link holds** (Toulmin's warrant; relations with their own provenance in micropublications and discourse graphs): a link can be written `{id: r-x, because: "…"}`. Unjustified support links are how claims drift through citation (Greenberg 2009). `kea check` notes links into conclusions without a reason; the site and the PDF show the reason with the link.
- **How certain a conclusion is** (Toulmin's qualifier, as in GRADE): `certainty: high | moderate | low | very_low` with `certainty_because:`.
- **The kind of a caveat** (threats to validity; Shadish, Cook and Campbell 2002): `kind: internal | external | construct | statistical | other`.

Not added, although the literature has them: background and motivation (prose on the experiment page), options and criteria as separate pages (a convention inside a decision page is enough), a method type apart from its execution (planned with code pages), and links between results that replicate or conflict (deferred until a project needs them).

## What was too much

- The `dataset` type was in the code but not in the schema and no project used it; removed (a dataset is a resource with `kind: dataset`).
- `relies_on` links any page to any page. `kea check` now notes each one where a typed relation fits.
- `supported_by` and `supports` are two spellings of one link. Both stay: Kea already shows each link once, and the one real project wrote only the conclusion side.

## Evidence from use (one project, exploratory)

In the S100 analysis, the only real one so far: 12 results, 2 conclusions and 6 questions, but no hypotheses, no premises, no `supports` or `tests` links, and 7 of 14 results and conclusions exploratory; 8 `relies_on` links where `decided_in` fits. With 1.17 its check gives no problems and 18 notes. Two readings remain open: the work is descriptive, or nothing asked the agent for premises and hypotheses. `kea context` now asks for them. Chan et al. (2024, arXiv:2407.20666) found the same in three years of discourse-graph use: the effort of writing the structure, not the model, decides whether it is used; so nothing here adds a page type.
