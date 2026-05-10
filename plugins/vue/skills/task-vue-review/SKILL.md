---
name: task-vue-review
description: Vue / Nuxt code review: Composition API, watchers, reactivity, v-html XSS, Pinia, Nitro, SSR hydration; spawns perf/security/obs subagents.
agent: vue-tech-lead
metadata:
  category: frontend
  tags: [vue, typescript, nuxt, vite, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the diff under review, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an acceptance criterion, NFR, or task; flag changes that touch out-of-scope items as **blockers**; flag missing coverage of in-scope acceptance criteria as gaps. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow.

# Vue Code Review

## Purpose

Vue-aware staff-level code review umbrella. Replaces the generic Phase A-E flow with Vue-specific correctness, architecture, AI-quality, and maintainability checks (Composition API discipline, `<script setup>` shape, reactivity correctness (deep `reactive` cost, destructure de-reactivity, watcher cascades), `v-for` `:key` correctness, state categorization (URL vs Pinia vs local), prop drilling smells, missing Zod validation on Nitro endpoints, `v-html` audit, accessibility regressions, anemic prop interfaces). Coordinates Vue-specific perf / security / observability subagents in parallel for extra scopes.

This workflow is the stack-specific delegate of `task-code-review` for Vue. The core workflow's contract (depth levels, scope auto-escalation, low-risk short-circuit, output format) is preserved. **Runs standalone** with full PR/branch resolution - the core dispatcher is optional.

## When to Use

- Reviewing a Nuxt or Vite + Vue PR before merge
- Post-AI-generation quality gate on a Vue change set
- Architecture drift detection in a Vue codebase
- Pre-merge risk assessment on a Vue branch

**Not for:**

- Pre-implementation feature design (use `task-vue-implement`)
- Active production incident triage (use `/task-oncall-start`)
- Single-error debugging (use `task-vue-debug`)
- Architecture/design review of a new system (use `task-design-architecture`)
- Single-scope reviews when only one concern matters - delegate directly to `task-vue-review-perf`, `task-vue-review-security`, or `task-vue-review-observability`

## Depth Levels

Mirrors `task-code-review`:

| Depth      | When to Use                                                               | What Runs                                                    |
| ---------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `quick`    | "Is this safe to merge?" - fast risk snapshot for time-constrained review | Risk snapshot + top 3 findings only (Phases A and B summary) |
| `standard` | Default - full Vue staff-level review                                     | Phases A-E                                                   |
| `deep`     | Architectural PRs, post-incident change review, or Principal sign-off     | Phases A-E + historical pattern matching + cross-PR context  |

Default: `standard`.

**Auto-promote to `deep`:** After Phase A computes blast radius, if `Blast Radius` is `Wide` or `Critical` and the user did not explicitly pass `quick`, promote depth from `standard` to `deep` automatically. Surface in Summary as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                                |
| --------------- | ------------------------------------------------------------------------ |
| Core            | Phases A-E only (Vue-flavored)                                           |
| + Perf          | Core + parallel subagent: `task-vue-review-perf`                         |
| + Security      | Core + parallel subagent: `task-vue-review-security`                     |
| + Observability | Core + parallel subagent: `task-vue-review-observability`                |
| Full            | Core + Performance + Security + Observability (3 parallel Vue subagents) |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Scope auto-escalation signals (Vue-tuned):**

- New Nitro endpoint / `server/middleware/*` change, `v-html` introduction, auth library / session config change, `NUXT_PUBLIC_*` / `VITE_*` additions, new file upload, new `navigateTo(...)` from user input, CSP / `routeRules.headers` change → auto-add **+Security**
- New page / layout, new heavy component, new client-side dependency in `dependencies`, new TanStack Query / Pinia store, new `<NuxtImg>` / `@nuxt/fonts` change, new lazy component / async chunk, `routeRules` change, new long list rendering → auto-add **+Perf**
- New Nuxt plugin / `plugins/*.ts`, new Sentry / RUM SDK init, new `web-vitals` reporter, new error boundary / `error.vue`, new logging utility, new analytics call → auto-add **+Observability**
- Two or more signal categories present → promote to **Full**

## Invocation

The slash command accepts an optional argument identifying the diff to review:

| Invocation                  | Meaning                                                                                                                                                                               |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-vue-review`          | Review current branch vs its base - fails fast if on a trunk branch (`main`/`master`/`develop`); commit or switch to a feature branch first                                           |
| `/task-vue-review <branch>` | Review `<branch>` vs its base (3-dot diff) - cross-review a teammate's branch checked out locally, or self-review a named branch from any session                                     |
| `/task-vue-review pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` - run `git fetch origin pull/<N>/head:pr-<N>` first (user runs it; see `review-precondition-check` for GitLab/Bitbucket variants) |

**No checkout required.** Stay on your current branch; the workflow reads git history via ref-qualified diffs.

**Explicit base override.** When the PR was opened against a non-trunk base branch, pass `--base <branch>`.

Examples:

- `/task-vue-review pr-123 --base release/2026.05`
- `/task-vue-review feature/x --base develop`

Scope and depth flags compose: `/task-vue-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Vue. If invoked as a delegate of `task-code-review` (parent already detected Vue), accept the pre-detected stack and skip re-detection. If the detected stack is not Vue, stop and tell the user to invoke `/task-code-review` instead.

Detect framework: Nuxt 3 vs Vite + Vue Router. Record `Framework: ...`, `Vue: <version>`. Each Phase B / C / D / E checklist below branches on this signal where the idiom differs.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). Forward `--base <branch>` if the user passed it.

