---
name: task-regression-plan
description: Export regression test plan - joins flows.yaml + scenarios/ into one Markdown doc with per-flow intent, steps, evidence, Coverage column.
metadata:
  category: testing
  tags: [regression, test-plan, documentation, qa, release]
  type: workflow
user-invocable: true
---

# Task: Regression Plan

Read-only export. Joins `.regression/flows.yaml` with `.regression/scenarios/**/*.spec.ts` and writes one Markdown file - the **test plan** - for QA leads, release managers, and auditors who need to see what the suite is supposed to verify, not what a run produced.

The skill never mutates `flows.yaml`, scenarios, or sibling repos. The Coverage column (`covered` / `kind-mismatch` / `no-spec` / `orphan`) falls out of the join; redundancy and stale-evidence analysis are out of scope.

## When to Use

- Release sign-off: an inventory of intended verifications.
- Handover / audit: a readable summary for non-engineers.
- Onboarding: a single document instead of 40 `.spec.ts` files.
- Periodic check: surface `no-spec` flows (uncovered intent), `kind-mismatch` rows (drift), and `orphan` specs (declared-flow gap).

**Not for:** run reports (`task-regression`), authoring flows (`task-regression-discover`), authoring a scenario (`task-regression-scenario`), deeper coverage analysis (unshipped).

## Inputs

| Input | Default | Notes |
| --- | --- | --- |
| `--out <path>` | `.regression/test-plan.md` | Output file, relative to the test repo root. Parent directory must already exist (skill does not create it). |
| `--group-by <flow-kind\|service\|owner\|none>` | `flow-kind` | `flow-kind`: groups by `api` / `browser` / `mixed`. `service`: groups by the **derived `services`** set (`entryPoint.service` + every `hops[].from/to`); a flow appears once under each distinct service it touches. `owner`: groups by required `owner:` field (`regression-flow-extract` Rule 9). `none`: flat alphabetical list. |
| `--include-orphans` | on | Pass `--include-orphans=false` to omit the appendix. |
| `--force` | off | Overwrite `--out` without the diff-confirm prompt. Use for scripted runs. |

Invoke from the test repo root (the directory containing `.regression/`). All paths below are relative to that root.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Preflight

In order; the first failure aborts with the named message:

1. `.regression/flows.yaml` exists. Missing -> `task-regression-plan: .regression/flows.yaml not found; run /task-regression-discover first.`
2. `.regression/scenarios/` exists. Missing -> warn and continue (every flow will render `no-spec`, orphan appendix empty). A gap-only plan is still useful.
3. `--out` parent directory exists. Missing -> `task-regression-plan: parent directory of <path> does not exist. Create it (mkdir -p <parent>) or rerun with --out under an existing directory; this workflow does not create directories.`

No codemap / OpenAPI / sibling-repo read at any point - generation is offline against `.regression/`.

### Step 3 - Load Flows

Parse `.regression/flows.yaml`. For each entry read every field present. Schema authority remains `regression-flow-extract`; this skill is a reader.

**Field handling:**

- **Known structured fields** (`name`, `kind`, `direction`, `owner`, `status`, `entryPoint`, `hops`, `observableOutcome`, `evidence`, `flowLabels`, `checks`, `clock`, `latencyBudget`, `archetype`) drive the per-flow lines in Output Format.
- **Every other field** (`priority`, ...) passes through into the `Additional fields` sub-row verbatim. No allow-list; nothing is dropped, nothing is validated.
- **`flowLabels:` is the flow-level label set; `@tags` are scenario test-title tags.** They live in different namespaces and were intentionally renamed apart - `tags:` on a flow entry is a legacy field treated as `flowLabels:` for back-compat reads only; new flows use `flowLabels:`.
- **`evidence:` shape.** Contract owned by `regression-flow-extract`: `"skeleton" | Array<{[kebab-key]: string}>`. Scalar `skeleton` -> render `_skeleton_`. List -> render as comma-separated `key: value` pairs (one per single-key map). Multi-line values collapse to single line. Legacy shapes (top-level map, plain list of strings) are read tolerantly but warned at the top of Summary: `legacy evidence shape on flows: <list>`.
- **`<USER FILL>` markers** render verbatim, unchanged. Do not abort - the plan documents gaps; `task-regression-scenario` is the gate that refuses unresolved markers.
- **Duplicate flow names.** Warn once at the top of Summary (`duplicate flow names: <list>`) and render every occurrence; do not dedupe.

### Step 4 - Scan Scenarios

Glob `.regression/scenarios/**/*.spec.ts`. For each file:

- **Flow name** = basename without `.spec.ts` (join key, set by `regression-scenario-author` Rule 1).
- **Spec kind** = parent directory name if `api` / `browser` / `mixed`; else `unknown-kind` (treated as orphan).
- **Tests + tags.** Extract every `test(...)` title via `test\(\s*["'\`]([^"'\`]+)["'\`]`. Tags are substrings beginning with `@` (e.g. `@smoke`, `@negative`, `@flake`). Only `@negative` drives the `Negative cases:` line; other tags ride along inside the verbatim test title. This is deliberate - extending to more structured tag projections is a separate workflow.
- **Flake markers.** Match `// flake \((REG-\d+|TODO-[a-z0-9-]+)\)` (the rest of the line is ignored - permissive on purpose so a missing `; remove after fix` suffix does not silently drop the marker).

