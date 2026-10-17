---
name: flutter-security-patterns
description: "Harden Flutter apps: secure storage, cert pinning, obfuscation limits, deep-link and platform-channel input, WebView, biometrics, secrets."
metadata:
  category: mobile
  tags: [flutter, dart, security, secure-storage, pinning, deep-links, webview, biometrics, obfuscation, masvs]
user-invocable: false
---

# Flutter Security Patterns

> Confirm the project's target platforms first - they decide which hardening applies. Store selection lives in `flutter-data-persistence`; HTTP client construction in `flutter-networking`; route shape and deep-link wiring in `flutter-navigation-patterns`. This skill owns the security decision inside each.

**Threat model.** The client runs on the attacker's hardware. The device may be rooted or jailbroken, the binary can be extracted and decompiled, the traffic can be proxied, and the process can be instrumented at runtime. Everything below reduces exposure or raises attacker cost; none of it makes the client trusted. Any control that must hold is enforced server-side.

## When to Use

- Deciding where a token, key, or sensitive record lives on device
- Reviewing deep links, platform channels, WebViews, or notification payloads as untrusted input
- Choosing whether to pin, obfuscate, gate on biometrics, or detect root
- Auditing a diff or release configuration for shipped secrets and leaky platform flags

## Rules

- Tokens, credentials, and keys live in platform secure storage (Keychain / Keystore). Never `shared_preferences`, a plain file, or a plain database column. Moving them out migrates existing installs on first launch: copy to secure storage, then delete the old entry
- **A secret compiled into the app is a published secret.** No key whose secrecy is the control goes into source, `pubspec.yaml`, bundled asset files, or `--dart-define` values, committed or not - those values are baked into the binary and readable from it. A vendor key the vendor restricts to this app's id and signing certificate is configuration, not a secret, and ships that way
- Every value crossing an app boundary is untrusted: deep links, platform-channel arguments, WebView messages, notification payloads, clipboard, imported files. Parse, validate against an allowlist, then use
- Authorization is a server decision. The client hides UI; the server decides access
- Obfuscation, root detection, and integrity checks raise cost. Never gate a security-critical branch on their result alone
- A biometric prompt proves user presence on that device at that moment - not identity to your backend. Bind it to a key the OS withholds, not to an `if`
- Pinning is an operational commitment: multiple pins, a rotation plan, and a remote off-switch, or do not pin
- Configure backup and export flags explicitly. Platform defaults leak
- Never log tokens, PII, or full request bodies; keep debug affordances out of release builds

## Patterns

### Token storage

```dart
// Bad - plaintext plist / XML, readable on a rooted device, may land in a backup
await prefs.setString('access_token', token);

// Good - Keychain (iOS) / Keystore-backed store (Android)
await secureStorage.write(key: 'access_token', value: token);
```

- iOS Keychain items **survive app uninstall**. Delete them on logout, and on first run after install, or the next installer inherits a live session
- Set the Keychain accessibility class so items are unavailable before first unlock and never sync to iCloud (the `AfterFirstUnlockThisDeviceOnly` family). On Android, Keystore keys never leave the device; exclude the secure-storage ciphertext file from backup, or a restored install cannot decrypt it
- Secure storage is small and slow: it holds keys and tokens, not datasets. Encrypt the dataset at rest - SQLCipher for rows, a per-file AES-GCM key for photos and documents - and keep only its key there. Captured photos carry EXIF location and device data: strip metadata before upload and before writing to any shared location. A queued upload runs only under a live session: it pauses when refresh fails and is purged on sign-out. Keychain classes apply on macOS too; its App Sandbox entitlements are `flutter-adaptive-responsive`'s. Analytics events carry ids, never names, emails, amounts, or free text (`Privacy`)
- No browser store offers secure-storage guarantees - do not persist secrets on web

### A shipped secret is a public secret

```dart
// Bad - compiled in; `strings` on the extracted app finds it
const key = String.fromEnvironment('MAPS_API_KEY');

// Good - the device holds a user token; the backend holds the vendor key and proxies
final res = await api.post('/v1/geocode', data: {'q': q});
```

