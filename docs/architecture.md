# WaiBrain v0 Architecture

WaiBrain is a governed memory system, not a note generator.

## Source of Truth

Canonical memory lives in structured ledgers:

- `knowledge/canonical/entities.jsonl`
- `knowledge/canonical/facts.jsonl`
- `knowledge/canonical/events.jsonl`
- `knowledge/canonical/relations.jsonl`
- `knowledge/canonical/evidence.jsonl`
- `knowledge/manifests/sources.jsonl`

Markdown and HTML are projections. They can be deleted and rebuilt from
canonical records.

## Review Lifecycle

1. Raw evidence is stored under `knowledge/raw/`.
2. An agent or CLI creates a `memory_upsert` proposal in
   `knowledge/review/proposals.jsonl`.
3. Pending proposals do not modify canonical memory.
4. A reviewer accepts or rejects the proposal.
5. Accepted proposals upsert canonical entities, facts, and events.
6. `python3 scripts/brain.py wiki build` regenerates Markdown.
7. `python3 scripts/brain.py site build` regenerates the local review UI.

This prevents AI slop from becoming memory by default.

## RAG Layer

RAG is a query layer over:

- accepted canonical records
- generated Markdown wiki pages
- immutable raw evidence

RAG may propose changes, but it must not write canonical truth directly.

## Markdown and HTML

Markdown is the durable human/agent reading format. HTML is the local review
surface. Neither is authoritative.

The generated wiki favors entity pages first because identity resolution and
deduplication are the first failure modes in multi-source memory.

Entity pages, source pages, YAML frontmatter, aliases, tags, wikilinks, and
claim anchors are generated for Obsidian and Quartz compatibility. The vault is
read-only from WaiBrain's point of view: manual edits should be converted into
raw sources or proposals, not treated as canonical writes.

## Review UX

The review surface is a memory inbox. A proposal should show:

- the current canonical state
- the proposed semantic diff
- exact evidence spans and quote hashes
- dedupe and conflict hints
- accept/reject actions with review reasons

High-risk proposals preserve uncertainty. Conflicting claims remain visible
until a reviewer explicitly supersedes, merges, rejects, or keeps both.

## Connector Boundary

Connectors should record source envelopes and raw artifacts. They must not write
facts directly. A connector can track provider ids, cursors, privacy class,
attachments, and sync state, then hand evidence to an extractor that creates
review proposals.

## v0 Boundaries

Implemented now:

- source hashing
- atomic JSONL writes
- pending typed review proposals
- accept/reject lifecycle
- entity merge proposals
- fact reinforcement, supersession, and conflict proposals
- relation proposals
- claim-level provenance with source spans and quote hashes
- quote-pinned evidence spans
- canonical entity/fact/event upserts
- canonical relation upserts
- generated Markdown entity and source pages
- Obsidian-compatible vault export
- generated static HTML review/workbench
- local live review server with browser accept/reject API
- reject reasons for review audit
- schema, provenance, source hash, and reference doctor checks
- local lexical search with wiki preference

Not implemented yet:

- explicit conflict-resolution proposals
- full temporal validity windows beyond supersede/conflict status
- vector embeddings/reranking
- Telegram/Gmail/voice connectors
- connector sync state and attachment manifests
