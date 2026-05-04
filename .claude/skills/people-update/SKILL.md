# people-update

## When to use

Use whenever creating or updating a file under `knowledge/people/`.

## Procedure

1. Read the target person page and the new source evidence.
2. Add a newest-first timeline entry below the first standalone `---`.
3. Rewrite compiled truth above the split so it reflects the current best understanding.
4. Keep uncertainty explicit. If evidence conflicts, add an Open Thread rather than flattening the conflict.
5. Update `compiled_truth_updated` when State changes.
6. Run `python3 scripts/brain.py doctor`.

## Required shape

Above the split:

- executive summary blockquote
- `## State`
- `## Open Threads`

Below the split:

- `## Timeline`
- entries in `- **YYYY-MM-DD** | summary. [Source: ...]` format
