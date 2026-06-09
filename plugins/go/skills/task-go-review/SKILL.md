---
name: task-go-review
description: Go / Gin / GORM / sqlx code review - goroutine leaks, context propagation, N+1, auth, validation; spawns perf/security/observability subagents.
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

Staff-level Go/Gin/GORM/sqlx review umbrella. Covers correctness, architecture, AI quality, maintainability. Coordinates perf / security / observability subagents in parallel.

## When to Use

- Pre-merge review on a Go/Gin PR
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:** pre-implementation design (`task-go-implement`), production incident (`/task-oncall-start`), single-error debug (`task-go-debug`), new-system architecture (`task-design-architecture`), single-scope reviews (delegate to perf/security/observability).

## Depth

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | Phases A-E |
| `deep` | Architecture PRs, post-incident, Principal sign-off | A-E + historical patterns + cross-PR context |

**Auto-promote to `deep`:** After Phase A, if Blast Radius is Wide/Critical, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E |
| + Perf | Core + `task-go-review-perf` subagent |
| + Sec | Core + `task-go-review-security` subagent |
| + Obs | Core + `task-go-review-observability` subagent |
| Full | Core + all three in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals:**

- **+Sec:** `c.FormFile`, JWT / auth changes, `ShouldBindJSON` DTO changes, raw SQL via `fmt.Sprintf` / `db.Raw`, secrets in config, Asynq / Kafka consuming user input, `mapstructure.Decode(req.Body, target)`, client-controlled price / amount / currency / discount fields on payment-adjacent endpoints (`/orders`, `/refunds`, `/checkout`)
- **+Perf:** new migration, new GORM query statement (`Find` / `First` / `Preload` / `Joins` - new DB roundtrip, not a modifier like `Order` / `Limit` added to an existing query), new pagination, new endpoints with payloads, loops calling DB or HTTP, new cache reads, new goroutines / `errgroup`
- **+Obs:** new service / package, new external client, new Asynq / Kafka producer / consumer, logging config change, `prometheus` registration, `pprof`, lifecycle changes
- **2+ categories -> Full**

## Invocation

| Form | Meaning |
|------|---------|
| `/task-go-review` | Current branch vs base; fails fast on trunk |
| `/task-go-review <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-go-review pr-<N>` | PR head fetched into local branch `pr-<N>` (user runs fetch) |

Pass `--base <branch>` when the PR was opened against a non-trunk base.

**No checkout required.** Read via ref-qualified diffs; never modify the working tree.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as subagent.

### Step 2 - Stack and Data Access

Use skill: `stack-detect`. Accept pre-detected stack from parent. If not Go, stop and recommend `/task-code-review`.

Detect data access (GORM / sqlx / database/sql / mixed) and messaging (Asynq / Kafka / none). Record both.

### Step 3 - Resolve Diff

Use skill: `review-precondition-check`. Forward `--base` if passed. If it fails fast, surface verbatim and stop.

The handle may include a `prior_checkpoint` block (a prior `review-<branch>.md` exists). Decision logic is Step 3.5; for now, just hold onto it.

Read once and reuse:

- `git diff <base>...<head>`
- `git diff --name-status <base>...<head>`
- `git log --oneline <base>..<head>`

**Skip entirely** when invoked as subagent and parent passed handle + pre-read artifacts.

Also capture the current SHAs for the report's checkpoint frontmatter:

- `current_head_sha = git rev-parse <head_ref>`
- `current_base_sha = git rev-parse <base_ref>`

### Step 3.5 - Decide Mode (re-review auto-detect)

Skip if the handle has no `prior_checkpoint` -> `mode = full`, `round = 1`, no fetch, no reconciliation. Continue to Step 4.

If `prior_checkpoint: legacy` (file present, frontmatter missing/invalid) -> `mode = full`, `round = 1`. Note in Summary: `Prior report lacks checkpoint metadata - treated as round 1.` Continue to Step 4.

Otherwise (valid prior checkpoint present):

**Step 3.5a - Auto-fetch the head branch.** Only when a valid prior checkpoint exists, refresh the local tracking ref so a script can re-run the same command without manually fetching:

```bash
upstream=$(git rev-parse --abbrev-ref --symbolic-full-name "<head_ref>@{u}" 2>/dev/null)
```

If `upstream` resolves to `<remote>/<branch>` form, split and run:

```bash
git fetch <remote> <branch>
```

