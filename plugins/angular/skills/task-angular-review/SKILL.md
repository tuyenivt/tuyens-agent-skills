---
name: task-angular-review
description: Angular code review - standalone, OnPush, signals, RxJS, sanitizer, SSR, a11y; spawns perf/security/obs subagents.
agent: angular-tech-lead
metadata:
  category: frontend
  tags: [angular, typescript, signals, rxjs, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

# Angular Code Review

Staff-level Angular code review covering correctness, architecture, AI-quality, and maintainability through an Angular lens. Coordinates perf / security / observability subagents in parallel.

## When to Use

- Pre-merge review on an Angular PR
- Post-AI-generation quality gate
- Architecture drift detection

**Not for:** pre-implementation design (`task-angular-implement`), production incident (`/task-oncall-start`), single-error debug (`task-angular-debug`), single-scope reviews (delegate to `task-angular-review-perf` / `-security` / `-observability`).

## Depth Levels

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | Phases A-E |
| `deep` | Architecture PRs, post-incident | A-E + historical pattern matching |

**Auto-promote to `deep`:** evaluated once in Phase A after Blast Radius is known. Surface as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E (Angular-flavored) |
| +Perf / +Sec / +Obs | Core + matching `task-angular-review-*` subagent |
| Full | Core + all three subagents in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress escalation.

**Auto-escalation signals:**

- **+Sec:** new `bypassSecurityTrust*`, new `[innerHTML]`, new functional interceptor / guard, auth config change, `Router.navigateByUrl` from user input, CSP change, secret-like `environment.ts` entries
- **+Perf:** new lazy route, heavy dependency, Default CD, new `@defer`, new store, `HttpClient` call without caching, long list without `track`
- **+Obs:** new `ErrorHandler`, Sentry / RUM SDK init, `web-vitals` reporter, analytics call, new `TransferState`
- **2+ categories -> Full**

## Invocation

| Form | Meaning |
|------|---------|
| `/task-angular-review` | Current branch vs base; fails fast on trunk |
| `/task-angular-review <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-angular-review pr-<N>` | PR head fetched into `pr-<N>` (user runs fetch) |

`--base <branch>` overrides default base. Scope and depth flags compose: `/task-angular-review pr-50273 --base release/2026.05 +sec deep`.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as a subagent.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. If not Angular, stop and recommend `/task-code-review`. Record `Angular: <version>`, `Change detection: zone.js | zoneless`, `SSR: enabled | disabled`, `Workspace: CLI | Nx`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. The handle may include a `prior_checkpoint` block (a prior `review-<branch>.md` exists). Decision logic is Step 3.5; for now, just hold onto it.

On approval, read once and reuse: `git diff <base>...<head>`, `git diff --name-status <base>...<head>`, `git log --oneline <base>..<head>`. Skip when invoked as subagent with pre-read artifacts.

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

### Step 4 - Evaluate Auto-Escalation

Scan diff for signals listed under **Scope**. Log each fire as `signal: <category> -> <file:line>`. Apply rules: zero/`core-only` -> Core; one category -> add scope; 2+ -> Full. User-passed explicit scope wins; signals still logged.

**Scope precedence on round 2+:** user flag > firing signals > inherit from `prior_checkpoint.scope`. If the user passed no flag and the diff (incremental, in incremental mode) fires no signals, inherit the prior round's scope so reviewer coverage does not silently narrow. Surface as `Scope: <inherited> (inherited from round <prior.round>)`.

### Phase A - PR Risk Snapshot

Use skills: `review-pr-risk`, `review-blast-radius`. Output risk level and blast radius before any findings.

**Auto-promote depth:** if Blast Radius Wide/Critical, set depth to `deep`. Log the promotion once (here, not in Step 4).

**Low-risk short-circuit:** if Risk Low + Blast Narrow + no architecture-relevant files (auth config, interceptors, route config, `app.config.ts`, `angular.json`, `vite.config.ts`, root component, shared services/stores), skip Phases C-D and use streamlined output.

### Phase B - Angular Correctness and Safety

Apply atomic skills - each owns canonical patterns:

- `angular-component-patterns` - standalone, OnPush, signal IO, content projection, control flow, `@defer`
- `angular-signals-patterns` - `computed` vs `effect`, `toSignal` init/sync, `linkedSignal`, `untracked`, `resource()`
- `angular-rxjs-patterns` - `takeUntilDestroyed` / `async` / `toSignal`, flattening op selection
- `angular-service-patterns` - functional interceptors with retry/refresh, DI scope, token origin scoping
- `angular-data-fetching` - `httpResource`, TanStack Query for Angular, cache invalidation, optimistic updates, SSR transfer cache
- `angular-state-patterns` - URL/NgRx/signal/service categorization, persistence, auth lifecycle
- `angular-forms-patterns` - typed `FormGroup`, validators, `FormArray`, `ControlValueAccessor`, server-side validation surfacing (when diff touches forms)
- `angular-routing-patterns` - `canMatch` on lazy routes, functional guards, `withComponentInputBinding`, SSR hydration (when diff touches route config)
- `angular-nx-patterns` - tags + `enforce-module-boundaries`, library taxonomy, `nx affected` (when workspace is Nx)
- `angular-styling-patterns` - tokens, hybrid Tailwind+Material, M3 theming (when diff touches styles)
- `angular-i18n-patterns` - untranslated user-facing strings/attributes, ICU vs string-concat plurals, stable `@@` IDs, locale-aware pipes (when i18n is configured and the diff touches templates/strings)
- `angular-testing-patterns` - coverage for changes (when diff adds logic)

**Orphan checks (no atomic owns - cross-cutting only):**

Control flow, `@defer`, NgModule, content projection, OnPush -> `angular-component-patterns`. Reactive Forms -> `angular-forms-patterns`. SSR hydration + `withHttpTransferCacheOptions` -> `angular-routing-patterns` + `angular-data-fetching`. Defer to those atomics, do not duplicate.

- **Mutable module-level state.** `let cache = {}` leaks across SSR requests.
- **Cross-cutting safety.** `[innerHTML]` on user content without sanitizer = `[Must]`; `bypassSecurityTrust*` needs justification + is `[Must]` on user content (audit the *upstream* - input must be DOMPurify-sanitized or server-trusted); open redirect via `Router.navigateByUrl(query.returnTo)` without allowlist = `[Must]`; `environment.ts` privileged secrets are `[Must]` (compile into client bundle).
- **TypeScript strict.** No `: any` inputs; `as any` outside test setup is a finding.
- **Accessibility.** `<input>` paired with `<label>`; dialogs use CDK `Dialog`; images use `NgOptimizedImage` or explicit `width`/`height`; `alt` present.
- **Test coverage for logic added.** Missing tests is a named finding (`[Recommend]`; escalate to `[Must]` on critical paths: auth, billing UI, form validation, error handlers).

### Phase C - Angular Architecture Guardrails

Use skill: `architecture-guardrail`.

- **Layering:** business logic in container/services, not leaf components. HTTP in services, not components.
- **Lazy-load:** feature routes use `loadComponent` / `loadChildren`; eager `component:` for non-trivial routes is a finding.
- **DI hierarchy:** `providedIn: 'root'` for app-wide singletons, route-scoped for per-route state, component-scoped for per-instance. Root-scoped per-user state without explicit logout reset bleeds.
- **Configuration:** typed config via `InjectionToken<AppConfig>`; `environment.X` sprinkled across components is a finding.
- **Module boundaries:** feature folders with defined public surface; cross-feature imports through `index.ts`. In Nx, missing `tags` on a new project or violation of `@nx/enforce-module-boundaries` is `[Recommend]` - see `angular-nx-patterns`.
- **NgModule sandwich:** legacy `AppModule` with >30 imports is a migration target when the diff touches it.

### Phase D - AI-Generated Code Quality

Use skill: `complexity-review`. Angular AI smells:

- **Pattern inflation:** generic `<DataTable<T>>` for one use case; content-projection trio when a flat input API would do
- **Over-abstraction:** `BaseFormComponent` parent for 2 children; "headless" abstraction for one consumer
- **Redundant signal transforms:** input signal -> `linkedSignal` -> `effect` syncing them; use input directly via `computed`. "Store input in writable signal" is almost always wrong
- **`effect` misuse:** `effect(() => mySignal.set(...))` -> `computed` / `linkedSignal`; `effect(() => { if (clicked()) ... })` triggered by `(click)` -> call handler directly
- **`as any` / `as unknown as T` proliferation:** bypassing a real type bug is a finding
- **Try-catch noise in observables:** `pipe(catchError(e => { throw e }))` -> delete; `pipe(catchError(e => of(null)))` swallows - prefer `catchError(e => { logger.error(e); return throwError(() => e) })`

### Phase E - Maintainability and Clarity

Use skill: `ops-observability` for cross-cutting logging/metrics presence (depth -> observability subagent).

- **Naming:** components PascalCase + `Component` suffix; services with `Service`; selectors kebab-case with prefix (`app-order-list`).
- **File naming:** `order-list.component.ts/.html/.spec.ts` colocated.
- **Magic numbers / strings:** module constants or `InjectionToken`-injected config.
- **Hardcoded URLs:** env-driven config, not inline.
- **Component length:** >200 lines reviewed for extraction.
- **Conditional ladders:** >3 nested `@if` / ternary -> extract sub-component or `computed`.
- **Logging hygiene:** `console.log` in `ngOnInit` / template bindings runs every CD cycle; route through `ErrorHandler` / RUM.

### Step 5 - Delegate Extra Scopes in Parallel

If scope is Core only, skip.

| Scope | Subagent |
|-------|----------|
| +Perf | `task-angular-review-perf` |
| +Sec | `task-angular-review-security` |
| +Obs | `task-angular-review-observability` |
| Full | All three in parallel |

**Subagent prompt:** resolved review target (`base_ref`, `head_ref`), pre-read diff + commit log, depth level, pre-confirmed stack + detected configuration. Instruction to return findings in its own Output Format.

**Failure isolation:** if a subagent fails or times out, continue. Note `Scope incomplete: <scope>` in Summary.

### Step 6 - Synthesize (only if Step 5 ran)

Merge into the single Output Format below. Do not append raw subagent reports.

- Dedupe key: identical `file:line` + same issue name = one finding (cite all scopes that raised it). Keep the most specific `Fix` text across versions.
- **Strongest intent wins** when labels differ across subagent reports for the same finding: `Must` > `Recommend` > `Question`. Map subagent tiers to parent labels: `Critical` -> `[Must]`, `High` -> `[Recommend]`, `Medium`/`Low` -> drop from the merged list (only `Must`, `Recommend`, `Question` are emitted).
- Preserve `file:line` citations
- Order by intent, not scope
- Merge Next Steps with `[Implement]` / `[Delegate]` tags preserved

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
- `scope` (resolved in Step 4), `depth` (resolved/auto-promoted), `stack = angular`

Print confirmation line.

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
**Blast Radius:** Narrow | Moderate | Wide | Critical
**Stack:** Angular <version> / <CD mode> / SSR: <enabled|disabled>
**Scope:** Core | +Sec | +Perf | +Obs | Full _(append `auto-escalated; signals: <list>` if applicable)_
**Depth:** standard | deep _(append `auto-promoted; Blast Radius: <level>` if applicable)_
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

- Issue: [Angular idiom name: bare `.subscribe()` without `takeUntilDestroyed`, `[innerHTML]` on user input, Default CD, missing `track`, `bypassSecurityTrustHtml` on user content, `environment.ts` secret, etc.]
- Impact: [user-visible or operational]
- System Risk: [why this is system-level]
- Fix: [concrete Angular change with code]

### [Recommend] file:line
- Issue / Impact / Fix

### [Question] file:line
- Question / Why it matters

_Use [Question] for genuine ambiguity, not as a softer Must._

## Architecture Notes

_Cross-cutting commentary. Reference findings by file:line; do not restate._

- Boundary impact / Coupling change / Drift detected
- SSR / hydration data flow: name systemic patterns ("components fetch in `ngOnInit` without `TransferState`") rather than producing N near-identical findings

## Maintainability Notes

- Over-engineering detected / Simplification opportunities

## Key Takeaways

2-4 bullets on systemic impact.

## Next Steps

On incremental rounds, prior-round Still open items are folded in with (open since round <N>) suffix and ordered by intent alongside new findings. Each item tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Implement]** [Recommend] old-list.component.ts:88 - missing track on @for (open since round 1)
3. **[Delegate]** [Recommend] [scope: design-system] - [one-line action]