If the precondition check stops with a fail-fast message, surface it verbatim and stop. Do not run any state-changing git command.

Once approved, read the diff and commit log directly using the returned refs:

- Diff: `git diff <base_ref>...<head_ref>`
- Files changed: `git diff --name-status <base_ref>...<head_ref>`
- Commit log: `git log --oneline <base_ref>..<head_ref>`

All subsequent phases operate on this read-once diff and log; do not re-derive them.

**Skip this entire step** when invoked as a subagent of `task-code-review` and the parent passed the precondition handle plus pre-read diff and commit log. Reuse the parent's artifacts.

### Step 3 - Evaluate Scope Auto-Escalation

Scan the file list and diff content for the auto-escalation signals listed under **Scope** above. For each signal that fires, log a one-liner: `signal: <category> -> <file:line>`. Then decide:

- Zero signals or user passed `core-only` → stay on Core
- One signal category → add the matching extra scope
- Two or more signal categories → promote to Full
- User passed an explicit scope → respect it (do not downgrade), but record signals so the Summary documents why

Surface the decision in the Summary's `Scope:` field. If escalated, append `auto-escalated from Core; signals: <list>`.

### Phase A - PR Risk Snapshot (run first)

- Use skill: `review-pr-risk` to evaluate cross-cutting risk signals
- Use skill: `review-blast-radius` to assess failure propagation scope
- Output risk level and blast radius before proceeding to findings

**Low-risk short-circuit:** If Phase A yields Risk Level: Low and Blast Radius: Narrow, **and** the change does not touch architecture-relevant files (auth config, server middleware, route layouts, shared providers / Pinia stores, `nuxt.config.ts`, `vite.config.ts`, top-level `app.vue` / `App.vue`), skip Phases C-D and produce a streamlined output with Phase B findings only.

### Step 3.5 - Re-evaluate Depth After Phase A

