# WaiBrain Market And Architecture Research

Research date: 2026-05-24.

## Consensus

No ready-made tool covers the whole target loop:

1. many input sources
2. immutable raw evidence
3. AI-generated proposals only
4. human review before canonical memory
5. structured entities, facts, events, and relations
6. generated Markdown wiki
7. Obsidian/Quartz-friendly publishing

WaiBrain should stay a governed memory compiler. RAG, graph search,
embeddings, static sites, and Obsidian vaults are projections over accepted
canonical memory, not the source of truth.

## References Worth Copying

- GBrain: typed brain repository, doctor checks, capture, hybrid retrieval,
  temporal claims, and agent-facing CLI/MCP ideas.
  https://github.com/garrytan/gbrain
- Karpathy LLM Wiki: raw sources plus compiled Markdown wiki as a practical
  Obsidian-first second brain pattern.
  https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Graphiti/Zep: temporal knowledge graph, episodes, validity windows, and
  provenance-first retrieval.
  https://github.com/getzep/graphiti
- Onyx/Danswer: connector model, metadata, sync observability, and permission
  boundaries for many input sources.
  https://docs.onyx.app/overview/core_features/connectors
- Obsidian: local Markdown vault, YAML properties, tags, aliases, and backlinks.
  https://help.obsidian.md/properties
- Quartz 4: Obsidian-style publishing with backlinks, graph, search, and
  frontmatter support.
  https://quartz.jzhao.xyz/
- Wikibase/Wikidata: statements with references, qualifiers, and rank.
  https://www.mediawiki.org/wiki/Wikibase/DataModel
  https://www.wikidata.org/wiki/Help:Ranking
- W3C PROV: provenance as structured relations between entities, activities,
  and agents.
  https://www.w3.org/TR/prov-o/

## What To Borrow

- From GBrain: schema-aware CLI, doctor/remediate, typed claims, and hybrid
  search as a rebuildable layer.
- From Karpathy: Markdown wiki, source logs, Obsidian as the human IDE, and git
  as history.
- From Graphiti/Zep: temporal facts, conflict preservation, and evidence-backed
  graph edges.
- From Onyx: connector contracts, incremental sync state, source metadata, and
  permissions.
- From Obsidian/Quartz: YAML frontmatter, aliases, tags, wikilinks, backlinks,
  and graph publishing.
- From Wikibase: fact statements should support qualifiers, references, status,
  and rank instead of page-level prose.

## Product Stance

WaiBrain is not a notes app and not a RAG chat app. It is the reviewable memory
compiler between messy private sources and clean human-readable projections.

The invariant is:

```text
raw evidence -> proposals -> review -> canonical JSONL -> wiki/site/Obsidian/RAG
```

AI can read everything it is allowed to read. It can propose memory changes. It
cannot write accepted truth directly.

