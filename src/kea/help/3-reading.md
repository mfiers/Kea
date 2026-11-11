## Reading a Kea site

Start at the top. With one experiment the site opens at the experiment's page: its summary, then every question with its answer in short. With more experiments the project page summarises them first. A question page leads with its answer so far, then its conclusions, results and hypotheses. Details are one click further down.

Every page has a type, shown as a coloured tag with an icon and a number (Q1, R2, C3; references show author and year). The tag is the link to the page; hover it for the page's one-line summary. In lists of pages the whole line is the link.

<!-- KINDS -->

| Type | What it is |
| --- | --- |
| Experiment | the experiment's home page: its summary, then every question with its answer in short |
| Premise | what the analysis takes as given, so a reader can question it |
| Question | what is asked; leads with its answer so far and the conclusions behind it |
| Hypothesis | what was expected, with its prediction and criterion, and whether it was written before its test |
| Step | what was done (the methods: data, tool, version, test, output files) |
| Decision | a choice made along the way, why, and the alternatives |
| Result | what a file shows; every number comes from a named file |
| Conclusion | what the results mean, with the evidence for and against and a certainty |
| Figure | a figure with its full caption, script and table |
| Artefact | a data file the analysis made, with checksum, preview and download |
| Resource | what the analysis takes from outside (a database, dataset, file or tool), with version, retrieval date and checksum |
| Caveat | what limits a result, conclusion or premise; open until a step addresses it |
| Term | a glossary entry; words with a dotted underline link to it |
| Reference | a paper, with its abstract and why it is cited |

On a page:

- The coloured bar on the left and the word above the title say the type. The page's own content (title, summary, text) is set in a typewriter face, indented behind a line. After it, tabs hang under one thick line in the type's colour; one is open at a time. "About this page" holds what Kea knows about the page: its permanent identifier (`kea:…`, which stays when the page is edited or moved, and `@…` for exactly this version, to cite), its sources, and its links to other pages as tables ("Tested by this step", "Supported by these results"), with the reason each link holds; long tables come in pages of 12. "Changes" lists one line per version, "Comments" the comments when the site was built. Resources, terms and references are not listed on the pages: the menu has them under Map.
- A page reads in this order: its title, summary and text, as written; on a question, the answer so far; then its figures and data files under their own separator (one tab per figure or file when there are several; the take-home under each figure, the rest of the caption under "Shows, method and statistics"; a question or conclusion also shows the figures of the results behind it as a row of small images); then the tabs. On an experiment page the first tabs are "Questions" (one line each) and "Answers so far" (each answer, with links to its conclusions), and "About this page" lists its hypotheses, steps, results and conclusions with a filter per kind. Under About, conclusions and caveats are listed one per line; how the page was made (steps, data, sources) is folded under Provenance; the exact changes per version are under History.
- Pills next to the title: the status (green: supported, done or answered; amber: open, planned, assumed or inconclusive; dark red: not supported, deprecated or dropped); "exploratory"; on a hypothesis "written before its test" or "written after results"; on a conclusion its certainty; "waiting for approval", "approved", "confirmed", "recheck"; and the release in which the page last changed.
- The menu bar: the kea head goes home, then project / experiment / page. Map (the experiment as a tree) opens, in a light strip beside it, Relations (the graph of links), Objects (every page in one table to search, filter and sort), Resources, Terms, References, Data files and Code; Plan (the current review cycle; Current comments); History (what changed per agent run; review cycles; all comments); PDF (the analysis as one document to read; with all records under it); Help. The signed-in name opens a menu with your comments, help and sign-out, and at its foot the Kea versions of the site and of the server or hub.
