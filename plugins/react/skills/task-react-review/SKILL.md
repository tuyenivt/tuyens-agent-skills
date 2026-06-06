---
name: task-react-review
description: Review React / Next.js PR - RSC boundaries, hooks rules, useEffect misuse, Server Actions, a11y; spawns perf/security/obs subagents.
agent: react-tech-lead
metadata:
  category: frontend
  tags: [react, typescript, nextjs, vite, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.
>
> **Spec-aware mode:** If `--spec <slug>` or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles`. Cross-check every changed surface against `spec.md` / `plan.md`: each change must trace to an AC, NFR, or task; out-of-scope changes are **blockers**; missing in-scope coverage is a gap. Never edit spec artifacts.

# React Code Review

Staff-level React / Next.js / Vite code review umbrella. Covers correctness, architecture, AI-quality, and maintainability. Coordinates perf / security / observability subagents in parallel for extra scopes. Runs standalone with full PR/branch resolution.

## When to Use

- Pre-merge review on a React / Next.js / Vite PR
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:**

- Pre-implementation design (`task-react-implement`)
- Production incident (`/task-oncall-start`)
- Single-error debug (`task-react-debug`)
- New-system architecture (`task-design-architecture`)
- Single-scope reviews - delegate to `task-react-review-perf` / `-security` / `-observability`

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
| Core | Phases A-E (React-flavored) |
| + Perf | Core + `task-react-review-perf` subagent |
| + Security | Core + `task-react-review-security` subagent |
| + Observability | Core + `task-react-review-observability` subagent |
| Full | Core + all three subagents in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals (React-tuned):**

- **+Security:** new Server Action / Route Handler / `middleware.ts`, `dangerouslySetInnerHTML`, auth / session config, `NEXT_PUBLIC_*` additions, file upload / `<form action={...}>`, `redirect(...)` from user input, CSP / `next.config.headers()` change
- **+Perf:** new route / page / layout, new `"use client"` component, new client dependency, new TanStack Query usage, `next/image` / `next/font` change, `next/dynamic` / `React.lazy`, ISR / `revalidate` change, long-list rendering
- **+Observability:** new or modified `instrumentation.ts`, `app/global-error.tsx`, `web-vitals` wiring / reporter, Sentry / RUM / OTel SDK init, new error boundary, new logging utility, analytics call
- **2+ categories -> Full**

## Invocation

| Form | Meaning |
|------|---------|
| `/task-react-review` | Current branch vs base; fails fast on trunk |
| `/task-react-review <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-react-review pr-<N>` | PR head fetched into local branch `pr-<N>` (user runs the fetch) |

Pass `--base <branch>` when the PR was opened against a non-trunk base. Scope and depth flags compose: `/task-react-review pr-50273 --base release/2026.05 +security deep`.

**No checkout required.** The workflow reads via ref-qualified diffs; never modifies the working tree.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as a subagent.

### Step 2 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. Accept pre-detected stack from parent if applicable. If not React, stop and recommend `/task-code-review`.

Detect framework: Next.js (App Router / Pages Router) vs Vite + React Router. Record `Framework`, `React: <version>` for branching in later phases.

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
| `prior_checkpoint.head_sha == current_head_sha`                        | **No-op.** Print `No new commits on <branch> since prior review at <sha_short>. Prior report unchanged.` and stop. Do not call `review-report-writer`. |
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

If the user's invocation expanded scope vs. the prior round (e.g., round 1 was `core-only`, round 2 is `full`), the newly-added scopes have no prior findings to reconcile. Record in Summary: `Scope expanded round <N>: +<list> - new scopes reviewed in full; previously-reviewed scopes reviewed incrementally.` The reconciliation table only covers findings whose scope was active in the prior round.

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

**Auto-promote depth:** if Blast Radius is Wide / Critical and the user did not pass `quick`, set depth to `deep` and surface promotion in Summary **before** Phases B-E (so historical pattern matching, cross-PR context, and anemic-prop assessment are in scope).

**Low-risk short-circuit:** if Risk Level is Low, Blast Radius is Narrow, **and** the change does not touch architecture-relevant files (auth config, middleware, route layouts, shared providers / contexts, `next.config.js`, `vite.config.js`, top-level `App.tsx` / `app/layout.tsx`), skip Phases C-D and produce a streamlined output with Phase B only.

### Phase B - React Correctness and Safety

Apply atomic skills. Each owns canonical patterns; this phase flags deviations:

- Use skill: `react-hooks-patterns` - hooks rules at top level, `useEffect` discipline (no derived state, no event-handler-via-effect), missing deps / stale closures, missing cleanup on subscriptions / intervals, `AbortController` on async setters
- Use skill: `react-component-patterns` - list `key` correctness (no `key={index}` on reorderable lists), `useRef` vs `useState`, `forwardRef` and ref-prop conventions, error boundary placement
- Use skill: `react-state-patterns` - URL / server / client state categorization (filter / page / sort belong in search params), context value memoization, no client-side caching of server state when TanStack Query / RSC owns it
- Use skill: `react-data-fetching` - fetch in Server Components or via TanStack Query; flag `useEffect(() => fetch(...))` in Client Components when a Server Component parent could fetch
- Use skill: `react-nextjs-patterns` (skip on Vite) - `"use client"` placement at the leaf (not layout root), Server Action `auth()` + Zod / `zod-form-data` validation, `'use server'` file exports only actions, Server Action / RSC return values projected to a DTO, `middleware.ts` `matcher` exclusions justified
- Use skill: `react-routing-patterns` if diff touches `app/**/page.tsx`, `app/**/layout.tsx`, or router config

**Additional React-specific checks (deviation-flagging only; canonical rules live in the atomics above):**

- **Test coverage finding** (named, not buried). PR adds logic without Vitest / Testing Library coverage -> `[Recommend]`; escalate to `[Must]` on critical paths: auth UI, Server Actions, money / billing UI, form validation, error boundaries.
- **TypeScript strict**: no `strict: false`, no `props: any`, no `as any` outside test setup.
- **Accessibility**: labels associated, `aria-describedby` for errors, dialogs use `<dialog>` or full ARIA, images have explicit dimensions and `alt`.
- **Canonical security rules** are defined in `react-nextjs-patterns` (loaded above): cite by name, do not restate. If the +Security subagent is running, defer depth to it.

### Phase C - React Architecture Guardrails

Use skill: `architecture-guardrail` for layer violations and coupling.

**React-specific:**

- **Layering:** business logic lives in pages / containers / custom hooks, not inside leaf components (`<Card>`, `<Button>`). Flag fetch calls or business decisions in display components
- **Server / Client split discipline (Next.js):** Client Component importing a server-only utility (`fs`, `node:crypto`, ORM client) is a bundle leak / build error; data fetching belongs in Server Components passing props down
- **Custom hook discipline:** a hook taking 8 params and returning 12 fields is a god hook - split or replace with context / state lib
- **Prop drilling:** a prop threaded 4+ layers - hoist to context or state library; flag chains of pure pass-through props
- **Context overuse:** context for state with a single consumer - flag as unnecessary indirection
- **Routing discipline:** `app/**/page.tsx` routes are thin (delegate to feature components); flag route files with > 100 lines of orchestration
- **Settings discipline:** typed config (`@/lib/config.ts` with Zod, or typed `next.config.js`); flag `process.env.X` sprinkled across components; missing-at-startup should fail fast
- **Module boundaries:** feature-folder layout (`src/features/orders/{components,hooks,api}.ts`) over layer-folder; cross-feature imports go through a defined public surface
- **Provider sandwich:** > ~5 nested providers in `app/layout.tsx` / `App.tsx` - consolidate into a `<Providers>` wrapper

### Phase D - AI-Generated Code Quality

Use skill: `complexity-review` for verbosity, over-engineering, simplification.

Use skill: `react-overengineering-review` for React-specific overengineering: premature memo / `useCallback`, single-consumer Context, store-for-two-slices, single-use custom hooks, generic-for-one-usage, premature compound components, prop -> state -> effect sync.

**React AI smells:**

- **Pattern inflation:** generic `<DataTable<T>>` for one use case; HoC + render prop + hook trio when one suffices; `forwardRef` where a ref prop or nothing would do
- **Over-abstraction:** `BaseFormField` parent for 2 children; premature compound components (`<Tabs.Root><Tabs.List><Tabs.Trigger>`) when a flat API would do; "headless" abstraction for one consumer
- **Speculative configurability:** props with documented but unused values; theme variants for a single design
- **Redundant prop transforms:** prop -> state-for-prop -> effect syncing them; use the prop directly. The "store prop in state" pattern is almost always wrong
- **`useEffect` for event handlers:** `useEffect(() => { if (clicked) handleClick() })` triggered by `setClicked(true)` in `onClick` - just call `handleClick`
- **`useMemo` / `useCallback` everywhere:** memoization on cheap values costs more than it saves; only use when the value feeds `React.memo` children or an effect's deps
- **Test verbosity:** wrapper-chain setups; full-tree snapshots; mocking entire modules when a single function would do
- **`as any` / `as unknown as T`:** legitimate uses are rare; `as React.FC<Props>` may signal copy-paste from older docs
- **Try-catch noise:** `try { await x() } catch (e) { throw e }` - delete; catches that swallow `cause` - use `e instanceof Error ? e : new Error(String(e))`
- **Anonymous default-export components:** breaks DevTools display names and stack traces - use named functions or set `displayName`

### Phase E - Maintainability and Clarity

Use skill: `ops-observability` for cross-cutting logging/metrics presence (depth belongs to `task-react-review-observability`).

**React-specific:**

- **Naming:** components PascalCase (`OrderList`); hooks `use<Noun>`; handlers `handle<Event>` or `on<Event>`; no abbreviations; `displayName` set on memoized / forwardRef components
- **Co-location:** feature folder holds its components, hooks, types, tests together - not scattered across `src/components/`, `src/hooks/`, `src/types/`
- **Magic numbers / strings:** module-level constants; route paths in a typed `routes.ts`
- **Hardcoded URLs / endpoints:** in env / typed config, not inline
- **Component length:** > 200 lines reviewed for extraction (sub-components, hooks, utilities)
- **Conditional rendering ladders:** > 3 nested `&&` / ternary in JSX -> extract to a function returning JSX or a sub-component
- **Logging hygiene:** flag `console.log` in render bodies (PII / RUM leak), `console.log(JSON.stringify(largeObject))`, `console.error` outside dev / fallback paths, production errors not routed through Sentry / RUM - depth belongs to the observability subagent

### Step 5 - Delegate Extra Scopes in Parallel

If scope is **Core only**, skip.

For each extra scope, spawn an independent subagent **in parallel** with the main thread:

| Scope | Subagents |
|-------|-----------|
| + Perf | `task-react-review-perf` |
| + Security | `task-react-review-security` |
| + Observability | `task-react-review-observability` |
| Full | All three in parallel |

**Subagent prompt contract** - each must include:

- The resolved review target (`base_ref`, `head_ref`) plus the pre-read diff and commit log (no re-running git)
- The depth level
- Pre-confirmed stack (React `<version>`) + detected framework (Next.js App Router / Pages Router / Vite + React Router) with version
- Instruction to return findings in its own Output Format

**Failure isolation:** if a subagent fails or times out, continue with the rest. Note the missing scope in Summary.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate** cross-cutting findings (one entry citing all scopes that raised it)
- **Strongest intent wins** when labels differ across subagent reports for the same finding: `Must` > `Recommend` > `Question`. Map subagent scales: `Critical` -> `Must`, `High` -> `Recommend`, `Medium` / `Low` -> drop from the merged list (only `Must`, `Recommend`, `Question` are emitted)
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
- `scope` (resolved in Step 4), `depth` (resolved/auto-promoted), `stack = react`

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
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** React <version> / TypeScript <version>
**Framework:** Next.js (App Router) <version> | Next.js (Pages Router) <version> | Vite + React Router <version>
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_
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

- Issue: [name the React idiom: `"use client"` at root of layout, missing Zod on Server Action, RSC leaking `passwordHash` across Client boundary, `useEffect` for derived state, missing `key`, `dangerouslySetInnerHTML` on user input, `NEXT_PUBLIC_` secret, etc.]
- Impact: [user-visible or operational]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete React change with code]

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
- Server / Client data flow: _(Next.js)_ when 3+ findings cluster around ORM rows crossing the RSC -> Client boundary, name the systemic pattern here rather than producing N near-identical findings

## Maintainability Notes

_Same rule as Architecture Notes._

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

2-4 bullets on systemic impact and what to address before merge.

## Next Steps

On incremental rounds, prior-round Still open items are folded in with (open since round <N>) suffix and ordered by intent alongside new findings. Each item tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [one-line action, e.g., "Move `\"use client\"` from app/dashboard/layout.tsx to app/dashboard/_components/Filters.tsx; revert layout to Server Component"]
2. **[Implement]** [Recommend] OldList.ts:88 - missing key on reorderable list (open since round 1)
3. **[Delegate]** [Recommend] [scope: design-system] - [one-line action]

