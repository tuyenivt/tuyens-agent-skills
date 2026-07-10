---
name: task-modernize-legacy
description: "Plan or review legacy modernization: strangler fig migration, behavioral verification, target stack evaluation, team transition."
agent: architecture-architect
metadata:
  category: architecture
  tags: [architecture, migration, legacy, modernization, rewrite, strangler-fig]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows. If a delegated skill is unavailable (standalone use), apply the section's inline instructions on judgment and say so in the output.

# Legacy System Modernization -- Staff Edition

## Purpose

Staff-level legacy modernization plan: incremental strangler-fig migration, target stack selection by trade-offs, behavioral preservation including undocumented behaviors, and team transition. Produces a plan; no implementation code. For DB-specific migration use `task-db-migration`.

## When to Use

- Migrating from an outdated language or framework to a modern one (e.g., COBOL to Java, PHP to Go, Rails 3 to modern Rails/Node)
- Replacing a legacy framework that limits scaling or developer productivity
- Modernizing architecture patterns (e.g., legacy MVC monolith to clean architecture, stored procedures to application logic)
- The existing system works but is increasingly hard to maintain, hire for, or scale

## Inputs

| Input                | Required | Description                                                      |
| -------------------- | -------- | ---------------------------------------------------------------- |
| Legacy system        | Yes      | Current system description (language, framework, architecture)   |
| Modernization driver | Yes      | Why modernize (hiring, scaling, maintainability, security, cost) |
| Target stack         | No       | Desired target if known; if not, skill helps evaluate options    |
| Constraints          | No       | Timeline, budget, team skills, compliance, uptime requirements   |
| System capabilities  | No       | Key features, business flows, integrations                       |
| Traffic profile      | No       | Request volume, growth projections, peak patterns                |
| Team profile         | No       | Current team skills, hiring plans, training capacity             |
| Depth                | No       | `quick`, `standard` (default), or `deep`                         |

Handle partial inputs gracefully. State assumptions explicitly when input is missing.

## Depth Levels

| Depth      | When to Use                                           | Sections Produced                                          |
| ---------- | ----------------------------------------------------- | ---------------------------------------------------------- |
| `quick`    | Early feasibility, "should we modernize and to what?" | Sections 1-3 (assessment, driver analysis, target evaluation) + top risks from 8 + Staff-Level Summary |
| `standard` | Default -- modernization plan for leadership sign-off | All 8 sections                                             |
| `deep`     | Large legacy system, multi-year migration, high risk  | All 8 sections + full behavioral matrix (Section 4) + Failure Simulation section |

At `quick`, keep template numbering, omit unproduced sections silently, and waive their Self-Check items.

**Failure Simulation (deep only):** rendered as `## Failure Simulation` between Section 8 and the Staff-Level Summary. Per scenario (one to two), walk the highest-risk migration phase end to end - failure cause -> propagation path -> user-visible impact -> mitigation that activates -> recovery - then state Blast radius {Narrow | Moderate | Wide | Critical}, MTTR estimate, and the gap the plan must close.

## Rules

- Modernization is incremental; legacy keeps serving traffic throughout
- Justify target stack with trade-offs, not preference or hype
- Discover and preserve (or explicitly deprecate) undocumented behaviors; verify each capability against legacy before cutover
- Extract and preserve domain knowledge in docs or tests
- No implementation code; omit empty sections

## Modernization Model

### 0. Scope Confirmation

Before analysis, confirm the modernization scope:

- If the user mentions "modular architecture", "services", or "microservices" as a target, clarify: "Is the goal to restructure within the monolith (this skill), or to extract into independently deployable services (use `/task-decompose-monolith`)?" If clarification is impossible (async run), default to modernization-only on the current architecture shape, set the output's Scope line to "modernize now, decompose later (deferred)", and recommend `/task-decompose-monolith` after cutover. The answer is "both" when the request names services/microservices as an explicit target (a passing mention defaults to modernize-only); even then, modernize-then-decompose is the default order - behavioral parity is verifiable against an unchanged shape; decompose during modernization only when the monolith itself blocks migration.
- If the user specifies a target stack, note it for validation in Section 3.
- If the user does not specify depth, default to `standard`. Auto-escalate to `deep` when the stack is 5+ years behind (measured from the last major framework/runtime upgrade) or the system exceeds 50K lines.

