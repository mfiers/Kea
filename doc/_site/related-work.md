---
title: Related work
short: How Kea relates to models of claims and evidence, to provenance standards and to AI systems that keep a structured state of an analysis, and how Kea's terms map onto theirs.
---
Kea's pages and relations were designed for running an analysis with an AI agent, not taken from a standard. Most of its parts have close counterparts elsewhere. This page names them, maps the vocabulary, and says what Kea adds. Citations were checked against the primary sources on 10 November 2026, except Toulmin (1958) and Peroni & Shotton (2012), cited from the record.

## Models of claims and evidence

**Micropublications** (Clark, Ciccarese & Goble 2014). A semantic model of the argument in a biomedical paper: statements, data, methods and materials linked by *supports* and *challenges*, grounded in Toulmin–Verheij argumentation, with an OWL 2 vocabulary at purl.org/mp. The minimal micropublication is "a statement with its attribution", which is what a Kea page with its permanent id and author is. Micropublications describe arguments in published papers, after the fact; Kea records an argument while the analysis is done.

**Discourse graphs** (Chan et al. 2024). Questions, claims, evidence and sources; evidence informs questions and supports or opposes claims. Built as a Roam Research extension, and adapted by hand by users of Obsidian and other notebooks, mostly for literature synthesis. This is the lightest model and the closest to Kea's core: Kea's question, conclusion (claim), result (evidence) and reference (source), with *supported_by* and *opposed_by*, form a discourse graph of one analysis. Kea adds the route around it: hypotheses fixed before their test, the steps that make results, premises, decisions and caveats.

**Octopus** (octopus.ac). A publishing platform with eight linked publication types: Research Problem, Rationale/Hypothesis, Method, Results/Sources of Evidence, Analysis, Interpretation, Applications/Implications, and Review. Its chain is the closest to Kea's route. Its founder has noted that authors ask what belongs in Results as opposed to Analysis (Coddington 2024); Kea cuts that line as a result (what a file shows, every number from a named file) against a conclusion (what the results mean, with a certainty).

**Nanopublications** (Kuhn et al. 2018). Each record is an assertion graph, a provenance graph and a publication-info graph, held together by a head graph, identified by a hash-based Trusty URI, with provenance in W3C PROV. The machine-readable format for publishing single claims; a possible export for Kea's confirmed conclusions.

**SEPIO**, the Scientific Evidence and Provenance Information Ontology (OBO Foundry). Assertions about propositions, evidence lines that support or dispute them, evidence and data items, assertion methods and agents. The GA4GH Variant Annotation specification (VA-Spec 1.0) derives its core model from SEPIO, with profiles for ACMG variant pathogenicity used by ClinGen. The most rigorous model here, and too heavy to write by hand page by page.

**Toulmin (1958) and IBIS (Kunz & Rittel 1970)**, the roots of the above. Toulmin's argument: claim, data, warrant, backing, qualifier and rebuttal. IBIS: issues, positions, and arguments for or against a position.

**GRADE** (Schünemann et al. 2013). Rates the quality (now: certainty) of a body of evidence as high, moderate, low or very low, lowered for risk of bias, inconsistency, indirectness, imprecision and publication bias. Kea's `certainty:` uses the same four labels with a one-line reason; it does not apply GRADE's rating method.

## Provenance

**W3C PROV-O** (Lebo, Sahoo & McGuinness 2013). Entities, activities and agents, linked by *wasGeneratedBy*, *used*, *wasDerivedFrom* and *wasAttributedTo*.

**Workflow Run RO-Crate** (Leo et al. 2024). JSON-LD packages of a run's inputs, code and outputs, aligned to PROV and schema.org, in three profiles (Process Run Crate, Workflow Run Crate, Provenance Run Crate), implemented in several workflow systems, among them Galaxy, COMPSs, StreamFlow and Autosubmit. Kea's `made_by`, `uses` and `sources` map onto PROV, so an RO-Crate export is possible; it would be thin until Kea's steps record their inputs and outputs per run.

**CiTO**, the Citation Typing Ontology (SPAR). Typed citations, among them *supports*, *disputes*, *critiques*, *agreesWith*, *disagreesWith* and *retracts*.

## AI systems that keep a structured state

**Kosmos** (Mitchener et al. 2025). An AI scientist whose data-analysis agent and literature agent share a "structured world model", updated each cycle with summaries of the task outputs and queried to plan the next; a run has over 200 agent rollouts, and the claims in its report link back to the analysis or paper they came from. The same idea as Kea's graph, but inside the machine: the paper gives no schema for the world model, and no person approves a step before the next one is built on it.

**POPPER** (Huang et al. 2025). Agents test a free-form hypothesis by sequential falsification: they design experiments on its measurable implications and pool the evidence as e-values, with control of the Type-I error. Kea's hypothesis with its `prediction:` and `criterion:`, tested by a step, is the same move made by hand, without the statistical frame.

## Kea's terms and theirs

