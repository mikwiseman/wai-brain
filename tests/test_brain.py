import json
import hashlib
import tempfile
import unittest
import urllib.request
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

from scripts import brain


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class WaiBrainReviewPipelineTests(unittest.TestCase):
    def test_proposal_stages_memory_without_canonical_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "knowledge/raw/telegram/yulia.md"
            write(root / "AGENTS.md", "# test")
            write(source, "Yulia wants governable memory, not duplicate AI slop.")

            brain.ensure_layout(root)
            proposal = brain.create_memory_proposal(
                root,
                title="Yulia memory governance problem",
                source_paths=[source],
                entity={"type": "person", "name": "Yulia Mitrovich", "aliases": ["@yuliamitrovich83"]},
                facts=[
                    {
                        "predicate": "has_problem",
                        "value": "needs governable AI memory without duplicate generated content",
                        "confidence": 0.86,
                        "valid_at": "2026-05-22",
                    }
                ],
                events=[
                    {
                        "date": "2026-05-22",
                        "summary": "Reported that current AI memory tools create duplicate content instead of a controllable wiki.",
                    }
                ],
            )

            self.assertEqual(proposal["status"], "pending")
            self.assertEqual(brain.read_jsonl(root / "knowledge/canonical/facts.jsonl"), [])
            pending = brain.pending_proposals(root)
            self.assertEqual([item["id"] for item in pending], [proposal["id"]])

    def test_accept_proposal_upserts_canonical_records_and_builds_wiki(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "knowledge/raw/telegram/yulia.md"
            write(root / "AGENTS.md", "# test")
            write(source, "Yulia wants governable memory, not duplicate AI slop.")
            brain.ensure_layout(root)
            proposal = brain.create_memory_proposal(
                root,
                title="Yulia memory governance problem",
                source_paths=[source],
                entity={"type": "person", "name": "Yulia Mitrovich", "aliases": ["@yuliamitrovich83"]},
                facts=[{"predicate": "has_problem", "value": "needs governable AI memory", "confidence": 0.86}],
                events=[{"date": "2026-05-22", "summary": "Discussed duplicated AI memory output."}],
            )

            accepted = brain.accept_proposal(root, proposal["id"])
            accepted_again = brain.accept_proposal(root, proposal["id"])
            wiki_paths = brain.build_wiki(root)

            self.assertEqual(accepted["status"], "accepted")
            self.assertEqual(accepted_again["status"], "already-accepted")
            self.assertEqual(len(brain.read_jsonl(root / "knowledge/canonical/entities.jsonl")), 1)
            self.assertEqual(len(brain.read_jsonl(root / "knowledge/canonical/facts.jsonl")), 1)
            self.assertEqual(len(brain.read_jsonl(root / "knowledge/canonical/events.jsonl")), 1)
            entity_page = root / "knowledge/wiki/entities/person/yulia-mitrovich.md"
            self.assertIn(entity_page, wiki_paths)
            text = entity_page.read_text(encoding="utf-8")
            self.assertIn("needs governable AI memory", text)
            self.assertIn("[Source: knowledge/raw/telegram/yulia.md]", text)

    def test_generated_site_shows_review_and_canonical_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "knowledge/raw/telegram/yulia.md"
            write(root / "AGENTS.md", "# test")
            write(source, "Yulia wants a reviewable memory wiki.")
            brain.ensure_layout(root)
            proposal = brain.create_memory_proposal(
                root,
                title="Yulia review queue",
                source_paths=[source],
                entity={"type": "person", "name": "Yulia Mitrovich"},
                facts=[{"predicate": "wants", "value": "a reviewable memory wiki", "confidence": 0.8}],
            )

            site = brain.build_site(root)
            html = site.read_text(encoding="utf-8")
            self.assertIn("Review Inbox", html)
            self.assertIn(proposal["title"], html)

            brain.accept_proposal(root, proposal["id"])
            brain.build_wiki(root)
            html = brain.build_site(root).read_text(encoding="utf-8")
            self.assertIn("Canonical Memory", html)
            self.assertIn("a reviewable memory wiki", html)

    def test_doctor_catches_fact_with_unknown_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "AGENTS.md", "# test")
            brain.ensure_layout(root)
            brain.write_jsonl(
                root / "knowledge/canonical/facts.jsonl",
                [
                    {
                        "id": "fact_bad",
                        "entity_id": "person/yulia-mitrovich",
                        "predicate": "wants",
                        "value": "source checking",
                        "source_ids": ["src_missing"],
                        "status": "active",
                    }
                ],
            )

            result = brain.run_doctor(root)
            self.assertFalse(result.ok())
            self.assertTrue(any("unknown source id" in error for error in result.errors))

    def test_search_prefers_generated_wiki_over_raw_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "knowledge/raw/telegram/yulia.md"
            write(root / "AGENTS.md", "# test")
            write(source, "reviewable memory wiki " * 20)
            brain.ensure_layout(root)
            proposal = brain.create_memory_proposal(
                root,
                title="Yulia review queue",
                source_paths=[source],
                entity={"type": "person", "name": "Yulia Mitrovich"},
                facts=[{"predicate": "wants", "value": "a reviewable memory wiki", "confidence": 0.8}],
            )
            brain.accept_proposal(root, proposal["id"])
            brain.build_wiki(root)

            results = brain.search_docs(root, "reviewable memory wiki", limit=2)
            self.assertTrue(results)
            self.assertEqual(results[0][1].as_posix(), "knowledge/wiki/entities/person/yulia-mitrovich.md")

    def test_accept_adds_claim_level_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "knowledge/raw/telegram/yulia.md"
            write(root / "AGENTS.md", "# test")
            write(source, "Yulia explicitly asks for a governed memory wiki.")
            brain.ensure_layout(root)
            proposal = brain.create_memory_proposal(
                root,
                title="Yulia wants governed wiki",
                source_paths=[source],
                entity={"type": "person", "name": "Yulia Mitrovich"},
                facts=[{"predicate": "wants", "value": "a governed memory wiki", "confidence": 0.84}],
            )

            brain.accept_proposal(root, proposal["id"])
            facts = brain.read_jsonl(root / "knowledge/canonical/facts.jsonl")
            evidence = brain.read_jsonl(root / "knowledge/canonical/evidence.jsonl")

            self.assertEqual(len(facts), 1)
            self.assertTrue(facts[0]["provenance"])
            self.assertEqual(facts[0]["provenance"][0]["source_id"], evidence[0]["source_id"])
            self.assertIn("span", facts[0]["provenance"][0])
            self.assertTrue(brain.run_doctor(root).ok())

    def test_supersede_proposal_invalidates_old_fact_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source1 = root / "knowledge/raw/telegram/old.md"
            source2 = root / "knowledge/raw/telegram/new.md"
            write(root / "AGENTS.md", "# test")
            write(source1, "Yulia wanted a better wiki.")
            write(source2, "Yulia now wants a governed memory wiki.")
            brain.ensure_layout(root)
            first = brain.create_memory_proposal(
                root,
                title="Old Yulia preference",
                source_paths=[source1],
                entity={"type": "person", "name": "Yulia Mitrovich"},
                facts=[{"predicate": "wants", "value": "a better wiki", "confidence": 0.7, "valid_at": "2026-05-20"}],
            )
            brain.accept_proposal(root, first["id"])

            second = brain.create_memory_proposal(
                root,
                title="Updated Yulia preference",
                source_paths=[source2],
                entity={"type": "person", "name": "Yulia Mitrovich"},
                facts=[{"predicate": "wants", "value": "a governed memory wiki", "confidence": 0.9, "valid_at": "2026-05-22"}],
            )

            self.assertEqual(second["kind"], "fact_supersede")
            brain.accept_proposal(root, second["id"])
            facts = sorted(brain.read_jsonl(root / "knowledge/canonical/facts.jsonl"), key=lambda item: item["value"])
            statuses = {fact["value"]: fact["status"] for fact in facts}
            self.assertEqual(statuses["a better wiki"], "superseded")
            self.assertEqual(statuses["a governed memory wiki"], "active")
            self.assertEqual(len(facts), 2)

    def test_conflicting_fact_creates_conflict_without_current_truth_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_source = root / "knowledge/raw/telegram/old.md"
            conflict_source = root / "knowledge/raw/telegram/conflict.md"
            write(root / "AGENTS.md", "# test")
            write(old_source, "Yulia wants local memory.")
            write(conflict_source, "Yulia wants hosted memory.")
            brain.ensure_layout(root)
            first = brain.create_memory_proposal(
                root,
                title="Yulia wants local memory",
                source_paths=[old_source],
                entity={"type": "person", "name": "Yulia Mitrovich"},
                facts=[{"predicate": "wants", "value": "local memory", "confidence": 0.8}],
            )
            brain.accept_proposal(root, first["id"])
            conflict = brain.create_memory_proposal(
                root,
                title="Yulia wants hosted memory",
                source_paths=[conflict_source],
                entity={"type": "person", "name": "Yulia Mitrovich"},
                facts=[{"predicate": "wants", "value": "hosted memory", "confidence": 0.8}],
            )

            self.assertEqual(conflict["kind"], "fact_conflict")
            brain.accept_proposal(root, conflict["id"])
            facts = brain.read_jsonl(root / "knowledge/canonical/facts.jsonl")
            self.assertEqual({fact["status"] for fact in facts}, {"contradicted"})
            brain.build_wiki(root)
            page = root / "knowledge/wiki/entities/person/yulia-mitrovich.md"
            text = page.read_text(encoding="utf-8")
            self.assertIn("## Open Conflicts", text)
            self.assertIn("hosted memory", text)
            self.assertIn("local memory", text)

    def test_entity_merge_requires_proposal_and_merges_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source1 = root / "knowledge/raw/telegram/yulia.md"
            source2 = root / "knowledge/raw/telegram/handle.md"
            write(root / "AGENTS.md", "# test")
            write(source1, "Yulia wants governed memory.")
            write(source2, "@yuliamitrovich83 wants governed memory.")
            brain.ensure_layout(root)
            first = brain.create_memory_proposal(
                root,
                title="Yulia entity",
                source_paths=[source1],
                entity={"type": "person", "name": "Yulia Mitrovich", "aliases": ["Yulia"]},
            )
            second = brain.create_memory_proposal(
                root,
                title="Yulia handle entity",
                source_paths=[source2],
                entity={"type": "person", "name": "@yuliamitrovich83", "aliases": ["@yuliamitrovich83"]},
            )
            brain.accept_proposal(root, first["id"])
            brain.accept_proposal(root, second["id"])

            merge = brain.create_entity_merge_proposal(
                root,
                winner_id="person/yulia-mitrovich",
                loser_id="person/yuliamitrovich83",
                reason="Telegram handle belongs to the same person.",
            )
            self.assertEqual(merge["kind"], "entity_merge")
            brain.accept_proposal(root, merge["id"])
            entities = {entity["id"]: entity for entity in brain.read_jsonl(root / "knowledge/canonical/entities.jsonl")}

            self.assertEqual(entities["person/yuliamitrovich83"]["status"], "merged")
            self.assertEqual(entities["person/yuliamitrovich83"]["merged_into"], "person/yulia-mitrovich")
            self.assertIn("@yuliamitrovich83", entities["person/yulia-mitrovich"]["aliases"])

    def test_cli_bad_review_id_returns_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "AGENTS.md", "# test")
            brain.ensure_layout(root)
            stderr = StringIO()
            with redirect_stderr(stderr):
                code = brain.main(["--root", str(root), "review", "show", "prop_missing"])

            self.assertEqual(code, 1)
            self.assertIn("proposal not found", stderr.getvalue())

    def test_review_server_accepts_proposal_through_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "knowledge/raw/telegram/yulia.md"
            write(root / "AGENTS.md", "# test")
            write(source, "Yulia wants a live review server.")
            brain.ensure_layout(root)
            proposal = brain.create_memory_proposal(
                root,
                title="Yulia wants live review",
                source_paths=[source],
                entity={"type": "person", "name": "Yulia Mitrovich"},
                facts=[{"predicate": "wants", "value": "a live review server", "confidence": 0.88}],
            )
            server = brain.start_review_server(root, port=0, open_browser=False)
            try:
                base = f"http://127.0.0.1:{server.port}"
                with urllib.request.urlopen(f"{base}/api/workspace", timeout=5) as response:
                    workspace = json.loads(response.read().decode("utf-8"))
                self.assertEqual(workspace["pending_count"], 1)
                self.assertEqual(workspace["proposals"][0]["id"], proposal["id"])

                request = urllib.request.Request(
                    f"{base}/api/review?action=accept&id={proposal['id']}",
                    data=b"{}",
                    method="POST",
                    headers={"content-type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    result = json.loads(response.read().decode("utf-8"))
                self.assertEqual(result["status"], "accepted")
                self.assertEqual(len(brain.read_jsonl(root / "knowledge/canonical/facts.jsonl")), 1)
            finally:
                server.close()

    def test_proposal_can_pin_claim_level_evidence_quote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "knowledge/raw/telegram/yulia.md"
            quote = "Yulia needs a governed memory wiki"
            write(root / "AGENTS.md", "# test")
            write(source, f"Noise before. {quote}. Noise after.")
            brain.ensure_layout(root)

            proposal = brain.create_memory_proposal(
                root,
                title="Yulia governed memory wiki",
                source_paths=[source],
                evidence_quotes=[quote],
                entity={"type": "person", "name": "Yulia Mitrovich"},
                facts=[{"predicate": "needs", "value": "a governed memory wiki", "confidence": 0.9}],
            )

            evidence = proposal["payload"]["evidence"][0]
            self.assertGreater(evidence["span"]["start"], 0)
            self.assertEqual(evidence["span"]["end"] - evidence["span"]["start"], len(quote))
            self.assertEqual(evidence["quote_hash"], hashlib.sha256(quote.encode("utf-8")).hexdigest())
            self.assertEqual(evidence["excerpt"], quote)

    def test_relation_proposal_builds_entity_graph_wiki_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mik_source = root / "knowledge/raw/notes/mik.md"
            yulia_source = root / "knowledge/raw/telegram/yulia.md"
            write(root / "AGENTS.md", "# test")
            write(mik_source, "Mik is building WaiBrain.")
            write(yulia_source, "Yulia discusses memory with Mik.")
            brain.ensure_layout(root)
            mik = brain.create_memory_proposal(
                root,
                title="Mik entity",
                source_paths=[mik_source],
                entity={"type": "person", "name": "Mik Wiseman"},
            )
            brain.accept_proposal(root, mik["id"])

            yulia = brain.create_memory_proposal(
                root,
                title="Yulia discusses with Mik",
                source_paths=[yulia_source],
                entity={"type": "person", "name": "Yulia Mitrovich"},
                relations=[
                    {
                        "predicate": "discusses_with",
                        "object_id": "person/mik-wiseman",
                        "confidence": 0.82,
                    }
                ],
            )

            self.assertEqual(yulia["kind"], "relation_add")
            brain.accept_proposal(root, yulia["id"])
            self.assertTrue(brain.run_doctor(root).ok())
            brain.build_wiki(root)
            page = root / "knowledge/wiki/entities/person/yulia-mitrovich.md"
            text = page.read_text(encoding="utf-8")
            self.assertIn("## Relations", text)
            self.assertIn("[[Mik Wiseman|Mik Wiseman]]", text)
            relations = brain.read_jsonl(root / "knowledge/canonical/relations.jsonl")
            self.assertEqual(relations[0]["object_id"], "person/mik-wiseman")

    def test_entity_merge_repoints_loser_facts_events_and_relations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            yulia_source = root / "knowledge/raw/telegram/yulia.md"
            handle_source = root / "knowledge/raw/telegram/handle.md"
            write(root / "AGENTS.md", "# test")
            write(yulia_source, "Yulia wants governed memory.")
            write(handle_source, "@yuliamitrovich83 wants governed memory and discussed it with Yulia.")
            brain.ensure_layout(root)
            winner = brain.create_memory_proposal(
                root,
                title="Yulia entity",
                source_paths=[yulia_source],
                entity={"type": "person", "name": "Yulia Mitrovich"},
            )
            loser = brain.create_memory_proposal(
                root,
                title="Yulia handle entity",
                source_paths=[handle_source],
                entity={"type": "person", "name": "@yuliamitrovich83", "aliases": ["@yuliamitrovich83"]},
                facts=[{"predicate": "wants", "value": "governed memory", "confidence": 0.8}],
                events=[{"date": "2026-05-24", "summary": "Discussed governed memory."}],
                relations=[{"predicate": "same_context_as", "object_id": "person/yulia-mitrovich"}],
            )
            brain.accept_proposal(root, winner["id"])
            brain.accept_proposal(root, loser["id"])

            merge = brain.create_entity_merge_proposal(
                root,
                winner_id="person/yulia-mitrovich",
                loser_id="person/yuliamitrovich83",
                reason="Telegram handle belongs to the same person.",
            )
            brain.accept_proposal(root, merge["id"])

            facts = brain.read_jsonl(root / "knowledge/canonical/facts.jsonl")
            events = brain.read_jsonl(root / "knowledge/canonical/events.jsonl")
            relations = brain.read_jsonl(root / "knowledge/canonical/relations.jsonl")
            self.assertEqual({fact["entity_id"] for fact in facts}, {"person/yulia-mitrovich"})
            self.assertEqual({event["entity_id"] for event in events}, {"person/yulia-mitrovich"})
            self.assertEqual({relation["subject_id"] for relation in relations}, {"person/yulia-mitrovich"})
            self.assertTrue(brain.run_doctor(root).ok())

    def test_wiki_build_exports_obsidian_friendly_vault_and_source_backlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export = root / "dist/obsidian"
            source = root / "knowledge/raw/telegram/yulia.md"
            write(root / "AGENTS.md", "# test")
            write(source, "Yulia wants Obsidian-compatible governed memory.")
            brain.ensure_layout(root)
            proposal = brain.create_memory_proposal(
                root,
                title="Yulia Obsidian memory",
                source_paths=[source],
                entity={"type": "person", "name": "Yulia Mitrovich", "aliases": ["@yuliamitrovich83"]},
                facts=[{"predicate": "wants", "value": "Obsidian-compatible governed memory", "confidence": 0.86}],
            )
            brain.accept_proposal(root, proposal["id"])
            brain.build_wiki(root)
            brain.export_obsidian_vault(root, export)

            entity_page = export / "entities/person/yulia-mitrovich.md"
            source_pages = list((export / "sources").glob("*.md"))
            entity_text = entity_page.read_text(encoding="utf-8")
            self.assertIn("aliases:", entity_text)
            self.assertIn("tags:", entity_text)
            self.assertIn("^fact-", entity_text)
            self.assertIn("[[Source ", entity_text)
            self.assertTrue(source_pages)
            self.assertIn("[[Yulia Mitrovich|Yulia Mitrovich]]", source_pages[0].read_text(encoding="utf-8"))
            self.assertTrue((export / ".obsidian/app.json").exists())

    def test_reject_records_reason_for_review_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "knowledge/raw/telegram/noise.md"
            write(root / "AGENTS.md", "# test")
            write(source, "Unclear duplicated memory claim.")
            brain.ensure_layout(root)
            proposal = brain.create_memory_proposal(
                root,
                title="Unclear duplicate",
                source_paths=[source],
                entity={"type": "person", "name": "Yulia Mitrovich"},
                facts=[{"predicate": "wants", "value": "unclear duplicate", "confidence": 0.3}],
            )

            rejected = brain.reject_proposal(root, proposal["id"], reason="Duplicate and weak evidence.")

            self.assertEqual(rejected["status"], "rejected")
            self.assertEqual(rejected["decision_reason"], "Duplicate and weak evidence.")

    def test_connector_state_upsert_is_idempotent_without_canonical_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "AGENTS.md", "# test")
            brain.ensure_layout(root)

            first = brain.upsert_connector_state(
                root,
                provider="telegram",
                account="yulia",
                scope="chat:yuliamitrovich83",
                cursor="message:100",
                privacy_class="private",
                sync_window={"mode": "incremental"},
                status="active",
            )
            second = brain.upsert_connector_state(
                root,
                provider="telegram",
                account="yulia",
                scope="chat:yuliamitrovich83",
                cursor="message:101",
                privacy_class="private",
                sync_window={"mode": "incremental"},
                status="active",
            )

            connectors = brain.read_jsonl(root / "knowledge/manifests/connectors.jsonl")
            self.assertEqual(first["id"], second["id"])
            self.assertEqual(len(connectors), 1)
            self.assertEqual(connectors[0]["cursor"], "message:101")
            self.assertEqual(connectors[0]["sync_window"], {"mode": "incremental"})
            self.assertEqual(brain.read_jsonl(root / "knowledge/canonical/facts.jsonl"), [])
            self.assertTrue(brain.run_doctor(root).ok())

    def test_doctor_catches_invalid_connector_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "AGENTS.md", "# test")
            brain.ensure_layout(root)
            brain.write_jsonl(
                root / "knowledge/manifests/connectors.jsonl",
                [
                    {
                        "schema_version": brain.SCHEMA_VERSION,
                        "id": "conn_bad",
                        "provider": "telegram",
                        "account": "yulia",
                        "scope": "chat:yuliamitrovich83",
                        "status": "guessing",
                        "privacy_class": "private",
                    }
                ],
            )

            result = brain.run_doctor(root)

            self.assertFalse(result.ok())
            self.assertTrue(any("invalid status" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
