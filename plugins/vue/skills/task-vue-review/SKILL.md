---
name: task-vue-review
description: Review Vue / Nuxt PR - Composition API, watcher / reactivity, v-html, Nitro, SSR hydration, Pinia leaks; spawns perf/security/obs subagents.
agent: vue-tech-lead
metadata:
  category: frontend
  tags: [vue, typescript, nuxt, vite, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

# Vue Code Review

Staff-level Vue / Nuxt / Vite code review umbrella. Covers correctness, architecture, AI-quality, and maintainability. Coordinates perf / security / observability subagents in parallel for extra scopes. Runs standalone with full PR/branch resolution.

## When to Use

- Pre-merge review on a Nuxt or Vite + Vue PR
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:**

- Pre-implementation design (`task-vue-implement`)
- Production incident (`/task-oncall-start`)
- Single-error debug (`task-vue-debug`)
- New-system architecture (`task-design-architecture`)
- Single-scope reviews - delegate to `task-vue-review-perf` / `-security` / `-observability`

## Depth Levels

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | Phases A-E |
| `deep` | Architecture PRs, post-incident, Principal sign-off | A-E + historical pattern matching + cross-PR context |

**Auto-promote to `deep`:** after Phase A, if `Blast Radius` is Wide or Critical, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E (Vue-flavored) |
| + Perf | Core + `task-vue-review-perf` subagent |
| + Sec | Core + `task-vue-review-security` subagent |
| + Obs | Core + `task-vue-review-observability` subagent |
| Full | Core + all three subagents in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals (Vue-tuned):**

- **+Sec:** new Nitro endpoint / `server/middleware/*`, `v-html` introduction, auth / session config, `NUXT_PUBLIC_*` / `VITE_*` additions, file upload, `navigateTo(...)` from user input, CSP / `routeRules.headers` change
- **+Perf:** new page / layout, new heavy component, new client dependency in `dependencies`, new TanStack Query / Pinia store, `<NuxtImg>` / `@nuxt/fonts` change, lazy component / async chunk, `routeRules` change, long-list rendering
- **+Obs:** new `plugins/*.ts`, Sentry / RUM SDK init, `web-vitals` reporter, new error boundary / `error.vue`, new logging utility, analytics call
- **2+ categories -> Full**

## Invocation

| Form | Meaning |
|------|---------|
| `/task-vue-review` | Current branch vs base; fails fast on trunk |
| `/task-vue-review <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-vue-review pr-<N>` | PR head fetched into local branch `pr-<N>` (user runs the fetch) |

Pass `--base <branch>` when the PR was opened against a non-trunk base. Scope and depth flags compose: `/task-vue-review pr-50273 --base release/2026.05 +sec deep`.

**No checkout required.** The workflow reads via ref-qualified diffs; never modifies the working tree.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as a subagent.

### Step 2 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. Accept pre-detected stack from parent if applicable. If not Vue, stop and recommend `/task-code-review`.

Detect framework: Nuxt 3 vs Vite + Vue Router. Record `Framework`, `Vue: <version>` for branching in later phases.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Forward `--base` if passed. If it fails fast (dirty tree, trunk branch, missing PR ref, denied head-vs-current confirmation), surface verbatim and stop. Never run state-changing git commands from this workflow.

The handle may include a `prior_checkpoint` block (a prior `review-<branch>.md` exists). Decision logic is Step 3.5; for now, just hold onto it.

Once approved, read once and reuse:

- `git diff <base>...<head>`
- `git diff --name-status <base>...<head>`
- `git log --oneline <base>..<head>`

**Skip entirely** when invoked as a subagent and the parent passed the handle plus pre-read artifacts.

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

### Step 4 - Evaluate Scope Auto-Escalation

Scan the file list and diff for the signals listed under **Scope**. Log each fire as `signal: <category> -> <file:line>`. Then:

- Zero signals or `core-only` -> stay Core
- One signal category -> add matching extra scope
- 2+ categories -> promote to Full
- User passed an explicit scope -> respect it; still log signals so the Summary documents why

**Scope precedence on round 2+:** user flag > firing signals > inherit from `prior_checkpoint.scope`. If the user passed no flag and the diff (incremental, in incremental mode) fires no signals, inherit the prior round's scope so reviewer coverage does not silently narrow. Surface as `Scope: <inherited> (inherited from round <prior.round>)`.

Surface the decision in Summary; if escalated, append `auto-escalated from Core; signals: <list>`.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk signals
- Use skill: `review-blast-radius` for failure propagation scope

Output risk level and blast radius before any findings.

**Auto-promote depth:** if Blast Radius is Wide / Critical, set depth to `deep` and surface promotion in Summary **before** Phases B-E.

**Low-risk short-circuit:** if Risk Level is Low, Blast Radius is Narrow, **and** the change does not touch architecture-relevant files (auth config, server middleware, route layouts, shared providers / Pinia stores, `nuxt.config.ts`, `vite.config.ts`, top-level `app.vue` / `App.vue`), skip Phases C-D and produce a streamlined output with Phase B only.

### Phase B - Vue Correctness and Safety

Apply atomic skills. Each owns canonical patterns; this phase flags deviations:

- Use skill: `vue-component-patterns` - `<script setup>` over Options API, `defineProps<{...}>` typed, `v-for` `:key` correctness (no `:key="index"` on reorderable lists), `v-for` + `v-if` on same element, conditional ladder extraction
- Use skill: `vue-composables-patterns` - composables called at top level (no conditions / loops / after early returns); `use<Noun>` naming; cleanup via `onScopeDispose` / `onUnmounted` for subscriptions / observers / intervals
- Use skill: `vue-state-patterns` - URL vs Pinia vs local state categorization (filter / page / sort belong in route query); reactivity primitives (deep `reactive` on large read-only data -> `shallowRef`); destructure / spread de-reactivity (`const { a } = reactive({...})`); watcher discipline (no `watch` for derived state -> `computed`; no `watch` for event handling -> call handler directly); `provide` re-render storms from non-stable values
- Use skill: `vue-data-fetching` - `useFetch` / `useAsyncData` for initial-render data; flag `onMounted(() => fetch(...))` when SSR fetch would serve
- Use skill: `vue-nuxt-patterns` (skip on Vite) - hydration safety (browser-only APIs guarded by `import.meta.client` / `onMounted`; async `<script setup>` needs `<Suspense>` ancestor; client-only components in `<ClientOnly>`); Nitro endpoint input via `readValidatedBody(event, Schema.parse)` / `getValidatedQuery`; mutating endpoints call `requireUserSession(event)` and scope by principal in the query; `server/middleware/auth.ts` exclusions justified
- Use skill: `vue-routing-patterns` if diff touches `pages/**/*.vue`, `app/router.options.ts`, or middleware

**Cross-cutting checks the atomics don't own:**

- **Test coverage.** PR adds logic without Vitest coverage -> `[Recommend]`; escalate to `[Must]` on critical paths (auth, Nitro endpoints, billing, form validation, error boundaries).
- **TypeScript strict.** `strict: true` silently disabled or `as any` outside tests is a finding.
- **Accessibility.** `<input>` paired with `<label>`; `aria-describedby` for errors; dialogs use full ARIA + focus trap (prefer Headless UI / Reka UI); images carry `width`/`height` + `alt`.

### Phase C - Vue Architecture Guardrails

Use skill: `architecture-guardrail` for layer violations and coupling.

**Vue-specific:**

- **Layering:** business logic lives in pages / containers / composables, not inside leaf components (`<Card>`, `<Button>`). Flag fetch calls or business decisions in display components
- **Server / client boundary (Nuxt):** a `.vue` / composable importing `fs`, `node:crypto`, ORM client into client-evaluated code is a bundle leak / build error - server-only modules belong in `server/**/*.ts`
- **Composable discipline:** a composable taking 8 params and returning 12 fields is a god composable - split or replace with a store
- **Prop drilling:** a prop threaded 4+ layers - hoist to `provide` / `inject` or a Pinia store; flag chains of pure pass-through props
- **`provide` overuse:** `provide` for state a single consumer reads - flag as unnecessary indirection
- **Routing discipline:** `pages/**/*.vue` routes are thin (delegate to feature components); flag route files with > 100 lines of orchestration
- **Settings discipline:** typed config (Nuxt `runtimeConfig` typed via `RuntimeConfig` interface; Vite `import.meta.env` through a single typed `config.ts` with Zod); flag `useRuntimeConfig().public.X` / `import.meta.env.X` sprinkled across components
- **Module boundaries:** feature-folder layout (`features/orders/{components,composables,api}.ts`) over flat `components/`, `composables/`; cross-feature imports go through a defined public surface
- **Plugin sandwich:** > ~5 nested `app.use(plugin)` calls in `plugins/` / `main.ts` - consolidate into a `<Providers>` wrapper

### Phase D - AI-Generated Code Quality

Use skill: `complexity-review` for verbosity, over-engineering, simplification.

**Vue AI smells:**

- **Pattern inflation:** generic `<DataTable<T>>` for one use case; scoped-slot / render-prop trio when a flat prop API would do; `defineExpose` on every component (each call widens the public surface)
- **Over-abstraction:** `BaseFormField` parent for 2 children; premature compound components when a flat API would do; "headless" abstraction for one consumer
- **Speculative configurability:** props with documented but unused values; theme variants for a single design
- **Redundant prop transforms:** prop -> `ref` initialized from prop -> `watch` syncing them; use the prop via `computed` or destructure (Vue 3.5+ props destructure compiles to accessors). The "store prop in state" pattern is almost always wrong
- **`watch` for event handlers:** `watch(clicked, () => { if (clicked) handleClick() })` triggered by setting `clicked` in `@click` - just call `handleClick`
- **`computed` chains on trivial values:** flag chains of trivial `computed` that obscure data flow
- **Test verbosity:** `mount(Component, { global: { stubs: { ...50 stubs... } } })` chains; module-wide mocks when a single function would do; full-tree snapshots
- **`as any` / `as unknown as T`:** legitimate uses are rare; `as any` to bypass a real type bug is a finding
- **Try-catch noise:** `try { await x() } catch (e) { throw e }` - delete; catches that swallow `cause` - use `error.value = e instanceof Error ? e : new Error(String(e))`
- **Anonymous SFC names:** `<script setup>` infers name from filename - flag SFCs named `Index.vue` deep inside feature folders (DevTools shows "Index" everywhere)

### Phase E - Maintainability and Clarity

Use skill: `ops-observability` for cross-cutting logging/metrics presence (depth belongs to `task-vue-review-observability`).

**Vue-specific:**

- **Naming:** components PascalCase (`OrderList.vue`); composables `use<Noun>`; event names kebab-case (`@order-saved`); no abbreviations (`OrdLst.vue` is wrong)
- **Co-location:** feature folder holds its components, composables, types, tests together - not scattered across `components/`, `composables/`, `types/`
- **Magic numbers / strings:** module-level constants; route paths in a typed `routes.ts`
- **Hardcoded URLs / endpoints:** in env / `runtimeConfig`, not inline
- **Component length:** > 200 lines reviewed for extraction (sub-components, composables, utilities)
- **Conditional rendering ladders:** > 3 nested `v-if` / ternary in template -> extract to a sub-component or a `computed` returning the right variant
- **Logging hygiene:** flag `console.log` in `<script setup>` body (PII / RUM leak), `console.log(JSON.stringify(largeObject))`, `console.error` outside dev / fallback paths, production errors not routed through Sentry / RUM - depth belongs to the observability subagent

### Step 5 - Delegate Extra Scopes in Parallel

If scope is **Core only**, skip.

For each extra scope, spawn one independent subagent **in parallel** with the main thread. Use the **declared subagent for that scope** (`subagent_type` below) - do not infer the agent from the scope name; an observability review is not a `vue-tech-lead` spawn:

| Scope | Skill | Subagent (`subagent_type`) |
|-------|-------|----------------------------|
| + Perf | `task-vue-review-perf` | `vue-performance-engineer` |
| + Sec | `task-vue-review-security` | `vue-security-engineer` |
| + Obs | `task-vue-review-observability` | `vue-observability-engineer` |

`Full` = 3 subagents.

**Subagent prompt contract** - each must include:

- The resolved review target (`base_ref`, `head_ref`) plus the pre-read diff and commit log (no re-running git)
- The depth level
- Pre-confirmed stack (Vue) + detected framework (Nuxt / Vite)
- Instruction to return findings in its own Output Format

**Failure isolation:** if a subagent fails or times out, continue with the rest. Note the missing scope in Summary.

**No-subagent fallback:** if the environment cannot spawn subagents, run each delegate skill inline and sequentially with the same prompt contract, producing each scope's findings in its own Output Format, then continue to Step 6. Note in Summary: `subagents unavailable - scopes ran inline`.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate** cross-cutting findings (one entry citing all scopes that raised it)
- **Strongest intent wins** when labels differ across subagent reports for the same finding: `Must` > `Recommend` > `Question`. Map subagent scales: `Critical` -> `Must`; security `High` -> `Must` (its rubric defines High as merge-blocking); perf / obs `High` -> `Recommend`; `Medium` / `Low` -> drop from the merged list (only `Must`, `Recommend`, `Question` are emitted)
- **Preserve `file:line` citations** from the originating subagent
- **Order by intent**, not by scope
- **Note missing scopes** in Summary as `Scope incomplete: <scope>`
- **Merge Next Steps** with `[Implement]` / `[Delegate]` tags preserved; re-sort by intent

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
- `scope` (resolved in Step 4), `depth` (resolved/auto-promoted), `stack = vue`

Write before ending; print the confirmation line.

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
**Stack Detected:** Vue <version> / TypeScript <version>
**Framework:** Nuxt 3 <version> | Vite + Vue Router <version>
**Scope:** Core | +Sec | +Perf | +Obs | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_
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

- Issue: [name the Vue idiom: deep `reactive` on a 5K-row dataset, missing Zod on Nitro endpoint, Pinia store leaking `passwordHash` via SSR payload, watcher cascade through three ticks, missing `:key`, `v-html` on user input, `NUXT_PUBLIC_` secret leak, etc.]
- Impact: [user-visible or operational]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete Vue change with code]

