---
name: task-breakdown-design
description: Break a system design (HLD/LLD) into an implementable task graph - phases, dependency order, critical path, sizing, scope flags - or review a breakdown someone else authored.
agent: architecture-planner
metadata:
  category: planning
  tags: [planning, task-breakdown, system-design, hld, lld, critical-path, review]
  type: workflow
user-invocable: true
---

# Design-to-Tasks Breakdown

Turn an approved system design (HLD and/or LLD) into an engineering task graph - or review a breakdown someone else authored against the design it claims to implement. One workflow, two modes. Audience: the architect or tech lead who owns the design and is planning the build.

Consumes a design doc as primary input - ideally the output of `task-design-architecture` (Sections 1-12), but any HLD/LLD works. In Breakdown Mode it produces a task plan; in Review Mode it produces severity-tagged findings and a verdict. Never implementation code or a design doc.

## When to Use

- **Breakdown:** an architecture design is signed off and needs to become buildable tasks; turning an HLD/LLD into a dependency-ordered plan before committing a timeline; surfacing hidden complexity (migrations, backward compat, rollback, observability) the design implies but did not task out.
- **Review:** a colleague's task plan needs sign-off before the team commits; checking a breakdown against the design it claims to implement; sanity-checking dependency order, critical path, and sizing before a timeline is set.

## Mode Detection

A pasted task breakdown (phased tasks, dependencies, sizes) with no authoring request is **Review Mode** even without a verb. A design doc, HLD/LLD, or rough scope handed in for planning is **Breakdown Mode**. If the input contains both a design and a plan built from it, default to Review (the plan is the artifact under review; the design is the ground truth). When genuinely ambiguous, ask. Default: Breakdown.

## Inputs

**Breakdown Mode.** Required: a system design - HLD, LLD, or both. A `task-design-architecture` proposal is the ideal shape but not required. Optional: constraints, exclusions, owning teams, capacity.

When input is a thin sketch rather than a real design, say so, list the design sections that would sharpen the plan, and break down on stated assumptions rather than inventing architecture. Do not design the system here - if a load-bearing decision is absent (sync vs. async, storage choice), raise it as an Open Question or spike, never resolve it silently.

**Review Mode.**

| Input | Required | Notes |
| --- | --- | --- |
| Task breakdown | Yes | The plan under review - phases, tasks, dependencies, sizes |
| Source design | No | The HLD/LLD the plan implements. When present, coverage is checked against it; when absent, coverage is judged against the plan's own stated scope, and the missing design is noted in Review Context |
| Constraints | No | Capacity, deadlines, team boundaries that bound feasibility |

Review the plan as written, not the plan you would have authored. Facts you know that the plan omits (a hidden consumer, a compliance deadline) enter as reviewer assumptions in Review Context and may ground findings - cite them as "reviewer context". When neither a design nor a stated scope is present, say so and review only internal soundness (dependencies, sizing, structure).

When the prompt names a stack and `stack-detect` returns `unknown`, trust the prompt and record the assumption.

## Setup (both modes)

Use skill: `behavioral-principles`.
Use skill: `stack-detect`. Stack output picks which deep-dive atomics fire and names stack-specific tooling (test frameworks, migration tools); in Review Mode it also grounds sizing sanity and the stack-specific tasks a complete plan should contain. If unknown, proceed stack-agnostic.

---

## Breakdown Mode

### STEP 1 - Map the Design to Work

Read the design and extract the work it implies. Match the design's content to the rows below by topic - the bold label is the key; the trailing S-numbers are `task-design-architecture` section hints, present only when the input follows that template. For a free-form HLD/LLD, ignore the S-numbers and map by heading or topic.

| Design content | Produces |
| --- | --- |
| **Module Boundaries / Components** (S2, S3) | Foundation tasks - one per new/changed module or data owner |
| **Data and Consistency Model** (S4) | Foundation + data tasks; schema, migration, backfill |
| **API Contracts** (S11) | Build + Integration tasks per endpoint group; contract tests |
| **Communication Model** (S3) | Integration tasks - events, queues, sync calls between components |
| **Failure and Risk Analysis** (S5) | Ops-Readiness tasks - circuit breakers, retries, idempotency |
| **Observability Plan** (S6) | Ops-Readiness tasks - metrics, traces, alerts, SLO wiring |
| **Deployment Strategy** (S8) | Ops-Readiness tasks - rollout mechanism, migration order, rollback drill, flag config |
| **Guardrails** (S10) | Validation tasks - lint/arch-test rules that enforce each guardrail |
| **Trade-Off / Significant Decisions** (S9) | Spikes where a decision is deferred or an ADR is still open |