| Kea | Nearest existing term | Source |
| --- | --- | --- |
| question | question; issue; research problem | discourse graphs; IBIS; Octopus |
| premise | none fits; nearest: backing, assumption | Toulmin |
| hypothesis | rationale/hypothesis | Octopus |
| `prediction:`, `criterion:` | measurable implication; falsification test | POPPER |
| step | method; activity | Octopus, micropublications; PROV |
| decision | position; architecture decision record | IBIS; software engineering |
| result | evidence; data; results/sources of evidence | discourse graphs, micropublications, Toulmin; Octopus |
| conclusion | claim; statement; assertion | discourse graphs; micropublications; nanopublications, SEPIO |
| `supported_by`, `opposed_by` | supports, opposes; supports, challenges | discourse graphs; micropublications |
| `because:` on a link | warrant | Toulmin |
| caveat | rebuttal, qualifier; limitation | Toulmin; GRADE |
| `certainty:` high … very low | certainty (quality) of evidence | GRADE, same four levels |
| `made_by`, `uses`, `sources` | wasGeneratedBy, used, wasDerivedFrom | PROV |
| resource | Dataset, SoftwareApplication (with an RRID) | schema.org, RO-Crate |
| reference | source | discourse graphs |
| permanent id with author | statement with its attribution; Trusty URI | micropublications; nanopublications |
| `fixed_before_results: true` | preregistered (but see below) | OSF, registered reports |
| exploratory, confirmatory | the same | standard usage |

Kea keeps its own word where no standard one fits: *premise* (no model above has it), *decision*, *step* and *caveat* (sharper than "limitation": it names what limits which page and stays open until a step addresses it). `fixed_before_results` is not called preregistration on purpose: the record is a commit in the project's own repository, whose history can be rewritten and which is often private, while a preregistration sits in a public registry.

## What Kea adds

We found none of the following, combined, in the systems above:

- a person's approval at each step of the route before the agent builds on it (`pace: guided`);
- hypotheses fixed before their test, recorded in the graph with the commit time as the record;
- recheck flags that run downstream when a page upstream changes;
- the agent's runs, change logs and review cycles tied to semantic versions of the whole graph;
- all of it as Markdown in the project's own git repository.

The survey is short; this is what we found, not a claim that nothing like it exists.

## Sources

- Chan J, Akamatsu M, Vargas D, Kawerau L, Gartner M (2024). Steps towards an infrastructure for scholarly synthesis. arXiv:2407.20666. <https://arxiv.org/abs/2407.20666>
- Clark T, Ciccarese PN, Goble CA (2014). Micropublications: a semantic model for claims, evidence, arguments and annotations in biomedical communications. J Biomed Semantics 5:28. doi:10.1186/2041-1480-5-28. <https://doi.org/10.1186/2041-1480-5-28>
- Coddington M (2024). How to enter a new chapter in academic publishing (interview with Alexandra Freeman). Technology Networks, 10 August 2024.
- Guyatt GH, Oxman AD, Vist GE et al. (2008). GRADE: an emerging consensus on rating quality of evidence and strength of recommendations. BMJ 336:924–926. doi:10.1136/bmj.39489.470347.AD
- Huang K, Jin Y, Li R, Li MY, Candès E, Leskovec J (2025). Automated hypothesis validation with agentic sequential falsifications. Proc. 42nd ICML, PMLR 267:25372–25437. arXiv:2502.09858. <https://proceedings.mlr.press/v267/huang25n.html>
- Kuhn T, Meroño-Peñuela A, Malic A, Poelen JH, Hurlbert AH et al. (2018). Nanopublications: a growing resource of provenance-centric scientific linked data. IEEE 14th International Conference on e-Science, 83–92. doi:10.1109/eScience.2018.00024. arXiv:1809.06532.
- Kunz W, Rittel HWJ (1970). Issues as elements of information systems. Working paper, Institute of Urban and Regional Development, University of California, Berkeley. <https://escholarship.org/uc/item/5cj786v8>
- Lebo T, Sahoo S, McGuinness D (eds) (2013). PROV-O: the PROV ontology. W3C Recommendation, 30 April 2013. <https://www.w3.org/TR/2013/REC-prov-o-20130430/>
- Leo S, Crusoe MR, Rodríguez-Navas L, Sirvent R, Kanitz A et al. (2024). Recording provenance of workflow runs with RO-Crate. PLOS ONE 19(9):e0309210. doi:10.1371/journal.pone.0309210.
- Mitchener L, Yiu A, Chang B, Bourdenx M, Nadolski T et al. (2025). Kosmos: an AI scientist for autonomous discovery. arXiv:2511.02824. <https://arxiv.org/abs/2511.02824>
- Octopus: <https://www.octopus.ac>; publication types in the author guide, <https://www.octopus.ac/author-guide>.
- Schünemann H, Brożek J, Guyatt G, Oxman A (eds) (2013). GRADE handbook. <https://gdt.gradepro.org/app/handbook/handbook.html>
- SEPIO: <https://obofoundry.org/ontology/sepio>; GA4GH VA-Spec 1.0, <https://va-spec.ga4gh.org/en/1.0/>
- SPAR CiTO: <http://purl.org/spar/cito>; Peroni S, Shotton D (2012). FaBiO and CiTO: ontologies for describing bibliographic resources and citations. J Web Semantics 17:33–43. doi:10.1016/j.websem.2012.08.001.
- Toulmin SE (1958). The uses of argument. Cambridge University Press.
