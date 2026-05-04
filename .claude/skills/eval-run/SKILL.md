# eval-run

## When to use

Use monthly, after major ingest batches, and before claiming search/retrieval improvements.

## Procedure

1. Read `knowledge/eval/golden-questions.md`.
2. Run `python3 scripts/brain.py eval --write`.
3. Inspect the generated `knowledge/eval/eval-YYYY-MM-DD.md`.
4. For every failed expected-source hit, decide whether the problem is:
   - missing compiled page
   - bad query wording
   - weak local search ranking
   - missing source citation
5. Fix content or golden questions, then rerun eval and `python3 scripts/brain.py doctor`.

## Metrics

Track at minimum:

- source hit at top 5
- top result path
- failed expected source
- notes for manual follow-up