State which design sections you drew from. If a required design section is absent (e.g., no failure analysis for a high-blast-radius change), flag it under Open Questions rather than fabricating tasks.

### STEP 2 - Hidden Complexity Scan

The design names components; this scan names the risks inside building them. Walk the checklist, state which signals apply with one-line evidence citing the design (a section, a heading, or a quoted phrase). The trailing S-references below are `task-design-architecture` hints; on a free-form doc cite the heading instead. Skipping the scan is the most common failure of this workflow.

| Signal | Look for in the design |
| --- | --- |
| Database changes | New table/column/index; zero-downtime required; backfill (S4) |
| Data store migration | Moving data between stores (Memcached->Redis, Postgres->DynamoDB) |
| API or protocol contract change | New/changed endpoints, field changes, auth-token format (S11) |
| Auth / permissions | New roles, scopes, token formats, key rotation - or a sensitive surface (money, bulk PII, admin action) with authz conspicuously *unstated* (S2, S11) |
| PII / compliance | Bulk export or new exposure of personal data, audit-logging, data-subject-access, retention (a data-export or reporting design implies this even when it never says so) |
| Async / events | New queues, topics, consumers; idempotency requirements (S3) |
| State machine | Lifecycle states + transition rules |
| Domain calculations | Billing, tax, shipping, refunds, prorations |
| Backward compatibility | Old and new behavior coexist during rollout (S8, S11) |
| Rollback | Can it be reverted? What data would be inconsistent? (S8) |
| Feature flag | Design calls for gradual rollout or kill switch (S8) |
| Observability | New flows need logs, metrics, traces (S6) |
| Test surface | Contract, integration, load, webhook replay |
| Deploy coordination | Cross-service or cross-team ordering; consumer SDK distribution (S8) |
| Third-party integration | External APIs, webhooks, SDKs |

A signal is **material** (load the deep-dive) when it will produce at least one L+ task or a Scope and Risk Flags entry. Otherwise note it and move on. Summarize non-applicable signals in one line ("Checked, not applicable: ...").

Deep-dive mapping (load only when material):

- DB schema or data changes -> `Use skill: backend-db-migration` (data-store moves without relational schema work do not route here)
- Schema, API, or protocol contract *change* -> `Use skill: ops-backward-compatibility`. A *net-new* published contract (a new event, endpoint, or export) has no old behavior to stay compatible with; its risk is provider-first ordering (the consumer must be ready before the producer emits) -> route it to `dependency-impact-analysis` instead
- Cross-service / cross-team dependencies -> `Use skill: dependency-impact-analysis`
- Flag-gated rollout -> `Use skill: ops-feature-flags`
- Any L/XL task touching shared state, auth, money, or cross-service contracts -> run `Use skill: review-blast-radius` and `Use skill: review-change-risk` on the single riskiest such task

Deep-dives inform task descriptions, sizes, and flag rationales - cite verdicts inline in the relevant flag (e.g. "blast radius Critical, Wide with flag"); do not paste their output blocks into the artifact.

### STEP 3 - Generate Tasks

Group by phase; include only phases that apply:

- **Foundation** - data model, contracts, infra that other work depends on
- **Build** - primary component logic from the design
- **Integration** - wiring components to each other, events, external services
- **Validation** - tests, contract checks, load tests, guardrail enforcement, QA
- **Ops Readiness** - observability, runbooks, flag config, rollback drill

Each task:

- **Name** - action-oriented ("Implement dual-mode /auth/validate"). Never "Backend work" or "Testing".
- **Type** - one of: `implementation`, `infrastructure`, `data`, `validation`, `ops`, `analysis` (specs, contracts, audits, decision records)
- **Description** - one or two sentences; what to build, not how
- **Traces to** - the design section, heading, or component this task implements (e.g., "S3 NotificationRouter", or a free-form heading like "Approach: WebSocket gateway"). An ops-readiness task may trace to an implied need the design carries rather than states (e.g., observability or rollback for a flagged rollout) - that is not scope creep. A task tracing to nothing in the design is scope creep - move it to Scope and Risk Flags.
- **Depends on** - task name(s), external (<team/system>), or none
- **Size** - S (<1d) / M (1-2d) / L (3-5d focused engineering days) / XL (>5d - keep in the backlog with a `split` note naming the cohorts/waves it breaks into). Size measures engineering effort; fixed elapsed time (soak windows, parallel runs) goes in the description, not the size.
- **Complexity signals** - required for L or XL; cite which Step 2 signals justify the size
- **Tag** - optional, only `nice-to-have` or `risk-reduction`

When a size hinges on a design decision the doc left open (sync vs. async), state the assumption in the description and the alternative under Open Questions, raise a spike, or both when the decision is load-bearing - break down the assumed path so the plan is usable, and spike the decision so it is not mistaken for settled. Do not pick for the architect.

### STEP 4 - Dependency Order and Critical Path

Number tasks with blocking relationships:

```
1. Define JWT spec (no deps)
2. JWKS endpoint infra (requires: 1)
3. Dual-mode /auth/validate (requires: 1)
4. Consumer SDK rollout - 30 services (requires: 2, 3)
```

**Critical path** = longest chain by hop count of dependent tasks (do not sum sizes; external dependencies are not hops). If chains tie on hops, pick the one carrying more external coordination or larger sizes. Name the chain in arrow form and add one sentence on *why* it pins delivery (size, externality, cross-team sequencing).

When tasks depend on other teams or external systems, name the owning team in `Depends on` so the critical path surfaces team-coordination risk. Another team's deliverable is an `external (<team>)` dependency, not a task - create tasks only for work your team executes. Spikes are numbered in the Dependency Order when other tasks depend on their outcome, but stay in the Spikes section and do not count toward the task count.

### STEP 5 - Scope and Risk Flags

Surface plan-level flags, each with a verdict: `proceed`, `de-scope`, `add spike`, `split epic`.

- **Design gaps:** load-bearing decisions the design left open; required sections absent for the blast radius (e.g., no rollback plan for a Wide change)
- **Scope creep:** work the plan needs that the design did not call for; tasks with no design trace
- **Hidden risks:** L/XL tasks on the critical path; data tasks with rollback complexity; integration blocked on external teams; tasks with unclear complexity (needs a spike); domain-calculation tasks (billing, tax, shipping)
- **XL tasks** stay in the backlog with `split` notes; promote to `split epic` only when the XL spans cohorts/waves that warrant their own planning

When the verdict is `add spike`, define:
- **Question:** specific unknown
- **Done condition:** what the spike must produce
- **Time-box:** maximum duration before it concludes with a finding

### Breakdown Output Format

```markdown
# Design-to-Tasks Breakdown: <Feature / System>

**Stack:** <detected | prompt-stated: <stack> | unknown> | **Design source:** <task-design-architecture proposal | HLD | LLD | sketch> | **Tasks:** <count>

## Design Coverage

- Sections/areas drawn from: <list, e.g., S2 boundaries, S4 data model, S11 API>
- Sections absent or thin: <list; each surfaces below as a Design gap or Open Question>

## Complexity Signals

- **<signal>:** <one-line evidence citing the design>
- **Checked, not applicable:** <non-material signals in one line>

## Tasks

### Foundation

#### <Task name>
- **Type:** implementation | infrastructure | data | validation | ops | analysis
- **Description:** what to build
- **Traces to:** <design section / component>
- **Depends on:** task(s), external (<team/system>), or none
- **Size:** S / M / L / XL
- **Complexity signals:** <Step-2 signals; required for L/XL>
- **Tag:** nice-to-have | risk-reduction (omit otherwise)

[repeat per task; omit phases with no tasks]

## Dependency Order

[numbered list with `requires:` clauses]

**Critical path:** Task A -> Task C -> Task E - <why this chain pins delivery>

## Scope and Risk Flags

- **<flag>:** <proceed | de-scope | add spike | split epic> - <one-line rationale>

## Spikes

- **Question:** <unknown>
  **Done:** <output>
  **Time-box:** <duration>

## Assumptions and Open Questions

- <assumption made due to missing design detail>
- <design decision left open that would change the breakdown>
```

Omit empty sections (Spikes, Scope and Risk Flags, Assumptions).

