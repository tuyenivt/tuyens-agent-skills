---
name: task-go-review
description: Go / Gin / GORM / sqlx code review - goroutine leaks, context propagation, N+1, auth; spawns perf/security/observability/reliability subagents.
agent: go-tech-lead
metadata:
  category: backend
  tags: [go, gin, gorm, sqlx, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Go Code Review

Staff-level Go/Gin/GORM/sqlx review umbrella. Covers correctness, architecture, AI quality, maintainability. Coordinates perf / security / observability / reliability subagents in parallel.

## When to Use

- Pre-merge review on a Go/Gin PR
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:** pre-implementation design (`task-go-implement`), single-error debug, new-system architecture (`task-design-architecture`), single-scope reviews (delegate to perf/security/observability/reliability).

## Depth

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | Phases A-E |
| `deep` | Architecture PRs, post-incident, Principal sign-off | A-E + the deep-only items below |

At `deep`, three things change and nothing else does: Phase C's anemic-domain check runs; `git log` over the touched files supplies branch history for `## Key Takeaways` (state "cross-PR context unavailable" when the surrounding PRs are not readable); and deep-only sections returned by subagents are preserved per Step 6.

**Auto-promote to `deep`:** After Phase A, if Blast Radius is Wide/Critical, set depth to `deep`. Surface it in the Summary's `Depth` line using the Output Format's wording - that template is the single source for every Summary string.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E |
| + Perf | Core + `task-go-review-perf` subagent |
| + Sec | Core + `task-go-review-security` subagent |
| + Obs | Core + `task-go-review-observability` subagent |
| + Rel | Core + `task-go-review-reliability` subagent |
| Full | Core + all four in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals:**

- **+Sec:** `c.FormFile`, JWT / auth changes, `ShouldBindJSON` DTO changes, raw SQL via `fmt.Sprintf` / `db.Raw`, secrets in config, Asynq / Kafka consuming user input, `mapstructure.Decode(req.Body, target)`, client-controlled price / amount / currency / discount fields on payment-adjacent endpoints (`/orders`, `/refunds`, `/checkout`)
- **+Perf:** new migration, new query statement (GORM `Find` / `First` / `Preload` / `Joins`, sqlx `GetContext` / `SelectContext` / `NamedExec` - a new DB roundtrip, not a pure shaping modifier like `Limit` on an existing query), a **new filter or sort predicate** on an existing query (it needs an index that may not exist), new pagination, new endpoints with payloads, loops calling DB or HTTP, new cache reads, new goroutines / `errgroup`
- **+Obs:** new service / package, new external client, new Asynq / Kafka producer / consumer, logging config change, `prometheus` registration, `pprof`, lifecycle changes
- **+Rel:** new `http.Client` without `Timeout` or use of `http.DefaultClient` / `http.Get` on a downstream call, `sony/gobreaker` / `cenkalti/backoff` config, new `go func()` without a `<-ctx.Done()` arm or owner, a downstream call not taking the request `ctx`, unbounded channel / per-request goroutine spawn, `tx.Create` + `asynq.Enqueue` / `kafka.Produce` dual write inside one transaction
- **2+ categories -> Full**

**Signals name the common case, not the only one - match the construct's role, not its spelling.** This applies to every named construct in this skill, whether or not the named tool is present:

- **Data-access calls.** GORM names read across to the project's layer (sqlx `GetContext` / `SelectContext` / `NamedExec`, `database/sql` `QueryContext`), in the scope signals, Phase B's raw-entity check, and the `go-data-access` bullet alike.
- **Binding calls.** `ShouldBindJSON` stands for any request-DTO binding - `ShouldBindQuery`, `ShouldBindUri`, `c.FormFile`. A DTO that reaches the request surface fires the signal regardless of which binder populates it.
- **Route lists.** `/orders`, `/refunds`, `/checkout`, `/payments`, `/subscriptions` are examples of a class: any endpoint that moves money or provisions an entitlement is in-class whatever its path.
- **Tooling.** When a named tool is genuinely absent (a different migration runner, no ORM), apply the rule the convention protects and suppress the tool-specific form of the finding.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-go-review` | Current branch vs base; fails fast on trunk |
| `/task-go-review <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-go-review pr-<N>` | PR head fetched into local branch `pr-<N>` (user runs fetch) |

Pass `--base <branch>` when the PR was opened against a non-trunk base.

Pass `--req <path>` to name a requirement source (ticket export, PRD, spec) for Phase 0; without it, Phase 0 uses whatever requirement is already in context.

**No checkout required.** Read via ref-qualified diffs; never modify the working tree.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as subagent.

### Step 2 - Stack and Data Access

Use skill: `stack-detect`. Accept pre-detected stack from parent. If not Go, stop and recommend `/task-code-review`.

Detect data access (GORM / sqlx / database/sql / mixed) and messaging (Asynq / Kafka / none). Record both as the Summary's own fields. `stack-detect` may supply them - it emits `ORM` first-class and carries anything a project's `## Tech Stack` declares into `Additional` - but it is not required to, and neither name matches this report's field names. Take what it gives, then confirm against `go.mod` and the wiring in `cmd/api/main.go`.

### Step 3 - Resolve Diff

Use skill: `review-precondition-check`. Forward `--base` if passed. If it fails fast, surface verbatim and stop - with one exception.

**When the only untracked file is this workflow's own prior report** (`review-<branch>.md` from an earlier round), the clean-tree gate is tripping on the artifact the last run wrote, and stopping would make every round-2 review unreachable. Say so, treat the tree as clean, continue, and tell the user to gitignore the report path so the next run does not hit it. Any other dirty-tree content is a genuine stop.

The handle may include a `prior_checkpoint` block (a prior `review-<branch>.md` exists). Decision logic is Step 3.5; for now, just hold onto it.

Read once and reuse:

- `git diff <base>...<head>`
- `git diff --name-status <base>...<head>`
- `git log --oneline <base>..<head>`
- `git ls-tree -r --name-only <head_ref>` - the file list at head, required by Step 6.5 on round 2+

**Skip entirely** when invoked as subagent and parent passed handle + pre-read artifacts.

Also capture the current SHAs for the report's checkpoint frontmatter:

- `current_head_sha = git rev-parse <head_ref>`
- `current_base_sha = git rev-parse <base_ref>`

### Step 3.5 - Decide Round (re-review auto-detect)

**Every round analyzes the full `<base_ref>...<head_ref>` range read in Step 3.** Risk, blast radius, scope signals, depth promotion, and requirement fit are scored on the whole change on every round, so a small follow-up commit cannot under-score a large PR and a defect missed in round 1 stays reachable in round 2. Rounds differ only in that round 2+ reconciles against the prior report.

Skip if the handle has no `prior_checkpoint` -> `round = 1`, no fetch, no reconciliation. Continue to Step 4.

If `prior_checkpoint: legacy` (file present, frontmatter missing/invalid) -> `round = 1`. Note in Summary: `Prior report lacks checkpoint metadata - treated as round 1.` Continue to Step 4.

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

**Step 3.5b - Compare checkpoints.** Rows are not mutually exclusive - evaluate top-down and take the first match.

| Condition                                                              | Decision                                                                                                                            |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `prior_checkpoint.head_sha == current_head_sha`, and the invocation adds no scope or depth beyond the prior checkpoint | **No-op.** Print `No new commits on <head_ref_short> since prior review at <sha_short>. Prior report unchanged.` (where `<head_ref_short>` is the short name of `head_ref` - the review target, not the user's current branch - and `<sha_short>` is the first 7 chars of `current_head_sha`) and stop. Do not call `review-report-writer`. |
| `prior_checkpoint.head_sha == current_head_sha`, but the invocation expands scope or depth beyond it | `round = prior.round + 1`. Note in Summary: `Same head as round <prior.round>; re-review for expanded <scope\|depth>.` |
| `git merge-base --is-ancestor <prior_head_sha> <current_head_sha>` fails (prior SHA unreachable) | `round = prior.round + 1`. Note in Summary: `Prior checkpoint unreachable - history rewritten.`      |
| `prior_checkpoint.base_sha != current_base_sha`                        | `round = prior.round + 1`. Note in Summary: `Base branch advanced since round <prior.round>.`       |
| `prior_checkpoint.base_ref != base_ref`                                | `round = prior.round + 1`. Note in Summary: `Base ref changed since round <prior.round>.`           |
| None of the above                                                       | `round = prior.round + 1`.                                                                          |

**Step 3.5c - Scope expansion handling.** Deferred to the end of Step 4, because scope is not resolved yet here.

Compare the **resolved** scope from Step 4 against the checkpoint's, whether it grew from a user flag or from firing signals - a scope that escalated on its own still has no prior findings to reconcile. Record in Summary: `Scope expanded round <N>: +<list>.`

The reconciliation table (when emitted) only covers findings whose scope was active in the prior round.

### Step 4 - Scope Auto-Escalation

Scan file list / diff for signals listed under **Scope**. Log each as `signal: <category> -> <file:line>` in your working notes. The Summary's `signals:` list names the **construct** that fired each category, not the category (which the Scope value already states) and not the sites: `auto-escalated from Core; signals: +Perf (new WHERE predicate, unindexed column)`. Then:

- Zero signals or `core-only` -> Core
- One category -> add matching scope
- 2+ categories -> Full
- Explicit scope -> respect; still log signals

**Scope precedence on round 2+:** user flag > firing signals. Signals are scored on the full range every round, so a scope that escalated in round 1 escalates again on its own - nothing is inherited from the prior checkpoint. When the resolved scope still falls below the checkpoint's (round 1 was user-flagged), note in Summary: `Scope narrowed vs round <prior.round>: <list> - re-run with <flags> to re-cover.`

Surface decision in Summary; if escalated, append `auto-escalated from Core; signals: <list>`.

### Phase 0 - Change Intent

Use skill: `review-change-intent` with the `<base_ref>...<head_ref>` diff and log, the `--req <path>` file when passed, and `prior_checkpoint.report_path` when round > 1.

`--req <path>` resolves against the directory the command was invoked from, not the git root.

Its `## Change Brief` block goes into the report verbatim, its `Requirement Source` and `Requirement Fit` lines into Summary, its `### Requirement Findings` / `### No Requirement Findings` marker directly under the Change Brief, and its findings join the assembled set verified in Step 6.6. With no requirement source the Brief still renders, and the traceability block and its two Summary lines are omitted. Runs before Phase A - acceptance criteria decide what counts as a defect downstream - and the low-risk short-circuit never skips it.

**Requirement fit does not cap a defect's label.** A criterion scored `Partial` maps to `[Recommend]` as a *requirement* finding; the same code reaching Phase B as an authorization hole is `[Must]`. Publish the stronger label - fit describes delivery against the ask, severity describes consequence, and the two are independent.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk
- Use skill: `review-blast-radius` for failure propagation

Output risk level + blast radius before any findings.

**Score the contract before scoring risk.** Phase B's contract-change signal list enumerates what breaks a consumer - a removed / renamed / retyped response field, a changed status code, a newly required request field, a new route on a versioned surface. Any of those present makes Blast Radius at least Wide, because the fix window is the slowest consumer's release train rather than this service's deploy. A five-character `json:` tag edit in a one-package diff scores Wide on this rule and Narrow on diff footprint; the rule wins.

**Low-risk short-circuit:** if Risk is Low, Blast Radius is Narrow, **and** change does not touch architecture-relevant files (auth middleware, JWT, router groups, shared interfaces, `cmd/api/main.go`, migrations), skip Phases C-E. The streamlined report contains Summary, the Phase 0 outputs (Change Brief, traceability, requirement findings), High-Impact Findings (Phase B), and Next Steps only; Step 7 still writes the checkpointed report.

### Step 4.5 - Re-evaluate Depth After Phase A

If Blast Radius is Wide / Critical, set depth to `deep` and surface promotion in Summary **before** Phases B-E.

**Depth precedence on round 2+:** user flag > this round's auto-promotion. Blast radius is scored on the full range every round, so a promotion that fired in round 1 fires again - nothing is inherited. When the resolved depth still falls below the checkpoint's (round 1 was user-flagged `deep`), note in Summary: `Depth narrowed vs round <prior.round> - re-run with deep to re-cover.`

### Phase B - Go Correctness and Safety

Apply atomic skills; each owns canonical patterns:

- Use skill: `go-error-handling` - `%w` wrapping, sentinels, `errors.Is/As`, no log-and-return
- Use skill: `go-concurrency` - goroutine ownership, `<-ctx.Done()` arms, `errgroup` for required ops, `sync.Mutex` not across I/O
- Use skill: `go-data-access` - `WithContext`, `defer rows.Close()`, `Preload` / `Joins`, transaction boundaries, post-commit dispatch
- Use skill: `go-gin-patterns` - `ShouldBindJSON` (not `BindJSON`), validator tags, response DTO (no raw GORM model in `c.JSON`)
- Use skill: `go-messaging-patterns` if diff touches Asynq / Kafka
- Use skill: `go-migration-safety` if diff touches `migrations/`. Use skill: `ops-backward-compatibility` for client / in-flight impact
- **API contract change** - when the diff carries a contract-change signal (a removed / renamed / retyped response-struct field, a changed status code, a new **required** request field or tightened `binding` constraint, a new public route on a `/v1/`-versioned or externally consumed API, a handler returning a raw GORM entity via `c.JSON`, or an edit to a committed OpenAPI / swaggo spec), use skills `backend-api-guidelines` and `ops-backward-compatibility`. Judge breakage from the consumer's view ("no external callers" needs a search; when consumption is unknown, treat a `/v1/`-versioned or spec-published surface as externally consumed); responses go through a response DTO, never a raw GORM model; errors follow RFC 9457; collections paginated; the committed OpenAPI / swaggo spec matches the code. Each finding names who breaks and how (for a leaked model: what it exposes and who couples to it). Severity maps to labels: High -> `[Must]` = unversioned breaking change to an externally consumed contract, or a raw GORM model on an externally consumed / versioned surface; Medium -> `[Recommend]` = internal breaking change with no coordinated-deploy note, inconsistent status / error envelope, unpaginated unbounded collection, **a committed OpenAPI / swaggo spec the diff left disagreeing with the code**; Low = naming drift with no consumer impact - below the reporting bar, write nothing. A raw GORM model on an internal-only surface is not a gate finding - it stays with the **Response DTO hygiene** check below at `[Recommend]`. Granularity: one finding per `file:line`, except where `backend-api-guidelines` folds one rule broken identically across N endpoints into a single finding listing all N sites - that fold wins, since the ask is one edit

**Pre-existing defects in touched files are in scope.** A defect on a line the diff did not add is reportable when the diff makes it newly reachable, newly consequential, or newly load-bearing (a guard removed in front of it, a first caller added, a second condition stacked on it, a shared resource whose holds now span new work). This phase's job is to raise it; `review-finding-verify` assigns the attribution. All three of those cases take **`Pre-existing (newly reachable)`** - "reachable" there means the diff changed how the defect is reached or how much it bears, not only that a new caller exists - so the label is retained rather than de-escalated. Plain `Pre-existing` is for a defect the diff neither reaches nor loads differently. A defect in a file the diff does not touch at all belongs in `Architecture Notes` or `Maintainability Notes`, not in findings.

**Additional checks (not owned by atomics):**

- **Test coverage finding (named, not buried).** PR adds logic without `*_test.go` -> `[Recommend]`; escalate to `[Must]` when critical path: auth, ownership / role checks, money / billing, multi-table writes, state machines, Asynq / Kafka mutators, migrations changing column semantics
- **Test files are reviewed for coverage only.** For files that are themselves tests, the only finding to raise is a coverage gap: production logic in the diff that no test exercises. Anchor that finding to the untested production `file:line` and state the case to cover, not the test file. Do not review test code for style, structure, duplication, naming, or performance - a passing test with awkward setup is not a finding.
- **Authorization + IDOR.** Every per-owner endpoint scopes queries by principal: `db.Where("id = ? AND user_id = ?", id, <principal-id>)` - where `<principal-id>` is whatever the project uses (`claims.UserID`, `claims.Sub`, `c.MustGet("user_id")`). JWT proves authn, not object access
- **Response DTO hygiene.** Compare response DTO `json:` fields against the model. Flag `PasswordHash` / `MFASecret` / `RecoveryCodes` / `APIKey` / `WebhookSecret` / `InternalNotes` / `AuditLog` / `IsAdmin` / `Role` / `DeletedAt` / `LastLoginIP` on the wire. Raw `c.JSON(200, *model.User)` is `[Recommend]` regardless of current fields (sensitive column added later silently exposes it)
- **HTTP `Idempotency-Key` on retry-prone POSTs.** `/payments`, `/orders`, `/refunds`, `/subscriptions`, `/webhooks` accept the header and dedupe via a `request_idempotency` table. Distinct from worker-side `asynq.TaskID`
- **Client-controlled money fields.** Price / amount / discount on payment-adjacent endpoints (`/orders`, `/refunds`, `/checkout`) come from the server (or a server-validated catalog), not the request DTO. Trusting `req.UnitPrice` is `[Must]`
- **Postgres FK indexes.** `REFERENCES other(id)` does not create an index on the FK column - add one explicitly in the migration. Missing FK indexes cause sequential scans on join, lock contention on cascade delete, and degrade as the parent grows
- **Go boundary quirks.** `net.JoinHostPort` (not `fmt.Sprintf("%s:%d", ...)`); `slog` (not `fmt.Println` / `log.Printf`); `time.Now().UTC()` for timestamps stored in a zone-less column (`TIMESTAMP`, `DATETIME`) - not a finding against `TIMESTAMPTZ`, which normalizes on write, so check the column type in `migrations/` before raising it
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
- **Anemic domain (deep depth only):** rules in services while models stay pure data - flag for refactor/extraction. Don't raise on a single PR alone

**Multi-service PRs:** API contract compatibility (OpenAPI diff, Pact); deployment order documented; use skill: `ops-backward-compatibility`.

### Phase D - AI-Generated Code Quality

- Use skill: `complexity-review` for verbosity, over-engineering
- Use skill: `go-overengineering-review` for binding/service guards vs GORM/DB, defensive nil, silent swallows, single-impl interfaces at impl, `BaseRepository` embedding, speculative config, `Result[T]` vs `(T, error)`, naked `go fn()`

Both atomics emit High / Medium / Low. Map High -> `[Must]`, Medium -> `[Recommend]`, Low -> below the reporting bar, write nothing.

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
- Duplicated query logic: same `WHERE` in 3+ places -> method or GORM scope. Not a finding for a security predicate (tenant, owner, soft-delete): repeating it at every call site is what makes an omission visible, and hiding it behind a helper is how one query silently loses it
- Logging hygiene: surface `fmt.Println` / `log.Printf` in prod paths; lines without correlation IDs; wrong levels
- `gofmt` / `goimports` / `golangci-lint` / `staticcheck` clean
- Godoc on exported APIs; `swaggo/swag` annotations when project uses them

### Step 5 - Delegate Extra Scopes in Parallel

Skip if scope is **Core only**. For each selected scope, spawn one independent subagent **in parallel** with the main thread. Use the **declared subagent for that scope** (`subagent_type` below) - do not infer the agent from the scope name; an observability review is not a `go-tech-lead` spawn:

| Scope | Skill                          | Subagent (`subagent_type`)  |
| ----- | ------------------------------ | --------------------------- |
| +Perf | `task-go-review-perf`          | `go-performance-engineer`   |
| +Sec  | `task-go-review-security`      | `go-security-engineer`      |
| +Obs  | `task-go-review-observability` | `go-observability-engineer` |
| +Rel  | `task-go-review-reliability`   | `go-reliability-engineer`   |

`Full` = 4 subagents.

**Subagent prompt contract** - pass every field; each delegate's Step 1/2 carve-out depends on receiving them:

- The `review-precondition-check` handle itself (each delegate skips its own precondition step only when it receives one)
- Resolved review target (`base_ref`, `head_ref`), `base_sha` / `head_sha`, + pre-read diff and commit log (no re-running git)
- Depth level. It propagates as resolved here, except `+Sec`, which always runs full by its own rule and ignores the value
- Pre-confirmed stack (Go / Gin), data-access mix, **and messaging** (every delegate records it and it has a Summary slot in each)
- Phase 0's acceptance criteria when a requirement source resolved, so a lens can judge intent rather than only mechanics
- Explicitly: return findings in your own Output Format, write no report file, and skip your own verify pass - the parent verifies the merged set once

**Failure isolation:** if subagent fails or times out, continue with the rest. Note missing scope in Summary.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into single Output Format. Do not append raw reports.

**Project each lens's sections onto this report's shape first.** Match on the severity word, not the exact heading string - perf, obs and reliability head their tiers `### High Impact` / `### Medium Impact` / `### Low Impact`, while security heads them `### Critical` / `### High` / `### Medium` / `### Low`. Convert before merging: Critical / High -> `[Must]`, Medium / Low -> `[Recommend]`, and re-file every entry under `## High-Impact Findings` as `### [Label] file:line`. Nothing downstream parses the lens headings - `review-prior-findings-reconcile` reads only `## High-Impact Findings` - so a finding left under its lens heading is invisible to the next round.

Map the lens's fields onto `Issue` / `Impact` / `System Risk` / `Fix`: the lens's own `Issue` and `Fix` carry over; `Failure Mode`, `Attack scenario` and the perf `Impact` become `Impact`; `Blast Radius` and `Severity rationale` become `System Risk`. When a lens block has nothing for `System Risk`, write why the finding is system-level rather than dropping the slot.

**Granularity is the parent's, not the lens's.** A lens may fold several defects into one entry - security's combined-finding rule composes missing auth, mass assignment and replayability on one handler into a single Critical. This report files **one entry per fix**, so un-fold it: publish each defect at its own `file:line` with its own remedy, and carry the composition in the strongest one's `System Risk` ("alone this is X; with the two below it is unauthenticated, unbounded, repeatable money movement"). The composition is the reason the severity is what it is, and it survives as prose rather than as a merged entry the next round cannot reconcile.

Each lens also returns a `## Recommendations` section that is not findings. Merge them into `Architecture Notes` or `Maintainability Notes` by subject; do not discard them.

- Deduplicate cross-cutting findings (one entry citing all scopes) - but never merge two findings that will verify differently in Step 6.6 (see its dedup rule)
- **Strongest intent wins** when labels differ across subagent reports for the same finding: `Must` > `Recommend`
- Preserve `file:line` citations
- Order by intent, not scope
- Note missing scopes as `Scope incomplete: <scope>`
- Merge Next Steps with `[Implement]` / `[Delegate]` tags; re-sort by intent
- Preserve every non-findings section a lens returns, not only the deep-only ones, and **match on heading text at any level** - a lens may emit `## Verified Clean` or `### Verified Clean` and both mean the same thing. Reliability's `Failure-Mode and Blast-Radius Map` and perf's `Capacity & Load Plan` become their own sections after Next Steps. `Sequencing` folds into this report's Next Steps ordering; `Verified Clean` joins this report's `## Verified Clean`; `Out of Lens` items join `## Next Steps` as `[Delegate]` rows carrying the owning lens; a lens's `Recommendations` merge into `Architecture Notes` or `Maintainability Notes` by subject. The merge drops nothing a lens was required to produce

**Cross-phase same root cause.** When one defect spans multiple phases (e.g., a layering violation that also degrades testability and DTO discipline), file the finding once under the phase where the root cause sits and reference its `file:line` from `Architecture Notes` or `Maintainability Notes`. Do not double-count by listing the same `file:line` as separate findings.

### Step 6.6 - Verify Findings (second pass)

Use skill: `review-finding-verify` with the assembled findings (including any merged back from subagents), the diff already read, and `base_ref` / `head_ref`.

Runs before reconciliation so prior-round matching sees the corrected set. Publish only rows whose Verdict is not `Dropped`, carrying the skill's `Label` column. Carry its tally into Summary verbatim in the skill's own form - `Findings verified: <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff)`, parenthetical omitted when `K` is 0.

**Dedup must not cross an attribution boundary.** Step 6 merges duplicate findings; this pass assigns each one verdict and one attribution. A merged entry whose halves verify differently - one `Confirmed` on new code, one `Pre-existing` that de-escalates - cannot carry both, and this skill only rules on what it is given. Un-merge those back into separate findings before verifying rather than forcing one verdict onto both.

### Step 6.5 - Reconcile Prior Findings (round 2+ only)

Skip on round 1. Otherwise use skill: `review-prior-findings-reconcile` with:

- `prior_report`: the loaded body of `review-<branch>.md` (frontmatter excluded)
- `diff`: the full-range diff from Step 3
- `name_status`: the full-range `git diff --name-status <base_ref>...<head_ref>` from Step 3
- `head_files`: `git ls-tree -r --name-only <head_ref>`. **Required, not optional.** A file created and then deleted inside the range nets out of `name_status` entirely, so its touch state reads `untouched`; without `head_files` the reconcile skill cannot tell "reverted to base state" (`Addressed`) from "gone at head" (`Obsolete`) and silently picks the first

The reconcile skill returns a Markdown table and a tally line. Insert the table under `## Prior Round Reconciliation` in the report (see Output Format).

Fold any `Still open` rows into `## Next Steps` as `(open since round <prior.round>)`-suffixed entries, ordered by severity alongside this round's new findings. Do not emit a standalone "Carry-Over Open Items" section.

**A carried-forward finding is re-assessed this round, and the reconciliation table is not.** The table preserves the prior label and `file:line` verbatim (the reconcile skill's own rule). The `## High-Impact Findings` entry and its Next Steps line carry **this** round's label and the site where the smell now lives - a round-1 `[Recommend]` that this round's rules make `[Must]`, or a smell that moved from `:38` to `:44`, is published at the current assessment. The two representations differ on purpose: the table is the audit trail, the finding is the ask.

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review` and these checkpoint fields:

- `branch`, `base_ref`, `base_sha = current_base_sha`, `head_ref`, `head_sha = current_head_sha`
- `mode: full` (the writer's only accepted value), `round` (from Step 3.5), `prior_head_sha` (omit on round 1)
- `scope` (resolved in Step 4, mapped to the writer's enum: `Core` -> `core-only`, `+Sec` -> `+sec`, `+Perf` -> `+perf`, `+Obs` -> `+obs`, `+Rel` -> `+rel`, `Full` -> `full` - the writer rejects unmapped display values), `depth` (resolved/auto-promoted), `stack = go-gin`

Write before ending; print confirmation.

The writer drops `review-<branch>.md` in the working directory. If that is inside the repo, the file dirties the tree and `review-precondition-check`'s clean-tree gate fails the next round on the same command - tell the user to gitignore the report path when the write lands in a tracked directory.

## Feedback Labels

| Label        | Meaning                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| [Must]       | Do not merge until this is fixed.                                        |
| [Recommend]  | Fix, or push back with reasoning. Cannot be silently acked.              |

No `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` - if it isn't `[Must]` or `[Recommend]`, don't write it down.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

```markdown
## Summary

- **Assessment:** Approve | Request Changes | Discuss
- **Risk Level:** Low | Medium | High | Critical
- **Blast Radius:** Narrow | Moderate | Wide | Critical
- **Stack Detected:** Go <version> / Gin <version>
- **Data Access:** GORM | sqlx | database/sql | mixed
- **Messaging:** Asynq | Kafka | none
- **Scope:** Core | +Sec | +Perf | +Obs | +Rel | Full _(if auto-escalated: `auto-escalated from Core; signals: <list>`)_
- **Depth:** standard | deep _(if auto-promoted: `auto-promoted from standard; Blast Radius: <level>`)_
- **Round:** <N>                                _(include from round 2 onward)_
- **Round Notes:** <every `Note in Summary` string Steps 3.5b, 3.5c, 4 and 4.5 produced, semicolon-separated> _(omit when there are none; round 1 has none)_
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff) _(parenthetical omitted when K is 0)_
- **Requirement Source:** <path or origin> (Specified | Self-attested) _(this line and the next are emitted together, or both omitted when Phase 0 resolved no source)_
- **Requirement Fit:** <n> met, <n> partial, <n> unmet, <n> deferred, <n> untraceable
- **Blast Radius rationale:** <the one factor that set the level - contract break, data reach, or reversibility>

## Change Brief

**Requested:** <what the change was asked to do, citing the source; `(inferred from commits)` when no source resolved>

**Delivered:** <the mechanism implemented and where>

**Author decisions:** <each choice the request did not imply, with its consequence, excluding choices already raised as findings; `None observed` when nothing remains>

**Watch points:** <what to confirm by hand before reading findings; `None` when there are none>

### Requirement Findings _(or `### No Requirement Findings` - the marker that Phase 0 ran; omit both when no source resolved)_

One bullet per requirement finding, each citing the `file:line` and the `## High-Impact Findings` entry that publishes it in full - `[Must] internal/handler/x.go:44 - AC1 partial: no ownership check (see finding 1)`. The bullet is an index, not a second copy: the finding itself is published once, below, at the label this round assigned it.

## Requirement Traceability _(omit when Phase 0 resolved no source)_

| Criterion | Status | Implementation | Proof |
| --------- | ------ | -------------- | ----- |
| <id or quoted outcome> | Met \| Partial \| Unmet \| Deferred \| Untraceable | <file:line, or `-`> | <file:line or verification note, or `-`> |

## Prior Round Reconciliation _(round 2+ only; omit otherwise)_

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |
| ...                 | ...       | ...    | ...   |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## High-Impact Findings

Every published finding lives here under `### [Must] file:line` or `### [Recommend] file:line`, `[Must]` first - this is the only heading the next round's reconciliation parses. Merged subagent findings are re-filed here per Step 6, never left under a lens heading.

When the set exceeds ~12, keep every `[Must]` and group the `[Recommend]` tail: one entry per root cause listing its sites, rather than one entry per site. Volume is not thoroughness - a 30-item list of blockers reads as none.

### [Must] file:line

- Issue: [name the Go idiom]
- Impact: [user-visible or operational]
- System Risk: [why this is system-level]
- Fix: [concrete Go change with code]

### [Recommend] file:line
- Issue, Impact, Fix

## Architecture Notes

_Cross-cutting commentary. Reference findings by file:line._
- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

- Over-engineering detected:
- Simplification opportunities:

## Verified Clean

Checks that ran and passed, with their evidence - the authz scoping that is correct, the response DTO that leaks nothing, the money field that is server-derived, the FK that is indexed. Includes any `### Verified Clean` a lens returned. A reader cannot otherwise tell "checked and fine" from "never checked", and on a clean PR that distinction is the review.

## Key Takeaways

2-4 bullets on systemic impact.

## Next Steps

On round 2+, prior-round Still open items are folded in with (open since round <N>) suffix and ordered by intent alongside new findings. Each item tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend.

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
- Delegate perf / security / observability / reliability depth to subagents

## Self-Check

Mark a line N/A with its reason when the invocation mode makes it inapplicable - `pr-ref` lines in branch mode, `head_matches_current` when it is true, round-2 lines on round 1.

- [ ] `behavioral-principles` loaded (or accepted from parent)
- [ ] Stack confirmed; data-access mix and messaging recorded
- [ ] `review-precondition-check` ran (or handle received); diff/log read once and reused; current_head_sha and current_base_sha captured
- [ ] Step 3.5 - round decided (1 / prior + 1 / no-op); auto-fetch attempted only when prior checkpoint exists; the full `<base_ref>...<head_ref>` range analyzed regardless of round; no-op path exits without writing the report
- [ ] For `pr-ref` mode: fetch surfaced; ref existed before review continued
- [ ] When `head_matches_current` was false: user approval obtained
- [ ] Scope auto-escalation evaluated; promotion (or `core-only`) recorded
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical
- [ ] Phase 0 - `review-change-intent` ran on the cumulative diff; Change Brief carried into the report; requirement lines in Summary, or all three requirement outputs omitted when no source resolved; its findings verified with the rest
- [ ] Risk + blast radius stated before any finding
- [ ] Phase B: atomic skills applied; test coverage, authz, response DTO, Idempotency-Key, race safety checked; API contract checks ran when a route, handler, response struct, or OpenAPI/swaggo spec changed
- [ ] Phase C: layering, interface-at-consumer, constructor injection, settings, multi-tenant
- [ ] Phase D: `complexity-review` + `go-overengineering-review` applied
- [ ] Phase E: naming, magic numbers, function length, structured logging
- [ ] Missing tests raised as named finding (not buried)
- [ ] Every Must cites system risk
- [ ] Every finding has label + `file:line` + a concrete fix in whatever language the fix lives in (Go, SQL, YAML)
- [ ] Every mandated `Note in Summary` string reached the `Round Notes` line
- [ ] Extra scopes ran in parallel with the full prompt contract (handle, refs, SHAs, diff, log, depth, stack, data access, messaging, acceptance criteria, no-write instruction)
- [ ] Subagent findings projected onto `### [Label] file:line` under `## High-Impact Findings`; no raw reports appended; no entry left under a lens heading
- [ ] Failed / missing subagent scope noted as `Scope incomplete: <scope>`
- [ ] Step 6.6 - review-finding-verify ran on all assembled findings; Dropped rows excluded; verdict labels applied; tally in Summary
- [ ] Step 6.5 - on round 2+, review-prior-findings-reconcile ran with `head_files` passed; reconciliation table inserted preserving prior labels and lines; Still open rows folded into Next Steps at this round's label and current site, suffixed (open since round <N>)
- [ ] Next Steps produced with `[Implement]` / `[Delegate]` tags, ordered by intent
- [ ] Review report written via `review-report-writer` with full checkpoint fields (mode, round, prior_head_sha when round > 1, head_sha, base_sha, scope, depth, stack); confirmation printed

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase). The one allowed exception is `git fetch <remote> <branch>` in Step 3.5a, and only when a valid prior checkpoint exists.
- Auto-fetching on round 1 (no prior checkpoint) - keeps first-run behavior strictly read-only.
- Scoping round 2+ analysis to `<prior_head_sha>...<head_sha>` - risk, scope, depth, and requirement fit score the full `<base_ref>...<head_ref>` range on every round.
- Writing the report on no-op exit (prior `head_sha == current head_sha`) - the file must stay byte-identical.
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`).
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
- Emitting a "Carry-Over Open Items" section - fold into Next Steps instead.
- Reviewing without reading the full diff and commit log first
- Generic backend conventions when a Go idiom exists ("define interface in consumer", not "use DI")
- Nitpicking style where `gofmt` applies
- Vague feedback ("this could be better")
- Blocking on personal preference
- Running extra scopes when `core-only` was passed
- Duplicating perf / security / observability / reliability depth here
- Sequential extra scopes that could parallelize
- Appending raw subagent reports
- Recommending `panic` in service code
- Recommending `db.AutoMigrate` for production
- Recommending `db.Raw(fmt.Sprintf(...))`
