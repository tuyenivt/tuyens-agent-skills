---
name: ops-engineering-governance
description: Convert incident lessons into enforceable guardrails and prioritized process improvements that target failure classes.
metadata:
  category: governance
  tags: [governance, process, review, deployment, testing, incident, prevention, guardrails, enforcement]
user-invocable: false
---

# Engineering Governance

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- During postmortem, after root cause is identified and containment is in place
- When converting incident lessons into enforceable guardrails or process changes
- When reviewing guardrail effectiveness across a pattern of related incidents

## Rules

- Target the failure **class**, not the specific incident.
- Every guardrail must be enforceable (automated, structural, or alert-backed) and verifiable.
- Every process change must be actionable, assignable, and tied to a trigger condition.
- Match the weight of the control to the risk it mitigates; prefer structural enforcement over "be careful".
- Weigh a guardrail's cost (deploy friction, reviewer load, false positives) against the blast radius it prevents. Reshape blanket manual gates into risk-scoped automated controls instead of adopting or silently dropping them; output the reshaped guardrail and name what it replaces in its Rule.
- Prioritize by blast-radius reduction; do not ship an unbounded improvement wishlist.

## Patterns

### Governance Areas

| Area               | Focus                                                                                  |
| ------------------ | -------------------------------------------------------------------------------------- |
| Review process     | Risk-based review triggers, ADR/design-doc requirements, branch protection             |
| Dependency control | New-dependency approval, CVE scanning, license compliance, ownership                   |
| Architecture       | Boundary enforcement, isolation, bulkheading                                           |
| Observability      | Missing signals that would have detected the failure earlier                           |
| Testing            | Coverage gaps, chaos experiment design, missing test types                             |
| Deployment safety  | Canary, feature flags, progressive rollout, rollback automation                        |
| Capacity / deps    | Pool sizing, timeout budgets, circuit breakers, rate limiting                          |
| Operational        | Runbooks, on-call training, incident playbooks                                         |

### Enforcement Tiers

Prefer higher-tier enforcement. If only manual is feasible, pair it with a plan to automate.

| Tier       | Mechanism                  | Reliability |
| ---------- | -------------------------- | ----------- |
| Automated  | CI gate, lint rule, policy | High        |
| Structural | Architecture constraint    | High        |
| Monitored  | Alert, dashboard, SLO      | Medium      |
| Manual     | Checklist, review policy   | Low         |

### Guardrail Definition

| Field                   | Description                                              |
| ----------------------- | -------------------------------------------------------- |
| Rule                    | Specific, enforceable constraint                         |
| Scope                   | Where it applies (code review, CI, deployment, runtime)  |
| Enforcement             | How it is checked (lint rule, CI gate, alert, checklist) |
| Failure class prevented | Category of failure this guards against                  |
| Priority                | immediate / next sprint / quarterly                      |

Categorize each guardrail as **new** (no rule covers this class), **strengthen** (existing rule too weak), **automate** (manual rule needs CI enforcement), or **broaden** (rule exists but missed the affected area). All categories go in the output's New Guardrails table; prefix non-new rules with the category, e.g. `[automate] Enforce the N+1 review rule via a CI query-count gate`.

### Process Improvement Structure

For each process change, specify: **What** (the change), **Why** (failure class addressed), **Trigger** (when the process activates), **Owner** (role, not individual), **Priority**.

Mandatory design-doc triggers include: transaction boundary changes across services, new async/event flows, data model changes with multiple consumers, new external dependency, auth/authz changes, infrastructure topology changes.

### Good: Enforceable guardrail

```
Rule: All external service calls must have a circuit breaker configured
Scope: Code review + CI
Enforcement: ArchUnit test verifies @CircuitBreaker on all REST client methods
Failure class prevented: Cascading failure from external dependency timeout
Priority: immediate
```

### Good: Specific process change with trigger

```
What: Require design doc for changes that modify transaction boundaries or add new async flows
Why: Three transaction-boundary incidents last quarter; review alone misses distributed-state impact
Trigger: PR modifies @Transactional, adds event publishers, or changes consumer logic
Owner: Tech lead for affected module
Priority: next sprint
```

### Bad: Behavioral expectation, no structure

```
We should be more careful with external service calls and do better design reviews.
```

## Output Format

Consuming workflow skills parse this structure to surface actionable, prioritized governance improvements.

```
## Engineering Governance Recommendations

### New Guardrails

| Rule | Scope | Enforcement | Failure Class Prevented | Priority |
| ---- | ----- | ----------- | ----------------------- | -------- |
| {specific enforceable constraint} | {code review / CI / deployment / runtime} | {lint rule / CI gate / alert / checklist} | {failure category} | immediate / next sprint / quarterly |

### Process Improvements

- **[Priority: immediate | next sprint | quarterly]** {What}: {specific process change}
  - Why: {failure class addressed}
  - Trigger: {when this process activates}
  - Owner: {role responsible}

### No Recommendations

{State explicitly if no governance improvements are needed - do not omit silently.}
```

Every guardrail needs an enforcement mechanism. Every process improvement needs a trigger and owner. Omit "No Recommendations" if recommendations were listed.

## Avoid

- Behavioral expectations without structural support ("be more careful").
- Guardrails so broad they generate false positives and get ignored.
- Manual-only enforcement for critical failure classes.
- Adding guardrails without retiring obsolete ones.
- Recommendations that fix the specific instance, not the failure class.
- Heavyweight process applied to low-risk areas, or unbounded wishlists.
- Architectural rewrites when targeted fixes suffice.
