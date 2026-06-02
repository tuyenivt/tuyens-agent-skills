---
name: task-regression-scenario
description: Scaffold a Playwright scenario for a named flow in .regression/flows.yaml. Infers kind (api/browser/mixed), emits golden + negative paths, lints and dry-runs.
metadata:
  category: testing
  tags: [regression, playwright, scenario, authoring, typescript]
  type: workflow
user-invocable: true
---

# Task: Regression Scenario

Scaffolds a single Playwright `.spec.ts` for one named flow from `flows.yaml`. The workflow emits a reviewable draft; the user edits before commit.

## When to Use

- After `task-regression-discover` populated `flows.yaml` and the user accepted a flow.
- When adding coverage for a flow surfaced by a postmortem or release-gate gap.

**Not for:**
- Editing an existing scenario in place (use `--overwrite`, or hand-edit).
- Authoring helpers / POMs - those live in `.regression/fixtures/`.
- Unit/integration tests -> `task-<stack>-test`.

## Inputs

| Input | Notes |
| --- | --- |
| `<flow-name>` | Required. Must match an entry in `.regression/flows.yaml`. |
| `--kind <api\|browser\|mixed>` | Override the inferred kind. Default: inferred from flow shape. |
| `--overwrite` | Replace an existing scenario at the target path. Without it, the workflow stops on collision and prints the existing path. Always prints the unified diff before replacing, never silent. |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Resolve Flow and Infer Kind

1. Load `.regression/flows.yaml`. If missing, **abort** (non-zero) with a pointer to `/task-regression-discover`. No report block emitted.
2. Look up `<flow-name>`. If not found, **abort** (non-zero) with the list of available flow names. No fuzzy matching, no "did you mean" suggestion - the user types exact names so this stays a quick mistake to correct. No report block emitted.
3. Infer `kind`:
   - All hops API-only, no UI entry -> `api`.
   - Browser entry, all assertions UI-observable -> `browser`.
   - Browser entry with API setup, or browser entry with DB observable -> `mixed`.
   Honor `--kind` if provided (the workflow trusts the user when an override is given).
4. Resolve target: `.regression/scenarios/<kind>/<flow-name>.spec.ts`. Create the `<kind>/` directory if absent.
5. If the file exists: without `--overwrite`, **stop** (non-zero) and print the existing path. With `--overwrite`, surface the unified diff (current vs. about-to-write) before Step 3 emits.

**Stop / abort semantics.** Either word means the workflow exits non-zero, prints the reason, and does not emit the Output Format report block. The skill never auto-fixes a missing flow or a name collision.

### Step 3 - Author the Scenario

Use skill: `regression-scenario-author`.

Emit `<target>.spec.ts` containing:

- Idempotent setup using seed-resident literal IDs from `.regression/seeds/` (never `gen_random_uuid()` in test code).
- Golden-path assertions covering each `observableOutcome` in the flow.
- One explicit negative-path stub (invalid input, missing auth, conflicting state). `test.fixme` is allowed when assertions are not yet authored; a silent gap is not.
- Data factory imports from `.regression/fixtures/`.
- Read-after-write via bounded poll (max 5s, 200ms backoff). No raw `sleep` / `waitForTimeout`.
- Trace-on-failure inherited from `playwright.config.ts`; no per-test trace override.

**Out-of-Playwright-fixture transports.** Flows that touch Kafka / gRPC streaming / native WebSocket beyond Playwright's `request` and `page` fixtures stay observable via downstream HTTP / DB state in the scenario. If a flow asserts directly on the transport itself, this workflow stops and refers the user to `regression-scenario-author` to extend its fixtures - it does not invent fixtures here.

### Step 4 - Lint and Dry-Run

From the test repo root:

1. `( cd .regression && npx tsc --noEmit )`.
2. `( cd .regression && npx playwright test --list <target> )`.
3. Surface every error with `file:line`.

**On failure.** Do not retry, do not auto-fix. The emitted draft remains on disk so the user can edit. The workflow exits non-zero; the report block surfaces the errors. Execution of the scenario itself belongs to `task-regression`.

## Output Format

Emitted only when Steps 2-4 all completed (resolved flow, written file, dry-run attempted). Aborts emit a one-line reason instead.

```markdown
# Regression Scenario Report

**Flow:** {flow-name}
**Kind:** {api | browser | mixed} ({inferred | overridden})
**Target:** .regression/scenarios/{kind}/{flow-name}.spec.ts ({new | overwritten})

## Coverage drafted

- Golden path: {one-line summary of assertions}
- Negative path: {one-line summary; marked test.fixme if assertions pending}
- Observable outcomes asserted: {N / total from flows.yaml}

## Dry-run

| Check | Result |
| --- | --- |
| `tsc --noEmit` | pass / {N} errors (file:line listed below) |
| `playwright test --list` | discovered: {test titles} / skipped (tsc failed) |

## Next

- Review and edit `.regression/scenarios/{kind}/{flow-name}.spec.ts` before commit.
- Run the single scenario: `( cd .regression && npx playwright test {flow-name} )` (or `/task-regression --grep @<tag>`).
- Commit when green.
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded.
- [ ] Step 2: `flows.yaml` loaded; flow resolved (or workflow aborted non-zero with no report); kind inferred or overridden honored; target dir created; `--overwrite` printed the diff before replacement.
- [ ] Step 3: `regression-scenario-author` emitted scenario with idempotent setup, golden-path assertions for every observable outcome, one explicit negative path, and bounded read-after-write helper; out-of-fixture transports observed via downstream state, not invented fixtures.
- [ ] Step 4: `tsc --noEmit` ran; `playwright test --list` ran (or was skipped because tsc failed); errors surfaced with `file:line`; exit non-zero on failure; no auto-fix attempted.

## Avoid

- Running `playwright test` (without `--list`) here. Execution belongs to `task-regression`.
- Inventing endpoint paths or DB tables not present in the flow's `hops` / `observableOutcome`.
- Omitting the negative path. Every scenario has one, even if `test.fixme`.
- `setTimeout` / `page.waitForTimeout` for async side effects. Use the bounded poll.
- Generating random UUIDs in the scenario. Reference seed-resident literal IDs.
- Overwriting an existing scenario without `--overwrite` *and* without printing the diff.
- Writing helpers into the scenario file. Helpers live in `.regression/fixtures/`.
- Fuzzy-matching the flow name. Exact match only.
- Auto-fixing tsc or `playwright test --list` errors. Surface and stop.
