---
name: task-flutter-review-security
description: Flutter mobile security review - secure storage, cert pinning, obfuscation, deep-link and platform-channel input, WebView, biometrics, MASVS.
agent: flutter-security-engineer
metadata:
  category: mobile
  tags: [flutter, dart, security, masvs, secure-storage, certificate-pinning, deep-link, webview, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Flutter Security Review

MASVS-shaped client security review: what the app stores on the device, what it sends and how it trusts the response, what it accepts at its edges (deep links, platform channels, WebView, notifications), how it authenticates locally, what the shipped build exposes, and what it leaks. Findings carry an attack scenario and a concrete Dart or platform-config remediation.

**Client boundary.** The client cannot enforce authorization; it can only avoid leaking and avoid being used as a lever. Server-side authentication, authorization, API security, and cross-service trust boundaries belong to the owning service.

## When to Use

- Flutter security regression review of a change set
- Tokens, credentials, or personal data moving into on-device storage
- A new deep link, app link, custom URL scheme, or platform channel
- WebView introduction or configuration change
- Certificate pinning added, changed, or removed
- Biometric or device-credential authentication
- Pre-release hardening pass (obfuscation, backup flags, permissions, debug artifacts)

**Not for:** perf review (`task-flutter-review-perf`), general review (`task-flutter-review`), server-side auth or API security (the owning service's plugin).

**Depth.** Every step runs on every invocation - security has cliff-edge consequences, and a shipped binary cannot be recalled. Scope by file, not by depth. The frontmatter's `depth` field is therefore always `deep`.

## Severity Rubric

| Severity | Definition |
| -------- | ---------- |
| **Critical** | A live credential, signing key, or privileged API secret committed or compiled into a shipped build (a client-side vendor key is graded by the High row's restriction clause); a session token or credential sent over cleartext; certificate validation disabled on a release path; a deep link or exported component reaching an authenticated action with no session check; a WebView JavaScript channel exposing a privileged operation to arbitrary page content; a platform channel that executes an attacker-influenced path or command; a security control the backend relies on that exists only on the client. Must fix before release; blocks merge. |
| **High** | Session token or credential in `shared_preferences` or a plaintext file; a session token, credential, or regulated or high-harm personal data in an unencrypted local database; sensitive data left backup-eligible; a production endpoint over cleartext `http://`; a biometric gate protecting data with no key binding; session material not cleared on logout; pinning removed with no recorded rationale; a token, credential, or PII in release-build logs; a deep-link or notification parameter used without validation; an extractable vendor key the vendor does not restrict to this app. Must fix before merge. |
| **Medium** | Hardening gap with a mitigating control elsewhere: obfuscation absent on a build that embeds no secrets, an over-broad permission, a missing backup pin where rotation is documented, verbose logging confined to a non-release flavour. A direct identifier or sensitive category collected or sent to a third party without a consent gate, or a native-code dependency added with no provenance record. Should fix in this change or the next. |
| **Low** | Defense in depth, a dependency advisory with no reachable path, resilience hardening with no concrete current attack. |

When two clauses match one defect, take the higher tier and name both in the rationale. A removed pin leaves CA validation in place, so it is High by the pinning clause; a removal that also installs an accept-all callback is Critical by the validation clause.

This rubric governs severity in every run, standalone or subagent. An atomic's own grade - the security atomic's tiers, networking's `Blocker | Major | Minor`, a persistence `VIOLATION` slot - is evidence for a clause, not the tier: name the matching clause, or the nearest one and why the finding sits above or below it.

A defect whose severity turns on a fact the diff cannot settle - a keystore's provenance, whether a release build carries a flag, what a vendor SDK transmits - is filed at the severity it carries **if confirmed**, with `pending: <what to check>` appended to the rationale. Do not discount severity for being unverified from a diff.

**Combined-finding rule.** When two findings *compose* on the same path into a worse threat than either alone, file one finding at the elevated severity:

- Token in `shared_preferences` (High) + backup left enabled (High) = **Critical**: the token is extractable without root through a routine backup (an iOS local backup; on Android, `adb backup` below targetSdk 31 or a device-to-device transfer)
- Deep-link handler that trusts its parameters (High) + a WebView that loads a URL taken from them (High) = **Critical**: attacker-controlled HTML rendered inside the app's own WebView context

Findings that do not compose into a worse threat stay separate at independent severities.

A combined finding anchors `Location:` at the code site that handles the asset (the storage write, the WebView load) and names each other composing site as `also <file:line>` there.

## Generated Code

Generated files are build output, not review surface. Exclude from findings: `*.g.dart`, `*.freezed.dart`, `*.gr.dart`, `*.config.dart`, `*.mocks.dart`, and generated localization output. When a generated file carries the defect, review the source that produces it - the annotated model, the route declaration, the ARB file - and cite that source's `file:line`.

## Invocation

`/task-flutter-review-security [<branch>|pr-<N>] [--base <branch>]`

Defaults to the current branch vs its base; `pr-<N>` reviews a locally fetched PR ref. `review-precondition-check` fails fast on a dirty working tree and on a trunk head - review compares committed code only.

**Never modify the working tree.** Git is read-only here (`status`, `diff`, `log`, `show`).

A request to audit the whole repository is not a mode: the change set is the review subject, and defects outside it go on `Pre-existing:` lines.

When invoked as a subagent (of `task-flutter-review`), the parent supplies the resolved `base_ref` / `head_ref`, the pre-read diff and name-status, the detected project shape, and the generated-file exclusion list: Step 3 is skipped, no git is re-run, and Step 12 returns the Output Format body instead of writing - the parent owns the report.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept the parent's confirmation if invoked as a subagent.

### Step 2 - Stack and Project Shape

Accept the project shape from the parent when invoked as a subagent. Otherwise read `pubspec.yaml`; if it is absent or declares no `flutter` dependency, stop - this workflow reviews Flutter projects only.

Record: secure-storage plugin in use, persistence store, networking client, whether a WebView is present, whether platform channels exist, deep-link mechanism, biometric plugin, and the platform targets present. An absent secure-storage dependency in an app that holds a session is itself a signal. Any field the project files do not establish is written `unconfirmed` in the Summary rather than inferred.

### Step 3 - Resolve the Change Set

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-security`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy`). **Skip entirely** when the parent supplied the refs plus the pre-read diff. Surface any fail-fast verbatim.

**Round gate.** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading any surface: a valid `prior_checkpoint` whose `head_sha` equals the captured `head_sha` -> print `No new commits since prior security review.` and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (Step 12 overwrites the file) -> `round: 1`, no `prior_head_sha`.

Then resolve the review set - the paths in `git diff --name-status <base_ref>...<head_ref>`, minus the generated-file list - and read once and reuse, limited to it: `git diff <base_ref>...<head_ref> -- <paths>` for the change body and the name-status for per-file status; a renamed path adds its old path to `<paths>`. The handle's `notes` go to Coverage Notes.

Reading outside the review set is expected: manifests, entitlements, build config, the lockfile, and prior revisions are security surface whether or not the diff touched them.

### Step 4 - Read the Security Surface

Cite real `file:line`. Open:

- `android/app/src/main/AndroidManifest.xml` - backup attributes, cleartext-traffic flag, debuggable, exported components, intent filters and their link verification, declared permissions
- `ios/Runner/Info.plist` and entitlements - App Transport Security settings, registered URL schemes, associated domains, permission usage strings
- Android network security config, when present - pin sets, cleartext exceptions, extra trust anchors, and any debug-only override
- `pubspec.yaml` and the lockfile - new dependencies, and plugins whose own manifests contribute permissions
- Build and CI config - obfuscation and split-debug-info flags, signing setup, and any secret passed in at build time via compile-time environment definitions
- Every storage call site, the networking client construction and its interceptors, router and deep-link declarations, every platform channel on both the Dart and native side, and WebView configuration

**Permissions arrive from dependencies.** Review the merged manifest, not only the app's own file.

**Removed controls are findings.** When the diff drops pinning, a validation step, a backup restriction, or an auth gate on a route, read the prior revision (`git log -p`) - the blame trail is authoritative. A removal is evidence of insecure design even when each individual line looks small, and the stated rationale ("we will add it back", "it broke the test proxy") is not a compensating control.

### Step 5 - MASVS Triage

**Triage pass**, not a findings list. One verdict per group, recording whether the diff touches that group's surface - not whether it produced a finding. `yes` means reviewed and clean or reviewed with findings; the Findings sections carry the outcome. Steps 6-11 produce the findings.

`Verdict: {yes | no signal in diff}`

| Group | Flutter signal | Owning step |
| ----- | -------------- | ----------- |
| MASVS-STORAGE | Token, credential, or PII in `shared_preferences`, a plaintext file, or an unencrypted local DB; a secret in source, an asset, a committed environment file, or a compile-time define; backup-eligible sensitive data; tokens or PII in logs or on the clipboard | 6, 10 (backup), 11 (logs, clipboard) |
| MASVS-CRYPTO | Hardcoded key or IV, non-secure random for tokens, hand-rolled or legacy algorithm | 6 |
| MASVS-NETWORK | Cleartext endpoint or flag, disabled certificate validation, pinning added / changed / removed | 7 |
| MASVS-PLATFORM | Deep-link, app-link, or intent handler, exported component, WebView and its JavaScript channels, new permission, app-switcher snapshot | 8, 9 (snapshot), 10 (permission) |
| MASVS-AUTH | Biometric or device-credential gate, token lifetime handling on device, logout teardown | 9, 6 (teardown) |
| MASVS-CODE | Platform-channel, notification-payload, clipboard, and imported-file input; unvetted dependency | 8 (input), 10 (dependencies) |
| MASVS-RESILIENCE | Obfuscation config, debuggable flag, root or tamper-detection claims | 10 |
| MASVS-PRIVACY | More personal data collected or sent than the feature needs; consent gating; third-party SDK collection | 11 |

The groups follow `flutter-security-patterns`' Category-to-Area mapping, and where the two disagree the atomic's mapping wins; a finding the atomic has no Category for (weak randomness, ECB, hand-rolled crypto, dependency provenance) takes the row it falls under. Load that skill at Step 6; it applies through Step 11, and every finding carries the MASVS Area it maps to.

### Step 6 - On-Device Storage, Secrets, and Crypto

Use skill: `flutter-security-patterns` for the canonical storage and crypto patterns. Use skill: `flutter-data-persistence` for store selection.

- [ ] **Tokens, refresh tokens, credentials, and keys go to platform-backed secure storage** (Keychain / Keystore); personal records go to the store `flutter-data-persistence`'s sensitivity rule selects (SQLCipher when regulated or high-harm). `shared_preferences` is an unencrypted file (a property list on iOS, XML or DataStore on Android) - readable on a rooted or jailbroken device and extractable through a backup
- [ ] **Secure-storage options set deliberately, not defaulted:** iOS keychain accessibility (the device-only variants stop an item migrating to a new device through a backup) and the Android options for the plugin version in the lockfile (on `flutter_secure_storage` 9.x, `encryptedSharedPreferences` is opt-in; 10.x deprecates it and applies its own default cipher)
- [ ] **A local database holding sensitive records is encrypted** at rest, or holds nothing worth encrypting
- [ ] **Logout clears everything:** secure storage entries, in-memory caches, cached responses containing user data, and any local database rows scoped to the session
- [ ] **No secret in source, `pubspec.yaml`, a bundled asset, or a committed environment file.** Assets ship unencrypted inside the APK or IPA, and compile-time environment values are embedded in the binary. Any of these is a *published* secret: the fix is to move the capability behind the server and rotate the key, never to hide it better
- [ ] **Cryptographically secure randomness** for tokens, nonces, and IVs - never the default pseudo-random generator
- [ ] **No hand-rolled crypto, no hardcoded key or IV, no ECB mode**; key material lives in the platform keystore where the platform provides one

**Bad / good.**

```dart
// Bad - session token in a plaintext preferences file
await prefs.setString('access_token', token);

// Good - platform keystore / keychain, with accessibility chosen explicitly
await secureStorage.write(
  key: 'access_token',
  value: token,
  iOptions: const IOSOptions(accessibility: KeychainAccessibility.first_unlock_this_device),
);
```

### Step 7 - Network and Transport

Use skill: `flutter-networking`.

- [ ] **Every endpoint is `https://`.** Cleartext is disabled at the platform level, and any exception is scoped to a named development host and absent from the release configuration
- [ ] **Certificate validation is never disabled.** A callback that accepts any bad certificate, or a global HTTP override that does the same, ships an app that trusts an interception proxy as readily as the real server. A test-only override not compiled out of release is Critical
- [ ] **Pinning, where used, pins something that survives renewal** - the issuing CA's certificate or SPKI, or a leaf SPKI plus pins for the next keys - never only the current leaf certificate, carries at least one backup pin, and has a documented rotation plan
- [ ] **Pinning is an availability risk as much as a control.** An expired pin bricks every installed copy with no server-side remedy, so a remote kill switch or forced-update path is part of this review, not a follow-up
- [ ] **Pinning coverage stated:** a pin installed on the Dart HTTP client does not cover WebView traffic or a native SDK's own connections
- [ ] **Auth material travels in headers, never in a path or query string** - URLs reach logs, proxies, and referrers
- [ ] **Server responses are untrusted input:** parsed defensively, size-bounded, never used to pick code paths by name, never injected as HTML into a WebView unescaped

### Step 8 - Untrusted Input at the App Edges

Use skill: `flutter-navigation-patterns` for deep-link routing. Use skill: `flutter-platform-channels` when the diff adds or changes a channel.

Everything crossing into the process from outside is attacker-controllable: deep-link and custom-scheme URLs, notification payloads, platform-channel arguments, WebView messages, and clipboard contents.

**Deep links and exported components:**

- [ ] Link parameters are validated and typed before use; an identifier taken from a link never drives a fetch or mutation that the server does not independently authorize - the client cannot check ownership
- [ ] A link never navigates past an auth gate: the router's redirect or guard evaluates session state for link-initiated navigation exactly as for in-app navigation
- [ ] A URL taken from a link, push payload, or server field is never handed to a WebView or an external launcher without an allowlist check - that is an open redirect that renders attacker content in the app's context
- [ ] Custom URL schemes are not an authentication channel: any installed app can register the same scheme. Only verified app links and universal links carry an ownership claim
- [ ] Android components are exported only when they must be; an exported activity with an intent filter is reachable by every app on the device

**Platform channels:**

- [ ] Arguments are validated on the **native** side, not only in Dart - the Dart caller is not a trust boundary once the process is under attacker influence
- [ ] The exposed method is the narrowest one that satisfies the feature. A generic "read this path" or "run this command" method hands the app's full privilege to whatever can reach it
- [ ] The channel does not return secrets to Dart that the native side could have used directly

**WebView:**

- [ ] JavaScript is enabled only where the content requires it
- [ ] A JavaScript channel is a bridge from page content into the app. Treat every message as hostile, allowlist the operations it can trigger, and never expose storage access, credentials, or navigation past an auth gate through one
- [ ] Navigation is constrained by a delegate that allowlists destinations rather than following whatever the page requests
- [ ] No token or session material is injected into page JavaScript or appended to a WebView URL
- [ ] File and content access are left disabled unless the feature requires them

### Step 9 - Local Authentication and Session Handling

- [ ] **A local biometric result is a UI gate, not proof to anyone.** Where the protected asset is data, bind the prompt to key release - a keystore key that requires user authentication, or a keychain item whose access control is tied to the current biometric set - so a bypassed prompt yields nothing
- [ ] **A change to enrolled biometrics invalidates the binding** rather than silently continuing to unlock
- [ ] **Device-credential fallback is a recorded decision**, not an unnoticed default
- [ ] **Token lifetime, refresh, and revocation are the server's** - the client's job is to store them safely, send them over TLS, and drop them completely on logout
- [ ] **Sensitive screens account for the app-switcher snapshot and screenshots** where the data warrants it

### Step 10 - Build Hardening and Dependency Hygiene

Use skill: `flutter-build-release` for flavor, signing, obfuscation, and `--dart-define` mechanics.

- [ ] **Release builds obfuscate with split debug info, and the symbol files are archived** for later crash symbolication. Obfuscation renames Dart symbols; it does not encrypt assets, hide strings, or make an embedded secret safe. Any finding whose proposed fix is "we obfuscate" is not fixed
- [ ] **No debug-only code in release:** debuggable off, debug endpoints and developer feature flags stripped, development trust anchors and proxy overrides absent from release configuration
- [ ] **Backup behaviour reviewed** - platform defaults will copy app data off the device. Sensitive files are excluded from backup, and Android backup rules are explicit rather than inherited
- [ ] **Permissions are minimal, requested at point of use with a rationale**, and any permission arriving through a plugin's manifest is either justified or removed
- [ ] **New dependencies reviewed for provenance and maintenance** - a plugin with native code inherits the app's full privilege on the device
- [ ] **Root, jailbreak, or tamper detection, where present, is framed as defense in depth only.** It is bypassable, and it is never the control that protects the asset

### Step 11 - Privacy and Leakage

- [ ] **No token, credential, PII, or full request and response body in log output**; release builds do not keep verbose logging enabled
- [ ] **Crash reports and analytics are scrubbed** - breadcrumbs, custom keys, HTTP interceptor logs, and error messages routinely carry the very token that caused the failure
- [ ] **Collection is consent-gated where required**, and the collected set matches the app's published privacy declaration
- [ ] **Sensitive values are not written to the clipboard** or left in a cache shared with other apps

### Step 12 - Write Report

Standalone only. A subagent run writes no file and prints no confirmation line: it returns the Output Format body - Summary, MASVS Triage, Findings, Checked and Correct, Recommendations, Limitations, Next Steps, and Coverage Notes - to the parent, which merges it and owns the report. The triage table and Limitations travel with the findings; the parent cannot recompute them. The checkpoint write is standalone-only.

**Atomic output lines.** Findings keep the atomics' unit: one per defect, further sites of that one defect named as `also <file:line>` on the Location line (each site of a repeated rule is its own defect), and an atomic's `(unconfirmed: depends on <path>)` becomes `pending: <what it depends on>` in the Severity rationale. `No security findings.` and the other atomics' `No <category> findings.` and `No <rule> findings.` lines are working notes: they confirm a check ran and stay out of the report. An absent attribute anchors to the element that should carry it; an absent file is cited as `<path> (missing)`. Every atomic's `Not checked:` line, and any in-scope file that could not be read, is carried into Limitations. There is no cap on findings; order carries priority.

**Pre-existing defects.** A defect on a line the change set does not touch is a finding only when the change makes it reachable or worse - a new caller, a new route into it, a new composition such as a token now stored where backup copies it, or an omission the change needs filled in an untouched file; anchor it at the changed line and name the old line as `also`. Any other defect seen while reading goes on a `Pre-existing: <file:line> - <defect>` line in Coverage Notes and does not affect the Overall Posture count. A defect outside this lens - a correctness or compile error, a cost the perf lens owns - goes on an `Outside this lens: <file:line> - <defect>` line there; in a subagent run the parent routes it to its owning phase. A pre-existing defect that composes into a combined finding keeps the combined-finding anchor.

**Round 2+ reconcile (standalone).** Project the prior report (the file at the handle's `report_path`, every severity section) into reconcile's parse shape: one `## High-Impact Findings` section with one `### [Label] file:line` heading per finding - the label its severity section maps to (Critical / High -> `[Must]`, Medium / Low -> `[Recommend]`), the bare `file:line` prefix of its `Location` line, and a trailing `_(carried from round <N>)_` group re-emitted on the heading as its own group - followed by its `Issue` line written as `Issue:`. Then Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files` when the name-status has a `D` entry. Its table, note line, and tally render as `## Prior Round Reconciliation`. A `Still open` or `Needs re-check` row this run did not re-derive publishes in its prior severity section with `_(carried from round <N>)_` (`<N>` = the prior report's `round`) appended to its `Location` line; one this run re-derived publishes once, at this run's severity. Both get a Next Steps entry. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table; `[Praise]` rows are never carried.

Use skill: `review-report-writer` with `report_type: review-security`, `report_body` (the assembled body), `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` from the Step 3 round gate, `mode: full`, `round` and `prior_head_sha` from the round gate, `scope: +sec`, `depth: deep` (every step runs on every invocation), `stack: flutter`, and `pr_url` when the request carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` when present. Print the writer's confirmation line.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit the report body as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

```markdown
## Flutter Security Review Summary

- **Stack Detected:** Flutter <constraint> / Dart <constraint>
- **Secure Storage:** <plugin> | none detected | unconfirmed
- **Persistence:** <store> | none | unconfirmed
- **Local Auth:** <biometric plugin> | none | unconfirmed
- **Networking:** <client> | pinning: yes / no / changed in this diff | unconfirmed
- **App Edges:** deep links | platform channels | WebView | notifications | none in diff _(deep-link mechanism: <package> | none | unconfirmed)_
- **Platform Targets:** <list> | unconfirmed
- **Round:** <N> _(round 2+ standalone runs only)_
- **Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment naming the client-specific risks: a token in plaintext preferences, a disabled certificate check, a deep link reaching an authed screen, a secret compiled into the binary.]

## MASVS Triage

| Group            | Verdict                 |
| ---------------- | ----------------------- |
| MASVS-STORAGE    | yes / no signal in diff |
| MASVS-CRYPTO     | ...                     |
| MASVS-NETWORK    | ...                     |
| MASVS-PLATFORM   | ...                     |
| MASVS-AUTH       | ...                     |
| MASVS-CODE       | ...                     |
| MASVS-RESILIENCE | ...                     |
| MASVS-PRIVACY    | ...                     |

## Findings

### Critical

- **Location:** [file:line, further sites as `also <file:line>`; `<path> (missing)` for an absent file] _(a carried finding appends `_(carried from round <N>)_`)_
- **Area:** [MASVS Area - from the security atomic's block, else the triage row the finding falls under; Platform when the atomic gives one, including `unconfirmed: <target>`]
- **Issue:** [the defect in Flutter terms: "the profile route reads `userId` from the deep link and loads that profile with no session check, so any link recipient opens any account's screen"]
- **Attack scenario:** [pick one and label: (a) a concrete exploit path; (b) "Regression risk: the next refactor silently drops this check"; (c) "Exposure-dependent: turns on whether the release build ships the debug trust anchor". Do not invent an exploit when the realistic threat is regression or exposure.]
- **Severity rationale:** [tier] per rubric - [which clause applies]
- **Fix:** [concrete Dart or platform-config remediation with code]

### High / Medium / Low

[Same structure]

_Within a tier, order by file and line. Omit severity sections with no findings. If all are omitted: "No security issues found."_

## Prior Round Reconciliation _(round 2+ standalone runs only)_

[table, note line, and tally from `review-prior-findings-reconcile`]

## Checked and Correct

[Security-relevant changes in the diff that are correctly handled and must not be re-raised: a usage-description string added alongside the capability it covers, a debug-scoped trust anchor absent from release, a `--dart-define` carrying a client-visible value rather than a secret. One line each, with why it is correct. Omit when the diff has none.]

## Recommendations

[Prioritized hardening not tied to a single finding]

## Limitations

[The checks this run could not perform - merged manifest, release build configuration, native handler source - and every atomic's `Not checked:` line. Omit when all were performed.]

## Next Steps

Each tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend.
Severity maps to intent: Critical / High -> [Must]; Medium / Low -> [Recommend].
Any finding the client cannot close alone also produces a `[Delegate]` entry naming what the backend or another owner must enforce, placed right after that finding's `[Implement]` entry and citing the same `file:line`. For findings from `flutter-security-patterns`, its non-`none` **Server-side dependency** field states this directly; for every other finding, judge it from the finding - an authorization, collection, or retention concern the server owns delegates the same way. A `[Delegate]` entry carries its finding's intent.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Must] file:line [scope: server contract] - [one-line action]

_Omit if no issues found._

## Coverage Notes

[One line each, omitted when empty: the handle's notes (standalone runs), `Pre-existing:`, `Outside this lens:`]
```

`Stack Detected` carries the `pubspec.yaml` constraints (`environment.flutter`, `environment.sdk`) as written; a missing constraint is `unconfirmed`.

## Rules

- Validate at the app's edges: deep-link and scheme URLs, notification payloads, platform-channel arguments, WebView messages, and every server response
- A secret that reached a shipped build is rotated, not hidden - obfuscation is not a remediation for an embedded credential
- Never disable certificate validation to unblock a test environment; point the environment at a trusted certificate instead
- Never widen the app's edge (a new exported component, scheme, channel method, or JavaScript channel) without recording why it is safe
- Authorization is the server's; a client-side check is a UX affordance and is never cited as the control

## Self-Check

**Verifiable from the diff (must check):**

- [ ] `behavioral-principles` loaded (or accepted from parent)
- [ ] Stack confirmed; storage plugin, persistence store, networking client, WebView presence, channels, deep-link mechanism, biometric plugin, and platform targets recorded
- [ ] `review-precondition-check` ran with `report_type: review-security` (or parent-supplied refs and diff reused); round decided before any surface was read (or the stop line printed); diff and name-status read once and reused
- [ ] Security surface read directly (manifest, plist and entitlements, network config, lockfile, build config, storage and network call sites, routes, channels, WebView); prior revision consulted wherever a control was removed
- [ ] MASVS triage produced one verdict per group; triage verdicts not duplicated as standalone findings
- [ ] Storage, secrets, and crypto checked: secure storage for session material, storage options set explicitly, local DB encryption, logout teardown, no secret in source or assets, secure randomness, no hand-rolled crypto, hardcoded key, or ECB
- [ ] Transport checked: TLS everywhere, no disabled validation, pinning shape plus backup pin, rotation path, and kill switch, pinning coverage stated, auth material in headers, server responses treated as untrusted
- [ ] Every app edge in the diff triaged as untrusted input: deep links, exported components, platform channels, WebView
- [ ] Local authentication reviewed when in diff: key binding rather than a UI gate, enrollment-change invalidation, device-credential fallback recorded, token lifetime handled on device, app-switcher and screenshot exposure
- [ ] Build hardening reviewed: obfuscation with archived symbols, debug artifacts absent, backup behaviour, permission minimality including plugin-contributed permissions, dependency provenance, root or tamper detection framed as defense in depth
- [ ] Leakage reviewed: logs, crash reports, analytics, consent gating, clipboard
- [ ] Generated files excluded from findings; the producing source cited instead
- [ ] Severity rubric applied consistently; combined-finding rule applied where two defects compose on one path
- [ ] Diff-unverifiable defects filed at their confirmed-severity with `pending:` rather than discounted
- [ ] Correctly handled security-relevant changes recorded under Checked and Correct
- [ ] Every finding carries an attack scenario, a regression-risk rationale, or an exposure-dependent framing
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Must > Recommend (omitted only when no issues)
- [ ] On round 2+ standalone runs, prior findings projected and reconciled, unresolved rows carried; report written via `review-report-writer` with every required field (`stack: flutter`, `mode: full`, `depth: deep`, round, both SHAs), confirmation line printed (standalone only; subagent runs return the Output Format body to the parent)

**Requires repo or device access:**

- [ ] Merged manifest inspected for permissions contributed by plugins
- [ ] Release build configuration confirmed (obfuscation flags, signing, absence of debug overrides) rather than inferred from the diff

## Avoid

- State-changing git from this workflow (fetch/checkout/merge/pull/rebase/stash) - the review reads history only
- Writing a report when invoked as a subagent - the parent owns it
- Reporting without an attack scenario ("input not validated" vs "any app can register this scheme and drive the victim's client to this authed screen")
- Skipping a MASVS group - state `no signal in diff` rather than leaving the row blank
- Raising findings against `*.g.dart`, `*.freezed.dart`, `*.gr.dart`, `*.config.dart`, `*.mocks.dart`, or generated localization output
- Accepting obfuscation, a compile-time environment define, or an asset file as a way to ship a secret safely
- Accepting a client-side role or ownership check as an authorization control
- Treating a local biometric result as proof of anything beyond "someone unlocked the prompt"
- Recommending pinning without a backup pin, a rotation plan, and a recovery path for pinned-out installs
- Leaving a permissive certificate callback or global HTTP override reachable from a release build
- Reviewing the server's authentication or API contract here - it belongs to the owning service
- Filing a hardcoded user-facing string as a security finding - that is a localization (`flutter-i18n`) finding, unless the string is itself a secret
- Conflating security with perf or general review
