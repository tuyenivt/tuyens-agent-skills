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

Scaffolds a single Playwright `.spec.ts` for one named flow from `flows.yaml`. Mirrors how `task-<stack>-test` works for unit tests: the workflow emits a reviewable draft; the user edits before commit.

## When to Use

- After `task-regression-discover` has populated `flows.yaml` and the user accepts a flow.
- When adding coverage for a flow surfaced by a postmortem or release-gate gap.

**Not for:**
- Editing an existing scenario.
- Authoring helpers/POMs - put those in `.regression/fixtures/`.
- Unit/integration tests -> `task-<stack>-test`.

## Inputs

| Input | Notes |
| --- | --- |
| `<flow-name>` | Required. Must match an entry in `.regression/flows.yaml`. |
| `--kind <api\|browser\|mixed>` | Override inferred kind. Default: inferred from flow shape. |
| `--overwrite` | Replace an existing scenario at the target path. Default: refuse and surface diff. |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Resolve Flow and Infer Kind

1. Load `.regression/flows.yaml`. Abort with a clear pointer to `/task-regression-discover` if missing.
2. Look up the named flow. If not found, list available flow names and stop.
3. Infer `kind`:
   - All hops are API-only and no UI entry -> `kind: api`.
   - Entry is browser-driven and all assertions are UI-observable -> `kind: browser`.
   - Browser entry with API setup, or browser entry with DB observable -> `kind: mixed`.
4. Honor `--kind` override if provided.
5. Resolve target path: `.regression/scenarios/<kind>/<flow-name>.spec.ts`.
6. If the file exists and `--overwrite` is not set, show the existing file path and stop with a hint to use `--overwrite` or rename.

### Step 3 - Author the Scenario

Use skill: `regression-scenario-author`.

Emit `<target>.spec.ts` containing:

- Idempotent setup (reuses seed-resident literal IDs from `.regression/seeds/`; no `gen_random_uuid()` in test code).
- Golden-path assertions covering each `observableOutcome` in the flow.
- One explicit negative-path stub (invalid input, missing auth, conflicting state) with a `test.fixme` or `test.skip` if assertions are not yet authored - never a silent gap.
- Data factory imports from `.regression/fixtures/`.
- Trace-on-failure inherited from `playwright.config.ts`; no per-test trace override.
- Read-after-write helper for async side effects (bounded retry, max 5s, 200ms backoff). No raw `sleep`.

### Step 4 - Lint and Dry-Run

From `.regression/`:

1. `npx tsc --noEmit` on the new file (or full project if cheaper).
2. `npx playwright test --list <target>` to confirm the test is discoverable.
3. Surface any lint/TS errors with file:line.

Do not actually execute the scenario - that is `task-regression`'s job.

## Output Format

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
| `tsc --noEmit` | pass / {N} errors |
| `playwright test --list` | discovered: {test titles} |

## Next

- Review and edit `.regression/scenarios/{kind}/{flow-name}.spec.ts` before commit.
- Run the single scenario: `npx playwright test {flow-name}` from `.regression/` (or `/task-regression --grep @<tag>`).
- Commit when green.
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: flow resolved from `flows.yaml`; kind inferred from flow shape (or override honored); target path collision handled
- [ ] Step 3: `regression-scenario-author` emitted scenario with idempotent setup, golden-path assertions for every observable outcome, and one explicit negative path
- [ ] Step 4: `tsc --noEmit` passed and `playwright test --list` discovered the new test; errors surfaced with file:line

## Avoid

- Running `playwright test` (without `--list`) here. Execution belongs to `task-regression`.
- Inventing endpoint paths or DB tables not present in the flow's `hops` / `observableOutcome`.
- Omitting the negative path. Every scenario has one, even if `test.fixme`.
- Hardcoding `setTimeout` or `sleep` for async side effects. Use the bounded retry helper.
- Generating random UUIDs in the scenario. Reference seed-resident literal IDs.
- Overwriting an existing scenario without `--overwrite`. Surface and stop.
- Writing helpers into the scenario file. Helpers live in `.regression/fixtures/`.
