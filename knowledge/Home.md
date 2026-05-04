---
type: home
title: "wai-brain public template home"
created: 2026-05-04
tags: [home, navigation]
---

# wai-brain

Public-safe template vault for a Markdown-native agent memory system.

> Read `AGENTS.md` at the repo root before working in this repo.

## Map

- `raw/example/` — synthetic immutable source examples.
- `wiki/INDEX.md` — generated catalog of compiled pages.
- `wiki/concepts/` — public-safe concept pages.
- `wiki/topics/` — public-safe topic pages.
- `projects/` — synthetic project pages using compiled-truth + timeline.
- `people/` — synthetic or empty person pages using compiled-truth + timeline.
- `manifests/` — source and claim ledgers.
- `eval/golden-questions.md` — public-safe retrieval eval set.

## Local Verification Commands

```bash
python3 -m unittest discover -s tests
python3 scripts/brain.py doctor
python3 scripts/brain.py index --check
python3 scripts/brain.py eval
```

## Privacy Boundary

This repository is the public engine/template. Private vault content belongs in a separate private repository or directory.
