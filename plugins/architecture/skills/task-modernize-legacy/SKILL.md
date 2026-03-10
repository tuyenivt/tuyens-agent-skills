---
name: task-modernize-legacy
description: Legacy system modernization - migrate from outdated language, framework, or architecture to a modern stack. Produces a phased modernization plan with technology selection, incremental migration, and coexistence strategy.
metadata:
  category: architecture
  tags: [architecture, migration, legacy, modernization, rewrite, strangler-fig]
  type: workflow
user-invocable: true
---

# Legacy System Modernization -- Staff Edition

## Purpose

Staff-level planning for modernizing a legacy system by migrating to a new language, framework, or architectural pattern. Focuses on:

- **Incremental replacement** -- strangler fig over big-bang rewrite; the legacy system keeps running
- **Technology selection with trade-offs** -- choose the target stack based on constraints, not hype
- **Knowledge transfer** -- legacy domain knowledge must survive the migration
- **Behavioral preservation** -- the new system must do what the old system does, including undocumented behaviors
- **Risk-ordered migration** -- migrate capabilities in the order that minimizes blast radius

This skill produces a modernization plan. It does not generate implementation code. For database-specific migration, use `task-db-migration-plan` from the core plugin.

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
| `quick`    | Early feasibility, "should we modernize and to what?" | Legacy assessment + target evaluation + top risks          |
| `standard` | Default -- modernization plan for leadership sign-off | All 8 sections                                             |
| `deep`     | Large legacy system, multi-year migration, high risk  | All 8 sections + behavioral inventory + failure simulation |

## Rules

- Never plan a big-bang rewrite -- all modernization must be incremental
- Target stack selection must be justified with trade-offs, not technology preference
- Undocumented behaviors in the legacy system must be discovered and preserved or explicitly deprecated
- The legacy system must keep running and serving traffic during modernization
- Every modernized capability must be verified against legacy behavior before cutover
- Domain knowledge must be extracted from legacy code and preserved in documentation or tests
- Do not generate implementation code
- Omit empty sections

## Modernization Model

### 1. Legacy System Assessment

**Understand the legacy system deeply before planning its replacement.**

Use skill: `stack-detect` to identify the current technology stack.
Use skill: `architecture-guardrail` to assess current architecture quality.

Analyze:

- **Technology profile** -- language, framework, runtime, dependencies, versions
- **Architecture pattern** -- monolith, layered, event-driven, stored procedures, etc.
- **System capabilities** -- what the system does (feature inventory)
- **Integration points** -- external systems, APIs, file feeds, databases shared with other systems
- **Technical debt inventory** -- known issues, workarounds, deprecated dependencies
- **Operational profile** -- how it runs (hosting, deployment, monitoring, on-call burden)
- **Knowledge concentration** -- who understands the system, bus factor, documentation quality
- **Scaling limits** -- what prevents the system from scaling (language, framework, architecture, data layer)

### 2. Modernization Driver Analysis

**Validate that modernization is the right solution.**

Not every legacy system needs modernization. Assess:

- **Driver specificity** -- is the pain caused by the technology, or by poor practices that would follow to any stack?
- **Cost of doing nothing** -- what happens if the system stays on the current stack for 2 more years?
- **Modernization ROI** -- investment required vs. expected benefit (hiring, velocity, scaling, cost)
- **Alternative approaches** -- would incremental refactoring on the current stack solve the problem cheaper?

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

For each option, state:

- Why it fits the requirements
- What trade-offs it introduces
- What risks are specific to this choice
- Estimated migration effort relative to other options

If the user has specified a target stack, validate the choice against these criteria and flag any concerns.

### 4. Behavioral Inventory

**The legacy system's behavior is the specification. Capture it.**

Before rewriting anything, inventory the legacy system's behavior:

- **Documented behaviors** -- features described in specs, user docs, or tests
- **Undocumented behaviors** -- logic that exists in code but has no documentation
- **Edge cases and workarounds** -- special handling for specific customers, data patterns, or error conditions
- **Integration contracts** -- exact request/response formats, error codes, timing expectations
- **Business rules in code** -- validation rules, calculation logic, state machines embedded in application code
- **Business rules in database** -- triggers, stored procedures, constraints, computed columns

Discovery methods:

1. **Existing test suites** -- extract behavioral contracts from tests
2. **Production traffic analysis** -- log request/response patterns to discover real usage
3. **Code reading** -- systematic review of legacy code for business rules
4. **Stakeholder interviews** -- ask domain experts about expected behaviors
5. **Shadow testing** -- run new system alongside legacy and compare outputs

For deep depth, produce a behavioral matrix:

| Capability   | Documented | Has Tests | Undocumented Behaviors | Migration Risk |
| ------------ | ---------- | --------- | ---------------------- | -------------- |
| Order create | Yes        | Partial   | Currency rounding rule | Medium         |

### 5. Migration Strategy and Phasing

**The core of the modernization plan.**

Use skill: `strangler-fig-pattern` for incremental migration strategy.
Use skill: `blast-radius-analysis` to assess migration risk per capability.
Use skill: `dependency-impact-analysis` for migration ordering.
Use skill: `feature-flags` for migration routing.

