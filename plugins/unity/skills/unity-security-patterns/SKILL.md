---
name: unity-security-patterns
description: Harden Unity mobile games - save tampering, IAP and rewarded-ad grant integrity, secrets in builds, SDK data flow, deep links, store privacy.
metadata:
  category: mobile
  tags: [unity, security, iap, ads, tampering, secrets, il2cpp, privacy, gdpr, deep-links]
user-invocable: false
---

# Unity Security Patterns

> This skill owns **what an attacker or a hostile client can do**. Save file format and migration belong to `unity-save-persistence`; stripping and signing mechanics belong to `unity-build-release`.

## When to Use

- Adding IAP, rewarded ads, or any client-granted reward
- Storing player progress, currency, or entitlements
- Integrating a third-party SDK (ads, analytics, attribution)
- Handling deep links, remote config, or downloaded content
- Preparing a store submission with a privacy declaration

## Rules

- **The client is hostile.** A shipped build runs on a device the player controls: memory is editable, files are readable, traffic is interceptable, and the binary is decompilable. Any value the client asserts can be forged
- **Anything of real value is validated server-side.** IAP receipts, rewarded-ad completions, leaderboard scores, and entitlements are granted by a server that verified them, not by the client that claims them
- No secret ships in a build - not in code, a ScriptableObject, or `Resources`. A secret authorizes server-side actions; a publishable client key (an analytics game key, an ad unit id) and an integrity-only HMAC key (below) are not secrets. IL2CPP raises the cost of extraction; it does not prevent it
- Obfuscation and integrity checks raise attacker cost. They are not a substitute for server authority - state which one a given control is
- All external input is untrusted: deep-link parameters, remote config values, downloaded content, and clipboard. Validate type, range, and origin before use
- Third-party SDKs are a data-flow decision, not just a dependency. Know what each one collects before it ships
- A single-player game with no server has no authoritative validation available - say so explicitly and scope the controls to tamper *detection*, rather than implying protection it cannot have. A managed backend (Firebase, PlayFab, Unity Gaming Services) counts as a server: cloud functions and server-to-server callbacks provide authority without self-hosting

## Patterns

### What actually needs protecting

| Asset | Real risk | Control |
| --- | --- | --- |
| IAP entitlement | Fake purchase, replayed receipt | Server-side receipt validation with the store, plus a record of each transaction id (`transactionId`, `purchaseToken`) that refuses a duplicate grant |
| Rewarded-ad grant | Client claims a reward it never watched | Server-to-server ad callback, not a client call |
| Currency / progress | Save-file edit, memory edit | Server authority when monetized; integrity check when not |
| Leaderboard score | Forged submission | Server validation or server-side simulation |
| Cosmetic-only progress | Low - the player cheats themselves | Integrity check at most; do not over-engineer |
| API keys / secrets | Extraction from the binary | Do not ship them; proxy through a server |

The right control depends on who is harmed. A single-player 2048 high score does not need what a rewarded-ad grant needs.

### Rewarded ads: the grant boundary

The most common monetization exploit in casual games - the client tells itself the ad finished.

```csharp
// Bad - the reward is granted by client code an attacker controls
void OnAdClosed() { wallet.Add(500); }

// Good - the ad network calls the server; the client refreshes state it does not compute
void OnAdClosed() => StartCoroutine(RefreshWalletFromServer());
```

Ad networks provide a **server-side verification callback** (server-to-server) for exactly this. Wire it and treat the client-side completion event as a UI hint only. Where a game genuinely has no server, say so and accept the exposure explicitly rather than pretending the client call is a control.

### IAP receipt validation

```csharp
// Bad - grants the item because the client-side purchase handler ran
public void OnPurchaseComplete(Product p) { inventory.Grant(p.definition.id); }

// Good (Unity IAP 4.x listener API) - the purchase stays pending until the server has validated and granted
public PurchaseProcessingResult ProcessPurchase(PurchaseEventArgs e) {
    var p = e.purchasedProduct;
    api.ValidateAndGrant(p.receipt, onGranted: () => controller.ConfirmPendingPurchase(p));
    return PurchaseProcessingResult.Pending;   // Complete here would finalize it even if the server call fails
}
```