If `Blast Radius` is `Wide` or `Critical` and the user did not explicitly pass `quick`, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)` in the Summary. Do this **before** launching Phases B-E so deep-only behaviors are in scope.

### Phase B - Vue Correctness and Safety

Logical correctness, error handling completeness, edge cases affecting UI integrity, backward compatibility, hydration correctness, accessibility - through a Vue lens.

**Test coverage finding:** If the PR adds or modifies logic without corresponding Vitest coverage, raise this as an explicit finding. At minimum a [Suggestion]; escalate to [High] when the change is in a critical path - any of: authentication / session UI, Nitro endpoints, money / billing UI, form validation, multi-step flows, error boundaries. Do not bury this finding in Key Takeaways.

Canonical patterns live in `vue-component-patterns`, `vue-composables-patterns`, `vue-data-fetching`, `vue-state-patterns`, `vue-nuxt-patterns`. This phase scans for diff-level findings:

**Vue correctness (both frameworks):**

- [ ] **TypeScript strict / typed props**: `strict: true` not silently disabled; `as any` outside test setup; `defineProps<{...}>` not `defineProps(['x'])`
- [ ] **`<script setup>` over Options API** for new components; mixed-style PRs flagged unless the project documents Options API
- [ ] **Composition API discipline**: composables called at top level (no conditions / loops / after early returns); `use<Noun>` naming - see `vue-composables-patterns`
- [ ] **Watcher discipline**: `watch` used for derived state (use `computed`) or for event handling (call the handler directly); `deep: true` on wide objects; missing `onUnmounted` / `onScopeDispose` cleanup for `onMounted`-registered subscriptions / observers / intervals (memory leak [High])
- [ ] **Reactivity loss via destructure / spread**: `const { a } = reactive({...})`, `{ ...state }`. Flag patterns expecting reactivity to survive (Vue 3.5+ props destructure is the exception - it compiles to accessors)
- [ ] **`v-for` keys**: missing or `:key="index"` on a reorderable / filterable / removable list breaks reconciliation
- [ ] **`v-for` + `v-if` on same element**: filter via `computed` first
- [ ] **Reactivity primitives**: `reactive(0)` / `reactive(['a','b'])` smells; deep `reactive(largeObject)` for read-only data should be `shallowRef` / `shallowReactive`

**Nuxt-specific correctness (skip on Vite):**

- [ ] **Hydration safety**: browser-only APIs (`window`, `document`, `localStorage`, `IntersectionObserver`) at top level of `<script setup>` crash SSR - wrap in `onMounted` or guard with `import.meta.client`. Async `<script setup>` (`await useFetch`) needs a `<Suspense>` ancestor. Inherently client-only components → `<ClientOnly>` with `<template #fallback>` to avoid CLS
- [ ] **Nitro endpoint input + auth**: `readValidatedBody(event, Schema.parse)` / `getValidatedQuery(event, Schema.parse)` at top before any DB call (raw `readBody` flowing into `prisma.x.update({ data })` is mass assignment, [Blocker]). Mutating endpoints call `requireUserSession(event)` and verify object-level ownership (IDOR). New / removed exclusions in `server/middleware/auth.ts` without security comment is [High]
- [ ] **Pinia / `useState` SSR ORM-leak audit** (Nuxt, [Critical]): a store / state populated server-side with a full ORM row serializes into `__NUXT__` payload visible in client HTML. Audit for sensitive fields - `passwordHash`, `mfaSecret`, `apiToken`, `refreshToken`, `internal*`, `*Secret`, `recoveryCode`. Project to a DTO at the data layer (`prisma.user.findUnique({ where, select: {...} })`) or before placing in the store

**Vue cross-cutting safety:**

- [ ] **`v-html` on user input** without sanitizer (`DOMPurify` / `sanitize-html`) - [Critical] when content path is user-controllable
- [ ] **Open redirect**: `navigateTo(query.returnTo)` / `router.push(returnTo)` without allowlist or `url.startsWith('/') && !url.startsWith('//')`
- [ ] **`NUXT_PUBLIC_*` / `VITE_*` for secrets** (API keys, DB URLs, signing secrets) - compiled into client bundle, [Critical]; server-only secrets live in `runtimeConfig`
- [ ] **State categorization**: filter / page / sort in `ref` instead of route query (breaks deep-linking, refresh, back-button); client-side caching of server state when `useFetch` / TanStack Query handle it. See `vue-state-patterns`
- [ ] **Mutable module-level state** (`let cache = {}` mutated by render / events) - in SSR (Nuxt) leaks across requests
- [ ] **Provide / inject re-render storm**: non-stable reactive provide value propagates to every consumer
- [ ] **Error boundaries**: non-trivial render / external data wrapped (Nuxt `error.vue` per-segment; Vue 3 `errorCaptured`; Vite explicit boundary). A bare render-path `throw` crashes the tree

