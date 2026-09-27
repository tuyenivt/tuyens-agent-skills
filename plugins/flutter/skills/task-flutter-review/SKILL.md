---
name: task-flutter-review
description: Flutter / Dart code review - rebuild cost, state discipline, disposal leaks, error mapping; spawns perf and security subagents.
agent: flutter-tech-lead
metadata:
  category: mobile
  tags: [flutter, dart, riverpod, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Flutter Code Review

Staff-level Flutter/Dart review umbrella. Covers correctness, architecture, AI quality, maintainability. Coordinates perf / security subagents in parallel.

## When to Use

- Pre-merge review of a Flutter branch or fetched PR ref against its base
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:** pre-implementation design (`task-flutter-implement`), single-error triage (`flutter-engineer`), single-scope reviews (delegate to perf/security).

## Depth

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | Phases A-E |
| `deep` | Architecture changes, post-incident, Principal sign-off | A-E + the touched files' `git log` history (Step 5) |

**Auto-promote to `deep`:** After Phase A, if Risk is High/Critical, set depth to `deep` and record it in the Summary's Depth field as `auto-promoted from standard; Risk: <level>`.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E |
| + Perf | Core + `task-flutter-review-perf` subagent |
| + Sec | Core + `task-flutter-review-security` subagent |
| Full | Core + both in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

This client consumes API contracts rather than designing them: a finding that the client mishandles a contract belongs to Core, and a finding that the contract itself is wrong routes to the owning service.

**Auto-escalation signals:**

- **+Sec:** a token or credential written to `shared_preferences` rather than secure storage, an `http://` URL, a new deep-link or app-link handler, a new platform-channel handler, a new or changed WebView, a certificate-pinning change, a secret in source or in a committed `--dart-define` file, biometric or `local_auth` usage, a new runtime permission request
- **+Perf:** work added anywhere in the widget layer that belongs below it (I/O, sorting, parsing, allocation) - `build` is the common case, not the only one; a non-builder list constructor over a dynamic collection, a widget that lost or should have gained `const`, new image loading or decoding, a new isolate or `compute` call, a new `AnimationController`, a new `Timer.periodic` or polling loop, a large in-memory collection held in state
- **2+ categories -> Full**

There is no `+Ux` scope. Localization is reviewed in Phase B, adaptivity in Phase C, and accessibility at baseline depth in Phase E; all three are designed in `task-flutter-implement`, and there is no dedicated UX lens to escalate to.

## Generated Code

Generated files are build output, not review surface. Exclude from findings: `*.g.dart`, `*.freezed.dart`, `*.gr.dart`, `*.config.dart`, `*.mocks.dart`, and generated localization output. When a generated file changed, review the source that produces it - the annotated model, the route declaration, the ARB file - and cite that source's `file:line`. A change set containing only generated files is a no-op for review purposes; say so rather than manufacturing findings.

## Invocation

`/task-flutter-review [<branch>|pr-<N>] [--base <branch>] [core-only|+perf|+sec|full] [--depth standard|deep]`

Defaults to the current branch vs its base; `pr-<N>` reviews a locally fetched PR ref. The scope flag overrides Step 4's escalation; the depth flag (also accepted bare, as `task-code-review` forwards it) overrides Step 5's promotion - wording such as "quick" is not a flag. `+obs` / `+rel` (forwarded by `task-code-review`'s `full` expansion) have no Flutter lens: drop them and resolve the rest - `+perf +sec` is `Full`. `review-precondition-check` fails fast on a dirty working tree and on a trunk head - review compares committed code only.

**Never modify the working tree.** Git is read-only here (`status`, `diff`, `log`, `show`).

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as subagent.

### Step 2 - Project Shape

Read `pubspec.yaml`. If it is absent or declares no `flutter` dependency, stop - this workflow reviews Flutter projects only.

Record: state management (Riverpod / Bloc / Provider / GetX / none), navigation (go_router / Navigator / auto_route), networking client, persistence store, and the platform target directories present. When Step 4 escalates, also record what the lens's own Step 2 needs: the secure-storage plugin, WebView presence, platform channels, deep-link mechanism, and biometric plugin for +Sec; the image-loading approach for +Perf.

If state management is not Riverpod, record it and note in the Summary: `Detected <X>; Riverpod-specific guidance does not apply.` Review against that library's own conventions rather than flagging it for not being Riverpod.

### Step 3 - Resolve the Change Set

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review`. If it fails fast, surface verbatim and stop. Hold the handle's `prior_checkpoint` (a block, the scalar `legacy`, or absent) for Step 3.5; its `notes` lines go to Coverage Notes.

Fix `branch` = the handle's `head_short_name` (never `HEAD`, never remote-prefixed); `head_ref` passes through unchanged to the diff commands and the writer. Capture `current_head_sha = git rev-parse <head_ref>` and `current_base_sha = git rev-parse <base_ref>` - Step 3.5 needs only these. Once Step 3.5 has not stopped the run, resolve the review set - the paths in `git diff --name-status <base_ref>...<head_ref>`, minus this workflow's generated-file list - and read once and reuse, limited to it: `git diff <base_ref>...<head_ref> -- <paths>` for the change body, the name-status for per-file status (a renamed path adds its old path to `<paths>`), and `git log --oneline <base_ref>..<head_ref>`.

**Skip entirely** when invoked as subagent and parent passed refs + pre-read artifacts.

### Step 3.5 - Decide Round

Every round analyses the full `<base_ref>...<head_ref>` range; round 2+ differs only in reconciling against the prior report (Step 7.5). Apply the first matching row:

| Handle's `prior_checkpoint` | Decision |
| --- | --- |
| absent | `round = 1` |
| `legacy` | `round = 1`; note `Prior report lacks checkpoint metadata - treated as round 1.` (Step 8 overwrites it) |
| `head_sha == current_head_sha`, `base_sha == current_base_sha`, and its `scope` / `depth` cover the invocation's flags (`full` covers every scope, any scope covers `core-only`, `deep` covers `standard`; compare in the writer enum per Step 8) | **No-op.** Print `No new commits on <branch> since prior review at <sha_short>. Prior report unchanged.` (`<sha_short>` = first 7 chars of `current_head_sha`) and stop - no review, no report write |
| any other valid checkpoint | `round = prior.round + 1`, `prior_head_sha = prior.head_sha` |

On round 2+, add a Summary note for each that applies: `Same head as round <prior.round>; re-review for expanded <scope|depth>.` (head unchanged), `Base branch advanced since round <prior.round>.` (`base_sha` differs), `Prior checkpoint unreachable - history rewritten.` (`git merge-base --is-ancestor <prior.head_sha> <current_head_sha>` fails). Scope and depth resolve on the full range exactly as on round 1; nothing is inherited from the checkpoint.

### Step 4 - Scope Auto-Escalation

Scan file list / diff for signals listed under **Scope**, ignoring generated files. Signals come from changed lines, not from unchanged code read for context. Log each as `signal: <category> -> <file:line>`; the log lines go to Coverage Notes. Then:

- Zero signals or `core-only` -> Core
- One category -> add matching scope
- 2+ categories -> Full
- Explicit scope -> respect; still log signals, and when `core-only` suppresses fired signals the Scope line reads `Core (core-only; signals suppressed: <list>)`

**Scope precedence:** user flag > firing signals.

Surface decision in Summary; if escalated, append `auto-escalated from Core; signals: <list>`.

### Phase A - Risk Snapshot

Assess the change set as a whole before any line-level finding. Weigh what the change can break: user-facing surface affected, data or schema touched, auth or payment paths involved, how far a failure propagates from the changed code, and whether a defect would be caught before release. Output a single risk level (Low | Medium | High | Critical) with a one-line rationale, before any findings: Critical = a failure reaches every installed user, loses data, money, or a session on update, or lets an attacker reach another user's data or session; High = a primary flow breaks for some users; Medium = a secondary flow or a recoverable failure; Low = contained and caught before release.

**Low-risk short-circuit:** if Risk is Low, depth was not set to `deep` by flag, **and** the change does not touch architecture-relevant files (app entry point, router configuration, auth or session state, the network client, a widget the diff shows imported by three or more features, the theme, on-device schema), skip Phases C-E. Escalated scopes still run (a Step 4 signal fired for a reason); their merged findings join High-Impact Findings. The streamlined report contains Summary, Prior Round Reconciliation (round 2+), High-Impact Findings (Phase B + any subagent findings), Next Steps, any non-finding lens sections per Step 7, and Coverage Notes with a `Phases C-E skipped: low-risk short-circuit` line - nothing else; Steps 7.5 and 8 still run.

### Step 5 - Re-evaluate Depth After Phase A

Apply the auto-promotion from the Depth table, surfacing it in the Summary **before** Phases B-E.

**Depth precedence:** user flag > this run's auto-promotion.

At `deep`, read `git log` on the touched files for the historical patterns the deep-only checks depend on; without that read, `deep` differs from `standard` only in name.

### Phase B - Flutter Correctness and Safety

Apply atomic skills; each owns canonical patterns:

- Use skill: `dart-language-patterns` - null safety discipline, exhaustive `switch` over sealed types, `late` misuse, async correctness
- Use skill: `flutter-widget-patterns` - `const`, keys, lifecycle, `BuildContext` across async gaps
- Use skill: `flutter-riverpod-patterns` if Step 2 detected Riverpod - provider scope, `ref` usage, disposal, side effects outside `build`. On any other library, load it in fallback mode: its state-management-agnostic subset is the contract for reviewing that library's state holders against its own conventions
- Use skill: `flutter-error-handling` - typed failures, no silent swallows, error-to-UI-state mapping
- Use skill: `flutter-navigation-patterns` if the diff touches routes, guards, deep links, or navigation calls
- Use skill: `flutter-networking` if the diff touches the network layer
- Use skill: `flutter-i18n` if the diff touches ARB files, locale handling, or user-facing copy; it owns every localization defect, a hardcoded user-facing string included, at its own grade
- Use skill: `flutter-local-db-migration` if the diff changes the on-device schema. Check installed-version impact directly: whether an older app version already on a device still works after this change - on-device schema readable by the version the user has, serialized data still deserializable, and server contract expectations unchanged for that older build

**Named checks.** Several overlap the atomics above by design - they are the highest-recurrence Flutter defects and must not be lost in a long atomic report. Emit one finding per defect: when an atomic already raised it, keep that finding; never file the same defect twice.

- **Test coverage finding (named, not buried).** The change adds logic without a matching test -> `[Recommend]`; escalate to `[Must]` when critical path: auth or session handling, money or purchase flows, on-device schema migration, data sync or conflict resolution, permission gating
- **Test files are reviewed for coverage only.** For files that are themselves tests, the only finding to raise is a coverage gap: production logic in the diff that no test exercises. Anchor that finding to the untested production `file:line` and state the case to cover, not the test file. Do not review test code for style, structure, duplication, naming, or performance - a passing test with awkward setup is not a finding. This holds for atomic findings anchored in a test file as well.
- **Disposal completeness.** Every `AnimationController`, `StreamSubscription`, `TextEditingController`, `ScrollController`, `FocusNode`, timer, and platform-channel listener created in a `State` is released in `dispose`. A missing release is a leak that survives navigation
- **`BuildContext` across async gaps.** Any `context` used after an `await` is guarded by a `mounted` check. This is the most common source of "widget disposed" crashes
- **Unawaited futures.** A future that is fired and not awaited either has an explicit reason or is a bug - errors from it bypass the caller's error handling entirely
- **Loading, error, empty, and populated states.** A screen that renders data renders all four, not just the happy path. Inferring emptiness from a null check alone is a finding; a screen with no reachable empty state says so rather than growing one
- **Secrets and endpoints.** No API keys, tokens, or credentials in source or in committed environment files. Client-side secrets are extractable from a shipped binary regardless of obfuscation
- **Untrusted input at the edges.** Deep-link parameters, platform-channel arguments, WebView messages, and notification payloads are attacker-controllable and validated before use
- **On-device schema changes** ship a migration, and old app versions stay installed - the change must be readable by whatever version the user has

### Phase C - Architecture Guardrails

Check the change set for layer violations and coupling drift: a dependency pointing the wrong way across a boundary, a module reaching past its public surface, or a new import that couples two previously independent areas.

**Flutter-specific:**

- **Layering:** presentation -> domain -> data. Widgets render and dispatch; state holders coordinate; repositories own I/O. A widget importing the HTTP client or the database directly is a violation
- **Repository interface in domain, implementation in data.** The UI depends on the abstraction so tests can substitute it
- **Dependency injection through providers, not singletons.** A global mutable instance reached from anywhere defeats override-based testing
- **Feature-module boundaries.** Cross-feature imports go through a shared layer, not sideways into another feature's internals
- **Navigation ownership.** Route decisions belong to the router configuration and guards, not scattered imperative pushes inside widgets
- **Theme and design tokens centralized** rather than per-widget colors and sizes
- **Platform-conditional code isolated** behind an abstraction rather than sprinkled `Platform.isX` branches through the widget tree
- **Anemic state holders (deep depth only):** logic in widgets while state holders only hold fields - flag for extraction. Raise it when the change set itself shows the split, or when `git log` on the touched files shows logic accumulating in the widget layer across commits. One file whose holder merely looks thin is not evidence on its own

**Multi-target changes:** when a change adds or affects a platform target, confirm the platform tier caveats were handled; use skill: `flutter-adaptive-responsive`.

### Phase D - AI-Generated Code Quality

- Check verbosity and over-engineering directly: overly complex methods, deep nesting, oversized files, and over-abstraction
- Use skill: `flutter-overengineering-review` for over-abstracted notifiers, single-implementation repository interfaces, freezed applied to everything, gratuitous providers, defensive null checks after non-nullable types, and custom `InheritedWidget` where a provider suffices. A `StatefulWidget` where `Stateless` suffices is filed once, as `flutter-widget-patterns`' `Widget Type` finding; the overengineering block for it is dropped

**Additional AI smells** (not owned by the atomics above):

- Comment cruft (restating widget names, doc comments on private helpers)

### Phase E - Maintainability

Check naming against the language's own conventions (below), and check that failure paths added by the change leave a log or error record behind rather than failing silently. Use skill: `flutter-accessibility`, running its `Semantic-Label`, `Image-Alternative`, and `Touch-Target` checks; the rest go on its `Not checked:` line as beyond baseline depth.

**Flutter-specific:**

- Naming: `lowerCamelCase` members, `UpperCamelCase` types, `snake_case` file names; no `Util` / `Manager` / `Helper` grab-bag classes
- Magic numbers and strings extracted to named constants or theme tokens
- Widget `build` length: extract past roughly 50 lines or 3 levels of nesting; a deeply nested tree is a composition failure, not a formatting one
- Duplicated widget subtrees: the same tree in 3+ places becomes a shared widget
- Logging hygiene: no `print` in production paths; no PII or tokens in log output
- `flutter analyze` clean; `dart format` applied; `analysis_options.yaml` lints not suppressed inline without a reason

### Step 6 - Delegate Extra Scopes in Parallel

Skip if scope is **Core only**. For each selected scope, spawn one independent subagent **in parallel** with the main thread. Use the **declared subagent for that scope** (`subagent_type` below) - do not infer the agent from the scope name; a security review is not a `flutter-tech-lead` spawn:

| Scope | Skill                          | Subagent (`subagent_type`)     |
| ----- | ------------------------------ | ------------------------------ |
| +Perf | `task-flutter-review-perf`     | `flutter-performance-engineer` |
| +Sec  | `task-flutter-review-security` | `flutter-security-engineer`    |

`Full` = 2 subagents.

**Subagent prompt contract:**

- The resolved `base_ref` / `head_ref` + the pre-read diff and name-status, so no subagent re-resolves the change set. Reading beyond the diff is expected and permitted - perf reads the unchanged file a regression rippled into, security reads manifests, entitlements, build config, and `git log -p` for a removed control
- Depth for +Perf: resolved by the perf Depth table (profiling data supplied, or a perf-critical release), else `standard` - the umbrella's own depth does not carry over. +Sec has no depth axis and always runs every step
- Pre-confirmed stack (Flutter) + state management, navigation, networking, persistence, and platform targets. For +Sec add the fields its own Step 2 needs: secure-storage plugin, WebView presence, platform channels, deep-link mechanism, biometric plugin; for +Perf, the image-loading approach
- The generated-file exclusion list
- Return the Output Format body, minus the frontmatter and confirmation line

**Failure isolation:** if a subagent fails or times out, continue with the rest. Note the missing scope as `Scope incomplete:` in Coverage Notes.

### Step 7 - Synthesize

The merge bullets apply when Step 6 ran; the rules after them apply to every run. Merge subagent findings into single Output Format. Do not append raw reports.

- Every merged finding is a `### [Label] file:line` heading followed by its `- Issue:` line - a lens finding's heading takes the bare `file:line` prefix of its `Location` line and its label per Feedback Labels. `review-prior-findings-reconcile` parses only that shape on the next round
- Deduplicate cross-cutting findings (one entry citing all scopes)
- **Strongest intent wins** when labels differ across subagent reports for the same finding: `Must` > `Recommend`
- Preserve `file:line` citations
- Order by intent, not scope
- Note missing scopes as `Scope incomplete: <scope>` in Coverage Notes
- A lens Summary is not carried: its counts feed the Assessment, perf's Measurement Basis opens a `Performance Lens` section (holding its Device & Measurement Plan when deep), and sec's assessment paragraph opens its MASVS Triage section. In a lens finding, perf's User-Visible Impact or sec's Attack scenario becomes Impact, a sec `pending:` moves from its Severity rationale onto Impact, perf's Evidence, Thread, and Verify and sec's Area follow as one `Lens:` line, System Risk is authored here for every `[Must]`, and perf's `Critical:` prefix is dropped with the other severity words
- The lens's Coverage Notes lines join this report's. An `Outside this lens:` line is reviewed in its owning phase and filed there if it holds, else kept
- Merge Next Steps with `[Implement]` / `[Delegate]` tags; re-sort by intent, keeping a sec `[Delegate]` directly after its `[Implement]`
- Non-finding sections returned by a subagent are not findings, and the merge must not drop them silently. Destinations: security's `MASVS Triage`, `Checked and Correct`, and `Limitations`, plus the `Performance Lens` section, are preserved verbatim as their own sections after Next Steps; each lens's `Recommendations` merge into Key Takeaways as attributed bullets after its 2-4 systemic ones, or, in a report with no Key Takeaways, follow perf's `Performance Lens` section and sec's `MASVS Triage` section; perf's `Checks with no findings` line is a working note like the atomics' `No <category> findings.` lines - it confirms lens coverage for the Self-Check and stays out of the report. "Do not append raw reports" forbids re-listing findings, not carrying these sections

**Lens seams.** Two lenses reporting the same `file:line` are one finding or two depending on the defect, not on the lens count. One defect seen twice - a token cached in an oversized collection, where the storage risk and the memory cost are the same cache - merges into one entry at the strongest intent, naming both consequences in its Impact line. Two defects that happen to share a line - a hardcoded string that is both untranslated and unlabelled for a screen reader - stay separate, because each has its own fix. A hardcoded user-facing string is a `flutter-i18n` finding from Phase B at that skill's grade, never +Sec unless the string is itself a secret.

**Cross-phase same root cause.** When one defect spans multiple phases (a layering violation that also degrades testability), file the finding once under the phase where the root cause sits and reference its `file:line` from `Architecture Notes` or `Maintainability Notes`. Do not double-count.

**Atomic output lines.** Findings keep the atomics' unit: one per defect, further sites of that one defect named as `also <file:line>` after the heading's `file:line` (each site of a repeated rule is its own defect: three hardcoded strings are three findings), and an atomic's `(unconfirmed: depends on <path>)` kept on the Impact line. `No <category> findings.`, `No <rule> findings.`, and `Checks clean:` lines are working notes: they confirm a check ran and stay out of the report. Every atomic's `Not checked:` line, and any in-scope file that could not be read, is carried into Coverage Notes. There is no cap on findings; order carries priority. An atomic block maps into the finding block as: its Category, Rule, Check, Defect, or Risk name opens Issue, followed by its Tier when it has one; its `Area:` line joins Issue; its effect - the Cost line when present, else the Problem, Impact, or `Unnecessary because` line, or the atomic's own Issue line - is Impact (authored from the citation when the block has none); its Fix or Recommendation is Fix; its Code or Call line and `Justified when:` are dropped once the heading holds the `file:line`. Within a label, order by file and line, then the atomic's enum order, then Phase order. A block whose Problem opens with `Pre-existing:` becomes a `Pre-existing:` line unless the change makes it reachable or worse (below), or the atomic reports it under a wider review scope of its own, where it stays a finding. Header lines - `Dart SDK inferred:`, `Dart 3 patterns unavailable:`, `Tiers:`, `Localization not configured` - go to Coverage Notes.

**Pre-existing defects.** A defect on a line the change set does not touch is a finding only when the change makes it reachable or worse - a new caller, a new route into it, a new composition such as a token now stored where backup copies it, or an omission the change needs filled in an untouched file; anchor it at the changed line and name the old line as `also`. Any other defect seen while reading goes on a `Pre-existing: <file:line> - <defect>` line in Coverage Notes and does not affect the Assessment. An atomic that states a wider review scope of its own (the migration strategy as a whole) keeps it.

### Step 7.5 - Reconcile Prior Findings (round 2+ only)

Skip on round 1. Otherwise Use skill: `review-prior-findings-reconcile` with `prior_report` (the body of the file at the handle's `report_path`, frontmatter excluded), the Step 3 diff and name-status, `head_sha = current_head_sha`, and `head_files` (`git ls-tree -r --name-only <current_head_sha>`) when the name-status has a `D` entry.

Its table, note line, and tally render under `## Prior Round Reconciliation`. A `Still open` or `Needs re-check` row this round re-derived publishes once in High-Impact Findings at this round's label. One it did not re-derive is still unresolved: publish it there at its prior label with `_(carried from round <prior.round>)_` as its own group on the heading - reconcile parses only that section, so a row kept out of it is invisible to round 3. Both kinds fold into Next Steps with an `(open since round <prior.round>)` suffix. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` rows are never carried.

### Step 8 - Write Report

Use skill: `review-report-writer` with `report_type: review`, `report_body` (the assembled report), `branch` (Step 3), `base_ref` / `head_ref` as the handle emitted them, `base_sha = current_base_sha`, `head_sha = current_head_sha`, `mode: full`, `round` and (round 2+) `prior_head_sha` from Step 3.5, `scope` (Step 4's resolution in the writer enum: `Core` -> `core-only`, `+Perf` -> `+perf`, `+Sec` -> `+sec`, `Full` -> `full`), `depth` (resolved/auto-promoted), `stack: flutter`, and `pr_url` when the request carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` when present. Print the writer's confirmation line.

## Feedback Labels

| Label        | Meaning                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| [Must]       | Do not merge until this is fixed.                                        |
| [Recommend]  | Fix, or push back with reasoning. Cannot be silently acked.              |

Atomic skills grade findings on their own severity scales. Translate on the way in: `Blocker`, `Critical`, `High`, `Major`, and perf's High Impact -> `[Must]`; `Medium`, `Low`, `Minor`, and perf's Medium and Low Impact -> `[Recommend]`; a finding already labelled `[Must]` or `[Recommend]` keeps it. A perf finding labelled `unverified`, and an accessibility finding whose Impact reads `unverifiable from source`, is `[Recommend]` whatever its impact. Nothing else is carried through - the atomic's severity word does not appear in the report.

**Assessment** follows from the open labels - this round's findings and carried `Still open` / `Needs re-check` rows alike: any `[Must]` -> `Request Changes`; only `[Recommend]` -> `Approve`, and say so plainly; no findings -> `Approve`. `Discuss` replaces `Request Changes` only when the `[Must]` findings would all be answered by one unresolved direction decision - a refactor whose target architecture is itself in question - and the Summary names that decision.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit the report body as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

```markdown
## Summary

- **Assessment:** Approve | Request Changes | Discuss
- **Risk Level:** Low | Medium | High | Critical
- **Stack Detected:** Flutter <constraint> / Dart <constraint>
- **State Management:** Riverpod | Bloc | Provider | GetX | none
- **Navigation:** go_router | Navigator | auto_route | other | none
- **Networking:** <client> | none
- **Persistence:** <store> | none
- **Platform Targets:** <list>
- **Scope:** Core | +Sec | +Perf | Full _(if auto-escalated: `auto-escalated from Core; signals: <list>`; if `core-only` suppressed signals: `core-only; signals suppressed: <list>`)_
- **Depth:** standard | deep _(if auto-promoted: `auto-promoted from standard; Risk: <level>`)_
- **Round:** <N> _(round 2+ only)_
- **Notes:** [one line each, omitted when empty: `Detected <X>; Riverpod-specific guidance does not apply.`, the Step 3.5 round notes, the direction decision behind `Discuss`]

## Prior Round Reconciliation _(round 2+ only)_

[the reconcile skill's table, its note line when it emitted one, and its tally line]

## High-Impact Findings

### [Must] file:line _(a carried finding appends `_(carried from round <N>)_`)_

- Issue: [name the Flutter or Dart pattern]
- Impact: [user-visible or operational]
- System Risk: [how far the failure reaches beyond this file - screens, installed versions, data]
- Lens: [lens findings only - perf Evidence, Thread, Verify; sec Area]
- Fix: [concrete Dart change with code]

### [Recommend] file:line
- Issue, Impact, Lens (lens findings), Fix

## Architecture Notes

_Cross-cutting commentary. Reference findings by file:line._
- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

2-4 bullets on systemic impact, then any lens Recommendations as attributed bullets.

## Next Steps

Each item tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Implement]** [Recommend] old_screen.dart:88 - move the hardcoded paddings to theme tokens
3. **[Delegate]** [Recommend] [scope: server contract] - [one-line action]

_Omit if no actionable findings._

[Preserved lens sections per Step 7]

## Coverage Notes

[One line each: `Scope incomplete:`, the handle's notes, `signal:` lines, atomic header lines, `Not checked:`, `Pre-existing:`, `Outside this lens:`, a short-circuit line]
```

`Stack Detected` carries the `pubspec.yaml` constraints (`environment.flutter`, `environment.sdk`) as written; a missing constraint is `unconfirmed`.

**Omit empty sections.** No Must heading if there are none.

A review with no findings is Summary, the single line `No findings.`, then any preserved lens sections and Coverage Notes - short-circuited or not. A short-circuited review with findings is Summary, High-Impact Findings, Next Steps, preserved lens sections, and Coverage Notes - Phases C-E contribute no sections.

## Rules

- Review whole-change system impact, not file-by-file
- Lead with risk; line-level findings follow
- Apply Dart and Flutter conventions (Effective Dart, Flutter style guidance)
- Actionable feedback with Dart code
- `dart format` applies; don't nitpick style
- Generated files are excluded from findings; review the source instead
- Default Core; auto-escalate; honor `core-only`
- Delegate perf / security depth to subagents

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded (or accepted from parent)
- [ ] Step 2 - `pubspec.yaml` confirms Flutter; state management, navigation, networking, persistence, and platform targets recorded
- [ ] Non-Riverpod state management surfaced rather than flagged as a defect
- [ ] Step 3 - `review-precondition-check` ran with `report_type: review` (or refs received); `branch` = `head_short_name`; both SHAs captured before the diff, name-status, and log were read once
- [ ] Step 3.5 - round decided (1 / prior + 1 / no-op) before any surface was read; no-op exits without writing; round notes in Summary
- [ ] Generated files excluded from findings and from signal scanning
- [ ] Step 4 - scope auto-escalation evaluated; promotion (or `core-only`) recorded
- [ ] Step 5 - depth auto-promoted to `deep` when Risk is High/Critical
- [ ] Risk stated before any finding
- [ ] Phase B: atomic skills applied, conditional ones only where the diff fires them; test coverage, disposal, `BuildContext` across async gaps, unawaited futures, UI states, secrets, untrusted edge input, on-device schema migration checked
- [ ] Phases C-E ran, or the Phase A short-circuit fired and is recorded
- [ ] Phase C: layering, repository abstraction, DI seam, feature boundaries, navigation ownership, theme tokens, platform-conditional isolation, anemic holders (deep), `flutter-adaptive-responsive` on multi-target changes
- [ ] Phase D: complexity and over-engineering checked; `flutter-overengineering-review` applied
- [ ] Phase E: naming, failure-path logging, accessibility baseline checks, magic numbers, build length, duplicated subtrees, logging hygiene, analyze and format
- [ ] Missing tests raised as named finding (not buried)
- [ ] Atomic severities translated to `[Must]` / `[Recommend]`; Assessment follows from the labels
- [ ] Every Must cites system risk
- [ ] Every finding has label + `file:line` + Dart fix
- [ ] Step 6 - extra scopes ran in parallel with the resolved refs, pre-read diff, and detected project shape
- [ ] Step 7 - every finding written as `### [Label] file:line`; subagent findings merged into one intent-ordered list; no raw reports appended
- [ ] Non-finding lens sections routed per Step 7: appendix sections preserved, Recommendations into Key Takeaways, clean-checks line consumed as a working note
- [ ] Same-line findings resolved per Step 7: one defect is one entry at the strongest intent, two defects stay two
- [ ] Coverage Notes carry `Scope incomplete:`, handle notes, `signal:` lines, atomic header lines, `Not checked:`, `Pre-existing:`, and `Outside this lens:` lines
- [ ] Next Steps produced with `[Implement]` / `[Delegate]` tags, ordered by intent
- [ ] Step 7.5 - on round 2+, `review-prior-findings-reconcile` ran with `head_sha`; table under `## Prior Round Reconciliation`; unresolved rows carried into High-Impact Findings and Next Steps; legacy labels mapped
- [ ] Step 8 - report written via `review-report-writer` with every required field (`stack: flutter`, `mode: full`, round, both SHAs, `prior_head_sha` on round 2+); confirmation line printed

## Avoid

- State-changing git from this workflow (fetch/checkout/merge/pull/rebase/stash) - the review reads history only.
- Reviewing without reading the full diff first
- Flagging a project for using Bloc, Provider, or GetX instead of Riverpod
- Reviewing the server's API contract here - it belongs to the owning service
- Generic backend conventions where a Flutter idiom exists ("scope the rebuild", not "optimize the query")
- Nitpicking style where `dart format` applies
- Vague feedback ("this could be better")
- Blocking on personal preference
- Running extra scopes when `core-only` was passed
- Duplicating perf / security depth here
- Sequential extra scopes that could parallelize
- Appending raw subagent reports
