---
name: task-spec-plan
description: SDD planning phase - reads spec.md, produces plan.md with architecture, data model, API contract, alternatives, NFR mapping, risks. Speckit-aware.
metadata:
  category: spec
  tags: [spec, sdd, plan, architecture, design]
  type: workflow
user-invocable: true
---

# Spec - Plan

Translates `spec.md` into `plan.md`: architecture, data model, API contract, NFR mapping, alternatives, risks. Stack-aware.

## When to Use

After `task-spec-specify` (and ideally `task-spec-clarify`). Requires `<slug>`. Default: amend existing `plan.md`; pass `--replan` to regenerate.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

If unknown, flag `Stack Type: unknown` and avoid framework-specific file extensions; use placeholders like `<module>/user_model.<ext>`. Do not invent paths.

### STEP 3 - Detect Mode

Use skill: speckit-detect

### STEP 4 - Resolve Paths

Use skill: spec-artifact-paths

If `plan.md` exists, default to **amend**; offer replace/abort. `--replan` forces regenerate even if amend is the default.

### STEP 5 - Read the Spec

Read `spec.md` and (if present) `clarifications.md`. Abort if `spec.md` is missing or any open question is tagged blocker/major (recommend `task-spec-clarify`).

Gaps surface as **Proposed Spec Amendments** in `plan.md` - never edit `spec.md`.

### STEP 6 - Branch on Mode

- **speckit-installed**: apply STEP 7 composition rules as a brief, hand to `/speckit-plan`, post-process with STEP 8 cross-check as suggestions. Skip to STEP 10.
- **standalone**: continue.

### STEP 7 - Compose the Plan

| Section                       | How to populate                                                                                                       |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| **Architecture overview**     | Components, boundaries, data ownership. Stack-aware.                                                                  |
| **Data model**                | Entities, key fields, relationships, indexes. Migration approach if existing schema is touched.                       |
| **API contract**              | Endpoints, request/response shapes, error model. Frontend: component contracts, state shape.                          |
| **NFR mapping**               | `Use skill: nfr-specification`. Every spec NFR maps to a plan element (or explicit waiver). Run the relevant floor formula on quantitative NFRs. |
| **Alternatives considered**   | For each significant decision: 2-3 viable options, chosen with rationale, >=1 rejected option with reason.            |
| **Risks and mitigations**     | Failure modes, rollback strategy, data-loss surfaces. Cross-reference NFRs.                                           |
| **Decisions worth recording** | Candidate ADRs - list each with one-line rationale; ADR authoring is the user's call.                                 |
| **Out of scope (reaffirmed)** | Restate spec's out-of-scope verbatim.                                                                                 |

#### Stack-aware additions (when `stack-detect` succeeds)

- Note framework defaults the plan must override (e.g., Spring Boot `multipart.max-file-size=1MB` default vs. 5MB payload).
- Use the framework's contract idiom (Spring `@RestController`, FastAPI router, NestJS controller). Unknown stack -> generic OpenAPI sketch.
- Data model uses the framework's persistence convention (JPA, Active Record, Prisma).

#### NFR floor formulas

| NFR shape       | Formula                                                                 |
| --------------- | ----------------------------------------------------------------------- |
| Latency         | `payload_bits / bandwidth + storage_round_trip` vs p95/p99 budget       |
| Throughput      | `per_request_cost * target_rps` vs instance capacity                    |
| Storage         | `users * size * retention` vs storage budget                            |

Show the calculation in the NFR table. If floor exceeds budget by `> 2x` or breaks a blocker NFR, stop and recommend `task-spec-clarify`. Smaller gaps -> Proposed Spec Amendment.

Composition rules:
- Stay at contract level. No class names, no SQL syntax.
- Every plan element traces to at least one AC or NFR.
- Fullstack: one plan with labeled backend/frontend sections.
- If `architecture` plugin is installed, soft-suggest `task-design-architecture`. Do not auto-run.

### STEP 8 - Plan-Spec Cross-Check

Pre-flight gate (full consistency is `task-spec-analyze`'s job; do not duplicate its rule set here):
- Every story addressed by an architecture component or API endpoint.
- Every AC has a plan element testable against it.
- No plan element touches out-of-scope.
- No plan element conflicts with another.

For each gap: add the missing element (preferred), stop and ask (if it implies a spec change), or mark as a Proposed Spec Amendment.

### STEP 9 - Write plan.md

Append-only in amend mode (new revision section, never delete prior content).

### STEP 10 - Summarize

Print path, sections populated, alternatives recorded, ADR candidates, mode, proposed amendments, next command (`task-spec-tasks <slug>`).

## Output Format

```markdown
# Plan - <Feature Name>

- **Slug:** <slug>
- **Stack:** <detected stack> (or `unknown`)
- **Created:** <YYYY-MM-DD>
- **Last updated:** <YYYY-MM-DD>

## Summary
<Two or three sentences: what is being built, chosen shape, why.>

## Architecture Overview
<Components, boundaries, data ownership.>

## Data Model
<Entities, fields, relationships, indexes, migrations.>

## API Contract
<Endpoints / interfaces / component contracts. Request/response shapes, error model.>

## NFR Mapping

| NFR Category | Spec Target  | Plan Element              | Floor Calculation              | Verdict       | Verification |
| ------------ | ------------ | ------------------------- | ------------------------------ | ------------- | ------------ |
| Throughput   | 1000 rps     | horizontal autoscale 4 pods | 250 rps/pod * 4 = 1000 rps     | Feasible      | k6 in CI     |
| Latency      | p95 < 200ms  | read-through cache         | 5MB / 10Mbps = 4s              | Infeasible (20x; flagged) | load test |

## Alternatives Considered

### Decision: <title>
- **Context:** <one paragraph>
- **Chosen:** <option>
- **Rejected:** <option> - <why not>
- **Trade-off accepted:** <what is sacrificed>
- **Reversibility:** Easy | Moderate | Hard - <reason>

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation | Rollback |
| ---- | ---------- | ------ | ---------- | -------- |

## Decisions Worth Recording (Candidate ADRs)
- **<title>** - <one-line rationale>

## Out of Scope (Reaffirmed)
<Verbatim from spec.md.>

## Proposed Spec Amendments
<Gaps surfaced during planning. Empty if none.>

## Revisions
- <YYYY-MM-DD>: <change> (by `task-spec-plan` | manual)
```

## Self-Check

- [ ] STEP 1-4: behavioral-principles, stack-detect, speckit-detect, paths loaded; `Stack Type: unknown` flagged if undetermined
- [ ] STEP 5: aborted on missing `spec.md` or unresolved blockers
- [ ] STEP 6: mode branch followed
- [ ] STEP 7: plan composed per table; floor formula run on quantitative NFRs; `>2x` infeasibility routed to clarify
- [ ] STEP 8: cross-check (stories, ACs, out-of-scope, no internal conflicts)
- [ ] STEP 9: `plan.md` written; `spec.md` not edited
- [ ] STEP 10: summary lists sections, alternatives, ADR candidates, mode, amendments, next command

## Avoid

- Writing code, class skeletons, or SQL syntax.
- Inventing requirements - propose amendments instead.
- Skipping Alternatives Considered because "the choice was obvious".
- Overwriting `plan.md` without offering replace/amend/abort.
- Auto-running `task-design-architecture`.
- Silently absorbing an arithmetically infeasible NFR.
