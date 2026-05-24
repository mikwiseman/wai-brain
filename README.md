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
  --fact "has_problem=needs governable AI memory without duplicate generated content" \
  --evidence-quote "needs governable AI memory"
python3 scripts/brain.py review list
python3 scripts/brain.py review accept <proposal_id>
python3 scripts/brain.py wiki build
python3 scripts/brain.py site build
python3 scripts/brain.py obsidian export --path dist/obsidian
python3 scripts/brain.py serve --port 8765
```

Typed proposal kinds include `fact_add`, `fact_reinforce`, `fact_supersede`,
`fact_conflict`, `event_add`, `relation_add`, `entity_create`, and
`entity_merge`.

Relations are accepted through the same review queue:

```bash
python3 scripts/brain.py propose \
  --title "Yulia discusses memory with Mik" \
  --source knowledge/raw/telegram/yulia.md \
  --entity-name "Yulia Mitrovich" \
  --entity-type person \
  --relation "discusses_with=person/mik-wiseman"
```

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

`knowledge/wiki/` is Obsidian-compatible generated Markdown. It includes entity
pages, source pages, YAML frontmatter, aliases, tags, wikilinks, source
backlinks, and claim anchors. Treat it as read-only; durable edits go through
review proposals and canonical JSONL.

The market/architecture research behind this direction is in
`docs/market-research.md`.

## Checks

```bash
python3 -m unittest discover -s tests
python3 scripts/brain.py doctor
python3 scripts/brain.py wiki build
python3 scripts/brain.py site build
python3 scripts/brain.py obsidian export --path dist/obsidian
python3 scripts/brain.py serve --port 8765
```
