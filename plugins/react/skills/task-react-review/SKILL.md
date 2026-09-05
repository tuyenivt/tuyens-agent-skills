---
name: task-react-review
description: Review React / Next.js PR - RSC boundaries, hooks rules, useEffect misuse, Server Actions, a11y; spawns perf/security/obs/reliability subagents.
agent: react-tech-lead
metadata:
  category: frontend
  tags: [react, typescript, nextjs, vite, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# React Code Review

Staff-level React / Next.js / Vite code review umbrella. Covers correctness, architecture, AI-quality, and maintainability. Coordinates perf / security / observability / reliability subagents in parallel for extra scopes. Runs standalone with full PR/branch resolution.

## When to Use

- Pre-merge review on a React / Next.js / Vite PR
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:**

- Pre-implementation design (`task-react-implement`)
- Single-error debug
- New-system architecture (an architecture-design workflow; not reachable from this plugin)
- Single-scope reviews - delegate to `task-react-review-perf` / `-security` / `-observability` / `-reliability`

## Depth Levels

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | Phases A-E |
| `deep` | Architecture PRs, post-incident, Principal sign-off | A-E, plus the two depth branches marked **deep** in Phases C and D, and every extra scope spawned at `deep` (except +Sec, which has no depth knob) |

**Auto-promote to `deep`:** after Phase A, if `Blast Radius` is Wide or Critical, set depth to `deep` and surface it in Summary as `auto-promoted from standard; Blast Radius: <level>`.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E (React-flavored) |
| + Perf | Core + `task-react-review-perf` subagent |
| + Sec | Core + `task-react-review-security` subagent |
| + Obs | Core + `task-react-review-observability` subagent |
| + Rel | Core + `task-react-review-reliability` subagent |
| Full | Core + all four subagents in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals (React-tuned):**

- **+Sec:** new Server Action / Route Handler / `middleware.ts`, `dangerouslySetInnerHTML`, auth / session config, `NEXT_PUBLIC_*` additions, file upload / `<form action={...}>`, `redirect(...)` from user input, CSP / `next.config.headers()` change
- **+Perf:** new route / page / layout, new `"use client"` component, new client dependency, new TanStack Query usage, `next/image` / `next/font` change, `next/dynamic` / `React.lazy`, ISR / `revalidate` change, long-list rendering
- **+Obs:** new or modified `instrumentation.ts`, `app/global-error.tsx`, `web-vitals` wiring / reporter, Sentry / RUM / OTel SDK init, new error boundary, new logging utility, analytics call
- **+Rel:** new `fetch` / client call without an `AbortSignal.timeout`, TanStack Query `retry` / `retryDelay` config, new or removed `error.tsx` / `global-error.tsx` / error boundary, `useOptimistic` or mutation rollback path, offline / reconnect handling, `revalidatePath` / `revalidateTag` invalidation change, `next/dynamic` / `React.lazy` chunk boundary
- **2+ categories -> Full**

## Invocation

| Form | Meaning |
|------|---------|
| `/task-react-review` | Current branch vs base; fails fast on trunk |
| `/task-react-review <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-react-review pr-<N>` | PR head fetched into local branch `pr-<N>` (user runs the fetch) |

Pass `--base <branch>` when the PR was opened against a non-trunk base. Scope and depth flags compose: `/task-react-review pr-50273 --base release/2026.05 +sec deep`.

Pass `--req <path>` to name a requirement source (ticket export, PRD, spec) for Phase 0; without it, Phase 0 uses whatever requirement is already in context.

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

No checkout, no merge. This updates `refs/remotes/<remote>/<branch>`, not the local branch, so re-resolve against the remote-tracking ref: `current_head_sha = git rev-parse <remote>/<branch>`. If `upstream` does not resolve (pr-ref with no upstream, detached HEAD, no remote configured), or if `<remote>/<branch>` does not exist afterwards (a remote with no configured fetch refspec updates only `FETCH_HEAD`), skip silently and keep `current_head_sha` from Step 3. If `git fetch` fails (offline, auth, deleted remote branch), continue silently - this is a convenience, not a gate. **If the re-resolved SHA differs from Step 3's, stop and tell the user to fast-forward the local branch** (`git merge --ff-only <remote>/<branch>`) and re-run. Do not analyze the remote SHA while `head_ref` still points at the local one: Step 6.5's verify reads code with `git show <head_ref>:<path>`, so the two must agree.

**Step 3.5b - Compare checkpoints.**

| Condition                                                              | Decision                                                                                                                            |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `prior_checkpoint.head_sha == current_head_sha`, and the invocation adds no scope or depth beyond the prior checkpoint | **No-op.** Print `No new commits on <head_ref_short> since prior review at <sha_short>. Prior report unchanged.` (where `<head_ref_short>` is the short name of `head_ref` - the review target, not the user's current branch - and `<sha_short>` is the first 7 chars of `current_head_sha`) and stop. Do not call `review-report-writer`. |
| `prior_checkpoint.head_sha == current_head_sha`, but the invocation expands scope or depth beyond it | `round = prior.round + 1`. Note in Summary: `Same head as round <prior.round>; re-review for expanded <scope\|depth>.` |
| `git merge-base --is-ancestor <prior_head_sha> <current_head_sha>` fails (prior SHA unreachable) | `round = prior.round + 1`. Note in Summary: `Prior checkpoint unreachable - history rewritten.`      |
| `prior_checkpoint.base_sha != current_base_sha`                        | `round = prior.round + 1`. Note in Summary: `Base branch advanced since round <prior.round>.`       |
| `prior_checkpoint.base_ref != base_ref`                                | `round = prior.round + 1`. Note in Summary: `Base ref changed since round <prior.round>.`           |
| None of the above                                                       | `round = prior.round + 1`.                                                                          |

Rows are evaluated top to bottom and **the first match wins**; when several conditions hold at once (a force-push onto a moved base), emit only the first matching row's Summary note.

**Step 3.5c - Scope expansion handling.**

If the user's invocation expanded scope vs. the prior round (e.g., round 1 was `core-only`, round 2 is `full`), the newly-added scopes have no prior findings to reconcile. Record in Summary: `Scope expanded round <N>: +<list>.`

The reconciliation table (when emitted) only covers findings whose scope was active in the prior round.

### Step 4 - Evaluate Scope Auto-Escalation

Scan the file list and diff for the signals listed under **Scope**. Log each fire as `signal: <category> -> <file:line>`. Then:

- Zero signals or `core-only` -> stay Core
- One signal category -> add matching extra scope
- 2+ categories -> promote to Full
- User passed an explicit scope -> respect it; still log signals so the Summary documents why

**Scope precedence on round 2+:** user flag > firing signals. Signals are scored on the full range every round, so a scope that escalated in round 1 escalates again on its own - nothing is inherited from the prior checkpoint. When the resolved scope still falls below the checkpoint's (round 1 was user-flagged), note in Summary: `Scope narrowed vs round <prior.round>: <list> - re-run with <flags> to re-cover.`

Surface the decision in Summary; if escalated, append `auto-escalated from Core; signals: <list>`.

### Phase 0 - Change Intent

Use skill: `review-change-intent` with the `<base_ref>...<head_ref>` diff and log, the `--req <path>` file when passed, and `prior_checkpoint.report_path` when round > 1.

Its `## Change Brief` block goes into the report verbatim, its `Requirement Source` and `Requirement Fit` lines into Summary, and its findings join the assembled set verified in Step 6.5. With no requirement source the Brief still renders, and the traceability block and its two Summary lines are omitted. Runs before Phase A - acceptance criteria decide what counts as a defect downstream - and the low-risk short-circuit never skips it.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk signals
- Use skill: `review-blast-radius` for failure propagation scope

Output risk level and blast radius before any findings.

**Auto-promote depth:** `review-blast-radius` can return two values with a `Mitigation:` line (`Critical (unmitigated) -> Wide (with the flag off)`); gate on the mitigated value only when the mitigation is tagged `in-place:`, otherwise on the unmitigated one, and record the value you gated on. If Blast Radius is Wide / Critical, set depth to `deep` and surface promotion in Summary **before** Phases B-E (so historical pattern matching, cross-PR context, and anemic-prop assessment are in scope). On round 2+ nothing is inherited; when the resolved depth falls below the checkpoint's (round 1 was user-flagged `deep`), note in Summary: `Depth narrowed vs round <prior.round> - re-run with deep to re-cover.`

**Low-risk short-circuit:** if Risk Level is Low, Blast Radius is Narrow, **and** the change does not touch architecture-relevant files (auth config, middleware, route layouts, shared providers / contexts, `next.config.*`, `vite.config.*`, top-level `App.tsx` / `app/layout.tsx`), skip Phases C-D and produce a streamlined report: Summary, the Phase 0 outputs (Change Brief, traceability, requirement findings), High-Impact Findings (Phases B and E), `## Scope Sections` when an auto-escalated scope returned one, `## Prior Round Reconciliation` when round > 1, `## Key Takeaways`, and Next Steps - each omitted when empty, per the Output Format's Omit-empty-sections rule. Phase E still runs; its findings join High-Impact Findings rather than getting their own Notes section.

### Phase B - React Correctness and Safety

Apply atomic skills. Each owns canonical patterns; this phase flags deviations:

- Use skill: `react-hooks-patterns` - hooks rules at top level, `useEffect` discipline (no derived state, no event-handler-via-effect), missing deps / stale closures, missing cleanup on subscriptions / intervals, `AbortController` on async setters
- Use skill: `react-component-patterns` - `forwardRef` and ref-prop conventions, error boundary placement. List `key` correctness (no `key={index}` on reorderable lists) and `useRef` vs `useState` are `react-hooks-patterns` rules, checked there
- Use skill: `react-state-patterns` - URL / server / client state categorization (filter / page / sort belong in search params), context value memoization, no client-side caching of server state when TanStack Query / RSC owns it
- Use skill: `react-data-fetching` - fetch in Server Components or via TanStack Query; flag `useEffect(() => fetch(...))` in Client Components when a Server Component parent could fetch
- Use skill: `react-nextjs-patterns` (skip on Vite) - `"use client"` placement at the leaf (not layout root), Server Action `auth()` + Zod / `zod-form-data` validation, `'use server'` file exports only actions. DTO projection of Server Action / RSC return values is `react-server-data-layer`'s rule and `middleware.ts` `matcher` scoping is `react-routing-patterns`' - load those two below rather than expecting them here
- Use skill: `react-routing-patterns` if the diff touches `app/**/page.tsx`, `app/**/layout.tsx`, `middleware.ts`, or router config - it owns `matcher` scoping
- Use skill: `react-server-data-layer` if the diff touches an ORM client, a schema file, `src/server/**`, or any Server Action / Route Handler that reads or writes persistent state - client singleton and hot-reload guard, server-only boundary, service-layer placement, RSC N+1, request memoization vs data cache, raw ORM rows crossing the client boundary
- Use skill: `backend-transaction-patterns` if the diff opens a transaction or dispatches a side effect (queue, mail, outbound HTTP) alongside a write
- Use skill: `react-selfhost-operations` if the diff touches `next.config.*`, `Dockerfile`, CDN or cache rules, or `NEXT_PUBLIC_` environment wiring. `instrumentation.ts` content belongs to `task-react-review-observability`; flag its presence here only as a scope signal

When a delegated atomic emits its own severity, map it to labels: `Critical` or `Blocker` or `High` -> `[Must]`, `Medium` -> `[Recommend]`, `Low` -> below the reporting bar. Every severity value any loaded atomic emits appears in that mapping - `react-hooks-patterns`, `react-state-patterns` and `react-data-fetching` all emit `Critical`.

**API contract gate (mandatory when triggered).** When the diff touches an `app/**/route.ts` Route Handler, a published spec or generated client, or a response shape returned from one, Use skill: `backend-api-guidelines` and Use skill: `ops-backward-compatibility`. Both run - the first judges design, the second judges consumer breakage. Apply the same coverage and the same severity-to-label mapping as the core `task-code-review` Phase B gate: removed, renamed, or retyped fields, tightened constraints, new required request fields, and changed status codes or error shapes are breaking until proven otherwise; DTOs never return raw ORM rows; collections are paginated; RFC 9457 error shape.

**Server Actions are excluded from this gate.** They have no stable URL and ship with their only caller, so they carry no compatibility surface. A monolith is still in scope when a Route Handler serves a consumer it cannot redeploy - a mobile client, an inbound webhook, or a public read surface. When consumption is unknown, treat a published or versioned surface (`/api/v1/`, OpenAPI-documented) as externally consumed. Server Action authorization and input validation belong to `task-react-review-security`, not here.

**Additional React-specific checks (deviation-flagging only; canonical rules live in the atomics above):**

- **Test coverage finding** (named, not buried). PR adds logic without Vitest / Testing Library coverage -> `[Recommend]`; escalate to `[Must]` on critical paths: auth UI, Server Actions, money / billing UI, form validation, error boundaries.
- **Test files are reviewed for coverage only.** For files that are themselves tests, the only finding to raise is a coverage gap: production logic in the diff that no test exercises. Anchor that finding to the untested production `file:line` and state the case to cover, not the test file. Do not review test code for style, structure, duplication, naming, or performance - a passing test with awkward setup is not a finding.
- **TypeScript strict**: no `strict: false`, no `props: any`, no `as any` outside test setup.
- **Accessibility**: labels associated, `aria-describedby` for errors, dialogs use `<dialog>` or full ARIA, images have `alt`. Explicit `width`/`height` is a CLS concern owned by `task-react-review-perf`.
- **Canonical security rules** are defined in `react-nextjs-patterns` (loaded above): cite by name, do not restate. If the +Sec subagent is running, defer depth to it.

### Phase C - React Architecture Guardrails

Use skill: `architecture-guardrail` for layer violations and coupling.

**deep only:** also read the unchanged modules the diff imports, and judge coupling against them rather than against the diff alone.

**React-specific:**

- **Layering:** business logic lives in pages / containers / custom hooks, not inside leaf components (`<Card>`, `<Button>`). Flag fetch calls or business decisions in display components
- **Server / Client split discipline (Next.js):** Client Component importing a server-only utility (`fs`, `node:crypto`, ORM client) is a bundle leak / build error; data fetching belongs in Server Components passing props down
- **Custom hook discipline:** a hook taking 8 params and returning 12 fields is a god hook - split or replace with context / state lib
- **Prop drilling:** a prop threaded 4+ layers - hoist to context or state library; flag chains of pure pass-through props
- **Context overuse:** context for state with a single consumer - flag as unnecessary indirection
- **Routing discipline:** `app/**/page.tsx` routes are thin (delegate to feature components); flag route files with > 100 lines of orchestration
- **Settings discipline:** typed config (`@/lib/config.ts` with Zod, or typed `next.config.ts`); flag `process.env.X` sprinkled across components; missing-at-startup should fail fast
- **Module boundaries:** feature-folder layout (`src/features/orders/{components,hooks,api}.ts`) over layer-folder; cross-feature imports go through a defined public surface
- **Provider sandwich:** > ~5 nested providers in `app/layout.tsx` / `App.tsx` - consolidate into a `<Providers>` wrapper

### Phase D - AI-Generated Code Quality

Use skill: `complexity-review` for verbosity, over-engineering, simplification.

Use skill: `react-overengineering-review` for React-specific overengineering: premature memo / `useCallback`, single-consumer Context, store-for-two-slices, single-use custom hooks, generic-for-one-usage, premature compound components, prop -> state -> effect sync.

**deep only:** before flagging an abstraction as premature, grep the repo for the same pattern - an abstraction that already exists three times elsewhere is a convention, not inflation.

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

Spawn these as early as Step 4, so they run while Phases 0 and A-E proceed on the main thread. For each selected scope, spawn one independent subagent **in parallel**. Use the **declared subagent for that scope** (`subagent_type` below) - do not infer the agent from the scope name; an observability review is not a `react-tech-lead` spawn:

| Scope | Skill                             | Subagent (`subagent_type`)     |
|-------|-----------------------------------|--------------------------------|
| + Perf | `task-react-review-perf`          | `react-performance-engineer`   |
| + Sec  | `task-react-review-security`      | `react-security-engineer`      |
| + Obs  | `task-react-review-observability` | `react-observability-engineer` |
| + Rel  | `task-react-review-reliability`   | `react-reliability-engineer`   |

`Full` = 4 subagents.

**Subagent prompt contract** - each must include:

- The resolved review target (`base_ref`, `head_ref`) plus the pre-read diff and commit log (no re-running git)
- The depth level
- Pre-confirmed stack (React `<version>`) + detected framework (Next.js App Router / Pages Router / Vite + React Router) with version
- Instruction to return findings in its own Output Format

**Failure isolation:** if a subagent fails or times out, continue with the rest. Note the missing scope in Summary.

**No-subagent runtime:** if the runtime cannot spawn subagents, run each selected lens inline in sequence and merge identically - the Step 6 contract is agnostic to how findings were produced. An inline lens is still in subagent mode: it returns its findings to this workflow and **writes no report of its own**, so a Full review produces one file, not five.

### Step 6 - Assemble and Deduplicate

Runs on every scope, whether or not Step 5 ran: Phase 0, Phase B, Phase C and Phase D can all raise the same defect (an ORM row crossing the RSC boundary is reachable from `react-nextjs-patterns`, `react-server-data-layer` and Phase C's server-only-import rule). Collapse those into one entry before Step 6.5 verifies them.

When Step 5 ran, also merge the subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate** cross-cutting findings (one entry citing all scopes that raised it)
- **Carry each finding's `Label` through unchanged.** Every lens computes its own `[Must]` / `[Recommend]` before returning; re-deriving a label from the bucket heading would override the lens's own rule and the verify pass's `Label` column, which both take precedence. Where two reports raise the same finding with different labels, `[Must]` wins. Nothing is dropped for its bucket: a lens that labelled a finding `[Recommend]` meant it to be emitted
- **Preserve `file:line` citations** from the originating subagent
- **Order by intent**, not by scope
- **Note missing scopes** in Summary as `Scope incomplete: <scope>`
- **Merge Next Steps** with `[Implement]` / `[Delegate]` tags preserved; re-sort by intent
- **Preserve every non-finding section** a subagent returned (each lens's `Recommendations`, security's `OWASP Triage` and `Could Not Verify From Diff`, observability's `Surface Map`, reliability's `Failure-Mode and User-Impact Map`, perf's `Capacity and Budget Plan`) under `## Scope Sections` - they are not findings and the merge must not drop them

### Step 6.5 - Verify Findings (second pass)

Use skill: `review-finding-verify` with the assembled findings (including any merged back from subagents), the diff already read, and `base_ref` / `head_ref`.

Runs before reconciliation so prior-round matching sees the corrected set. Publish only rows whose Verdict is not `Dropped`, carrying the skill's `Label` column. Carry its tally into Summary in the full contracted shape - the `(<F> false positive, <R> resolved by diff)` parenthetical when K > 0, and the `; <U> of these unverified` clause when any surviving row is unverified.

### Step 6.6 - Reconcile Prior Findings (round 2+ only)

Skip on round 1. Otherwise Use skill: `review-prior-findings-reconcile` with:

- `prior_report`: read `prior_checkpoint.report_path` now and pass its body (frontmatter excluded)
- `diff`: the full-range diff from Step 3
- `name_status`: the full-range `git diff --name-status <base_ref>...<head_ref>` from Step 3

The reconcile skill returns a Markdown table and a tally line. Insert the table under `## Prior Round Reconciliation` in the report (see Output Format).

`Still open` **and `Needs re-check`** rows are unresolved: carry both into `## High-Impact Findings` with their original label and a `(open since round <prior.round>)` suffix, so the Assessment rule sees a carried `[Must]` and the next round can reconcile them again. Mirror each in `## Next Steps` with the same suffix. Do not emit a standalone "Carry-Over Open Items" section.

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review` and these checkpoint fields:

- `branch` = the head's short name: when the handle's `head_ref` is the literal `HEAD` use its `current_branch`, and when it resolved from `refs/remotes/` strip the leading `<remote>/` segment (`origin/feature/x` -> `feature/x`) so this round and the next chain on one file. Never pass `HEAD` or a remote-prefixed name, `base_ref`, `base_sha = current_base_sha`, `head_ref`, `head_sha = current_head_sha`
- `mode: full` (the writer's only accepted value), `round` (from Step 3.5), `prior_head_sha` (omit on round 1)
- `scope` (resolved in Step 4, mapped to the writer's enum: `Core` -> `core-only`, `+Sec` -> `+sec`, `+Perf` -> `+perf`, `+Obs` -> `+obs`, `+Rel` -> `+rel`, `Full` -> `full` - the writer rejects unmapped display values), `depth` (resolved/auto-promoted), `stack = typescript-nextjs` (Vite: `typescript-react`)

Write before ending; print the confirmation line.

## Feedback Labels

| Label        | Meaning                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| [Must]       | Do not merge until this is fixed.                                        |
| [Recommend]  | Fix, or push back with reasoning. Cannot be silently acked.              |

No `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` - if it isn't `[Must]` or `[Recommend]`, don't write it down.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Assessment follows the open-label set, not a mood:** `Request Changes` when any `[Must]` is open (new this round or carried); `Approve` when no `[Must]` is open, even if `[Recommend]`s remain; `Discuss` when the blocker is a design disagreement a finding cannot settle.

```markdown
## Summary

- **Assessment:** Approve | Request Changes | Discuss
- **Risk Level:** Low | Medium | High | Critical
- **Blast Radius:** Narrow | Moderate | Wide | Critical
- **Stack Detected:** React <version> / TypeScript <version>
- **Framework:** Next.js (App Router) <version> | Next.js (Pages Router) <version> | Vite + React Router <version>
- **Scope:** Core | +Sec | +Perf | +Obs | +Rel | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
- **Depth:** standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_
- **Assessment basis:** <the open-label set the Assessment line was read from: `<n> Must open, <n> Recommend open`>
- **Round:** <N>                                _(include from round 2 onward)_
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff) _(the parenthetical only when K > 0)_; <U> of these unverified _(that clause only when a surviving row is unverified)_
- **Requirement Source:** <path or origin> (Specified | Self-attested) _(this line and the next are emitted together, or both omitted when Phase 0 resolved no source)_
- **Requirement Fit:** <n> met, <n> partial, <n> unmet, <n> deferred, <n> untraceable
- **Notes:** <one line per round, scope or depth note the Workflow requires - `Prior report lacks checkpoint metadata`, `Same head as round <N>`, `Prior checkpoint unreachable`, `Base branch advanced`, `Base ref changed`, `Scope expanded round <N>`, `Scope narrowed vs round <N>`, `Depth narrowed vs round <N>`, `Scope incomplete: <scope>`, and the auto-escalation signal log; omit the line when none apply>

## Change Brief

**Requested:** <what the change was asked to do, citing the source; `(inferred from commits)` when no source resolved>

**Delivered:** <the mechanism implemented and where>

**Author decisions:** <each choice the request did not imply, with its consequence, excluding choices already raised as findings; `None observed` when nothing remains>

**Watch points:** <what to confirm by hand before reading findings; `None` when there are none>

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

### [Must] file:line

- Provenance: [only when the verify pass set one: `_(pre-existing)_`, `_(pre-existing; newly reachable via <path>)_`, `(unverified: <reason>)`. `review-prior-findings-reconcile` keys its `untouched` classification on this, so dropping it misclassifies the finding next round. Omit the line when the verdict was `Confirmed`.]
- Issue: [name the React idiom: `"use client"` at root of layout, missing Zod on Server Action, RSC leaking `passwordHash` across Client boundary, `useEffect` for derived state, missing `key`, `dangerouslySetInnerHTML` on user input, `NEXT_PUBLIC_` secret, etc.]
- Impact: [user-visible or operational]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete React change with code]

### [Recommend] file:line
- Issue: ...
- Impact: ...
- Fix: ...

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

## Scope Sections

_One subsection per extra scope that returned content the merged Findings list cannot hold: every lens's `## Recommendations`; security's `## OWASP Triage`, `## Could Not Verify From Diff` and its `+N unverifiable` count; observability's `## Surface Map`; and every `deep`-only section (reliability's `Failure-Mode and User-Impact Map`, perf's `Capacity and Budget Plan`). Reproduce each under a `### <scope>: <section name>` heading, unedited. A lens's own Summary block is not reproduced - fold anything in it that changes a verdict into the finding it supports. Omit the whole section when no scope returned one._

## Key Takeaways

2-4 bullets on systemic impact and what to address before merge.

## Next Steps

On round 2+, prior-round Still open items are folded in with (open since round <N>) suffix and ordered by intent alongside new findings. Each item tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend.

1. **[Implement]** [Must] file:line - [one-line action, e.g., move `"use client"` from app/dashboard/layout.tsx to app/dashboard/_components/Filters.tsx and revert the layout to a Server Component]
2. **[Implement]** [Recommend] OldList.tsx:88 - missing key on reorderable list (open since round 1)
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
- Delegate perf / security / observability / reliability depth to subagents

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (or accepted from parent)
- [ ] Step 2: stack confirmed as React; framework and React version recorded
- [ ] Step 3: `review-precondition-check` ran (or handle received); a fail-fast was surfaced verbatim and stopped the run; diff and commit log read once and reused; current_head_sha and current_base_sha captured, and `branch` resolved to a real branch name rather than `HEAD`
- [ ] Step 3.5 - round decided (1 / prior + 1 / no-op); auto-fetch attempted only when prior checkpoint exists; the full `<base_ref>...<head_ref>` range analyzed regardless of round; no-op path exits without writing the report
- [ ] Step 4: scope auto-escalation evaluated; promotion (or `core-only` suppression) recorded with firing signals
- [ ] Phase 0 - `review-change-intent` ran on the cumulative diff; Change Brief carried into the report; requirement lines in Summary, or all three requirement outputs omitted when no source resolved; its findings verified with the rest
- [ ] Phase A: risk level and blast radius stated before any finding; depth auto-promoted to `deep` when Blast Radius is Wide/Critical; low-risk short-circuit applied when applicable
- [ ] Phase B: atomic skills applied (`react-hooks-patterns`, `react-component-patterns`, `react-state-patterns`, `react-data-fetching`, plus `react-nextjs-patterns` / `react-routing-patterns` when relevant); the conditional delegations fired when their trigger appeared (`react-server-data-layer`, `backend-transaction-patterns`, `react-selfhost-operations`, and the API contract gate's `backend-api-guidelines` + `ops-backward-compatibility`); test coverage, RSC -> Client ORM leak, TS strict and a11y checked. Security depth (`dangerouslySetInnerHTML`, open redirect, `NEXT_PUBLIC_*`) is checked here only when the +Sec scope is not running
- [ ] Phase C: layering, RSC / Client split, custom hook / prop drilling / context discipline, settings, module boundaries, provider sandwich applied
- [ ] Phase D: `complexity-review` + `react-overengineering-review` applied; React AI smells covered (pattern inflation, over-abstraction, redundant prop transforms, `useEffect` misapplication, memo overuse, `as any`, anonymous default-export components)
- [ ] Phase E: naming, co-location, magic numbers, component length, conditional ladders, logging hygiene
- [ ] Missing tests raised as a named finding (not buried)
- [ ] Every Must cites system risk
- [ ] Every finding has label + `file:line` + actionable React fix
- [ ] Step 5: extra scopes ran in parallel with the pre-resolved diff/log handle plus framework detection
- [ ] Step 6: cross-phase duplicates collapsed (runs whether or not Step 5 ran); subagent findings merged into one intent-ordered Findings list with each lens's `Label` carried through unchanged; raw reports not appended; every non-finding section preserved under `## Scope Sections`; failed/missing scope noted as `Scope incomplete: <scope>`; Next Steps tagged `[Implement]` / `[Delegate]`
- [ ] Depth honored: `standard` ran Phases A-E; `deep` additionally ran the Phase C and Phase D depth branches and spawned every extra scope at `deep`
- [ ] Assessment set from the open-label set per the Output Format rule, not from overall impression
- [ ] Step 6.5 - review-finding-verify ran on all assembled findings; Dropped rows excluded; verdict labels applied; tally in Summary
- [ ] Step 6.6 - on round 2+, review-prior-findings-reconcile ran; reconciliation table inserted; Still open rows folded into Next Steps with (open since round <N>) suffix
- [ ] Step 7: review report written via `review-report-writer` with full checkpoint fields (mode, round, prior_head_sha when round > 1, head_sha, base_sha, scope, depth, stack); confirmation line printed

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase). The one allowed exception is `git fetch <remote> <branch>` in Step 3.5a, and only when a valid prior checkpoint exists.
- Auto-fetching on round 1 (no prior checkpoint) - keeps first-run behavior strictly read-only.
- Scoping round 2+ analysis to `<prior_head_sha>...<head_sha>` - risk, scope, depth, and requirement fit score the full `<base_ref>...<head_ref>` range on every round.
- Writing the report on the Step 3.5b no-op exit (same `head_sha` **and** no added scope or depth) - the file must stay byte-identical. An equal SHA with expanded scope or depth is a real round and does write.
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`).
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
- Emitting a "Carry-Over Open Items" section - fold into Next Steps instead.
- Reviewing without reading the full diff and commit log first
- Generic frontend conventions when a React idiom exists ("extract to a custom hook", not "extract to a helper")
- Nitpicking style where no project standard exists
- Vague feedback ("this could be better")
- Blocking on personal preference
- Running extra scopes when `core-only` was passed
- Duplicating perf / security / observability / reliability depth here when the dedicated React subagent owns them
- Sequential extra scopes that could parallelize
- Appending raw subagent reports instead of merging
- Recommending `useEffect` for derived state, `"use client"` at the root of a layout, `dangerouslySetInnerHTML` on user input, or `NEXT_PUBLIC_` for secrets as acceptable