No execution, no AST, no POM / fixture / assertion lint.

### Step 5 - Join and Classify

Key by flow name = spec basename.

| Status | Condition |
| --- | --- |
| `covered` | flow entry exists, matching spec exists, spec's parent-dir kind matches flow's declared kind |
| `kind-mismatch` | flow entry + spec both exist, kinds differ |
| `no-spec` | flow entry exists, no matching spec file |
| `orphan` | spec exists, no flow entry (appendix only, not in main table) |

**`kind-mismatch` rendering convention.** Group by the flow's **declared** kind (source of truth = `flows.yaml`). The `Kind:` row line shows the declared kind. The `Scenario file:` line shows the **actual on-disk path** (since that's what the user has to act on). Append `(declared kind <X>, found under <Y>/)` to the file line to make the drift visible.

### Step 6 - Emit Plan

Write to `--out` (default `.regression/test-plan.md`). Use the section headers in Output Format verbatim - downstream tooling may grep them.

If the file exists and `--force` is not set, show a unified diff and ask `replace / cancel`. With `--force`, overwrite silently.

**Sort order.** Groups sorted alphabetically by label; flows within a group sorted alphabetically by name.

### Step 7 - Summary

Print to the console: total flows, per-bucket counts (`covered` / `kind-mismatch` / `no-spec` / `orphan`), grouping mode, output path. Do not duplicate the document body.

## Output Format

Timestamp is ISO-8601 UTC (deterministic across re-runs). Use `_missing_` for absent values and `_none_` for empty lists. Omit lines with no data when explicitly marked "omit if empty" below.

```markdown
# Regression Test Plan

**Workspace:** .regression/
**Generated at:** {ISO-8601 UTC}
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

### {group label - e.g. "Kind: mixed", "Service: gateway-api", "All flows"}

#### {flow-name}

- **Coverage:** {covered | kind-mismatch | no-spec | orphan}
- **Owner:** {kebab-case team slug from `owner:`, or `_missing_`}
- **Status:** {active | deprecated | stale} _(omit if `active`)_
- **Kind:** {declared kind from flows.yaml}{` / direction: <d>` when `kind=mixed`}
- **Entry point:** {service} - {action}
- **Services touched:** {derived union of entryPoint + hops}
- **Steps:**
  1. {hop.from} -> {hop.to}: {hop.call}
- **Expected outcome:**
  - {observableOutcome[0]}
- **Negative cases:** {comma-separated test titles tagged @negative, or `_none_`}
- **Evidence:** {comma-separated `key: value`, `_skeleton_`, or list form}
- **Scenario file:** {actual on-disk path, or `_missing_`} {append `(declared kind <X>, found under <Y>/)` for kind-mismatch}
- **Tests in file:** {comma-separated test titles, or `_missing_`}
- **Known flake markers:** {comma-separated tokens} _(omit if none)_
- **Additional fields:** {`key: value` pairs from non-known flow fields} _(omit if none)_

## Orphan scenarios

Scenario files under `.regression/scenarios/` with no matching entry in `flows.yaml`. Add a flow entry (`/task-regression-discover --refresh-flows`) or delete the file.

- `.regression/scenarios/{kind}/{name}.spec.ts` - {test titles}

_(Omit section if `--include-orphans=false` or no orphans.)_

## Next

- `no-spec` flows: `/task-regression-scenario "<flow-name>"`.
- `orphan` scenarios: add a `flows.yaml` entry or delete the spec.
- `kind-mismatch`: move the spec file or fix the flow's `kind:` declaration.
- Run the suite: `/task-regression`.
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded.
- [ ] Step 2: preflight checks ran in order; abort messages used verbatim where applicable; no sibling-repo / codemap / OpenAPI read.
- [ ] Step 3: every flow parsed; non-known fields passed through to `Additional fields`; `<USER FILL>` rendered verbatim; `evidence` shape handled per the rules.
- [ ] Step 4: every `.spec.ts` scanned by text; `test()` titles + `@`-tags extracted; flake markers matched with the permissive regex; no execution.
- [ ] Step 5: every row classified per the four-status table; kind-mismatch rendered under declared kind with actual on-disk path.
- [ ] Step 6: output written to `--out`; pre-existing file diffed and confirmed unless `--force`; verbatim section headers; sort order applied.
- [ ] Step 7: console summary printed (counts + grouping + output path), document body not duplicated.

## Avoid

- Mutating `flows.yaml`, scenarios, or sibling repos.
- Reading codemap, OpenAPI, or sibling repos.
- Executing any scenario file.
- Silently overwriting `--out` without `--force`.
- Inferring or filling `<USER FILL>` markers.
- Dropping non-known flow fields - they belong in `Additional fields`.
- Embedding run results (pass/fail, durations). The plan is forward-looking intent.
- Asserting redundancy, staleness, or evidence freshness - separate (unshipped) analyses.