Choose the primary migration approach:

| Approach              | Use When                                               | Trade-off                                         |
| --------------------- | ------------------------------------------------------ | ------------------------------------------------- |
| Strangler fig         | Capabilities can be migrated independently             | Longest but safest; requires routing layer        |
| Branch by abstraction | Replacing internal implementation within same codebase | Works within monolith; requires good abstractions |
| Parallel run          | Must verify behavioral equivalence before cutover      | Expensive (run two systems); highest confidence   |
| Component extraction  | One module has clear boundaries, extract and rewrite   | Smallest scope; good starting point               |

For each migration phase:

- **Capability migrated** -- what moves from legacy to new system
- **Prerequisites** -- what must be in place (routing layer, data sync, tests)
- **Behavioral verification** -- how to confirm the new implementation matches legacy
- **Traffic migration** -- how traffic shifts from legacy to new system
- **Data migration** -- how data moves or stays accessible (see Section 6)
- **Rollback plan** -- how to revert to legacy if the migration fails
- **Duration estimate** -- rough timeline

Migration order heuristics:

1. **Non-critical, well-understood capabilities** -- build confidence and migration muscle
2. **Capabilities with good test coverage** -- easier to verify behavioral parity
3. **Performance bottlenecks** -- demonstrate modernization value early
4. **Core domain logic** -- highest risk, most valuable; migrate with full verification
5. **Integration points** -- migrate last; highest coordination cost

### 6. Data Migration and Coexistence

**Data outlives code. Plan the data transition carefully.**

Use skill: `data-consistency-modeling` for consistency during migration.
Use skill: `backward-compatibility-analysis` for schema compatibility.

Address:

- **Schema evolution** -- legacy schema to modern schema (normalization, type changes, naming conventions)
- **Data access during coexistence** -- both legacy and new system need data; who is the source of truth?
- **Data sync strategy** -- CDC, dual-write, shared database with access control, or API-mediated access
- **Historical data** -- migrate all history or archive and start fresh with cutover date
- **Data validation** -- how to verify data integrity after migration

This section focuses on application-level data coexistence. For detailed database migration planning (schema changes, zero-downtime DDL, rollback scripts), use `task-db-migration-plan` from the core plugin.

### 7. Team and Knowledge Transition

**Technology changes require people changes.**

Address:

- **Skills gap analysis** -- what skills the team needs for the target stack
- **Training plan** -- how the team learns the new stack (training, pairing, pilot projects)
- **Knowledge extraction** -- how domain knowledge in legacy code is captured before it is replaced
- **Staffing model during migration** -- who maintains legacy while others build new
- **Transition timeline** -- when the team stops maintaining legacy and fully operates new system

### 8. Risk Analysis

Use skill: `failure-classification` for failure categorization.
Use skill: `failure-propagation-analysis` for cascading failure assessment.
Use skill: `resiliency` for mitigation patterns.

Analyze modernization-specific risks:

- **Behavioral divergence** -- new system behaves differently from legacy in subtle ways
- **Second system effect** -- temptation to over-engineer the replacement
- **Migration fatigue** -- multi-year migration loses momentum and funding
- **Knowledge loss** -- legacy experts leave before domain knowledge is transferred
- **Coexistence complexity** -- running two systems is operationally expensive
- **Sunk cost trap** -- legacy investment makes it hard to commit to replacement
- **Scope creep** -- modernization becomes an excuse to add features, delaying delivery

For each high-risk scenario:

- State the risk
- State the likelihood (High / Medium / Low)
- State the impact
- State the mitigation

## Output

```markdown
# Legacy System Modernization Plan

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

## 4. Behavioral Inventory (deep only - summary for standard)

Key undocumented behaviors discovered:
Business rules in database:
Edge cases requiring special handling:

## 5. Migration Plan

### Migration Approach: {Strangler Fig / Branch by Abstraction / Parallel Run}

### Phase 1: {Capability}

What: {capability being migrated}
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

Skills Gap: {what the team needs to learn}
Training Plan: {approach and timeline}
Knowledge Extraction: {how domain knowledge is preserved}

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

- [ ] Modernization driver is specific and validated, not "legacy is old"
- [ ] Target stack selection has trade-off analysis with alternatives
- [ ] Behavioral inventory captures undocumented behaviors and edge cases
- [ ] Migration is incremental with strangler fig or equivalent pattern
- [ ] Every phase has behavioral verification against legacy
- [ ] Data coexistence strategy is explicit
- [ ] Team knowledge transition is planned
- [ ] No big-bang rewrite -- every phase is independently reversible
- [ ] Second system effect is acknowledged -- scope is migration, not redesign

## Avoid

- Big-bang rewrite -- the single biggest cause of failed modernizations
- Choosing target stack based on hype instead of constraints and trade-offs
- Ignoring undocumented behaviors -- they will surface as production bugs
- Treating modernization as an opportunity to redesign everything
- Underestimating the coexistence period -- plan for months or years, not weeks
- Losing domain knowledge when replacing legacy code
- Migration plans without behavioral verification at every phase
- Assuming the new system is better until proven by traffic