### [Recommend] file:line
- Issue: ...
- Impact: ...
- Fix: ...

### [Question] file:line
- Question: [what is ambiguous]
- Why it matters: [what the right next step depends on]

_Use [Question] for genuine ambiguity, not as a softer Must._

## Architecture Notes

_Cross-cutting commentary. Do not restate individual findings; reference them by file:line._

- Boundary impact:
- Coupling change:
- Drift detected:
- SSR / hydration data flow: _(Nuxt)_ when 3+ findings cluster around ORM rows being passed across SSR into client payload, name the systemic pattern here ("pages consistently place full ORM rows in Pinia stores; introduce a DTO layer at `server/api/_dto.ts`") rather than producing N near-identical findings

## Maintainability Notes

_Same rule as Architecture Notes._

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

2-4 bullets on systemic impact and what to address before merge.

## Next Steps

On incremental rounds, prior-round Still open items are folded in with (open since round <N>) suffix and ordered by intent alongside new findings. Each item tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [one-line action, e.g., "Wrap `server/api/account.put.ts` body with `readValidatedBody(event, AccountUpdateSchema.parse)`; whitelist `name`, `email`, `bio`"]
2. **[Implement]** [Recommend] OldList.ts:88 - missing :key on reorderable list (open since round 1)
3. **[Delegate]** [Recommend] [scope: design-system] - [one-line action]

