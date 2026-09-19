---
name: ops-engineering-governance
description: Convert incident lessons into enforceable guardrails and prioritized process improvements that target failure classes.
metadata:
  category: governance
  tags: [governance, process, review, deployment, testing, incident, prevention, guardrails, enforcement]
user-invocable: false
---

# Engineering Governance

## When to Use

- During postmortem, after root cause is identified and containment is in place
- When converting incident lessons into enforceable guardrails or process changes
- When reviewing guardrail effectiveness across a pattern of related incidents - the same output, where every existing control gets a `[strengthen]`, `[automate]`, `[broaden]`, or `[retire]` row naming the incidents it did not stop, and `Guardrails That Held` names the ones that did

## Rules

- Target the failure **class**, not the specific incident.
- Every guardrail must be enforceable (automated, structural, or alert-backed) and verifiable.
- Every process change must be actionable, assignable, and tied to a trigger condition.
- Match the weight of the control to the risk it mitigates; prefer structural enforcement over "be careful".
- Weigh a guardrail's cost (deploy friction, reviewer load, false positives) against the blast radius it prevents. Reshape blanket manual gates into risk-scoped automated controls instead of adopting or silently dropping them. A *proposed* gate emits one row: the reshaped guardrail, naming what it replaces in its Rule. A gate *already in force* emits the pair: a `[retire]` row for the blanket rule and a row for its risk-scoped replacement, when the replacement covers the class the gate was created for (its motivating incident); otherwise the gate gets a `[strengthen]` row and stays.
- Prioritize by blast-radius reduction. The bound on the list: one row per distinct failure class the incident evidence names; a row with no incident sentence behind it is wishlist and is cut. Two mechanisms that prevent the same class merge into one row when one control enforces both, and stay separate otherwise.
- The incident record is the authority for what happened; the code and its deployment manifests are the authority for what the system does. Read the code the record names and each row's enforcement point, no further. When they disagree (the record names a call or route the code does not have, a timeline that does not add up), cite the contradiction in the row's Failure Class Prevented or the process change's Why, and classify from the code; when the code has no such path at all, classify from the nearest code-confirmed instance of the class and cite both.
- A vendor is in scope when the trigger was theirs: contract terms (latency SLA, status webhook, escalation contact) are guardrails with scope `vendor`.

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
| Vendor             | Contract SLAs, status feeds, escalation paths                                          |

### Enforcement Tiers

Prefer higher-tier enforcement. Manual enforcement is acceptable only for a non-critical class, and then the Enforcement cell carries the automation plan: `checklist (automate: <planned mechanism>)` or `review policy (automate: <planned mechanism>)`. A critical class with only a manual option is a blocker to name in Process Improvements (an entry whose change begins with `Blocker:`), not a row that quietly ships manual. `contract term` is the exception: a vendor class has no higher tier, so its row ships bare at its priority, beside the code-side rows that bound the risk until the contract lands.

| Tier       | Enforcement values                          | Reliability |
| ---------- | ------------------------------------------- | ----------- |
| Automated  | CI gate, lint rule, policy-as-code          | High        |
| Structural | architecture test, framework constraint     | High        |
| Monitored  | alert, dashboard, SLO                       | Medium      |
| Manual     | checklist, review policy, contract term     | Low         |

### Guardrail Definition

Each row of the Guardrails table carries: a category prefix (`[new]` no rule covers this class, `[strengthen]` existing rule too weak, `[automate]` manual rule needs CI enforcement, `[broaden]` rule exists but missed the affected area, `[retire]` obsolete rule to remove); the Rule (specific, enforceable constraint); Scope (one of `code review`, `CI`, `deployment`, `runtime`, `operations`, `vendor`); Enforcement (one value from the tiers table, plus `(automate: ...)` on a checklist or review policy; on a `[retire]` row `remove: <step>`); Failure Class Prevented (the category with the incident sentence or code fact behind it in parentheses, or on a `[retire]` row `superseded by <replacement>` / `obsolete - <reason>`); Priority. A reshaped gate's Rule names what it replaces.

