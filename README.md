# wai-brain

Public-safe template for a local-first second brain and agent-memory system.

The repository keeps Markdown as the canonical store, uses immutable raw evidence, lets agents compile durable knowledge into wiki/project/person pages, and verifies the whole system with deterministic local tooling.

## What This Repo Contains

- `scripts/brain.py` — stdlib-only CLI for `doctor`, `search`, `index`, `eval`, and source manifests.
- `.claude/skills/` — reusable agent workflows for inbox processing, source ingest, linting, eval, weekly review, and people updates.
- `knowledge/` — synthetic example vault structure.
- `knowledge/manifests/` — JSONL provenance ledgers.
- `infra/openclaw/wai-brain-capture.md` — generic capture recipe with placeholders.
- `docs/publication-safety.md` — rules for keeping a public repo separate from a private vault.

## What This Repo Must Not Contain

- Real chat exports or raw private messages.
- Real people, family, health, financial, customer, investor, or company memory.
- Chat IDs, server IPs, deploy-key paths, OAuth usernames, token locations, or secret names.
- Private project pages or decisions.
- Manifests pointing at private source files.

Keep private memory in a separate private vault. Use this repository as the public engine/template.

## Layout

- `knowledge/raw/example/` — synthetic immutable raw examples.
- `knowledge/wiki/` — compiled topical pages and generated `INDEX.md`.
- `knowledge/people/` — person pages using compiled-truth + timeline rules.
- `knowledge/projects/` — project pages using compiled-truth + timeline rules.
- `knowledge/eval/` — golden retrieval questions and generated eval reports.
- `knowledge/manifests/` — append-only source/claim JSONL ledgers.

## Local Checks

```bash
python3 -m unittest discover -s tests
python3 scripts/brain.py doctor
python3 scripts/brain.py index --check
python3 scripts/brain.py eval
```

`doctor` includes public-safety checks for common private-data patterns.

## Publishing Warning

Deleting private files in a commit does not remove them from Git history. If a repository has ever contained private data, do not make that existing repository public. Create a fresh public repo from a clean tree or rewrite history and verify it before publication.

## References

- Karpathy LLM Wiki — https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- GBrain — https://github.com/garrytan/gbrain
- AGENTS.md standard — https://agents.md
