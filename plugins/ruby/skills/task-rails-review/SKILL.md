---
name: task-rails-review
description: Rails code review - Zeitwerk, callbacks, fat controllers, AR-in-API, services, scopes; spawns perf/security/observability subagents.
agent: rails-tech-lead
metadata:
  category: backend
  tags: [ruby, rails, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

# Rails Code Review

Rails-aware staff-level review. Runs correctness, architecture, AI-quality, and maintainability through a Rails lens; spawns perf/security/observability subagents in parallel when scope warrants. Stack-specific delegate of `task-code-review`.

## When to Use

- Pre-merge Rails PR review, post-AI quality gate, architecture-drift detection

**Not for:** feature design (`task-rails-implement`), incident triage (`/task-oncall-start`), single-error debugging (`task-rails-debug`), new-system design (`task-design-architecture`), single-scope reviews (delegate to `task-rails-review-{perf,security,observability}`).

## Depth and Scope

Depth (`quick` | `standard` | `deep`, default `standard`) and scope (`Core` | `+Perf` | `+Security` | `+Observability` | `Full`) mirror `task-code-review`. Pass `core-only` to suppress auto-escalation.

**Auto-promote depth to `deep`** after Step 4 when Blast Radius is Wide/Critical and the user did not pass `quick`. Record in Summary.

**Auto-escalate scope (Rails signals):**

- **+Security**: Active Storage / Shrine / CarrierWave, Devise config, Pundit/CanCanCan policies, `params.permit` changes, raw SQL / `find_by_sql`, secrets, Sidekiq jobs taking user input
- **+Perf**: new `db/migrate/`, `add_index`, new scopes / `.where` / `.order`, new payload endpoints, loops hitting DB or HTTP
- **+Observability**: new service, external dependency, ActiveJob/Sidekiq job class, log config changes, new `ActiveSupport::Notifications`
- Two or more signal categories -> **Full**

## Invocation

| Form                              | Behavior                                                     |
| --------------------------------- | ------------------------------------------------------------ |
| `/task-rails-review`              | Current branch vs base; fails fast on trunk                  |
| `/task-rails-review <branch>`     | 3-dot diff vs base                                           |
| `/task-rails-review pr-<N>`       | Local ref `pr-<N>` (user fetches first)                      |

Flags compose: `/task-rails-review pr-50273 --base phase-01 +security deep`. Pass `--base <branch>` when the PR's true base is non-trunk. The workflow never modifies the working tree.

## Workflow

### Step 1 - Load Behavioral Rules

Use skill: `behavioral-principles`. If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists, also use skill: `spec-aware-preamble`; cross-check the diff against `spec.md`/`plan.md` - out-of-scope changes are blockers, missing AC coverage is a gap.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-detected stack from a parent dispatcher. If not Rails, redirect to `/task-code-review`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Surface fail-fast messages verbatim and stop. On approval, read and log **once** (skip when a parent passed pre-read artifacts):

- `git diff <base_ref>...<head_ref>`
- `git diff --name-status <base_ref>...<head_ref>`
- `git log --oneline <base_ref>..<head_ref>`

### Step 4 - PR Risk Snapshot

- Use skill: `review-pr-risk`
- Use skill: `review-blast-radius`
- State Risk Level and Blast Radius before line-level findings

**Low-risk short-circuit:** if Risk: Low and Blast Radius: Narrow **and** the change does not touch auth, middleware, API contracts, shared concerns, `app/services/`, or `lib/`, skip Steps 6-7 and produce Step 5 only.

### Step 5 - Rails Correctness and Safety

Logical correctness, error handling, state-integrity edge cases, backward compat, transaction boundaries.

**Test-coverage finding (named, not buried):** logic added without RSpec coverage is `[Suggestion]`. Escalate to `[High]` on critical paths: auth, authorization, money/billing, multi-record transactions, state machines, data-mutating Sidekiq jobs, migrations changing column semantics.

**Diff-scan checks:**

- [ ] **Transactions**: writes wrapped; no HTTP / `.perform_async` inside - use `after_commit`
- [ ] **Callbacks**: cross-aggregate work and Sidekiq dispatch via `after_commit`, not `after_save`/`after_create`
- [ ] **`save!`** in services / transactions so failures surface
- [ ] **Strong params**: explicit `permit(...)`; no `permit!` / `to_unsafe_h`
- [ ] **N+1 / unbounded queries**: preload in controllers and serializers; `find_each` over `.all.each`
- [ ] **AR-in-API**: no bare `render json: @model` - serializer required. Sensitive fields (`password_digest`, `*_secret`, `api_key`, `is_admin`, internal/audit columns) flagged `[High]`
- [ ] **Idempotency-Key** on new unsafe write endpoints (`payments`, `orders#create`, `refunds`, `subscriptions#create`, inbound webhooks): missing = `[High]`. HTTP-layer key is distinct from Sidekiq `unique_for:`
- [ ] **Authorization** on every action: `authorize @resource` / `load_and_authorize_resource`; explicit `skip_authorization` with rationale
- [ ] **Error handling**: no blanket `rescue StandardError`; `rescue_from` in `ApplicationController` for `RecordNotFound`, `Pundit::NotAuthorizedError`
- [ ] **Bulk operations**: partial-failure path defined; transaction wraps one chunk, not the whole run or one row
- [ ] **Concurrency**: no class-level mutable state, no `Time.zone=`; race-prone updates use row-level lock or `with_advisory_lock`

**Migration PRs** (any `db/migrate/` change) - use skill: `ops-backward-compatibility`:

- [ ] Two-phase column rename/drop (add -> backfill -> cut over -> remove)
- [ ] `NOT NULL` on existing columns via two-step (nullable -> backfill -> set NOT NULL)
- [ ] `add_index` on large tables: PG `algorithm: :concurrently` + `disable_ddl_transaction!`; MySQL `:inplace`
- [ ] FKs added with `validate: false`, validated separately
- [ ] Data migrations in rake tasks, not `db/migrate/`
- [ ] Rollback path documented

Atomic skills: `rails-activerecord-patterns`; `rails-service-objects` if PR adds/extends a service; `rails-sidekiq-patterns` if PR adds/modifies a job.

### Step 6 - Rails Architecture Guardrails

Use skill: `architecture-guardrail`.

- [ ] **Layering**: presentation -> service/domain -> data. No business logic in controllers; no `Net::HTTP` in models; no view rendering in services
- [ ] **Service discipline**: controller actions > 5 orchestration lines extracted; services expose `.call` returning `Result`; no mixed `.call`/`.execute`/`.run` interfaces
- [ ] **Concern hygiene**: `app/**/concerns/*.rb` role-based (`Sluggable`, `SoftDeletable`), not grab-bags
- [ ] **Zeitwerk**: file paths match constant names; no `require_relative` inside `app/`
- [ ] **Namespace / engine boundaries**: cross-namespace access via service objects, not direct `Billing::Invoice.find`
- [ ] **Multi-tenant isolation**: enforced at the model layer (`acts_as_tenant`, `default_scope`, query objects), not only in controllers
- [ ] **Multi-database**: `connects_to` declared on models; cross-DB joins flagged

For multi-service PRs, use skill: `ops-backward-compatibility` for API contract compatibility and deployment order.

### Step 7 - AI-Generated Code Quality

- Use skill: `complexity-review` (cyclomatic / cognitive complexity; redundant mapping layers like `User -> UserDecorator -> UserPresenter -> UserSerializer`)
- Use skill: `rails-overengineering-review` (validations duplicating DB constraints, defensive guards on impossible states, services / `Result` / base classes wrapping trivial logic)
- [ ] **Test verbosity**: setup > 30 lines per example; `let!` chains replaceable by a FactoryBot trait; matchers reimplemented when shoulda-matchers exist

### Step 8 - Rails Maintainability

- [ ] **Naming**: classes are nouns; services describe an action (`FulfillOrder`); scopes are queries (`active`, `completed_after`)
- [ ] **Magic numbers/strings** extracted to constants or `Rails.application.config.x.*`
- [ ] **Credentials/URLs**: `Rails.application.credentials` or env config, never inline
- [ ] **Method length**: > 15 lines reviewed; > 30 flagged unless `.call` orchestrating clearly named steps
- [ ] **Duplicated query logic**: same `.where(...).order(...)` in 3+ places extracted to a scope or query object
- [ ] **Logging hygiene**: correct levels; structured fields when `lograge` / `semantic_logger` is configured

Load conditionally: `backend-coding-standards` when new naming/structure patterns introduced; `ops-observability` when diff touches logging or metrics (depth owned by `task-rails-review-observability`).

### Step 9 - Delegate Extra Scopes in Parallel

Skip if scope is Core-only. For each selected scope, spawn an independent subagent in parallel.

| Scope                                | Subagents                                            |
| ------------------------------------ | ---------------------------------------------------- |
| +Perf / +Security / +Observability   | 1 subagent running the matching `task-rails-review-*` |
| Full                                 | 3 subagents in parallel                              |

**Subagent prompt contract:** resolved `base_ref`/`head_ref` + pre-read diff and commit log (no re-running `review-precondition-check` or `git diff`); depth level; pre-confirmed stack; return findings using its own skill's Output Format.

**Failure isolation:** if a subagent fails or times out, continue with remaining results; note `Scope incomplete: <scope>` under Summary.

### Step 10 - Synthesize and Report

Merge subagent findings into the single Output Format:
- Deduplicate cross-cutting findings; one entry citing all scopes that raised it
- On differing labels, highest severity wins (`Blocker > High > Suggestion > Question`)
- Preserve `file:line` citations; order by severity, not scope
- Merge Next Steps into one prioritized list; preserve `[Implement]` / `[Delegate]` tags

Use skill: `review-report-writer` with `report_type: review`. Print confirmation line.

## Feedback Labels

| Label        | Meaning                                          |
| ------------ | ------------------------------------------------ |
| [Blocker]    | Must fix before merge - correctness or risk      |
| [High]       | Should fix - significant impact or smell         |
| [Suggestion] | Would improve - non-blocking                     |
| [Question]   | Need clarity from author                         |

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Ruby <version> / Rails <version>
**Scope:** Core | +Security | +Perf | +Observability | Full _(append `auto-escalated from Core; signals: <list>` if applicable)_
**Depth:** quick | standard | deep _(append `auto-promoted from standard; Blast Radius: <level>` if applicable)_

## Findings

Each entry, ordered Blocker > High > Suggestion > Question:

### [Label] file:line

- Issue: [Rails idiom named: callback abuse, fat controller, AR-in-API, missing authorize, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is system-level] _(required for Blocker; optional otherwise)_
- Fix: [concrete Rails change with code]

## Architecture Notes
- Boundary impact / Coupling change / Drift detected

## Maintainability Notes
- Over-engineering detected / Simplification opportunities

## Key Takeaways
- 2-4 bullets on systemic impact

## Next Steps

Prioritized; each item `[Implement]` or `[Delegate]`; order Blocker > High > Suggestion.

1. **[Implement]** [Blocker] file:line - one-line action
2. **[Delegate]** [High] [scope] - one-line action
```

_Omit empty sections. Omit Next Steps entirely if no actionable findings._

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded; `spec-aware-preamble` when applicable
- [ ] Step 2: stack confirmed (or accepted from parent)
- [ ] Step 3: `review-precondition-check` ran (or handle received); diff/log read once and reused
- [ ] Step 4: Risk Level and Blast Radius stated before line-level findings; depth auto-promoted on Wide/Critical
- [ ] Step 5: Rails correctness checks applied; missing tests raised as a named finding
- [ ] Step 6: architecture checks applied
- [ ] Step 7: complexity and over-engineering reviewed
- [ ] Step 8: maintainability checks applied
- [ ] Step 9: non-Core subagents ran in parallel with pre-resolved artifacts; failed scopes noted as `Scope incomplete`
- [ ] Step 10: findings merged with deduplication and highest-severity-wins; report written via `review-report-writer`; confirmation printed
- [ ] Every Blocker states a system risk; every finding has a label, `file:line`, and actionable Rails fix
- [ ] If `--spec` was passed, every finding traces to AC/NFR/task or is flagged out-of-scope

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command
- Reviewing without reading the full diff and log first
- Applying generic backend conventions where a Rails idiom exists
- Nitpicking style without a project standard; no `[Nitpick]` / `[Praise]` labels
- Blocking on personal preference rather than correctness, risk, or maintainability
- Duplicating perf / security / observability depth here when a dedicated subagent owns it
- Running extra-scope subagents sequentially or when `core-only` was passed
- Appending raw subagent reports instead of merging into one severity-ordered list
