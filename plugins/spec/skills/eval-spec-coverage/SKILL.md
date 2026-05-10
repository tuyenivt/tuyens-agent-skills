---
name: eval-spec-coverage
description: Map every AC and NFR in spec.md to satisfying tests / code regions; emits per-criterion verdicts (covered / uncovered / violated) plus NFR status.
metadata:
  category: spec
  tags: [spec, sdd, evaluation, coverage, traceability]
user-invocable: false
---

> Load `Use skill: spec-artifact-paths` first to resolve the feature's spec, plan, and tasks paths.

# Eval - Spec Coverage

> Composed by `task-spec-evaluate` after `eval-test-runner`. The bridge between the spec (what should be true) and the test/code reality (what is true). Read-only. Not for code-coverage measurement, test generation, or requirements review.

## Rules

- Every AC and every NFR appears in the output exactly once.
- Coverage is evidence-based: each `covered` cites a test name or file:line. No evidence -> `uncovered`.
- A failing test for an AC is `violated` (stronger than `uncovered`); the scorer treats it as a hard fail.
- Out-of-scope drift is reported as a separate signal even if no AC is affected.
- Never modify spec/plan/tasks/source - surface gaps as proposed amendments.

## Inputs

`spec_path`, `plan_path`, `tasks_path` (from `spec-artifact-paths`); `test_run` (from `eval-test-runner`); `changed_files` (optional - if absent, evidence search is repo-wide and signal is weaker).

## Procedure

1. **Extract** ACs (with IDs) and NFRs from `spec.md`; NFR verification methods from `plan.md`; `Satisfies:` markers from `tasks.md`. Also extract the out-of-scope list.
2. **Per-AC verdict.** Match tests by explicit `Satisfies: ACx` (preferred) or text-keyword heuristic (flag `match: heuristic`). Failing tests beat passing ones. If text appears in out-of-scope -> `out-of-scope-drift`.
3. **Per-NFR verdict** using the verification method declared in `plan.md`. Absence of evidence is `unverified`, not `verified`.
4. **Drift scan.** Independently scan `changed_files` and test names for out-of-scope keywords; record any match.

## AC Verdicts

| Verdict                | Meaning                                                                              |
| ---------------------- | ------------------------------------------------------------------------------------ |
| `covered`              | Passing test cites the AC (explicit `Satisfies: ACx` or text match)                  |
| `covered-by-code-only` | Code implements it but no test verifies                                              |
| `uncovered`            | No evidence, or evidence too weak to confirm                                         |
| `violated`             | A test for the AC failed, or test/code explicitly contradicts AC text                |
| `out-of-scope-drift`   | AC keywords appear in spec's out-of-scope list (internal spec contradiction)         |

## NFR Verdicts

`verified` / `partially-verified` / `unverified` / `failed`. Acceptable evidence by category:

| Category                 | Acceptable evidence                                                                |
| ------------------------ | ---------------------------------------------------------------------------------- |
| Latency / throughput     | Load test, benchmark, or explicit "deferred to integration env"                    |
| Security                 | Test for auth/authz path, security scan, referenced threat-model ADR               |
| Accessibility            | Axe/a11y test, or manual audit checklist in `evaluation.md`                        |
| Reliability / resiliency | Retry/timeout test, chaos test, fault-injection note                               |
| Observability            | Test asserting log/metric/trace emission, or "manually verified" note              |

## Output Format

```yaml
spec_coverage:
  spec_path: <relative path>
  acceptance_criteria:
    - id: AC1
      text: <one-line summary>
      verdict: covered | covered-by-code-only | uncovered | violated | out-of-scope-drift
      evidence:
        - kind: test | code | none
          ref: <test name or file:line>
          match: explicit | heuristic
      notes: <optional>
  nfrs:
    - category: latency
      threshold: <as written in spec>
      verification_method: <from plan.md>
      verdict: verified | partially-verified | unverified | failed
      evidence: [{ kind: test | benchmark | manual-note | reference, ref: <...> }]
      notes: <optional>
  out_of_scope_drift:
    - item: <out-of-scope item>
      drift_ref: <file or test name>
      severity: blocker
  summary:
    ac_total, ac_covered, ac_uncovered, ac_violated, ac_drift   # ac_covered = covered + covered-by-code-only
    nfr_total, nfr_verified, nfr_unverified, nfr_failed         # nfr_verified = verified + partially-verified
    drift_count
```

## Edge Cases

- **Spec ACs lack IDs**: derive ordinal `AC1..ACn`, add `notes: "AC IDs derived; spec needs amendment"`.
- **Plan missing NFR verification method**: NFR verdict `unverified` with note; surface as proposed amendment, not coverage failure.
- **Test run timeout/error**: dependent ACs become `uncovered` (NOT `violated`) with the run note - we have no verdict.
- **Conflicting test evidence** (one pass + one fail referencing same AC): verdict is `violated`; failures are stronger.
- **No `changed_files` passed**: evidence search is repo-wide; add `notes` so the scorer knows pre-existing tests may be in scope.

## Avoid

- `covered` from a heuristic name match without flagging `match: heuristic`.
- Inferring NFR `verified` from "no failures" - that is `unverified`.
- Editing artifacts to fix missing IDs/methods.
- Conflating line-coverage with spec-coverage (orthogonal concepts).
- Treating drift as a soft warning - it is a blocker.
