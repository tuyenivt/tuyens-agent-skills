---
name: task-angular-review
description: Angular code review: standalone, OnPush, signals, RxJS hygiene, bypassSecurityTrust, control-flow, SSR, a11y; spawns perf/security/obs subagents.
agent: angular-tech-lead
metadata:
  category: frontend
  tags: [angular, typescript, signals, rxjs, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.
>
> **Spec-aware mode:** If `--spec <slug>` or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles`. Cross-check every changed surface against `spec.md` / `plan.md`: each change must trace to an AC, NFR, or task; out-of-scope changes are **blockers**; missing in-scope coverage is a gap. Never edit spec artifacts.

# Angular Code Review

Staff-level Angular code review umbrella. Covers correctness, architecture, AI-quality, and maintainability through an Angular lens (standalone, OnPush, signals, RxJS hygiene, new control flow, functional guards/interceptors, `provideX`, `bypassSecurityTrust*`, SSR, a11y). Coordinates perf / security / observability subagents in parallel for extra scopes. Runs standalone with full PR/branch resolution.

## When to Use

- Pre-merge review on an Angular PR
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:**

- Pre-implementation design (`task-angular-implement`)
- Production incident (`/task-oncall-start`)
- Single-error debug (`task-angular-debug`)
- New-system architecture (`task-design-architecture`)
- Single-scope reviews - delegate to `task-angular-review-perf` / `-security` / `-observability`

## Depth Levels

| Depth | When | Runs |
|-------|------|------|
| `quick` | Time-constrained risk snapshot | Phase A + top 3 Phase B findings |
| `standard` | Default | Phases A-E |
| `deep` | Architecture PRs, post-incident, Principal sign-off | A-E + historical pattern matching + cross-PR context |

**Auto-promote to `deep`:** after Phase A, if `Blast Radius` is Wide or Critical and the user did not pass `quick`, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E (Angular-flavored) |
| + Perf | Core + `task-angular-review-perf` subagent |
| + Security | Core + `task-angular-review-security` subagent |
| + Observability | Core + `task-angular-review-observability` subagent |
| Full | Core + all three subagents in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals (Angular-tuned):**

- **+Security:** new `bypassSecurityTrust*`, new `[innerHTML]`, new functional interceptor / guard, auth or session config change, `Router.navigateByUrl` from user input, CSP change, new file upload, secret-like `environment.ts` entries
- **+Perf:** new route / lazy component, new heavy dependency, new component with Default change detection, new `@defer` block, new NgRx / signal store, new `HttpClient` call without caching, long list without `track`
- **+Observability:** new `ErrorHandler` provider, Sentry / RUM SDK init, `web-vitals` reporter, new logging utility, analytics call, new `TransferState` use
- **2+ categories -> Full**

## Invocation

| Form | Meaning |
|------|---------|
| `/task-angular-review` | Current branch vs base; fails fast on trunk |
| `/task-angular-review <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-angular-review pr-<N>` | PR head fetched into local branch `pr-<N>` (user runs the fetch) |

Pass `--base <branch>` when the PR was opened against a non-trunk base. Scope and depth flags compose: `/task-angular-review pr-50273 --base release/2026.05 +security deep`.

**No checkout required.** The workflow reads via ref-qualified diffs; never modifies the working tree.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as a subagent.

### Step 2 - Confirm Stack and Detect Configuration

Use skill: `stack-detect`. Accept pre-detected stack from parent if applicable. If not Angular, stop and recommend `/task-code-review`.

Detect and record for later phases:

- `Angular: <version>` (21+ enables `linkedSignal`, `resource`, signal-based forms; 20 stabilizes `effect` + signal inputs; 17/18 introduce new control flow + standalone-by-default)
- `Change detection: zone.js | zoneless` (look for `provideExperimentalZonelessChangeDetection` / `provideZonelessChangeDetection` in `app.config.ts`)
- `SSR: enabled | disabled` (`@angular/ssr` / `provideClientHydration`)

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Forward `--base` if passed. If it fails fast (dirty tree, trunk branch, missing PR ref, denied head-vs-current confirmation), surface verbatim and stop. Never run state-changing git commands from this workflow.

Once approved, read once and reuse:

- `git diff <base>...<head>`
- `git diff --name-status <base>...<head>`
- `git log --oneline <base>..<head>`

**Skip entirely** when invoked as a subagent and the parent passed the handle plus pre-read artifacts.

### Step 4 - Evaluate Scope Auto-Escalation

Scan the file list and diff for the signals listed under **Scope**. Log each fire as `signal: <category> -> <file:line>`. Then:

- Zero signals or `core-only` -> stay Core
- One signal category -> add matching extra scope
- 2+ categories -> promote to Full
- User passed an explicit scope -> respect it; still log signals so the Summary documents why

Surface the decision in Summary; if escalated, append `auto-escalated from Core; signals: <list>`.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk signals
- Use skill: `review-blast-radius` for failure propagation scope

Output risk level and blast radius before any findings.

**Auto-promote depth:** if Blast Radius is Wide / Critical and the user did not pass `quick`, set depth to `deep` and surface promotion in Summary **before** Phases B-E.

**Low-risk short-circuit:** if Risk Level is Low, Blast Radius is Narrow, **and** the change does not touch architecture-relevant files (auth config, HTTP interceptors, route config, `app.config.ts` / `app.providers.ts`, root `AppComponent`, shared services / NgRx stores), skip Phases C-D and produce a streamlined output with Phase B only.

### Phase B - Angular Correctness and Safety

Apply atomic skills. Each owns canonical patterns; this phase flags deviations:

- Use skill: `angular-component-patterns` - standalone, OnPush mandate, signal inputs over `@Input()`, `inject()` over constructor, `host: {}` over `@HostBinding/@HostListener` in new code
- Use skill: `angular-signals-patterns` - `computed` vs `effect` vs `linkedSignal`, `untracked` to break deps, `effect` cleanup, `toSignal` `initialValue` / `requireSync`, no `effect` writing back to a signal it reads
- Use skill: `angular-rxjs-patterns` - `takeUntilDestroyed` / `async` pipe / `toSignal`; no bare `.subscribe()` in component / directive / service; `catchError` on HTTP
- Use skill: `angular-service-patterns` - HTTP / business rules / cross-component state in services; functional guards / resolvers / interceptors; `provideHttpClient(withInterceptors([...]))`; `provideRouter(...)`
- Use skill: `angular-state-patterns` - URL / NgRx / signal / service categorization (filters / page / sort via route params + `withComponentInputBinding`, not a `signal`); no client-side cache of server state when transfer cache handles it
- Use skill: `angular-routing-patterns` if diff touches route config / lazy loading

**Additional Angular-specific checks the atomics don't own:**

- **Test coverage (named finding, not buried).** Logic added without Vitest / Jest / Karma + Angular Testing Library / TestBed coverage? At minimum `[Suggestion]`; escalate to `[High]` on critical paths: auth / session UI, HTTP interceptors, money / billing UI, form validation, multi-step flows, error handlers.
- **New control flow over structural directives.** New code using `*ngIf` / `*ngFor` / `*ngSwitch` is a finding; use `@if` / `@for` / `@switch`.
- **`@for` `track`.** Missing or `track $index` on reorderable / filterable / removable list is `[High]`.
- **`@defer` triggers + `@placeholder`.** Default `on idle` rarely intended; missing `@placeholder` causes CLS.
- **Standalone over NgModule.** New `@NgModule({...})` is `[High]`; existing modules fine to leave.
- **Reactive Forms.** Typed `FormGroup<{...}>` with `FormBuilder` and `Validators.*`; validators on the form, not in submit handlers.
- **Mutable module-level state.** `let cache = {}` at module top leaks across SSR requests - move to service or signal.
- **SSR (skip when disabled).** `provideClientHydration(withHttpTransferCacheOptions({...}))` for server-fetched data (request waterfall otherwise); guard `window` / `document` / `localStorage` / `IntersectionObserver` with `isPlatformBrowser` or `afterNextRender`.
- **Cross-cutting safety.** `[innerHTML]` on user-controllable content is `[Critical]` without `DomSanitizer.sanitize(SecurityContext.HTML, ...)`; every `bypassSecurityTrust*` needs a justifying comment and is `[Critical]` on user content; open redirect via `Router.navigateByUrl(query.returnTo)` / `window.location.href = userInput` without allowlist; `environment.ts` secrets compile into the client bundle (`[Critical]`); global `ErrorHandler` provider routes to Sentry / structured logging.
- **DI scope.** `providedIn: 'root'` for per-user state leaks across users without explicit reset.
- **TypeScript strict.** `strict: true` + `strictTemplates: true` not silently disabled; no `: any` inputs; `as any` outside test setup is a finding; inputs via `input<T>()` / `input.required<T>()` or `@Input() x!: T`.
- **Accessibility.** `<input>` paired with `<label>`; `aria-describedby` for errors; dialogs use CDK `Dialog` / `Overlay` (focus trap, return-focus, ARIA) over hand-rolled `<div>` modals; images use `<img ngSrc>` (NgOptimizedImage) or explicit `width`/`height`; `alt` present (`alt=""` for decorative); `priority` on LCP image.

### Phase C - Angular Architecture Guardrails

Use skill: `architecture-guardrail` for layer violations and coupling.

**Angular-specific:**

- **Layering:** business logic lives in route-level / container components / services, not in leaf / display components. Flag HTTP calls or business decisions in display components
- **Service / component boundary:** HTTP, business rules, cross-component state in services; flag direct `HttpClient.get` in components
- **Route-level cohesion:** `loadComponent` targets are thin orchestrators; flag route components > 200 lines of orchestration
- **Lazy-load discipline:** feature routes use `loadComponent` / `loadChildren`; flag eager `component:` for non-trivial routes
- **DI hierarchy:** `providedIn: 'root'` for app-wide singletons, route-scoped providers for per-route state, component providers for per-instance state. Flag root-scoped service that should be route-scoped (state bleeds), or component-scoped state hoisted unnecessarily
- **Configuration:** typed config via `InjectionToken<AppConfig>`; flag `environment.X` accessed across many components
- **Module boundaries:** feature-folder layout (`features/orders/{components,services,routes}.ts`); cross-feature imports go through a defined public surface (`features/orders/index.ts`)
- **Cross-boundary import:** component importing `fs`, `node:crypto`, ORM client is a bundle leak / SSR build error
- **NgModule sandwich:** legacy `AppModule` with > 30 imports / declarations is a standalone-migration target when the diff touches it

### Phase D - AI-Generated Code Quality

Use skill: `complexity-review` for verbosity, over-engineering, simplification.

**Angular AI smells:**

- **Pattern inflation:** generic `<DataTable<T>>` for one use case; content-projection trio when a flat input API would do; `@ViewChild` on every component (widens public surface)
- **Over-abstraction:** `BaseFormComponent` parent for 2 children; premature compound components; "headless" abstraction for one consumer
- **Speculative configurability:** inputs with documented-but-unused values; theme variants for a single design; "extensibility" hooks no caller uses
- **Redundant signal transforms:** input signal -> `linkedSignal` -> `effect` syncing them; use the input directly via `computed`. The "store input in writable signal" pattern is almost always wrong
- **`effect` for things that should be `computed`:** `effect(() => mySignal.set(otherSignal() + 1))` -> use `computed` (or `linkedSignal` if writable)
- **`effect` for things that should be event handlers:** `effect(() => { if (clicked()) handleClick() })` triggered by `(click)` setting `clicked` - just call `handleClick()` from the handler
- **`computed` chains on cheap values:** flag trivial `computed` chains that obscure data flow
- **Test verbosity:** 50-mock `TestBed.configureTestingModule` setups; mocking entire services when one method would do; full-component snapshots
- **Comment cruft:** comments restating input names; JSDoc on private helpers; `// TODO` without owner / date
- **`as any` / `as unknown as T` proliferation:** legitimate uses are rare; bypassing a real type bug is a finding
- **Try-catch noise in observables:** `pipe(catchError(e => { throw e }))` - delete; `pipe(catchError(e => of(null)))` swallows the error and loses telemetry - prefer `catchError(e => { logger.error(e); return throwError(() => e) })` or surface to global `ErrorHandler`

### Phase E - Maintainability and Clarity

Use skill: `ops-observability` for cross-cutting logging/metrics presence (depth belongs to `task-angular-review-observability`).

**Angular-specific:**

- **Naming:** components PascalCase + `Component` suffix (`OrderListComponent`); services with `Service`; pipes with `Pipe`; selectors kebab-case with project prefix (`app-order-list`); no abbreviations
- **File naming:** `order-list.component.ts/html/spec.ts` colocated; flag mixed-case or missing `.component` / `.service` / `.pipe` discriminators
- **Magic numbers / strings:** module-level constants or `InjectionToken`-injected config; route paths in a typed `app.routes.ts`
- **Hardcoded URLs / endpoints:** in env-driven config (`InjectionToken<AppConfig>`), not inline
- **Component length:** > 200 lines reviewed for extraction (sub-components, services, utilities)
- **Conditional rendering ladders:** > 3 nested `@if` / ternary -> extract sub-component or `computed` returning the right variant
- **Logging hygiene:** flag `console.log` in constructor / `ngOnInit` / template binding (runs every CD cycle, leaks PII), `console.log(JSON.stringify(largeObject))`, `console.error` outside error handlers / dev paths, production errors not routed through `ErrorHandler` to Sentry / RUM - depth belongs to the observability subagent

### Step 5 - Delegate Extra Scopes in Parallel

If scope is **Core only**, skip.

For each extra scope, spawn an independent subagent **in parallel** with the main thread:

| Scope | Subagents |
|-------|-----------|
| + Perf | `task-angular-review-perf` |
| + Security | `task-angular-review-security` |
| + Observability | `task-angular-review-observability` |
| Full | All three in parallel |

**Subagent prompt contract** - each must include:

- The resolved review target (`base_ref`, `head_ref`) plus the pre-read diff and commit log (no re-running git)
- The depth level
- Pre-confirmed stack (Angular) + detected configuration (Angular version, zoneless / zone.js, SSR enabled / disabled)
- Instruction to return findings in its own Output Format

**Failure isolation:** if a subagent fails or times out, continue with the rest. Note the missing scope in Summary.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate** cross-cutting findings (one entry citing all scopes that raised it)
- **Highest severity wins** (`Blocker` > `High` > `Suggestion` > `Question`). Map subagent scales: `Critical` -> `Blocker`, `High` -> `High`, `Medium` / `Low` -> `Suggestion`
- **Preserve `file:line` citations** from the originating subagent
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
**Stack Detected:** Angular <version> / TypeScript <version>
**Change detection:** zone.js | zoneless
**SSR:** enabled | disabled
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line

- Issue: [name the Angular idiom: bare `.subscribe()` without `takeUntilDestroyed`, `[innerHTML]` on user input, Default change detection, missing `track` on `@for`, `effect` writing back to a signal it reads, `bypassSecurityTrustHtml` on user content, `environment.ts` containing a secret, missing `TransferState` causing SSR re-fetch, etc.]
- Impact: [user-visible or operational]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete Angular change with code]

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
- SSR / hydration data flow: when 3+ findings cluster around HTTP calls re-running on hydration, name the systemic pattern here ("components fetch in `ngOnInit` without `TransferState`; enable HTTP transfer cache via `provideClientHydration(withHttpTransferCacheOptions({}))`") rather than producing N near-identical findings

