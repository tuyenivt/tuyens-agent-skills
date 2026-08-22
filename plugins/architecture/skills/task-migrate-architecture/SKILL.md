---
name: task-migrate-architecture
description: "Plan or review a system migration: monolith decomposition, service consolidation, legacy modernization, or zero-downtime schema change."
agent: architecture-architect
metadata:
  category: architecture
  tags: [architecture, migration, decomposition, consolidation, modernization, schema, strangler-fig]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows. Then load `Use skill: stack-detect` unless Shape = Schema (which is engine-driven, not stack-driven) - the stack grounds merge feasibility, target-stack evaluation, and interoperability. If a delegated skill is unavailable (standalone use), apply the section's inline instructions on judgment and say so in the output. When no codebase is accessible, repo-analysis delegations (stack-detect, architecture-guardrail) run on the facts stated in the request or plan under review (recorded on the output's Assumptions line), and claims needing code verification become discovery tasks under Knowledge gaps. Delegated skills supply analysis method, not structure: this skill's Output template is the only output contract - absorb their findings into its fields and never emit their own Output blocks.

# Architecture Migration -- Staff Edition

## Purpose

Staff-level plan to move a system from its current state to a target state while it keeps serving traffic: incremental phasing, explicit data ownership transfer, per-phase rollback, and a feasibility verdict. Produces a plan; no implementation code.

For designing a target state with no transition to plan, use `task-design-architecture`. For a library or platform version bump, use `task-dependency-upgrade`.

## When to Use

- Breaking a monolith into independently deployable services, or into a modular monolith
- Merging over-split microservices into fewer, well-bounded services
- Migrating off an outdated language, framework, or architecture pattern
- Changing a production schema where the change is not purely additive (rename, type change, constraint on existing data, table split, backfill at scale)

## Migration Shape

Every migration moves a boundary. The shape names which direction, and selects one shape-specific section on top of the shared spine.

| Shape           | Direction of travel                      | Shape section | Typical trigger                                     |
| --------------- | ---------------------------------------- | ------------- | --------------------------------------------------- |
| **Decompose**   | One system -> many services              | 3a            | Scaling hotspots, deploy contention, team autonomy  |
| **Consolidate** | Many services -> fewer                   | 3b            | Ops overhead, chatty services, distributed monolith |
| **Modernize**   | One system -> equivalent on a new stack  | 3c            | EOL runtime, hiring, maintainability                |
| **Schema**      | One data shape -> another, same system   | 3d            | Rename, type change, constraint add, table split    |

Detect the shape from the request; when two apply, name the primary and run the second as a follow-up phase rather than interleaving both. Modernize + Decompose in one request defaults to modernize-then-decompose - behavioral parity is verifiable only against an unchanged shape. State the chosen shape and the deferred one in the output's Scope line.

Shape = Schema runs Sections 1, 3d, 5, 6, 7 only; Sections 2 and 4 do not apply (a schema change moves no service boundary and transfers no ownership between teams). All other shapes run every section.

## Inputs

| Input                | Required | Description                                                                       |
| -------------------- | -------- | --------------------------------------------------------------------------------- |
| Current state        | Yes      | The system today: modules/services, data model, key flows (Schema: the DDL)       |
| Migration driver     | Yes      | Why move - scaling, autonomy, ops cost, EOL, correctness                          |
| Target state         | No       | Desired end state if known; otherwise the plan evaluates options                  |
| Constraints          | No       | Timeline, team capacity, compliance, uptime, freeze windows                       |
| Dependencies         | No       | Call graph, event flows, shared tables                                            |
| Traffic profile      | No       | Volume, hotspots, peak patterns (Schema: row counts)                              |
| Reference doc        | No       | Company template or an approved prior plan; path or pasted content                |
| Depth                | No       | `quick`, `standard` (default), or `deep`                                          |

When a reference doc is supplied, or the project's instruction file carries a `## Design Docs` section, load `Use skill: design-reference-pattern` (authoring only - in Review Mode do not load it; the review follows the lens's structure, and the house template is not review evidence). It governs headings, order, and metadata slots only - the one sanctioned exception to the behavioral directive's structure rule; every section this workflow requires maps to a house heading or is appended under its own name, the Shape, Scope, and Assumptions header lines ride with the metadata slots, and nothing is dropped to fit the template.

Handle partial inputs gracefully. State assumptions explicitly when input is missing. For inputs naming only 1-3 specific services, skip the full landscape and scope the assessment to those and their immediate dependencies.

## Depth Levels

| Depth      | When to Use                                          | Sections Produced                                                                 |
| ---------- | ---------------------------------------------------- | --------------------------------------------------------------------------------- |
| `quick`    | Feasibility check - "should we do this at all?"      | Sections 1, the shape section, top risks from 6, Staff-Level Summary              |
| `standard` | Default - plan for engineering leadership sign-off   | All applicable sections                                                           |
| `deep`     | Large system, multi-team, multi-quarter migration    | All applicable sections + dependency deep-dive + failure simulation               |