- If a vendor SDK genuinely requires an on-device key, treat it as public: restrict it at the vendor to your bundle id / package plus signing certificate, scope it to the minimum API surface, and monitor usage. Restriction is the control; secrecy is not on the table
- `--dart-define` and `--dart-define-from-file` are build configuration, not a secret mechanism. Committing the file makes it worse, not different
- Anything already shipped in a public build is compromised. Rotate it - deleting it from `git` does not un-ship it

### Certificate pinning and its rotation risk

- Pin the **public key** (SPKI hash), not the certificate. A leaf key survives renewal only when the renewal reuses the key pair, and managed certificates usually rotate it, so pin the issuing CA's key or ship pins for the keys you will rotate to
- Ship at least one backup pin for a key you are not yet serving. Without it, renewal bricks every installed app - and a bricked client cannot be fixed by a server deploy
- Pair pinning with a server-driven off-switch and a forced-update path so a mis-rotation is recoverable
- Pinning defeats a network attacker with a user-installed CA. It does **not** defeat an attacker who owns the device; hooking frameworks patch the check. Scope the claim accordingly
- Dart's `HttpClient` on Android never trusts user-added CAs (it reads only the system store; the API 24+ network-security default applies to platform-stack clients), so much of the casual-proxy threat is covered there without pinning; iOS trusts a user-installed profile CA once the user enables it, so it has no such baseline. Weigh the operational cost per platform
- Where the check lives depends on the HTTP stack. Dart's `HttpClient`, and Dio's default adapter, run their own TLS and ignore the Android network security config and iOS `NSPinnedDomains`; pin there with a `SecurityContext(withTrustedRoots: false)` that trusts only the issuing CA certificates you pin (a certificate pin, so ship the backup CA with it), or a package that checks the SPKI hash. Dio's `IOHttpClientAdapter(validateCertificate: ...)` runs after the request, headers included, has been sent, so it detects a mismatch rather than preventing the leak. `badCertificateCallback` runs only after validation has failed and receives the certificate where it failed, which varies by platform, so it is not a dependable pin. Platform config pins apply only to a platform-stack client (`cupertino_http`, `cronet_http`). Implement it once in the client factory, never per call site

### Obfuscation and its limits

```
flutter build appbundle --obfuscate --split-debug-info=build/symbols
```

- Renames Dart symbols. It does not encrypt strings, hide assets, protect Kotlin/Swift code, or stop runtime instrumentation
- Keep the symbol directory for every shipped build - crash reports are unreadable without the matching one, and a mismatched directory symbolizes to garbage
- It raises reverse-engineering cost. It is never a reason to move a secret or a check into the client

### Deep links are attacker-controlled input

```dart
// Bad - any app or web page can drive navigation into an authenticated surface
router.go(uri.queryParameters['next']!);

// Good - allowlist known routes, reject the rest
final next = uri.queryParameters['next'];
if (next != null && allowedRoutes.contains(next)) router.go(next);
```

- Custom URL schemes are **not exclusive**: another app can register `myapp://` and receive links meant for you. Only verified App Links / Universal Links (`assetlinks.json`, `apple-app-site-association`) bind to a domain you own
- A link navigates; it must not perform a state-changing or privileged action on arrival. The action still requires the session and, when sensitive, an explicit confirmation
- Ids and tokens in parameters are attacker-chosen. Access is decided by server-side authorization on the follow-up call, not by the parameter being present
- Same treatment for notification payloads and inbound intent extras

### Platform channels

```dart
// Bad - native side trusts the Dart caller
//   val path = call.argument<String>("path")!!
//   File(path).readText()

// Good - validate on the receiving side: type, range, allowlisted base directory
```

- The channel is not a boundary you control: anything in the process, including injected code, can invoke a method channel by name. Validate arguments natively even though "only our Dart calls it"
- The return direction is `dynamic`. Check types before casting values coming back into Dart
- Expose the specific operation the feature needs, never a general primitive (arbitrary file read, arbitrary URL open, shell execution)

