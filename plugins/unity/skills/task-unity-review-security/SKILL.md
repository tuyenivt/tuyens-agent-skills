---
name: task-unity-review-security
description: Unity mobile game security review - rewarded-ad grant integrity, IAP receipt validation, save tampering, secrets in builds, deep links, store privacy.
agent: unity-security-engineer
metadata:
  category: mobile
  tags: [unity, csharp, security, iap, rewarded-ads, tampering, secrets, il2cpp, privacy, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Unity Security Review

Client security review for a shipped game binary: what the client is trusted to assert, what a player can edit in a save or in memory, what secrets the build carries, what the app accepts at its edges (deep links, remote config, downloaded content), what third-party SDKs collect, and what the store requires. Findings carry a concrete attack, who is harmed, and a remediation that names its control type.

**The client is hostile.** A shipped build runs on a device the player controls: memory is editable, files are readable, traffic is interceptable, and the binary is decompilable. Any value the client asserts can be forged. Anything of real value - an IAP entitlement, a rewarded-ad grant, a leaderboard score - is granted by a server that verified it, not by the client that claims it. The server's own authentication and API design belong to the owning service's team.

## When to Use

- A Unity change set adding IAP, rewarded ads, or any client-granted reward
- Player progress, currency, or entitlements moving into a save file
- A third-party SDK integrated or upgraded (ads, analytics, attribution, mediation)
- Deep links, remote config, or downloaded content becoming an input
- Secrets, API keys, or build configuration changing
- Pre-submission privacy and store-compliance pass (ATT, privacy manifests, GDPR consent, children's audience)

**Not for:** perf review (`task-unity-review-perf`), general review (`task-unity-review`), server-side auth or API security (the owning service's team).

**Depth.** This workflow always runs at `deep` - security has cliff-edge consequences, and a shipped binary cannot be recalled. Every step runs on every invocation; scope by file, not by depth. `deep` is the value written to the report's `depth` field, and a depth a parent passes is ignored.

## Severity Rubric

The bands extend `unity-security-patterns`' bands with this workflow's edge and SDK cases and its merge consequence. This workflow reads source, so the atomic's inferred-evidence cap applies only to a finding whose deciding lines were not read; its `Severity rationale` then says what was not seen.

| Severity | Definition |
| -------- | ---------- |
| **Critical** | Revenue, or an entitlement of real value, granted on an unverified client claim (a rewarded-ad reward granted in the client's ad-closed callback, an IAP item granted without server validation, a grant or paid unlock driven by a deep-link parameter); a shipped secret - a credential that authorizes server-side actions, compiled into the build or committed; a privacy control absent where legally required (an SDK collecting before consent is resolved in a consent region, personalized ads or device identifiers in a children's-audience game). Blocks merge - except that a Critical whose Control type is `accepted exposure` blocks merge only through its client-side remainders. |
| **High** | Tamperable state that affects other players or monetization (leaderboard-bound currency, a score submitted without server validation); a deep-link, remote-config, or server-response value driving navigation, an unlock of content not sold for money, or a price with no validation; a runtime-issued credential in player-readable storage (`PlayerPrefs`, a plain file) - per-device rather than global, which separates it from a shipped secret. Must fix before merge. |
| **Medium** | Tamperable single-player state that gates progress; an SDK data-flow gap with consent correctly present (collection beyond the declaration); a store-submission requirement missing (a privacy manifest, the ATT usage string) - the store rejects the build before it reaches players. Should fix in this change or the next. |
| **Low** | A cosmetic-only grant or tampering (the player cheats themselves); cost-raising hardening with no current exploit path - obfuscation posture, an integrity check on non-valuable state, a defensive validation on an input that is already constrained. |

A value is **of real value** when it is sold for money, buys what money buys, or affects other players; currency that is also sold through IAP is of real value even when it only buys cosmetics. A key is a **secret** when holding it lets a caller act server-side beyond what every shipped client already does - read other players' data, write config or content, issue grants, call a paid API, sign a release. A key every shipped client must send for the SDK to work is publishable, whatever the vendor calls it (an analytics game key, an ad unit id, an SDK's event-signing key), and so is the integrity-only HMAC key of a keyed save hash. A key whose role the review cannot determine is filed at High, its Fix opening with the check that settles it (the vendor console's permissions for that key).

**Combined-finding rule.** When two defects on the same path compose into a worse threat than either alone, file one finding at the elevated severity:

- Plaintext editable save (Medium alone, when it gates progress) + purchased entitlements recorded only in it = **Critical**: remove-ads and unlocks are granted by editing a file
- Unvalidated remote-config price (High) + a soft-currency purchase that charges that price (Medium alone) = **Critical**: a compromised or misconfigured config becomes a free purchase with no floor
- A runtime-issued per-device credential in player-readable storage (High) + a destructive endpoint it can call = **Critical**

The rows are the rule; where one matches, merge at the elevated severity even though each half is also exploitable alone. File separately when the two defects sit on **different paths**, or when one is merely the reach of the other (an exported activity is the reach of the handler it exposes, not a second defect). Where one finding already carries the pair's full impact, say which finding owns it rather than filing the composition twice.

## Server Presence

Record which applies, because it decides what "server authority" can mean:

| Server | Meaning | Effect |
| --- | --- | --- |
| Server-side code the team controls | A first-party service, or a managed backend where the team runs code: Firebase Cloud Functions, PlayFab CloudScript, Unity Gaming Services Cloud Code | Server-authority findings are actionable. Control type names the owning team; standalone runs also raise a `[Delegate]` Next Step |
| A backend with no team-run code | A hosted data store or config service used as configured, where nothing the team writes runs server-side | Classify per grant. A backend feature that verifies server-side with no team code - a receipt-redeem API (PlayFab or Unity Gaming Services Economy), Firestore or Realtime Database Security Rules - makes that grant `server authority (<backend feature>)`. A grant no backend feature can verify is `accepted exposure (backend runs no team code)`, its client clamp or validation `client control`, and access control on the console a `[Delegate]` Next Step |
| None | Client-only game | The No-Server rule below |

A backend that exists but does not handle a given grant counts as none for that grant only when the team cannot add the handler there; where it can (team-run code, a redeem API), the fix is server authority on that backend.

**No-Server rule.** When Step 2 finds no server, the Summary's assessment opens with `unity-security-patterns`' line, verbatim: `No server or managed backend: server-authority defects below are accepted exposures.` Every server-authority finding's server half is then recorded as accepted exposure with its reason, rather than emitted as a fix the project cannot implement. The reviewable controls are tamper *detection* (a keyed hash over the save, with its limit stated: the key ships in the build and is extractable), input validation, secret absence, SDK data flow, and store compliance. Never recommend server validation as an action item to a project with no server - name it as the boundary the exposure sits behind.

**Accepted exposure does not lower severity and does not delete the finding.** Severity states what is at risk; Control type states what can be done about it. A Critical finding whose server half is unimplementable stays Critical, and every client-side remainder it carries - deleting a grant with no precondition, restoring a removed integrity check, ordering a durable write before an acknowledgement - is still an action item and still appears in Next Steps. Only the server half produces no Next Step.

## Excluded Surfaces

Not review surface: `Library/`, `Temp/`, `obj/`, `Build/`, `Logs/`, generated `*.csproj` and `*.sln`, and third-party SDK *source* - the managed and native code a vendor ships, under `Assets/Plugins/` or in the vendor folders an SDK's `.unitypackage` installs (`Assets/GoogleMobileAds/`, `Assets/MaxSdk/`, `Assets/ExternalDependencyManager/`, and the like). Project-authored files at those paths stay review surface: `Assets/Plugins/Android/**/AndroidManifest.xml`, `*.androidlib` manifests, and any `PrivacyInfo.xcprivacy`. **The SDK's own source is excluded; its integration, configuration, version, and initialization order are not** - an ads SDK initialized in `Awake` before the consent answer exists is a finding cited at the calling code. Do not raise a finding *on* a `.meta` file; cite the asset it describes. In subagent mode this list governs this lens even where the parent's reviewable-surface table keeps SDK sources in scope.

**Assets are review surface.** A ScriptableObject `.asset` holding an API key, a scene wiring a reward handler directly to a wallet, or a prefab carrying a debug cheat component is a legitimate finding cited at the asset path.

**Test files are review surface for credentials only.** A real token, key, or endpoint credential in a test fixture is committed and therefore disclosed - it is a finding at its shipped-secret severity even though the test assembly never reaches the player build, and the remediation is rotation, not deletion. Raise nothing else against test code.

## Invocation

`/task-unity-review-security [<branch>|pr-<N>] [--base <branch>]`

Defaults to the current branch vs its base; `pr-<N>` reviews a locally fetched PR ref. `review-precondition-check` fails fast on a dirty working tree and on a trunk head - review compares committed code only; this workflow's own `review-security-*.md` checkpoint at the repository root does not count as dirt.

**Never modify the working tree.** Read via `git diff`, `git show`, and `git log -p` only. A file's content at the head is read with `git show <head_ref>:<path>` whenever the head is not the checked-out branch.

**Citations, every mode.** A `file:line` is the line number inside that file at the head - read it from the file (`git show <head_ref>:<path>`), or count from the `+<start>` of the hunk header `@@ -a,b +<start>,c @@` - never a line number of the diff output or of a prompt.

When invoked as a subagent (of `task-unity-review`), the parent supplies the resolved `base_ref` / `head_ref`, the pre-read diff and name-status, the detected project shape, and its reviewable-surface table: Step 3 is skipped and the diff is not re-read, but `git show <head_ref>:<path>` and `git log -p` stay available for the Step 4 reads and removed controls. Step 10 returns findings instead of writing - the parent owns the report.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles` - as a subagent too, unless the spawning prompt inlined its Rules.

### Step 2 - Stack and Project Shape

Accept the engine and project shape from the parent when invoked as a subagent. Otherwise read `ProjectSettings/ProjectVersion.txt`; if it is absent, stop - this workflow reviews Unity projects only.

**Engine floor is Unity 6.3 LTS (`6000.3.x`).** Compare numerically. Below the floor, state the mismatch and stop; at or above it (`6000.3.x`, `6000.4.x`, and later) proceed. If `ProjectVersion.txt` is unreadable, say so and proceed with version-independent findings only.

Then, after Step 3's round gate has passed and in every invocation mode, record the security shape from the head (a parent supplies scripting backend, persistence, and platform targets; it does not gather the rest): scripting backend (`ProjectSettings/ProjectSettings.asset`, or `unknown`), **server presence and kind** (Server Presence table), **the declared audience** (general 13+ / children under 13 / mixed, from the store listing, README, or a families or Kids Category declaration), monetization surfaces present (IAP, rewarded ads, mediation), save store and format, third-party SDKs and their versions (`Packages/manifest.json`, `Packages/packages-lock.json`, vendor folders, and the External Dependency Manager `*Dependencies.xml` files that pin native SDK versions), deep-link and remote-config mechanisms, and platform targets.

**Audience is recorded before any finding is graded.** A children's-audience declaration changes what is legal: COPPA requires verifiable parental consent before personal information is collected, Google Play Families forbids personalized ads and transmitting device identifiers from children, and Apple's Kids Category bars third-party advertising and analytics outside narrow exceptions. A finding graded before the audience is known is graded wrong.

An absent server in a game that sells anything is itself the headline signal - record it and drive the No-Server rule from it.

### Step 3 - Resolve the Change Set

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-security`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy`). Surface any fail-fast verbatim and stop.

**Round gate.** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading any surface: a valid `prior_checkpoint` whose `head_sha` and `base_sha` both equal the captured ones -> print `No new commits since prior security review.` and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (Step 10 overwrites the file) -> `round: 1`, no `prior_head_sha`.

Then read once and reuse:

- `git diff <base_ref>...<head_ref>` for the change body
- `git diff --name-status <base_ref>...<head_ref>` for the file list

The changed paths outside Excluded Surfaces are the review surface; Step 4's reads beyond them follow the out-of-diff rule there. A binary asset git reports as `Binary files differ` is not diffed - its `.meta` carries the reviewable settings.

**Skip entirely** when invoked as a subagent and the parent passed the refs plus the pre-read diff.

**No-op exit.** When the change set touches only excluded surfaces, write no report: state `No reviewable change in this change set - <reason>` and stop.

A `.meta`-only change set is not automatically a no-op: read the changes, and proceed when a setting delta is present, cited at the asset. Importer-version churn alone is a no-op; a changed `guid:` line is not - it breaks every reference to the asset, and is listed under `## Reviewed, Not Filed` as `-> task-unity-review`.

### Step 4 - Read the Security Surface

Cite real `file:line` or asset path. Open:

- Every purchase, reward, and entitlement grant path - the IAP callback, the ad-closed callback, and whatever writes the wallet or inventory
- Save write and read call sites, plus the save DTO and any integrity check
- SDK presence and versions (Step 2's sources); the SDK initialization call sites and their ordering relative to consent
- Deep-link and custom-scheme handling, remote-config fetch and use sites, and any downloaded-content path
- `ProjectSettings/` for scripting backend, stripping level, and anything that reads like a credential
- The Android manifest under `Assets/Plugins/Android` - permissions, exported components, registered schemes - and, for iOS, the Player Settings usage descriptions any `[PostProcessBuild]` / `IPostprocessBuildWithReport` script that edits `Info.plist` (the ATT usage string), and the app's `PrivacyInfo.xcprivacy` (placed under `Assets/Plugins` or added by such a script)
- CI configuration for signing credentials and store API keys
- ScriptableObject `.asset` files added or changed, for embedded keys and endpoints

**Removed controls are findings.** When the diff drops a validation call, an integrity check, a consent gate, or a server round-trip, read the prior revision (`git log -p`) - the blame trail is authoritative. A removal is evidence of insecure design even when each line looks small, and the stated rationale ("we will add it back", "it broke the test build") is not a compensating control.

**Out-of-diff defects.** A defect read in a file the change set does not touch is filed only when it is Critical or High, or when this change makes it newly reachable; its Location carries `_(pre-existing)_`, plus `_(newly reachable via <file:line>)_` as its own group when that is the filing reason. Only a path absent from the name-status takes the annotation - an unchanged line inside a changed file takes none. A lesser one is a line in `## Reviewed, Not Filed` with the reason. Either way it is never dropped.

### Step 5 - Asset Triage

**Triage pass**, not a findings list. One verdict per row (`yes` / `no signal in diff`). Steps 6-9 produce the findings.

| Asset | Real risk | Owning step |
| ----- | --------- | ----------- |
| IAP entitlement | Fake purchase, replayed transaction | 6 |
| Rewarded-ad grant | Client claims a reward it never watched | 6 |
| Currency / progress | Save-file edit, memory edit | 7 |
| Leaderboard score | Forged submission | 6 |
| API keys and secrets | Extraction from the binary | 7 |
| Untrusted external input | Crafted input driving a grant or navigation - deep link, remote config, downloaded content, or a server response | 8 |
| SDK data collection | Collection before consent, or beyond the declaration | 9 |
| Store privacy posture | ATT, privacy manifests, GDPR, children's audience | 9 |

The right control depends on who is harmed. A single-player 2048 high score does not need what a rewarded-ad grant needs - say so rather than filing both at the same tier.

### Step 6 - Client Authority: Ads, IAP, and Scores

Use skill: `unity-security-patterns` for the canonical grant-boundary patterns.

**The rewarded-ad grant is the casual-game exploit.** The client tells itself the ad finished, and the reward lands.

- [ ] **A rewarded-ad reward is granted by the network's server-side verification callback**, not by the client's ad-closed event. The client event is a UI hint that triggers a refresh of state it does not compute. A client-side timer or duration check is not verification. The server verifies the callback's signature, refuses a repeated callback `transaction_id`, and credits the user id bound in the verification's custom data
- [ ] **IAP entitlements are granted on a transaction the server verified with the store** - the App Store Server API or the signed transaction (StoreKit 2, which Unity IAP 5.x uses), the Google Play Developer API purchase token. Local validation raises the bar against casual tampering, but the validating code and its keys ship inside the binary the attacker controls
- [ ] **Each transaction id is recorded server-side and a duplicate grant is refused** - a replayed receipt or purchase token grants nothing twice
- [ ] **A transaction is not acknowledged or consumed until the entitlement is durably recorded** - acknowledging first is how a player pays and receives nothing. The purchase stays pending until the server records the grant: in Unity IAP 4.x `ProcessPurchase` returns `Pending` and `ConfirmPendingPurchase` runs after; in 5.x the order arrives in `OnPurchasePending` and `ConfirmPurchase` runs after. Read the installed version from `Packages/manifest.json`
- [ ] **Leaderboard submissions are validated or simulated server-side** where placement has value
- [ ] **No grant path is reachable from a debug, cheat, or test component left in a shipped scene or prefab**

```csharp
// Bad - the reward is granted by client code the attacker controls
void OnAdClosed() { wallet.Add(500); }

// Good - the network calls the server; the client refreshes state it does not compute
void OnAdClosed() => StartCoroutine(RefreshWalletFromServer());
```

**IAP and ads SDK APIs move faster than the engine.** Name the flow and the integrity boundary; check the package's current surface rather than asserting a call signature.

### Step 7 - Save Tampering and Secrets in the Build

Use skill: `unity-save-persistence` when the finding touches save format or storage path. Use skill: `unity-build-release` for scripting backend, stripping, and signing mechanics.

- [ ] **Monetized or multiplayer-visible state is server-authoritative**, not save-resident. A save is a file on a device the player owns
- [ ] **Where a server is absent, an integrity check is a detection control with its limit stated** - a keyed hash over the payload catches a hand-edited value, and the key ships in the build and is extractable. Never present it as protection
- [ ] **`PlayerPrefs` holds nothing security-relevant.** It is a registry entry, a plist, or a SharedPreferences file - readable through device backups (iOS), a debuggable build, or root, and editable on desktop with none of them - and never a store for tokens, entitlements, or currency
- [ ] **No secret in code, in a ScriptableObject, in `Resources`, or in a bundled asset.** Any of these is a *published* secret (a runtime-issued token in `PlayerPrefs` is the High per-device case above, not this one): the fix is to move the capability behind a server and rotate the credential, never to hide it better. Publishable identifiers and integrity-only keys are not secrets (Severity Rubric)
- [ ] **IL2CPP is cost, not protection.** It makes decompilation meaningfully harder than Mono's near-source IL; strings, resources, and asset bundles stay readable and IL2CPP metadata tooling exists. A finding whose proposed fix is "we use IL2CPP" is not fixed
- [ ] **Tokens that must exist on-device sit behind a platform keychain plugin**, with the rooted-device caveat stated; the durable fix is a short-lived server-issued token, not a long-lived embedded key
- [ ] **Signing credentials, keystores, and store API keys live in CI secrets** - never in the repo, never in `ProjectSettings`

### Step 8 - Untrusted External Input

Everything crossing into the process from outside is attacker-controllable: deep-link and custom-scheme parameters, remote-config values, downloaded content and Addressables catalogs, notification payloads, clipboard contents, and server responses.

- [ ] **Deep-link parameters are parsed defensively and validated against what exists and what the player has unlocked** before they drive navigation. A link navigates; it never grants or discounts - a reward or price arrives through the server
- [ ] **A custom URL scheme is not an authentication channel** - any installed app can register the same scheme. Only verified App Links and Universal Links carry an ownership claim
- [ ] **Remote-config values driving currency, pricing, unlocks, or difficulty are validated on arrival; one outside its range is rejected for the bundled default**, not clamped to the bound. A compromised or misconfigured config otherwise becomes an economy bug with no floor
- [ ] **Downloaded content and remote catalogs are treated as untrusted** - served over TLS, size-bounded, and never used to select code paths by name
- [ ] **Server responses are parsed defensively and validated field by field before they touch live state** - including a first-party server's. Every endpoint is TLS with no cleartext exception, but the transport terminates on a device the player controls: a proxy CA the player installs (iOS) or injects through root or a repackaged APK (Android) makes the response attacker-authored. Certificate pinning raises that cost and is `cost-raising only`; it never substitutes for validation. A response driving progress, currency, or unlocks with no validation is High, the same as an unvalidated deep link
- [ ] **Conflict resolution does not key on the device clock.** Last-write-wins on a client-supplied timestamp is a write primitive: the player sets the date forward and their save wins permanently. The server assigns the timestamp, or the client sends a monotonic counter the server compares
- [ ] **Android components are exported only when they must be**; a new permission arriving through an SDK's manifest is justified or removed

```csharp
// Bad - a crafted link loads any level, including locked or paid ones
var level = int.Parse(deepLinkParams["level"]);
LoadLevel(level);

// Good - validated against what exists and what the player unlocked
if (deepLinkParams.TryGetValue("level", out var raw) && int.TryParse(raw, out var level)
    && progression.Exists(level) && progression.IsUnlocked(level)) LoadLevel(level);
```

### Step 9 - SDK Data Flow and Store Compliance

- [ ] **Each ads, analytics, attribution, and mediation SDK has a known collection profile** - what it collects, whether it needs consent first, and whether it initializes before the consent answer exists. An SDK that phones home in `Awake` before the dialog is answered is a compliance defect regardless of the dialog's correctness
- [ ] **Consent gates SDK initialization, not just reporting.** Order is startup -> consent resolved -> SDK init -> events. Withdrawing consent stops collection by the SDKs already started
- [ ] **iOS ATT is requested before any tracking as Apple defines it** - IDFA access, or sharing user or device data with third parties for ads or measurement - with the usage string present; fingerprinting is never allowed
- [ ] **Apple privacy manifests are present** - the app's `PrivacyInfo.xcprivacy` declares its required-reason API use and data collection, and each SDK that Apple lists ships its own; an SDK upgrade without its manifest is a submission rejection
- [ ] **Consent is gated in the EEA, UK, and Switzerland**, through a Google-certified IAB TCF consent tool where Google ad products are used, and the decision is revocable and honored. The digital-consent age is 13 to 16 by EU member state, so a `general (13+)` game relying on consent there can still need parental authorization
- [ ] **A children's-audience game follows its audience rules** (Step 2): no personalized ads, no device identifiers, and only ads SDKs from the Families Self-Certified Ads SDK program under Google Play Families, no third-party ads or analytics outside the exceptions under Apple's Kids Category, verifiable parental consent under COPPA - decided before integration, not after. The ads posture and the analytics posture are answered by the same audience declaration
- [ ] **The store data-collection declaration matches what the app actually sends** - the App Store privacy label and the Google Play Data safety form. A field added in code without updating the declaration is a compliance defect, not only a privacy one
- [ ] **No PII in what leaves the device** - names, emails, precise location, raw device identifiers, or user-authored text. Player identifiers are opaque and app-scoped

This step owns whether the collection is legal and whether the SDK respects the gate.

### Step 10 - Write Report

**Subagent return.** A subagent run returns `## Asset Triage`, `## Findings`, `## Reviewed, Not Filed`, `## Limitations`, and `## Lens Context` (two bullets, `- **Server:** {Summary value}` and `- **Audience:** {Summary value}`) - nothing else. No frontmatter, no Summary block, no Recommendations, no Next Steps: the parent owns those and derives the `[Delegate]` entries from each finding's Control type. Where the no-server boundary applies, each affected finding's Control type reads `accepted exposure (no server or managed backend)`.

**Round 2+ reconcile (standalone).** Project the prior report (the body of the file at the handle's `report_path`, frontmatter excluded, every severity section) into reconcile's parse shape: one `## High-Impact Findings` section with one `### [Label] file:line` heading per finding - the label its severity section maps to (Critical / High -> `[Must]`, Medium / Low -> `[Recommend]`), the first `file:line` or asset path of its `Location` line, then its `_(pre-existing)_` and `_(carried from round <N>)_` groups, each re-emitted on the heading as its own group, never merged - followed by its `Issue` line written as `Issue:`. Then Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files` when the name-status has a `D` entry. Its table, note line, and tally render as `## Prior Round Reconciliation`. A `Still open` or `Needs re-check` row this run did not re-derive publishes in its prior severity section with `_(carried from round <N>)_` (`<N>` = the prior report's `round`) on its `Location` line, replacing any earlier carried group and keeping its `_(pre-existing)_` group; one this run re-derived publishes once, at this run's severity. Both get a Next Steps entry. `[Praise]` rows are never carried.

Use skill: `review-report-writer` with `report_type: review-security`, `report_body` (the assembled body), `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` from the Step 3 round gate, `mode: full`, `round` and (round 2+) `prior_head_sha` from the round gate, `scope: +sec`, `depth: deep`, `stack: unity`, and `pr_url` when the request carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` when present. Emit the report body in chat, then the writer's confirmation line.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit the report body as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

A Summary field whose observed state matches no listed value is written as the closest value followed by ` - <what was actually observed>`. Every field except `Round` is always present; a surface the diff leaves untouched is still recorded, with ` - untouched in diff`.

```markdown
## Unity Security Review Summary

- **Stack Detected:** Unity <internal version> (Unity <marketing name>) / {IL2CPP | Mono | unknown}
- **Server:** {team-run server code at <owner> | backend with no team-run code (<vendor>) | none - client-only game}
- **Audience:** {general (13+) | children (under 13) | mixed}
- **Monetization:** {<each present, comma-separated> | none}
- **Save Store:** {<path and format>, integrity check at file:line | <path and format>, no integrity check | none}
- **SDKs in Diff:** {<name and version, each> | none}
- **App Edges:** {<each present: deep links, remote config, downloaded content> | none}
- **Platform Targets:** {list}
- **Round:** {N}   {round 2+ only}
- **Overall Posture:** {Clean | Issues Found - <Critical/High/Medium/Low counts>}

{2-3 sentence assessment naming the client-specific risks; when Server is none it opens with the No-Server line verbatim}

## Asset Triage

| Asset                      | Verdict                         |
| -------------------------- | ------------------------------- |
| IAP entitlement            | {yes \| no signal in diff}      |
| Rewarded-ad grant          | {yes \| no signal in diff}      |
| Currency / progress        | {yes \| no signal in diff}      |
| Leaderboard score          | {yes \| no signal in diff}      |
| API keys and secrets       | {yes \| no signal in diff}      |
| Untrusted external input   | {yes \| no signal in diff}      |
| SDK data collection        | {yes \| no signal in diff}      |
| Store privacy posture      | {yes \| no signal in diff}      |

## Findings

### Critical

- **Location:** {file:line | asset path | several paths, the one where the fix starts first} {_(pre-existing)_} {_(newly reachable via <file:line>)_} {_(carried from round <N>)_}   {each group only when it applies}
- **Issue:** {the defect in Unity terms: "`OnAdClosed` adds 500 coins directly, so any player who calls the handler grants themselves the reward without watching"}
- **Attack:** {what an attacker does, concretely: "edits `coins` in `save.json` and relaunches"; for a compliance defect, `none - compliance: <who enforces it and how>`}
- **Impact:** {who is harmed and how - revenue loss, economy break, other players' rankings, data exposure, store rejection}
- **Regression of:** {the commit that added the control this diff removes, and what it was added to fix}   {only when the diff removes a control}
- **Severity rationale:** {tier} per rubric - {which clause applies}
- **Control type:** {server authority (<owning team or backend feature>) | client control | cost-raising only | accepted exposure (<reason>) | <primary> + <secondary>}
- **Fix:** {concrete C#, asset, or configuration change with code}

### High

{same structure}

### Medium

{same structure}

### Low

{same structure}

## Prior Round Reconciliation   {round 2+ standalone runs only}

{table, note line, and tally from `review-prior-findings-reconcile`}

## Reviewed, Not Filed

- {path - why it produced no finding, or the out-of-diff defect below the filing bar}

## Limitations

- {access-dependent check this run could not perform - the merged Android manifest, the release build configuration - and what that leaves unverified}

## Recommendations

- {prioritized hardening not tied to a single finding}

## Next Steps

1. **[Implement]** [Must] {file:line} - {one-line action}
2. **[Delegate]** [Must] [scope: {server contract | console access | store declaration | credential rotation}] - {what the owner must do}
```

Rules for the template:

- `client control` is a client-side change that fully closes the defect (consent order, input validation, SDK configuration); `cost-raising only` raises an attacker's cost without closing it; rotating a shipped credential is `server authority` (the issuing service revokes it). A finding whose fixes span two writes `<primary> + <secondary>` and its Fix says which fix is which.
- On a multi-path Location, `_(pre-existing)_` follows each path it applies to.
- The Summary's Round line adds `; base advanced since round <N-1>` when `base_sha` differs from the prior checkpoint's.
- Within a severity section, root cause leads - the finding whose fix removes or narrows the others. Omit a severity section with no findings; if all are omitted, write `No security issues found.` under `## Findings`.
- `## Reviewed, Not Filed` is omitted only when every reviewable path produced a finding: without it a near-clean report cannot be told apart from one where the file was never opened. `## Limitations` is omitted when every check ran. `## Next Steps` is omitted when there are no findings.
- Next Steps are ordered Must > Recommend; within a band, root cause before the symptoms it produces, an `[Implement]` before the `[Delegate]` that depends on it, then the wider player impact, then the order the findings appear. Severity maps to intent: Critical / High -> `[Must]`; Medium / Low -> `[Recommend]`. Every Next Steps entry carries exactly one label, `[Must]` or `[Recommend]`.
- A finding also produces a `[Delegate]` entry whenever the control that closes it sits outside this codebase - `server authority` naming what the backend must enforce, a console's access control, or a store declaration (Data safety form, privacy label, Families or Kids Category setting) to update. Where Control type is `accepted exposure`, the server half produces no Next Step, and every client-side remainder the finding names still produces one.

## Rules

- Validate at the app's edges: deep-link parameters, remote-config values, downloaded content, notification payloads, and every server response
- A secret that reached a shipped build is rotated, not hidden - IL2CPP, stripping, and obfuscation are cost, never remediation for an embedded credential
- Never widen the app's edge (a new scheme, exported component, or config key driving a grant) without recording why it is safe
- Authority over anything of value is the server's; a client-side check is a UX affordance and is never cited as the control
- State which control type each fix is, so the reader is never told a hash is protection

## Self-Check

**Verifiable from the diff (must check):**

- [ ] Step 1: `behavioral-principles` loaded, or its Rules inlined in the spawning prompt
- [ ] Step 2: engine version checked numerically against the `6000.3.x` floor before the round gate; after it, scripting backend, **server presence and kind**, **declared audience**, monetization surfaces, save store, SDKs and versions, edges, and platform targets recorded from the head before any finding is graded
- [ ] Step 3: `review-precondition-check` ran with `report_type: review-security` (or parent-supplied refs and diff reused); round decided on `head_sha` and `base_sha` before any surface was read (or the stop line printed); diff and name-status read once and reused; no-op exit taken on an excluded-only change set
- [ ] Step 4: security surface read directly (grant paths, save call sites, SDK init order, edges, `ProjectSettings/`, Android manifest, iOS post-process scripts, CI, changed `.asset` files); prior revision consulted wherever a control was removed; out-of-diff defects filed with `_(pre-existing)_` or listed under Reviewed, Not Filed
- [ ] Step 5: asset triage produced one verdict per row; triage verdicts not duplicated as standalone findings
- [ ] Step 6: `unity-security-patterns` consulted; ad-grant boundary, IAP server verification, transaction-id replay refusal, acknowledgement ordering, leaderboard authority, and shipped debug grant paths checked
- [ ] Step 7: `unity-save-persistence` and `unity-build-release` consulted where relevant; save authority, integrity-check limits stated, `PlayerPrefs` misuse, no shipped secret, IL2CPP framed as cost, CI credential placement
- [ ] Step 8: every edge in the diff triaged as untrusted input - deep links, remote config (rejected for the default, not clamped), downloaded content, server responses, transport and pinning, device-clock conflict resolution, exported components and permissions
- [ ] Step 9: SDK collection profile, consent gating init and withdrawal, ATT, privacy manifests, consent regions and TCF, children's-audience rules, store declaration match, and PII checked
- [ ] Step 10: standalone: on round 2+, prior findings projected with their annotation groups and reconciled, unresolved rows carried; report written via `review-report-writer` with every required field (`report_type`, `branch`, both refs, both SHAs, `mode: full`, `round`, `prior_head_sha` on round 2+, `scope: +sec`, `depth: deep`, `stack: unity`); confirmation line printed; subagent: the five sections returned, citations are head-file lines, no file written
- [ ] Excluded surfaces (including vendor SDK folders) raised no findings; SDK *integration, version, and init order* still reviewed; `.meta` defects cited at the asset; scenes, prefabs, and `.asset` files treated as reviewable
- [ ] Severity rubric (extending `unity-security-patterns`' bands) applied consistently, with the secret test for keys; combined-finding rule applied where two defects compose on one path
- [ ] Every finding carries a concrete attack (or the compliance form), an impact, and a Control type; a removed control also carries `Regression of:`
- [ ] No-Server rule honored where it applies: the verbatim line in the Summary (standalone) or `accepted exposure (no server or managed backend)` in Control type (subagent), server halves recorded as accepted exposure, no unimplementable action items
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Must > Recommend (omitted only when no issues)

**Requires repo or device access:**

- [ ] Merged Android manifest inspected for permissions and components contributed by SDK plugins
- [ ] Release build configuration confirmed (scripting backend, stripping level, absence of debug grant paths) rather than inferred from the diff
- [ ] Where either check could not run, the gap stated in `## Limitations` rather than dropped

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase/fetch/stash) - the review reads history only
- Writing a report when invoked as a subagent - the parent owns it
- Writing a report at all when the change set touches only excluded surfaces
- Recommending server validation to a project with no server, instead of recording accepted exposure
- Reporting without a concrete attack ("input not validated" vs "a crafted link sets `level=99` and skips the paid unlock")
- Skipping an asset-triage row - state `no signal in diff` rather than leaving it blank
- Raising findings against `Library/`, `Temp/`, `obj/`, `Build/`, generated `*.csproj` / `*.sln`, or third-party SDK sources - while still reviewing their integration and init order
- Raising a finding on a `.meta` file rather than the asset it describes
- Granting currency, items, or entitlements on a client-side callback
- Treating a client-side rewarded-ad completion event, or a timer around it, as proof of a view
- Local-only IAP validation for anything of value
- Any secret, API key, keystore, or signing key shipped inside a build or committed to the repo
- `PlayerPrefs` for tokens, entitlements, or currency
- Presenting IL2CPP, stripping, obfuscation, or a hash check as protection rather than cost
- Deep-link, remote-config, or downloaded values used without validation
- An ads or analytics SDK initialized before consent is resolved
- Personalized ads in a children's-audience game, or third-party ads or analytics in a Kids Category app
- Filing a tamperable cosmetic single-player value at the same tier as a monetized one
- Reviewing the server's authentication or API contract here - it belongs to the owning service