## Maintainability Notes

_Same rule as Architecture Notes._

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

2-4 bullets on systemic impact and what to address before merge.

## Next Steps

Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action, e.g., "Add `takeUntilDestroyed()` to the `.subscribe()` in src/app/orders/order-list.component.ts:42 to prevent leaks across navigation"]
2. **[Delegate]** [High] [scope: design-system] - [one-line action]

_Omit if no actionable findings._
```

**Omit empty sections.** No Blocker heading if there are none.

### Streamlined output (low-risk short-circuit only)

When Phase A short-circuits (Risk Level: Low + Blast Radius: Narrow + no architecture-relevant files), drop Architecture Notes, Maintainability Notes, and any C/D-only sections:

```markdown
## Summary

**Assessment:** Approve | Discuss
**Risk Level:** Low
**Blast Radius:** Narrow
**Stack Detected:** Angular <version> / TypeScript <version>
**Change detection:** zone.js | zoneless
**SSR:** enabled | disabled
**Scope:** Core (low-risk short-circuit; Phases C-D skipped)
**Depth:** quick | standard

## Findings

### [High] file:line _(if any)_
- Issue:
- Impact:
- Fix:

### [Suggestion] file:line _(if any)_
- Improvement:

_Omit if no findings._

## Key Takeaways

- 1-2 bullets max - this is a low-risk PR.
```

## Rules

- Review whole-change system impact, not file-by-file
- Lead with risk; line-level findings follow
- Apply Angular conventions, not generic frontend conventions
- Provide actionable feedback with TypeScript / Angular code examples
- Default Core; auto-escalate; honor `core-only`
- Delegate perf / security / observability depth to subagents

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (or accepted from parent)
- [ ] Step 2: stack confirmed as Angular; Angular version, change-detection mode, SSR status recorded
- [ ] Step 3: `review-precondition-check` ran (or handle received); diff and commit log read once and reused; for `pr-ref` mode the fetch command was surfaced; when `head_matches_current` was false, explicit approval was obtained
- [ ] Step 4: scope auto-escalation evaluated; promotion (or `core-only` suppression) recorded with firing signals
- [ ] Phase A: risk level and blast radius stated before any finding; depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`; low-risk short-circuit applied when applicable
- [ ] Phase B: atomic skills applied (`angular-component-patterns`, `angular-signals-patterns`, `angular-rxjs-patterns`, `angular-service-patterns`, `angular-state-patterns`, plus `angular-routing-patterns` when relevant); test coverage, new control flow, `@for` `track`, `@defer` placeholder, standalone, SSR `TransferState` / browser-API guards, `[innerHTML]` / `bypassSecurityTrust*` / open-redirect / `environment.ts` secret, TS strict, a11y checked
- [ ] Phase C: layering, service/component boundary, lazy loading, DI hierarchy, configuration, module boundaries, cross-boundary imports, NgModule sandwich applied
- [ ] Phase D: `complexity-review` applied; Angular AI smells covered (pattern inflation, over-abstraction, redundant signal transforms, `effect` misapplication, `computed` overuse, `as any`, observable try-catch noise)
- [ ] Phase E: naming, file naming, magic numbers, component length, conditional ladders, logging hygiene
- [ ] Missing tests raised as a named finding (not buried)
- [ ] Every Blocker states a system risk
- [ ] Every finding has label + `file:line` + actionable Angular fix
- [ ] If `--spec` passed: every finding traces to AC/NFR/task or is flagged as out-of-scope blocker
- [ ] Step 5: extra scopes ran in parallel with the pre-resolved diff/log handle plus configuration detection
- [ ] Step 6: subagent findings merged into one severity-ordered Findings list; raw reports not appended; failed/missing scope noted as `Scope incomplete: <scope>`; Next Steps tagged `[Implement]` / `[Delegate]` and ordered by severity
- [ ] Step 7: review report written via `review-report-writer`; confirmation line printed

## Avoid

- `git fetch` / `git checkout` from this workflow - user runs these
- Reviewing without reading the full diff and commit log first
- Generic frontend conventions when an Angular idiom exists ("use `takeUntilDestroyed`", not "manage subscriptions"; "extract to a service", not "extract to a helper")
- Nitpicking style where no project standard exists
- Vague feedback ("this could be better")
- Blocking on personal preference
- Running extra scopes when `core-only` was passed
- Duplicating perf / security / observability depth here when the dedicated Angular subagent owns them
- Sequential extra scopes that could parallelize
- Appending raw subagent reports instead of merging
- Recommending Default change detection, bare `.subscribe()` in components, `[innerHTML]` on user input, `bypassSecurityTrust*` without justification, or `environment.ts` for secrets as acceptable