_Omit if no actionable findings._
```

**Omit empty sections.** No Must heading if there are none.

## Rules

- Review whole-change system impact, not file-by-file
- Lead with risk; line-level findings follow
- Apply Vue conventions, not generic frontend conventions
- Provide actionable feedback with TypeScript / SFC code examples
- Default Core; auto-escalate; honor `core-only`
- Delegate perf / security / observability depth to subagents

## Self-Check

- [ ] Steps 1-3: behavioral principles loaded; Vue stack + framework recorded; diff/log resolved and read once (or handle accepted from parent); `review-precondition-check` ran (or handle received); current_head_sha and current_base_sha captured
- [ ] Step 3.5 - mode decided (full / incremental / no-op); auto-fetch attempted only when prior checkpoint exists; incremental range re-read when mode flipped to incremental; no-op path exits without writing the report
- [ ] Step 4: scope auto-escalation evaluated; firing signals logged
- [ ] Phase A: risk + blast radius stated before findings; depth auto-promoted on Wide/Critical; low-risk short-circuit applied when applicable
- [ ] Phase B: atomic skills consulted; cross-cutting test coverage / TS strict / a11y checked
- [ ] Phase C: layering, server/client boundary, composable/prop discipline, settings, module boundaries applied
- [ ] Phase D: `complexity-review` applied to Vue AI smells (pattern inflation, redundant prop transforms, `watch` misuse, `as any`)
- [ ] Phase E: naming, co-location, component length, conditional ladders, logging hygiene
- [ ] Every finding: label + `file:line` + actionable fix; every Must cites system risk; missing tests named, not buried
- [ ] Steps 5-6: extra scopes ran in parallel (or inline fallback noted in Summary); findings merged intent-ordered; missing scope noted; Next Steps tagged `[Implement]`/`[Delegate]`
- [ ] Step 6.5 - on incremental rounds, review-prior-findings-reconcile ran; reconciliation table inserted; Still open rows folded into Next Steps with (open since round <N>) suffix
- [ ] Step 7: report written via `review-report-writer` with full checkpoint fields (mode, round, prior_head_sha when round > 1, head_sha, base_sha, scope, depth, stack); confirmation printed

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase). The one allowed exception is `git fetch <remote> <branch>` in Step 3.5a, and only when a valid prior checkpoint exists.
- Auto-fetching on round 1 (no prior checkpoint) - keeps first-run behavior strictly read-only.
- Running incremental analysis against the full-range diff (must re-read scoped to `<prior_head_sha>...<head_sha>`).
- Writing the report on no-op exit (prior `head_sha == current head_sha`) - the file must stay byte-identical.
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`).
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
- Emitting a "Carry-Over Open Items" section - fold into Next Steps instead.
- Reviewing without reading the full diff and commit log first.
- Generic frontend conventions when a Vue idiom exists.
- Vague feedback or blocking on personal preference.
- Duplicating perf / security / observability depth - delegate to the subagents.
- Sequential extra scopes when subagents are available; appending raw subagent reports instead of merging.
