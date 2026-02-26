---
name: engineering-governance
description: Engineering process, governance improvement, and guardrail evolution for incident prevention
metadata:
  category: governance
  tags: [governance, process, review, deployment, testing, incident, prevention, guardrails, enforcement]
user-invocable: false
---

# Engineering Governance

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- During postmortem to recommend process improvements
- When identifying governance gaps that contributed to a production failure
- When strengthening engineering processes after a pattern of related incidents
- When evaluating deployment, review, or testing process effectiveness
- When converting incident lessons into enforceable guardrails
- When reviewing guardrail effectiveness across multiple incidents
- After root cause analysis is complete and containment is in place
- When identifying patterns across multiple related incidents for systemic prevention

## Rules

- Process changes must be proportional to the risk they mitigate
- Every recommendation must be actionable and assignable
- Prevention must address the class of failure, not just the specific instance
- Include both technical and process improvements
- Prefer structural enforcement over behavioral expectations
- Balance safety with development velocity -- do not over-process low-risk areas
- Prioritize by blast radius reduction potential
- Guardrails must target failure classes, not specific incidents
- Every guardrail must be enforceable (automated or structurally embedded)
- Do not propose guardrails that cannot be verified

## Pattern

### Governance Dimensions

| Dimension             | Focus                                                              |
| --------------------- | ------------------------------------------------------------------ |
| Review process        | Checklist updates, reviewer assignment, risk-based review triggers |
| Testing strategy      | Missing test types, coverage gaps, chaos experiment design         |
| Deployment safety     | Canary, feature flags, progressive rollout, rollback criteria      |
| Design governance     | When to require design docs, ADRs, architecture review             |
| Operational readiness | Runbook updates, on-call training, incident response playbooks     |
| Knowledge sharing     | Post-incident learnings distribution, pattern documentation        |

### Prevention Categories

| Category               | Focus                                                       |
| ---------------------- | ----------------------------------------------------------- |
| Architecture guardrail | Boundary enforcement, isolation, bulkheading                |
| Observability          | Missing signals that would have caught this earlier         |
| Testing                | Test scenario that would have prevented this in CI          |
| Deployment safety      | Canary, feature flags, rollback automation                  |
| Capacity planning      | Resource limits, pool sizing, rate limiting                 |
| Dependency management  | Timeout budgets, circuit breakers, fallback paths           |
| Process improvement    | Review checklist update, runbook addition, on-call training |
| Chaos engineering      | Fault injection scenario to validate resilience             |

### Recommendation Structure

For each recommendation:

1. **What** -- specific process change
2. **Why** -- which failure class or gap it addresses
3. **Trigger** -- when this process activates (change scope, risk level, module affected)
4. **Owner** -- who is responsible for implementation (role, not individual)
5. **Priority** -- immediate / next sprint / quarterly

### Good: Specific governance improvement with trigger

```
What: Require design doc for changes that modify transaction boundaries or add new async flows
Why: Transaction boundary changes have caused 3 incidents in the last quarter; review alone is insufficient for assessing distributed state impact
Trigger: PR modifies @Transactional annotations, adds new event publishers, or changes message consumer logic
Owner: Tech lead for affected module
Priority: next sprint
```

### Good: Specific prevention tied to failure class

```
1. Add connection pool circuit breaker (Priority: immediate)
   What: Configure HikariCP leak detection (30s) and add circuit breaker on payment-gateway client
   Why: Prevents connection pool exhaustion from slow downstream dependencies
   Blast radius reduction: Isolates payment failures from order and cart flows

2. Add timeout budget enforcement (Priority: next sprint)
   What: Set total request timeout = sum(downstream timeouts) + 20% buffer, fail fast when budget exceeded
   Why: Prevents retry amplification from consuming full connection pool
   Blast radius reduction: Bounds cascading latency at the integration boundary
```

### Bad: Vague process suggestion

```
We should have better design reviews for important changes.
```

### Design Doc Triggers

Recommend mandatory design documentation when changes involve:

- Transaction boundary modifications across services
- New async flows or event-driven communication
- Data model changes affecting multiple consumers
- New external dependency integration
- Changes to authentication or authorization model
- Infrastructure topology changes

### Chaos Experiment Design

For each proposed chaos experiment:

- **Hypothesis** -- what failure mode is being validated
- **Injection** -- specific fault to introduce (latency, error, resource limit)
- **Expected behavior** -- how the system should respond (fallback, graceful degradation)
- **Blast radius control** -- how to limit experiment impact

### Guardrail Definition

When proposing new or strengthened guardrails, define each with:

| Field                   | Description                                              |
| ----------------------- | -------------------------------------------------------- |
| Rule                    | Specific, enforceable constraint                         |
| Scope                   | Where it applies (code review, CI, deployment, runtime)  |
| Enforcement mechanism   | How it is checked (lint rule, CI gate, alert, checklist) |
| Failure class prevented | Category of failure this guards against                  |
| Priority                | immediate / next sprint / quarterly                      |

### Enforcement Tiers

| Tier       | Mechanism                  | Reliability |
| ---------- | -------------------------- | ----------- |
| Automated  | CI gate, lint rule, policy | High        |
| Structural | Architecture constraint    | High        |
| Monitored  | Alert, dashboard, SLO      | Medium      |
| Manual     | Checklist, review policy   | Low         |

Prefer higher-tier enforcement. If only manual enforcement is possible, pair it with a plan to automate.

### Good: Enforceable guardrail with clear scope

```
Rule: All external service calls must have a circuit breaker configured
Scope: Code review + CI
Enforcement: Custom ArchUnit test that verifies @CircuitBreaker on all REST client methods
Failure class prevented: Cascading failure from external dependency timeout
Priority: immediate
```

### Bad: Vague unenforceable suggestion

```
Rule: Be more careful with external service calls
```

### Guardrail Evolution Triggers

When proposing guardrail changes, categorize the change:

- **New guardrail** -- no existing rule covers this failure class
- **Strengthen existing** -- existing guardrail was too weak or narrow
- **Automate existing** -- manual guardrail needs automated enforcement
- **Broaden scope** -- guardrail exists but did not apply to the affected area

## Avoid

- Process changes disproportionate to the risk (heavyweight process for low-risk areas)
- Behavioral expectations without structural support ("be more careful" is not a process)
- Governance changes that only apply to the specific incident, not the failure class
- Adding process without removing or streamlining existing overhead
- Ignoring the cost of process on development velocity
- Guardrails that cannot be verified or enforced
- Rules so broad they generate false positives and get ignored
- Manual-only enforcement for critical failure classes
- Adding guardrails without removing or consolidating obsolete ones
- Recommendations that only fix the specific instance, not the failure class
- Unbounded improvement wishlists without prioritization
- Ignoring process and human factors (runbooks, training, review checklists)
- Proposing architectural rewrites when targeted fixes suffice