**Accessibility:**

- [ ] **Form a11y**: `<input>` with associated `<label>`, `aria-describedby` for error messages, accessible submit name, `required` / `aria-required` with surfaced validation
- [ ] **Interactive a11y**: dialogs use `<dialog>` or full ARIA (`role="dialog"`, `aria-modal`, focus trap, return-focus); reach for Headless UI / Reka UI / shadcn-vue before reinventing key handling
- [ ] **Images**: `<NuxtImg>` or explicit `width`/`height` on `<img>` (CLS); `alt` present (`alt=""` for decorative)

### Phase C - Vue Architecture Guardrails

Use skill: `architecture-guardrail` to detect layer violations, new coupling, circular dependency risk, bypassing abstractions, boundary erosion.

**Vue-specific architecture checks:**

- [ ] **Component layering**: presentational vs container distinction not strict, but business logic does not live inside `<Card>` / `<Button>` / leaf components - it lives in pages / containers / composables. Flag fetch calls inside leaf components, business decisions in display components
- [ ] **Server / client boundary discipline (Nuxt)**: data fetching lives in `useFetch` / `useAsyncData` (which run server-side during SSR and reuse on hydration); flag `onMounted(() => fetch(...))` for initial-render data when `useFetch` would serve via SSR
- [ ] **Composable discipline**: a composable that takes 8 different params and returns 12 fields signals it should be split. Flag god composables. Composables should be focused and named for the concern
- [ ] **Prop drilling depth**: a prop threaded through 4+ component layers is a smell - hoist to `provide` / `inject`, a Pinia store, or co-locate. Flag chains of pure pass-through props
- [ ] **`provide` overuse**: `provide` for state that only one consumer reads (where prop / lift would suffice) - flag as unnecessary indirection
- [ ] **Routing discipline**: route components are thin (delegate to feature components); business logic is not in `pages/**/*.vue` directly. Flag route files with > 100 lines of orchestration
- [ ] **Settings / config discipline**: typed config (Nuxt: `runtimeConfig` typed via `RuntimeConfig` interface; Vite: `import.meta.env` accessed via a single typed `config.ts` with Zod) - flag `import.meta.env.X` / `useRuntimeConfig().public.X` sprinkled across components
- [ ] **Module / package boundaries**: feature-folder layout (`features/orders/{components,composables,api}.ts`) preferred over flat `components/`, `composables/` for everything; cross-feature imports go through a defined public surface
- [ ] **Server-only utility imported into Client component (Nuxt)**: a `.vue` file or composable that imports `fs`, `node:crypto`, ORM client into client-evaluated code is a build error / bundle leak - flag any cross-boundary import. Server-only modules belong in `server/**/*.ts`
- [ ] **Plugin sandwich**: more than ~5 nested `app.use(plugin)` calls in `plugins/` or `main.ts` signals a `<Providers>` consolidation. Not a hard rule, but flag for cleanup

### Phase D - AI-Generated Code Quality Control

Use skill: `complexity-review` to detect verbosity, over-engineering, and simplification opportunities.

**Vue-specific AI smells:**