### WebView safety

| Setting | Posture | Why |
| --- | --- | --- |
| JavaScript | off unless the content requires it | unrestricted JS is the precondition for everything below |
| JavaScript channels | none, or one narrow channel | a channel is a callable bridge for whatever script the page loads, including injected third-party script |
| Navigation | allowlist origins in the navigation delegate | otherwise a redirect walks the WebView to hostile content that still holds your channels |
| Loaded URL | never raw user- or link-supplied | deep link into a WebView is a standard chain |
| File access / file URLs | off | web content reading local files reads app-private data |
| Mixed content | off | silently downgrades the transport for subresources |

A JavaScript channel handler validates its input and must not proxy a privileged operation (token read, storage write, native call) to page script. If the handler would be dangerous when invoked by an arbitrary website, it is dangerous. A WebView URL from any caller - a route parameter or a constructor argument - is untrusted until checked against an origin allowlist.

### Biometrics

```dart
// Bad - a bool decides access; patch the branch or the return value and it is gone
if (await auth.authenticate(localizedReason: 'Unlock')) showSecrets();

// Good - the OS releases the material only after a successful check; no bool to patch
// the value lives behind a key created with user authentication required (Keystore /
// Keychain biometry access control), e.g. through biometric_storage
final token = await biometricStore.read(); // no passing prompt -> exception, no value
```

- What it proves: a credential enrolled on this device was presented just now. Nothing about which human, nothing about device integrity, nothing to your server. A backend must never accept "the client says biometrics passed"
- The strong form binds a stored key to biometric authentication at the platform layer so the value is unreadable without it. Whether the Flutter package in use exposes that binding varies - verify against the package before designing on it, and fall back to gating a locally encrypted value
- Enrolment changes matter: a newly added fingerprint or face should invalidate a biometric-bound key (both platforms offer a current-set binding for this)
- Always keep a non-biometric path (device passcode or re-login). Biometric-only locks users out on sensor failure
- `local_auth` provides the prompt; the security comes entirely from what a passing prompt is wired to

### Platform flags that leak by default

| Flag / mechanism | Risk at default | Posture |
| --- | --- | --- |
| Android `android:allowBackup` | app data copied off device via cloud backup | disable, and on targetSdk 31+ also exclude sensitive paths with `dataExtractionRules`, which govern cloud backup and device-to-device transfer and replace `fullBackupContent` on Android 12+ |
| Android `android:exported` | another app invokes your activity, receiver, or provider; targetSdk 31+ requires it explicit on any component with an intent filter | `false` unless deliberately public; a deep-link activity is `true`, so validate its input |
| iOS file backup | app files sync into iCloud / local backups | mark sensitive files excluded from backup; keep secrets in the Keychain with a `ThisDeviceOnly` class |
| Cleartext HTTP (`usesCleartextTraffic`, ATS exceptions) | blocked by default on modern targets; an explicit opt-in re-enables it | off; no per-domain exception without a written reason. Dart's own `HttpClient` does not enforce these flags, so an `http://` URL in Dart code is the finding there |
| Debug logging, debuggable builds, test endpoints | release ships with debug affordances | gate on `kReleaseMode` and verify in the built artifact, not the source |

Sensitive screens: Android `FLAG_SECURE` blocks screenshots and the task-switcher thumbnail; iOS has no equivalent flag, so cover the window when the app resigns active.

### Root and jailbreak detection: defense-in-depth only

- Bypassable by construction - the check runs inside the environment it is assessing. Root-hiding and hooking tools defeat it
- Useful as a **signal**: report the result to the server as one input to risk scoring, where the response can change without an app release
- Useless as a **gate**: refusing to launch on a rooted device blocks hobbyists, stops no real attacker, and breaks legitimate users
- When the decision matters, use platform attestation verified server-side (Play Integrity, App Attest / DeviceCheck) - the server evaluates the verdict, not the app

## Output Format

When invoked from a review workflow, emit one block per finding:

```
### [{Critical | High | Medium | Low}] {file:line}

- Category: {Storage | Secrets | Transport | UntrustedInput | WebView | AuthN | PlatformConfig | Integrity | Privacy}
- MASVS Area: {STORAGE | CRYPTO | AUTH | NETWORK | PLATFORM | CODE | RESILIENCE | PRIVACY}
- Platform: {android | ios | web | desktop | all | unconfirmed: <target it depends on>}
- Code: {one-line citation}
- Attack scenario: {who, with what access - rooted device, network MITM, malicious app, hostile page}
- Fix: {concrete change; name the store, flag, or validation}
- Server-side dependency: {none | what the backend must also enforce}
```

The heading severity is one of Critical, High, Medium, Low. Critical = user credentials or user data recoverable with realistic access (a rooted device, a device backup, a malicious app on the same device), a privileged action reachable from an app boundary with no precondition (a deep link that acts on arrival), or a security control the backend relies on that exists only on the client. High = a concrete path to sensitive data or action given one plausible precondition, or a compiled-in key - first-party or vendor, as source or as a CI build argument - that grants access on its own and is not restricted to this app (Critical when it grants access to user data). Medium = exposure requiring an unlikely precondition, or two or more plausible ones. Low = hardening with no exploitable path in this app, including a compiled-in key that only identifies the app to a first-party backend behind a user session. When a finding matches anchors in two bands, the higher band wins. Default Category to Area mapping: Storage and Secrets -> STORAGE (a hardcoded cryptographic key -> CRYPTO), Transport -> NETWORK, UntrustedInput -> PLATFORM when it arrives from another app (deep links, intents) and CODE otherwise (platform channels, clipboard, imported files), WebView -> PLATFORM, PlatformConfig -> STORAGE for backup flags, NETWORK for cleartext flags, RESILIENCE for a debuggable flag, PLATFORM otherwise, AuthN -> AUTH, Integrity -> RESILIENCE, Privacy (collecting or sending more personal data than the feature needs) -> PRIVACY. Logged tokens or PII are Secrets, STORAGE. An unchecked cast on a boundary value is UntrustedInput; data from the app's own server is a boundary value. An absent manifest attribute (`allowBackup`, `exported`) anchors on the element that should carry it. A session secret held only in memory is not a finding, and pinning absent on a stack that never pinned is not a finding unless the product requires it. `Platform` is `all` when the attack needs no platform feature (a rooted device reading plaintext), and the artifact's target for a CI workflow finding; platform configuration absent from the read set (no `android/` or `ios/` directory) puts `PlatformConfig` on `Not checked`.

**Unknown platform targets:** emit the finding with `Platform: unconfirmed: <target>`. Do not drop it.

Blocks are one per defect, ordered by severity, then file path (repository-relative, byte order), then line, then enum order. A defect is one rule at one fix site: the same rule broken at N sites that each need their own edit is N blocks; the same rule broken at N sites that one edit fixes (a declaration, a shared helper, a config key) is one block anchored on the line to edit, naming the other sites as `also <file:line>` on its citation line (the block's `Code:` line); one line breaking two rules with two different fixes is two blocks, with one fix it is one block under the rule naming the worse failure (on a tie, the earlier enum value).

Review output is, in order: any opening lines this skill defines, the finding blocks, one `Also seen: <file:line> - <defect> (owner: <skill>)` line per defect in the files read that no value of this skill's enum covers - one per line, blank-separated, in file order (no block, no severity; the owner is whichever of dart-language-patterns, flutter-widget-patterns, flutter-riverpod-patterns, flutter-navigation-patterns, flutter-networking, flutter-data-persistence, flutter-local-db-migration, flutter-adaptive-responsive, flutter-accessibility, flutter-i18n, flutter-performance, flutter-error-handling, flutter-platform-channels, flutter-testing-patterns, flutter-build-release, flutter-overengineering-review covers it, or `unowned`), one `Not checked: <names> - <reason>` line (names are this skill's `Category` values, or the path of a file that could not be read) when any check could not be exercised, then `No security findings.` when there are no blocks. A check is `Not checked` when the files read reference its subject but the code that decides it was not read (an imported file, a test or platform directory, release history); a check whose subject nothing in the files read references is clean; the sentinel is emitted only when there are no blocks, `Not checked` lines or not. A check with a finding is never `Not checked`. A file in scope that could not be read is its own `Not checked` entry, `<path> - not readable`; when the file that decides a finding is unknown, `<path>` in the unconfirmed suffix reads `unknown file`. A finding whose confirmation lies in a file not read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to its `Attack scenario:` line, and does not move its check to `Not checked`. Invoked directly, a request to write or change code takes the implement shape and a request to review, audit, or explain a failure takes the review shape.

