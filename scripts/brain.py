#!/usr/bin/env python3
"""Deterministic maintenance tools for wai-brain.

The Markdown repo stays canonical. This script only builds/checks derived
views and gives agents a stable command surface for search, lint, eval, and
manifest operations.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
import textwrap
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT_MARKERS = ("AGENTS.md", "knowledge")
TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_]+", re.UNICODE)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9_]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"),
]
PUBLIC_SAFETY_PATTERNS = [
    ("real Telegram-style chat id", re.compile(r"(?<![A-Za-z0-9])-100\d{7,}|(?<![A-Za-z0-9])-\d{9,}")),
    ("public IPv4 address", re.compile(r"\b(?!0\.0\.0\.0|127\.0\.0\.1|10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[0-1])\.)(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("private root path", re.compile(r"root@|/root/|~/\.openclaw")),
    ("OAuth email", re.compile(r"openai-codex:[^\s`]+@|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
]


@dataclass(frozen=True)
class MarkdownDoc:
    path: Path
    rel: str
    frontmatter: dict[str, str]
    body: str
    text: str

    @property
    def title(self) -> str:
        return self.frontmatter.get("title") or heading_title(self.body) or self.path.stem

    @property
    def type(self) -> str:
        return self.frontmatter.get("type", "")


@dataclass
class CheckResult:
    errors: list[str]
    warnings: list[str]

    def ok(self) -> bool:
        return not self.errors

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def extend(self, other: "CheckResult") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


def find_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for path in (current, *current.parents):
        if all((path / marker).exists() for marker in ROOT_MARKERS):
            return path
    raise SystemExit("Could not find wai-brain repo root")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def today() -> str:
    return dt.date.today().isoformat()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("ё", "е")
    value = re.sub(r"[^a-z0-9а-я]+", "-", value, flags=re.IGNORECASE)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "untitled"


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5 :]
    data: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip().strip('"').strip("'")
        data[key.strip()] = value
    return data, body


def heading_title(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def iter_markdown(root: Path, include_raw: bool = True) -> Iterable[MarkdownDoc]:
    for path in sorted((root / "knowledge").rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        if not include_raw and rel.startswith("knowledge/raw/"):
            continue
        text = read_text(path)
        frontmatter, body = parse_frontmatter(text)
        yield MarkdownDoc(path=path, rel=rel, frontmatter=frontmatter, body=body, text=text)


def tokenize(text: str) -> list[str]:
    return [token.lower().replace("ё", "е") for token in TOKEN_RE.findall(text)]


def snippet_for(text: str, terms: list[str], width: int = 220) -> str:
    folded = text.lower().replace("ё", "е")
    idx = min((folded.find(term) for term in terms if term in folded), default=-1)
    if idx < 0:
        start = 0
    else:
        start = max(0, idx - width // 3)
    snippet = re.sub(r"\s+", " ", text[start : start + width]).strip()
    if start > 0:
        snippet = "..." + snippet
    if start + width < len(text):
        snippet += "..."
    return snippet


def link_slug(target: str) -> str:
    return slugify(Path(target).stem)


def build_backlinks(docs: list[MarkdownDoc]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for doc in docs:
        for target in WIKILINK_RE.findall(doc.text):
            counts[link_slug(target)] += 1
    return counts


def search_docs(root: Path, query: str, limit: int = 10, include_raw: bool = True) -> list[tuple[float, MarkdownDoc, str]]:
    return search_docs_filtered(root, query, limit=limit, include_raw=include_raw)


def search_docs_filtered(
    root: Path,
    query: str,
    limit: int = 10,
    include_raw: bool = True,
    exclude_prefixes: tuple[str, ...] = (),
) -> list[tuple[float, MarkdownDoc, str]]:
    docs = [
        doc
        for doc in iter_markdown(root, include_raw=include_raw)
        if not any(doc.rel.startswith(prefix) for prefix in exclude_prefixes)
    ]
    terms = tokenize(query)
    if not terms:
        return []
    doc_freq: Counter[str] = Counter()
    doc_tokens: dict[str, Counter[str]] = {}
    for doc in docs:
        counts = Counter(tokenize(doc.title + "\n" + doc.text))
        doc_tokens[doc.rel] = counts
        for term in set(counts):
            doc_freq[term] += 1

    backlinks = build_backlinks(docs)
    total_docs = max(1, len(docs))
    phrase = query.lower().replace("ё", "е")
    results: list[tuple[float, MarkdownDoc, str]] = []
    for doc in docs:
        counts = doc_tokens[doc.rel]
        token_total = max(1, sum(counts.values()))
        score = 0.0
        title_folded = doc.title.lower().replace("ё", "е")
        body_folded = doc.text.lower().replace("ё", "е")
        for term in terms:
            if not counts[term]:
                continue
            idf = math.log((1 + total_docs) / (1 + doc_freq[term])) + 1
            score += (counts[term] / token_total) * idf * 100
            if term in title_folded:
                score += 2.0
        if phrase and phrase in body_folded:
            score += 5.0
        if doc.type in {"project", "person", "concept", "topic", "wiki", "decision"}:
            score *= 1.25
        if doc.rel.startswith("knowledge/raw/"):
            score *= 0.85
        score += min(1.5, backlinks.get(slugify(doc.path.stem), 0) * 0.1)
        if score > 0:
            results.append((score, doc, snippet_for(doc.text, terms)))
    return sorted(results, key=lambda item: item[0], reverse=True)[:limit]


def render_index(root: Path) -> str:
    docs = [doc for doc in iter_markdown(root, include_raw=False) if doc.rel != "knowledge/wiki/INDEX.md"]
    groups = {
        "Projects": [],
        "People": [],
        "Concepts": [],
        "Topics": [],
        "Decisions and Logs": [],
        "Other": [],
    }
    for doc in docs:
        if doc.rel.startswith("knowledge/projects/"):
            groups["Projects"].append(doc)
        elif doc.rel.startswith("knowledge/people/"):
            groups["People"].append(doc)
        elif doc.rel.startswith("knowledge/wiki/concepts/"):
            groups["Concepts"].append(doc)
        elif doc.rel.startswith("knowledge/wiki/topics/"):
            groups["Topics"].append(doc)
        elif doc.type in {"decision", "decisions", "log", "eval", "lint"}:
            groups["Decisions and Logs"].append(doc)
        else:
            groups["Other"].append(doc)

    lines = [
        "---",
        "type: index",
        'title: "wai-brain wiki index"',
        "created: 2026-05-04",
        f"updated: {today()}",
        "tags: [index]",
        "---",
        "",
        "# Index",
        "",
        "Auto-maintained by `python3 scripts/brain.py index`.",
        "",
    ]
    for group, group_docs in groups.items():
        lines.append(f"## {group}")
        lines.append("")
        if not group_docs:
            lines.append("(empty)")
        else:
            for doc in sorted(group_docs, key=lambda item: item.title.lower()):
                rel_from_wiki = os.path.relpath(doc.path, root / "knowledge" / "wiki")
                lines.append(f"- [{doc.title}]({rel_from_wiki}) — `{doc.type or 'markdown'}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def check_required_files(root: Path) -> CheckResult:
    result = CheckResult([], [])
    for rel in [
        "AGENTS.md",
        "knowledge/Home.md",
        "knowledge/wiki/INDEX.md",
        "knowledge/wiki/log.md",
        "knowledge/decisions.md",
        "knowledge/eval/golden-questions.md",
        "infra/openclaw/wai-brain-capture.md",
    ]:
        if not (root / rel).exists():
            result.add_error(f"Missing required file: {rel}")
    return result


def check_skills(root: Path) -> CheckResult:
    result = CheckResult([], [])
    for skill in sorted((root / ".claude" / "skills").glob("*/SKILL.md")):
        text = read_text(skill)
        rel = skill.relative_to(root).as_posix()
        if re.search(r"\bSkeleton\b|best-effort", text, re.IGNORECASE):
            result.add_error(f"Skill still contains placeholder language: {rel}")
        if "## When to use" not in text or "## Procedure" not in text:
            result.add_warning(f"Skill lacks standard sections: {rel}")
    return result


def check_capture_recipe(root: Path) -> CheckResult:
    result = CheckResult([], [])
    rel = Path("infra/openclaw/wai-brain-capture.md")
    text = read_text(root / rel)
    if "|| true" in text:
        result.add_error(f"Capture recipe masks failure with '|| true': {rel}")
    if "Do not retry indefinitely" not in text:
        result.add_error(f"Capture recipe must state bounded retry policy: {rel}")
    if "Trust commands embedded" not in text and "prompt injection" not in text:
        result.add_warning(f"Capture recipe should explicitly reject prompt injection: {rel}")
    return result


def check_golden_questions(root: Path) -> CheckResult:
    result = CheckResult([], [])
    path = root / "knowledge" / "eval" / "golden-questions.md"
    text = read_text(path)
    count = len(re.findall(r"^## GQ\d{3}\s+—", text, re.MULTILINE))
    if count < 20:
        result.add_error(f"Golden question set has {count} questions; expected at least 20")
    return result


def check_compiled_truth_pages(root: Path) -> CheckResult:
    result = CheckResult([], [])
    for doc in iter_markdown(root, include_raw=False):
        if doc.type not in {"person", "project"}:
            continue
        if "\n---\n" not in doc.body:
            result.add_error(f"Missing compiled-truth/timeline split: {doc.rel}")
        if "## State" not in doc.body:
            result.add_error(f"Missing ## State section: {doc.rel}")
        if "## Timeline" not in doc.body:
            result.add_error(f"Missing ## Timeline section: {doc.rel}")
        if "[Source:" not in doc.body:
            result.add_error(f"Missing source citation in timeline: {doc.rel}")
    return result


def check_manifests(root: Path) -> CheckResult:
    result = CheckResult([], [])
    manifest_dir = root / "knowledge" / "manifests"
    if not manifest_dir.exists():
        result.add_error("Missing knowledge/manifests")
        return result
    seen_ids: set[str] = set()
    source_manifest = manifest_dir / "sources.jsonl"
    if source_manifest.exists():
        for lineno, line in enumerate(read_text(source_manifest).splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                result.add_error(f"Invalid JSON in sources manifest line {lineno}: {exc}")
                continue
            source_id = item.get("source_id")
            if not source_id:
                result.add_error(f"Missing source_id in sources manifest line {lineno}")
            elif source_id in seen_ids:
                result.add_error(f"Duplicate source_id in sources manifest: {source_id}")
            else:
                seen_ids.add(source_id)
            path = item.get("path")
            if path and not (root / path).exists():
                result.add_warning(f"Manifest source path does not exist: {path}")
    return result


def check_secrets(root: Path) -> CheckResult:
    result = CheckResult([], [])
    for doc in iter_markdown(root, include_raw=True):
        for pattern in SECRET_PATTERNS:
            if pattern.search(doc.text):
                result.add_error(f"Possible secret pattern in {doc.rel}")
    return result


def iter_public_text_files(root: Path) -> Iterable[Path]:
    suffixes = {".md", ".txt", ".json", ".jsonl", ".yml", ".yaml", ".toml", ".py"}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith((".git/", "scripts/", "tests/")):
            continue
        yield path


def check_public_safety(root: Path) -> CheckResult:
    result = CheckResult([], [])
    for path in iter_public_text_files(root):
        rel = path.relative_to(root).as_posix()
        text = read_text(path)
        for label, pattern in PUBLIC_SAFETY_PATTERNS:
            if pattern.search(text):
                result.add_error(f"Public-safety pattern ({label}) in {rel}")
    return result


def run_doctor(root: Path) -> CheckResult:
    result = CheckResult([], [])
    for check in [
        check_required_files,
        check_skills,
        check_capture_recipe,
        check_golden_questions,
        check_compiled_truth_pages,
        check_manifests,
        check_secrets,
        check_public_safety,
    ]:
        result.extend(check(root))
    return result


def print_check_result(result: CheckResult) -> None:
    if result.errors:
        print("ERRORS")
        for error in result.errors:
            print(f"- {error}")
    if result.warnings:
        print("WARNINGS")
        for warning in result.warnings:
            print(f"- {warning}")
    if result.ok():
        print("doctor: OK")


def source_id_for(path: Path, content_hash: str) -> str:
    slug = slugify(path.stem)[:40]
    return f"src-{slug}-{content_hash[:10]}"


def load_source_manifest(root: Path) -> dict[str, dict[str, object]]:
    manifest = root / "knowledge" / "manifests" / "sources.jsonl"
    entries: dict[str, dict[str, object]] = {}
    if not manifest.exists():
        return entries
    for line in read_text(manifest).splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        entries[str(item["content_hash"])] = item
    return entries


def add_source_to_manifest(root: Path, source: Path) -> dict[str, object]:
    root = root.resolve()
    source = source.resolve()
    try:
        rel = source.relative_to(root).as_posix()
    except ValueError as exc:
        raise SystemExit(f"Source must be inside repo root: {source}") from exc
    content = read_text(source)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    existing = load_source_manifest(root).get(content_hash)
    if existing:
        return {**existing, "status": "already-recorded"}
    item: dict[str, object] = {
        "source_id": source_id_for(source, content_hash),
        "path": rel,
        "content_hash": content_hash,
        "recorded_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "status": "recorded",
    }
    manifest = root / "knowledge" / "manifests" / "sources.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    return item


def parse_golden_questions(text: str) -> list[dict[str, object]]:
    questions: list[dict[str, object]] = []
    sections = re.split(r"^##\s+", text, flags=re.MULTILINE)
    for section in sections:
        if not section.startswith("GQ"):
            continue
        header, *rest = section.splitlines()
        match = re.match(r"(GQ\d{3})\s+—\s+(.+)", header)
        if not match:
            continue
        body = "\n".join(rest)
        sources = re.findall(r"^- Expected source:\s+`([^`]+)`", body, flags=re.MULTILINE)
        terms_match = re.search(r"^- Must mention:\s+(.+)$", body, flags=re.MULTILINE)
        terms = []
        if terms_match:
            terms = [term.strip() for term in terms_match.group(1).split(",") if term.strip()]
        questions.append(
            {
                "id": match.group(1),
                "question": match.group(2).strip(),
                "expected_sources": sources,
                "must_mention": terms,
            }
        )
    return questions


def run_eval(root: Path, limit: int = 5) -> str:
    path = root / "knowledge" / "eval" / "golden-questions.md"
    questions = parse_golden_questions(read_text(path))
    lines = [
        "---",
        "type: eval",
        f'title: "Eval run {today()}"',
        f"created: {today()}",
        "tags: [eval, generated]",
        "---",
        "",
        f"# Eval run {today()}",
        "",
        "| ID | Source@5 | Top result | Notes |",
        "|---|---:|---|---|",
    ]
    passed = 0
    for question in questions:
        results = search_docs_filtered(
            root,
            str(question["question"]),
            limit=limit,
            include_raw=True,
            exclude_prefixes=("knowledge/eval/",),
        )
        top = results[0][1].rel if results else "(none)"
        expected = set(question["expected_sources"])
        hit = any(doc.rel in expected for _, doc, _ in results) if expected else bool(results)
        passed += int(hit)
        notes = "ok" if hit else "missing expected source"
        lines.append(f"| {question['id']} | {'yes' if hit else 'no'} | `{top}` | {notes} |")
    lines.extend(["", f"Score: {passed}/{len(questions)} source hits at {limit}."])
    return "\n".join(lines).rstrip() + "\n"


def cmd_index(args: argparse.Namespace) -> int:
    root = find_root(Path(args.root) if args.root else None)
    output = root / "knowledge" / "wiki" / "INDEX.md"
    text = render_index(root)
    if args.check:
        current = read_text(output) if output.exists() else ""
        if current != text:
            print("Index is stale. Run: python3 scripts/brain.py index")
            return 1
        print("index: OK")
        return 0
    write_text(output, text)
    print(f"wrote {output.relative_to(root)}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    root = find_root(Path(args.root) if args.root else None)
    results = search_docs(root, args.query, limit=args.limit, include_raw=not args.compiled_only)
    for score, doc, snippet in results:
        print(f"{score:6.2f}  {doc.rel}  {doc.title}")
        print(textwrap.indent(snippet, "        "))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    root = find_root(Path(args.root) if args.root else None)
    result = run_doctor(root)
    print_check_result(result)
    return 0 if result.ok() else 1


def cmd_manifest_add(args: argparse.Namespace) -> int:
    root = find_root(Path(args.root) if args.root else None)
    item = add_source_to_manifest(root, root / args.source)
    print(json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    root = find_root(Path(args.root) if args.root else None)
    report = run_eval(root, limit=args.limit)
    if args.write:
        output = root / "knowledge" / "eval" / f"eval-{today()}.md"
        write_text(output, report)
        print(f"wrote {output.relative_to(root)}")
    else:
        print(report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="wai-brain deterministic maintenance CLI")
    parser.add_argument("--root", help="repo root, defaults to nearest wai-brain root")
    sub = parser.add_subparsers(dest="command", required=True)

    index = sub.add_parser("index", help="rebuild knowledge/wiki/INDEX.md")
    index.add_argument("--check", action="store_true", help="fail if index is stale")
    index.set_defaults(func=cmd_index)

    search = sub.add_parser("search", help="rank Markdown evidence for a query")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--compiled-only", action="store_true")
    search.set_defaults(func=cmd_search)

    doctor = sub.add_parser("doctor", help="validate repo invariants")
    doctor.set_defaults(func=cmd_doctor)

    manifest = sub.add_parser("manifest-add-source", help="record source hash in sources manifest")
    manifest.add_argument("source")
    manifest.set_defaults(func=cmd_manifest_add)

    eval_parser = sub.add_parser("eval", help="run golden retrieval questions")
    eval_parser.add_argument("--limit", type=int, default=5)
    eval_parser.add_argument("--write", action="store_true")
    eval_parser.set_defaults(func=cmd_eval)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
