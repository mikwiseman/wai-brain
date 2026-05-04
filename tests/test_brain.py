import tempfile
import unittest
from pathlib import Path

from scripts import brain


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class BrainCliTests(unittest.TestCase):
    def test_slugify_keeps_russian_and_ascii(self) -> None:
        self.assertEqual(brain.slugify("WaiConnect / Recruiting Lane"), "waiconnect-recruiting-lane")
        self.assertEqual(brain.slugify("Приключения приятные!"), "приключения-приятные")

    def test_search_prefers_compiled_pages_over_raw(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "AGENTS.md", "# test")
            write(root / "knowledge/wiki/topics/waiconnect.md", """---
type: topic
title: "WaiConnect recruiting"
---

# WaiConnect recruiting

WaiConnect uses an audit-first recruiting lane with a 3-minute diagnostic.
""")
            write(root / "knowledge/raw/_inbox/main-dm/source.md", "WaiConnect recruiting lane raw mention")
            results = brain.search_docs(root, "WaiConnect recruiting diagnostic", limit=2)
            self.assertTrue(results)
            self.assertEqual(results[0][1].rel, "knowledge/wiki/topics/waiconnect.md")

    def test_manifest_add_source_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "AGENTS.md", "# test")
            write(root / "knowledge/raw/_inbox/main-dm/source.md", "same evidence")
            first = brain.add_source_to_manifest(root, root / "knowledge/raw/_inbox/main-dm/source.md")
            second = brain.add_source_to_manifest(root, root / "knowledge/raw/_inbox/main-dm/source.md")
            self.assertEqual(first["source_id"], second["source_id"])
            self.assertEqual(second["status"], "already-recorded")

    def test_eval_ignores_golden_question_file_as_answer_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "AGENTS.md", "# test")
            write(root / "knowledge/projects/waiconnect.md", """---
type: project
title: "WaiConnect"
---

# WaiConnect

Recruiting diagnostic source of truth.
""")
            write(root / "knowledge/eval/golden-questions.md", """---
type: eval
---

# Golden questions

## GQ001 — What is the WaiConnect recruiting diagnostic source of truth?

- Expected source: `knowledge/projects/waiconnect.md`
- Must mention: recruiting diagnostic
""")
            report = brain.run_eval(root)
            self.assertIn("| GQ001 | yes | `knowledge/projects/waiconnect.md` | ok |", report)

    def test_doctor_catches_placeholder_skill_and_masked_capture_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "AGENTS.md", "# test")
            write(root / "knowledge/Home.md", "# home")
            write(root / "knowledge/wiki/INDEX.md", "# index")
            write(root / "knowledge/wiki/log.md", "# log")
            write(root / "knowledge/decisions.md", "# decisions")
            write(root / "knowledge/eval/golden-questions.md", "# Golden questions\n")
            write(root / "knowledge/manifests/sources.jsonl", "")
            write(root / ".claude/skills/process-inbox/SKILL.md", "Skeleton. best-effort")
            write(root / "infra/openclaw/wai-brain-capture.md", "git pull --rebase origin main || true")
            result = brain.run_doctor(root)
            self.assertFalse(result.ok())
            self.assertTrue(any("placeholder" in error for error in result.errors))
            self.assertTrue(any("|| true" in error for error in result.errors))

    def test_public_safety_catches_private_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "AGENTS.md", "# test")
            write(root / "knowledge/Home.md", "# home\nprivate server 203.0.113.42 and chat -1001234567890")
            result = brain.check_public_safety(root)
            self.assertFalse(result.ok())
            self.assertTrue(any("chat id" in error for error in result.errors))
            self.assertTrue(any("IPv4" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
