---
name: task-code-review
description: Code review entry point: risk, correctness, maintainability. Detects stack and dispatches to stack-specific review workflow.
metadata:
  category: review
  tags: [code-review, pull-request, risk-assessment, multi-stack, router]
  type: workflow
user-invocable: true
---

# Code Review (Router)

Detects the project stack and delegates to the matching stack-specific review workflow (`task-{stack}-review`). When no stack workflow is available, runs a minimal generic Phase 0-E review.

## When to Use

- PR review, pre-merge risk assessment, post-AI-generation quality gate.

**Not for:** New-system architecture, security-only audits (`task-code-review-security`), perf-only (`task-code-review-perf`), observability-only (`task-code-review-observability`), reliability-only (`task-code-review-reliability`).

## Invocation

`/task-code-review [<branch> | pr-<N>] [+perf | +sec | +obs | +rel | full | core-only] [standard | deep] [--base <branch>] [--req <path>]`

Scope flags combine (`+sec +perf`); `full` expands to all four. All flags are forwarded to the dispatched stack workflow. `--req <path>` names a requirement source for Phase 0 (ticket export, PRD, spec); without it Phase 0 resolves the source in `review-change-intent`'s order (requirement text in context, an in-tree spec the change names, the prior round's source, then a PR body or commit messages that enumerate criteria).

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Universal and unconditional.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Dispatch to Stack Workflow

| Detected stack       | Delegate to           | Plugin    |
| -------------------- | --------------------- | --------- |
| Java / Spring Boot   | `task-spring-review`  | `java`    |
| Python               | `task-python-review`  | `python`  |
| Ruby / Rails         | `task-rails-review`   | `ruby`    |
| Node.js / TypeScript | `task-node-review`    | `node`    |
| Go / Gin             | `task-go-review`      | `go`      |
| React / Next.js      | `task-react-review`   | `react`   |
| C# / Unity           | `task-unity-review`   | `unity`   |
| Dart / Flutter       | `task-flutter-review` | `flutter` |

Dispatch keys on the detection's primary `Language` / `Framework` pair; a secondary stack in `Additional` never dispatches. A row matches when both its language and its framework match - a trailing version never blocks a match (`Spring Boot 4.1`, `Unity 6000.3.21f1`) and the Ruby row matches `Rails` or `Ruby on Rails`, while another language or framework does (Kotlin / Spring Boot and Java / Micronaut take the fallback). Python matches under any framework; Node.js / TypeScript matches Language `JavaScript` or `TypeScript` with a server framework (NestJS, Express, Fastify, Koa, Hono) or `unknown`; a Framework naming Next.js (`React (Next.js)`, `Next.js 16.3 (App Router)`) takes the React row, and every other frontend framework (Vite, CRA, React Router, Remix, Vue, Angular, Svelte) matches no row. Exactly one outcome follows, its one-line announcement printed in chat before anything else (Step 4's precondition prompts and the user's answers follow it) and never part of `report_body`:

- Matched and installed: `Dispatching to task-rails-review.` (substitute the target); invoke it with the user's argument string unchanged (target ref, `--base`, `--req`, scope, depth), except `full`, which expands to `+perf +sec +obs +rel` because not every stack umbrella accepts a bare `full`; then stop - Steps 4-5 do not run. The announcement is the router's only output: the forwarding is the invocation, not printed, and the detection block stays internal. The stack umbrella owns precondition checks, diff resolution, sub-scope dispatch, and the report.
- Matched, plugin not installed: `task-rails-review is provided by the ruby plugin, which is not installed - running the generic review.` (substitute target and plugin); run Steps 4-5.
- No row: `No stack workflow for <Language> / <Framework> - running the generic review.`; run Steps 4-5.

### Step 4 - Generic Fallback (no dispatch)