_Omit if no actionable findings._
```

**Omit empty sections.**

### Streamlined output (low-risk short-circuit)

Drop Architecture Notes, Maintainability Notes, and any C/D-only sections. Keep Summary + Findings + Key Takeaways only.

## Self-Check

- [ ] Principles loaded; stack confirmed (Angular version, CD mode, SSR)
- [ ] Diff resolved and read once; pr-ref fetch surfaced to user when applicable; `review-precondition-check` ran (or handle received); current_head_sha and current_base_sha captured
- [ ] Step 3.5 - mode decided (full / incremental / no-op); auto-fetch attempted only when prior checkpoint exists; incremental range re-read when mode flipped to incremental; no-op path exits without writing the report
- [ ] Auto-escalation evaluated; promotions logged with firing signals
- [ ] Phase A: risk + blast radius stated before findings; low-risk short-circuit applied when applicable
- [ ] Phase B: atomic skills applied (component/signals/rxjs/service/data-fetching/state/forms/routing/nx/styling/i18n/testing); orphan checks (module-level mutable state, `[innerHTML]`/`bypassSecurityTrust*` upstream audit, env-ts secrets, open redirect, a11y, tests) raised
- [ ] Phase C-D-E: layering, AI smells, naming/length/logging applied (skipped if short-circuit)
- [ ] Every finding has label + `file:line` + actionable fix; every Must cites system risk
- [ ] Extra scopes ran in parallel with pre-resolved diff handle; failures noted as `Scope incomplete`
- [ ] Findings merged intent-ordered; raw subagent reports not appended
- [ ] Step 6.5 - on incremental rounds, review-prior-findings-reconcile ran; reconciliation table inserted; Still open rows folded into Next Steps with (open since round <N>) suffix
- [ ] Report written via `review-report-writer` with full checkpoint fields (mode, round, prior_head_sha when round > 1, head_sha, base_sha, scope, depth, stack); confirmation line printed

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase). The one allowed exception is `git fetch <remote> <branch>` in Step 3.5a, and only when a valid prior checkpoint exists.
- Auto-fetching on round 1 (no prior checkpoint) - keeps first-run behavior strictly read-only.
- Running incremental analysis against the full-range diff (must re-read scoped to `<prior_head_sha>...<head_sha>`).
- Writing the report on no-op exit (prior `head_sha == current head_sha`) - the file must stay byte-identical.
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`).
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
- Emitting a "Carry-Over Open Items" section - fold into Next Steps instead.
- Reviewing without reading full diff and commit log first
- Generic frontend feedback when an Angular idiom exists ("use `takeUntilDestroyed`", not "manage subscriptions")
- Sequential extra scopes that could parallelize
- Appending raw subagent reports instead of merging
- Approving Default CD, bare `.subscribe()` in components, `[innerHTML]` on user input, `bypassSecurityTrust*` without justification, or `environment.ts` secrets
