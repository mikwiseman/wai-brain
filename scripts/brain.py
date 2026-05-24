#!/usr/bin/env python3
"""Local-first WaiBrain maintenance CLI.

The canonical store is structured JSONL under knowledge/canonical. Markdown
and HTML are generated views. AI-generated memory must enter through review
proposals before it becomes canonical.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import http.server
import json
import math
import os
import re
import sys
import tempfile
import threading
import webbrowser
from dataclasses import dataclass, field
from collections import Counter
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse


TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_]+", re.UNICODE)
SCHEMA_VERSION = 1
ACTIVE_FACT_STATUSES = {"active", "contradicted"}
ENTITY_STATUSES = {"active", "merged", "forgotten", "deleted"}
FACT_STATUSES = {"active", "superseded", "contradicted", "rejected", "forgotten", "deleted"}
PROPOSAL_KINDS = {
    "entity_create",
    "entity_merge",
    "event_add",
    "fact_add",
    "fact_conflict",
    "fact_reinforce",
    "fact_supersede",
    "memory_upsert",
}
PROPOSAL_STATUSES = {"pending", "accepted", "rejected", "blocked"}
SECRET_PATTERNS = [
    ("OpenAI-style secret", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("GitHub token", re.compile(r"(?:github_pat_|ghp_)[A-Za-z0-9_]{20,}")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}")),
    ("public IPv4 address", re.compile(r"\b(?!127\.0\.0\.1|10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[0-1])\.)(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("Telegram-style chat id", re.compile(r"(?<![A-Za-z0-9])-100\d{7,}|(?<![A-Za-z0-9])-\d{9,}")),
]

LAYOUT_FILES = [
    "knowledge/canonical/evidence.jsonl",
    "knowledge/canonical/entities.jsonl",
    "knowledge/canonical/facts.jsonl",
    "knowledge/canonical/events.jsonl",
    "knowledge/canonical/relations.jsonl",
    "knowledge/manifests/sources.jsonl",
    "knowledge/review/proposals.jsonl",
]

LAYOUT_DIRS = [
    "knowledge/raw",
    "knowledge/wiki/entities",
    "knowledge/wiki/topics",
    "knowledge/site",
    "knowledge/review/archive",
]


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        return not self.errors

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    value = value.strip().lower().replace("ё", "е")
    value = re.sub(r"[^a-z0-9а-я]+", "-", value, flags=re.IGNORECASE)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "untitled"


def stable_hash(value: Any, length: int = 16) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel_path(root: Path, path: Path) -> str:
    root_abs = root.resolve()
    path_abs = path.resolve()
    try:
        return path_abs.relative_to(root_abs).as_posix()
    except ValueError as exc:
        raise ValueError(f"path is outside wai-brain root: {path}") from exc


def ensure_layout(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for directory in LAYOUT_DIRS:
        (root / directory).mkdir(parents=True, exist_ok=True)
    for filename in LAYOUT_FILES:
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("", encoding="utf-8")
    home = root / "knowledge/Home.md"
    if not home.exists():
        home.write_text("# WaiBrain\n\nLocal-first memory with review before canonical writes.\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSONL: {exc.msg}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"{path}:{line_no}: JSONL record must be an object")
        records.append(item)
    return records


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    text = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    atomic_write_text(path, text)


def upsert_by_id(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    records = read_jsonl(path)
    for index, existing in enumerate(records):
        if existing.get("id") == record.get("id"):
            records[index] = record
            write_jsonl(path, records)
            return record
    records.append(record)
    write_jsonl(path, records)
    return record


def add_source(root: Path, source_path: Path) -> dict[str, Any]:
    ensure_layout(root)
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    rel = rel_path(root, source_path)
    digest = file_hash(source_path)
    source_id = "src_" + stable_hash({"path": rel, "sha256": digest}, 12)
    sources_path = root / "knowledge/manifests/sources.jsonl"
    existing = {item["id"]: item for item in read_jsonl(sources_path)}
    status = "already-recorded" if source_id in existing else "recorded"
    record = existing.get(source_id) or {
        "schema_version": SCHEMA_VERSION,
        "id": source_id,
        "path": rel,
        "sha256": digest,
        "created_at": now_iso(),
        "kind": "raw",
        "status": "active",
    }
    record["updated_at"] = now_iso()
    record["status"] = status
    upsert_by_id(sources_path, record)
    return record


def evidence_for_source(root: Path, source: dict[str, Any]) -> dict[str, Any]:
    source_path = root / str(source["path"])
    text = source_path.read_text(encoding="utf-8", errors="ignore")
    span = {"start": 0, "end": len(text)}
    excerpt = re.sub(r"\s+", " ", text).strip()[:500]
    quote_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    evidence_id = "ev_" + stable_hash({"source_id": source["id"], "span": span, "quote_hash": quote_hash}, 16)
    return {
        "schema_version": SCHEMA_VERSION,
        "id": evidence_id,
        "source_id": source["id"],
        "source_path": source["path"],
        "source_sha256": source["sha256"],
        "span": span,
        "quote_hash": quote_hash,
        "excerpt": excerpt,
        "created_at": now_iso(),
    }


def provenance_from_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": item["id"],
            "source_id": item["source_id"],
            "span": item["span"],
            "quote_hash": item["quote_hash"],
        }
        for item in evidence
    ]


def normalize_entity(entity: dict[str, Any], source_ids: list[str]) -> dict[str, Any]:
    name = str(entity.get("name") or "").strip()
    if not name:
        raise ValueError("entity.name is required")
    entity_type = slugify(str(entity.get("type") or "note"))
    entity_id = f"{entity_type}/{slugify(name)}"
    aliases = sorted({str(alias).strip() for alias in entity.get("aliases", []) if str(alias).strip()})
    return {
        "schema_version": SCHEMA_VERSION,
        "id": entity_id,
        "type": entity_type,
        "name": name,
        "aliases": aliases,
        "status": "active",
        "merged_into": None,
        "source_ids": sorted(set(source_ids)),
    }


def normalize_fact(
    entity_id: str,
    fact: dict[str, Any],
    source_ids: list[str],
    provenance: list[dict[str, Any]],
    *,
    status: str = "active",
) -> dict[str, Any]:
    predicate = str(fact.get("predicate") or "").strip()
    value = str(fact.get("value") or "").strip()
    if not predicate or not value:
        raise ValueError("fact.predicate and fact.value are required")
    valid_at = fact.get("valid_at")
    fact_id = "fact_" + stable_hash({"entity_id": entity_id, "predicate": predicate, "value": value, "valid_at": valid_at})
    confidence = float(fact.get("confidence", 0.5))
    return {
        "schema_version": SCHEMA_VERSION,
        "id": fact_id,
        "entity_id": entity_id,
        "subject_id": entity_id,
        "predicate": predicate,
        "slot_key": str(fact.get("slot_key") or predicate),
        "cardinality": str(fact.get("cardinality") or "single"),
        "value": value,
        "confidence": max(0.0, min(1.0, confidence)),
        "valid_at": valid_at,
        "invalid_at": fact.get("invalid_at"),
        "status": status,
        "supersedes": list(fact.get("supersedes", [])),
        "superseded_by": fact.get("superseded_by"),
        "provenance": provenance,
        "source_ids": sorted(set(source_ids)),
    }


def normalize_event(entity_id: str, event: dict[str, Any], source_ids: list[str], provenance: list[dict[str, Any]]) -> dict[str, Any]:
    summary = str(event.get("summary") or "").strip()
    if not summary:
        raise ValueError("event.summary is required")
    date = str(event.get("date") or dt.date.today().isoformat())
    event_id = "evt_" + stable_hash({"entity_id": entity_id, "date": date, "summary": summary})
    return {
        "schema_version": SCHEMA_VERSION,
        "id": event_id,
        "entity_id": entity_id,
        "date": date,
        "summary": summary,
        "status": "active",
        "provenance": provenance,
        "source_ids": sorted(set(source_ids)),
    }


def normalize_fact_value(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower().replace("ё", "е"))


def existing_slot_facts(root: Path, entity_id: str, predicate: str) -> list[dict[str, Any]]:
    return [
        fact
        for fact in read_jsonl(root / "knowledge/canonical/facts.jsonl")
        if fact.get("entity_id") == entity_id
        and fact.get("predicate") == predicate
        and fact.get("status") in ACTIVE_FACT_STATUSES
    ]


def typed_fact_operations(root: Path, fact_record: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    existing = existing_slot_facts(root, str(fact_record["entity_id"]), str(fact_record["predicate"]))
    if not existing:
        return "fact_add", "low", [{"op": "insert_fact", "record": fact_record}]

    same_value = [
        fact
        for fact in existing
        if normalize_fact_value(fact.get("value")) == normalize_fact_value(fact_record.get("value"))
    ]
    if same_value:
        return "fact_reinforce", "low", [
            {
                "op": "reinforce_fact",
                "id": same_value[0]["id"],
                "provenance": fact_record.get("provenance", []),
                "source_ids": fact_record.get("source_ids", []),
                "confidence": fact_record.get("confidence", 0.5),
            }
        ]

    if fact_record.get("valid_at"):
        old_ids = [fact["id"] for fact in existing]
        record = dict(fact_record)
        record["supersedes"] = old_ids
        operations = [{"op": "set_fact_status", "id": old_id, "status": "superseded", "superseded_by": record["id"]} for old_id in old_ids]
        operations.append({"op": "insert_fact", "record": record})
        return "fact_supersede", "medium", operations

    record = dict(fact_record)
    record["status"] = "contradicted"
    operations = [{"op": "set_fact_status", "id": fact["id"], "status": "contradicted"} for fact in existing]
    operations.append({"op": "insert_fact", "record": record})
    return "fact_conflict", "high", operations


def create_memory_proposal(
    root: Path,
    *,
    title: str,
    source_paths: list[Path],
    entity: dict[str, Any],
    facts: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    sources = [add_source(root, path) for path in source_paths]
    source_ids = sorted({source["id"] for source in sources})
    evidence = [evidence_for_source(root, source) for source in sources]
    provenance = provenance_from_evidence(evidence)
    entity_record = normalize_entity(entity, source_ids)
    fact_records = [normalize_fact(entity_record["id"], fact, source_ids, provenance) for fact in facts or []]
    event_records = [normalize_event(entity_record["id"], event, source_ids, provenance) for event in events or []]
    operations: list[dict[str, Any]] = [{"op": "insert_evidence", "record": item} for item in evidence]
    operations.append({"op": "insert_entity", "record": entity_record})
    proposal_kind = "entity_create"
    risk = "low"
    for fact_record in fact_records:
        kind, fact_risk, fact_ops = typed_fact_operations(root, fact_record)
        proposal_kind = kind if proposal_kind == "entity_create" else "memory_upsert"
        if fact_risk == "high" or risk == "high":
            risk = "high"
        elif fact_risk == "medium" or risk == "medium":
            risk = "medium"
        operations.extend(fact_ops)
    for event_record in event_records:
        proposal_kind = "event_add" if proposal_kind == "entity_create" else proposal_kind
        operations.append({"op": "insert_event", "record": event_record})
    payload = {"entity": entity_record, "facts": fact_records, "events": event_records, "evidence": evidence}
    proposal_id = "prop_" + stable_hash(
        {
            "title": title,
            "entity_id": entity_record["id"],
            "fact_ids": [fact["id"] for fact in fact_records],
            "event_ids": [event["id"] for event in event_records],
            "source_ids": source_ids,
        }
    )
    proposals_path = root / "knowledge/review/proposals.jsonl"
    existing = {item["id"]: item for item in read_jsonl(proposals_path)}
    if proposal_id in existing:
        return existing[proposal_id]
    proposal = {
        "schema_version": SCHEMA_VERSION,
        "id": proposal_id,
        "kind": proposal_kind,
        "title": title,
        "status": "pending",
        "risk": risk,
        "target_ids": [entity_record["id"], *[fact["id"] for fact in fact_records], *[event["id"] for event in event_records]],
        "source_ids": source_ids,
        "payload": payload,
        "operations": operations,
        "preconditions": [],
        "created_at": now_iso(),
        "decided_at": None,
    }
    upsert_by_id(proposals_path, proposal)
    return proposal


def pending_proposals(root: Path) -> list[dict[str, Any]]:
    return [item for item in read_jsonl(root / "knowledge/review/proposals.jsonl") if item.get("status") == "pending"]


def _merge_list(left: Iterable[Any], right: Iterable[Any]) -> list[Any]:
    return sorted({item for item in [*left, *right] if item is not None})


def _upsert_entity(root: Path, record: dict[str, Any]) -> None:
    path = root / "knowledge/canonical/entities.jsonl"
    records = read_jsonl(path)
    for index, existing in enumerate(records):
        if existing.get("id") == record["id"]:
            merged = dict(existing)
            merged["name"] = existing.get("name") or record["name"]
            merged["type"] = existing.get("type") or record["type"]
            merged["status"] = existing.get("status") or record.get("status", "active")
            merged["merged_into"] = existing.get("merged_into")
            merged["aliases"] = _merge_list(existing.get("aliases", []), record.get("aliases", []))
            merged["source_ids"] = _merge_list(existing.get("source_ids", []), record.get("source_ids", []))
            merged["updated_at"] = now_iso()
            records[index] = merged
            write_jsonl(path, records)
            return
    fresh = dict(record)
    fresh["created_at"] = now_iso()
    fresh["updated_at"] = fresh["created_at"]
    records.append(fresh)
    write_jsonl(path, records)


def _upsert_canonical_record(root: Path, filename: str, record: dict[str, Any]) -> None:
    path = root / f"knowledge/canonical/{filename}"
    records = read_jsonl(path)
    for index, existing in enumerate(records):
        if existing.get("id") == record["id"]:
            merged = dict(existing)
            merged.update(record)
            merged["source_ids"] = _merge_list(existing.get("source_ids", []), record.get("source_ids", []))
            if "confidence" in existing or "confidence" in record:
                merged["confidence"] = max(float(existing.get("confidence", 0.0)), float(record.get("confidence", 0.0)))
            merged["updated_at"] = now_iso()
            records[index] = merged
            write_jsonl(path, records)
            return
    fresh = dict(record)
    fresh["created_at"] = now_iso()
    fresh["updated_at"] = fresh["created_at"]
    records.append(fresh)
    write_jsonl(path, records)


def _update_record(root: Path, filename: str, record_id: str, updates: dict[str, Any]) -> None:
    path = root / f"knowledge/canonical/{filename}"
    records = read_jsonl(path)
    for index, existing in enumerate(records):
        if existing.get("id") == record_id:
            updated = dict(existing)
            updated.update(updates)
            updated["updated_at"] = now_iso()
            records[index] = updated
            write_jsonl(path, records)
            return
    raise KeyError(f"{filename} record not found: {record_id}")


def _reinforce_fact(root: Path, fact_id: str, provenance: list[dict[str, Any]], source_ids: list[str], confidence: float) -> None:
    path = root / "knowledge/canonical/facts.jsonl"
    records = read_jsonl(path)
    for index, fact in enumerate(records):
        if fact.get("id") != fact_id:
            continue
        updated = dict(fact)
        existing_provenance = updated.get("provenance", [])
        seen = {item.get("evidence_id") for item in existing_provenance if isinstance(item, dict)}
        for item in provenance:
            if item.get("evidence_id") not in seen:
                existing_provenance.append(item)
        updated["provenance"] = existing_provenance
        updated["source_ids"] = _merge_list(updated.get("source_ids", []), source_ids)
        updated["confidence"] = max(float(updated.get("confidence", 0.0)), float(confidence))
        updated["updated_at"] = now_iso()
        records[index] = updated
        write_jsonl(path, records)
        return
    raise KeyError(f"fact not found: {fact_id}")


def _merge_entities(root: Path, winner_id: str, loser_id: str, reason: str) -> None:
    path = root / "knowledge/canonical/entities.jsonl"
    records = read_jsonl(path)
    by_id = {record.get("id"): record for record in records}
    if winner_id not in by_id:
        raise KeyError(f"winner entity not found: {winner_id}")
    if loser_id not in by_id:
        raise KeyError(f"loser entity not found: {loser_id}")
    winner = dict(by_id[winner_id])
    loser = dict(by_id[loser_id])
    winner["aliases"] = _merge_list(
        [winner.get("name"), *winner.get("aliases", [])],
        [loser.get("name"), *loser.get("aliases", [])],
    )
    winner["source_ids"] = _merge_list(winner.get("source_ids", []), loser.get("source_ids", []))
    winner["updated_at"] = now_iso()
    loser["status"] = "merged"
    loser["merged_into"] = winner_id
    loser["merge_reason"] = reason
    loser["updated_at"] = now_iso()
    updated_records = []
    for record in records:
        if record.get("id") == winner_id:
            updated_records.append(winner)
        elif record.get("id") == loser_id:
            updated_records.append(loser)
        else:
            updated_records.append(record)
    write_jsonl(path, updated_records)


def apply_operation(root: Path, operation: dict[str, Any]) -> None:
    op = operation.get("op")
    if op == "insert_evidence":
        _upsert_canonical_record(root, "evidence.jsonl", operation["record"])
    elif op == "insert_entity":
        _upsert_entity(root, operation["record"])
    elif op == "insert_fact":
        _upsert_canonical_record(root, "facts.jsonl", operation["record"])
    elif op == "insert_event":
        _upsert_canonical_record(root, "events.jsonl", operation["record"])
    elif op == "set_fact_status":
        updates = {"status": operation["status"]}
        if operation.get("superseded_by"):
            updates["superseded_by"] = operation["superseded_by"]
        _update_record(root, "facts.jsonl", operation["id"], updates)
    elif op == "reinforce_fact":
        _reinforce_fact(
            root,
            str(operation["id"]),
            list(operation.get("provenance", [])),
            list(operation.get("source_ids", [])),
            float(operation.get("confidence", 0.5)),
        )
    elif op == "merge_entity":
        _merge_entities(root, str(operation["winner_id"]), str(operation["loser_id"]), str(operation.get("reason") or ""))
    else:
        raise ValueError(f"unknown operation: {op}")


def _set_proposal_status(root: Path, proposal_id: str, status: str) -> dict[str, Any]:
    proposals_path = root / "knowledge/review/proposals.jsonl"
    proposals = read_jsonl(proposals_path)
    for index, proposal in enumerate(proposals):
        if proposal.get("id") != proposal_id:
            continue
        current = proposal.get("status")
        if current == status:
            already = dict(proposal)
            already["status"] = f"already-{status}"
            return already
        if current != "pending":
            blocked = dict(proposal)
            blocked["status"] = f"already-{current}"
            return blocked
        proposal = dict(proposal)
        proposal["status"] = status
        proposal["decided_at"] = now_iso()
        proposals[index] = proposal
        write_jsonl(proposals_path, proposals)
        return proposal
    raise KeyError(f"proposal not found: {proposal_id}")


def accept_proposal(root: Path, proposal_id: str) -> dict[str, Any]:
    ensure_layout(root)
    proposals = {item["id"]: item for item in read_jsonl(root / "knowledge/review/proposals.jsonl")}
    proposal = proposals.get(proposal_id)
    if not proposal:
        raise KeyError(f"proposal not found: {proposal_id}")
    if proposal.get("status") == "accepted":
        already = dict(proposal)
        already["status"] = "already-accepted"
        return already
    if proposal.get("status") != "pending":
        already = dict(proposal)
        already["status"] = f"already-{proposal.get('status')}"
        return already

    operations = proposal.get("operations")
    if operations:
        for operation in operations:
            apply_operation(root, operation)
    else:
        payload = proposal.get("payload") or {}
        _upsert_entity(root, payload["entity"])
        for fact in payload.get("facts", []):
            _upsert_canonical_record(root, "facts.jsonl", fact)
        for event in payload.get("events", []):
            _upsert_canonical_record(root, "events.jsonl", event)
    return _set_proposal_status(root, proposal_id, "accepted")


def reject_proposal(root: Path, proposal_id: str) -> dict[str, Any]:
    ensure_layout(root)
    return _set_proposal_status(root, proposal_id, "rejected")


def create_entity_merge_proposal(root: Path, *, winner_id: str, loser_id: str, reason: str) -> dict[str, Any]:
    ensure_layout(root)
    entities = {entity["id"]: entity for entity in read_jsonl(root / "knowledge/canonical/entities.jsonl")}
    if winner_id not in entities:
        raise KeyError(f"winner entity not found: {winner_id}")
    if loser_id not in entities:
        raise KeyError(f"loser entity not found: {loser_id}")
    proposal_id = "prop_" + stable_hash({"kind": "entity_merge", "winner_id": winner_id, "loser_id": loser_id, "reason": reason})
    proposals_path = root / "knowledge/review/proposals.jsonl"
    existing = {item["id"]: item for item in read_jsonl(proposals_path)}
    if proposal_id in existing:
        return existing[proposal_id]
    proposal = {
        "schema_version": SCHEMA_VERSION,
        "id": proposal_id,
        "kind": "entity_merge",
        "title": f"Merge {loser_id} into {winner_id}",
        "status": "pending",
        "risk": "medium",
        "target_ids": [winner_id, loser_id],
        "source_ids": _merge_list(entities[winner_id].get("source_ids", []), entities[loser_id].get("source_ids", [])),
        "payload": {"winner_id": winner_id, "loser_id": loser_id, "reason": reason},
        "operations": [{"op": "merge_entity", "winner_id": winner_id, "loser_id": loser_id, "reason": reason}],
        "preconditions": [
            {"record_id": winner_id, "status": entities[winner_id].get("status", "active")},
            {"record_id": loser_id, "status": entities[loser_id].get("status", "active")},
        ],
        "created_at": now_iso(),
        "decided_at": None,
    }
    upsert_by_id(proposals_path, proposal)
    return proposal


def sources_by_id(root: Path) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in read_jsonl(root / "knowledge/manifests/sources.jsonl")}


def source_refs(source_ids: Iterable[str], sources: dict[str, dict[str, Any]]) -> str:
    refs = []
    for source_id in source_ids:
        source = sources.get(source_id)
        label = source.get("path") if source else source_id
        refs.append(f"[Source: {label}]")
    return " ".join(refs)


def build_wiki(root: Path) -> list[Path]:
    ensure_layout(root)
    entities = [item for item in read_jsonl(root / "knowledge/canonical/entities.jsonl") if item.get("status", "active") == "active"]
    all_facts = read_jsonl(root / "knowledge/canonical/facts.jsonl")
    facts = [item for item in all_facts if item.get("status") == "active"]
    conflicted_facts = [item for item in all_facts if item.get("status") == "contradicted"]
    events = [item for item in read_jsonl(root / "knowledge/canonical/events.jsonl") if item.get("status") == "active"]
    sources = sources_by_id(root)
    facts_by_entity: dict[str, list[dict[str, Any]]] = {}
    conflicts_by_entity: dict[str, list[dict[str, Any]]] = {}
    events_by_entity: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        facts_by_entity.setdefault(str(fact.get("entity_id")), []).append(fact)
    for fact in conflicted_facts:
        conflicts_by_entity.setdefault(str(fact.get("entity_id")), []).append(fact)
    for event in events:
        events_by_entity.setdefault(str(event.get("entity_id")), []).append(event)

    written: list[Path] = []
    index_lines = ["# WaiBrain Wiki Index", "", "Generated from canonical memory records.", ""]
    for entity in sorted(entities, key=lambda item: (str(item.get("type")), str(item.get("name")))):
        entity_id = str(entity["id"])
        entity_type, slug = entity_id.split("/", 1)
        path = root / "knowledge/wiki/entities" / entity_type / f"{slug}.md"
        entity_facts = sorted(facts_by_entity.get(entity_id, []), key=lambda item: str(item.get("predicate")))
        entity_conflicts = sorted(conflicts_by_entity.get(entity_id, []), key=lambda item: (str(item.get("predicate")), str(item.get("value"))))
        entity_events = sorted(events_by_entity.get(entity_id, []), key=lambda item: str(item.get("date")), reverse=True)
        summary = entity_facts[0]["value"] if entity_facts else "Conflicting facts need review." if entity_conflicts else "No accepted facts yet."
        lines = [
            "---",
            "type: entity",
            f"entity_id: {entity_id}",
            f"title: {json.dumps(entity['name'], ensure_ascii=False)}",
            "generated_from: canonical",
            f"generated_at: {now_iso()}",
            "---",
            "",
            f"# {entity['name']}",
            "",
            f"> {summary}",
            "",
            "## State",
            "",
        ]
        if entity.get("aliases"):
            lines.append(f"- **Aliases:** {', '.join(entity['aliases'])}")
        if entity_facts:
            for fact in entity_facts:
                confidence = float(fact.get("confidence", 0.0))
                lines.append(
                    f"- **{fact['predicate']}:** {fact['value']} "
                    f"(confidence: {confidence:.2f}) {source_refs(fact.get('source_ids', []), sources)}"
                )
        else:
            lines.append("- No accepted facts.")
        if entity_conflicts:
            lines.extend(["", "## Open Conflicts", ""])
            conflicts_by_slot: dict[str, list[dict[str, Any]]] = {}
            for fact in entity_conflicts:
                conflicts_by_slot.setdefault(str(fact.get("predicate")), []).append(fact)
            for predicate, slot_facts in sorted(conflicts_by_slot.items()):
                lines.append(f"### {predicate}")
                for fact in slot_facts:
                    lines.append(f"- {fact['value']} {source_refs(fact.get('source_ids', []), sources)}")
        lines.extend(["", "## Timeline", ""])
        if entity_events:
            for event in entity_events:
                lines.append(f"- **{event['date']}** | {event['summary']} {source_refs(event.get('source_ids', []), sources)}")
        else:
            lines.append("- No accepted events.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        written.append(path)
        index_lines.append(f"- [{entity['name']}](entities/{entity_type}/{slug}.md) - `{entity_id}`")
    index_path = root / "knowledge/wiki/INDEX.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("\n".join(index_lines).rstrip() + "\n", encoding="utf-8")
    written.append(index_path)
    return written


def build_site(root: Path) -> Path:
    ensure_layout(root)
    proposals = read_jsonl(root / "knowledge/review/proposals.jsonl")
    pending = [item for item in proposals if item.get("status") == "pending"]
    entities = read_jsonl(root / "knowledge/canonical/entities.jsonl")
    facts = [item for item in read_jsonl(root / "knowledge/canonical/facts.jsonl") if item.get("status") == "active"]
    sources = sources_by_id(root)
    facts_by_entity: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        facts_by_entity.setdefault(str(fact.get("entity_id")), []).append(fact)

    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)

    review_cards = []
    for proposal in pending:
        payload = proposal.get("payload", {})
        entity = payload.get("entity", {})
        fact_items = "".join(f"<li>{esc(f.get('predicate'))}: {esc(f.get('value'))}</li>" for f in payload.get("facts", []))
        evidence_items = "".join(
            f"<li><code>{esc(item.get('source_path'))}</code><br>{esc(item.get('excerpt'))}</li>"
            for item in payload.get("evidence", [])
        )
        operation_items = "".join(
            f"<li><code>{esc(op.get('op'))}</code> {esc(op.get('id') or op.get('winner_id') or op.get('record', {}).get('id') or '')}</li>"
            for op in proposal.get("operations", [])
        )
        review_cards.append(
            "<article class=\"card\">"
            f"<div class=\"eyebrow\">{esc(proposal.get('kind'))} / {esc(proposal.get('risk', 'low'))}</div><h3>{esc(proposal.get('title'))}</h3>"
            f"<p><strong>{esc(entity.get('name', 'unknown'))}</strong> <code>{esc(entity.get('id', ''))}</code></p>"
            f"<ul>{fact_items or '<li>No facts in proposal.</li>'}</ul>"
            f"<h4>Evidence</h4><ul>{evidence_items or '<li>No evidence spans.</li>'}</ul>"
            f"<h4>Semantic diff</h4><ul>{operation_items or '<li>No operations.</li>'}</ul>"
            f"<p class=\"muted\">{esc(source_refs(proposal.get('source_ids', []), sources))}</p>"
            f"<code>python3 scripts/brain.py review accept {esc(proposal.get('id'))}</code>"
            "</article>"
        )

    canonical_cards = []
    conflicts_by_entity: dict[str, list[dict[str, Any]]] = {}
    for fact in read_jsonl(root / "knowledge/canonical/facts.jsonl"):
        if fact.get("status") == "contradicted":
            conflicts_by_entity.setdefault(str(fact.get("entity_id")), []).append(fact)
    for entity in entities:
        entity_facts = facts_by_entity.get(str(entity.get("id")), [])
        entity_conflicts = conflicts_by_entity.get(str(entity.get("id")), [])
        fact_items = "".join(f"<li><strong>{esc(f.get('predicate'))}</strong>: {esc(f.get('value'))}</li>" for f in entity_facts)
        conflict_items = "".join(f"<li><strong>{esc(f.get('predicate'))}</strong>: {esc(f.get('value'))}</li>" for f in entity_conflicts)
        canonical_cards.append(
            "<article class=\"card\">"
            f"<div class=\"eyebrow\">{esc(entity.get('type'))}</div><h3>{esc(entity.get('name'))}</h3>"
            f"<p><code>{esc(entity.get('id'))}</code></p>"
            f"<ul>{fact_items or '<li>No accepted facts yet.</li>'}</ul>"
            f"{'<h4>Open conflicts</h4><ul>' + conflict_items + '</ul>' if conflict_items else ''}"
            "</article>"
        )

    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WaiBrain Review</title>
  <style>
    :root {{ color-scheme: light; --ink: #17201a; --muted: #68736b; --line: #dce4dd; --bg: #f7f8f5; --card: #ffffff; --accent: #245c4f; }}
    body {{ margin: 0; font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: var(--bg); }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 48px; }}
    header {{ display: flex; justify-content: space-between; gap: 16px; align-items: end; border-bottom: 1px solid var(--line); padding-bottom: 18px; margin-bottom: 24px; }}
    h1 {{ font-size: 28px; margin: 0; letter-spacing: 0; }}
    h2 {{ font-size: 18px; margin: 28px 0 12px; }}
    h3 {{ font-size: 16px; margin: 4px 0 8px; }}
    h4 {{ font-size: 13px; margin: 12px 0 4px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }}
    .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }}
    .eyebrow {{ color: var(--accent); font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }}
    .muted {{ color: var(--muted); }}
    code {{ background: #edf2ee; border: 1px solid var(--line); border-radius: 5px; padding: 2px 5px; white-space: pre-wrap; }}
    ul {{ padding-left: 18px; }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>WaiBrain Review</h1>
      <div class="muted">Candidate memory first. Canonical memory only after review.</div>
    </div>
    <div class="muted">{now_iso()}</div>
  </header>
  <section>
    <h2>Review Inbox</h2>
    <div class="grid">{''.join(review_cards) if review_cards else '<article class="card muted">No pending proposals.</article>'}</div>
  </section>
  <section>
    <h2>Canonical Memory</h2>
    <div class="grid">{''.join(canonical_cards) if canonical_cards else '<article class="card muted">No accepted canonical records yet.</article>'}</div>
  </section>
</main>
</body>
</html>
"""
    path = root / "knowledge/site/index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")
    return path


