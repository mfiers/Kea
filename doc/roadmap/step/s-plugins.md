---
id: s-plugins
uid: yxjfgdieb4gilefg47f5ky3dhi
type: step
title: "Plugins: what it would take"
short: "Kea has no plugin mechanism, but types, relations and tags are already data. A plugin interface would turn internal structures into a public contract, so the proposal is to wait for two real plugins and keep only the hooks they use."
parent: q-order
status: planned
order: 13
relations:
  relies_on: [p-small-kernel]
---
## What can be extended today without code

- Node types, numbering, statuses, relations and required fields: `doc/_schema.yaml`.
- Tags and their instructions for the agent: `tags:` in kea.yaml ([[s-tags]]).
- Agent behaviour: the Kea skill and CLAUDE.md, which are text.

That covers more than it seems: a new kind of page with its own relations needs no code at all.

## What a plugin would need to do

The candidates so far are the Lean checker ([[s-lean-checker]]), an Anthive or other catalogue resource (fetch version and checksum of a dataset), a manuscript builder ([[s-paper-compiler]]) and lab-specific checks (for example "every figure of a mouse experiment names the strain"). From those, four hook points:

| Hook | Called with | Returns | Needed by |
| --- | --- | --- | --- |
| check | one page (front matter, body, relations) | problems and notes | Lean checker, lab checks |
| page section | one page | an HTML block for the page | Lean checker (proof state), resources |
| command | the CLI arguments | exit code | manuscript builder, resource fetchers |
| build step | the built site folder | files added | manuscript builder |

## How

Python entry points (`[project.entry-points."kea.plugins"]` in the plugin's pyproject.toml), found with `importlib.metadata`, enabled per project in kea.yaml (`plugins: [kea-lean]`). Plugins run only where the site is built, on the author's machine; the hub receives a built site and runs no plugin code. That keeps the hub safe.

## Cost

- The loader and the four hooks: my estimate is about 150 lines, not measured.
- The real cost is the contract. Once a plugin reads the page object, its fields can no longer change freely, and that works against [[p-small-kernel]]. Every hook needs a version number and a test that a plugin built against it still loads.

## Proposal (Claude, 7 November 2026)

Do not build a plugin interface before two plugins exist. Write the Lean checker and the manuscript builder inside Kea first, behind kea.yaml switches. When both work, move them out, keeping only the hooks they used. A general interface designed before its first user tends to be wrong in the ways that matter.
