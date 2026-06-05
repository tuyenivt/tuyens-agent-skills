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

> **Spec-aware mode:** If `--spec <slug>` or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble`. Every change must trace to an AC, NFR, or task; out-of-scope changes are **blockers**.

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
| `quick` | Time-constrained risk snapshot | Phase A + top 3 Phase B findings |
| `standard` | Default | Phases A-E |
| `deep` | Architecture PRs, post-incident | A-E + historical pattern matching |

**Auto-promote to `deep`:** evaluated once in Phase A after Blast Radius is known. Surface as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E (Angular-flavored) |
| +Perf / +Security / +Observability | Core + matching `task-angular-review-*` subagent |
| Full | Core + all three subagents in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress escalation.

**Auto-escalation signals:**

- **+Security:** new `bypassSecurityTrust*`, new `[innerHTML]`, new functional interceptor / guard, auth config change, `Router.navigateByUrl` from user input, CSP change, secret-like `environment.ts` entries
- **+Perf:** new lazy route, heavy dependency, Default CD, new `@defer`, new store, `HttpClient` call without caching, long list without `track`
- **+Observability:** new `ErrorHandler`, Sentry / RUM SDK init, `web-vitals` reporter, analytics call, new `TransferState`
- **2+ categories -> Full**

## Invocation

| Form | Meaning |
|------|---------|
| `/task-angular-review` | Current branch vs base; fails fast on trunk |
| `/task-angular-review <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-angular-review pr-<N>` | PR head fetched into `pr-<N>` (user runs fetch) |

`--base <branch>` overrides default base. Scope and depth flags compose: `/task-angular-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as a subagent.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. If not Angular, stop and recommend `/task-code-review`. Record `Angular: <version>`, `Change detection: zone.js | zoneless`, `SSR: enabled | disabled`, `Workspace: CLI | Nx`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read once and reuse: `git diff <base>...<head>`, `git diff --name-status <base>...<head>`, `git log --oneline <base>..<head>`. Skip when invoked as subagent with pre-read artifacts.

### Step 4 - Evaluate Auto-Escalation

Scan diff for signals listed under **Scope**. Log each fire as `signal: <category> -> <file:line>`. Apply rules: zero/`core-only` -> Core; one category -> add scope; 2+ -> Full. User-passed explicit scope wins; signals still logged.

### Phase A - PR Risk Snapshot

Use skills: `review-pr-risk`, `review-blast-radius`. Output risk level and blast radius before any findings.

**Auto-promote depth:** if Blast Radius Wide/Critical and user did not pass `quick`, set depth to `deep`. Log the promotion once (here, not in Step 4).

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
- `angular-testing-patterns` - coverage for changes (when diff adds logic)

**Orphan checks (no atomic owns - cross-cutting only):**

Control flow, `@defer`, NgModule, content projection, OnPush -> `angular-component-patterns`. Reactive Forms -> `angular-forms-patterns`. SSR hydration + `withHttpTransferCacheOptions` -> `angular-routing-patterns` + `angular-data-fetching`. Defer to those atomics, do not duplicate.

- **Mutable module-level state.** `let cache = {}` leaks across SSR requests.
- **Cross-cutting safety.** `[innerHTML]` on user content without sanitizer = `[Blocker]`; `bypassSecurityTrust*` needs justification + is `[Blocker]` on user content (audit the *upstream* - input must be DOMPurify-sanitized or server-trusted); open redirect via `Router.navigateByUrl(query.returnTo)` without allowlist = `[Blocker]`; `environment.ts` privileged secrets are `[Blocker]` (compile into client bundle).
- **TypeScript strict.** No `: any` inputs; `as any` outside test setup is a finding.
- **Accessibility.** `<input>` paired with `<label>`; dialogs use CDK `Dialog`; images use `NgOptimizedImage` or explicit `width`/`height`; `alt` present.
- **Test coverage for logic added.** Missing tests is a named finding (`[Suggestion]`; `[High]` on critical paths: auth, billing UI, form validation, error handlers).

### Phase C - Angular Architecture Guardrails

Use skill: `architecture-guardrail`.

- **Layering:** business logic in container/services, not leaf components. HTTP in services, not components.
- **Lazy-load:** feature routes use `loadComponent` / `loadChildren`; eager `component:` for non-trivial routes is a finding.
- **DI hierarchy:** `providedIn: 'root'` for app-wide singletons, route-scoped for per-route state, component-scoped for per-instance. Root-scoped per-user state without explicit logout reset bleeds.
- **Configuration:** typed config via `InjectionToken<AppConfig>`; `environment.X` sprinkled across components is a finding.
- **Module boundaries:** feature folders with defined public surface; cross-feature imports through `index.ts`. In Nx, missing `tags` on a new project or violation of `@nx/enforce-module-boundaries` is `[High]` - see `angular-nx-patterns`.
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
| +Security | `task-angular-review-security` |
| +Observability | `task-angular-review-observability` |
| Full | All three in parallel |

