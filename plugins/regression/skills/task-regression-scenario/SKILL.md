---
name: task-regression-scenario
description: Scaffold a Playwright scenario from a named flow or a freeform ticket/story (--from). Infers kind, drafts flows.yaml entry on-the-fly, emits golden + negative paths.
metadata:
  category: testing
  tags: [regression, playwright, scenario, authoring, typescript]
  type: workflow
user-invocable: true
---

# Task: Regression Scenario

Scaffolds one Playwright `.spec.ts` for one flow. Two modes: pass an existing flow name from `flows.yaml`, or pass `--from` with a ticket / incident / user-story narrative. In from-story mode the workflow first drafts a `flows.yaml` entry via `regression-scenario-author`, then scaffolds the test from the accepted entry. All authoring contracts (POMs, fixtures, `@smoke` / `@negative` shape, `<USER FILL>` semantics, evidence rules, no-fabrication) live in `regression-scenario-author`; this workflow orchestrates and gates.

## When to Use

- **From an existing flow:** `task-regression-discover` populated `flows.yaml` and the user accepted a flow.
- **From a ticket / story (`--from`):** a QA ticket, user-reported bug, or postmortem narrative needs an outside-in regression guard.
- When refreshing coverage after a release-gate gap.

**Not for:**
- Editing an existing scenario in place (use `--overwrite` or hand-edit).
- Authoring helpers / page objects - those live under `.regression/fixtures/` and are user-owned.
- Unit / integration tests - delegate to `task-<stack>-test`.

## Inputs

| Input                          | Notes                                                                                                                                                                                                                                                  |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `<flow-name>`                  | From-flow mode. Required; must match exactly an entry in `.regression/flows.yaml`. **Mutually exclusive with `--from`.**                                                                                                                                |
| `--from <text-or-path>`        | From-story mode. Inline narrative or file path (auto-detected: existing file -> read; otherwise -> inline). The workflow drafts a `flows.yaml` entry, asks the user to accept / edit / reject, then scaffolds. **Mutually exclusive with `<flow-name>`.** |
| `--name <slug>`                | From-story mode only. Override the auto-derived flow name (Rule "Flow-name derivation" in `regression-scenario-author`).                                                                                                                                |
| `--kind <api\|browser\|mixed>` | Override the inferred / drafted kind. If a from-story draft yielded `kind: <USER FILL>`, the user must either pass `--kind` or resolve the placeholder in `flows.yaml` before scaffolding (the unresolved-marker gate blocks emission).                  |
| `--overwrite`                  | Replace an existing scenario at the target path. Without it, name collisions abort. Always prints a unified diff before replacing.                                                                                                                       |

**Both `<flow-name>` and `--from` present -> abort (no precedence, no fallback). Neither present -> abort with usage. Other flags (`--name`, `--kind`, `--overwrite`) are not consulted when the mode-detection abort fires.**

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Resolve Mode and Flow

Mode detection happens **before any file I/O**. Both args present -> abort with `task-regression-scenario: pass either <flow-name> or --from, not both.` Neither -> abort with `task-regression-scenario: pass <flow-name> or --from <text-or-path>.`

#### Step 2a - From-flow mode (`<flow-name>` given)

1. Load `.regression/flows.yaml`. Missing -> abort with `task-regression-scenario: .regression/flows.yaml not found; run /task-regression-discover first.` No report block.
2. Exact-match `<flow-name>`. Missing -> abort with `task-regression-scenario: flow '<name>' not found in flows.yaml; available: [list].` No fuzzy match, no "did you mean."
3. Continue at Step 2c with the resolved flow.

#### Step 2b - From-story mode (`--from` given)

`Use skill: regression-scenario-author` for the drafting contract (no-fabrication rules, evidence requirement, `<USER FILL>` semantics, flow-name derivation, kind inference).

1. **Resolve input.** Existing file -> read. Else -> inline text. Empty / whitespace-only -> abort with `task-regression-scenario: --from value is empty.`
2. **Require `services.yaml`.** Missing -> abort with `task-regression-scenario: .regression/services.yaml not found; run /task-regression-discover first.` From-story drafting validates every referenced service against this list.
3. **Draft the entry.** The atomic emits a YAML entry with `<USER FILL>` markers wherever the story is silent and surfaces gaps (missing services, unstated kind, no negative path). The workflow displays the draft, the gap list, and abort conditions.
4. **Resolve the flow name.** `--name` if given; else auto-derived per the atomic's "Flow-name derivation" rule. Collision with an existing entry -> abort with `task-regression-scenario: flow name '<name>' already exists; pass --name <new-slug>.`
5. **Accept / edit / reject prompt.**
   - `accept` -> append the YAML to `.regression/flows.yaml`, continue at Step 2c with the appended entry.
   - `edit` -> the user edits the displayed YAML in their editor; on return, re-validate every rule (services exist in `services.yaml`, evidence non-empty, kind not silently fabricated, name does not collide with existing entries after any rename). Loop until valid or rejected. Each edit cycle re-prints the draft so the conversation log shows the final state.
   - `reject` -> abort with `task-regression-scenario: from-story draft rejected, no files changed.`
6. Continue at Step 2c.

#### Step 2c - Common: Infer Kind and Resolve Target