### 1. Legacy System Assessment

Understand the legacy system deeply before planning its replacement.

Use skill: `stack-detect` for the current stack.
Use skill: `architecture-guardrail` for current boundary quality.

Capture: tech profile (language/framework/runtime/versions), architecture pattern, capability inventory, integration points, technical debt, operational profile, knowledge concentration (bus factor), and scaling limits with named cause. These feed Sections 2-5 and the Capability Inventory table in the Output.

### 2. Modernization Driver Analysis

Not every legacy system needs modernization. Validate the driver:

- Is the pain caused by the technology, or by practices that follow to any stack?
- What is the cost of doing nothing for 2 more years?
- Would incremental refactoring on the current stack solve it cheaper?

Produce a modernization justification:

| Factor                 | Current State                | After Modernization   | Confidence |
| ---------------------- | ---------------------------- | --------------------- | ---------- |
| Developer productivity | Slow due to {reason}         | Expected improvement  | High/Med   |
| Hiring pipeline        | Hard to hire for {stack}     | Larger talent pool    | High/Med   |
| Scaling ceiling        | Limited by {constraint}      | Removed by {approach} | High/Med   |
| Maintenance cost       | {hours/month} on workarounds | Reduced by {estimate} | Med/Low    |
| Security risk          | {EOL dependencies}           | Supported, patched    | High       |

If the justification is weak, recommend incremental improvement over full modernization.

### 3. Target Stack Evaluation

**Choose the target stack based on constraints and trade-offs, not trends.**

Use skill: `tradeoff-analysis` for structured decision documentation.

If the user has not specified a target stack, evaluate 2-3 realistic options:

| Criterion            | Option A            | Option B            | Option C            |
| -------------------- | ------------------- | ------------------- | ------------------- |
| Language/Framework   | {stack}             | {stack}             | {stack}             |
| Team familiarity     | High / Med / Low    | High / Med / Low    | High / Med / Low    |
| Hiring market        | Large / Med / Small | Large / Med / Small | Large / Med / Small |
| Ecosystem maturity   | Mature / Growing    | Mature / Growing    | Mature / Growing    |
| Performance fit      | Fits / Overkill     | Fits / Overkill     | Fits / Overkill     |
| Migration complexity | Low / Med / High    | Low / Med / High    | Low / Med / High    |
| Long-term viability  | Strong / Uncertain  | Strong / Uncertain  | Strong / Uncertain  |

Per option: why it fits, trade-offs, choice-specific risks, relative migration effort. If a target was already chosen, validate against these criteria and flag concerns rather than skip the analysis.

### 4. Behavioral Inventory

The legacy system's behavior is the specification. Capture it before rewriting.

[standard: summary of key undocumented behaviors. deep: full behavioral matrix below.]

Capture across: documented vs. undocumented behaviors, edge cases and workarounds, integration contracts (exact request/response, error codes), business rules in code (validation, calculation, state machines), business rules in DB (triggers, stored procedures, computed columns).

Discovery methods (use multiple): existing tests, production traffic analysis, code reading, stakeholder interviews, shadow testing against legacy. In a planning-only run with no codebase access, matrix rows are discovery tasks (method + owner), never hypotheses stated as facts. At deep, the matrix is added on top of the prose summary, one row per capability.

For deep depth, produce a behavioral matrix:

| Capability   | Documented | Has Tests | Undocumented Behaviors | Migration Risk |
| ------------ | ---------- | --------- | ---------------------- | -------------- |
| Order create | Yes        | Partial   | Currency rounding rule | Medium         |