### Breakdown Self-Check

- [ ] **Setup:** behavioral-principles + stack-detect loaded; prompt-stated stack honored when detect is unknown
- [ ] **Map:** design sections drawn-from and absent listed; every task traces to a design section/component; no architecture invented
- [ ] **Scan:** every applicable signal listed with design-citing evidence; material deep-dive atomics loaded
- [ ] **Tasks:** each has Name, Type (from enum), Description, Traces-to, Depends-on, Size; L/XL cite complexity signals; XL has a `split` note; team/system named when external
- [ ] **Dependencies:** critical path named by hop count with a "why" sentence; Ops Readiness includes observability/rollback when the design implies them
- [ ] **Flags:** each flag carries a verdict; design gaps surfaced; spikes have Question + Done + Time-box
- [ ] **Assumptions and Open Questions** populated when the design left decisions open

---

## Review Mode

Critique a breakdown as written; do not rewrite it. Produce severity-tagged findings and a verdict, grounded in the source design when one is supplied.

### STEP 1 - Intake

State in one sentence each: what the plan builds, its stated scope/exclusions, the source design (or "none supplied"), and the plan's task count and critical path as the author states them.

### STEP 2 - Coverage Audit

Does the plan cover the work the design (or stated scope) implies? For each area, mark **Covered** (a task implements it), **Under-specified** (named but no real task), or **Missing** (no task). When a source design is supplied, walk it against the areas below - by section when it is a `task-design-architecture` proposal, by heading or topic when it is a free-form HLD/LLD or a prose excerpt. When no design is supplied, replace the rows with each in-scope item the stated scope names plus the ops areas it implies (an export needs failure/retry + alerting; a write path needs rollback), and mark `n/a` any area the scope does not reach - `n/a` is not Missing.

| Area | A complete plan has |
| --- | --- |
| Module boundaries / components | A Foundation/Build task per new or changed component |
| Data and consistency model | Schema, migration, and backfill tasks; rollback data handling |
| API contracts | Endpoint implementation + contract-test tasks |
| Security / PII | Authz tasks on sensitive surfaces (money, bulk PII, admin); audit-logging, retention, data-subject-access tasks when the design exposes personal data |
| Communication / events | Integration tasks for each cross-component call, queue, consumer |
| Failure and risk analysis | Ops-readiness tasks for the design's mitigations (breakers, retries, idempotency) |
| Observability | Metrics/traces/alerts/SLO tasks |
| Deployment and rollback | Rollout, migration-order, rollback-drill, flag-config tasks |
| Guardrails | Validation tasks that enforce each guardrail |

The most common defect is a plan that tasks out the happy-path build and omits migration, backward-compat, rollback, and observability the design calls for. Severity of a Missing item:

- **Blocker** - a high-blast-radius area is untasked: rollback or migration on a Wide change, **or any money/data-integrity mitigation the design calls for** (idempotency on a money path, dedup, backfill of a required column).
- **Major** (minimum) - any other Missing area the design or stated scope implies.
- **Minor** (minimum) - Under-specified; **Major** if it forces guesswork on a load-bearing task.
- Not a finding - scope silence on an area the plan's purpose does not touch (mark it `n/a`, not Missing).

Treat a change as Wide/Critical - and its Missing rollback/migration/idempotency gap as a Blocker - when it touches a core data model, money movement, or an externally consumed contract (public API, published events, partner export). That trigger is self-sufficient: tag the Blocker from it directly. Load `Use skill: review-blast-radius` only to settle a borderline level (read its Code/Data/User scope against the design, not a codebase) when the call is not obvious.

### STEP 3 - Structural Soundness

Check the plan's internal mechanics. Record each as a finding with severity.

- **Dependency graph:** every task states dependencies; no cycles; no task depends on work sequenced after it; another team's deliverable is `external`, not a task the plan owns
- **Critical path:** correctly identified (longest chain by hop count, not summed sizes; externals are not hops); the named chain matches the dependency graph
- **Sizing:** L/XL tasks justify their size; XL tasks carry a `split` note and are not silently dropped; sizes are engineering effort, not calendar time. When the coverage gaps invalidate the author's own task-count or timeline claim, fold that into the driving coverage findings - do not raise it as a separate scored finding.
- **Scope creep:** tasks with no design trace and not in stated scope; must-have framing on work that was never agreed
- **Phasing:** foundation work precedes the build that needs it; ops-readiness is not deferred past the risky launch

