---
type: index
title: "Manifests"
created: 2026-05-04
updated: 2026-05-04
tags: [manifest, provenance]
---

# Manifests

Machine-readable provenance ledgers. Markdown remains canonical; manifests make source and claim tracking inspectable and testable.

## Files

- `sources.jsonl` — one JSON object per source recorded by `brain manifest-add-source`.
- `claims.jsonl` — reserved for extracted claim ids, source ids, validity windows, and supersession links.

## Rules

- Append-only unless repairing invalid JSON before first use.
- Never store secrets or full private message text here.
- Public manifests must reference synthetic sources only.
