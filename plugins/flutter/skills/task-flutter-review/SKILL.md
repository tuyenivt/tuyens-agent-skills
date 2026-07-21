---
name: task-flutter-review
description: Flutter / Dart code review - rebuild cost, state discipline, disposal leaks, error mapping; spawns perf/security/observability/reliability subagents.
agent: flutter-tech-lead
metadata:
  category: mobile
  tags: [flutter, dart, riverpod, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Flutter Code Review

Staff-level Flutter/Dart review umbrella. Covers correctness, architecture, AI quality, maintainability. Coordinates perf / security / observability / reliability subagents in parallel.

## When to Use

- Pre-merge review on a Flutter PR
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:** pre-implementation design (`task-flutter-implement`), production incident (`/task-oncall-start`), single-error triage (`flutter-engineer`), new-system architecture (`task-design-architecture`), single-scope reviews (delegate to perf/security/observability/reliability).

## Depth

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | Phases A-E |
| `deep` | Architecture PRs, post-incident, Principal sign-off | A-E + historical patterns + cross-PR context |

**Auto-promote to `deep`:** After Phase A, if Blast Radius is Wide/Critical, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E |
| + Perf | Core + `task-flutter-review-perf` subagent |
| + Sec | Core + `task-flutter-review-security` subagent |
| + Obs | Core + `task-flutter-review-observability` subagent |
| + Rel | Core + `task-flutter-review-reliability` subagent |
| Full | Core + all four in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

There is no `+Api` scope. This client consumes API contracts rather than designing them; a finding that the client mishandles a contract belongs to Core or +Rel, and a finding that the contract itself is wrong routes to the owning service or the architecture plugin.

**Auto-escalation signals:**

- **+Sec:** a token or credential written to `shared_preferences` rather than secure storage, an `http://` URL, a new deep-link or app-link handler, a new platform-channel handler, a WebView, a certificate-pinning change, a secret in source or in a committed `--dart-define` file, biometric or `local_auth` usage, a new runtime permission request
- **+Perf:** work added inside `build` (I/O, sorting, parsing, allocation), a non-builder list constructor over a dynamic collection, a widget that lost or should have gained `const`, new image loading or decoding, a new isolate or `compute` call, a new `AnimationController`, a large in-memory collection held in state
- **+Obs:** crash-reporter initialization, analytics events, a new error zone or uncaught-error handler, logging configuration, a change to app entry point or bootstrap
- **+Rel:** a network call without a timeout or cancellation path, a new call site with no offline handling, a screen missing a loading or error state, a background task, retry logic, an optimistic update, cache invalidation
- **2+ categories -> Full**

There is no `+Ux` scope. Adaptivity, accessibility, and localization are reviewed at baseline depth in Phase E, and designed in `task-flutter-implement`; there is no dedicated UX lens to escalate to.

## Generated Code

Generated files are build output, not review surface. Exclude from findings: `*.g.dart`, `*.freezed.dart`, `*.gr.dart`, `*.config.dart`, `*.mocks.dart`, and generated localization output. When a generated file changed, review the source that produces it - the annotated model, the route declaration, the ARB file - and cite that source's `file:line`. A diff containing only generated files is a no-op for review purposes; say so rather than manufacturing findings.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-flutter-review` | Current branch vs base; fails fast on trunk |
| `/task-flutter-review <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-flutter-review pr-<N>` | PR head fetched into local branch `pr-<N>` (user runs fetch) |

Pass `--base <branch>` when the PR was opened against a non-trunk base.

**No checkout required.** Read via ref-qualified diffs; never modify the working tree.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as subagent.

### Step 2 - Stack and Project Shape

Use skill: `stack-detect`. Accept pre-detected stack from parent. If not Flutter, stop and recommend `/task-code-review`.

Record: state management (Riverpod / Bloc / Provider / GetX / none), navigation (go_router / Navigator / auto_route), networking client, persistence store, and the platform target directories present.

If state management is not Riverpod, record it and note in the Summary: `Detected <X>; Riverpod-specific guidance does not apply.` Review against that library's own conventions rather than flagging it for not being Riverpod.

### Step 3 - Resolve Diff

Use skill: `review-precondition-check`. Forward `--base` if passed. If it fails fast, surface verbatim and stop.

The handle may include a `prior_checkpoint` block (a prior `review-<branch>.md` exists). Decision logic is Step 3.5; for now, just hold onto it.

Read once and reuse:

- `git diff <base>...<head>`
- `git diff --name-status <base>...<head>`
- `git log --oneline <base>..<head>`

**Skip entirely** when invoked as subagent and parent passed handle + pre-read artifacts.

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

### Step 4 - Scope Auto-Escalation

Scan file list / diff for signals listed under **Scope**, ignoring generated files. Log each as `signal: <category> -> <file:line>`. Then:

- Zero signals or `core-only` -> Core
- One category -> add matching scope
- 2+ categories -> Full
- Explicit scope -> respect; still log signals

**Scope precedence on round 2+:** user flag > firing signals > inherit from `prior_checkpoint.scope`. If the user passed no flag and the diff (incremental, in incremental mode) fires no signals, inherit the prior round's scope so reviewer coverage does not silently narrow. Surface as `Scope: <inherited> (inherited from round <prior.round>)`.

Surface decision in Summary; if escalated, append `auto-escalated from Core; signals: <list>`.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk
- Use skill: `review-blast-radius` for failure propagation

Output risk level + blast radius before any findings.

**Low-risk short-circuit:** if Risk is Low, Blast Radius is Narrow, **and** the change does not touch architecture-relevant files (app entry point, router configuration, auth or session state, the network client, shared base widgets, the theme, on-device schema), skip Phases C-E. The streamlined report contains Summary, High-Impact Findings (Phase B), and Next Steps only; Step 7 still writes the checkpointed report.

### Step 4.5 - Re-evaluate Depth After Phase A

If Blast Radius is Wide / Critical, set depth to `deep` and surface promotion in Summary **before** Phases B-E.

**Depth precedence on round 2+:** user flag > this round's auto-promotion > inherit `prior_checkpoint.depth`. An incremental diff's blast radius is naturally narrower than the PR's, so auto-promotion cannot re-fire; inheriting prevents a silent deep -> standard demotion. Surface as `Depth: deep (inherited from round <prior.round>)`.

### Phase B - Flutter Correctness and Safety

Apply atomic skills; each owns canonical patterns:

- Use skill: `dart-language-patterns` - null safety discipline, exhaustive `switch` over sealed types, `late` misuse, async correctness
- Use skill: `flutter-widget-patterns` - `const`, keys, lifecycle, `BuildContext` across async gaps
- Use skill: `flutter-riverpod-patterns` - provider scope, `ref` usage, disposal, side effects outside `build`
- Use skill: `flutter-error-handling` - typed failures, no silent swallows, error-to-UI-state mapping
- Use skill: `flutter-navigation-patterns` if the diff touches routes, guards, or deep links
- Use skill: `flutter-networking` if the diff touches the network layer
- Use skill: `flutter-local-db-migration` if the diff changes the on-device schema. Use skill: `ops-backward-compatibility` for installed-version impact

**Additional checks (not owned by atomics):**

- **Test coverage finding (named, not buried).** PR adds logic without a matching test -> `[Recommend]`; escalate to `[Must]` when critical path: auth or session handling, money or purchase flows, on-device schema migration, data sync or conflict resolution, permission gating
- **Test files are reviewed for coverage only.** For files that are themselves tests, the only finding to raise is a coverage gap: production logic in the diff that no test exercises. Anchor that finding to the untested production `file:line` and state the case to cover, not the test file. Do not review test code for style, structure, duplication, naming, or performance - a passing test with awkward setup is not a finding.
- **Disposal completeness.** Every `AnimationController`, `StreamSubscription`, `TextEditingController`, `ScrollController`, `FocusNode`, timer, and platform-channel listener created in a `State` is released in `dispose`. A missing release is a leak that survives navigation
- **`BuildContext` across async gaps.** Any `context` used after an `await` is guarded by a `mounted` check. This is the most common source of "widget disposed" crashes
- **Unawaited futures.** A future that is fired and not awaited either has an explicit reason or is a bug - errors from it bypass the caller's error handling entirely
- **Loading, error, and empty states.** A screen that renders data renders all four cases, not just the happy path. Inferring emptiness from a null check alone is a finding
- **Secrets and endpoints.** No API keys, tokens, or credentials in source or in committed environment files. Client-side secrets are extractable from a shipped binary regardless of obfuscation
- **Untrusted input at the edges.** Deep-link parameters, platform-channel arguments, WebView messages, and notification payloads are attacker-controllable and validated before use
- **On-device schema changes** ship a migration, and old app versions stay installed - the change must be readable by whatever version the user has

### Phase C - Architecture Guardrails

Use skill: `architecture-guardrail` for layer violations and coupling.

**Flutter-specific:**

- **Layering:** presentation -> domain -> data. Widgets render and dispatch; state holders coordinate; repositories own I/O. A widget importing the HTTP client or the database directly is a violation
- **Repository interface in domain, implementation in data.** The UI depends on the abstraction so tests can substitute it
- **Dependency injection through providers, not singletons.** A global mutable instance reached from anywhere defeats override-based testing
- **Feature-module boundaries.** Cross-feature imports go through a shared layer, not sideways into another feature's internals
- **Navigation ownership.** Route decisions belong to the router configuration and guards, not scattered imperative pushes inside widgets
- **Theme and design tokens centralized** rather than per-widget colors and sizes
- **Platform-conditional code isolated** behind an abstraction rather than sprinkled `Platform.isX` branches through the widget tree
- **Anemic state holders (deep depth only):** logic in widgets while notifiers only hold fields - flag for extraction. Do not raise on a single PR alone

**Multi-target PRs:** when a change adds or affects a platform target, confirm the platform tier caveats were handled; use skill: `flutter-adaptive-responsive`.

### Phase D - AI-Generated Code Quality

- Use skill: `complexity-review` for verbosity and over-engineering
- Use skill: `flutter-overengineering-review` for `StatefulWidget` where `Stateless` suffices, over-abstracted notifiers, single-implementation repository interfaces, freezed applied to everything, gratuitous providers, deep widget nesting, defensive null checks after non-nullable types, and custom `InheritedWidget` where a provider suffices

**Additional AI smells** (not owned by the atomics above):

- Test verbosity (a 30-line pump-and-settle setup for one assertion; golden tests for widgets with no visual complexity)
- Comment cruft (restating widget names, doc comments on private helpers)

### Phase E - Maintainability

Use skill: `backend-coding-standards` for cross-language naming only. Use skill: `ops-observability` for cross-cutting logging presence (depth in `task-flutter-review-observability`). Use skill: `flutter-accessibility` for baseline label and target-size presence.

**Flutter-specific:**

- Naming: `lowerCamelCase` members, `UpperCamelCase` types, `snake_case` file names; no `Util` / `Manager` / `Helper` grab-bag classes
- Magic numbers and strings extracted to named constants or theme tokens
- Hardcoded user-facing strings routed through localization
- Widget `build` length: extract past roughly 50 lines or 3 levels of nesting; a deeply nested tree is a composition failure, not a formatting one
- Duplicated widget subtrees: the same tree in 3+ places becomes a shared widget
- Logging hygiene: no `print` in production paths; no PII or tokens in log output
- `flutter analyze` clean; `dart format` applied; `analysis_options.yaml` lints not suppressed inline without a reason

### Step 5 - Delegate Extra Scopes in Parallel

Skip if scope is **Core only**. For each selected scope, spawn one independent subagent **in parallel** with the main thread. Use the **declared subagent for that scope** (`subagent_type` below) - do not infer the agent from the scope name; a reliability review is not a `flutter-tech-lead` spawn:

| Scope | Skill                               | Subagent (`subagent_type`)       |
| ----- | ----------------------------------- | -------------------------------- |
| +Perf | `task-flutter-review-perf`          | `flutter-performance-engineer`   |
| +Sec  | `task-flutter-review-security`      | `flutter-security-engineer`      |
| +Obs  | `task-flutter-review-observability` | `flutter-observability-engineer` |
| +Rel  | `task-flutter-review-reliability`   | `flutter-reliability-engineer`   |

`Full` = 4 subagents.

**Subagent prompt contract:**

- Resolved review target (`base_ref`, `head_ref`) + pre-read diff and commit log (no re-running git)
- Depth level
- Pre-confirmed stack (Flutter) + state management, navigation, networking, persistence, and platform targets
- The generated-file exclusion list
- Return findings in own Output Format

**Failure isolation:** if a subagent fails or times out, continue with the rest. Note the missing scope in Summary.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into single Output Format. Do not append raw reports.

- Deduplicate cross-cutting findings (one entry citing all scopes)
- **Strongest intent wins** when labels differ across subagent reports for the same finding: `Must` > `Recommend`
- Preserve `file:line` citations
- Order by intent, not scope
- Note missing scopes as `Scope incomplete: <scope>`
- Merge Next Steps with `[Implement]` / `[Delegate]` tags; re-sort by intent
- Preserve deep-only sections returned by subagents as their own section after Next Steps - they are not findings; the merge must not drop them

**Lens seams.** One defect can legitimately surface in two lenses: a network call with no timeout is both reliability (the request can hang forever) and perf (the screen holds a spinner and the work stays resident). Keep the state-machine finding under +Rel and the frame-cost finding under +Perf, deduped to one line at the strongest intent. A hardcoded user-facing string is a Phase E maintainability finding, not +Sec, unless the string is itself a secret.

**Cross-phase same root cause.** When one defect spans multiple phases (a layering violation that also degrades testability), file the finding once under the phase where the root cause sits and reference its `file:line` from `Architecture Notes` or `Maintainability Notes`. Do not double-count.

### Step 6.6 - Verify Findings (second pass)

Use skill: `review-finding-verify` with the assembled findings (including any merged back from subagents), the diff already read, and `base_ref` / `head_ref`.

Runs before reconciliation so prior-round matching sees the corrected set. Publish only rows whose Verdict is not `Dropped`, carrying the skill's `Label` column. Carry its tally into Summary as `Findings verified: <N> confirmed, <M> reattributed, <K> dropped`.

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
- `scope` (resolved in Step 4, mapped to the writer's enum: `Core` -> `core-only`, `+Sec` -> `+sec`, `+Perf` -> `+perf`, `+Obs` -> `+obs`, `+Rel` -> `+rel`, `Full` -> `full` - the writer rejects unmapped display values), `depth` (resolved/auto-promoted), `stack = flutter`

Write before ending; print confirmation.

## Feedback Labels

| Label        | Meaning                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| [Must]       | Do not merge until this is fixed.                                        |
| [Recommend]  | Fix, or push back with reasoning. Cannot be silently acked.              |

No `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` - if it isn't `[Must]` or `[Recommend]`, don't write it down.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide | Critical
**Stack Detected:** Flutter <version> / Dart <version>
**State Management:** Riverpod | Bloc | Provider | GetX | none
**Navigation:** go_router | Navigator | auto_route | other
**Persistence:** <store> | none
**Platform Targets:** <list>
**Scope:** Core | +Sec | +Perf | +Obs | +Rel | Full _(if auto-escalated: `auto-escalated from Core; signals: <list>`)_
**Depth:** standard | deep _(if auto-promoted: `auto-promoted from standard; Blast Radius: <level>`)_
**Round:** <N>                                _(include from round 2 onward)_
**Mode:** incremental (since <prior_head_sha_short>) | full _(include from round 2 onward)_
**Findings verified:** <N> confirmed, <M> reattributed, <K> dropped
**Diff Range:** <range_short> (<N> commits, <M> files) _(incremental rounds only)_

## Prior Round Reconciliation _(incremental rounds only; omit otherwise)_

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |
| ...                 | ...       | ...    | ...   |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## High-Impact Findings

### [Must] file:line

- Issue: [name the Flutter or Dart pattern]
- Impact: [user-visible or operational]
- System Risk: [why this is system-level]
- Fix: [concrete Dart change with code]

### [Recommend] file:line
- Issue, Impact, Fix

## Architecture Notes

_Cross-cutting commentary. Reference findings by file:line._
- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

2-4 bullets on systemic impact.

## Next Steps

On incremental rounds, prior-round Still open items are folded in with (open since round <N>) suffix and ordered by intent alongside new findings. Each item tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Implement]** [Recommend] old_screen.dart:88 - controller never disposed (open since round 1)
3. **[Delegate]** [Recommend] [scope: server contract] - [one-line action]

_Omit if no actionable findings._
```

**Omit empty sections.** No Must heading if there are none.

## Rules

- Review whole-change system impact, not file-by-file
- Lead with risk; line-level findings follow
- Apply Dart and Flutter conventions (Effective Dart, Flutter style guidance)
- Actionable feedback with Dart code
- `dart format` applies; don't nitpick style
- Generated files are excluded from findings; review the source instead
- Default Core; auto-escalate; honor `core-only`
- Delegate perf / security / observability / reliability depth to subagents

## Self-Check

- [ ] `behavioral-principles` loaded (or accepted from parent)
- [ ] Stack confirmed; state management, navigation, persistence, and platform targets recorded
- [ ] Non-Riverpod state management surfaced rather than flagged as a defect
- [ ] `review-precondition-check` ran (or handle received); diff/log read once and reused; current_head_sha and current_base_sha captured
- [ ] Step 3.5 - mode decided (full / incremental / no-op); auto-fetch attempted only when prior checkpoint exists; incremental range re-read when mode flipped to incremental; no-op path exits without writing the report
- [ ] Generated files excluded from findings and from signal scanning
- [ ] Scope auto-escalation evaluated; promotion (or `core-only`) recorded
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical
- [ ] Risk + blast radius stated before any finding
- [ ] Phase B: atomic skills applied; test coverage, disposal, `BuildContext` across async gaps, unawaited futures, UI states, secrets, untrusted edge input checked
- [ ] Phase C: layering, repository abstraction, provider-based DI, feature boundaries, navigation ownership
- [ ] Phase D: `complexity-review` + `flutter-overengineering-review` applied
- [ ] Phase E: naming, magic numbers, localization, build length, logging hygiene
- [ ] Missing tests raised as named finding (not buried)
- [ ] Every Must cites system risk
- [ ] Every finding has label + `file:line` + Dart fix
- [ ] Extra scopes ran in parallel with pre-resolved handle and detected project shape
- [ ] Subagent findings merged into one intent-ordered list; no raw reports appended
- [ ] Lens seams (rel/perf overlap) deduped to one line at strongest intent
- [ ] Failed / missing subagent scope noted as `Scope incomplete: <scope>`
- [ ] Step 6.6 - review-finding-verify ran on all assembled findings; Dropped rows excluded; verdict labels applied; tally in Summary
- [ ] Step 6.5 - on incremental rounds, review-prior-findings-reconcile ran; reconciliation table inserted; Still open rows folded into Next Steps with (open since round <N>) suffix
- [ ] Next Steps produced with `[Implement]` / `[Delegate]` tags, ordered by intent
- [ ] Review report written via `review-report-writer` with full checkpoint fields (mode, round, prior_head_sha when round > 1, head_sha, base_sha, scope, depth, stack); confirmation printed

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase). The one allowed exception is `git fetch <remote> <branch>` in Step 3.5a, and only when a valid prior checkpoint exists.
- Auto-fetching on round 1 (no prior checkpoint) - keeps first-run behavior strictly read-only.
- Running incremental analysis against the full-range diff (must re-read scoped to `<prior_head_sha>...<head_sha>`).
- Writing the report on no-op exit (prior `head_sha == current head_sha`) - the file must stay byte-identical.
- Raising findings against `*.g.dart`, `*.freezed.dart`, `*.gr.dart`, `*.config.dart`, `*.mocks.dart`, or generated localization output.
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count.
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels.
- Emitting a "Carry-Over Open Items" section - fold into Next Steps instead.
- Reviewing without reading the full diff and commit log first
- Flagging a project for using Bloc, Provider, or GetX instead of Riverpod
- Reviewing the server's API contract here - it belongs to the owning service or the architecture plugin
- Generic backend conventions where a Flutter idiom exists ("scope the rebuild", not "optimize the query")
- Nitpicking style where `dart format` applies
- Vague feedback ("this could be better")
- Blocking on personal preference
- Running extra scopes when `core-only` was passed
- Duplicating perf / security / observability / reliability depth here
- Sequential extra scopes that could parallelize
- Appending raw subagent reports
