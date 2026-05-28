---
name: eval-spec-coverage
description: Map every acceptance criterion and NFR in spec.md to test/code evidence and emit per-criterion verdicts plus drift signals for eval-scorer.
metadata:
  category: spec
  tags: [spec, sdd, evaluation, coverage, traceability]
user-invocable: false
---

# Eval - Spec Coverage

> Load `Use skill: spec-artifact-paths` first to resolve `spec_path`, `plan_path`, `tasks_path`.

## When to Use

Composed by `task-spec-evaluate` after `eval-test-runner`. Read-only.

Inputs: `spec_path`, `plan_path`, `tasks_path`, `test_run`, `changed_files` (optional; if absent, search is repo-wide and `notes` records the weaker signal).

## Rules

- Every AC and every NFR appears in the output exactly once.
- Evidence is required for any non-`uncovered` AC and any non-`unverified` NFR verdict. Cite test name or `file:line`.
- A failing test linked to an AC by an **explicit** match makes the AC `violated`. A failing **heuristic** match stays `uncovered`.
- Never edit spec/plan/tasks/source.
- Emit `summary.hard_fail_inputs`; `eval-scorer` owns the final `hard_fail` boolean.

## Patterns

### Explicit vs heuristic match

A test is **explicit** for `ACn` iff any of:

- Test name matches regex `(^|[_\W])acn([_\W]|$)`, case-insensitive (so `test_ac1_*` matches AC1; `test_mac10_*` does not match AC1).
- Test docstring or comment contains `Satisfies: ACn`.
- A task in `tasks.md` declares `Satisfies: ACn` and lists a source file that the candidate test imports or exercises.

Everything else (substring overlap with AC text) is **heuristic**. Heuristic matches never upgrade to `violated` on failure.

```yaml
- ref: test_ac1_rejects_8mb_file       # explicit (regex hit on ac1)
  match: explicit
- ref: test_avatar_upload_jpeg          # heuristic (no acN token; substring overlap with AC1 "avatar upload")
  match: heuristic
```

### NFR evidence states

| Method in plan.md | Evidence in test_run | Verdict             |
| ----------------- | -------------------- | ------------------- |
| Declared          | Present + passing    | `verified`          |
| Declared          | Present + failing    | `failed`            |
| Declared          | Absent               | `unverified` ("method declared, evidence not produced") |
| Missing           | Any                  | `unverified` ("plan missing verification method - amend plan.md") |

Never infer `verified` from "no failures".

`partially-verified` only when multiple sub-conditions exist and some have evidence (e.g., security NFR with auth tested but authz untested).

### Drift detection

Tokenize each out-of-scope item: lowercase, split on `\s|-|_`, drop stopwords `{a, an, the, and, or, of, for, to}`. For each token, scan `changed_files` path segments and test names with regex `(^|[_/\W])<token>([_/\W]|$)`. A multi-token item drifts when **all** tokens hit within the same path or test name. Dedupe by `(item, drift_ref)`.

### `covered-by-code-only`

A `changed_files` path contains AC-keyword evidence (function/class name or path segment) for the AC's text (tokenized as in Drift, requiring **two** token hits in one path/symbol) but no test references the AC by explicit or heuristic match.

## AC Verdicts

| Verdict                | Trigger                                                                  |
| ---------------------- | ------------------------------------------------------------------------ |
| `covered`              | Passing test with explicit or heuristic match (heuristic flagged)        |
| `covered-by-code-only` | Code evidence exists, no test evidence                                   |
| `uncovered`            | No evidence, or only a failing heuristic match                           |
| `violated`             | A failing test matches the AC explicitly, or code contradicts AC text    |
| `out-of-scope-drift`   | AC text overlaps the spec's own out-of-scope list (spec self-contradiction; surface as amendment) |

## NFR Verdicts

`verified` / `partially-verified` / `unverified` / `failed` per the table above.

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
      notes: <optional - amendment requests here>
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
  hard_fail_inputs:
    ac_violated: <int>
    nfr_failed: <int>
    drift_count: <int>
    any_out_of_scope_drift_verdict: true | false
```

## Edge Cases

- **Spec lacks AC IDs**: assign `AC1..ACn` in document order; `notes: "AC IDs derived; spec needs amendment"`.
- **Test run timed out or errored**: dependent ACs are `uncovered` (no verdict possible), not `violated`; carry the run error in `notes`.
- **Conflicting evidence for same AC** (pass + fail, both explicit): `violated` - failures win.
- **No `changed_files`**: search is repo-wide; add summary-level note.

## Avoid

- Inferring NFR `verified` from "no failures".
- Upgrading a heuristic-match failure to `violated`.
- Conflating line-coverage with spec-coverage (orthogonal).
- Emitting the final `hard_fail` boolean (eval-scorer owns it).