Use skill: `review-precondition-check` with `argument` (the user's target, if any - default target: current branch), `base` (from `--base`, if given), and `report_type: review`. On failure, surface the message verbatim and stop. On success, print each handle `notes` entry in chat, one line each, before the report body (nothing when it has none; the handle itself stays internal), capture `base_sha`/`head_sha` via `git rev-parse <base_ref>` / `git rev-parse <head_ref>`, decide the round from the table below (the same-SHA stop needs only the SHAs, the handle and the checkpoint), and only then read once: `git diff <base_ref>...<head_ref>`, `git log <base_ref>..<head_ref>`, and `git diff -M --name-status <base_ref>...<head_ref>`.

**Round** (from the handle's `prior_checkpoint`). Every round analyzes the full `<base_ref>...<head_ref>` range - risk, scope, and requirement fit score the whole change each time, so a small follow-up commit cannot under-score a large PR. Rounds differ only in that round 2+ reconciles against the prior report:

| Checkpoint state                                                        | Decision                                                          |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Absent, or `prior_checkpoint: legacy`                                    | `round: 1` (legacy report is overwritten)                          |
| `prior head_sha == head_sha`, `prior base_ref == base_ref`, and the checkpoint's `scope`/`depth` cover the requested ones (covering = superset: `full` covers every scope, `+perf +sec` covers `+sec`, any scope covers `core-only` - flags add lenses to the core review; `deep` covers `standard`) | Print `No new commits since prior review.` and stop - no report |
| `prior head_sha == head_sha`, and the base differs or the requested scope or depth exceeds the checkpoint's | `round: prior + 1` - same commits, new range or wider lens          |
| Otherwise                                                                | `round: prior + 1`                                                 |

**Prior-round reconciliation.** On round 2+, Use skill: `review-prior-findings-reconcile` with the prior report body (the file at the handle's `report_path`), the full-range diff, the name-status, and `head_sha`; its output (table, any note lines, tally) goes verbatim under `## Prior Round Reconciliation`. Round 1 skips it. Run it after the phases below and after **Verify findings**, so this workflow matches its rows against the verified set (reconcile itself takes only the inputs above). `Still open` and `Needs re-check` rows are unresolved and carry forward. A carried finding the current phases re-derive (they drafted a finding on the same construct) publishes once, as this round's finding with this round's label and verify's `file:line`, noted `_(carried from round <N>)_` (`<N>` = the prior report's own `round` frontmatter value); its reconciliation row and Next Steps entry are its only other appearances. A carried finding the phases did not re-derive is carried into High-Impact Findings at its prior label with the same note and its prior heading's annotation groups (a prior `_(carried from round ...)_` group replaced by this note), skipping verify - reconciliation already re-checked it - its `file:line` the right side of reconcile's cell when that cell extends the prior cite with ` -> <new path>:<line>` (reconcile's rename form), else the prior cite. A carried finding whose claim names an acceptance criterion or an unrequested change follows this round's Phase 0, which re-derives those findings from the full range: it publishes only as Phase 0's re-derived finding for that criterion or change, noted `_(carried from round <N>)_`, and when Phase 0 drafts none for it (for a criterion: `Met`, `Deferred`, `Untraceable`, gone from the source, or no source resolved; for a change: now requested by the source, or, with no source, the commit log's stated intent) it is not carried. A carried finding annotated `_(unverified: no cite)_` publishes only when the current phases re-derive it. In both cases its reconciliation row stays as reconcile wrote it. A prior label outside this workflow's vocabulary (`[Blocker]`, `[High]`, `[Question]` in a legacy report) stays verbatim in the reconciliation table, which reconcile owns, and maps through Feedback Labels before it is published.

**Depth.** `standard` (default): review diff hunks plus immediate context. `deep`: skip the Phase A fast-path and read each touched file in full. A defect the diff did not introduce, found in that read, is drafted like any other and verification attributes it; a file the diff does not touch is read only to confirm what a finding depends on, and a Phase B-E or sub-scope defect in it is drafted only when the diff newly reaches it; Phase 0 anchors follow `review-change-intent`.

**Phase 0 - Change Intent.** Use skill: `review-change-intent` with the `<base_ref>...<head_ref>` diff and the `<base_ref>..<head_ref>` log, the `--req <path>` file when passed, and the handle's `report_path` when round > 1. Its `## Change Brief` block is carried into the report verbatim, its `Requirement Source` and `Requirement Fit` lines into Summary, and its findings join the assembled set for **Verify findings** (the atomic's requirement-findings section - or its `### No Requirement Findings` marker - is consumed into the set, never rendered). When no requirement source resolves, the Brief still renders and the traceability block and its two Summary lines are omitted. Phase 0 runs before Phase A - acceptance criteria decide what counts as a defect downstream - and no short-circuit skips it.

**Phase A - Risk Snapshot.** Use skill: `review-pr-risk`. Use skill: `review-blast-radius`. State Risk Level (Low/Medium/High/Critical) and Blast Radius (Narrow/Moderate/Wide/Critical) before any line-level finding - only those two Summary lines carry into the report, each the atomic's line value as emitted (a `(contract break: ...)` parenthetical or a two-state `<level> (unmitigated) -> <level> (with ...)` form stays whole). The fast-path test reads the level `review-blast-radius` says to gate on: the unmitigated value unless the `Mitigation:` line's leading tag is `in-place:`. If both are Low/Narrow and the diff touches no architecture-sensitive files (auth, middleware, API contracts, shared libs), produce the Phase 0 outputs (Change Brief, traceability, requirement findings) and Phase B findings only, and skip C-E; requested extra scopes still run.

**Phase B - Correctness and Safety.** Logical correctness, error handling, edge cases, transaction boundaries, unsafe shared-state mutation. Use skill: `ops-resiliency` for fault tolerance. Use skill: `architecture-concurrency` when concurrency is present. Use skill: `backend-transaction-patterns` when the diff opens or changes a transaction scope or a cross-boundary write. **Raise an explicit named finding when logic was added or modified without tests** ([Recommend] minimum; [Must] for critical paths - money movement, auth, data integrity).

**API contract gate (mandatory).** When the diff touches a route/handler registration, a controller, a request/response DTO or params schema, a serializer or response model, or a published spec file, Use skill: `backend-api-guidelines` and Use skill: `ops-backward-compatibility`. Both run - the first judges design, the second judges consumer breakage. Cover: contract compatibility from the consumer's view (removed/renamed/retyped field, tightened constraint, new required request field, changed status code or error shape is breaking until proven otherwise; "no callers" requires a search); response honesty (DTOs never raw ORM entities, RFC 9457 errors, collections paginated); versioning on breaking change; and **OpenAPI drift** - when the project publishes a spec or generated client, changed endpoints, schemas, status codes, and error shapes match the code. Each finding names the impacted consumer and the concrete harm - who breaks and how for a compatibility finding, what internal detail the response now exposes for a design finding - not just the deviated convention. Severity maps to labels: High -> [Must] = unversioned breaking change to an externally consumed contract, or a leaked internal shape (High for any consumer - the leak couples every caller to internals); Medium -> [Recommend] = breaking change to an internal contract without a coordinated-deploy note, inconsistent status code or error envelope, unpaginated unbounded collection; Low = below the reporting bar, write nothing (naming drift, a verb path on a deliberate RPC endpoint) - except an atomic-rated Low that names a consumer harm (a deprecated endpoint with no `Deprecation`/`Sunset` header), which publishes as [Recommend]. When consumption is unknown, treat a published or versioned surface (`/v1/`, OpenAPI-documented) as externally consumed. An `ops-backward-compatibility` row reading `No` or `No (unverified)` is a breaking change for this mapping; with consumers unknown on an unpublished, unversioned surface it is [Recommend], its Fix naming the consumer check that would clear it. Migrations and non-API contract changes still load `ops-backward-compatibility` on their own.

**Test files are reviewed for coverage only.** The only finding a test file raises is a coverage gap - production logic in the diff that no test exercises - anchored to the untested production `file:line` with the case to cover. Test code is not reviewed for style, structure, duplication, naming, or performance.

**Phase C - Architecture Guardrails.** Use skill: `architecture-guardrail` for layer violations, new coupling, circular dependency risk, boundary erosion.

**Phase D - AI-Generated Code Quality.** Use skill: `complexity-review` for its full signal table, speculative abstraction (an interface, factory, or registry with one implementation) included. Speculative generalization outside that table (config for a case nothing exercises) is raised by this workflow directly at `[Recommend]`.

**Phase E - Maintainability.** Use skill: `backend-coding-standards`. Use skill: `ops-observability` for logging/metrics/tracing coverage. Flag naming clarity, mixed responsibilities, large unreviewable chunks, hardcoded URLs/secrets/magic numbers.

**Extra scopes.** If `+perf`, `+sec`, `+obs`, or `+rel` was passed, load the matching `task-code-review-*` skill (`full` = all four) and run it as a subagent, passing the read-once diff/log, the precondition handle, the active depth, and the stack-detect output; each subagent loads `behavioral-principles` as its Step 1, or the spawning prompt inlines its whole Rules section and the unverifiable-change disclosure block. Each sub-scope skill defines its subagent contract in its own Invocation section. Run in parallel; when subagents are unavailable, run each sub-scope skill inline in sequence under the same contract. Sub-scopes return findings and write no report. A returned block maps into this report's shape: its label line and the `file:line` prefix of `Location` form the `### [Label] file:line` heading, `Issue` (or an observability `Missing`) becomes `Issue`, its consequence line (`Attack scenario`, `Impact`, or `Failure Mode` with `Blast Radius`) becomes `Impact`, `Fix` stays, and `System Risk` is written here from the Phase A lines and the lens's stated exposure. A phase atomic's entry maps the same way: its description line (with any `Rule`, `Signal`, `Violation`, `Missing` or `Measured` value; for `architecture-guardrail` its `Issue` line, for `ops-backward-compatibility` its row's `Change` cell) is `Issue`; its `Risk` or `Impact` line is `Impact` - for `ops-backward-compatibility`, its row's `Consumers (evidence)` with the Breaking Changes entry's `Consumers affected`, and where an atomic emits neither (`backend-api-guidelines`, `backend-coding-standards`, `complexity-review`, `review-change-intent`), `Impact` is written here from the description; its `Fix`, `Recommendation`, `Simplification`, or backward-compatibility's `Action Required` with `Migration plan` is `Fix`; where an atomic emits none, `Fix` is written here - for `architecture-guardrail`, its Drift line's action when present, else the change that restores the boundary its Issue line names (the migration the Drift line costs, for a convention-is-the-violation finding); a requirement finding's `Fix` names each missing piece - the outcome, or the part of it, not yet implemented (or the contradicting behaviour to change), and the proof not yet present for it, and an unrequested-scope finding's names the source change that would request it, or the revert; `System Risk` comes from the Phase A lines. An `architecture-guardrail` module-level or cycle anchor (`<dir>/ (<n> files)`, `a -> b -> a`) is drafted at the touched `file:line` that created or extended it, the module or edge named in Issue, so verify can read it. A lens's `out of lens` line is in lens here: draft it as a finding at its `file:line` (label by Feedback Labels, Issue from the line's defect sentence; Impact, System Risk and Fix written here) before verify. A coverage list (security's OWASP rows) confirms the lens ran to completion and is not rendered.

**Cross-phase dedup.** A single defect can surface in more than one phase or lens - the Phase B contract gate and a sub-scope, Phase 0 and Phase B, Phase B and the Phase C guardrail. Merge before **Verify findings**: publish one entry at the strongest intent (Must > Recommend) whose Issue line names each lens that surfaced it and whose System Risk line states the combined exposure in one sentence; preserve `file:line`. A Phase 0 criterion finding and Phase B's missing-tests finding are one defect only when the criterion's sole gap is the missing proof; a criterion with an implementation gap stays its own finding at its own anchor.

**Order of operations.** The phases above only gather. Then, in this order: merge sub-scope findings into the set, dedup across phases and lenses, run **Verify findings**, reconcile against the prior round (round 2+), then write Step 5. The reading order of this step is not its execution order.

**Verify findings.** Use skill: `review-finding-verify` with the assembled findings (including any merged from sub-scopes), the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, taking each row's `file:line` (for the `###` heading; a `no cite` row - its cell a bare file path or a construct name, not `path:line` - publishes at `<path>:1` of that file when the cell is a path, else of the touched file whose hunk raised it, keeping `_(unverified: no cite)_`; never a directory or a bare construct name - this `path:line` form replaces verify's bare-path heading, since reconcile parses only `path:line`), `Label`, and `Annotation` columns. The Summary's `Findings verified:` line is the atomic's Summary form of its tally (`<N> confirmed, <M> reattributed, <U> unverified, <K> dropped`, plus its false-positive/resolved split when emitted), which counts its table only - never restated from memory. Atomic output blocks (risk, resiliency, guardrail, the verify table) inform the review and are never emitted - the report carries only the slots Output Format names.

### Step 5 - Write Report

Use skill: `review-report-writer` with `report_type: review` and every required input: `report_body` (the assembled report per Output Format), `branch` (the handle's `head_short_name`, the checkpoint lookup key), `base_ref`/`head_ref`, `base_sha`/`head_sha` (Step 4), `mode: full` (the writer's only accepted value), `round` (Step 4; plus `prior_head_sha` = `prior_checkpoint.head_sha` when round > 1 - on a same-SHA round it equals `head_sha`, which is expected), `scope` (writer enum value - `core-only` when no scope flag was passed; combined flags join with single spaces in the canonical order `+perf +sec +obs +rel`; all four = `full`), `depth` (`standard` when no depth flag), `stack` (`<language>-<framework>` from `stack-detect`, versions dropped, lowercased, `#` written `sharp` and `+` written `p`, then each run of characters outside `[a-z0-9]` one `-`, leading and trailing `-` stripped, e.g. `elixir-phoenix`, `Vue (Nuxt)` on TypeScript -> `typescript-vue-nuxt`, `C#` / `Unity 6000.3.21f1` -> `csharp-unity`; a segment reported `unknown` dropped; `unknown` when both are), and `pr_url` when the request text carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` (omitted when neither).

## Feedback Labels

| Label        | Meaning                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| [Must]       | Do not merge until this is fixed.                                        |
| [Recommend]  | Fix, or push back with reasoning. Cannot be silently acked.              |

No `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` - if it isn't `[Must]` or `[Recommend]`, don't write it down. A legacy label carried from a prior report maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; `[Suggestion]`, `[Nitpick]`, `[Question]`, `[Medium]`, `[Low]`, and any unrecognised label -> `[Recommend]`; `[Praise]` rows are never carried (reconcile marks them `Obsolete`).

Findings arriving from phase atomics with High/Medium/Low severity map High -> `[Must]`, Medium/Low -> `[Recommend]`; a sub-scope finding, and a phase atomic that emits a label rather than a severity (`architecture-guardrail`, `backend-coding-standards`, `review-change-intent`), keeps the label its entry carries; a phase's own mapping (the Phase B contract gate) governs its findings, and a defect outside that mapping's enum falls back to the general mapping. A maintainability-only High - complexity, structure, naming - carries `[Recommend]`: `[Must]` blocks a merge, and readability alone does not. A finding this workflow raises directly, with no atomic-supplied severity, takes `[Must]` when it risks incorrect behaviour, data loss, or a security hole, and `[Recommend]` otherwise. Where `review-finding-verify` publishes a different `Label` than the mapping assigned, the published label governs - including in Next Steps and in Assessment.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence. The report body prints in chat, then the writer's confirmation line.

When Step 3 dispatched: the stack workflow owns the output. When fallback ran:

**Findings.** Every published finding - Phase 0, Phases B-E, extra scopes, and carried - sits in High-Impact Findings at its label, subject to the fold rule at the end of the template. High-Impact Findings and Next Steps order Must > Recommend, then by `file:line` (path, then line), then in phase order; a multi-line construct cites its first line, and a two-site anchor (`cause:line -> symptom:line`, `caller:line -> callee:line`) publishes at its first site with the second named in Issue. The High-Impact Findings heading renders on every fallback run - alone when nothing publishes, so the next round reconciles an empty section rather than a missing one; Next Steps is omitted when nothing publishes.

**Notes sections.** Architecture Notes summarises `architecture-guardrail`'s block line by line - `Boundary impact` from its Issue lines, `Coupling change` from its Impact lines, `Drift detected` from its Drift lines; Maintainability Notes: `Over-engineering detected` from `complexity-review`'s Issue signals with their measured values, `Simplification opportunities` from its Simplification lines and `backend-coding-standards`' Fix lines, then `(anti-pattern scan not assessed - <reason>)` when its Anti-Patterns section says so. A line with nothing found reads `none`; both sections render on every run whose fast-path did not skip C-E, and are omitted when it did. **Key Takeaways** - 2-4 bullets drawn from the Phase A lines and the published findings' System Risk lines; when nothing publishes, one bullet stating the risk snapshot.

**Next Steps.** One entry per published finding, in the findings' order. `[Implement]` when the fix is local to the change; `[Delegate]` with `[scope: <owner>]` when another owner (dependencies, schema, platform, infra, or another named team) must act. Either tag takes either label, and both keep the `file:line`.

**Assessment** derives from the published findings - verified and carried-forward alike: any `[Must]` -> Request Changes; no `[Must]` but at least one `[Recommend]` -> Discuss; none -> Approve.

**Annotations** sit on the `###` heading line after `file:line`, each its own `_(...)_` group, space-separated: `review-finding-verify`'s Annotation column first (`_(pre-existing)_` / `_(unverified: ...)_` / `_(mechanism: <actual>)_`; its combined `_(pre-existing; newly reachable via ...)_` is written as two groups, `_(pre-existing)_ _(newly reachable via ...)_`), then `_(carried from round <N>)_` for a carried finding. A finding on a file absent from this round's name-status gets `_(pre-existing)_`, written first, unless its annotations have a group opening `pre-existing` or `unverified` (a verify row whose Verdict is `Unverified`, or a carried finding keeping a prior `_(unverified: ...)_`, gets no attribution) - Phase 0 requirement findings included, since the group records the anchored file's provenance for reconcile, not the finding's attribution. Groups are never merged - `review-prior-findings-reconcile` matches `_(pre-existing)_` exactly, and an unannotated finding on an untouched file reads as reverted.

**Scope** displays combined flags capitalized in the canonical order (`+Perf +Sec`); the writer input keeps the lowercase form in the same order.

```markdown
## Summary

- **Assessment:** Approve | Request Changes | Discuss
- **Risk Level:** Low | Medium | High | Critical
- **Blast Radius:** <review-blast-radius's line value as emitted: Narrow | Moderate | Wide | Critical, with any `(contract break: ...)` parenthetical or two-state form>
- **Stack:** <`<Language> / <Framework>` as stack-detect's Stack slot renders it, versions kept as detected (`Python 3.12 / FastAPI 0.115`)> (generic fallback: no stack workflow | generic fallback: `<plugin>` plugin not installed)
- **Scope:** Core | +Perf | +Sec | +Obs | +Rel | Full
- **Depth:** standard | deep
- **Round:** <N>   {round 2+ only}
- **Findings verified:** <from `review-finding-verify`'s tally, in its Summary form: `<N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}`>
- **Requirement Source:** <path or origin> (Specified | Self-attested)   {this line and the next together, only when Phase 0 resolved a source}
- **Requirement Fit:** <n> met, <n> partial, <n> unmet, <n> deferred, <n> untraceable

## Change Brief

**Requested:** <what the change was asked to do; with no source, the atomic's marker as emitted - `(inferred from commits)`, `(inferred from PR body)`, or `(inferred from <path or document title>)`>

**Delivered:** <the mechanism implemented and where>

**Author decisions:** <each choice the request did not imply, with its consequence, excluding choices already raised as findings; `None observed` when nothing remains>

**Watch points:** <what to confirm by hand before reading findings; `None` when there are none>

## Requirement Traceability   {only when Phase 0 resolved a source}

<table from `review-change-intent`>

## Prior Round Reconciliation   {round 2+ only}

<reconcile's output verbatim - table, any note lines, tally>

## High-Impact Findings

### [Must] file:line

- Issue:
- Impact:
- System Risk:
- Fix:

### [Recommend] file:line

[Same structure]

## Architecture Notes   {when the fast-path did not skip C-E}

- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes   {when the fast-path did not skip C-E}

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

- <2-4 bullets from the Phase A lines and the published findings' System Risk lines; one bullet stating the risk snapshot when nothing publishes>

## Next Steps   {when at least one finding publishes}

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] file:line [scope: <owner>] - [one-line action]

_Publish every `[Must]` and every carried finding. Where the remaining `[Recommend]` findings exceed roughly a dozen, publish the highest-impact dozen and close High-Impact Findings with one line naming how many were folded and the files they sit in - never drop a `[Must]` or a carried finding to fit; reconcile reads only `###` headings. A defect-dense diff legitimately yields many `[Must]` findings; that is the correct output, not a reason to demote._
```

## Self-Check

- [ ] Step 1: behavioral-principles loaded
- [ ] Step 2: `stack-detect` ran
- [ ] Step 3: exactly one announcement printed before any output; if matched and available, stack workflow invoked with the invocation forwarded (`full` expanded), Steps 4-5 skipped; otherwise fallback ran
- [ ] Step 4: precondition called with `argument` / `base` / `report_type`; SHAs captured; round decided from `prior_checkpoint` (head, base, scope, depth) before the diff was read; Phase 0 `review-change-intent` ran on the full-range diff with its Change Brief in the report; Phase A risk stated before line findings; the Phase B API contract gate ran when the diff touched a route, controller, DTO, serializer, or spec file; missing tests raised as named finding; Phases C-E ran (`architecture-guardrail`, `complexity-review`, `backend-coding-standards`, `ops-observability`) unless the fast-path skipped them; the set deduped across phases and lenses before `review-finding-verify` ran on it, Dropped rows excluded and verify's `file:line` published; prior findings reconciled on round 2+ with `head_sha` passed, carried findings published; findings ordered Must > Recommend
- [ ] Step 4: subagent loaded behavioral-principles, or the whole Rules section and the disclosure block inlined in the spawning prompt; sub-scopes merged without writing their own reports
- [ ] Step 5: report written via `review-report-writer` with all required inputs, or the `No new commits since prior review.` stop line printed, or a precondition failure surfaced verbatim with no report written (fallback path only)

## Avoid

- State-changing git commands (`fetch`, `checkout`, `merge`)
- Reviewing without reading the full diff first
- Stylistic nits without a project standard
- Blocking on personal preference over correctness, risk, or maintainability
- Treating the fallback as equivalent to a stack workflow
- Emitting labels outside `[Must]` / `[Recommend]` (see Feedback Labels)
