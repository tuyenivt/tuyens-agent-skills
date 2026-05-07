---
name: task-react-review
description: React staff-level code review umbrella - Phases A-E (risk, correctness, architecture, AI quality, maintainability) with React idioms (RSC vs Client Component boundary, hooks rules, useEffect discipline, key correctness, state categorization, Server Action validation, dangerouslySetInnerHTML, prop-drilling vs context, accessibility regressions). Spawns React-specific perf / security / observability subagents for extra scopes. Stack-specific override of task-code-review for React. Runs standalone with full PR/branch resolution.
agent: react-tech-lead
metadata:
  category: frontend
  tags: [react, typescript, nextjs, vite, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the diff under review, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an acceptance criterion, NFR, or task; flag changes that touch out-of-scope items as **blockers**; flag missing coverage of in-scope acceptance criteria as gaps. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow.

# React Code Review

## Purpose

React-aware staff-level code review umbrella. Replaces the generic Phase A-E flow with React-specific correctness, architecture, AI-quality, and maintainability checks (Server vs Client Component boundary placement, hooks-rules violations, `useEffect` overuse for derived state, missing `key` / `key={index}`, state categorization (URL vs server vs client), prop-drilling smells, missing Zod validation on Server Actions, `dangerouslySetInnerHTML` audit, accessibility regressions, anemic prop interfaces). Coordinates React-specific perf / security / observability subagents in parallel for extra scopes.

This workflow is the stack-specific delegate of `task-code-review` for React. The core workflow's contract (depth levels, scope auto-escalation, low-risk short-circuit, output format) is preserved. **Runs standalone** with full PR/branch resolution - the core dispatcher is optional.

## When to Use

- Reviewing a Next.js or Vite + React PR before merge
- Post-AI-generation quality gate on a React change set
- Architecture drift detection in a React codebase
- Pre-merge risk assessment on a React branch

**Not for:**

- Pre-implementation feature design (use `task-react-new`)
- Active production incident triage (use `/task-oncall-start`)
- Single-error debugging (use `task-react-debug`)
- Architecture/design review of a new system (use `task-design-architecture`)
- Single-scope reviews when only one concern matters - delegate directly to `task-react-review-perf`, `task-react-review-security`, or `task-react-review-observability`

## Depth Levels

Mirrors `task-code-review`:

| Depth      | When to Use                                                               | What Runs                                                    |
| ---------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `quick`    | "Is this safe to merge?" - fast risk snapshot for time-constrained review | Risk snapshot + top 3 findings only (Phases A and B summary) |
| `standard` | Default - full React staff-level review                                   | Phases A-E                                                   |
| `deep`     | Architectural PRs, post-incident change review, or Principal sign-off     | Phases A-E + historical pattern matching + cross-PR context  |

Default: `standard`.

**Auto-promote to `deep`:** After Phase A computes blast radius, if `Blast Radius` is `Wide` or `Critical` and the user did not explicitly pass `quick`, promote depth from `standard` to `deep` automatically. Surface in Summary as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                                  |
| --------------- | -------------------------------------------------------------------------- |
| Core            | Phases A-E only (React-flavored)                                           |
| + Perf          | Core + parallel subagent: `task-react-review-perf`                         |
| + Security      | Core + parallel subagent: `task-react-review-security`                     |
| + Observability | Core + parallel subagent: `task-react-review-observability`                |
| Full            | Core + Performance + Security + Observability (3 parallel React subagents) |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Scope auto-escalation signals (React-tuned):**

- New Server Action / Route Handler / `middleware.ts` change, `dangerouslySetInnerHTML` introduction, auth library / session config change, `NEXT_PUBLIC_*` additions, new file upload / `<form action={...}>`, new `redirect(...)` from user input, CSP / `next.config.headers()` change → auto-add **+Security**
- New route / page / layout, new `"use client"` component, new client-side dependency in `dependencies`, new TanStack Query usage, new `next/image` / `next/font` change, new `next/dynamic` / `React.lazy`, ISR / `revalidate` change, new long list rendering → auto-add **+Perf**
- New `instrumentation.ts`, new Sentry / RUM SDK init, new `web-vitals` reporter, new error boundary, new logging utility, new analytics call → auto-add **+Observability**
- Two or more signal categories present → promote to **Full**

## Invocation

The slash command accepts an optional argument identifying the diff to review:

| Invocation                    | Meaning                                                                                                                                                                               |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-react-review`          | Review current branch vs its base - fails fast if on a trunk branch (`main`/`master`/`develop`); commit or switch to a feature branch first                                           |
| `/task-react-review <branch>` | Review `<branch>` vs its base (3-dot diff) - cross-review a teammate's branch checked out locally, or self-review a named branch from any session                                     |
| `/task-react-review pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` - run `git fetch origin pull/<N>/head:pr-<N>` first (user runs it; see `review-precondition-check` for GitLab/Bitbucket variants) |

**No checkout required.** Stay on your current branch; the workflow reads git history via ref-qualified diffs.

**Explicit base override.** When the PR was opened against a non-trunk base branch, pass `--base <branch>`.

Examples:

- `/task-react-review pr-123 --base release/2026.05`
- `/task-react-review feature/x --base develop`

Scope and depth flags compose: `/task-react-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm React. If invoked as a delegate of `task-code-review` (parent already detected React), accept the pre-detected stack and skip re-detection. If the detected stack is not React, stop and tell the user to invoke `/task-code-review` instead.

Detect framework: Next.js (App Router / Pages Router) vs Vite + React Router. Record `Framework: ...`, `React: <version>`. Each Phase B / C / D / E checklist below branches on this signal where the idiom differs.

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

**Low-risk short-circuit:** If Phase A yields Risk Level: Low and Blast Radius: Narrow, **and** the change does not touch architecture-relevant files (auth config, middleware, route layouts, shared providers / contexts, `next.config.js`, `vite.config.js`, top-level `App.tsx` / `app/layout.tsx`), skip Phases C-D and produce a streamlined output with Phase B findings only.

### Step 3.5 - Re-evaluate Depth After Phase A

If `Blast Radius` is `Wide` or `Critical` and the user did not explicitly pass `quick`, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)` in the Summary. Do this **before** launching Phases B-E so deep-only behaviors (historical pattern matching, cross-PR context, anemic-prop assessment) are in scope.

### Phase B - React Correctness and Safety

Logical correctness, error handling completeness, edge cases affecting UI integrity, backward compatibility, hydration correctness, accessibility - through a React lens.

**Test coverage finding:** If the PR adds or modifies logic without corresponding Vitest coverage, raise this as an explicit finding. At minimum a [Suggestion]; escalate to [High] when the change is in a critical path - any of: authentication / session UI, Server Actions, money / billing UI, form validation, multi-step flows, error boundaries. Do not bury this finding in Key Takeaways.

**React-specific correctness checks (both frameworks):**

- [ ] **TypeScript strict mode**: `strict: true` not silently disabled; `as any` flagged outside test setup; `noImplicitAny` / `strictNullChecks` not relaxed; component prop interfaces are typed (no `props: any`)
- [ ] **Hooks rules**: `useState` / `useEffect` / custom hooks called at the top level - never inside conditions, loops, or after early returns. `eslint-plugin-react-hooks` enabled; flag any `// eslint-disable-next-line react-hooks/rules-of-hooks` without a comment justifying
- [ ] **`useEffect` discipline**: every `useEffect` synchronizes with an external system (subscription, DOM, interval, network). Effects for "compute derived state" (`useEffect(() => setX(a + b))`), event handling (`useEffect(() => { if (clicked) ... })`), or "running on mount" (when initialization could happen during render) are smells - flag and recommend the right primitive
- [ ] **`useEffect` dependency array correct**: every value used inside the effect appears in the deps array OR is a stable ref (set state, ref); flag exhaustive-deps eslint disables; flag `[]` deps when the effect uses props / state (stale closure)
- [ ] **`useEffect` cleanup**: subscriptions / observers / intervals return a cleanup function; flag missing cleanup as a [High] memory-leak finding
- [ ] **Missing `key` on lists / `key={index}`**: `.map((item, index) => <Row key={index} />)` is wrong on a reorderable / filterable / removable list - reconciliation breaks. `key={item.id}` (stable) is right. Flag both
- [ ] **`"use client"` placement (Next.js)**: directive is at the leaf of the tree (a small interactive component), not the root of a layout / page. A root-level `"use client"` pulls the entire descendent tree into the client bundle and defeats RSC. Flag as a [High] correctness + perf finding
- [ ] **Unnecessary `"use client"` (Next.js)**: a Client Component file with no hook, event handler, browser API, or `useState` / `useEffect` / `useRef` - revert to Server Component. The umbrella review owns presence (it's a code smell signaling confused mental model); `task-react-review-perf` owns the bundle-cost depth
- [ ] **State / hooks in Server Component (Next.js)**: any `useState` / `useEffect` / `useRef` in a file without `"use client"` is a build error - flag as a code smell that signals confused mental model even if the build catches it
- [ ] **Server Component data leak**: Server Component passing entire ORM rows (Prisma model / TypeORM entity) as a prop to a Client Component serializes internal fields (`passwordHash`, `mfaSecret`) into the page HTML. Project to a DTO at the data layer or before passing the prop
- [ ] **Server Action input validation (Next.js)**: every `'use server'` function or `<form action={...}>` target validates input via Zod / `zod-form-data` `.strict()` at the top, before any auth or DB call. Missing validation is a [High] / [Blocker] depending on whether the action mutates data; raw `Object.fromEntries(formData)` going into `prisma.x.update({ data })` is a critical mass-assignment finding (`{ role: 'admin' }` in a FormData wins)
- [ ] **Server Action authorization (Next.js)**: every Server Action that mutates data calls `await auth()` (or session equivalent) at the top and verifies the principal can act on the resource (object-level scoping, not just authenticated). An IDOR via Server Action is the same severity as IDOR via REST endpoint
- [ ] **`'use server'` file exports only Server Actions (Next.js)**: a file with the `'use server'` directive at the top makes every export network-callable. Re-exporting a utility (`export { formatOrderId } from './utils'`) silently exposes that utility as an authentication-less, validation-less network endpoint. Flag any non-action export in a `'use server'` module as [High] - the depth (exploit walkthrough) belongs to `task-react-review-security`, but the umbrella review owns presence/absence
- [ ] **Server Action return value leaks server-only fields**: `return order` where `order` is a full Prisma row leaks `internalNotes` / `paymentMethodToken` back through the Server Action response into client-visible state. Project to a DTO before returning, or use Prisma `select` / `omit`
- [ ] **`middleware.ts` change widens the public surface**: a new entry in `matcher` exclusions (`'/api/test/*'`, `'/internal/*'`) without a security comment justifying why the route is exempt from auth is a [High]. The depth (whether the route should be public) belongs to security review; the umbrella owns presence
- [ ] **`dangerouslySetInnerHTML` on user input**: any usage where the HTML originates from user input, URL params, or external API must be sanitized (`DOMPurify` client / `sanitize-html` server). Flag as Critical when the content path is user-controllable
- [ ] **Open redirect**: `redirect(searchParams.get('returnTo'))` (Next.js) / `navigate(returnTo)` (React Router) without allowlist or relative-path-only check (`url.startsWith('/') && !url.startsWith('//')`)
- [ ] **`NEXT_PUBLIC_*` for secrets**: `process.env.NEXT_PUBLIC_*` referencing API keys, DB URLs, or signing secrets compiles into the client bundle - flagged as Critical
- [ ] **Form accessibility**: `<input>` has an associated `<label>` (via `htmlFor` or wrapping); error messages associated via `aria-describedby`; submit button has accessible name; required fields use `aria-required` (or `required`) and surface validation errors when invalid
- [ ] **Interactive accessibility**: dialogs use `<dialog>` or proper ARIA (`role="dialog"`, `aria-modal`, focus trap, return-focus on close); menus use `role="menu"` / proper key handling; new interactive components built on Radix / shadcn primitives by default rather than reinventing keyboard handling
- [ ] **Image / media**: `next/image` (Next.js) or explicit `width`/`height` on raw `<img>` to prevent CLS; `alt` attribute present (empty string `alt=""` for decorative); flag missing
- [ ] **Error boundaries**: components with non-trivial render logic / external data have an error boundary above them (Next.js: `error.tsx` per route segment; Vite: explicit `<ErrorBoundary>` wrapper). A bare `throw` in a render path crashes the whole tree if no boundary catches
- [ ] **Stale state in effects / closures**: refs (`useRef`) for mutable values needed inside callbacks; flag `setState` calls inside effects that read prior state without the functional setter form
- [ ] **`useRef` vs `useState`**: refs do not trigger re-render; flag `useState` for values used only inside `onChange` handlers / refs but never rendered
- [ ] **Async state setter after unmount**: `useEffect(() => { fetch().then(setX) }, [])` without cleanup or `AbortController` produces "state update on unmounted component" warnings; modern React tolerates it but the underlying request is wasted - flag for an `AbortController`

**Concurrency / state-management safety:**

- [ ] **State categorization**: state lives in the right place - URL (search params for filters / page / sort), server (TanStack Query for fetched data), local (`useState` for UI-only). Flag `useState` for filter state when the URL would deep-link better; flag client-side caching of server state when TanStack Query / Server Components handle it
- [ ] **Context boundaries**: a context that re-renders every consumer on every change (no memoized value, no split provider) for a frequently-changing piece of state - flag for memoization or state-management library (Zustand / Jotai)
- [ ] **No mutable module-level state**: `let counter = 0; export function inc() { counter++; }` works in dev with HMR but is a smell - flag for state lib or for moving the state inside a hook / component

Use skill: `react-component-patterns` for canonical component shape.
Use skill: `react-hooks-patterns` for canonical hook patterns.
Use skill: `react-data-fetching` for canonical data-fetching patterns.
Use skill: `react-state-patterns` for state-management patterns.

### Phase C - React Architecture Guardrails

Use skill: `architecture-guardrail` to detect layer violations, new coupling, circular dependency risk, bypassing abstractions, boundary erosion.

**React-specific architecture checks:**

- [ ] **Component layering**: presentational vs container distinction not strict, but business logic does not live inside `<Card>` / `<Button>` / leaf components - it lives in pages / containers / custom hooks. Flag fetch calls inside leaf components, business decisions in display components
- [ ] **Server Component boundary discipline (Next.js)**: data fetching lives in Server Components; Client Components receive props or use TanStack Query for client-driven fetching. Flag `useEffect(() => fetch(...))` inside a Client Component when a Server Component parent could fetch and pass props
- [ ] **Custom hook discipline**: a custom hook that takes 8 different params and returns 12 fields signals it should be split or replaced with a context / state lib. Flag god hooks
- [ ] **Prop drilling depth**: a prop threaded through 4+ component layers is a smell - hoist to a context or a state library. Flag chains of pure pass-through props
- [ ] **Context overuse**: a context for state that only one consumer reads (where prop / lift would suffice) - flag as unnecessary indirection
- [ ] **Routing discipline**: route components are thin (delegate to feature components); business logic is not in `app/**/page.tsx` directly. Flag route files with > 100 lines of orchestration
- [ ] **Settings / config discipline**: typed config (`@/lib/config.ts` with Zod schema, or `next.config.js` typed) - flag `process.env.X` sprinkled across components; centralize so missing-at-startup fails fast
- [ ] **Module / package boundaries**: feature-folder layout (`src/features/orders/{components,hooks,api}.ts`) preferred over layer-folder (`src/components/`, `src/hooks/` for everything); cross-feature imports go through a defined public surface
- [ ] **Server / Client split discipline (Next.js)**: a Client Component that imports a server-only utility (`fs`, `node:crypto`, ORM client) is a build error / bundle leak - flag any cross-boundary import that violates the contract
- [ ] **Provider sandwich**: more than ~5 nested providers in `app/layout.tsx` / `App.tsx` signals a `<Providers>` consolidation. Not a hard rule, but flag for cleanup

### Phase D - AI-Generated Code Quality Control

Use skill: `complexity-review` to detect verbosity, over-engineering, and simplification opportunities.

**React-specific AI smells:**

- [ ] **Pattern inflation**: generic `<DataTable<T>>` for a single use case where a typed concrete component would suffice; HoC + render prop + hook trio when one suffices; `forwardRef` where a ref prop would do (or unnecessary entirely)
- [ ] **Over-abstraction**: `BaseFormField` parent component for 2 children; premature compound components (`<Tabs.Root><Tabs.List><Tabs.Trigger>`) when a flat prop API would do; "headless" abstraction for one consumer
- [ ] **Speculative configurability**: props with documented but unused values; theme variants for a single design; "extensibility" hooks that no caller uses
- [ ] **Redundant prop transforms**: prop → state-for-prop → effect syncing them - just use the prop directly. The `getDerivedStateFromProps` / "store prop in state" pattern is almost always wrong
- [ ] **`useEffect` for things that should be event handlers**: `useEffect(() => { if (clicked) handleClick() })` triggered by setting `clicked` in an `onClick` - just call `handleClick` directly
- [ ] **`useMemo` / `useCallback` everywhere**: memoization on cheap values costs more than it saves; only use when the value is a stable ref for `React.memo` children or feeds an effect's deps
- [ ] **Test verbosity**: `render(<Wrapper><Wrapper2><Component /></Wrapper2></Wrapper>)` setup chains; mocking the entire module when a single function would do; full-tree snapshots
- [ ] **Comment cruft**: comments restating prop names; JSDoc on private internal helpers; `// TODO` markers without owner / date
- [ ] **`as any` / `as unknown as T` proliferation**: legitimate uses are rare; `as any` to bypass a real type bug is a finding. `as React.FC<Props>` (deprecated typing) may signal copy-paste from older docs
- [ ] **Try-catch noise**: `try { await x() } catch (e) { throw e }` - delete; `try { ... } catch (e) { setError(e.message) }` loses the cause - use `setError(e instanceof Error ? e : new Error(String(e)))`
- [ ] **Anonymous default exports for components**: `export default function() { ... }` makes stack traces unhelpful and breaks React DevTools display name. Named function or `displayName` set

### Phase E - React Maintainability and Clarity

Naming that obscures intent, mixed responsibilities, large unreviewable chunks, hardcoded values that should be config or constants.

**React-specific maintainability checks:**

- [ ] **Naming conventions**: components in PascalCase (`OrderList`); hooks `use<Noun>` (`useOrderFilters`); event handlers `handle<Event>` or `on<Event>`; no abbreviations (`OrdLst` is wrong); display name set on memoized / forwardRef components
- [ ] **File / component co-location**: each feature has its components, hooks, types, tests co-located in a folder; not scattered across `src/components/`, `src/hooks/`, `src/types/` for one feature
- [ ] **Magic numbers / strings**: extracted to module-level constants or config; route paths declared in a typed `routes.ts` rather than string literals scattered
- [ ] **Hardcoded URLs / API endpoints**: in env vars / config, not inline (allows env-specific behavior)
- [ ] **Component length**: components > 200 lines reviewed for extraction; extract sub-components, custom hooks, or move logic to utility functions
- [ ] **Conditional rendering ladders**: > 3 nested `&&` / ternary in JSX → extract to a function returning JSX or a sub-component; readability degrades fast
- [ ] **Logging / error reporting hygiene**: surface obvious offenders as Core findings - `console.log` in a render body (called on every render, leaks PII into devtools and may be picked up by RUM forwarders), `console.log(JSON.stringify(largeObject))` of any non-trivial payload (the serialization cost itself is noticeable), `console.error` outside of error boundary fallbacks / dev paths, production errors not routed through Sentry / RUM SDK. The observability subagent owns depth (sample rates, attribution, instrumentation API); do not duplicate that audit here. If observability is not in scope this run, still surface obvious offenders so they are not lost

Use skill: `frontend-coding-standards` if the project has one (otherwise rely on TS strict + ESLint + project-specific conventions).
Use skill: `ops-observability` for cross-cutting logging/metrics presence (the `task-react-review-observability` subagent owns depth).

### Step 4 - Delegate Extra Scopes in Parallel (if scope includes)

If scope is **Core only**, skip this step.

For any selected extra scope, spawn an independent subagent **in parallel** with the main thread (which continues running Phases A-E for Core).

| Scope                | Subagents spawned                                                                                                         |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Core + Perf          | 1 subagent running `task-react-review-perf`                                                                               |
| Core + Security      | 1 subagent running `task-react-review-security`                                                                           |
| Core + Observability | 1 subagent running `task-react-review-observability`                                                                      |
| Full                 | 3 subagents running `task-react-review-perf`, `task-react-review-security`, `task-react-review-observability` in parallel |

**Subagent prompt contract.** Each subagent prompt must include:

- The resolved review target from Step 2 (`base_ref`, `head_ref`) plus the already-read diff and commit log
- The depth level (`quick` | `standard` | `deep`)
- The pre-confirmed stack (React) and detected framework (Next.js / Vite) so the subagent skips its own `stack-detect` and framework branching
- Instruction to return findings using its own skill's Output Format

**Failure isolation.** If a subagent fails or times out, continue with the remaining results. Note the missing scope in the synthesized output rather than blocking the whole review.

### Step 5 - Synthesize (only if Step 4 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate cross-cutting findings.** The same issue may surface in multiple scopes (e.g., a `"use client"` at the root of a layout flagged by both Core/Phase B and Perf). Keep one entry, citing all scopes that raised it.
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
**Stack Detected:** React <version> / TypeScript <version>
**Framework:** Next.js (App Router) <version> | Next.js (Pages Router) <version> | Vite + React Router <version>
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line

- Issue: [what is wrong - name the React idiom: `"use client"` at root of layout, missing Zod validation on Server Action, Server Component leaking `passwordHash`, `useEffect` for derived state, missing `key`, `dangerouslySetInnerHTML` on user input, `NEXT_PUBLIC_` secret leak, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is a system-level concern, not just a local bug]
- Fix: [concrete React change with code example]

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
- Server / Client data flow: _(Next.js)_ when 3+ findings cluster around ORM rows being passed across the Server → Client boundary, name the systemic pattern here ("Server Components consistently pass full ORM rows across the Client boundary; introduce a DTO layer at app/lib/dto/**.ts") rather than producing N near-identical findings

## Maintainability Notes

_Same rule as Architecture Notes._

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

- 2-4 concise bullets summarizing systemic impact and what to address before merge.

## Next Steps

Prioritized action list. Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action, e.g., "Move `\"use client\"` from app/dashboard/layout.tsx to app/dashboard/_components/Filters.tsx; revert layout to Server Component"]
2. **[Delegate]** [High] [scope: design-system] - [one-line action]
3. **[Implement]** [Suggestion] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

