# weekly-review

## When to use

Use on Friday or on demand to summarize the last 7 days of repository and capture activity.

## Procedure

1. Run `git log --since='7 days ago' --oneline -- knowledge infra .claude scripts tests`.
2. Review `knowledge/wiki/log.md`, recent eval reports, and recent `_inbox` files.
3. Summarize:
   - major decisions
   - new or changed project/person/topic pages
   - unresolved Open Threads
   - eval/lint regressions
   - next three maintenance actions
4. Append a dated entry to `knowledge/wiki/log.md`.
5. Run `python3 scripts/brain.py doctor`.

## Output

Keep the chat answer short and link to the log entry. Do not quote sensitive raw content.
