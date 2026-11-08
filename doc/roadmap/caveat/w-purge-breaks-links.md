---
id: w-purge-breaks-links
type: caveat
title: Purging old identifiers breaks links from other projects unless a tombstone stays
short: "An identifier that is promised never to change cannot simply disappear; a purge must leave a record of what the object was and why it was removed."
parent: s-stable-ids
status: open
relations:
  limits: [s-stable-ids]
---
Raised in the review of the identifier proposal on 7 November 2026 (Claude). DOIs of withdrawn papers resolve to a retraction notice; a purged Kea id should resolve to a tombstone in the same way.
