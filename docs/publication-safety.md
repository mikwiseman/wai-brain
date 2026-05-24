# Publication Safety

This repository is the public-safe WaiBrain engine/template. It must not
contain private memory, raw Telegram exports, customer data, health data,
financial data, real private identifiers, OAuth usernames, server IPs, token
locations, or secret names.

Deleted files remain in Git history. If a repository has ever contained private
data, do not simply make it public. Create a fresh clean repository or rewrite
history and verify it separately.

Before publishing or pushing public-facing changes, run:

```bash
python3 -m unittest discover -s tests
python3 scripts/brain.py doctor
python3 scripts/brain.py wiki build
python3 scripts/brain.py site build
python3 scripts/brain.py obsidian export --path /tmp/wai-brain-obsidian-check
git diff --check
```

The canonical public-safe boundary is:

- `knowledge/raw/` contains only synthetic examples in this public repo.
- `knowledge/canonical/*.jsonl` must not contain private records here.
- `knowledge/review/proposals.jsonl` must not contain private source excerpts.
- Generated `knowledge/wiki/` and `knowledge/site/` are public-safe projections.