Local receipt validation (`CrossPlatformValidator`) raises the bar against casual tampering, but its check runs in a binary the attacker can patch or hook, and it cannot see a genuine receipt replayed from another purchase. Server-side validation against the store is the only control that holds. Restore-purchases flow is a correctness concern rather than a security one.

### Save integrity without a server

For an unmonetized single-player game, the goal is detecting casual edits, not defeating a determined attacker:

```text
Bad - plaintext JSON with the value an editor searches for first:
{"coins": 5000}

Good - payload plus a keyed hash; a hand-edited value fails verification:
{"data": "...", "sig": "<HMAC over data with a build-embedded key>"}
```

The key ships in the build and is therefore extractable - this raises cost, it does not prevent tampering. State that limit when recommending it. Never use this pattern as the basis for granting anything another player's experience depends on.

### Secrets and the build

`PlayerPrefs` is not secure storage: a registry entry on Windows, a plist (`NSUserDefaults`) on macOS and iOS, and a SharedPreferences XML file on Android - readable through device backups (iOS), a debuggable build, or root, and editable on desktop with none of them. Nothing sensitive goes in it. There is no secure keystore equivalent shipped with Unity, so tokens that must exist on-device belong behind a platform keychain plugin, with the same caveat that a rooted device defeats it.

The durable fix is architectural: the client holds a short-lived token issued by a server, not a long-lived key that unlocks a third-party service.

### IL2CPP and reverse engineering

IL2CPP compiles managed code to native, which makes decompilation meaningfully harder than Mono's near-source IL. It does not make it impossible - strings, resources, and asset bundles remain readable, and tooling exists for IL2CPP metadata. Treat it as raising cost, and never as an argument for shipping a secret.

### Untrusted external input

```csharp
// Bad - a crafted link drives arbitrary navigation and grants
var level = int.Parse(deepLinkParams["level"]);
LoadLevel(level);

// Good - validated against what actually exists and what the player has unlocked
if (deepLinkParams.TryGetValue("level", out var raw) && int.TryParse(raw, out var level)
    && progression.Exists(level) && progression.IsUnlocked(level)) LoadLevel(level);
```

A link navigates; it never grants. A `bonus`-style parameter is dropped, and any reward arrives through the server. Prefer verified App Links (Android) and Universal Links (iOS) to a bare custom scheme, which any installed app can claim.

Same discipline for remote config: a value driving currency, pricing, or unlocks is validated on arrival, and one outside its range is rejected for the bundled default rather than clamped to the bound, because a compromised or misconfigured config becomes an economy bug.

### Third-party SDK data flow

Each ads, analytics, or attribution SDK collects device and behavioural data on its own schedule. Before shipping, know for each: what it collects, whether it needs consent first, and whether it initializes before the consent answer exists. An SDK that phones home in `Awake` before the consent dialog has been answered is a compliance defect regardless of the dialog's correctness.

Store and legal requirements that touch the build: the ATT prompt before tracking on iOS; Apple's privacy manifests (`PrivacyInfo.xcprivacy`) - each SDK ships its own and Xcode aggregates them; the app's declares its own required-reason API use and data collection; the App Store privacy label and the Google Play Data safety form; consent gating in the EEA, UK, and Switzerland, where Google requires a certified IAB TCF consent tool for its ad products; and children's-audience rules - COPPA requires verifiable parental consent, Google Play Families forbids personalized ads, and Apple's Kids Category bars third-party advertising and analytics outside narrow exceptions. A game plausibly appealing to children needs this decided before integration, not after.

## Output Format

Two modes, chosen by what the request supplies.

**Authoring mode** - the request asks for code or a design. Emit, in order: any `Precondition: {defect in existing code the design depends on fixing}` lines; the code or design; one-line notes after it, one per decision this skill governs; then any `Deferred:` lines. No finding blocks, no severity, no status line.

**Review mode** - the request supplies something to judge: source, a diff, an asset or setting, or a report of a symptom (a QA ticket, a crash or CI log, a verbal description). Emit, in order: the no-server line when it applies, the finding blocks, any `Deferred:` lines, and - only when no block was emitted - the status line. Nothing else precedes the first block. A review requested with nothing to judge is still review mode.