The closing lines - `Also seen` and `Not checked` only when they have content, the sentinel only when there are no blocks:

```
Also seen: {<file:line> - <defect> (owner: <skill>)}

Not checked: {<names> - <reason>}

No security findings.
```



When invoked from an implementation workflow, emit a decision table:

```
| Concern | Decision | Rationale | Server-side dependency |
|---------|----------|-----------|------------------------|
| {asset, input, or control} | {where it lives, what validates it, or what is deliberately not done} | {threat it answers} | {what the backend must also enforce \| none} |
```

One row per concern the change touches or the brief names; an unchanged decision (not pinning) gets a row only when the change relies on it. For example: `Refresh token | secure storage, deleted on logout and first run | Keychain survives uninstall | rotation and revocation`, `Vendor map key | server proxy | shipped binary is extractable | proxy endpoint, per-user quota`, `Card data | vendor SDK hosted fields; never touches app code | keeps PCI scope with the vendor | payment confirmation by webhook, not by the client`, `Pinning | not pinned | no rotation owner; Android CA baseline accepted, iOS risk accepted | none`, `Deep-link next param | route allowlist | attacker-supplied navigation target | authorization on the fetched resource`.

```
Fixed in plan: {<file:line> - <defect> | none}

Pre-existing: {<file:line> - <defect> | none}

Not read: {<path> - <reason> | none}
```

Implement mode describes the state after the plan and ends with these lines, each on its own line with a blank line between: `Fixed in plan: <file:line> - <defect>` per defect in existing code the plan corrects, or `Fixed in plan: none`; `Pre-existing: <file:line> - <defect>` per defect left in place, or `Pre-existing: none`; `Not read: <path> - <reason>` per file the plan needs that is absent, could not be read, or was not read, or `Not read: none`. A defect is fixed in the plan when it sits in code the change edits, or when the new code would misbehave on first run on top of it; every other defect in code the new code calls or reads is `Pre-existing`; code the new code neither edits, calls, nor reads is not listed, except a defect that breaks the build, which is always `Fixed in plan`. Code not yet written is cited as `<path> (new)`.

## Avoid

- Tokens, credentials, or keys in `shared_preferences`, a file, a plain column, or any web store
- Keys whose secrecy is the control in source, `pubspec.yaml`, assets, or `--dart-define` values
- Treating `--obfuscate` as protection for an embedded secret, or shipping without keeping the symbol directory
- Pinning without backup pins, a rotation owner, and a remote off-switch
- Deep links or notification payloads used unvalidated, or performing a privileged action on arrival
- Trusting a custom URL scheme as if it were exclusive to your app
- Platform-channel arguments consumed natively without validation, or a channel exposing a general-purpose primitive
- WebViews with unrestricted JavaScript, unrestricted navigation, file access, or a channel that proxies privileged work to page script
- Loading a user- or link-supplied URL into a WebView
- Branching on a biometric bool, or reporting biometric success to a server as authentication
- Biometric-only access with no passcode or re-login fallback
- Leaving `allowBackup` at its default, or opting into cleartext traffic or exporting a component without a written reason
- Root detection as a gate, or any client-side check standing in for server-side authorization
- Logging tokens, PII, or full request bodies; `print` / verbose logging surviving into release