1. **Resolve `kind`.** Precedence: `--kind` flag -> flow entry's `kind:` if a literal value -> abort if `<USER FILL>` and no `--kind`. Abort message: `task-regression-scenario: flow '<name>' has kind=<USER FILL>; pass --kind <api|browser|mixed> or resolve the placeholder in flows.yaml.`
2. **Resolve target.** `.regression/scenarios/<kind>/<flow-name>.spec.ts`. Create the `<kind>/` directory if absent.
3. **Collision check.** Target exists, no `--overwrite` -> abort with `task-regression-scenario: <target> exists; pass --overwrite to replace.` With `--overwrite` -> print a unified diff against the existing file before Step 3 emits. Never silent replacement.

### Step 3 - Author the Scenario

Use skill: `regression-scenario-author`.

The atomic owns: idempotent identifier scoping (`scopedId` / `scopedEmail` from `regression-data-isolation`), bounded `pollUntil` semantics, POM imports, the `@smoke` / `@negative` rule, mid-flow HTTP-hop assertions for browser-driven mixed flows, DB-state assertions, the kind-specific template differences, and the `<USER FILL>` gate.

Two behaviors this workflow enforces around the atomic, in this order:

1. **`<USER FILL>` gate (runs first).** Scan the resolved flow entry. Any `<USER FILL>` in `kind`, `entryPoint`, `hops`, or `observableOutcome` -> abort with `task-regression-scenario: flow '<name>' has unresolved <USER FILL> in <field>; resolve in flows.yaml and re-run.` The drafting step is the legitimate producer of these markers; the scaffolding step is the gate. Running this first avoids asking a follow-up question that the user would then have to discard. Alternative shapes like `<USER FILL: a | b>` count as unresolved; alternatives are surfaced to the user, not silently picked.
2. **Negative-path gate (runs second, only if the `<USER FILL>` gate passed).** Detect a missing negative by the absence of a story-stated failure mode the atomic could ground a `@negative` test on. Ask `task-regression-scenario: flow '<name>' has no negative variant in the story; describe one (validation / authz / conflict) or pass --negative <description>.` Wait for the user's answer, pass it through to the atomic, then resume. Never auto-emit `test.fixme` / `test.skip`.

### Step 4 - Lint and Dry-Run

From the test repo root:

1. `( cd .regression && npx tsc --noEmit )`.
2. `( cd .regression && npx playwright test --list scenarios/<kind>/<flow-name>.spec.ts )` - pass the relative file path of the target, not the flow-name slug.
3. Surface every error with `file:line`.

On failure: do not retry, do not auto-fix. The emitted draft remains on disk; the workflow exits non-zero; the report block lists the errors. Execution of the scenario itself belongs to `task-regression`.

## Output Format

The interactive accept / edit / reject prompt happens mid-Step-2b; the report block below fires only after Step 4 completes successfully. Aborts at any step emit the one-line reason given in that step instead - no report block.

```markdown
# Regression Scenario Report

**Mode:** {from-flow | from-story}
**Flow:** {flow-name}
**Kind:** {api | browser | mixed} (source: {flow-entry | --kind flag | from-story inference})
**Target:** .regression/scenarios/{kind}/{flow-name}.spec.ts ({new | overwritten})

## Flow drafted

Omit this section entirely in from-flow mode. In from-story mode:

- Source: {file path | inline snippet, first 80 chars}
- Evidence cited: {N entries; keys used}
- Services referenced: {list; all validated against services.yaml}
- `<USER FILL>` fields remaining in flows.yaml entry: {N}

## Coverage drafted

- Golden path (`@smoke`): {one-line summary covering each observableOutcome}
- Negative path (`@negative`): {one-line summary; the user-supplied or story-derived failure mode}
- Observable outcomes asserted: {N of N from flows.yaml}

## Dry-run

| Check                       | Result                                          |
| --------------------------- | ----------------------------------------------- |
| `tsc --noEmit`              | pass / {N} errors (file:line listed below)      |
| `playwright test --list`    | discovered: {test titles} / skipped (tsc failed) |

## Next

- Review and edit `.regression/scenarios/{kind}/{flow-name}.spec.ts` before commit.
- Resolve any `<USER FILL>` placeholders in the new `flows.yaml` entry (from-story mode).
- Run the single scenario: `( cd .regression && npx playwright test {flow-name} )`, or via the suite: `/task-regression --grep @<tag>`.
- Commit when green.
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded.
- [ ] Step 2: mode detected before any file I/O; both-present and neither-present aborted with the specified messages; from-flow path exact-matched against `flows.yaml`; from-story path validated services, required evidence, surfaced gaps including the negative-path question, ran the accept / edit / reject loop, honored `--name` collisions; kind resolved with `--kind` > flow literal > abort; collision check produced a diff when `--overwrite` was passed.
- [ ] Step 3: delegated to `regression-scenario-author`; unresolved `<USER FILL>` in the flow entry aborted before scaffolding; negative path was supplied (story-derived or via the user prompt) before the `.spec.ts` was written; no `test.fixme` / `test.skip` in `@negative`.
- [ ] Step 4: `tsc --noEmit` ran; `playwright test --list` ran (or was skipped because tsc failed); errors surfaced with `file:line`; exit non-zero on failure; no auto-fix.

## Avoid

- Treating both-args present as a from-flow or from-story preference. Always abort.
- Skipping the accept / edit / reject prompt in from-story mode. The user is the gate.
- Auto-resolving `<USER FILL>` markers in flows.yaml. The drafting step produces them; the user resolves them.
- Auto-emitting `test.fixme` / `test.skip` for a missing `@negative`. Ask the user.
- Silent overwrite. `--overwrite` always prints a unified diff first.
- Running `playwright test` without `--list` here. Execution belongs to `task-regression`.
- Auto-fixing tsc or `playwright test --list` errors. Surface and stop.
- Fuzzy-matching the flow name. Exact match only.