```
### [{Critical | High | Medium | Low}] {anchor}

- Category: {ClientAuthority | IAPValidation | AdGrant | SaveTampering | Secret | SDKDataFlow | UntrustedInput | Privacy | Obfuscation}
- Evidence: {source | inferred (what was not seen)}
- Code: {one-line citation | not supplied}
- Attack: {what an attacker does, concretely - "edits coins in the save file", "calls the reward handler without watching"}
- Impact: {who is harmed and how - revenue loss, economy break, data exposure, store rejection}
- Fix: {concrete change, naming whether it is server authority or cost-raising}
```

The anchor is the first that applies: `file:line` when the source carries paths (a diff hunk by its new-file line); `Type.Member` when it arrived without paths; the asset path for an asset or setting; a short paraphrase of the reported symptom when nothing was read. `Code` is `not supplied` when nothing was read.

**One block per defect** - one root cause with one fix. The same defect at several sites is one block: anchor the clearest site and list the others in `Impact`. One line carrying two defects with separate fixes is two blocks. A reported symptom gets one block per cause - among those this skill's Patterns name for it - that the evidence cannot rule out, most likely first, each `Fix` opening with the check that confirms or eliminates it.

`Category` takes exactly one value. Where a defect fits two, take the one whose failure is worse and name the other in `Impact`; where it fits none, take the closest and name the real concern in `Impact`. A value in this enum is this skill's finding even where a sibling owns adjacent mechanics.

Severity bands - Critical = revenue, or an entitlement of real value, granted on unverified client claims (an ad, IAP, or deep-link grant), a shipped secret, or a privacy control absent where legally required (an SDK collecting before consent is resolved). High = tamperable state that affects other players or monetization, or a runtime credential stored in `PlayerPrefs` or a plain file. Medium = tamperable single-player state that gates progress. Low = a cosmetic-only grant or tampering, or a cost-raising control worth adding with no current exploit path. A defect no band names takes the band of the listed defect with the closest consequence, and `Impact` names that comparison.

`Evidence: source` means the lines that decide the defect and its band were read; an absence is source when the whole file that would hold it was read, and a diff hunk is source for the lines it shows. `Evidence: inferred` means some were not - a symptom report, a diff summary naming only a path, or a read line whose band turns on something unseen (a declaration, a caller, whether an asset is referenced); state what was not seen. Inferred caps the header at High: a Critical-band defect is written `[High]` and its `Impact` ends with `Uncapped: Critical.` Evidence never raises a band.

Order blocks by band, Critical first; a capped `[High]` block sorts before the other High blocks. Within a band, a root cause comes before the symptoms it produces, then the defect with the wider player impact; where neither separates two blocks, keep the order the input presents them in.

A defect owned by a sibling skill this file names is not emitted here. Write it after the findings as `Deferred: {defect} -> {owning skill}`, one line per defect. When a finding's fix needs a sibling's decision, emit the finding and add a `Deferred:` line for that part. In authoring mode the same line routes a design decision the sibling owns (`Deferred: save file atomic write -> unity-save-persistence`). `Deferred:` lines may precede any status line; omit them when there are none.

When the project has no server and no managed backend, the first line of the report is exactly `No server or managed backend: server-authority defects below are accepted exposures.` A backend that exists but does not handle a given grant counts as no server for that grant. Each server-authority defect is then still a normal finding block, with `Fix` replaced by `Accepted exposure: {why no authoritative fix exists; the cost-raising mitigation, if any}`. Severity keeps the band the defect would carry.

When no block was emitted, close with exactly one status line - the first row whose condition holds:

| Condition | Line |
| --- | --- |
| Source, a diff, an asset or setting, or a symptom report was supplied, and it yields no finding | `No security findings.` |
| A review was requested with nothing to judge | `Security check not run: no source supplied.` |

## Avoid

- Granting currency, items, or entitlements on a client-side callback
- Treating a client-side rewarded-ad completion event as proof of a view
- Local-only IAP receipt validation for anything of value
- Any secret, API key, or signing key shipped inside a build
- `PlayerPrefs` for tokens, entitlements, or anything security-relevant
- Presenting obfuscation, IL2CPP, or a hash check as protection rather than cost
- Deep-link, remote-config, or downloaded values used without validation
- An ads or analytics SDK initialized before consent is resolved
- Personalized ads in a children's-audience game, or any third-party ads or analytics in a Kids Category app
- Recommending server validation without noting the project has no server
