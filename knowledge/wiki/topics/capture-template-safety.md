---
type: topic
title: "Capture template safety"
created: 2026-05-04
updated: 2026-05-04
tags: [capture, safety, template]
---

# Capture Template Safety

The generic capture template is a public-safe recipe for silent raw-source ingest. It uses placeholders only and keeps real deployment details private. [Source: infra/openclaw/wai-brain-capture.md]

## Command Failure Behavior

If `git pull --rebase`, `git commit`, or `git push` fails, the capture pipeline stops. It may retry once after a fresh rebase, then it must save partial state privately and notify the operator with a human-readable reason. It must not mask failures or continue on a stale local branch. [Source: infra/openclaw/wai-brain-capture.md]

## Reply Safety

The capture template must never expose raw filenames, slugs, local paths, or internal tool errors in user-visible replies. [Source: infra/openclaw/wai-brain-capture.md]

## Frontmatter

The generic raw frontmatter includes `type: raw`, `title`, `created`, `tags`, `source`, `source_id`, `captured_at`, and `needs-pii-review`. [Source: infra/openclaw/wai-brain-capture.md]
