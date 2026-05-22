---
name: task-go-review
description: Go / Gin / GORM / sqlx code review: goroutine leaks, context propagation, N+1, auth, validation; spawns perf/security/observability subagents.
agent: go-tech-lead
metadata:
  category: backend
  tags: [go, gin, gorm, sqlx, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.
>
> **Spec-aware mode:** If `--spec <slug>` or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles`. Cross-check every changed surface against `spec.md` / `plan.md`: each change must trace to an AC, NFR, or task; out-of-scope changes are **blockers**; missing in-scope coverage is a gap. Never edit spec artifacts.

# Go Code Review

Staff-level Go/Gin/GORM/sqlx code review umbrella. Covers correctness, architecture, AI-quality, and maintainability. Coordinates perf / security / observability subagents in parallel for extra scopes. Runs standalone with full PR/branch resolution.

## When to Use

- Pre-merge review on a Go/Gin PR
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:**
- Pre-implementation design (`task-go-implement`)
- Production incident (`/task-oncall-start`)
- Single-error debug (`task-go-debug`)
- New-system architecture (`task-design-architecture`)
- Single-scope reviews - delegate to `task-go-review-perf` / `-security` / `-observability`

## Depth Levels

| Depth | When | Runs |
|-------|------|------|
| `quick` | Time-constrained risk snapshot | Risk snapshot + top 3 findings (Phase A + B summary) |
| `standard` | Default | Phases A-E |
| `deep` | Architecture PRs, post-incident, Principal sign-off | A-E + historical pattern matching + cross-PR context |

**Auto-promote to `deep`:** After Phase A, if `Blast Radius` is Wide or Critical and the user did not pass `quick`, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E (Go-flavored) |
| + Perf | Core + `task-go-review-perf` subagent |
| + Security | Core + `task-go-review-security` subagent |
| + Observability | Core + `task-go-review-observability` subagent |
| Full | Core + all three subagents in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals (Go-tuned):**

- **+Security:** file uploads (`c.FormFile`), JWT / auth changes, `ShouldBindJSON` DTO changes, raw SQL via `fmt.Sprintf` / `db.Raw` with interpolation, secrets in env / config, Asynq / Kafka consuming user input, `mapstructure.Decode(req.Body, target)`
- **+Perf:** new migration file, new GORM query (`Find` / `First` / `Preload` / `Joins`), new pagination, new endpoints with payloads, loops calling DB or HTTP, new cache reads, new goroutines / `errgroup` fan-out
- **+Observability:** new service / package, new external client, new Asynq / Kafka producer / consumer, logging config change, new `prometheus` registration, new `pprof`, lifecycle changes
- **2+ categories → Full**

## Invocation

| Form | Meaning |
|------|---------|
| `/task-go-review` | Current branch vs base; fails fast on trunk |
| `/task-go-review <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-go-review pr-<N>` | PR head fetched into local branch `pr-<N>` (user runs the fetch) |

Pass `--base <branch>` when the PR was opened against a non-trunk base.

**No checkout required.** The workflow reads via ref-qualified diffs; never modifies the working tree.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as a subagent.

### Step 2 - Confirm Stack and Detect Data Access

Use skill: `stack-detect`. Accept pre-detected stack from parent if applicable. If not Go, stop and recommend `/task-code-review`.

Detect data access: GORM (`gorm.io/gorm`), sqlx (`github.com/jmoiron/sqlx`), raw `database/sql`, mixed. Detect messaging: Asynq, Kafka, none. Record `Data Access` and `Messaging` for branching in later phases.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Forward `--base` if passed. If it fails fast, surface verbatim and stop.

Once approved, read once and reuse:

- `git diff <base>...<head>`
- `git diff --name-status <base>...<head>`
- `git log --oneline <base>..<head>`

**Skip entirely** when invoked as a subagent and the parent passed the handle plus pre-read artifacts.

### Step 4 - Evaluate Scope Auto-Escalation

Scan the file list and diff for the signals listed under **Scope**. Log each fire as `signal: <category> -> <file:line>`. Then:

- Zero signals or `core-only` → stay Core
- One signal category → add matching extra scope
- 2+ categories → promote to Full
- User passed an explicit scope → respect it; still log signals so the Summary documents why

Surface the decision in Summary; if escalated, append `auto-escalated from Core; signals: <list>`.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk signals
- Use skill: `review-blast-radius` for failure propagation scope

Output risk level and blast radius before any findings.

**Low-risk short-circuit:** if Risk Level is Low, Blast Radius is Narrow, **and** the change does not touch architecture-relevant files (auth middleware, JWT, router groups, shared interfaces, `cmd/api/main.go`, migrations), skip Phases C-D and produce a streamlined output with Phase B only.

### Step 4.5 - Re-evaluate Depth After Phase A

If Blast Radius is Wide / Critical and user did not pass `quick`, set depth to `deep` and surface promotion in Summary **before** Phases B-E.

### Phase B - Go Correctness and Safety

Apply atomic skills. Each owns the canonical patterns; this phase flags deviations and surfaces what they did not see:

- Use skill: `go-error-handling` - wrapping with `%w`, sentinels, `errors.Is` / `errors.As`, no log-and-return
- Use skill: `go-concurrency` - goroutine ownership, `<-ctx.Done()` arms, `errgroup` for required ops, `sync.Mutex` not held across I/O
- Use skill: `go-data-access` - `WithContext(ctx)`, `defer rows.Close()`, `Preload` / `Joins`, transaction boundaries, post-commit dispatch
- Use skill: `go-gin-patterns` - `ShouldBindJSON` (not `BindJSON`), validator tags, response DTO mapping (no raw GORM model in `c.JSON`)
- Use skill: `go-messaging-patterns` if diff touches Asynq / Kafka
- Use skill: `go-migration-safety` if diff touches `migrations/`. Also use skill: `ops-backward-compatibility` for client/in-flight impact

**Additional Go-specific checks the atomics don't own:**

- **Test coverage finding (named, not buried).** PR adds logic without `*_test.go`? At minimum `[Suggestion]`; escalate to `[High]` when the change is critical path: auth, ownership / role checks, money / billing, multi-table writes, state machines, Asynq / Kafka mutators, migrations changing column semantics. Surface as a dedicated finding.
- **Authorization + IDOR.** JWT middleware proves authentication, not object access. Every per-owner endpoint must scope queries by principal: `db.Where("id = ? AND user_id = ?", id, claims.UserID)`.
- **Response DTO field hygiene.** Compare the response DTO's `json:` fields against the model. Flag any of `PasswordHash` / `MFASecret` / `RecoveryCodes` / `APIKey` / `WebhookSecret` / `InternalNotes` / `AuditLog` / `IsAdmin` / `Role` / `DeletedAt` / `LastLoginIP` on the wire. Raw `c.JSON(200, *model.User)` with no DTO is `[High]` regardless of current fields - adding a sensitive column later silently exposes it.
- **HTTP `Idempotency-Key` on retry-prone POSTs.** `/payments`, `/orders`, `/refunds`, `/subscriptions`, `/webhooks` accept an `Idempotency-Key` header and dedupe via a `request_idempotency` table. Distinct from worker-side `asynq.TaskID` - the HTTP key protects the client→server boundary.
- **Go quirks at boundaries.** `net.JoinHostPort` (not `fmt.Sprintf("%s:%d", ...)`); `time.Now().UTC()` for stored timestamps; `slog` (not `fmt.Println` / `log.Printf`).
- **Multi-replica race safety.** Counters / balances / state transitions use DB locking (`db.Clauses(clause.Locking{Strength: "UPDATE"})` or optimistic versioning), not in-process `sync.Mutex` (only protects one replica).
- **HTTP client sharing.** `http.Client` / `resty.Client` shared at package level. Per-request `&http.Client{}` breaks connection reuse.
- **`go test -race`** clean in CI. Races at test time are confirmed bugs.

### Phase C - Go Architecture Guardrails

Use skill: `architecture-guardrail` for layer violations and coupling.

**Go-specific:**

- **Layering**: `handler` → `service` → `repository` → `model`. Handlers parse / delegate / respond; services hold rules (no `gin.Context`, no GORM); repositories return domain types; `cmd/api/main.go` wires constructors
- **Interfaces at the consumer**: the `service` package declares the interface it needs; the `repository` package returns the concrete struct
- **Constructor injection, no `init()` / globals**: package-level `*gorm.DB` vars are a smell
- **`internal/` for non-exported code; `pkg/` for libraries**
- **Settings discipline**: typed config struct loaded once at startup; no `os.Getenv("X")` scattered across files
- **Feature-package layout** preferred over layer-package; cross-feature imports go through public service interfaces
- **Multi-tenant isolation** enforced at the repository layer (GORM scope or sqlx wrapper), not at routes alone
- **Gin middleware order**: `recovery → logging → request-id → CORS → auth → rate-limit → handler`. Auth applied at group level, not per-route
- **GORM hooks for genuine cross-cutting** (audit, search-index sync) - not as hidden control flow for emails / Asynq dispatch
- **Error-handling middleware**: `c.Error(err)` flows to centralized middleware mapping sentinels → HTTP status; per-handler `c.JSON(500, gin.H{...})` scattered is `[Suggestion]`
- **Anemic domain (deep depth only)**: business rules accumulating in services while models stay pure data - flag for `task-go-refactor`. Do not raise on a single PR's evidence alone

**Multi-service PRs:**

- API contract compatibility (OpenAPI diff, Pact)
- Deployment order documented or independent
- Use skill: `ops-backward-compatibility`

### Phase D - AI-Generated Code Quality

- Use skill: `complexity-review` for verbosity, over-engineering, simplification
- Use skill: `go-overengineering-review` for binding/service guards vs GORM/DB constraints, defensive nil after non-nil constructors, silent error swallows, single-impl interfaces at the implementation side, `BaseRepository` embedding, speculative config, `Result[T]` over `(T, error)`, naked `go fn()` wrapping sequential calls

**Additional Go AI smells:**

- Redundant mapping layers (`Model → InternalDTO → ServiceDTO → ResponseDTO` when one would do)
- Test verbosity (setup helpers > 30 lines for one assertion; full deep-equal when a few fields would do)
- DTO noise (identical DTOs reimplemented per endpoint; gratuitous `json:"...,omitempty"`)
- Comment cruft (restating function names, end-of-function markers, godoc on private helpers repeating the signature)
- `interface{}` / `any` proliferation (generics replace most legitimate uses; `any` to silence a type bug is a finding)

### Phase E - Maintainability and Clarity

Use skill: `backend-coding-standards` for cross-language naming. Use skill: `ops-observability` for cross-cutting logging/metrics presence (depth belongs to `task-go-review-observability`).

**Go-specific:**

- **Naming**: lowercase package names, no stutter (`user.UserService` → `user.Service`); exported types have doc comments starting with the type name; no `Util` / `Manager` / `Helper` packages
- **Magic numbers / strings**: extracted to `const`
- **Hardcoded URLs / credentials**: env / config struct, not inline
- **Function length**: > 30 lines extracted; > 60 lines unless clearly orchestrating
- **Duplicated query logic**: same `WHERE` in 3+ places extracted to a method or GORM scope
- **Logging hygiene**: surface `fmt.Println` / `log.Printf` in prod paths, lines without correlation IDs, wrong levels (depth in observability subagent)
- **`gofmt` / `goimports` clean**; `golangci-lint` / `staticcheck` clean
- **Godoc on exported APIs**; `swaggo/swag` annotations when the project uses them

### Step 5 - Delegate Extra Scopes in Parallel

If scope is **Core only**, skip.

For each extra scope, spawn an independent subagent **in parallel** with the main thread:

| Scope | Subagents |
|-------|-----------|
| + Perf | `task-go-review-perf` |
| + Security | `task-go-review-security` |
| + Observability | `task-go-review-observability` |
| Full | All three in parallel |

**Subagent prompt contract** - each must include:

- The resolved review target (`base_ref`, `head_ref`) plus the pre-read diff and commit log (no re-running git)
- The depth level
- Pre-confirmed stack (Go / Gin) + detected data-access mix
- Instruction to return findings in its own Output Format

**Failure isolation:** if a subagent fails or times out, continue with the rest. Note the missing scope in Summary.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate** cross-cutting findings (one entry citing all scopes that raised it)
- **Highest severity wins** (`Blocker` > `High` > `Suggestion` > `Question`)
- **Preserve `file:line` citations**
- **Order by severity**, not by scope
- **Note missing scopes** in Summary as `Scope incomplete: <scope>`
- **Merge Next Steps** with `[Implement]` / `[Delegate]` tags preserved; re-sort by severity

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review`. Write before ending; print the confirmation line.

## Feedback Labels

| Label | Meaning | Required |
|-------|---------|----------|
| [Blocker] | Must fix before merge - correctness / risk | Yes |
| [High] | Should fix - significant impact | Strong |
| [Suggestion] | Would improve - non-blocking | No |
| [Question] | Need clarity from author | Clarify |

No `[Nitpick]` or `[Praise]`.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Go <version> / Gin <version>
**Data Access:** GORM | sqlx | database/sql | mixed
**Messaging:** Asynq | Kafka | none
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line

- Issue: [name the Go idiom: unchecked `error`, goroutine without cancellation, missing `defer rows.Close()`, N+1 via per-iteration query, raw SQL `fmt.Sprintf`, missing JWT middleware, ORM model in `c.JSON`, `sync.Mutex` across I/O, Asynq enqueue inside transaction, etc.]
- Impact: [user-visible or operational]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete Go change with code]

