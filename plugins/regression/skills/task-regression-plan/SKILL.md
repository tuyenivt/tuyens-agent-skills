---
name: task-regression-plan
description: Export a human-readable test plan from .regression/ - joins flows.yaml + scenarios/ into one Markdown doc with per-flow intent, steps, expected outcome, negative cases, evidence, and a Coverage column.
metadata:
  category: testing
  tags: [regression, test-plan, documentation, qa, release]
  type: workflow
user-invocable: true
---

# Task: Regression Plan

Read-only export. Joins `.regression/flows.yaml` with `.regression/scenarios/**/*.spec.ts` and emits a single Markdown document - the **test plan** - intended for QA leads, release managers, and auditors who need to see what the suite is supposed to verify (not what a run produced).

Never mutates `flows.yaml`, scenarios, or any sibling repo. Output is one file: `.regression/test-plan.md` (or the path passed to `--out`). The coverage column (`covered` / `no-spec` / `orphan`) falls out of the join for free; deeper coverage analysis (redundancy, stale evidence) is out of scope and stays a separate future workflow.

## When to Use

- Before a release: sign-off document showing what regression covers.
- Handover / audit: give a non-engineer a readable inventory of intended verifications.
- Onboarding: new team member needs to see the test surface without reading 40 `.spec.ts` files.
- Periodically, to spot `no-spec` flows (uncovered intent) and `orphan` specs (drifted from declared flows).

**Not for:**
- A run report -> `task-regression` produces `reports/<runId>/summary.md` via `regression-report-format`.
- Authoring or refreshing flows -> `task-regression-discover`.
- Authoring a single scenario -> `task-regression-scenario`.
- Deep coverage analysis (redundancy, staleness, evidence re-validation against sibling repos) -> not shipped; revisit when the suite has actually rotted.

## Inputs

| Input | Default | Notes |
| --- | --- | --- |
| `--out <path>` | `.regression/test-plan.md` | Output file. Relative to the test repo root. Parent directory must exist. |
| `--group-by <flow-kind\|service\|none>` | `flow-kind` | Top-level grouping. `flow-kind` groups by `api` / `browser` / `mixed`. `service` groups by the `entryPoint.service`. `none` emits one flat sorted list. |
| `--include-orphans` | on | Include an "Orphan scenarios" appendix listing `.spec.ts` files with no matching `flows.yaml` entry. Pass `--include-orphans=false` to suppress. |
| `--format <markdown>` | `markdown` | Only Markdown ships in v1. Reserved for future `csv` / `html` without forcing a flag rename. |

**Working directory.** Invoke from the test repo root (the directory containing `.regression/`). All paths below are relative to that root.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Preflight

In order; first failure stops with the named remediation:

1. `.regression/flows.yaml` exists. Missing -> abort with `task-regression-plan: .regression/flows.yaml not found; run /task-regression-discover first.`
2. `.regression/scenarios/` exists. Missing -> warn and continue (every flow will render as `no-spec`; orphan appendix will be empty). Do not abort - a plan with all gaps is still a useful document.
3. `--out` parent directory exists. Missing -> abort with `task-regression-plan: parent directory of <path> does not exist.`
4. **No codemap / OpenAPI / sibling-repo read.** Plan generation is offline against `.regression/` only.

### Step 3 - Load Flows

Parse `.regression/flows.yaml`. For each entry read: `name`, `kind`, `entryPoint`, `hops`, `observableOutcome`, `evidence`, and any optional fields the user added (`owner`, `tags`, `priority`, `status`). Unknown fields are passed through into the plan's "Additional fields" sub-row - never dropped, never validated. Schema authority remains with `regression-flow-extract` (Patterns / Candidate shape); this skill is a reader.

Unresolved `<USER FILL>` markers in any flow field are surfaced verbatim in the plan, prefixed `<USER FILL>` so the reader sees them as gaps. The plan does not abort on them - it documents them. (`task-regression-scenario` is the gate that refuses to scaffold unresolved markers; this workflow is documentation.)

### Step 4 - Scan Scenarios

Glob `.regression/scenarios/**/*.spec.ts`. For each file:

- Derive `flow-name` from the basename (`<flow>.spec.ts` -> `<flow>`). This is the join key, set by `regression-scenario-author` Rule 1.
- Derive `kind` from the parent directory (`scenarios/api/...` -> `api`, `browser` -> `browser`, `mixed` -> `mixed`). Files under `scenarios/` but not in one of these three subdirectories are recorded as `unknown-kind` orphans.
- Parse the file as text (no execution, no AST). Extract:
  - Every `test(...)` title via regex `test\(\s*["'\`]([^"'\`]+)["'\`]`. Tags are substrings starting with `@` inside the title (e.g. `@smoke`, `@negative`, `@flake`).
  - `// flake (REG-\d+|TODO-[a-z0-9-]+); remove after fix` comments (the `regression-scenario-author` Rule 5 marker) - listed under "Known flake markers" for that flow.