def workspace_payload(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    proposals = read_jsonl(root / "knowledge/review/proposals.jsonl")
    facts = read_jsonl(root / "knowledge/canonical/facts.jsonl")
    entities = read_jsonl(root / "knowledge/canonical/entities.jsonl")
    evidence = read_jsonl(root / "knowledge/canonical/evidence.jsonl")
    return {
        "generated_at": now_iso(),
        "pending_count": sum(1 for item in proposals if item.get("status") == "pending"),
        "proposal_count": len(proposals),
        "entity_count": len(entities),
        "fact_count": len(facts),
        "conflict_count": sum(1 for item in facts if item.get("status") == "contradicted"),
        "proposals": proposals,
        "entities": entities,
        "facts": facts,
        "evidence": evidence,
    }


def render_review_app_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WaiBrain Review</title>
  <style>
    :root { --bg: #f6f7f4; --panel: #ffffff; --line: #d9e0da; --ink: #17201a; --muted: #68736b; --accent: #245c4f; --danger: #a33b2f; --warn: #a36a1f; }
    * { box-sizing: border-box; }
    body { margin: 0; font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--ink); }
    header { height: 56px; border-bottom: 1px solid var(--line); display: flex; align-items: center; justify-content: space-between; padding: 0 18px; background: var(--panel); }
    h1 { font-size: 17px; margin: 0; letter-spacing: 0; }
    main { display: grid; grid-template-columns: 270px minmax(360px, 1fr) 380px; min-height: calc(100vh - 56px); }
    aside, section { border-right: 1px solid var(--line); padding: 14px; overflow: auto; }
    section:last-child { border-right: 0; }
    .muted { color: var(--muted); }
    .countbar { display: flex; gap: 8px; flex-wrap: wrap; }
    .chip { border: 1px solid var(--line); border-radius: 999px; padding: 3px 8px; background: #f9faf8; }
    .queue-item, .card { width: 100%; text-align: left; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px; margin-bottom: 8px; }
    .queue-item { cursor: pointer; }
    .queue-item.active { border-color: var(--accent); outline: 2px solid rgba(36, 92, 79, .12); }
    .eyebrow { color: var(--accent); text-transform: uppercase; font-weight: 700; font-size: 11px; letter-spacing: .04em; }
    .risk-high { color: var(--danger); }
    .risk-medium { color: var(--warn); }
    h2 { margin: 4px 0 8px; font-size: 20px; letter-spacing: 0; }
    h3 { margin: 12px 0 6px; font-size: 13px; }
    code { background: #edf2ee; border: 1px solid var(--line); border-radius: 5px; padding: 1px 4px; overflow-wrap: anywhere; }
    button { border: 1px solid var(--line); background: var(--panel); color: var(--ink); border-radius: 6px; padding: 7px 10px; cursor: pointer; }
    button.primary { background: var(--accent); color: white; border-color: var(--accent); }
    button.danger { color: var(--danger); border-color: rgba(163, 59, 47, .35); }
    .actions { display: flex; gap: 8px; margin: 12px 0; }
    .list { padding-left: 18px; }
    .status { position: fixed; bottom: 0; left: 0; right: 0; border-top: 1px solid var(--line); background: var(--panel); padding: 7px 14px; color: var(--muted); }
    @media (max-width: 920px) { main { grid-template-columns: 1fr; } aside, section { border-right: 0; border-bottom: 1px solid var(--line); } }
  </style>
</head>
<body>
  <header>
    <h1>WaiBrain Review</h1>
    <div id="counts" class="countbar"></div>
  </header>
  <main>
    <aside>
      <div class="eyebrow">Review Inbox</div>
      <div id="queue"></div>
    </aside>
    <section>
      <div id="decision" class="card muted">No proposal selected.</div>
    </section>
    <section>
      <div class="eyebrow">Evidence / Diff</div>
      <div id="details" class="muted">Select a proposal to inspect evidence.</div>
    </section>
  </main>
  <div id="status" class="status">J/K navigate · A accept · R reject · Cmd/Ctrl+K reserved</div>
<script>
let workspace = null;
let selected = 0;

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

async function loadWorkspace() {
  const res = await fetch("/api/workspace");
  workspace = await res.json();
  if (selected >= workspace.proposals.length) selected = Math.max(0, workspace.proposals.length - 1);
  render();
}

function currentProposal() {
  if (!workspace || !workspace.proposals.length) return null;
  return workspace.proposals[selected];
}

function renderCounts() {
  const counts = document.getElementById("counts");
  counts.innerHTML = [
    `<span class="chip">${workspace.pending_count} pending</span>`,
    `<span class="chip">${workspace.conflict_count} conflicts</span>`,
    `<span class="chip">${workspace.entity_count} entities</span>`,
    `<span class="chip">${workspace.fact_count} facts</span>`
  ].join("");
}

function renderQueue() {
  const queue = document.getElementById("queue");
  const proposals = workspace.proposals.filter((p) => p.status === "pending");
  if (!proposals.length) {
    queue.innerHTML = `<p class="muted">No pending proposals.</p>`;
    return;
  }
  workspace.proposals = proposals;
  queue.innerHTML = proposals.map((p, i) => `
    <button class="queue-item ${i === selected ? "active" : ""}" onclick="selected=${i}; render();">
      <div class="eyebrow ${p.risk === "high" ? "risk-high" : p.risk === "medium" ? "risk-medium" : ""}">${esc(p.kind)} / ${esc(p.risk || "low")}</div>
      <strong>${esc(p.title)}</strong>
      <div class="muted">${esc((p.target_ids || []).join(", "))}</div>
    </button>
  `).join("");
}

function renderDecision() {
  const p = currentProposal();
  const decision = document.getElementById("decision");
  if (!p) {
    decision.className = "card muted";
    decision.innerHTML = "No pending proposal.";
    return;
  }
  const entity = p.payload?.entity || {};
  const facts = p.payload?.facts || [];
  decision.className = "card";
  decision.innerHTML = `
    <div class="eyebrow ${p.risk === "high" ? "risk-high" : p.risk === "medium" ? "risk-medium" : ""}">${esc(p.kind)} / ${esc(p.risk || "low")}</div>
    <h2>${esc(p.title)}</h2>
    <p><strong>${esc(entity.name || "Unknown")}</strong> <code>${esc(entity.id || "")}</code></p>
    <h3>Proposed change</h3>
    <ul class="list">${facts.length ? facts.map((f) => `<li><strong>${esc(f.predicate)}</strong>: ${esc(f.value)}</li>`).join("") : "<li>No facts in proposal.</li>"}</ul>
    <div class="actions">
      <button class="primary" onclick="review('accept')">Accept</button>
      <button class="danger" onclick="review('reject')">Reject</button>
      <button onclick="loadWorkspace()">Refresh</button>
    </div>
    <p class="muted"><code>${esc(p.id)}</code></p>
  `;
}

function renderDetails() {
  const p = currentProposal();
  const details = document.getElementById("details");
  if (!p) {
    details.innerHTML = "Select a proposal to inspect evidence.";
    return;
  }
  const evidence = p.payload?.evidence || [];
  const ops = p.operations || [];
  details.innerHTML = `
    <h3>Evidence</h3>
    <ul class="list">${evidence.length ? evidence.map((e) => `<li><code>${esc(e.source_path)}</code><br>${esc(e.excerpt)}</li>`).join("") : "<li>No evidence spans.</li>"}</ul>
    <h3>Semantic Diff</h3>
    <ul class="list">${ops.length ? ops.map((op) => `<li><code>${esc(op.op)}</code> ${esc(op.id || op.winner_id || op.record?.id || "")}</li>`).join("") : "<li>No operations.</li>"}</ul>
  `;
}

function render() {
  renderCounts();
  renderQueue();
  renderDecision();
  renderDetails();
}

async function review(action) {
  const p = currentProposal();
  if (!p) return;
  const res = await fetch(`/api/review?action=${action}&id=${encodeURIComponent(p.id)}`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
  const body = await res.json();
  document.getElementById("status").textContent = res.ok ? `${action}: ${body.id || p.id}` : `error: ${body.error}`;
  await loadWorkspace();
}

document.addEventListener("keydown", (event) => {
  if (!workspace) return;
  if (event.key === "j" || event.key === "ArrowDown") { selected = Math.min(selected + 1, Math.max(0, workspace.proposals.length - 1)); render(); }
  if (event.key === "k" || event.key === "ArrowUp") { selected = Math.max(0, selected - 1); render(); }
  if (event.key === "a") review("accept");
  if (event.key === "r") review("reject");
});

loadWorkspace();
</script>
</body>
</html>
"""


@dataclass
class ReviewServerHandle:
    server: http.server.ThreadingHTTPServer
    thread: threading.Thread
    port: int

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def json_response(handler: http.server.BaseHTTPRequestHandler, status: int, payload: dict[str, Any] | list[Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: http.server.BaseHTTPRequestHandler, status: int, text: str, content_type: str = "text/html; charset=utf-8") -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", content_type)
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def start_review_server(root: Path, port: int = 8765, *, open_browser: bool = False) -> ReviewServerHandle:
    root = root.resolve()

    class ReviewHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if parsed.path in {"/", "/index.html"}:
                text_response(self, 200, render_review_app_html())
                return
            if parsed.path == "/api/workspace":
                json_response(self, 200, workspace_payload(root))
                return
            json_response(self, 404, {"error": f"not found: {parsed.path}"})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/api/review":
                proposal_id = (query.get("id") or [""])[0]
                action = (query.get("action") or [""])[0]
                if not proposal_id or action not in {"accept", "reject"}:
                    json_response(self, 400, {"error": "missing proposal id or invalid action"})
                    return
                try:
                    result = accept_proposal(root, proposal_id) if action == "accept" else reject_proposal(root, proposal_id)
                    build_wiki(root)
                    build_site(root)
                    json_response(self, 200, result)
                except (KeyError, ValueError) as exc:
                    json_response(self, 404, {"error": str(exc)})
                return
            json_response(self, 404, {"error": f"not found: {parsed.path}"})

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), ReviewHandler)
    actual_port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, name="waibrain-review-server", daemon=True)
    thread.start()
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{actual_port}/")
    return ReviewServerHandle(server=server, thread=thread, port=actual_port)


def tokenize(text: str) -> list[str]:
    return [token.lower().replace("ё", "е") for token in TOKEN_RE.findall(text)]


def iter_markdown(root: Path) -> Iterable[Path]:
    knowledge = root / "knowledge"
    if not knowledge.exists():
        return []
    return sorted(knowledge.rglob("*.md"))


def search_docs(root: Path, query: str, limit: int = 10) -> list[tuple[float, Path, str]]:
    terms = tokenize(query)
    if not terms:
        return []
    docs = list(iter_markdown(root))
    doc_tokens: dict[Path, Counter[str]] = {}
    doc_freq: Counter[str] = Counter()
    for path in docs:
        text = path.read_text(encoding="utf-8", errors="ignore")
        counts = Counter(tokenize(text))
        doc_tokens[path] = counts
        for term in set(counts):
            doc_freq[term] += 1
    total_docs = max(1, len(docs))
    results: list[tuple[float, Path, str]] = []
    for path in docs:
        text = path.read_text(encoding="utf-8", errors="ignore")
        counts = doc_tokens[path]
        if not any(counts.get(term, 0) for term in terms):
            continue
        score = 0.0
        folded_name = path.name.lower()
        for term in terms:
            if counts.get(term, 0):
                idf = math.log((1 + total_docs) / (1 + doc_freq[term])) + 1
                score += idf
                if term in folded_name:
                    score += 1.5
        rel = path.relative_to(root)
        rel_text = rel.as_posix()
        if rel_text.startswith("knowledge/wiki/"):
            score = (score + 5.0) * 3.0
        elif rel_text.startswith("knowledge/raw/"):
            score *= 0.2
        snippet = re.sub(r"\s+", " ", text).strip()[:220]
        results.append((score, rel, snippet))
    return sorted(results, key=lambda item: item[0], reverse=True)[:limit]


def check_public_safety(root: Path) -> CheckResult:
    result = CheckResult()
    for path in sorted(root.rglob("*")):
        if ".git" in path.parts or not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".py", ".jsonl", ".json", ".html", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                result.add_error(f"{path.relative_to(root).as_posix()}: possible {label}")
    return result


def check_duplicate_ids(result: CheckResult, label: str, records: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for record in records:
        record_id = str(record.get("id") or "")
        if not record_id:
            result.add_error(f"{label}: record missing id")
        elif record_id in seen:
            result.add_error(f"{label}:{record_id}: duplicate id")
        seen.add(record_id)


def require_fields(result: CheckResult, label: str, record: dict[str, Any], fields: Iterable[str]) -> None:
    record_id = str(record.get("id") or "?")
    for field_name in fields:
        if field_name not in record or record.get(field_name) in (None, ""):
            result.add_error(f"{label}:{record_id}: missing {field_name}")


def run_doctor(root: Path) -> CheckResult:
    ensure_layout(root)
    result = CheckResult()
    for filename in LAYOUT_FILES:
        try:
            read_jsonl(root / filename)
        except ValueError as exc:
            result.add_error(str(exc))

    sources = sources_by_id(root)
    evidence = {item["id"]: item for item in read_jsonl(root / "knowledge/canonical/evidence.jsonl")}
    entities = {item["id"]: item for item in read_jsonl(root / "knowledge/canonical/entities.jsonl")}
    for label, records in [
        ("sources", list(sources.values())),
        ("evidence", list(evidence.values())),
        ("entities", list(entities.values())),
        ("facts", read_jsonl(root / "knowledge/canonical/facts.jsonl")),
        ("events", read_jsonl(root / "knowledge/canonical/events.jsonl")),
        ("relations", read_jsonl(root / "knowledge/canonical/relations.jsonl")),
        ("proposals", read_jsonl(root / "knowledge/review/proposals.jsonl")),
    ]:
        check_duplicate_ids(result, label, records)

    for source in sources.values():
        require_fields(result, "sources", source, ["id", "path", "sha256", "kind"])
        source_path = root / str(source.get("path", ""))
        if not source_path.exists():
            result.add_error(f"sources:{source.get('id')}: source path missing {source.get('path')}")
        elif file_hash(source_path) != source.get("sha256"):
            result.add_error(f"sources:{source.get('id')}: source hash drift for {source.get('path')}")

    for evidence_record in evidence.values():
        require_fields(result, "evidence", evidence_record, ["id", "source_id", "source_path", "source_sha256", "span", "quote_hash"])
        if evidence_record.get("source_id") not in sources:
            result.add_error(f"evidence:{evidence_record.get('id')}: unknown source id {evidence_record.get('source_id')}")

    for entity in entities.values():
        require_fields(result, "entities", entity, ["id", "type", "name", "status"])
        if entity.get("status") not in ENTITY_STATUSES:
            result.add_error(f"entities:{entity.get('id')}: invalid status {entity.get('status')}")
        if entity.get("status") == "merged" and not entity.get("merged_into"):
            result.add_error(f"entities:{entity.get('id')}: merged entity missing merged_into")

    for filename in ["facts.jsonl", "events.jsonl", "relations.jsonl"]:
        for record in read_jsonl(root / f"knowledge/canonical/{filename}"):
            for source_id in record.get("source_ids", []):
                if source_id not in sources:
                    result.add_error(f"{filename}:{record.get('id')}: unknown source id {source_id}")
            entity_id = record.get("entity_id") or record.get("subject_id")
            if entity_id and entity_id not in entities:
                result.add_error(f"{filename}:{record.get('id')}: unknown entity id {entity_id}")

    for fact in read_jsonl(root / "knowledge/canonical/facts.jsonl"):
        require_fields(result, "facts", fact, ["id", "entity_id", "predicate", "value", "status", "source_ids"])
        if fact.get("status") not in FACT_STATUSES:
            result.add_error(f"facts:{fact.get('id')}: invalid status {fact.get('status')}")
        if fact.get("status") in ACTIVE_FACT_STATUSES and not fact.get("provenance"):
            result.add_error(f"facts:{fact.get('id')}: active fact missing provenance")
        for prov in fact.get("provenance", []):
            evidence_id = prov.get("evidence_id") if isinstance(prov, dict) else None
            if evidence_id not in evidence:
                result.add_error(f"facts:{fact.get('id')}: unknown evidence id {evidence_id}")

    for event in read_jsonl(root / "knowledge/canonical/events.jsonl"):
        require_fields(result, "events", event, ["id", "entity_id", "date", "summary", "status", "source_ids"])
        if event.get("status") == "active" and not event.get("provenance"):
            result.add_error(f"events:{event.get('id')}: active event missing provenance")

    for proposal in read_jsonl(root / "knowledge/review/proposals.jsonl"):
        require_fields(result, "proposals", proposal, ["id", "kind", "status", "operations"])
        if proposal.get("kind") not in PROPOSAL_KINDS:
            result.add_error(f"proposal:{proposal.get('id')}: invalid kind {proposal.get('kind')}")
        if proposal.get("status") not in PROPOSAL_STATUSES:
            result.add_error(f"proposal:{proposal.get('id')}: invalid status {proposal.get('status')}")
        for source_id in proposal.get("source_ids", []):
            if source_id not in sources:
                result.add_error(f"proposal:{proposal.get('id')}: unknown source id {source_id}")

    safety = check_public_safety(root)
    result.errors.extend(safety.errors)
    result.warnings.extend(safety.warnings)
    if pending_proposals(root):
        result.add_warning(f"{len(pending_proposals(root))} pending review proposal(s)")
    return result


def _parse_fact_args(values: list[str]) -> list[dict[str, Any]]:
    facts = []
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--fact must be predicate=value: {value}")
        predicate, fact_value = value.split("=", 1)
        facts.append({"predicate": predicate.strip(), "value": fact_value.strip(), "confidence": 0.75})
    return facts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WaiBrain canonical memory, review, wiki, and site tooling")
    parser.add_argument("--root", default=".", help="wai-brain root")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor")
    sub.add_parser("init")
    site = sub.add_parser("site")
    site.add_argument("action", choices=["build"])
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--open", action="store_true")
    wiki = sub.add_parser("wiki")
    wiki.add_argument("action", choices=["build"])
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)

    propose = sub.add_parser("propose")
    propose.add_argument("--title", required=True)
    propose.add_argument("--source", action="append", required=True)
    propose.add_argument("--entity-name", required=True)
    propose.add_argument("--entity-type", default="person")
    propose.add_argument("--alias", action="append", default=[])
    propose.add_argument("--fact", action="append", default=[], help="predicate=value")
    propose.add_argument("--event-date")
    propose.add_argument("--event-summary")

    merge_entity = sub.add_parser("merge-entity")
    merge_entity.add_argument("--winner", required=True)
    merge_entity.add_argument("--loser", required=True)
    merge_entity.add_argument("--reason", required=True)

    review = sub.add_parser("review")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_sub.add_parser("list")
    show = review_sub.add_parser("show")
    show.add_argument("id")
    accept = review_sub.add_parser("accept")
    accept.add_argument("id")
    reject = review_sub.add_parser("reject")
    reject.add_argument("id")

    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    if args.command == "init":
        ensure_layout(root)
        print(f"initialized {root}")
        return 0
    if args.command == "doctor":
        result = run_doctor(root)
        for warning in result.warnings:
            print(f"warning: {warning}")
        for error in result.errors:
            print(f"error: {error}")
        print("ok" if result.ok() else "failed")
        return 0 if result.ok() else 1
    if args.command == "wiki":
        paths = build_wiki(root)
        print(f"wrote {len(paths)} wiki file(s)")
        return 0
    if args.command == "site":
        path = build_site(root)
        print(path)
        return 0
    if args.command == "serve":
        server = start_review_server(root, port=args.port, open_browser=args.open)
        print(f"serving WaiBrain review at http://127.0.0.1:{server.port}/")
        try:
            while True:
                threading.Event().wait(3600)
        except KeyboardInterrupt:
            server.close()
            print("\nstopped")
            return 0
    if args.command == "search":
        for score, path, snippet in search_docs(root, args.query, args.limit):
            print(f"{score:.2f}\t{path.as_posix()}\t{snippet}")
        return 0
    if args.command == "propose":
        events = []
        if args.event_summary:
            events.append({"date": args.event_date or dt.date.today().isoformat(), "summary": args.event_summary})
        proposal = create_memory_proposal(
            root,
            title=args.title,
            source_paths=[Path(item) if Path(item).is_absolute() else root / item for item in args.source],
            entity={"type": args.entity_type, "name": args.entity_name, "aliases": args.alias},
            facts=_parse_fact_args(args.fact),
            events=events,
        )
        print(json.dumps(proposal, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "merge-entity":
        try:
            proposal = create_entity_merge_proposal(root, winner_id=args.winner, loser_id=args.loser, reason=args.reason)
            print(json.dumps(proposal, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    if args.command == "review":
        if args.review_command == "list":
            for proposal in pending_proposals(root):
                print(f"{proposal['id']}\t{proposal['title']}")
            return 0
        if args.review_command == "show":
            proposals = {item["id"]: item for item in read_jsonl(root / "knowledge/review/proposals.jsonl")}
            if args.id not in proposals:
                print(f"error: proposal not found: {args.id}", file=sys.stderr)
                return 1
            print(json.dumps(proposals[args.id], ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.review_command == "accept":
            try:
                print(json.dumps(accept_proposal(root, args.id), ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            except KeyError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
        if args.review_command == "reject":
            try:
                print(json.dumps(reject_proposal(root, args.id), ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            except KeyError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