Priority assignment: **immediate** - the failure class can recur now with comparable or larger blast radius; **next sprint** - recurrence partially mitigated or blast radius reduced; **quarterly** - hygiene or low blast radius. Priority tracks recurrence risk, not lead time: a contract renegotiation that closes an immediate class is `immediate` with a long lead, and the code-side rows that bound the risk meanwhile sit beside it.

### Process Improvement Structure

For each process change, specify: **What** (the change), **Why** (failure class addressed), **Trigger** (when the process activates), **Owner** (role, not individual), **Priority**.

When the incident's failure class is one of transaction-boundary change across services, new async/event flow, data-model change with several consumers, new external dependency, auth/authz change, or infrastructure topology change, the design-doc trigger row must cover that class.

### Good: Enforceable guardrail (a table row)

```
| [new] Every outbound HTTP client (RestClient, RestTemplate, WebClient, Feign or @HttpExchange interface) is used only from the adapter package, whose call sites go through the breaker-decorating factory; an architecture test fails the build when any other package imports a client type | CI | architecture test | Cascading failure from external dependency timeout (INC-2104, INC-2291: gateway p99 9s pinned the DB pool) | immediate |
```

### Good: Specific process change (a bullet)

```
- **[Priority: next sprint]** Require a design doc for changes that modify transaction boundaries or add async flows
  - Why: transaction boundary error across services (three incidents last quarter); review alone misses distributed-state impact
  - Trigger: PR modifies transaction scope, adds an event publisher, or changes consumer logic
  - Owner: tech lead for the affected module
```

### Bad: Behavioral expectation, no structure

```
We should be more careful with external service calls and do better design reviews.
```

## Output Format

Consuming workflow skills parse this structure to surface actionable, prioritized governance improvements. Guardrail rows and Process Improvement entries are each ordered by priority, `immediate` first.

```
## Engineering Governance Recommendations

### Guardrails                                   {when at least one row}

| Rule | Scope | Enforcement | Failure Class Prevented | Priority |
| ---- | ----- | ----------- | ----------------------- | -------- |
| {[new] \| [strengthen] \| [automate] \| [broaden] \| [retire]} {specific enforceable constraint} | {code review \| CI \| deployment \| runtime \| operations \| vendor} | {CI gate \| lint rule \| policy-as-code \| architecture test \| framework constraint \| alert \| dashboard \| SLO \| checklist (automate: ...) \| review policy (automate: ...) \| contract term \| remove: <step>} | {failure category (incident sentence or code fact), or `superseded by <replacement>` / `obsolete - <reason>` on a retire row} | {immediate \| next sprint \| quarterly} |

### Process Improvements                         {when at least one entry}

- **[Priority: {immediate | next sprint | quarterly}]** {specific process change; `Blocker: ` first when a critical class has only a manual control}
  - Why: {failure class addressed, with the incident evidence}
  - Trigger: {when this process activates}
  - Owner: {role responsible}

### Guardrails That Held

- {existing control that caught or bounded this failure and what it prevented; a control that fired late or on a symptom is listed with that caveat; or "none"}

### No Recommendations                           {instead of Guardrails and Process Improvements, when neither has an entry: one sentence}
```

`Guardrails That Held` is never omitted: a control that stopped a failure is the only evidence that it earns its cost, and `retire` decisions are otherwise made from friction complaints alone. An incident with no recommendations still produces this section - that is its whole finding.

## Avoid

- Behavioral expectations without structural support ("be more careful").
- Guardrails so broad they generate false positives and get ignored.
- Manual-only enforcement for critical failure classes.
- Adding guardrails without retiring obsolete ones.
- Recommendations that fix the specific instance, not the failure class.
- Heavyweight process applied to low-risk areas, or rows with no incident evidence behind them.
- Architectural rewrites when targeted fixes suffice.