- Do not attempt to validate POM imports, fixture usage, or assertion shape. The plan is descriptive, not a lint.

### Step 5 - Join and Classify

Build the join table keyed by flow name. Each row gets a `coverageStatus`:

| Status | Condition |
| --- | --- |
| `covered` | flow entry exists in `flows.yaml` AND a `.spec.ts` exists at `scenarios/<kind>/<name>.spec.ts` AND its parent-dir `kind` matches the flow's declared `kind` |
| `kind-mismatch` | flow entry + spec both exist, but the spec lives under a different `<kind>/` than the flow declares (rare, indicates a manual move; surfaced so the user can fix one or the other) |
| `no-spec` | flow entry exists, no matching spec file |
| `orphan` | spec file exists, no matching flow entry |

Orphans are not rows in the main table - they go in the appendix (Step 6).

### Step 6 - Emit Plan

Write to `--out` (default `.regression/test-plan.md`). If the file exists, show a unified diff and ask `replace / cancel`. Never silently overwrite. The exact section order is fixed (see Output Format) - downstream tooling may grep these headers.

### Step 7 - Summary

Print a short summary to the user: total flows, covered / no-spec / kind-mismatch / orphan counts, output path. Do not duplicate the document body in the console.

## Output Format

```markdown
# Regression Test Plan

**Workspace:** .regression/
**Generated at:** {ISO timestamp}
**Group-by:** {flow-kind | service | none}

## Summary

| Bucket | Count |
| --- | --- |
| Total flows | {N} |
| Covered | {N} |
| No spec | {N} |
| Kind mismatch | {N} |
| Orphan scenarios | {N} |

## Flows

### {group label - e.g. "Kind: mixed" or "Service: api" or "All flows"}

#### {flow-name}

- **Coverage:** {covered | no-spec | kind-mismatch | orphan}
- **Kind:** {api | browser | mixed}
- **Entry point:** {service} - {action}
- **Steps:**
  1. {hop.from} -> {hop.to}: {hop.call}
  2. ...
- **Expected outcome:**
  - {observableOutcome[0]}
  - ...
- **Negative cases:** {list of test() titles tagged @negative, or `_None declared._`}
- **Evidence:** {comma-separated `key: value` from flow.evidence, or `_skeleton_` for evidence: skeleton}
- **Scenario file:** `.regression/scenarios/{kind}/{name}.spec.ts` (or `_missing_` for no-spec)
- **Tests in file:** {comma-separated test titles, or `_n/a_` for no-spec}
- **Known flake markers:** {list of `REG-... / TODO-...` tokens from `// flake` comments, or omitted if none}
- **Additional fields:** {`owner: ...`, `priority: ...`, etc. from flows.yaml, or omitted if none}

... (repeat per flow within group)

... (repeat per group)

## Orphan scenarios

Scenario files under `.regression/scenarios/` with no matching entry in `flows.yaml`. Either add a flow entry (run `/task-regression-discover --refresh-flows` and accept the candidate, or hand-author the entry) or delete the file.

- `.regression/scenarios/{kind}/{name}.spec.ts` - {comma-separated test titles}
- ...

(Omitted entirely if `--include-orphans=false` or no orphans.)

## Next

- `no-spec` flows: `/task-regression-scenario "<flow-name>"` to scaffold.
- `orphan` scenarios: add the missing `flows.yaml` entry or delete the spec.
- `kind-mismatch`: move the spec file or fix the flow's `kind:` declaration.
- Run the suite: `/task-regression`.
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded.
- [ ] Step 2: `flows.yaml` exists; `scenarios/` absence warned but did not abort; `--out` parent directory verified; no codemap / OpenAPI / sibling-repo read.
- [ ] Step 3: every `flows.yaml` entry parsed; unknown fields passed through; `<USER FILL>` markers surfaced verbatim, not silently filtered.
- [ ] Step 4: every `.spec.ts` under `scenarios/` scanned by text; `test()` titles and tags extracted; flake-marker comments captured; no execution, no AST.
- [ ] Step 5: join keyed by flow name (= spec basename); `covered` / `no-spec` / `kind-mismatch` / `orphan` assigned per the table; orphan list deferred to appendix.
- [ ] Step 6: output file written at `--out`; pre-existing file diffed and confirmed before replace; fixed section headers used verbatim.
- [ ] Step 7: summary printed (counts + output path); document body not duplicated in console.

## Avoid

- Mutating `flows.yaml`, scenarios, or sibling repos. This workflow is read-only.
- Executing the suite or any scenario file. The plan is offline.
- Reading codemap, OpenAPI, or sibling repos. Discovery-time inputs are not consulted here.
- Silently overwriting an existing `--out` file. Always diff and confirm.
- Inferring missing fields. `<USER FILL>` stays `<USER FILL>` in the plan.
- Asserting redundancy or staleness. Those are separate (unshipped) analyses.
- Embedding run results (pass/fail counts, durations). The plan is forward-looking intent, not run history.
- Dropping unknown flow fields. Pass them through into "Additional fields".
