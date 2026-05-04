---
type: eval
title: "Golden retrieval questions"
created: 2026-05-04
tags: [eval]
---

# Golden Questions

Public-safe questions whose answers should be retrievable from this synthetic template vault.

## GQ001 — What is the wai-brain architecture?

- Expected source: `knowledge/wiki/concepts/agent-memory-architecture.md`
- Must mention: immutable raw evidence, compiled wiki, deterministic harness, Markdown canonical

## GQ002 — What must processing never do to raw files?

- Expected source: `knowledge/wiki/topics/raw-ingest-invariants.md`
- Must mention: never move, edit, delete, normalize, redact

## GQ003 — Where does private memory belong?

- Expected source: `knowledge/wiki/topics/public-private-boundary.md`
- Must mention: private vault, public template, no real raw captures

## GQ004 — What does the example project page demonstrate?

- Expected source: `knowledge/projects/example-research-project.md`
- Must mention: compiled truth, open threads, timeline, source citation

## GQ005 — Which commands verify the repo?

- Expected source: `knowledge/Home.md`
- Must mention: unittest, doctor, index --check, eval

## GQ006 — How should publication be handled if history ever contained private data?

- Expected source: `knowledge/wiki/topics/publication-history-safety.md`
- Must mention: fresh repo, rewrite history, do not toggle public

## GQ007 — What does the capture template do on command failure?

- Expected source: `knowledge/wiki/topics/capture-template-safety.md`
- Must mention: stop, retry once, do not mask failures

## GQ008 — What do source manifests store?

- Expected source: `knowledge/manifests/README.md`
- Must mention: source ids, content hashes, append-only

## GQ009 — What is the public-safety rule for chat IDs and server IPs?

- Expected source: `knowledge/wiki/topics/public-private-boundary.md`
- Must mention: do not commit, chat IDs, server IPs

## GQ010 — What is the purpose of skills in this repository?

- Expected source: `knowledge/wiki/topics/skill-workflows.md`
- Must mention: workflows, ingest, lint, eval

## GQ011 — Which files are safe to keep public?

- Expected source: `knowledge/wiki/topics/public-private-boundary.md`
- Must mention: generic scripts, reusable skills, synthetic examples, placeholder infra

## GQ012 — Which files must stay private?

- Expected source: `knowledge/wiki/topics/public-private-boundary.md`
- Must mention: real raw captures, private project pages, chat IDs, server IPs

## GQ013 — What is the design bias before adding vector search or graph storage?

- Expected source: `knowledge/wiki/concepts/agent-memory-architecture.md`
- Must mention: start with files, tests, evals, add database only when needed

## GQ014 — What does the synthetic raw source say the first milestone is?

- Expected source: `knowledge/raw/example/2026-05-04-example-source.md`
- Must mention: public-safe template release, no private data

## GQ015 — What does the decisions ledger say about separating public template and private vault?

- Expected source: `knowledge/decisions.md`
- Must mention: public-safe, generic code, synthetic examples, private vault

## GQ016 — What is the generated index file?

- Expected source: `knowledge/INDEX.md`
- Must mention: knowledge/wiki/INDEX.md, generated catalog

## GQ017 — What should the capture template never expose in replies?

- Expected source: `knowledge/wiki/topics/capture-template-safety.md`
- Must mention: raw filenames, slugs, local paths, internal tool errors

## GQ018 — What frontmatter fields does the generic capture template include?

- Expected source: `knowledge/wiki/topics/capture-template-safety.md`
- Must mention: type raw, source_id, captured_at, needs-pii-review

## GQ019 — What is recorded in the ingest log baseline?

- Expected source: `knowledge/wiki/log.md`
- Must mention: private content moved out, generic, synthetic, deterministic checks

## GQ020 — What does the README publishing warning say about deleted private files?

- Expected source: `knowledge/wiki/topics/publication-history-safety.md`
- Must mention: deleting private files, Git history, fresh public repo
