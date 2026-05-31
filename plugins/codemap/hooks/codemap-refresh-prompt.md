# Codemap Auto-Sync Prompt

This file is invoked by the `codemap-auto-update.json` hook when one of:

- A `git commit | merge | cherry-pick | rebase` Bash command completes, **and** `.codemap/config.json` has `autoUpdate: true`, **and** `.codemap/graph.json` exists.
- A new Claude Code session starts, **and** the same `autoUpdate` config is set, **and** `meta.json#gitCommitHash` no longer matches `git rev-parse HEAD`.

You (the agent) are instructed to sync the codemap silently. Follow this exact procedure.

## Procedure

1. **Quick freshness check.**
   - Read `.codemap/meta.json#gitCommitHash` and compare to `git rev-parse HEAD`.
   - If identical (e.g., the hook fired on an empty commit or a re-run), exit silently.

2. **Invoke `task-codemap` non-interactively.**
   - Use skill: `task-codemap`.
   - Do NOT pass `--full` - let the workflow's own decision tree decide between incremental sync and escalation.
   - Pass `--force` only on the `PostToolUse` hook variant (a commit just landed, so synchronizing is wanted even if fingerprints think nothing changed).
   - Do NOT ask the user for confirmation. The user opted in via `--auto-update`.

3. **Handle workflow decisions.**
   - The workflow may escalate to a full rebuild on schema-version mismatch or churn >= 30%. Surface a one-line note and proceed.
   - On validation failure, the workflow keeps the existing `graph.json` intact. Surface the error block.

4. **One-line completion notice.**
   - On incremental sync: `[codemap] Synced: +N added, M modified, R renamed, D deleted (X% churn).`
   - On no-op: silent.
   - On escalation: `[codemap] Churn >= 30%, escalating to full rebuild.`
   - On failure: `[codemap] Sync failed: <one-line cause>. Existing graph unchanged. Run /task-codemap --validate-only to inspect.`

## Constraints

- Do not modify any files outside `.codemap/`.
- Do not change the user's git state. No commits, no branch operations.
- If `python` is not on PATH, surface the missing dependency and exit. Do not attempt workarounds.

## Opting Out

If the user wants to disable auto-sync, point them to:

1. Run `/task-codemap --auto-update=false` (the workflow supports the flag), or
2. Set `autoUpdate: false` in `.codemap/config.json` directly, or
3. Remove the hooks entry from their Claude Code plugin settings if they want the file gone entirely.