At `quick`, keep template numbering, omit unproduced sections silently, waive their Self-Check items, and lead with the Staff-Level Summary feasibility verdict.

**Deep adds:** per-unit transitive dependency enumeration (code, data, config) classified severable or requires-migration; and a failure simulation walking the highest-risk phase end to end - cause -> propagation -> user-visible impact -> mitigation that activates -> recovery - closing with Blast radius {Narrow | Moderate | Wide | Critical}, MTTR estimate, and the gap the plan must close.

**Driver validation gate.** The driver passes when the problem needs what the target state uniquely provides. It fails when a cheaper same-shape remedy addresses it: slow tests -> parallelize; tangled code -> modular monolith; single-team velocity -> CI/CD; "the stack is old" with no EOL, hiring, or scaling consequence -> incremental refactor. A failed driver makes the honest deliverable Sections 1-2 plus a Staff-Level Summary opening **Not recommended**, with duration and highest-risk as N/A and two added lines: "Why not recommended: {reason}" and "Recommended alternative: {what to do instead}". Do not produce hypothetical phases for a migration you are recommending against.

## Rules

- Validate the driver before planning the migration; a cheaper same-shape remedy beats a migration
- Boundaries follow domain ownership, not code structure or convenience
- Every phase is incremental and independently reversible; no big-bang cutover
- Plan data ownership transfer explicitly per unit; one owner per entity in steady state
- Phase order is set by risk and dependency, not convenience
- Every phase states a verification that must pass before the next begins
- No implementation code; omit empty sections

## Migration Model

### 1. Current State Assessment

Run first. Understand what exists before planning its replacement.

Use skill: `architecture-guardrail` to assess current boundary quality.

Capture: deploy frequency, duration, and rollback frequency (this gates the cadence check in 3a); specific pain points with evidence, since vague drivers produce vague plans; integration points; and knowledge concentration (bus factor). Apply the driver validation gate here.

**Landscape predicate.** Build a landscape before the shape section when the current state has more than one independently deployed application whose code or config this migration changes. Backing infrastructure (DB, cache, broker, search) and unchanged SaaS integrations are inventory or integration rows, not systems - a monolith with external dependencies needs no landscape; a schema change with several direct-reader services does. The landscape covers inventory, integrations, and cross-system risks. Enrich any user-supplied inventory rather than restating it.

