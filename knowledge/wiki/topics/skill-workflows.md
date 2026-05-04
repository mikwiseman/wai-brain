---
type: topic
title: "Skill workflows"
created: 2026-05-04
updated: 2026-05-04
tags: [skills, workflow, agents]
---

# Skill Workflows

Skills encode repeatable agent workflows for the public template. They cover inbox processing, source ingest, wiki linting, weekly review, people-page updates, and retrieval eval runs. [Source: AGENTS.md]

## Current Skills

- `process-inbox` sweeps immutable raw sources and selects files for ingest. [Source: .claude/skills/process-inbox/SKILL.md]
- `ingest-source` records a source hash, extracts durable claims, updates compiled pages, rebuilds the index, and runs doctor. [Source: .claude/skills/ingest-source/SKILL.md]
- `lint-wiki` checks stale claims, contradictions, broken links, orphan pages, and privacy leaks. [Source: .claude/skills/lint-wiki/SKILL.md]
- `eval-run` writes and inspects retrieval eval reports. [Source: .claude/skills/eval-run/SKILL.md]
- `weekly-review` summarizes recent repo and capture activity. [Source: .claude/skills/weekly-review/SKILL.md]
- `people-update` enforces compiled truth plus timeline discipline for people pages. [Source: .claude/skills/people-update/SKILL.md]