**Omit empty sections.** If there are no Blockers, do not include a Blocker heading.

## Rules

- Review the whole change as a system impact, not file-by-file in isolation
- Lead with risk assessment before line-level findings
- Apply React conventions, not generic frontend conventions
- Provide actionable feedback with TypeScript / JSX code examples
- Never comment on trivial formatting or style where no project standard exists
- Default to Core scope; auto-escalate on signals; honor `core-only` flag
- Delegate perf / security / observability depth to the appropriate React subagent rather than duplicating the check here

## Self-Check

- [ ] Stack confirmed as React (or accepted from parent dispatcher); framework and React version detected
- [ ] `review-precondition-check` ran (or its handle was received); `base_ref` / `base_source` / `head_ref` / `current_branch` / `head_matches_current` captured. If `--base` passed, `base_source: explicit-override` recorded
- [ ] Diff and commit log were read once and reused by all phases (and shared with subagents) - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran
- [ ] Scope auto-escalation evaluated in Step 3; promotion (or `core-only` suppression) recorded in Summary along with the firing signals
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`
- [ ] Risk level and blast radius stated before any line-level findings
- [ ] Phase B - TypeScript strict + hooks rules + `useEffect` discipline + `key` checks applied
- [ ] Phase B - `"use client"` placement audited (Next.js); leaf-level placement preferred
- [ ] Phase B - Server Action input validation + authorization checked (object-level scoping, not just authenticated)
- [ ] Phase B - `'use server'` file checked for non-action exports (every export becomes a network endpoint)
- [ ] Phase B - Server Action return values checked for ORM-row leakage to client
- [ ] Phase B - `middleware.ts` `matcher` exclusions checked for justification when widened
- [ ] Phase B - Unnecessary `"use client"` (no client-only need) flagged as a code smell distinct from root-of-layout placement
- [ ] Phase B - `dangerouslySetInnerHTML`, open redirect, `NEXT_PUBLIC_*` secrets, Server Component → Client Component prop projection checked
- [ ] Phase B - accessibility (form labels, dialog ARIA, image alt, error boundary presence) checked
- [ ] Phase B - state categorization (URL / server / local) and context boundaries reviewed
- [ ] Phase C React architecture checks applied: component layering, Server Component boundary, prop-drilling, settings discipline, package boundaries
- [ ] Phase D AI-quality checks applied: pattern inflation, over-abstraction, speculative configurability, `useEffect` misapplication, memo overuse
- [ ] Phase E React maintainability checks applied: naming, magic numbers, component length, conditional rendering ladders, logging hygiene
- [ ] Missing tests raised as an explicit named finding (not buried in Key Takeaways)
- [ ] Every Blocker states a system risk, not just a code observation
- [ ] Every finding has a label, location (file:line), and actionable React fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged as out-of-scope blocker
- [ ] For non-Core scopes, React-specific subagents (`task-react-review-perf`, `-security`, `-observability`) ran in parallel and received the pre-resolved diff/log handle plus framework detection
- [ ] Subagent findings merged into the single Output Format with deduplication and highest-severity-wins; raw subagent reports not appended
- [ ] Any failed/missing subagent scope noted under Summary as `Scope incomplete: <scope>`
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Blocker > High > Suggestion (omitted only when no actionable findings exist)

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reviewing without reading the full diff and commit log first
- Applying generic frontend conventions when a React idiom exists (say "extract to a custom hook", not "extract to a helper")
- Nitpicking style where no project standard exists; no `[Nitpick]` or `[Praise]` labels
- Providing vague feedback without a concrete React fix ("this could be better")
- Blocking on personal preference rather than correctness, risk, or maintainability
- Running perf / security / observability sub-workflows when user passed `core-only`
- Treating auto-escalation signals as advisory; the default is to promote and let the user opt out via `core-only`
- Duplicating perf / security / observability depth checks here when the dedicated React subagent owns them - flag and delegate
- Running multiple extra scopes sequentially when they could spawn in parallel
- Appending raw subagent reports section-by-section instead of merging into one severity-ordered Findings list
- Recommending `useEffect` for derived state, `"use client"` at the root of a layout, `dangerouslySetInnerHTML` on user input, or `NEXT_PUBLIC_` for secrets as acceptable - all are anti-patterns