- Mark every row **Confirmed** (authored documentation, code-verified, or stated in the request) or **Inferred** (derived from config, naming, or convention - a compose file or IaC alone is Inferred). A row's confidence is that of its least-confirmed cell. Never invent values: unknown Owner/Stack cells say Unknown, and undocumented systems still get rows - they are usually where the risk lives
- State protocol and coupling separately: protocol is how the call travels (sync REST/gRPC, async event, batch, direct DB); coupling is how failure propagates - **Tight** = caller blocks and target failure propagates, **Loose** = caller continues on target failure. A sync call is loose with a fallback; an async event is tight when the consumer cannot progress without it. When failure behavior is undeterminable, mark Tight and Inferred
- One row per direct edge, From = initiator; describe multi-hop chains in notes, never as one aggregate row. Broker-mediated flows get one row per producer-consumer pair with the topic named; the broker is inventoried as infrastructure. Direct cross-service DB or cache access is an integration row with To = the data's owning system. External SaaS is an integration row marked external
- Cross-system risks fall into single points of failure (shared DB, auth, or broker with no fallback), shared data (more than one writer - name the authoritative writer or record "writer unknown"), and missing capability (implied by the landscape but unowned). Severity rates consequence, not confidence: High = failure halts multiple systems, risks data loss, or breaches a compliance obligation; Medium = degrades function or has a workaround; Low = friction only. Risks cite landscape evidence, not generic concern
- Separate a **Risk** (a finding about the system's design) from a **Gap** (a finding about your knowledge of it - undocumented system, unverifiable integration, unknown owner). Inventory without a risk section is an input, not an output

For Shape = Schema, this section is the current DDL, row counts, engine and version, and the deployment model (single service, multi-service, rolling, blue-green) - the cadence and bus-factor items do not apply.

### 2. Boundary Analysis [not Schema]

Identify the domain boundaries before drawing new lines.

Use skill: `system-boundary-design` for formal boundary modeling.

Per boundary: owned entities, inbound/outbound dependencies, data access pattern. Surface shared-kernel entities explicitly and minimize them. Name the cross-boundary domain events that become integration contracts. One module owns each entity; cross-boundary access goes through API or event, never direct DB reads.

### 3a. Decomposition [Shape = Decompose]

Use skill: `architecture-data-consistency` for inter-service consistency strategy.
Use skill: `ops-resiliency` for fault tolerance between services.
Use skill: `tradeoff-analysis` for communication model and integration pattern decisions.

**Target shape.** When no target state is supplied, evaluate 2-3 candidate end states (modular monolith, modular core plus selective extraction, full decomposition) against the driver, the cadence-gate result, and team count via `tradeoff-analysis`; name the choice and why the others lose.

Map each target service to an owning team; when ownership is unstated, propose the team whose current module work is closest and mark it Proposed. Flag services no team plausibly owns - team-autonomy drivers fail without Conway alignment. Name the communication model (sync vs async) and consistency requirement (strong vs eventual) per interaction. If the target stack differs from the source, add interoperability: serialization contracts, client-library strategy, contract testing across the language boundary.

**Deploy cadence prerequisite.** Independently deployable services require frequent deployment. The test is literal: deploy frequency below weekly (every-two-weeks fails) makes CI/CD a prerequisite, not a nice-to-have. Recommend establishing continuous deployment first, or a modular monolith as the intermediate step. When only the cadence gate fails and the driver is valid, proceed and make Phase 0 the gate's remedy.

**Lowest-risk-first candidates.** Analytics/reporting (read-only, isolated), notifications (tolerates eventual consistency), and search (read model over events) are safe first extractions in nearly any system. Recommend one as Phase 1 unless unusually coupled here.

Extraction order criteria:

| Criterion               | Extract first                                       | Extract later                   |
| ----------------------- | --------------------------------------------------- | ------------------------------- |
| Coupling                | Few inbound/outbound dependencies                   | Many cross-cutting dependencies |
| Data sharing            | Owns its data, few shared tables                    | Heavily shared tables           |
| Business criticality    | Non-critical, failure tolerable                     | Revenue-critical, zero-downtime |
| Bounded context clarity | Clear domain boundary                               | Fuzzy boundary, shared logic    |

### 3b. Consolidation [Shape = Consolidate]

Use skill: `system-boundary-design` for boundary redesign.
Use skill: `tradeoff-analysis` for merge vs keep-separate on borderline candidates.

Justify every merge by a concrete smell:

| Smell                    | Signal                                                          | Indicates                                    |
| ------------------------ | --------------------------------------------------------------- | -------------------------------------------- |
| Chatty services          | >5 sync calls between two services per user request             | Should be one service or use async           |
| Distributed monolith     | Services must deploy together; change in A requires change in B | Not independently deployable = not a service |
| Nano service             | Wraps a single entity or single CRUD operation                  | Too fine-grained; merge with parent domain   |
| Shared database          | Multiple services read/write the same tables                    | No real boundary; merge or fix ownership     |
| Circular dependencies    | A -> B -> A call chains                                         | Boundary drawn in wrong place                |
| Distributed transaction  | Saga/2PC for what was one DB transaction                        | Artificial split; merge restores atomicity   |
| Single consumer / proxy  | Exists only for one caller, or adds no logic beyond forwarding  | Inline into the consumer or remove the proxy |
| Team mismatch            | One person maintains 5+ services                                | Consolidate to match team capacity           |

Per merge group: which services combine, the resulting service (name, responsibility, data ownership), smells resolved, and boundary improvement. List services that stay separate with the reason - borderline candidates may resolve to "keep separate, fix the boundary", recorded with the boundary fix named. Cross-language merges mean rewriting the smaller service: account for rewrite cost and behavioral fidelity, or co-locate both behind one API instead. The goal is right-sized services, not monolith restoration.

Merge order: blast radius wins when criteria conflict - split a group across phases and merge low-risk members first. Decommission and cleanup belong inside their merge group's phase, not as separate phases.

### 3c. Modernization [Shape = Modernize]

Use skill: `tradeoff-analysis` for target stack selection.

**Target stack.** If unspecified, evaluate 2-3 realistic options on team familiarity, hiring market, ecosystem maturity, performance fit, migration complexity, and long-term viability. Per option: why it fits, trade-offs, choice-specific risks, relative effort. If a target was already chosen, validate against these criteria and flag concerns rather than skip the analysis. "Modern" is not a rationale.

**Behavioral inventory.** The legacy system's behavior is the specification - capture it before rewriting. Cover documented vs undocumented behaviors, edge cases and workarounds, integration contracts (exact request/response and error codes), business rules in code, and business rules in the database (triggers, stored procedures, computed columns). Discovery uses multiple methods: existing tests, production traffic analysis, code reading, stakeholder interviews, shadow testing. In a planning-only run with no codebase access, inventory rows are discovery tasks (method + owner), never hypotheses stated as facts. At `deep`, add a per-capability matrix: Capability | Documented | Has Tests | Undocumented Behaviors | Migration Risk.

**Team transition.** Skills gap to the target stack, training approach (training/pairing/pilot), domain-knowledge extraction from legacy code, staffing model during migration (who maintains legacy while others build new), and the point the team stops maintaining legacy.

Migration order heuristics: non-critical well-understood capabilities first (build migration muscle), then well-tested capabilities (parity is verifiable), then performance bottlenecks (demonstrate value), then core domain logic (highest risk, full verification), then integration points last (highest coordination cost).

### 3d. Schema Change [Shape = Schema]

Use skill: `review-change-risk` to identify risk domains.
Use skill: `backend-db-migration` for lock risk, expand-contract sequencing, and backfill safety.
Use skill: `backend-db-indexing` for index creation lock behavior.
Use skill: `ops-backward-compatibility` for application-level compatibility during transition.
Use skill: `backend-idempotency` to keep the backfill safe to re-run.

**Classification.** State type and risk before planning steps.

| Type                    | Risk Level | Zero-Downtime Complexity                     |
| ----------------------- | ---------- | -------------------------------------------- |
| Add nullable column     | Low        | Low - single phase                           |
| Add table               | Low        | Low - single phase                           |
| Add index (concurrent)  | Low-Medium | Medium - locking depends on engine           |
| Add NOT NULL constraint | Medium     | High - requires backfill first               |
| Add unique constraint   | Medium     | High - requires data validation first        |
| Add foreign key         | Medium     | High - requires existing data to be valid    |
| Rename column           | High       | Very high - requires expand-contract         |
| Change column type      | High       | Very high - requires expand-contract         |
| Drop column             | High       | High - requires all readers removed first    |
| Drop table              | High       | High - requires all references removed first |
| Backfill existing rows  | Variable   | Medium-High - batch sizing critical          |
| Split or merge tables   | Very High  | Very high - requires dual-write phase        |

"Variable" resolves by scale: Medium below 1M rows, High at or above. Compound migrations classify each sub-change separately, state dependency order, and take the highest sub-change risk as the overall level.

**Lock risk.** Per operation state the lock type in the engine's vocabulary (PostgreSQL: ACCESS SHARE through ACCESS EXCLUSIVE; MySQL: metadata lock + InnoDB row locks - an MDL request queues behind long-running queries and blocks everything behind it), estimated duration relative to table size, and whether a concurrent/online alternative exists.

| Operation                         | PostgreSQL                                      | MySQL/MariaDB                                               |
| --------------------------------- | ----------------------------------------------- | ----------------------------------------------------------- |
| ADD COLUMN (nullable, no default) | Brief lock - safe                               | Brief (InnoDB)                                              |
| ADD COLUMN with DEFAULT (PG11+)   | Metadata only - safe                            | INSTANT on 8.0.12+ (any position 8.0.29+); table copy older |
| ADD COLUMN with DEFAULT (< PG11)  | Full table rewrite - dangerous                  | -                                                           |
| CREATE INDEX                      | Full scan; use CONCURRENTLY (cannot run in txn) | Online DDL in InnoDB                                        |
| ADD CONSTRAINT NOT NULL / FK      | Full table scan to validate; NOT VALID defers it | Full table copy                                             |
| DROP COLUMN                       | Brief lock - safe                               | Online DDL                                                  |

Flag any step whose exclusive lock duration scales with table size above 1M rows as high risk. Brief metadata-only exclusive locks pass, but set a `lock_timeout` with retry so they cannot queue behind long transactions. This table shows each operation's naive form; the sequences below avoid the worst cases.

**Expand-contract** applies to any non-additive change. Expand: add new column/table, keep old, dual-write both, read old. Migrate: new populated and validated, reads flip after verification. Contract: drop old in a separate deploy once no readers or writers reference it.

- *PostgreSQL NOT NULL on large tables:* validating with a full scan takes ACCESS EXCLUSIVE. Above 1M rows use `NOT VALID` + `VALIDATE CONSTRAINT` (ShareUpdateExclusiveLock, non-blocking). Sequence: nullable column -> dual-write -> batched backfill -> `ADD CONSTRAINT ... NOT VALID` -> background `VALIDATE CONSTRAINT` -> `SET NOT NULL` (metadata-only on PG12+ once a validated CHECK exists) -> drop the redundant CHECK. On a rename, relax the old column's NOT NULL before stopping dual-write.
- *MySQL/InnoDB:* prefer `ALGORITHM=INPLACE` or `INSTANT`, verifying support per operation and server version; use pt-osc/gh-ost where a table rebuild is forced. Multi-table `RENAME TABLE` is atomic - use it for cutovers. Unique-index builds fail on duplicate data - dedupe first. For table splits, bake new constraints into the new table's DDL and keep the old table write-complete until cutover so a reverse RENAME is lossless.

Name the dual-write mechanism and its failure modes: trigger-based survives mixed app versions during rolling deploys; application-level is simpler to remove. Bidirectional trigger sync must suppress its own echo (guard with `pg_trigger_depth()` or a session flag) or the two triggers recurse. Renames and swaps carry dependent objects - inventory indexes, FKs, views, triggers, RLS policies, grants, and replication publications as pre-conditions. Build secondary indexes after bulk backfill unless reads need them during dual-write. Skip expand-contract only when the change is purely additive, or downtime is explicitly authorized and scheduled.

**Backfill.** Never run an unbounded UPDATE on a production table - batch by ID range or cursor, 100-1000 rows per batch, looping until zero rows change. Estimate rows, batch size, rows/sec (1000-5000 for simple updates, less for joins), total duration (flag above 1 hour - risk of failure mid-run), lock held per batch, and retry safety. Any job over ~1 hour needs checkpointed resume; bulk copies via batched `INSERT...SELECT` size by measured rows/sec on a staging slice. Backfills preparing a constraint include data repair: define the survivor policy for duplicates (keep newest, merge, quarantine) and dedupe as a batched idempotent job before adding the constraint. Rows repair cannot resolve get an explicit disposition before the constraint lands - sentinel value, exclusion (archive or delete), or narrowed constraint scope; rows left NULL block NOT NULL. A backfill that approximates semantics (proxy timestamps, derived values) documents the approximation and gets data-owner sign-off before reads flip. Throttle on replica lag (pause above 10s, resume below 5s); the same throttle protects logical-replication/CDC consumers - backfill floods their slots, so watch slot lag, WAL retention, and how schema changes appear in decoded events; a table split also adds the new table to the publication/connector and plans its initial snapshot before cutover. Prefer a background job over an in-migration script for large tables; use application-layer dual-write with lazy migration when the backfill cannot finish before deploy.

### 4. Data Ownership Transfer [not Schema]

The hardest part of any boundary migration. Plan explicitly per unit.

Use skill: `architecture-data-consistency` for consistency during migration.
Use skill: `ops-backward-compatibility` for schema change safety.

Per unit: current layout, target layout, migration strategy, consistency guarantee during transition, and reconciliation. Shared-database separation work (schema separation, write-path inventory) starts first even when the owning services move later.

**Strategy by case:**

- *Already shared DB* (Consolidate): no data migration - schema cleanup, remove artificial boundaries, merge models. Do not apply the full phase template.
- *Same engine, separate DBs:* schema merge with migration scripts; reintroduce the FKs and constraints the original split dropped, validating existing data first.
- *Different engines:* pick the target, migrate data.
- *Event-sourced:* merge event stores, or project to a unified store.
- *Splitting out* (Decompose): shared DB -> schema separation -> separate DB, with CDC or dual-write for sync and a reconciliation job to detect drift.

When data physically relocates, phase it: dual-read -> migrate/transform -> dual-write -> cutover -> cleanup. Per entity in a decomposition: new service read path (from CDC) -> new service write authority -> remove source reads -> remove source writes -> remove sync infrastructure. State the consistency guarantee at each step.

**Calendar-critical systems.** For mandatory processing windows (payroll, month-end close, regulatory deadlines), identify blackout periods explicitly and schedule risky phases between them with at least a 3-business-day pre-blackout freeze.

**Frozen external contracts.** Regulatory or contractual notice periods: preserve the legacy protocol behind a facade at the routing layer and freeze it until the notice period ends. The implementation may migrate behind the facade earlier; only the contract cutover is pinned.

### 5. Phasing and Cutover

The core of the plan.

Use skill: `strangler-fig-pattern` for incremental migration and coexistence [not Schema].
Use skill: `review-blast-radius` to assess per-phase risk.
Use skill: `dependency-impact-analysis` for ordering across components and services.
Use skill: `ops-release-safety` for rollout and deploy ordering.
Use skill: `ops-feature-flags` for traffic routing and consumer cutover.

Prerequisite work (CI/CD, routing layer, event infrastructure, test harness, verification tooling) is **Phase 0**, carried in the summary table with the unit named Foundation and inapplicable fields marked N/A.

Per phase, the Output template fixes the fields. Every phase needs a rollback path and a concrete verification that must pass before the next begins - vague validation ("verify it worked") is not acceptable on a high-risk phase. A phase may move a group of units together when they share a transaction boundary; name the group in the phase header.

When summed phase durations exceed a stated horizon, say so and re-scope: cut scope or parallelize independent phases - never compress verification or bake time. Concurrent phases keep their numbers and name each other in the Phase Summary's Key Dependency column ("parallel with Phase N").

**Consumer migration [not Schema].** Per affected consumer: strategy, deprecation timeline, coordination. Facade (old APIs preserved, routed internally - lowest disruption), versioned (new API alongside old with a deprecation window), or direct (consumers update - only safe with few consumers and coordinated deploys). For Schema, the equivalent is multi-service deploy ordering: non-app consumers (ETL jobs, BI dashboards, replication slots) need rows too - their "deploy" is a query or config update.

**Rollback.** Designed before the migration runs, per phase: what rollback requires (schema/data/code), data safety (rows that cannot be un-written without loss), time estimate, and trigger condition. Flag any phase whose rollback needs a backup restore - that is a go/no-go decision point. Undoing a merge or a completed backfill is materially harder than undoing a split or an additive change; say so where it applies.

### 6. Risk Analysis

Use skill: `ops-failure-classification` for failure categorization.
Use skill: `failure-propagation-analysis` for cascading failure assessment.
Use skill: `ops-resiliency` for mitigation patterns.

Per high-risk scenario: blast radius (Narrow / Moderate / Wide / Critical), mitigation, rollback. Cover the risks your shape actually carries:

- **Decompose:** distributed transactions where atomicity was free, latency amplification (in-process -> network), dual-write conflicts during transition, partial-extraction smell (service exists but the source still couples to it), operational overhead, team cognitive load
- **Consolidate:** blast-radius increase (one failure now affects more capabilities), scaling mismatch across merged sub-capabilities, newly coupled deploys, data migration loss, rollback cost, ownership ambiguity
- **Modernize:** behavioral divergence, second-system effect, migration fatigue on multi-year efforts, knowledge loss as legacy experts leave, coexistence cost, sunk-cost trap, scope creep (rewrite plus new features doubles risk)
- **Schema:** lock contention on hot tables, backfill overrunning its window, replica or CDC lag, rollback requiring restore, mixed app versions reading a half-migrated shape

### 7. Verification and Governance

Use skill: `ops-observability` for monitoring patterns.
Use skill: `ops-engineering-governance` for process guardrails [not Schema].

A migration dashboard tracks per phase: comparison metrics between old and new paths (latency, error rate, data divergence), traces spanning both, automated reconciliation for data drift, and measurable per-phase success criteria.

Behavioral verification is the gate for Modernize - shadow traffic, replay, or diff testing; matching the source system is what promotes a phase. For other shapes, name the concrete signal that proves the phase succeeded.

Governance: decision gates with an approver by role (EM, Staff, platform lead - not by individual), specific rollback triggers, feature flags for traffic routing, and cleanup discipline - removing dead source code and sync infrastructure post-migration, since tech debt is otherwise the predictable outcome. For Schema, gates sit at the expand -> migrate -> contract transitions, flags govern the read-path flip, and cleanup is the Contract phase.

## Review Mode

When reviewing a migration plan authored by someone else:

Use skill: `architecture-review-lens` for severity taxonomy, completeness audit, internal-consistency check, assumptions audit, criteria scoring, questions for the author, and verdict.

Depth levels apply to authoring only; reviews run the full lens (standalone formatting defaults; the lens's skip rule covers steps that do not fit). This skill's planning content - the smell table, cadence gate, extraction-order criteria, classification and lock tables, backfill discipline - is valid review evidence; cite it as the bar the plan must meet. Mark structurally inapplicable factors N/A with one line; N/A is not Missing.

Supply the factor list for the plan's shape to the completeness audit. Required = Blocker-eligible when Missing; advisory (No) factors cap at Major. State the plan's shape on the review's context line. The driver validation gate applies in review: a driver that fails it makes the Migration driver factor Present-but-wrong at Blocker, and the verdict names the cheaper remedy; a genuine driver stated without cheaper-remedy validation is under-specified at Major. A DB-engine change embedded in a Modernize plan is audited under the Modernize data-migration factor, with the Schema quality checks applied to its cutover steps.

**All shapes:**

| Factor                   | Required | What "Present" Looks Like                                                    |
| ------------------------ | -------- | ---------------------------------------------------------------------------- |
| Current state assessment | No       | Inventory, deploy/operational profile, pain points justifying the migration  |
| Migration driver         | Yes      | Specific and validated against cheaper same-shape remedies; not "it's old"   |
| Phasing                  | Yes      | Sequenced with risk-ordered rationale, not "then we migrate"                 |
| Per-phase rollback       | Yes      | Each phase has a rollback path; irreversible steps flagged explicitly        |
| Per-phase verification   | Yes      | Concrete, checkable criterion gating promotion to the next phase             |
| Risks and mitigations    | No       | Shape-appropriate risks with mitigations, not generic caution                |

**Decompose adds:** domain decomposition with per-service data ownership (Yes); target services named with responsibility and failure mode (Yes); strangler-fig coexistence and traffic routing (Yes); data ownership transfer per service (Yes); cross-cutting concerns - auth, observability, pipeline (No); governance (No).

**Consolidate adds:** over-split detection with specific signals (Yes); merge candidates with bounded-context rationale (Yes); post-merge boundaries and data ownership (Yes); data reunification including FK reintroduction and backfill (Yes); consumer migration or compatibility window per consumer (Yes); backward compatibility during transition (No).

**Modernize adds:** target stack named with rationale (Yes); behavioral inventory and how it is captured (Yes); behavioral verification - shadow, replay, diff (Yes); data migration with schema mapping and dual-run consistency (Yes); phased cutover with rollback gates, not a one-shot swap (Yes); team transition (No); scope discipline - explicit non-goals (No).

**Schema adds:** change classification per sub-change (Yes); lock risk per operation with duration and alternative (Yes); expand-contract for non-additive changes or explicit justification for skipping (Yes); application backward compatibility with old and new shape (Yes); batched idempotent backfill when rows need updating (Yes*); backup-restore dependency flagged as go/no-go (No); multi-service and non-app-consumer coordination (No).

*Required only when existing rows need updating.

Quality checks beyond the standard lens - a check's preset severity overrides the advisory cap:

- **Big-bang cutover** (code and data in one deploy, or a one-shot swap): Blocker for any system serving real users
- **Shared database across services in steady state** (Decompose): Blocker unless an explicit transitional phase
- **Distributed transactions assumed to behave like local ones** (Decompose): Blocker
- **Merge target without bounded-context rationale** (Consolidate): Major; ignoring bounded contexts recreates the original problem
- **Endpoints unified but data left sharded across old service DBs** (Consolidate): Major; partial consolidation is often worse than none
- **No consumer migration plan** (Consolidate/Decompose/Modernize): Blocker when consumers are external or cross-team
- **Rewrite without behavioral inventory** (Modernize): Blocker; rewrites without behavioral capture fail to match
- **"Modernize and add features" combined scope** (Modernize): Major minimum; usually doubles timeline and risk
- **Target stack justified only as "modern"** (Modernize): Major
- **Unbounded UPDATE/DELETE on production** (Schema): Blocker; never acceptable
- **NOT NULL, FK, or unique constraint added without backfill or validation** (Schema): Blocker
- **Expand-contract skipped on a non-additive change with no downtime authorization** (Schema): Blocker
- **Rollback requires backup restore but is not flagged go/no-go**: Major minimum, often Blocker
- **No cleanup plan for dead source code post-migration**: Major; tech debt is the predictable outcome. Retiring the whole system passes only when the plan names the decommission step and its trigger; a standby window of any length is not a decommission step
- **Vague verification ("confirm it worked")**: Minor; promote to Major on a Blocker-risk phase

A check fires when its substance is met even if wording differs - a big-bang code merge with a deferred data merge still fires the big-bang check, and a compound schema change that is non-additive in aggregate is not "single phase additive" because each sub-change looks additive alone. Concretely stated but wrong content promotes severity; vagueness does not excuse it. A plan that concretely commits to the opposite of a factor's bar is Present-but-wrong, not Missing - Missing means the plan is silent on it. Record each hit once, in the lens step that owns it (Missing factor -> Completeness; internal contradiction -> Internal Consistency; Present-but-wrong or under-specified -> Per-Factor Findings), numbered with the lens's F-numbers.

Output header: `# Migration Plan Review` and use the output structure defined in `architecture-review-lens`. Skip the plan Output template below. In this mode the Review Self-Check replaces the authoring Self-Check (self-checks are applied internally, never emitted in the deliverable):

- [ ] All factors audited for the plan's shape with Required marking applied; verdict driven by highest severity
- [ ] Quality-check hits recorded once in the correct lens step and numbered
- [ ] Every finding cites a plan section; non-Approve verdict lists required changes

## Output

```markdown
# Migration Plan: {Shape} - {system or change}

Shape: {Decompose | Consolidate | Modernize | Schema}

Scope: {what this plan covers; any deferred second shape}

Assumptions: {stated assumptions from partial inputs}

## 1. Current State

Overview:

Deployment Profile: {frequency, duration, rollback rate; Schema: the deployment model (single service, multi-service, rolling, blue-green) instead}

Pain Points:

### Inventory
<!-- Decompose: modules + coupling. Consolidate: services + consumers + team.
     Modernize: capabilities + test coverage. Schema: tables, row counts, engine/version. -->

| Unit | Responsibility | Data Owned | Depends On | Notes |
| ---- | -------------- | ---------- | ---------- | ----- |

### Landscape  <!-- multi-system migrations only; omit otherwise -->

| From (initiator) | To | Protocol | Coupling | Confidence | Notes |
| ---------------- | -- | -------- | -------- | ---------- | ----- |
|  |  | sync call / async event / batch / direct DB | Tight/Loose | Confirmed/Inferred |  |

| Cross-System Risk | Category | Affected Systems | Severity | Evidence |
| ----------------- | -------- | ---------------- | -------- | -------- |
|  | SPOF / Shared data / Missing capability | | High/Med/Low | |

Knowledge gaps: {unknown or unverifiable facts: what each blocks + discovery task (method, owner) - omit if none}

## 2. Boundary Analysis  <!-- omit for Schema -->

| Boundary | Owned Entities | Dependencies (in/out) | Data Pattern | Notes |
| -------- | -------------- | --------------------- | ------------ | ----- |

Shared-kernel entities:

Cross-boundary events:

## 3. {Decomposition | Consolidation | Modernization | Schema Change}

<!-- Decompose: target service inventory (service, responsibility, data owned, owning
     team, communication, consistency) + cadence-gate result + extraction order.
     Consolidate: smells detected (smell, services, evidence, recommendation) + merge map
     (group, services merging, resulting service, justification) + services staying separate.
     Modernize: target stack decision (chosen, alternatives, reason, trade-off, risk) +
     behavioral inventory + team transition.
     Schema: classification (type, risk, strategy, backfill required, multi-service) +
     lock risk per operation (step, operation, lock type, duration, alternative). -->

## 4. Data Ownership Transfer  <!-- omit for Schema -->

### {Unit or entity group}

| Aspect                | Detail                              |
| --------------------- | ----------------------------------- |
| Current location      |                                     |
| Target location       |                                     |
| Migration strategy    | CDC / dual-write / schema merge / batch |
| Transition period     |                                     |
| Consistency guarantee |                                     |
| Reconciliation        |                                     |

## 5. Phases

### Phase 0: Foundation  <!-- when prerequisite work exists -->

What: {CI/CD, routing layer, event infrastructure, test harness}

Verification: {what proves the foundation is ready}

Rollback: N/A

Duration:

### Phase {N}: {unit or group}

What:

Prerequisites:

Data strategy: {how ownership or shape moves}

Coexistence: {how old and new run together; routing}

Verification: {concrete criterion gating the next phase}

Rollback: {revert path; note if a backup restore is required}

Duration:

<!-- Schema phases are Expand / Migrate / Contract, each with a step table:
     | Step | Action | Pre-condition | Lock Risk | Rollback | Validation |
     A compound change runs one Expand/Migrate/Contract cycle per sub-change in
     dependency order, each cycle's Expand, Migrate, and Contract numbered as
     separate phases; combine cycles only when steps share a deploy or lock window.
     Insert additional deploy phases and renumber as needed; a purely additive
     change emits one phase. -->

### Phase Summary

| Phase | Unit | Risk Level | Duration | Key Dependency |
| ----- | ---- | ---------- | -------- | -------------- |

### Consumer Migration  <!-- Schema: multi-service + non-app consumer ordering -->

| Consumer | Current | Target | Strategy | Timeline |
| -------- | ------- | ------ | -------- | -------- |

### Rollback Summary

| Phase | Rollback Action | Data Safety | Time Estimate | Trigger |
| ----- | --------------- | ----------- | ------------- | ------- |

Phases requiring backup restore to roll back: {list, or "none"}

## 6. Risks and Mitigations

| Risk | Blast Radius | Mitigation | Rollback |
| ---- | ------------ | ---------- | -------- |
|      | Narrow/Moderate/Wide/Critical | | |

## 7. Verification and Governance

### Migration Dashboard

| Signal | Threshold | Source | Action When Breached |
| ------ | --------- | ------ | -------------------- |

### Phase Success Criteria

| Phase | Criterion | Measurement | Target |
| ----- | --------- | ----------- | ------ |

Decision Gates: {approver by role}

Rollback Triggers:

Feature Flags:

Cleanup Plan:

## Failure Simulation (deep only)

{Highest-risk phase walked end to end: cause -> propagation -> user impact ->
 mitigation -> recovery.}

**Blast radius:** {Narrow | Moderate | Wide | Critical}

**MTTR estimate:**

**Gap identified:**

## Staff-Level Summary

- Feasibility: {Recommended = driver passes, no gate outstanding | Conditional = driver passes, a named prerequisite gate must clear first | Not recommended = driver fails}
- {Shape-specific headline: services before -> after; target stack; change type and risk}
- Estimated duration: {weeks or quarters; match the Phase Summary}
- Highest-risk phase: {which and why}
- Key prerequisite: {what must happen before the migration starts}
```

## Self-Check

- [ ] Shape stated; sections produced match the shape and depth (Schema omits 2 and 4)
- [ ] Driver validated against cheaper same-shape remedies; a failed driver produced the Not-recommended deliverable, not hypothetical phases
- [ ] Boundaries follow domain ownership; one owner per entity in steady state (not Schema)
- [ ] Shape section complete: cadence gate and extraction order (Decompose) / smells and merge map (Consolidate) / target-stack rationale and behavioral inventory (Modernize) / classification, lock risk, expand-contract and backfill discipline (Schema)
- [ ] Data ownership transfer has an explicit per-unit strategy with consistency guarantee (not Schema)
- [ ] Every phase has a rollback path and a concrete verification gating the next; backup-restore phases flagged
- [ ] Consumer migration or multi-service deploy ordering addressed
- [ ] Shape-appropriate risks carry blast radius and mitigation
- [ ] Verification signals and per-phase success criteria named; cleanup planned
- [ ] If depth = deep: dependency deep-dive and failure simulation present

## Avoid

- Migrating without validating the driver - the cheaper same-shape remedy is often correct
- Drawing boundaries by code package instead of domain ownership
- Moving the hardest, most-coupled unit first
- Treating a merge or a completed backfill as easily reversible
- Assuming the new system is better until proven by traffic
- Treating "add a column" as trivially safe - NOT NULL, DEFAULT, and constraint adds are not
- Generic advice ("use microservices", "add caching") without context-specific reasoning