_Omit if no actionable findings._
```

**Omit empty sections.** No Must heading if there are none.

## Rules

- Review whole-change system impact, not file-by-file
- Lead with risk; line-level findings follow
- Apply React conventions, not generic frontend conventions
- Provide actionable feedback with TypeScript / JSX code examples
- Default Core; auto-escalate; honor `core-only`
- Delegate perf / security / observability depth to subagents

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (or accepted from parent)
- [ ] Step 2: stack confirmed as React; framework and React version recorded
- [ ] Step 3: `review-precondition-check` ran (or handle received); diff and commit log read once and reused; for `pr-ref` mode the fetch command was surfaced; when `head_matches_current` was false, explicit approval was obtained; current_head_sha and current_base_sha captured
- [ ] Step 3.5 - mode decided (full / incremental / no-op); auto-fetch attempted only when prior checkpoint exists; incremental range re-read when mode flipped to incremental; no-op path exits without writing the report
- [ ] Step 4: scope auto-escalation evaluated; promotion (or `core-only` suppression) recorded with firing signals
- [ ] Phase A: risk level and blast radius stated before any finding; depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`; low-risk short-circuit applied when applicable
- [ ] Phase B: atomic skills applied (`react-hooks-patterns`, `react-component-patterns`, `react-state-patterns`, `react-data-fetching`, plus `react-nextjs-patterns` / `react-routing-patterns` when relevant); test coverage, RSC -> Client ORM leak, Server Action auth + Zod, `dangerouslySetInnerHTML` / open-redirect / `NEXT_PUBLIC_*` secrets, TS strict, a11y checked
- [ ] Phase C: layering, RSC / Client split, custom hook / prop drilling / context discipline, settings, module boundaries, provider sandwich applied
- [ ] Phase D: `complexity-review` + `react-overengineering-review` applied; React AI smells covered (pattern inflation, over-abstraction, redundant prop transforms, `useEffect` misapplication, memo overuse, `as any`, anonymous default-export components)
- [ ] Phase E: naming, co-location, magic numbers, component length, conditional ladders, logging hygiene
- [ ] Missing tests raised as a named finding (not buried)
- [ ] Every Must cites system risk
- [ ] Every finding has label + `file:line` + actionable React fix
- [ ] If `--spec` passed: every finding traces to AC/NFR/task or is flagged as out-of-scope blocker
- [ ] Step 5: extra scopes ran in parallel with the pre-resolved diff/log handle plus framework detection
- [ ] Step 6: subagent findings merged into one intent-ordered Findings list; raw reports not appended; failed/missing scope noted as `Scope incomplete: <scope>`; Next Steps tagged `[Implement]` / `[Delegate]` and ordered by intent
- [ ] Step 6.5 - on incremental rounds, review-prior-findings-reconcile ran; reconciliation table inserted; Still open rows folded into Next Steps with (open since round <N>) suffix
- [ ] Step 7: review report written via `review-report-writer` with full checkpoint fields (mode, round, prior_head_sha when round > 1, head_sha, base_sha, scope, depth, stack); confirmation line printed

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase). The one allowed exception is `git fetch <remote> <branch>` in Step 3.5a, and only when a valid prior checkpoint exists.
- Auto-fetching on round 1 (no prior checkpoint) - keeps first-run behavior strictly read-only.
- Running incremental analysis against the full-range diff (must re-read scoped to `<prior_head_sha>...<head_sha>`).
- Writing the report on no-op exit (prior `head_sha == current head_sha`) - the file must stay byte-identical.
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`).
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
- Emitting a "Carry-Over Open Items" section - fold into Next Steps instead.
- Reviewing without reading the full diff and commit log first
- Generic frontend conventions when a React idiom exists ("extract to a custom hook", not "extract to a helper")
- Nitpicking style where no project standard exists
- Vague feedback ("this could be better")
- Blocking on personal preference
- Running extra scopes when `core-only` was passed
- Duplicating perf / security / observability depth here when the dedicated React subagent owns them
- Sequential extra scopes that could parallelize
- Appending raw subagent reports instead of merging
- Recommending `useEffect` for derived state, `"use client"` at the root of a layout, `dangerouslySetInnerHTML` on user input, or `NEXT_PUBLIC_` for secrets as acceptable