### 5. Migration Strategy and Phasing

**The core of the modernization plan.**

Use skill: `strangler-fig-pattern` for incremental migration strategy.
Use skill: `review-blast-radius` to assess migration risk per capability.
Use skill: `dependency-impact-analysis` for migration ordering.
Use skill: `ops-feature-flags` for migration routing.

Choose the primary migration approach:

| Approach              | Use When                                               | Trade-off                                         |
| --------------------- | ------------------------------------------------------ | ------------------------------------------------- |
| Strangler fig         | Capabilities can be migrated independently             | Longest but safest; requires routing layer        |
| Branch by abstraction | Replacing internal implementation within same codebase | Works within monolith; requires good abstractions |
| Parallel run          | Must verify behavioral equivalence before cutover      | Expensive (run two systems); highest confidence   |
| Component extraction  | One module has clear boundaries, extract and rewrite   | Smallest scope; good starting point               |

Per phase, the Output template specifies the fields: capability, prerequisites, behavioral verification, traffic migration, data migration, rollback, duration. Every phase needs a rollback path and behavioral verification (shadow/replay/diff) - matching legacy is the gate. Foundation work (routing layer, CI, test harness, verification tooling) is Phase 0, numbered ahead of the template's Phase 1 with the same block (inapplicable fields N/A). Check summed phase durations against stated deadlines; on conflict, say so and re-scope - parallelize independent capabilities or cut scope, never compress verification.

Frozen external contracts (regulatory or contractual notice periods): preserve the legacy protocol behind a facade at the routing layer and freeze it until the notice period ends. The implementation may migrate behind the facade earlier; only the contract cutover is pinned past the notice date. Record the constraint in Section 1 and the phase plan.

Migration order heuristics:

1. **Non-critical, well-understood capabilities** -- build confidence and migration muscle
2. **Capabilities with good test coverage** -- easier to verify behavioral parity
3. **Performance bottlenecks** -- demonstrate modernization value early
4. **Core domain logic** -- highest risk, most valuable; migrate with full verification
5. **Integration points** -- migrate last; highest coordination cost

### 6. Data Migration and Coexistence

Data outlives code. Plan the transition carefully.

Use skill: `architecture-data-consistency` for consistency during migration.
Use skill: `ops-backward-compatibility` for schema compatibility.

Address: schema evolution (legacy -> modern), who is the source of truth during coexistence, sync strategy (CDC, dual-write, shared DB with ACL, API-mediated), historical-data scope (full migrate vs. archive + cutover date), and post-migration integrity validation.

**Calendar-critical systems:** For mandatory processing windows (payroll 1st/15th, month-end closes, regulatory deadlines), identify blackout periods explicitly and schedule risky phases between them with at least a 3-business-day pre-blackout freeze.

DB-engine EOL upgrades (e.g., MySQL 5.7 -> 8.0) are in scope here as a coexistence prerequisite; detailed schema-change planning (zero-downtime DDL, rollback scripts) still defers to `task-db-migration`.

### 7. Team and Knowledge Transition

Technology changes require people changes. Plan: skills gap to target stack, training approach (training/pairing/pilot), domain-knowledge extraction from legacy code, staffing model during migration (who maintains legacy while others build new), and the cutover when the team stops maintaining legacy. The Team Transition table in the Output template is the contract.

### 8. Risk Analysis

Use skill: `ops-failure-classification` for failure categorization.
Use skill: `failure-propagation-analysis` for cascading failure assessment.
Use skill: `ops-resiliency` for mitigation patterns.

Modernization-specific risks: behavioral divergence, second-system effect (over-engineering the replacement), migration fatigue (multi-year initiatives lose momentum), knowledge loss (legacy experts leave), coexistence cost, sunk-cost trap, scope creep (rewrite + new features doubles risk). Per high-risk scenario: likelihood, impact, mitigation.

## Review Mode

When reviewing a legacy-modernization plan authored by someone else:

Use skill: `architecture-review-lens` for severity taxonomy, completeness audit, internal-consistency check, assumptions audit, criteria scoring, questions for the author, and verdict.

Depth levels apply to plan authoring only; reviews run the full lens (tables for audits, lists for findings; report depth as "full"; the lens's skip rule covers steps that do not fit). This skill's planning content (driver analysis, approach table, migration-order heuristics) is valid review evidence - cite it as the bar the plan must meet.

Supply this modernization-plan-specific factor list to the completeness audit. Required factors carry no severity cap (Missing - or critically under-specified - required factors may be Blockers); advisory (No) factors cap at Major:

| Factor                       | Required | What "Present" Looks Like                                                          |
| ---------------------------- | -------- | ---------------------------------------------------------------------------------- |
| Legacy system assessment     | No       | Technology, architecture, age, team size, hidden behaviors / undocumented features |
| Modernization justification  | Yes      | Specific drivers (hiring, EOL, scaling ceiling, security); not just "it's old"     |
| Target stack                 | Yes      | Named language/framework/runtime with rationale, not "modern stack"                |
| Behavioral inventory         | Yes      | How current behavior is captured (tests, characterization, prod traffic capture)   |
| Strangler-fig migration      | Yes      | Coexistence phases, traffic routing, gradual replacement; not big-bang             |
| Data migration               | Yes      | Schema mapping, backfill plan, rollback safety, consistency during dual-run        |
| Behavioral verification      | Yes      | Shadow traffic, replay, diff testing - how new system is proven to match old       |
| Cutover strategy             | Yes      | Phased traffic shift with rollback gates; not a one-shot DNS swap                  |
| Team transition              | No       | Training plan, knowledge transfer from legacy maintainers, hiring timeline         |
| Scope discipline             | No       | Explicit non-goals (no new features during migration); cleanup of old system       |
| Risks and mitigations        | No       | Behavioral drift, performance regression, scope creep with mitigations             |

Specific quality checks beyond the standard lens:

- **Rewrite without behavioral inventory**: Blocker; rewrites without behavioral capture fail to match the legacy
- **Big-bang cutover**: Blocker for any system serving real users
- **"Modernize and add features" combined scope**: Major minimum; usually doubles the timeline and risk
- **Target stack without rationale beyond "modern"**: Major; "use Rust because it's modern" is not a justification
- **No team transition plan for the legacy maintainers**: Major; the people who understand the legacy are critical during migration
- **No diff testing or shadow traffic plan**: Major; behavioral parity must be measurable

Record each quality-check hit once, in the lens step that owns it (Missing factor -> Completeness; internal contradiction -> Internal Consistency; Present-but-wrong or Under-specified content -> Per-Factor Findings). A check's preset severity overrides the advisory cap - the cap binds only completeness-status findings.

Output header: `# Modernization Plan Review` and use the output structure defined in `architecture-review-lens`. Skip the plan Output template below. In this mode the Review Self-Check replaces the authoring Self-Check (self-checks are applied internally, never emitted in the deliverable):

- [ ] All factors audited with Required marking applied; verdict driven by highest severity
- [ ] Quality-check hits recorded once in the correct lens step and numbered
- [ ] Every finding cites a plan section; non-Approve verdict lists required changes

## Output

```markdown
# Legacy System Modernization Plan

Scope (from Section 0): {modernize-only | modernize now, decompose later (deferred)}
Assumptions: {stated assumptions from partial inputs}

## 1. Legacy System Assessment

Technology: {language, framework, runtime}
Architecture: {pattern}
Age: {years}
Team: {size, knowledge concentration}
Scaling Limits: {what constrains growth}

### Capability Inventory

| Capability | Complexity | Test Coverage     | Integration Points | Migration Risk |
| ---------- | ---------- | ----------------- | ------------------ | -------------- |
| Name       | Low/Med/Hi | Good/Partial/None | Count              | Low/Med/High   |

## 2. Modernization Justification

### Driver Analysis

| Factor   | Current State | After Modernization | Confidence |
| -------- | ------------- | ------------------- | ---------- |
| {factor} | {current}     | {expected}          | High/Med   |

Recommendation: Modernize / Incremental improvement / Defer

## 3. Target Stack

### Decision: {Chosen Stack}

| Aspect       | Detail                       |
| ------------ | ---------------------------- |
| Chosen       | {language/framework}         |
| Alternatives | {evaluated options}          |
| Reason       | {why this stack}             |
| Trade-off    | {what is sacrificed}         |
| Risk         | {what could make this wrong} |

## 4. Behavioral Inventory

**Standard depth** - prose summary:

- Key undocumented behaviors discovered:
- Business rules in database (triggers, stored procedures, computed columns):
- Edge cases requiring special handling:

**Deep depth** - add the full matrix:

| Capability   | Documented | Has Tests | Undocumented Behaviors | Migration Risk |
| ------------ | ---------- | --------- | ---------------------- | -------------- |
| {capability} | Yes/No     | Good/Partial/None | {behavior}     | Low/Med/High   |

## 5. Migration Plan

### Migration Approach: {Strangler Fig / Branch by Abstraction / Parallel Run / Component Extraction / hybrid - name the combination}

### Phase 1: {Capability}

What: {capability being migrated}
Prerequisites: {what must be in place}
Behavioral verification: {how to confirm parity}
Traffic migration: {routing strategy}
Data migration: {how data moves}
Rollback: {revert plan}
Duration: {estimate}

### Phase Summary

| Phase | Capability | Risk Level | Duration | Verification Method |
| ----- | ---------- | ---------- | -------- | ------------------- |
| 1     | Name       | Low        | Weeks    | Shadow comparison   |

## 6. Data Migration

Schema Evolution: {key changes}
Coexistence Strategy: {how both systems access data}
Historical Data: {migrate / archive / cutover date}

## 7. Team Transition

### Team Transition

| Aspect              | Current State  | Target State        | Action                               | Timeline   |
| ------------------- | -------------- | ------------------- | ------------------------------------ | ---------- |
| Language skills     | {current}      | {needed}            | {training approach}                  | {weeks}    |
| Framework knowledge | {current}      | {needed}            | {approach}                           | {weeks}    |
| Domain knowledge    | {who holds it} | {documented/tested} | {extraction method}                  | {weeks}    |
| Staffing model      | {current}      | {during migration}  | {who maintains legacy vs builds new} | {duration} |

## 8. Risks and Mitigations

| Risk                  | Likelihood | Impact | Mitigation                            |
| --------------------- | ---------- | ------ | ------------------------------------- |
| Behavioral divergence | Medium     | High   | Shadow testing, behavioral tests      |
| Migration fatigue     | Medium     | High   | Phased milestones with value delivery |

## Staff-Level Summary

- Modernization feasibility: Recommended / Conditional / Not recommended
- Target stack: {chosen stack}
- Estimated duration: {quarters/years}
- Highest-risk phase: {which and why}
- Key prerequisite: {what must happen before migration starts}
```

## Self-Check

- [ ] Section 1 covers integration points, scaling limits, knowledge concentration
- [ ] Modernization driver is specific and validated, not "legacy is old" (Section 2)
- [ ] Target stack selection has trade-off analysis with at least one alternative (Section 3)
- [ ] Behavioral inventory captures undocumented behaviors and edge cases (Section 4)
- [ ] Migration approach explicitly chosen; every phase has behavioral verification (Section 5)
- [ ] Data coexistence strategy explicit with consistency guarantees (Section 6)
- [ ] Team transition planned (Section 7); high-risk scenarios have mitigations (Section 8)
- [ ] Every phase is independently reversible

## Avoid

- Treating modernization as an excuse to redesign everything (second-system effect)
- Underestimating coexistence period - plan in months/years, not weeks
- Assuming the new system is better until proven by traffic