### [High] file:line
- Issue: ...
- Impact: ...
- Fix: ...

### [Suggestion] file:line
- Improvement: ...

### [Question] file:line
- Question: [what is ambiguous]
- Why it matters: [what the right next step depends on]

_Use [Question] for genuine ambiguity, not as a softer Blocker._

## Architecture Notes

_Cross-cutting commentary. Do not restate individual findings; reference them by file:line._

- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

_Same rule as Architecture Notes._

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

2-4 bullets on systemic impact and what to address before merge.

## Next Steps

Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action]
2. **[Delegate]** [High] [scope: cross-service] - [one-line action]

_Omit if no actionable findings._
```

**Omit empty sections.** No Blocker heading if there are none.

## Rules

- Review whole-change system impact, not file-by-file
- Lead with risk; line-level findings follow
- Apply Go conventions (Effective Go, Code Review Comments wiki)
- Provide actionable feedback with Go code examples
- `gofmt` / `goimports` apply; do not nitpick style
- Default Core; auto-escalate; honor `core-only`
- Delegate perf / security / observability depth to subagents

## Self-Check

- [ ] `behavioral-principles` loaded (or accepted from parent)
- [ ] Stack confirmed; data-access mix and messaging recorded
- [ ] `review-precondition-check` ran (or handle received); diff/log read once and reused
- [ ] For `pr-ref` mode: fetch command surfaced; ref existed before review continued
- [ ] When `head_matches_current` was false: explicit user approval obtained
- [ ] Scope auto-escalation evaluated; promotion (or `core-only`) recorded
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`
- [ ] Risk level + blast radius stated before any finding
- [ ] Phase B: applied atomic skills; checked test coverage, authorization, response DTO hygiene, Idempotency-Key, race safety
- [ ] Phase C: layering, interface-at-consumer, constructor injection, settings discipline, multi-tenant
- [ ] Phase D: `complexity-review` + `go-overengineering-review` applied; AI smells covered
- [ ] Phase E: naming, magic numbers, function length, structured logging
- [ ] Missing tests raised as a named finding (not buried)
- [ ] Every Blocker states a system risk
- [ ] Every finding has label + `file:line` + actionable Go fix
- [ ] If `--spec` passed: every finding traces to AC/NFR/task or is flagged as out-of-scope blocker
- [ ] Extra scopes ran in parallel with the pre-resolved diff/log handle + data-access detection
- [ ] Subagent findings merged into one severity-ordered Findings list; no raw reports appended
- [ ] Failed/missing subagent scope noted as `Scope incomplete: <scope>`
- [ ] Next Steps produced with `[Implement]` / `[Delegate]` tags, ordered by severity
- [ ] Review report written via `review-report-writer`; confirmation line printed

## Avoid

- `git fetch` / `git checkout` from this workflow - user runs these
- Reviewing without reading the full diff and commit log first
- Generic backend conventions when a Go idiom exists ("define the interface in the consuming package", not "use dependency inversion")
- Nitpicking style where `gofmt` applies
- Vague feedback ("this could be better")
- Blocking on personal preference
- Running extra scopes when `core-only` was passed
- Duplicating perf / security / observability depth here when the dedicated subagent owns them
- Sequential extra scopes that could parallelize
- Appending raw subagent reports instead of merging
- Recommending `panic` in service code; return a wrapped error
- Recommending `db.AutoMigrate` for production schema
- Recommending `db.Raw(fmt.Sprintf(...))` for dynamic queries