No checkout, no merge. If `upstream` does not resolve (pr-ref with no upstream, detached HEAD, no remote configured), skip the fetch silently. If `git fetch` fails (offline, auth, deleted remote branch), continue silently - this is a convenience, not a gate. After a successful fetch, re-resolve `current_head_sha = git rev-parse <head_ref>`.

**Step 3.5b - Compare checkpoints.**

| Condition                                                              | Decision                                                                                                                            |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `prior_checkpoint.head_sha == current_head_sha`                        | **No-op.** Print `No new commits on <head_ref_short> since prior review at <sha_short>. Prior report unchanged.` (where `<head_ref_short>` is the short name of `head_ref` - the review target, not the user's current branch - and `<sha_short>` is the first 7 chars of `current_head_sha`) and stop. Do not call `review-report-writer`. |
| `git merge-base --is-ancestor <prior_head_sha> <current_head_sha>` fails (prior SHA unreachable) | `mode = full`, `round = prior.round + 1`. Note in Summary: `Prior checkpoint unreachable - history rewritten; full re-review.`      |
| `prior_checkpoint.base_sha != current_base_sha`                        | `mode = full`, `round = prior.round + 1`. Note in Summary: `Base branch advanced since round <prior.round> - full re-review.`       |
| `prior_checkpoint.base_ref != base_ref`                                | `mode = full`, `round = prior.round + 1`. Note in Summary: `Base ref changed since round <prior.round> - full re-review.`           |
| None of the above                                                       | `mode = incremental`, `round = prior.round + 1`, `incremental_range = <prior_head_sha>...<current_head_sha>`.                       |

**Step 3.5c - Incremental: re-read the diff scoped to the new range.**

If `mode = incremental`, replace the diff read from Step 3 with:

- `git diff <prior_head_sha>...<current_head_sha>`
- `git diff --name-status <prior_head_sha>...<current_head_sha>`
- `git log --oneline <prior_head_sha>..<current_head_sha>`

The full-range diff from Step 3 is discarded; all Phase A-E analysis operates on the incremental range only.

**Step 3.5d - Scope expansion handling.**

If the user's invocation expanded scope vs. the prior round (e.g., round 1 was `core-only`, round 2 is `full`), the newly-added scopes have no prior findings to reconcile. Record in Summary based on mode:

- `mode = incremental`: `Scope expanded round <N>: +<list> - new scopes reviewed in full; previously-reviewed scopes reviewed incrementally.`
- `mode = full`: `Scope expanded round <N>: +<list>.` (the incremental clause does not apply)

The reconciliation table (when emitted) only covers findings whose scope was active in the prior round.

### Step 4 - Scope Auto-Escalation

Scan file list / diff for signals listed under **Scope**. Log each as `signal: <category> -> <file:line>`. Then:

- Zero signals or `core-only` -> Core
- One category -> add matching scope
- 2+ categories -> Full
- Explicit scope -> respect; still log signals

**Scope precedence on round 2+:** user flag > firing signals > inherit from `prior_checkpoint.scope`. If the user passed no flag and the diff (incremental, in incremental mode) fires no signals, inherit the prior round's scope so reviewer coverage does not silently narrow. Surface as `Scope: <inherited> (inherited from round <prior.round>)`.

Surface decision in Summary; if escalated, append `auto-escalated from Core; signals: <list>`.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk
- Use skill: `review-blast-radius` for failure propagation

Output risk level + blast radius before any findings.

**Low-risk short-circuit:** if Risk is Low, Blast Radius is Narrow, **and** change does not touch architecture-relevant files (auth middleware, JWT, router groups, shared interfaces, `cmd/api/main.go`, migrations), skip Phases C-D and produce a streamlined output with Phase B only.

### Step 4.5 - Re-evaluate Depth After Phase A

If Blast Radius is Wide / Critical, set depth to `deep` and surface promotion in Summary **before** Phases B-E.

### Phase B - Go Correctness and Safety

Apply atomic skills; each owns canonical patterns:

- Use skill: `go-error-handling` - `%w` wrapping, sentinels, `errors.Is/As`, no log-and-return
- Use skill: `go-concurrency` - goroutine ownership, `<-ctx.Done()` arms, `errgroup` for required ops, `sync.Mutex` not across I/O
- Use skill: `go-data-access` - `WithContext`, `defer rows.Close()`, `Preload` / `Joins`, transaction boundaries, post-commit dispatch
- Use skill: `go-gin-patterns` - `ShouldBindJSON` (not `BindJSON`), validator tags, response DTO (no raw GORM model in `c.JSON`)
- Use skill: `go-messaging-patterns` if diff touches Asynq / Kafka
- Use skill: `go-migration-safety` if diff touches `migrations/`. Use skill: `ops-backward-compatibility` for client / in-flight impact

**Additional checks (not owned by atomics):**

- **Test coverage finding (named, not buried).** PR adds logic without `*_test.go` -> `[Recommend]`; escalate to `[Must]` when critical path: auth, ownership / role checks, money / billing, multi-table writes, state machines, Asynq / Kafka mutators, migrations changing column semantics
- **Authorization + IDOR.** Every per-owner endpoint scopes queries by principal: `db.Where("id = ? AND user_id = ?", id, <principal-id>)` - where `<principal-id>` is whatever the project uses (`claims.UserID`, `claims.Sub`, `c.MustGet("user_id")`). JWT proves authn, not object access
- **Response DTO hygiene.** Compare response DTO `json:` fields against the model. Flag `PasswordHash` / `MFASecret` / `RecoveryCodes` / `APIKey` / `WebhookSecret` / `InternalNotes` / `AuditLog` / `IsAdmin` / `Role` / `DeletedAt` / `LastLoginIP` on the wire. Raw `c.JSON(200, *model.User)` is `[Recommend]` regardless of current fields (sensitive column added later silently exposes it)
- **HTTP `Idempotency-Key` on retry-prone POSTs.** `/payments`, `/orders`, `/refunds`, `/subscriptions`, `/webhooks` accept the header and dedupe via a `request_idempotency` table. Distinct from worker-side `asynq.TaskID`
- **Client-controlled money fields.** Price / amount / discount on payment-adjacent endpoints (`/orders`, `/refunds`, `/checkout`) come from the server (or a server-validated catalog), not the request DTO. Trusting `req.UnitPrice` is `[Must]`
- **Postgres FK indexes.** `REFERENCES other(id)` does not create an index on the FK column - add one explicitly in the migration. Missing FK indexes cause sequential scans on join, lock contention on cascade delete, and degrade as the parent grows
- **Go boundary quirks.** `net.JoinHostPort` (not `fmt.Sprintf("%s:%d", ...)`); `time.Now().UTC()` for stored timestamps; `slog` (not `fmt.Println` / `log.Printf`)
- **Multi-replica race safety.** Counters / balances / state transitions use DB locking (`clause.Locking{Strength: "UPDATE"}` or optimistic versioning), not in-process `sync.Mutex` (one replica only)
- **HTTP client sharing.** `http.Client` shared at package level; per-request `&http.Client{}` breaks connection reuse
- **`go test -race`** clean in CI

### Phase C - Architecture Guardrails

Use skill: `architecture-guardrail` for layer violations and coupling.

**Go-specific:**

- **Layering:** `handler` -> `service` -> `repository` -> `model`. Handlers parse / delegate / respond; services hold rules (no `gin.Context`, no GORM); repositories return domain types; `cmd/api/main.go` wires constructors
- **Interfaces at consumer.** `service` package declares the interface; `repository` returns concrete struct
- **Constructor injection, no `init()` / globals.** Package-level `*gorm.DB` vars are a smell
- **`internal/` for non-exported; `pkg/` for libraries**
- **Settings discipline:** typed config struct loaded once; no `os.Getenv("X")` scattered
- **Feature-package layout** preferred over layer-package
- **Multi-tenant isolation** at the repository layer, not routes alone
- **Gin middleware order:** `recovery -> logging -> request-id -> CORS -> auth -> rate-limit -> handler`. Auth at group level, not per-route
- **GORM hooks** for genuine cross-cutting (audit, search-index sync) - not hidden control flow for emails / Asynq dispatch
- **Error-handling middleware:** `c.Error(err)` flows to centralized middleware; per-handler `c.JSON(500, ...)` scattered is `[Recommend]`
- **Anemic domain (deep depth only):** rules in services while models stay pure data - flag for `task-go-refactor`. Don't raise on a single PR alone

**Multi-service PRs:** API contract compatibility (OpenAPI diff, Pact); deployment order documented; use skill: `ops-backward-compatibility`.

### Phase D - AI-Generated Code Quality

- Use skill: `complexity-review` for verbosity, over-engineering
- Use skill: `go-overengineering-review` for binding/service guards vs GORM/DB, defensive nil, silent swallows, single-impl interfaces at impl, `BaseRepository` embedding, speculative config, `Result[T]` vs `(T, error)`, naked `go fn()`

**Additional AI smells:**

- Redundant mapping layers (`Model -> InternalDTO -> ServiceDTO -> ResponseDTO`)
- Test verbosity (setup > 30 lines for one assertion; full deep-equal when a few fields would do)
- DTO noise (identical DTOs reimplemented per endpoint; gratuitous `json:"...,omitempty"`)
- Comment cruft (restating function names, godoc on private helpers)
- `interface{}` / `any` proliferation (generics replace most uses; `any` to silence a type bug is a finding)

### Phase E - Maintainability

Use skill: `backend-coding-standards` for cross-language naming. Use skill: `ops-observability` for cross-cutting logging/metrics presence (depth in `task-go-review-observability`).

**Go-specific:**

- Naming: lowercase package names, no stutter (`user.UserService` -> `user.Service`); exported types have doc starting with the name; no `Util` / `Manager` / `Helper` packages
- Magic numbers / strings extracted to `const`
- Hardcoded URLs / credentials in env / config struct
- Function length: > 30 lines extracted; > 60 lines unless clearly orchestrating
- Duplicated query logic: same `WHERE` in 3+ places -> method or GORM scope
- Logging hygiene: surface `fmt.Println` / `log.Printf` in prod paths; lines without correlation IDs; wrong levels
- `gofmt` / `goimports` / `golangci-lint` / `staticcheck` clean
- Godoc on exported APIs; `swaggo/swag` annotations when project uses them

### Step 5 - Delegate Extra Scopes in Parallel

If scope is **Core only**, skip.

For each extra scope, spawn an independent subagent **in parallel** with the main thread.

**Subagent prompt contract:**

- Resolved review target (`base_ref`, `head_ref`) + pre-read diff and commit log (no re-running git)
- Depth level
- Pre-confirmed stack (Go / Gin) + data-access mix
- Return findings in own Output Format

**Failure isolation:** if subagent fails or times out, continue with the rest. Note missing scope in Summary.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into single Output Format. Do not append raw reports.

- Deduplicate cross-cutting findings (one entry citing all scopes)
- **Strongest intent wins** when labels differ across subagent reports for the same finding: `Must` > `Recommend` > `Question`
- Preserve `file:line` citations
- Order by intent, not scope
- Note missing scopes as `Scope incomplete: <scope>`
- Merge Next Steps with `[Implement]` / `[Delegate]` tags; re-sort by intent

**Cross-phase same root cause.** When one defect spans multiple phases (e.g., a layering violation that also degrades testability and DTO discipline), file the finding once under the phase where the root cause sits and reference its `file:line` from `Architecture Notes` or `Maintainability Notes`. Do not double-count by listing the same `file:line` as separate findings.

### Step 6.5 - Reconcile Prior Findings (incremental mode only)

Skip if `mode = full`. Otherwise use skill: `review-prior-findings-reconcile` with:

- `prior_report`: the loaded body of `review-<branch>.md` (frontmatter excluded)
- `incremental_diff`: from Step 3.5c
- `name_status`: from Step 3.5c

The reconcile skill returns a Markdown table and a tally line. Insert the table under `## Prior Round Reconciliation` in the report (see Output Format).

Fold any `Still open` rows into `## Next Steps` as `(open since round <prior.round>)`-suffixed entries, ordered by severity alongside this round's new findings. Do not emit a standalone "Carry-Over Open Items" section.

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review` and these checkpoint fields:

- `branch`, `base_ref`, `base_sha = current_base_sha`, `head_ref`, `head_sha = current_head_sha`
- `mode` (from Step 3.5), `round` (from Step 3.5), `prior_head_sha` (omit on round 1)
- `scope` (resolved in Step 4), `depth` (resolved/auto-promoted), `stack = go-gin`

Write before ending; print confirmation.

## Feedback Labels

| Label        | Meaning                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| [Must]       | Do not merge until this is fixed.                                        |
| [Recommend]  | Fix, or push back with reasoning. Cannot be silently acked.              |
| [Question]   | Author must answer; reviewer decides if a fix follows.                   |

No `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Go <version> / Gin <version>
**Data Access:** GORM | sqlx | database/sql | mixed
**Messaging:** Asynq | Kafka | none
**Scope:** Core | +Sec | +Perf | +Obs | Full _(if auto-escalated: `auto-escalated from Core; signals: <list>`)_
**Depth:** standard | deep _(if auto-promoted: `auto-promoted from standard; Blast Radius: <level>`)_
**Round:** <N>                                _(include from round 2 onward)_
**Mode:** incremental (since <prior_head_sha_short>) | full _(include from round 2 onward)_
**Diff Range:** <range_short> (<N> commits, <M> files) _(incremental rounds only)_

## Prior Round Reconciliation _(incremental rounds only; omit otherwise)_

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |
| ...                 | ...       | ...    | ...   |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## High-Impact Findings

### [Must] file:line

- Issue: [name the Go idiom]
- Impact: [user-visible or operational]
- System Risk: [why this is system-level]
- Fix: [concrete Go change with code]

### [Recommend] file:line
- Issue, Impact, Fix

### [Question] file:line
- Question: [what is ambiguous]
- Why it matters

_Use [Question] for genuine ambiguity, not as softer Must._

## Architecture Notes

_Cross-cutting commentary. Reference findings by file:line._
- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

2-4 bullets on systemic impact.

## Next Steps

On incremental rounds, prior-round Still open items are folded in with (open since round <N>) suffix and ordered by intent alongside new findings. Each item tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Implement]** [Recommend] old_file.go:88 - N+1 in listAll (open since round 1)
3. **[Delegate]** [Recommend] [scope: cross-service] - [one-line action]

