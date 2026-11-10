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

- The coloured bar on the left and the word above the title say the type. The page's own content (title, summary, text) is set in a serif face. Under the line "About this page" is what Kea knows about it: its permanent identifier (`kea:…`, which stays when the page is edited or moved, and `@…` for exactly this version, to cite), its sources, and its links to other pages as tables ("Tested by this step", "Supported by these results"), with the reason each link holds.
- A result's figures come right under its summary, with the take-home; open "Shows, method and statistics" for the rest of the caption. A question or conclusion shows the figures of the results behind it as a row of small images. Under the text, conclusions and caveats are listed one per line; how the page was made (steps, data, sources) is folded under Provenance. "Changes to this page" lists one line per version; the exact changes are under History.
- Pills next to the title: the status (green: supported, done or answered; amber: open, planned, assumed or inconclusive; dark red: not supported, deprecated or dropped); "exploratory"; on a hypothesis "written before its test" or "written after results"; on a conclusion its certainty; "waiting for approval", "approved", "confirmed", "recheck"; and the release in which the page last changed.
- The menu bar: the kea head goes home, then project / experiment / page. Map (the experiment as a tree) with Relations (the graph of links) and Objects (every page in one table to search, filter and sort; Data and Code under it); Plan (the current review cycle); History (what changed per agent run; review cycles; all comments); PDF (the analysis as one document to read; with all records under it); Help.