- [ ] **Pattern inflation**: generic `<DataTable<T>>` for a single use case where a typed concrete component would suffice; render-prop / scoped-slot trio when a flat prop API would do; `defineExpose` on every component (each `defineExpose` widens the public surface)
- [ ] **Over-abstraction**: `BaseFormField` parent component for 2 children; premature compound components when a flat prop API would do; "headless" abstraction for one consumer
- [ ] **Speculative configurability**: props with documented but unused values; theme variants for a single design; "extensibility" hooks that no caller uses
- [ ] **Redundant prop transforms**: prop → `ref` initialized from prop → `watch` syncing them - just use the prop directly via `computed` or destructure. The "store prop in state" pattern is almost always wrong
- [ ] **`watch` for things that should be event handlers**: `watch(clicked, () => { if (clicked) handleClick() })` triggered by setting `clicked` in `@click` - just call `handleClick()` directly
- [ ] **`computed` everywhere on cheap values**: `computed(() => count.value + 1)` is fine but flag chains of trivial `computed` that obscure the data flow
- [ ] **Test verbosity**: `mount(Component, { global: { stubs: { ... 50 stubs ... } } })` setup chains; mocking the entire module when a single function would do; full-tree snapshots
- [ ] **Comment cruft**: comments restating prop names; JSDoc on private internal helpers; `// TODO` markers without owner / date
- [ ] **`as any` / `as unknown as T` proliferation**: legitimate uses are rare; `as any` to bypass a real type bug is a finding
- [ ] **Try-catch noise**: `try { await x() } catch (e) { throw e }` - delete; `try { ... } catch (e) { error.value = e.message }` loses the cause - use `error.value = e instanceof Error ? e : new Error(String(e))`
- [ ] **Anonymous default exports for components**: `export default {}` (Options API) without `name` makes stack traces unhelpful and breaks Vue DevTools display name. `<script setup>` infers the name from the filename - flag SFCs whose filename is `Index.vue` deep inside a feature folder (DevTools shows "Index" everywhere)

### Phase E - Vue Maintainability and Clarity

Naming that obscures intent, mixed responsibilities, large unreviewable chunks, hardcoded values that should be config or constants.

**Vue-specific maintainability checks:**

- [ ] **Naming conventions**: components in PascalCase (`OrderList.vue`); composables `use<Noun>` (`useOrderFilters`); event names kebab-case (`@order-saved`); no abbreviations (`OrdLst.vue` is wrong)
- [ ] **File / component co-location**: each feature has its components, composables, types, tests co-located in a folder; not scattered across `components/`, `composables/`, `types/` for one feature
- [ ] **Magic numbers / strings**: extracted to module-level constants or config; route paths declared in a typed `routes.ts` rather than string literals scattered
- [ ] **Hardcoded URLs / API endpoints**: in env vars / `runtimeConfig`, not inline (allows env-specific behavior)
- [ ] **Component length**: components > 200 lines reviewed for extraction; extract sub-components, composables, or move logic to utility functions
- [ ] **Conditional rendering ladders**: > 3 nested `v-if` / ternary in template → extract to a sub-component or a `computed` returning the right variant; readability degrades fast
- [ ] **Logging / error reporting hygiene**: surface obvious offenders as Core findings - `console.log` in `<script setup>` body (called on every component setup, leaks PII into devtools and may be picked up by RUM forwarders), `console.log(JSON.stringify(largeObject))` of any non-trivial payload, `console.error` outside of error boundary fallbacks / dev paths, production errors not routed through Sentry / RUM SDK. The observability subagent owns depth (sample rates, attribution, instrumentation API); do not duplicate that audit here

Use skill: `frontend-coding-standards` if the project has one (otherwise rely on TS strict + ESLint + project-specific conventions).
Use skill: `ops-observability` for cross-cutting logging/metrics presence (the `task-vue-review-observability` subagent owns depth).

### Step 4 - Delegate Extra Scopes in Parallel (if scope includes)

If scope is **Core only**, skip this step.

For any selected extra scope, spawn an independent subagent **in parallel** with the main thread (which continues running Phases A-E for Core).

| Scope                | Subagents spawned                                                                                                   |
| -------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Core + Perf          | 1 subagent running `task-vue-review-perf`                                                                           |
| Core + Security      | 1 subagent running `task-vue-review-security`                                                                       |
| Core + Observability | 1 subagent running `task-vue-review-observability`                                                                  |
| Full                 | 3 subagents running `task-vue-review-perf`, `task-vue-review-security`, `task-vue-review-observability` in parallel |