When a contract/migration/flag gap drives a finding, cite the relevant atomic's verdict inline (`ops-backward-compatibility`, `backend-db-migration`, `ops-feature-flags`) rather than pasting its block; load it only when the finding's severity depends on it.

### STEP 4 - Findings and Verdict

Number findings (F1, F2, ...). Each cites a specific task, phase, or omission, carries a severity, and recommends the smallest concrete change - do not redesign the plan. Distinguish **Missing** (absent), **Under-specified** (vague), and **Wrong** (incorrect on the facts, e.g., a miscomputed critical path). Record each root cause once; the verdict is driven by the highest severity, not the count.

| Severity | Meaning |
| --- | --- |
| Blocker | Plan cannot be committed - a load-bearing area is untasked (rollback for a Wide change) or the critical path is wrong |
| Major | Significant coverage gap, dependency error, or unjustified XL that must be fixed before commitment |
| Minor | Weak spot to improve; does not block commitment |
| Nit | Naming, formatting, phrasing |

| Verdict | Criteria |
| --- | --- |
| **Approve** | No Blockers, no Majors; all design areas Covered |
| **Approve with changes** | No Blockers; Majors bounded and specifically addressable |
| **Needs rework** | One or more Blockers, or gaps spanning multiple areas |

Any non-Approve verdict lists its required changes as a checkbox list (for Needs rework, the items driving the Blockers).

### Review Output Format

```markdown
# Task Breakdown Review: <Feature / System>

## Review Context

- **Plan reviewed:** <one line>
- **Source design:** <supplied | none - coverage judged against stated scope | none and no scope - internal soundness only>
- **Stack:** <detected | unknown>
- **Reviewer assumptions:** <reviewer-context facts; unavailable composed skills, if any>

## Intake

<what it builds; scope/exclusions; author-stated task count and critical path>

## Coverage Audit

| Area | Status | Note |
| --- | --- | --- |
| <area> | Covered / Under-specified / Missing / n/a | <task name or gap> |

## Structural Soundness

- **Dependency graph:** <finding or "sound">
- **Critical path:** <finding or "correct">
- **Sizing:** <finding or "sound">
- **Scope creep:** <finding or "none">
- **Phasing:** <finding or "sound">

## Findings

- **F1 (<Blocker | Major | Minor | Nit>):** <finding citing the task/phase/omission>. Recommendation: <smallest concrete change>.
- **F2 ...**

## Verdict

**<Approve | Approve with changes | Needs rework>** - <driving findings>.

Required changes (omit if Approve):
- [ ] <change tied to a finding>
```

### Review Self-Check

- [ ] **Setup:** behavioral-principles + stack-detect loaded
- [ ] **Intake:** plan, stated scope, and source-design status stated
- [ ] **Coverage:** each area marked Covered/Under-specified/Missing/n/a; no-design reviews key rows to stated scope + implied ops areas; Missing on a Wide/money/data-integrity area is a Blocker; scope-silent areas marked `n/a`, not Missing
- [ ] **Structure:** dependency graph, critical path, sizing, scope creep, and phasing each assessed
- [ ] **Findings:** each numbered, cites a specific task/omission, carries a severity, recommends the smallest change; each root cause once
- [ ] **Verdict:** driven by highest severity; non-Approve lists required changes as a checklist

---

## Avoid

**Both modes**

- Designing the system - resolve open architecture decisions as spikes/questions, never silently
- Implementation code or technical design (that is the design doc's job)
- Recomputing the critical path by summing sizes instead of counting hops
- Treating a missing rollback/migration/idempotency task on a Wide/money/data-integrity change as low severity

**Breakdown Mode**

- Tasks with no design trace (that is scope creep - flag it)
- Calendar estimates unless asked
- Estimating without the complexity scan
- Generic task names ("Backend", "Testing")
- Treating all tasks as must-have when scope hasn't been agreed
- Tasks without dependency statements
- Silently dropping XL tasks from the backlog

**Review Mode**

- Reviewing the plan you wish the author had written
- Rewriting the breakdown instead of naming the smallest fix
- Generic critique ("needs more tasks") without naming the design area or task
- Padding a Blocker review with Nits
- Approving with changes without listing the changes
