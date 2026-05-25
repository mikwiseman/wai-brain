# WaiBrain Next-Generation Memory Engine

Research snapshot: 2026-05-25.

WaiBrain should become a memory engine, not a note app, a RAG chatbot, or a
pretty export layer. The engine's job is to turn many private, changing sources
into reviewable, durable, agent-readable memory without losing provenance or
human control.

## Product Thesis

The winning memory product is a governed compiler:

```text
connectors -> raw evidence -> source manifests -> review proposals
-> accepted canonical memory -> generated wiki/site -> agent retrieval
```

RAG, embeddings, graph search, Markdown, HTML, and MCP are useful layers. None of
them is the source of truth.

## Non-Negotiable Invariants

1. Raw evidence is immutable.
2. AI output is not accepted truth.
3. Every canonical claim has source provenance.
4. Every write to canonical memory is reviewable and auditable.
5. Identity merge requires evidence stronger than display-name similarity.
6. Contradictions are preserved until a reviewer resolves them.
7. Generated wiki/site/search indexes are rebuildable projections.
8. Connectors are incremental and idempotent.
9. Agents can read accepted memory by default, but write only proposals.
10. Unknown is a valid answer when evidence or capability is missing.

## Architecture Layers

### 1. Connector Layer

Connectors read from MCP servers, APIs, local files, and exports. They must write
only source envelopes, raw artifacts, attachment manifests, and sync state.

Required records:

- `connector_state`: one row per connector/account/scope.
- `source_manifest`: one row per raw artifact or provider object.
- `attachment_manifest`: one row per fetched or deferred attachment.
- `ingestion_run`: one row per import/sync attempt.

Connectors must never create canonical facts directly.

### 2. Evidence Layer

Evidence is addressable by source id, path/URI, provider ids, checksum,
timestamp, and optional quote/span. Raw evidence should be enough to prove how a
memory was created without trusting an LLM summary.

### 3. Proposal Layer

The proposal layer is the AI write boundary. Extractors and agents create typed
proposals:

- `entity_create`
- `entity_merge`
- `fact_add`
- `fact_reinforce`
- `fact_supersede`
- `fact_conflict`
- `event_add`
- `relation_add`
- `source_import`
- `privacy_review`
- `connector_error`

Each proposal must carry evidence refs, confidence, privacy class, and a
reviewer-facing reason.

### 4. Canonical Memory Layer

Canonical memory is structured JSONL today and can later move to SQLite or a
graph store without changing the contract.

Core ledgers:

- entities
- facts
- events
- relations
- evidence
- source manifests
- connector state
- review decisions

Canonical records should prefer statement-level structure over prose. Pages are
rendered from statements, not handwritten as truth.

### 5. Temporal Graph Layer

Next-generation memory needs time:

- `observed_at`: when the source said it.
- `valid_from` / `valid_until`: when the claim is true.
- `recorded_at`: when WaiBrain learned it.
- `reviewed_at`: when a human accepted it.
- `superseded_by` / `invalidated_by`: why it is no longer current.

The system should not overwrite memory. It should move claims through states.

### 6. Retrieval Layer

Retrieval should be hybrid:

- keyword/BM25 for exact names, ids, dates, emails, and rare terms
- embeddings for semantic candidate generation
- graph traversal for entities, relations, source chains, and timelines
- reranking for final context assembly

Retrieval can answer questions and propose updates. It cannot mutate canonical
truth.

### 7. Human Wiki Layer

The user-facing site should feel like a personal wiki, not a database console.

Default surfaces:

- Wiki home
- Search
- People, projects, organizations, places, and topics
- Sources
- Review Inbox
- Conflicts
- Recent changes

Technical data stays available behind "Source" and "Details", but the main UI
uses human language.

### 8. Agent API Layer

Agents need a stable interface:

- `search_memory(query, mode, limit)`
- `read_entity(entity_id)`
- `read_source(source_id)`
- `list_pending_reviews(filters)`
- `propose_memory_change(payload)`
- `explain_memory(record_id)`
- `answer_with_citations(question)`

The API must distinguish accepted, pending, contradicted, superseded, rejected,
and unknown states.

## MCP-First Runtime

If MCP servers are already connected, WaiBrain should treat them as source
adapters, not as trusted memory.

MCP run order:

1. Inventory servers, tools, resources, auth state, and scopes.
2. Run read-only smoke tests with small limits.
3. Classify each source by privacy and mutability risk.
4. Read bounded metadata pages before fetching content.
5. Write source manifests and raw artifacts.
6. Create review proposals.
7. Build wiki/site.
8. Verify agent read-back through the same interface agents will use.

Write/send/delete/share/publish tools require explicit per-action approval.

## Anti-Slop Controls

The engine should measure and block the common memory failure modes:

- duplicate entities
- duplicate claims
- ungrounded facts
- stale claims presented as current
- name-only merges
- source-less summaries
- private data in public views
- generated Markdown edited as truth
- pending proposals used as accepted memory
- MCP tool output treated as complete corpus

`doctor` should eventually become a full memory auditor, not only a schema
checker.

## Roadmap

### v0.1 Current Base

Implemented:

- raw/review/canonical/wiki/site split
- typed proposals
- accept/reject lifecycle
- entity merge proposals
- fact reinforcement/supersede/conflict handling
- claim-level provenance
- generated Markdown and HTML review surface
- local lexical search
- doctor checks

### v0.2 Connector Backbone

Add:

- connector state ledger
- source manifest enrichment
- ingestion run ledger
- idempotency keys for provider objects
- page/cursor budgets
- privacy classes
- connector error proposals

### v0.3 Memory Auditor

Add:

- duplicate entity report
- duplicate claim report
- unsupported claim report
- stale claim report
- pending-vs-canonical leakage checks
- private-data leakage checks for generated site/wiki

### v0.4 Agent Read API

Add:

- structured search/read/explain commands
- accepted/pending/unknown separation
- citation chains
- MCP-compatible read server

### v0.5 Temporal Graph

Add:

- temporal validity windows
- source episodes
- graph traversal
- relationship timeline pages
- conflict resolution proposals

### v1.0 User Product

Ship:

- local web wiki
- review inbox with plain-language labels
- source viewer
- search with citations
- MCP connector inventory
- safe scheduler for read-only sync and rebuild
- one-command local start

## First Implementation Slice

The next useful code slice is `connector_state` and richer source manifests.
Without this, MCP-connected sources cannot update safely over time.

Acceptance criteria:

- `knowledge/manifests/connectors.jsonl` exists in the layout.
- CLI can upsert/list connector state without touching canonical memory.
- Connector state includes provider, account, scope, cursor, status, privacy
  class, sync window, and last error.
- `doctor` validates connector state schema and warns on stale/error states.
- Tests prove connector upserts are idempotent.