**Subagent prompt contract.** Each subagent prompt must include:

- The resolved review target from Step 2 (`base_ref`, `head_ref`) plus the already-read diff and commit log
- The depth level (`quick` | `standard` | `deep`)
- The pre-confirmed stack (Vue) and detected framework (Nuxt / Vite) so the subagent skips its own `stack-detect` and framework branching
- Instruction to return findings using its own skill's Output Format

**Failure isolation.** If a subagent fails or times out, continue with the remaining results. Note the missing scope in the synthesized output rather than blocking the whole review.

### Step 5 - Synthesize (only if Step 4 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate cross-cutting findings.** The same issue may surface in multiple scopes (e.g., a `v-html` introduction flagged by both Core/Phase B and Security). Keep one entry, citing all scopes that raised it.
- **Severity wins.** When the same finding has different labels across scopes, use the highest severity (`Blocker` > `High` > `Suggestion` > `Question`).
- **Preserve `file:line` citations** from the originating subagent.
- **Order findings by severity, not by scope.**
- **Note missing scopes.** If any subagent failed, add `Scope incomplete: <scope>` under Summary.
- **Merge Next Steps.** Combine Core Next Steps with each subagent's Next Steps into one prioritized list. Preserve `[Implement]` / `[Delegate]` tags; deduplicate items mapping to the same fix; re-sort by severity.

## Feedback Labels

| Label        | Meaning                                     | Required |
| ------------ | ------------------------------------------- | -------- |
| [Blocker]    | Must fix before merge - correctness or risk | Yes      |
| [High]       | Should fix - significant impact or smell    | Strong   |
| [Suggestion] | Would improve - non-blocking                | No       |
| [Question]   | Need clarity from author                    | Clarify  |

No `[Nitpick]` or `[Praise]` labels.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Vue <version> / TypeScript <version>
**Framework:** Nuxt 3 <version> | Vite + Vue Router <version>
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line

- Issue: [what is wrong - name the Vue idiom: deep `reactive` over a 5K-row dataset, missing Zod validation on Nitro endpoint, Pinia store leaking `passwordHash` via SSR payload, watcher cascade through three ticks, missing `:key`, `v-html` on user input, `NUXT_PUBLIC_` secret leak, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is a system-level concern, not just a local bug]
- Fix: [concrete Vue change with code example]

### [High] file:line

- Issue:
- Impact:
- Fix:

### [Suggestion] file:line

- Improvement:

### [Question] file:line

- Question: [what is ambiguous in the change]
- Why it matters: [what the right next step depends on - author intent, business rule, deployment topology, etc.]

_Use [Question] when the change is genuinely ambiguous. Do NOT use it as a softer Blocker._

## Architecture Notes

_Summary commentary on systemic patterns. **Do not restate individual findings here.** If a pattern is severe enough to be a finding, keep it in Findings and reference it by file:line._

- Boundary impact:
- Coupling change:
- Drift detected:
- SSR / hydration data flow: _(Nuxt)_ when 3+ findings cluster around ORM rows being passed across SSR into client payload, name the systemic pattern here ("Nuxt pages consistently place full ORM rows in Pinia stores; introduce a DTO layer at server/api/_dto.ts") rather than producing N near-identical findings

## Maintainability Notes

_Same rule as Architecture Notes._

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

- 2-4 concise bullets summarizing systemic impact and what to address before merge.

## Next Steps

Prioritized action list. Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action, e.g., "Wrap server/api/account.put.ts body with `readValidatedBody(event, AccountUpdateSchema.parse)`; whitelist `name`, `email`, `bio`"]
2. **[Delegate]** [High] [scope: design-system] - [one-line action]
3. **[Implement]** [Suggestion] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

**Omit empty sections.** If there are no Blockers, do not include a Blocker heading.

## Rules

