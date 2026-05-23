---
name: eval-spec-coverage
description: Map every acceptance criterion and NFR in spec.md to test/code evidence and emit per-criterion verdicts plus drift signals for eval-scorer.
metadata:
  category: spec
  tags: [spec, sdd, evaluation, coverage, traceability]
user-invocable: false
---

> Load `Use skill: spec-artifact-paths` first to resolve the feature's spec, plan, and tasks paths.

# Eval - Spec Coverage

## When to Use

Composed by `task-spec-evaluate` after `eval-test-runner` to bridge spec (what should be true) and test/code reality (what is true). Read-only. Not for code-coverage measurement, test generation, or requirements review.

Inputs: `spec_path`, `plan_path`, `tasks_path`, `test_run` (eval-test-runner output), `changed_files` (optional; if absent, search is repo-wide and `notes` records the weaker signal).

## Rules

- Every AC and every NFR appears in the output exactly once.
- Evidence is required for any non-`uncovered` AC verdict and any non-`unverified` NFR verdict. Cite test name or `file:line`.
- A failing test linked to an AC by an explicit match makes the AC `violated`. A failing weak/heuristic match is `uncovered`, not `violated`.
- Never edit spec/plan/tasks/source. Missing IDs or verification methods become amendment notes, not coverage failures.

## Patterns

### Explicit vs heuristic match (deterministic)

A test is an **explicit** match for `ACn` when any of:

- Test docstring or comment contains `Satisfies: ACn`.
- Test name contains the token `acn` (case-insensitive, word-boundary or `_` boundary).
- A task in `tasks.md` declares `Satisfies: ACn` and the task's referenced file matches the test's file path.

Everything else (substring overlap with AC text, semantic similarity) is **heuristic**. Heuristic matches set `match: heuristic` and never upgrade to `violated` on failure.

```yaml
# Good - explicit
- ref: test_ac1_rejects_8mb_file
  match: explicit
# Heuristic - AC1 mentions "avatar upload"; name overlaps but no acN token
- ref: test_avatar_upload_jpeg
  match: heuristic
```

### NFR evidence states

| Method in plan.md | Evidence in test_run | Verdict             |
| ----------------- | -------------------- | ------------------- |
| Declared          | Present + passing    | `verified`          |
| Declared          | Present + failing    | `failed`            |
| Declared          | Absent               | `unverified` (note: "method declared, evidence not produced") |
| Missing           | Any                  | `unverified` (note: "plan missing verification method - amend plan.md") |

Never infer `verified` from "no failures."

### Drift detection

Scan `changed_files` paths and test names for tokens derived from each out-of-scope item (split on whitespace and `-`, lowercase, drop stopwords; match word/path-segment boundaries). Dedupe entries by `(out-of-scope item, drift_ref)`. Drift is always a blocker; absent `severity` flexibility, omit the field.

### `covered-by-code-only`

Emit when a `changed_files` path contains AC-keyword evidence (function/class name or file path) but no test references the AC by explicit or heuristic match.

## AC Verdicts

| Verdict                | Trigger                                                                  |
| ---------------------- | ------------------------------------------------------------------------ |
| `covered`              | Passing test with explicit or heuristic match (heuristic flagged)        |
| `covered-by-code-only` | Code evidence exists, no test evidence                                   |
| `uncovered`            | No evidence, or only a failing heuristic match                           |
| `violated`             | A failing test matches the AC explicitly, or code contradicts AC text    |
| `out-of-scope-drift`   | AC text overlaps with the spec's own out-of-scope list (spec self-contradiction; surface as amendment) |

## NFR Verdicts

`verified` / `partially-verified` / `unverified` / `failed`. Use the table under `Patterns > NFR evidence states`. `partially-verified` only when multiple sub-conditions exist and some have evidence (e.g., security NFR with auth tested but authz untested).

## Output Format

```yaml
spec_coverage:
  spec_path: <relative path>
  acceptance_criteria:
    - id: AC1                          # derived ordinal if spec lacked IDs
      text: <one-line summary>
      verdict: covered | covered-by-code-only | uncovered | violated | out-of-scope-drift
      evidence:
        - kind: test | code | none
          ref: <test name or file:line>
          match: explicit | heuristic
      notes: <optional - amendment requests live here>
  nfrs:
    - category: <e.g., latency | security | observability>
      threshold: <as written in spec>
      verification_method: <from plan.md, or null>
      verdict: verified | partially-verified | unverified | failed
      evidence:
        - kind: test | benchmark | manual-note | reference
          ref: <...>
      notes: <optional>
  out_of_scope_drift:
    - item: <out-of-scope item>
      drift_ref: <file or test name>
  summary:
    ac_total, ac_covered, ac_uncovered, ac_violated, ac_drift   # ac_covered counts both covered and covered-by-code-only
    nfr_total, nfr_verified, nfr_unverified, nfr_failed         # nfr_verified counts both verified and partially-verified
    drift_count
  hard_fail: <true | false>
  hard_fail_reasons:                   # empty when hard_fail is false
    - <"ac_violated" | "nfr_failed" | "out_of_scope_drift" | "spec_self_contradiction">
```

`hard_fail` is true whenever `ac_violated > 0`, `nfr_failed > 0`, `drift_count > 0`, or any AC has verdict `out-of-scope-drift`. `eval-scorer` reads this directly - do not require it to recompute the rule.

## Edge Cases

- **Spec lacks AC IDs**: assign `AC1..ACn` in document order; add `notes: "AC IDs derived; spec needs amendment"`.
- **Test run timed out or errored**: dependent ACs are `uncovered` (no verdict possible), not `violated`; carry the run error in `notes`.
- **Conflicting evidence for same AC** (pass + fail, both explicit): `violated` - failures win when both sides are explicit.
- **No `changed_files`**: search is repo-wide; add summary-level note that pre-existing tests may be in scope.

## Avoid

- Inferring NFR `verified` from "no failures."
- Upgrading a heuristic-match failure to `violated`.
- Conflating line-coverage with spec-coverage (orthogonal).
- Emitting drift as a warning - it is always a blocker and always sets `hard_fail`.
