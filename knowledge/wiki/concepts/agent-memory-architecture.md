---
type: concept
title: "Agent memory architecture"
created: 2026-05-04
updated: 2026-05-04
tags: [architecture, agent-memory, second-brain]
---

# Agent Memory Architecture

`wai-brain` keeps Markdown canonical. Raw evidence is immutable, compiled pages are agent-maintained, and deterministic commands verify search/index/eval behavior before changes are trusted. [Source: AGENTS.md]

## Layers

- `knowledge/raw/` stores immutable evidence. In this public repo, it stores synthetic examples only. [Source: AGENTS.md]
- `knowledge/wiki/` stores compiled topic and concept pages. [Source: AGENTS.md]
- `knowledge/projects/` and `knowledge/people/` use compiled truth above a horizontal rule and append-only timeline entries below it. [Source: AGENTS.md]
- `knowledge/manifests/` stores append-only machine-readable provenance ledgers. [Source: knowledge/manifests/README.md]
- `scripts/brain.py` provides the deterministic harness for doctor, search, index, eval, and manifest operations. [Source: README.md]

## Design Bias

Start with files and tests. Add vector search, graph storage, or a database only when the Markdown corpus and retrieval evals prove they are needed.
