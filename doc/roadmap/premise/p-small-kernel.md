---
id: p-small-kernel
type: premise
title: Kea's main strength is that it is small
short: No database, static HTML and a code base an agent can read and change during a session when a reader asks; every addition should keep a small kernel with ambition in optional parts around it.
parent: home
status: assumed
order: 1
---
Small enough that an agent can extend the tool on the spot when a reader asks for something. Every idea on this
roadmap should keep that: a small kernel, with ambition in optional parts around it.

The note of 6 November gives the size as about 4,000 lines of Python. Measured on 7 November 2026 (v1.10.1,
`src/kea`), it is about 8,100 lines; `docsite/pdf.py` alone is 1,664. The premise still holds, but the kernel is
already twice the size the note assumes.
