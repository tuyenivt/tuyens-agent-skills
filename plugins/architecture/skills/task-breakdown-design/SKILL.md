---
name: task-breakdown-design
description: Break a system design (HLD/LLD) into an implementable task graph with phases, dependency order, critical path, sizing, and scope-creep flags.
metadata:
  category: planning
  tags: [planning, task-breakdown, system-design, hld, lld, critical-path]
  type: workflow
user-invocable: true
---

# Design-to-Tasks Breakdown

Turn an approved system design (HLD and/or LLD) into an engineering task graph: phased tasks, dependency order, critical path, relative sizing, and scope flags. Audience: the architect or tech lead who owns the design and is planning the build.

Consumes a design doc as primary input - ideally the output of `task-design-architecture` (Sections 1-12), but any HLD/LLD works. Produces a task plan, not implementation code or a design doc. To review a breakdown someone else authored, use `task-breakdown-review`.

## When to Use

- An architecture design is signed off and needs to become buildable tasks
- Turning an HLD/LLD into a dependency-ordered plan before committing a timeline
- Surfacing hidden complexity (migrations, backward compat, rollback, observability) the design implies but did not task out

## Inputs

Required: a system design - HLD, LLD, or both. A `task-design-architecture` proposal is the ideal shape but not required.
Optional: constraints, exclusions, owning teams, capacity.

When input is a thin sketch rather than a real design, say so, list the design sections that would sharpen the plan, and break down on stated assumptions rather than inventing architecture. Do not design the system here - if a load-bearing decision is absent (sync vs. async, storage choice), raise it as an Open Question or spike, never resolve it silently.

When the prompt names a stack and `stack-detect` returns `unknown`, trust the prompt and record the assumption.

## Workflow

### STEP 1 - Setup

Use skill: `behavioral-principles`.
Use skill: `stack-detect`. Stack output picks which deep-dive atomics fire and names stack-specific tooling in tasks (test frameworks, migration tools). If unknown, proceed stack-agnostic.

### STEP 2 - Map the Design to Work

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

### STEP 3 - Hidden Complexity Scan

The design names components; this scan names the risks inside building them. Walk the checklist, state which signals apply with one-line evidence citing the design (a section, a heading, or a quoted phrase). The trailing S-references below are `task-design-architecture` hints; on a free-form doc cite the heading instead. Skipping the scan is the most common failure of this workflow.

| Signal | Look for in the design |
| --- | --- |
| Database changes | New table/column/index; zero-downtime required; backfill (S4) |
| Data store migration | Moving data between stores (Memcached->Redis, Postgres->DynamoDB) |
| API or protocol contract change | New/changed endpoints, field changes, auth-token format (S11) |
| Auth / permissions | New roles, scopes, token formats, key rotation (S2, S11) |
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
- Schema, API, or protocol contract change -> `Use skill: ops-backward-compatibility`
- Cross-service / cross-team dependencies -> `Use skill: dependency-impact-analysis`
- Flag-gated rollout -> `Use skill: ops-feature-flags`
- Any L/XL task touching shared state, auth, money, or cross-service contracts -> run `Use skill: review-blast-radius` and `Use skill: review-change-risk` on the single riskiest such task

Deep-dives inform task descriptions, sizes, and flag rationales - cite verdicts inline in the relevant flag (e.g. "blast radius Critical, Wide with flag"); do not paste their output blocks into the artifact.

### STEP 4 - Generate Tasks

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
- **Complexity signals** - required for L or XL; cite which Step 3 signals justify the size
- **Tag** - optional, only `nice-to-have` or `risk-reduction`

When a size hinges on a design decision the doc left open (sync vs. async), state the assumption in the description and the alternative under Open Questions, or raise a spike - do not pick for the architect.

### STEP 5 - Dependency Order and Critical Path

Number tasks with blocking relationships:

```
1. Define JWT spec (no deps)
2. JWKS endpoint infra (requires: 1)
3. Dual-mode /auth/validate (requires: 1)
4. Consumer SDK rollout - 30 services (requires: 2, 3)
```

**Critical path** = longest chain by hop count of dependent tasks (do not sum sizes; external dependencies are not hops). If chains tie on hops, pick the one carrying more external coordination or larger sizes. Name the chain in arrow form and add one sentence on *why* it pins delivery (size, externality, cross-team sequencing).

When tasks depend on other teams or external systems, name the owning team in `Depends on` so the critical path surfaces team-coordination risk. Another team's deliverable is an `external (<team>)` dependency, not a task - create tasks only for work your team executes. Spikes are numbered in the Dependency Order when other tasks depend on their outcome, but stay in the Spikes section and do not count toward the task count.

### STEP 6 - Scope and Risk Flags

Surface plan-level flags, each with a verdict: `proceed`, `de-scope`, `add spike`, `split epic`.

- **Design gaps:** load-bearing decisions the design left open; required sections absent for the blast radius (e.g., no rollback plan for a Wide change)
- **Scope creep:** work the plan needs that the design did not call for; tasks with no design trace
- **Hidden risks:** L/XL tasks on the critical path; data tasks with rollback complexity; integration blocked on external teams; tasks with unclear complexity (needs a spike); domain-calculation tasks (billing, tax, shipping)
- **XL tasks** stay in the backlog with `split` notes; promote to `split epic` only when the XL spans cohorts/waves that warrant their own planning

When the verdict is `add spike`, define:
- **Question:** specific unknown
- **Done condition:** what the spike must produce
- **Time-box:** maximum duration before it concludes with a finding

## Output Format

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
- **Complexity signals:** <Step-3 signals; required for L/XL>
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

## Self-Check

- [ ] **Setup:** behavioral-principles + stack-detect loaded; prompt-stated stack honored when detect is unknown
- [ ] **Map:** design sections drawn-from and absent listed; every task traces to a design section/component; no architecture invented
- [ ] **Scan:** every applicable signal listed with design-citing evidence; material deep-dive atomics loaded
- [ ] **Tasks:** each has Name, Type (from enum), Description, Traces-to, Depends-on, Size; L/XL cite complexity signals; XL has a `split` note; team/system named when external
- [ ] **Dependencies:** critical path named by hop count with a "why" sentence; Ops Readiness includes observability/rollback when the design implies them
- [ ] **Flags:** each flag carries a verdict; design gaps surfaced; spikes have Question + Done + Time-box
- [ ] **Assumptions and Open Questions** populated when the design left decisions open

## Avoid

- Designing the system - resolve open architecture decisions as spikes/questions, never silently
- Implementation code or technical design (that is the design doc's job)
- Tasks with no design trace (that is scope creep - flag it)
- Calendar estimates unless asked
- Estimating without the complexity scan
- Generic task names ("Backend", "Testing")
- Treating all tasks as must-have when scope hasn't been agreed
- Tasks without dependency statements
- Summing T-shirt sizes
- Silently dropping XL tasks from the backlog
