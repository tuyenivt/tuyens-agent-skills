---
name: review-change-risk
description: Classify risk domains for a proposed change before code exists. Use for architecture proposals, migration plans, refactor plans.
metadata:
  category: governance
  tags: [risk-assessment, change-analysis, pre-implementation, classification]
user-invocable: false
---

# Change Risk Classification

## When to Use

- Pre-implementation: architecture proposals, migration plans, refactor plans, design docs
- When no diff exists yet, so `review-pr-risk` cannot apply
- As the framing step for downstream design and review

A change that is partly implemented gets both: `review-pr-risk` on the diff, this skill on the still-proposed remainder; a trigger that sits in the implemented half is the diff's, and a domain with triggers in both halves is classified here from the proposed half's triggers only.

## Rules

- Classify by risk domain, not diff signal. Evidence comes from the proposal and from any repository context that describes what it touches - architecture docs, incident history, schema, existing writers of a resource. Facts read from those sources are evidence, not assumptions.
- A change may trigger multiple primary and secondary domains; both count toward the overall level. Primary means the proposal states the trigger directly; secondary means the trigger is inferred from stated facts or repo evidence, or assumed. Neither carries more weight.
- Every domain triggered must cite the evidence that triggered it.
- Classify Low only when no domain is triggered at Medium or higher effective severity.
- A proposal offering options without choosing one is classified on the union of the options' triggers; Evidence names the option each High trigger belongs to. A stub the proposal adds for later use triggers nothing until it is reachable; when a config switch could make it reachable, the switch is an Open Question.
- Underspecified proposal: classify from stated facts, mark each domain whose trigger rests on a premise neither the proposal nor repo evidence states `(assumed - <what is not stated>)` in its evidence (a domain inferred from stated facts or repo evidence is secondary, not assumed), and record under Open Questions every unknown that could change the level and the question behind every assumed domain. An assumed domain keeps its default severity unless a cited justification downgrades it, the same as an evidenced one, and counts toward the ladder. A domain with no textual trigger and no repo evidence is not triggered - raise it as an Open Question instead. Never fail silently into a confident classification.
- When assumed domains outnumber the evidenced ones, the classification is a prompt for information, not a verdict: keep the level (an alarming level on a vague proposal is the useful signal) and open the Evidence line with `Provisional - N of M domains assumed;` (M counts triggered domains) so the reader knows answering the Open Questions is what settles it.

## Patterns

### Risk Domain Table

| Domain                   | Trigger Signals                                                                              | Default Severity |
| ------------------------ | -------------------------------------------------------------------------------------------- | ---------------- |
| Data                     | Schema migration, model change, new entity, column type change                               | High             |
| Concurrency              | In-process shared mutable state, new locking, thread pool change, concurrency model migration (a persistent resource written by several flows is the amplifier below, not this domain) | High             |
| Transaction boundary     | Scope change, new distributed transaction, isolation level change, retry of a non-idempotent operation (money movement, external writes) | High             |
| Security                 | Auth change, new exposure, access scope change, secret management, TLS/cert config           | High             |
| Configuration            | Config shared across environments, env-var pollution, prod-derived config                    | High             |
| Async/event              | New event flow, new consumer, event schema change, ordering assumption                       | Medium           |
| External integration     | New third-party API, modified contract, new outbound dependency                              | Medium           |
| Dependency upgrade       | Major version bump, framework upgrade, transitive change                                     | Medium           |
| Performance              | New hot path, query pattern change, cache invalidation change, pool change                   | Medium           |
| Architecture drift       | Boundary erosion, layer violation, new cross-module dependency, ownership shift              | Medium           |
| Deployment               | Non-reversible migration, multi-step deploy, config-dependent rollout                        | Medium           |

### Classification Rules

1. Identify triggered domains with evidence.
2. Mark each as primary (the proposal states the trigger) or secondary (inferred from stated facts or repo evidence, or assumed). A domain with several independent triggers is one bullet naming all of them. A domain's default severity may be downgraded one step, only with the justification cited in the domain's evidence (e.g. additive column, low-traffic table); never silently. The ladder in step 3 counts effective severities - a justified downgrade changes the domain's tier.
3. Determine the base level from the first matching row:

| Condition (first match wins)                      | Overall Level |
| -------------------------------------------------- | ------------- |
| Two or more high-severity domains                  | Critical      |
| One high-severity domain, OR three or more medium  | High          |
| One or two medium domains                          | Medium        |
| No domain at Medium or higher (none triggered, or only justified-downgrade-to-Low domains) | Low           |

4. Amplify: if a shared persistent resource (table, queue, cache key space) is written by two or more flows touched by the change, raise the level one tier (caps at Critical). A flow is a distinct write entry point in the architecture - an endpoint, consumer, scheduled job, or service - not a deploy-time version overlap, and not one code path writing two different resources (that is two resources with one writer each; its risk is already carried by the Data and Deployment domains). Evaluate every phase the proposal includes - a transitional window where two flows write the same resource counts even if the end state has one writer. Amplify once, however many resources qualify. An amplifier whose writer count is assumed applies the raise like an evidenced one (`Yes (assumed)`), and its question goes under Open Questions.
5. Assess reversibility: Irreversible when any triggered domain includes a destructive or non-reversible step (data loss, irreversible migration, an external side effect that cannot be recalled); Partially reversible when rollback needs manual or multi-step action; Reversible otherwise.

### Good

```
Overall Risk Level: Critical

Primary Risk Domains:
- Data (High) - schema migration on a high-traffic write table
- Transaction boundary (High) - webhook retries re-run a non-idempotent charge update

Secondary Risk Domains:
- Async/event (Medium) - webhook introduces an ordering assumption
- Deployment (Medium) - migration must precede code (assumed - the proposal does not state the deploy order)

Shared State: orders table (order-service endpoint, webhook handler)

Shared State Amplification: Yes

Reversibility: Irreversible - processed webhook events cannot be recalled

Evidence: Two high-severity domains (base Critical); shared writes to orders meet the amplifier condition, already at the cap

Open Questions: is the migration deployed before the code (Deployment assumed)
```

## Output Format

Callers parse the `Overall Risk Level` line. Blank lines between fields; domains listed highest severity first.

```
Overall Risk Level: {Low | Medium | High | Critical}

Primary Risk Domains:
- {Domain} ({High | Medium | Low}) - {1-sentence evidence}

Secondary Risk Domains:
- {Domain} ({High | Medium | Low}) - {1-sentence evidence}{ (assumed - <what is not stated>)}

Shared State: {resource} ({writing flow}, {writing flow}, ...); {next resource} (...) | none

Shared State Amplification: {Yes | No | Yes (assumed) | No (assumed)}

Reversibility: {Reversible | Partially reversible | Irreversible} - {1-sentence rollback path or blocker}

Evidence: {Provisional - N of M domains assumed; }{key signals driving the overall classification}

Open Questions: {unknowns that could change the level} | none
```

Always produce all sections. An empty domain list is the single bullet `- none`; Shared State lists every persistent resource the change touches that two or more flows write, and reads `none` when no resource has two writers; Open Questions reads `none` when empty; Evidence and Open Questions may run to several lines, one bullet each. The `Provisional` prefix is written only when assumed domains outnumber evidenced ones, and opens the first Evidence bullet when there are several. `Shared State Amplification: Yes` means the amplifier condition is met, whether or not the cap absorbed the raise; `(assumed)` on that line means the writer count rests on a premise neither the proposal nor repo evidence states. Never omit Evidence.

## Avoid

- Conflating code-quality concerns with systemic risk