_Omit if no actionable findings._
```

**Omit empty sections.** No Must heading if there are none.

## Rules

- Review whole-change system impact, not file-by-file
- Lead with risk; line-level findings follow
- Apply Go conventions (Effective Go, Code Review Comments wiki)
- Actionable feedback with Go code
- `gofmt` / `goimports` apply; don't nitpick style
- Default Core; auto-escalate; honor `core-only`
- Delegate perf / security / observability depth to subagents

## Self-Check

- [ ] `behavioral-principles` loaded (or accepted from parent)
- [ ] Stack confirmed; data-access mix and messaging recorded
- [ ] `review-precondition-check` ran (or handle received); diff/log read once and reused; current_head_sha and current_base_sha captured
- [ ] Step 3.5 - mode decided (full / incremental / no-op); auto-fetch attempted only when prior checkpoint exists; incremental range re-read when mode flipped to incremental; no-op path exits without writing the report
- [ ] For `pr-ref` mode: fetch surfaced; ref existed before review continued
- [ ] When `head_matches_current` was false: user approval obtained
- [ ] Scope auto-escalation evaluated; promotion (or `core-only`) recorded
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical
- [ ] Risk + blast radius stated before any finding
- [ ] Phase B: atomic skills applied; test coverage, authz, response DTO, Idempotency-Key, race safety checked
- [ ] Phase C: layering, interface-at-consumer, constructor injection, settings, multi-tenant
- [ ] Phase D: `complexity-review` + `go-overengineering-review` applied
- [ ] Phase E: naming, magic numbers, function length, structured logging
- [ ] Missing tests raised as named finding (not buried)
- [ ] Every Must cites system risk
- [ ] Every finding has label + `file:line` + Go fix
- [ ] If `--spec`: every finding traces to AC/NFR/task or flagged out-of-scope
- [ ] Extra scopes ran in parallel with pre-resolved handle + data-access detection
- [ ] Subagent findings merged into one intent-ordered list; no raw reports appended
- [ ] Failed / missing subagent scope noted as `Scope incomplete: <scope>`
- [ ] Step 6.5 - on incremental rounds, review-prior-findings-reconcile ran; reconciliation table inserted; Still open rows folded into Next Steps with (open since round <N>) suffix
- [ ] Next Steps produced with `[Implement]` / `[Delegate]` tags, ordered by intent
- [ ] Review report written via `review-report-writer` with full checkpoint fields (mode, round, prior_head_sha when round > 1, head_sha, base_sha, scope, depth, stack); confirmation printed

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase). The one allowed exception is `git fetch <remote> <branch>` in Step 3.5a, and only when a valid prior checkpoint exists.
- Auto-fetching on round 1 (no prior checkpoint) - keeps first-run behavior strictly read-only.
- Running incremental analysis against the full-range diff (must re-read scoped to `<prior_head_sha>...<head_sha>`).
- Writing the report on no-op exit (prior `head_sha == current head_sha`) - the file must stay byte-identical.
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`).
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
- Emitting a "Carry-Over Open Items" section - fold into Next Steps instead.
- Reviewing without reading the full diff and commit log first
- Generic backend conventions when a Go idiom exists ("define interface in consumer", not "use DI")
- Nitpicking style where `gofmt` applies
- Vague feedback ("this could be better")
- Blocking on personal preference
- Running extra scopes when `core-only` was passed
- Duplicating perf / security / observability depth here
- Sequential extra scopes that could parallelize
- Appending raw subagent reports
- Recommending `panic` in service code
- Recommending `db.AutoMigrate` for production
- Recommending `db.Raw(fmt.Sprintf(...))`
