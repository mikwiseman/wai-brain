---
type: topic
title: "Publication safety"
created: 2026-05-04
updated: 2026-05-04
tags: [publishing, safety]
---

# Publication Safety

This repository is safe to publish only when the working tree and Git history contain no private material.

## Rule

If a repository has ever contained private data, do not simply toggle it public. Deleted files remain in Git history.

Safe publication paths:

1. Create a fresh public repository from a clean tree.
2. Or rewrite history, verify the rewritten history, and force-push only after a separate review.

## Public-Safe Checklist

- No real raw captures.
- No private project/person/family/company pages.
- No real chat IDs.
- No server IPs or private hostnames.
- No deploy-key paths.
- No OAuth usernames.
- No token locations or secret names.
- No manifests pointing at private files.

Run:

```bash
python3 -m unittest discover -s tests
python3 scripts/brain.py doctor
python3 scripts/brain.py index --check
python3 scripts/brain.py eval
git diff --check
```