- Review the whole change as a system impact, not file-by-file in isolation
- Lead with risk assessment before line-level findings
- Apply Vue conventions, not generic frontend conventions
- Provide actionable feedback with TypeScript / SFC code examples
- Never comment on trivial formatting or style where no project standard exists
- Default to Core scope; auto-escalate on signals; honor `core-only` flag
- Delegate perf / security / observability depth to the appropriate Vue subagent rather than duplicating the check here


### Step 6 - Write Report

Use skill: `review-report-writer` with `report_type: review`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as Vue (or accepted from parent dispatcher); framework and Vue version detected
- [ ] `review-precondition-check` ran (or its handle was received); refs captured. If `--base` passed, `base_source: explicit-override` recorded
- [ ] Diff and commit log were read once and reused by all phases (and shared with subagents) - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran
- [ ] Scope auto-escalation evaluated in Step 3; promotion (or `core-only` suppression) recorded in Summary along with the firing signals
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`
- [ ] Risk level and blast radius stated before any line-level findings
- [ ] Phase B - TypeScript strict + Composition API discipline + watcher discipline + `:key` checks applied
- [ ] Phase B - Reactivity correctness audited (deep `reactive` cost, destructure / spread de-reactivity, `shallowRef` for large structures)
- [ ] Phase B - Nitro endpoint input validation + authorization checked (object-level scoping, not just authenticated)
- [ ] Phase B - Server middleware allowlist exclusions checked for justification when widened
- [ ] Phase B - Pinia / `useState` SSR payload checked for ORM-row leakage to client
- [ ] Phase B - `v-html`, open redirect, `NUXT_PUBLIC_*` / `VITE_*` secrets checked
- [ ] Phase B - accessibility (form labels, dialog ARIA, image alt, error boundary presence) checked
- [ ] Phase B - state categorization (URL / Pinia / local) and provide/inject boundaries reviewed
- [ ] Phase B - hydration audit (browser-only API in setup body, async setup without `<Suspense>`) for Nuxt
- [ ] Phase C Vue architecture checks applied: component layering, server/client boundary, prop-drilling, settings discipline, package boundaries
- [ ] Phase D AI-quality checks applied: pattern inflation, over-abstraction, speculative configurability, watcher misapplication, computed overuse
- [ ] Phase E Vue maintainability checks applied: naming, magic numbers, component length, conditional rendering ladders, logging hygiene
- [ ] Missing tests raised as an explicit named finding (not buried in Key Takeaways)
- [ ] Every Blocker states a system risk, not just a code observation
- [ ] Every finding has a label, location (file:line), and actionable Vue fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged as out-of-scope blocker
- [ ] For non-Core scopes, Vue-specific subagents (`task-vue-review-perf`, `-security`, `-observability`) ran in parallel and received the pre-resolved diff/log handle plus framework detection
- [ ] Subagent findings merged into the single Output Format with deduplication and highest-severity-wins; raw subagent reports not appended
- [ ] Any failed/missing subagent scope noted under Summary as `Scope incomplete: <scope>`
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Blocker > High > Suggestion (omitted only when no actionable findings exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reviewing without reading the full diff and commit log first
- Applying generic frontend conventions when a Vue idiom exists (say "extract to a composable", not "extract to a helper")
- Nitpicking style where no project standard exists; no `[Nitpick]` or `[Praise]` labels
- Providing vague feedback without a concrete Vue fix ("this could be better")
- Blocking on personal preference rather than correctness, risk, or maintainability
- Running perf / security / observability sub-workflows when user passed `core-only`
- Treating auto-escalation signals as advisory; the default is to promote and let the user opt out via `core-only`
- Duplicating perf / security / observability depth checks here when the dedicated Vue subagent owns them - flag and delegate
- Running multiple extra scopes sequentially when they could spawn in parallel
- Appending raw subagent reports section-by-section instead of merging into one severity-ordered Findings list
- Recommending `watch` for derived state, deep `reactive` over large datasets, `v-html` on user input, or `NUXT_PUBLIC_` for secrets as acceptable - all are anti-patterns
