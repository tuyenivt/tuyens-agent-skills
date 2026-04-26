---
name: eval-spec-coverage
description: Map every acceptance criterion and NFR in `spec.md` to the tests / code regions that satisfy it. Emits per-criterion verdicts (covered / uncovered / violated) plus per-NFR verification status. Composed by `task-spec-evaluate` and consumed by `eval-scorer`.
metadata:
  category: spec
  tags: [spec, sdd, evaluation, coverage, traceability]
user-invocable: false
---

> Load `Use skill: spec-artifact-paths` first to resolve the feature's spec, plan, and tasks paths.

# Eval - Spec Coverage

> This atomic is composed by `task-spec-evaluate` - do not invoke directly. It produces the spec-side of the evaluation: which acceptance criteria and NFRs are demonstrably satisfied by the produced code/tests, which are not, and which are violated.

## When to Use

- Inside `task-spec-evaluate` after `eval-test-runner` has produced a test result
- When the user asks "does this implementation satisfy the spec?"
- When orchestration needs a spec-coverage signal to gate the fix loop (after #18)

**Not for:** Code-coverage measurement (use `eval-test-runner`'s coverage field), generating new tests (use `task-code-test`), reviewing requirements quality (use `spec-review`).

## Rules

- Every acceptance criterion in `spec.md` MUST appear in the output exactly once
- Every NFR MUST appear in the output exactly once with its verification status
- Coverage is determined by **evidence**, not assertion - each `covered` verdict cites a test name (from `eval-test-runner` output) or a code region (file:line)
- An AC with no traceable test and no code evidence is `uncovered`, never silently `covered`
- A test that explicitly contradicts an AC (e.g., test asserts behavior the AC excludes) marks the AC `violated` - this is stronger than `uncovered` and should block scoring
- Out-of-scope items in `spec.md` are checked too: if any test or code reference touches an out-of-scope item, it is reported as `out-of-scope-drift` (a separate signal from AC coverage)
- The atomic does not modify spec.md, plan.md, tasks.md, or any source code - it is read-only

## Inputs

| Input           | Source                                                                                                                                         |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `spec_path`     | From `spec-artifact-paths` for the current slug                                                                                                |
| `plan_path`     | From `spec-artifact-paths` (used to locate NFR verification methods)                                                                           |
| `tasks_path`    | From `spec-artifact-paths` (cross-reference task `Satisfies:` markers)                                                                         |
| `test_run`      | Output object from `eval-test-runner`                                                                                                          |
| `changed_files` | Optional list of files modified during orchestration (from dev/test handoff `outputs`) - if provided, restricts evidence search to these paths |

## Mapping Procedure

### Step 1 - Extract criteria and NFRs

From `spec.md`:

- Acceptance criteria with stable IDs (e.g., `AC1`, `AC2`, ...). If IDs are missing, derive from order; flag as `notes` so the spec gets amended later.
- NFRs by category (latency, security, accessibility, throughput, etc.) with their measurable thresholds.
- Out-of-scope list.

From `plan.md`:

- NFR verification methods (load test? security scan? a11y audit?). The plan is the source of truth for "how this NFR is verified."

From `tasks.md`:

- Task `Satisfies:` fields - reverse map to find which tasks claimed each AC/NFR.

### Step 2 - Per-AC verdict

For each AC:

1. **Test evidence:** scan `test_run.failures` and (if available) the per-test list for any test whose name references the AC ID (`AC1`, `Satisfies AC1`, `should X when Y` matching the AC's behavior). Match by:
   - Explicit `Satisfies: ACx` in test name (preferred convention; emitted by `task-code-test` in spec-aware mode)
   - Deterministic match on AC text keywords (lower confidence; flag as `match: heuristic`)
2. **Code evidence:** if no test ties to the AC but a code region under `changed_files` plausibly implements it, mark as `covered-by-code-only` (a weaker form of covered - flagged because it has no test).
3. **Violation check:** if a test is named for the AC but is in `test_run.failures`, the AC is `violated` (the spec says X; the implementation does not deliver X).
4. **Out-of-scope drift:** if the AC's keywords appear in `spec.md`'s out-of-scope list, flag as `out-of-scope-drift` instead of `covered`.

Verdicts:

| Verdict                | Meaning                                                                              |
| ---------------------- | ------------------------------------------------------------------------------------ |
| `covered`              | At least one passing test cites the AC (preferred) or AC text directly               |
| `covered-by-code-only` | Code implements it but no test verifies it - the AC is partially satisfied           |
| `uncovered`            | No test, no code evidence, or evidence too weak to confirm                           |
| `violated`             | A test named for the AC failed, OR test/code explicitly contradicts AC text          |
| `out-of-scope-drift`   | The AC keywords appear in the spec's out-of-scope list (spec internal contradiction) |

### Step 3 - Per-NFR verification

For each NFR, the plan should specify a verification method. Map:

| NFR category             | Acceptable evidence                                                                |
| ------------------------ | ---------------------------------------------------------------------------------- |
| Latency / throughput     | Load test result, benchmark file, or explicit "deferred to integration env" note   |
| Security                 | Test for the auth/authz path, security scan output, or referenced threat-model ADR |
| Accessibility            | Axe / a11y test result, or manual audit checklist in `evaluation.md`               |
| Reliability / resiliency | Retry/timeout test, chaos test, or fault-injection note                            |
| Observability            | Test asserting log/metric/trace emission, or a "manually verified" note            |

NFR verdicts: `verified` / `partially-verified` / `unverified` / `failed`. `unverified` is the default when no evidence is found; do not assume `verified`.

### Step 4 - Out-of-scope drift detection

Independently of AC coverage: scan `changed_files` and test names for keywords from the spec's out-of-scope list. Any match is reported under `out_of_scope_drift` with the offending file/test. Drift is a hard signal - the scorer should treat it as a blocker.

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
    - id: AC2
      ...
  nfrs:
    - category: latency
      threshold: <as written in spec>
      verification_method: <from plan.md>
      verdict: verified | partially-verified | unverified | failed
      evidence:
        - kind: test | benchmark | manual-note | reference
          ref: <test name or path>
      notes: <optional>
  out_of_scope_drift:
    - item: <out-of-scope item from spec>
      drift_ref: <file or test name that touched it>
      severity: blocker
  summary:
    ac_total: <int>
    ac_covered: <int>           # covered + covered-by-code-only
    ac_uncovered: <int>
    ac_violated: <int>
    ac_drift: <int>
    nfr_total: <int>
    nfr_verified: <int>         # verified + partially-verified
    nfr_unverified: <int>
    nfr_failed: <int>
    drift_count: <int>
```

## Handling Edge Cases

- **`spec.md` missing AC IDs:** derive ordinal IDs (`AC1..ACn`) and emit `notes: "AC IDs derived; spec needs amendment"` per AC. Do not abort.
- **Plan does not specify NFR verification method:** verdict defaults to `unverified` with `notes: "verification method not specified in plan.md"`. Surface as a proposed plan amendment, not a coverage failure.
- **Test run timed out (`status: timeout` from `eval-test-runner`):** all AC verdicts that depended on tests become `uncovered` with `notes: "test run did not complete"`. Do not mark them `violated` - we do not have a verdict.
- **Test run errored (`status: error`):** same as timeout - cannot conclude `violated`; mark `uncovered` with the error note.
- **Conflicting evidence:** an AC with one passing test AND one failing test referencing it -> verdict is `violated`. Failing tests are stronger than passing ones; the spec is not satisfied if any verification fails.
- **No `changed_files` provided:** scan the entire repo for evidence. Flag `notes: "evidence search was repo-wide; results may include pre-existing tests"` so the scorer knows the signal is weaker.

## Avoid

- Marking an AC `covered` based on a heuristic name match without flagging `match: heuristic` - downgrades the scorer's confidence
- Inferring NFR verification from absence of failures (e.g., "no latency test failed -> latency verified") - absence of evidence is `unverified`, not `verified`
- Modifying `spec.md`/`plan.md`/`tasks.md` to "fix" missing IDs or verification methods - surface as proposed amendments, never edit
- Conflating code coverage (lines hit) with spec coverage (criteria satisfied) - they are orthogonal
- Treating `out-of-scope-drift` as a soft warning - it is a blocker; the implementation went beyond the spec's boundaries

## Notes

- This atomic is the bridge between the spec (what should be true) and the test/code reality (what is true). It is **the** signal for whether orchestration produced what the spec asked for.
- Pairs with `eval-test-runner` (raw test outcome) and feeds `eval-scorer` (aggregated score). The scorer never re-derives coverage; it only consumes this atomic's verdict counts.
- The `match: explicit` vs `match: heuristic` distinction matters: in spec-aware mode, `task-code-test` should produce tests with `Satisfies: ACx` in their names. Coverage that relies on heuristics tells the user their tests are not yet spec-traced.
