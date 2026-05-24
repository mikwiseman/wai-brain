# wai-brain

Local-first WaiBrain prototype: reviewable AI memory with canonical JSONL,
generated Markdown wiki, and a minimal static HTML review surface.

## Philosophy

WaiBrain separates memory into layers:

- `knowledge/raw/` keeps immutable source evidence.
- `knowledge/review/proposals.jsonl` stores candidate memory changes.
- `knowledge/canonical/*.jsonl` is the source of truth after review.
- `knowledge/wiki/` is generated Markdown for humans and agents.
- `knowledge/site/index.html` is a minimal local review/workbench page.

RAG is a query layer over canonical records, generated wiki, and raw evidence.
It is not allowed to write truth directly.

## Quick Start

```bash
python3 scripts/brain.py init
python3 scripts/brain.py propose \
  --title "Yulia memory governance problem" \
  --source knowledge/raw/telegram/yulia.md \
  --entity-name "Yulia Mitrovich" \
  --entity-type person \
  --alias "@yuliamitrovich83" \
  --fact "has_problem=needs governable AI memory without duplicate generated content"
python3 scripts/brain.py review list
python3 scripts/brain.py review accept <proposal_id>
python3 scripts/brain.py wiki build
python3 scripts/brain.py site build
python3 scripts/brain.py serve --port 8765
```

Typed proposal kinds include `fact_add`, `fact_reinforce`, `fact_supersede`,
`fact_conflict`, `event_add`, `entity_create`, and `entity_merge`.

To stage an entity merge:

```bash
python3 scripts/brain.py merge-entity \
  --winner person/yulia-mitrovich \
  --loser person/yuliamitrovich83 \
  --reason "Telegram handle belongs to the same person"
```

Open `http://127.0.0.1:8765/` after `serve` for the live review workbench.
It supports pending proposal inspection plus browser accept/reject actions.
`knowledge/site/index.html` remains a static snapshot export.

## Checks

```bash
python3 -m unittest discover -s tests
python3 scripts/brain.py doctor
python3 scripts/brain.py wiki build
python3 scripts/brain.py site build
python3 scripts/brain.py serve --port 8765
```