**Subagent prompt:** resolved review target (`base_ref`, `head_ref`), pre-read diff + commit log, depth level, pre-confirmed stack + detected configuration. Instruction to return findings in its own Output Format.

**Failure isolation:** if a subagent fails or times out, continue. Note `Scope incomplete: <scope>` in Summary.

### Step 6 - Synthesize (only if Step 5 ran)

Merge into the single Output Format below. Do not append raw subagent reports.

- Dedupe key: identical `file:line` + same issue name = one finding (cite all scopes that raised it). Keep the most specific `Fix` text across versions.
- Severity merge: Map subagent tiers to parent labels: `Critical` → `[Blocker]`, `High` → `[High]`, `Medium`/`Low` → `[Suggestion]`. Highest wins on collisions.
- Preserve `file:line` citations
- Order by severity, not scope
- Merge Next Steps with `[Implement]` / `[Delegate]` tags preserved

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review`. Print confirmation line.

## Feedback Labels

| Label | Meaning |
|-------|---------|
| [Blocker] | Must fix before merge - correctness / risk |
| [High] | Should fix - significant impact |
| [Suggestion] | Would improve - non-blocking |
| [Question] | Need clarity from author |

No `[Nitpick]` or `[Praise]`.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack:** Angular <version> / <CD mode> / SSR: <enabled|disabled>
**Scope:** Core | +Security | +Perf | +Observability | Full _(append `auto-escalated; signals: <list>` if applicable)_
**Depth:** quick | standard | deep _(append `auto-promoted; Blast Radius: <level>` if applicable)_

## High-Impact Findings

### [Blocker] file:line

- Issue: [Angular idiom name: bare `.subscribe()` without `takeUntilDestroyed`, `[innerHTML]` on user input, Default CD, missing `track`, `bypassSecurityTrustHtml` on user content, `environment.ts` secret, etc.]
- Impact: [user-visible or operational]
- System Risk: [why this is system-level]
- Fix: [concrete Angular change with code]

### [High] file:line
- Issue / Impact / Fix

### [Suggestion] file:line
- Improvement

### [Question] file:line
- Question / Why it matters

_Use [Question] for genuine ambiguity, not as a softer Blocker._

## Architecture Notes

_Cross-cutting commentary. Reference findings by file:line; do not restate._

- Boundary impact / Coupling change / Drift detected
- SSR / hydration data flow: name systemic patterns ("components fetch in `ngOnInit` without `TransferState`") rather than producing N near-identical findings

## Maintainability Notes

- Over-engineering detected / Simplification opportunities

## Key Takeaways

2-4 bullets on systemic impact.

## Next Steps

Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action]
2. **[Delegate]** [High] [scope: design-system] - [one-line action]

_Omit if no actionable findings._
```

**Omit empty sections.**

### Streamlined output (low-risk short-circuit)

Drop Architecture Notes, Maintainability Notes, and any C/D-only sections. Keep Summary + Findings + Key Takeaways only.

## Self-Check

- [ ] Principles loaded; stack confirmed (Angular version, CD mode, SSR)
- [ ] Diff resolved and read once; pr-ref fetch surfaced to user when applicable
- [ ] Auto-escalation evaluated; promotions logged with firing signals
- [ ] Phase A: risk + blast radius stated before findings; low-risk short-circuit applied when applicable
- [ ] Phase B: atomic skills applied (component/signals/rxjs/service/data-fetching/state/forms/routing/nx/styling/testing); orphan checks (module-level mutable state, `[innerHTML]`/`bypassSecurityTrust*` upstream audit, env-ts secrets, open redirect, a11y, tests) raised
- [ ] Phase C-D-E: layering, AI smells, naming/length/logging applied (skipped if short-circuit)
- [ ] Every finding has label + `file:line` + actionable fix; every Blocker states system risk
- [ ] Extra scopes ran in parallel with pre-resolved diff handle; failures noted as `Scope incomplete`
- [ ] Findings merged severity-ordered; raw subagent reports not appended
- [ ] Report written; confirmation line printed

## Avoid

- `git fetch` / `git checkout` from this workflow - user runs these
- Reviewing without reading full diff and commit log first
- Generic frontend feedback when an Angular idiom exists ("use `takeUntilDestroyed`", not "manage subscriptions")
- Sequential extra scopes that could parallelize
- Appending raw subagent reports instead of merging
- Approving Default CD, bare `.subscribe()` in components, `[innerHTML]` on user input, `bypassSecurityTrust*` without justification, or `environment.ts` secrets
