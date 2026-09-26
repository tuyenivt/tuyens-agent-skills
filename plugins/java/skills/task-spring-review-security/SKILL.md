---
name: task-spring-review-security
description: "Spring Boot security review: SecurityFilterChain, OAuth2/JWT, @PreAuthorize, Bean Validation, Actuator, OWASP."
agent: java-security-engineer
metadata:
  category: backend
  tags: [java, spring-boot, security, spring-security, oauth2, jwt, owasp, workflow]
  type: workflow
user-invocable: true
---

# Spring Boot Security Review

Spring-aware security review naming `SecurityFilterChain`, OAuth2 Resource Server, JWT, method security, Bean Validation, and Spring Security Crypto idioms directly. Findings include an attack scenario and a concrete Spring remediation. Stack-specific delegate of `task-code-review-security` for Java / Spring Boot.

## When to Use

- Spring Boot PR for security regressions
- Pre-deployment hardening on auth, authz, file upload, payment, PII paths
- Validation / method-security drift sweep across controllers
- Auditing an OAuth2 / JWT flow or new `@PreAuthorize`

**Not for:** performance (`task-spring-review-perf`), general review (`task-spring-review`).

## Invocation

| Invocation                              | Meaning                                                |
| --------------------------------------- | ------------------------------------------------------ |
| `/task-spring-review-security`          | Current branch vs base; on trunk, routes to the audit path below |
| `/task-spring-review-security <branch>` | `<branch>` vs base (3-dot diff)                        |
| `/task-spring-review-security pr-<N>`   | PR head fetched into `pr-<N>` (user runs fetch first)  |
| `/task-spring-review-security audit`    | Whole-service audit at `HEAD`, from any branch or a detached `HEAD` (CI) |

**Whole-service audit:** entered by the `audit` argument, or when Step 3 fails fast on trunk - do not stop. No handle exists, so assemble the fields: `branch` = `git symbolic-ref -q --short HEAD`, else `git describe --exact-match --tags HEAD`, else `detached-<short sha>`; `base_ref` = `head_ref` = `HEAD`; `base_sha` = `head_sha` = `git rev-parse HEAD`. With the `audit` argument, its dirty-tree check reuses `review-precondition-check` Step 1's filter and stop message. Then run Step 3's round gate and every step from Step 4 against the full security surface at `HEAD`: no diff scoping, findings cite `file:line` at `HEAD`, depth `deep`.

Audits are unbounded by nature, so bound them by exposure: every `SecurityFilterChain` and every internet-reachable controller in full, then authenticated controllers, then internal ones. State in the Summary's `Coverage` field what you read and what you did not - a truncated audit that says so is useful; one that reads as complete is not.

**Subagent mode** (spawned by `task-spring-review`, or run inline by it when it cannot spawn; any other invocation is standalone): the parent passes the handle's `base_ref` / `head_ref`, `base_sha` / `head_sha`, the diff and commit log already read, `depth`, the stack (with Boot/Java versions and database engine), `round`, and - on round 2+ - `prior_head_sha` and the prior findings for this scope. Step 3, verification, reconciliation, and the report file are the parent's; never re-raise a prior finding the parent passed unless its cited site changed since `prior_head_sha`.

**Depth:** `standard` (default) scopes Steps 4-9 to the diff. `deep` (user-passed or parent-promoted) additionally runs the audit-scope pass over the full security surface.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed stack from a parent. If not Spring Boot (standalone only): stop and tell the user to invoke `/task-code-review-security`; as a subagent, return the mismatch to the parent instead.

Read the Spring Boot version from the build file (Gradle `org.springframework.boot` plugin or version catalog; Maven `spring-boot-starter-parent` or the imported `spring-boot-dependencies` BOM) and the Java version from `java.toolchain` / `<java.version>` / `maven.compiler.release`; `stack-detect` does not report either. Every construct a finding cites as present and every fix recommends must exist and bind on that version - including fixes taken from a composed atomic. Below Boot 4.0, write the row's or the atomic's Boot 3 form; when it has none, say `Boot 3 form not given` rather than emitting the Boot 4 one.

Boot 3 manages Spring Security 6.x, which deprecates rather than removes `authorizeRequests()` (from 6.0), `and()` / `csrf()` and the rest of the no-arg DSL (from 6.1), and `AntPathRequestMatcher` / `MvcRequestMatcher` (from 6.5); `@EnableGlobalMethodSecurity(prePostEnabled = true)` still enables `@PreAuthorize` there. Each is a `[Recommend]` Boot 4 upgrade blocker, never broken code.

### Step 3 - Resolve the Diff and Round

Skip in subagent mode; the `audit` argument skips only the precondition call - the round gate still runs. Use skill: `review-precondition-check` with the invocation's target argument and `report_type: review-security`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy`). Fail-fast on trunk -> the whole-service audit only when `git symbolic-ref --short HEAD` equals the named trunk, otherwise print the precondition's trunk message, point at `audit`, and stop; any other fail-fast -> surface the message verbatim and stop. No state-changing git.

**Round gate (standalone), before any surface read.** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs. An audit has its SHAs already and reads `review-security-<branch>.md` (the writer's filename sanitization) directly as its `prior_checkpoint` - `legacy` when the frontmatter is missing, unparseable, or another lens's or branch's. A valid `prior_checkpoint` with the same `head_sha`, the same kind (an audit's `base_sha` equals its `head_sha`; a diff review's does not), and a `depth` not below this run's -> print `No new commits since prior security review.` and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` -> `round: 1`. Then read `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>` once and reuse (an audit has neither). Read the build and deploy files at `git show <head_ref>:<path>` after the round gate, never from the working tree before it - Step 2's version read included.

### Step 4 - Read the Security Surface

Filter chains, method-security enablement, JWT converter/decoder beans (`JwtAuthenticationConverter`, `JwtDecoder`), and security config are read in full at every depth - they gate every endpoint; controllers, DTOs, and tests where the diff changes them.

- Every `SecurityFilterChain` `@Bean` - read matchers top-to-bottom. A broad `permitAll` placed above a narrower authenticated rule shadows it and is a real vulnerability; a narrow allowlist above a trailing `anyRequest().authenticated()` is the correct shape, not a finding
- Every changed `@RestController` / `@Controller` - `@RequestBody` types (entity vs DTO), `@PreAuthorize` / `@PostAuthorize` added or removed, and whether `@EnableMethodSecurity` (or Step 2's Security 6 form) is anywhere in the application context (without it, every `@PreAuthorize` in the codebase is inert)
- `application.yml` and per-profile - `management.endpoints.web.exposure.include`, `spring.security.*`, `server.servlet.session.*`, `server.ssl.*`
- `build.gradle(.kts)` / `pom.xml` - `spring-boot-starter-security`, `spring-boot-starter-security-oauth2-resource-server` (Boot 3 name: `spring-boot-starter-oauth2-resource-server`), `spring-boot-devtools` (must be `developmentOnly` / `runtime optional`), and every explicitly pinned version (a version on a Boot-managed dependency, a version-catalog entry, an `ext` / `<properties>` override) for the A06 row
- Modified tests - a green test obtained by disabling security, removing `@PreAuthorize`, or swapping an authenticated request for an anonymous one is a finding, not a fix

When the diff removes a security annotation or relaxes a matcher, consult the prior revision via `git log -p` to confirm what was protected before. When the prior revision is unreachable (shallow clone, audit path), review the present state only and say so on the finding rather than asserting a regression you cannot see.

At `deep`, the bullets read repo-wide, bounded by the exposure order above.

### Step 5 - Apply Canonical Patterns

Use skill: `spring-security-patterns`. Where it and a checklist row below disagree on the current idiom, the atomic wins, except a Security 6 form this file states (SPA CSRF).

### Step 6 - Authentication

Run the rows that match the mechanism in use; a resource server issues no tokens and has no credential endpoint, so token-issuance and login rows are N/A there rather than findings.

- [ ] **`SecurityFilterChain` explicit and current** - `WebSecurityConfigurerAdapter` removed in 6.0; on Security 7 (Boot 4), `and()`, `authorizeRequests()`, `AntPathRequestMatcher` / `MvcRequestMatcher` and the no-arg DSL (`csrf()`) are removed - on 6.x, deprecated: `authorizeRequests()` from 6.0, `and()` / `csrf()` from 6.1, matchers from 6.5
- [ ] **OAuth2 Resource Server** - `issuer-uri` (or `jwk-set-uri`) configured, with `spring.security.oauth2.resourceserver.jwt.audiences` set so audience is actually validated; a `JwtAuthenticationConverter` only where claim mapping needs code
- [ ] **JWT authorities mapping** - Every hasRole / hasAuthority check is only as real as the JWT converter feeding it: a top-level claim needs authorities-claim-name plus authority-prefix ROLE_; a nested claim (Keycloak realm_access.roles) yields no authorities through setAuthoritiesClaimName - Boot 4.1 authorities-claim-expressions plus authority-prefix ROLE_, else a custom converter; the prefix is empty instead when the claim values already carry ROLE_ (the default is SCOPE_). When the mapping yields nothing, every role gate denies everyone: say so, and never propose a role-based bypass. Boot's converter backs off when the app declares its own `JwtAuthenticationConverter` bean, so the 4.1 fix also deletes that bean.
- [ ] **JWT validation** - issuer and audience verified, not just signature and expiry; HMAC secret never falls back to a hardcoded default. `NimbusJwtDecoder` cannot be configured to accept `alg: none`, so do not raise that against a Boot resource server - it is a concern for hand-rolled jjwt/java-jwt decoding
- [ ] **Token and secret generation** - unguessable source. `UUID.randomUUID()` is v4 over `SecureRandom` and is not a weak-randomness finding; `Math.random()`, `new Random()`, timestamps, and sequential ids are
- [ ] **Refresh-token rotation** (authorization servers only) - short access-token life (5-15 min); refresh tokens revocable
- [ ] **Form / Basic login** - `PasswordEncoderFactories.createDelegatingPasswordEncoder()` (bcrypt default), `BCryptPasswordEncoder` (no-arg strength 10 meets the bar), or `Argon2PasswordEncoder`; `DaoAuthenticationProvider` + `UserDetailsService`; `NoOpPasswordEncoder` only in tests or as the delegating encoder's default-for-matches on legacy rows with a re-hash path (`UserDetailsPasswordService`)
- [ ] **Session** - Spring Security defaults `sessionFixation` to `changeSessionId()`, which is correct on Servlet 3.1+; flag only an explicit downgrade. Cookies `Secure`, `HttpOnly`, `SameSite=Lax|Strict`
- [ ] **Brute-force protection** - rate limiting on any endpoint that verifies a credential or sends outbound mail/SMS: `/login`, token endpoints, password reset, email change, MFA challenge
- [ ] **No credentials in committed config** - env vars, Vault, AWS Secrets Manager, Spring Cloud Config

### Step 7 - Authorization

- [ ] **`@EnableMethodSecurity` (or Step 2's Security 6 form) active** - present-but-inert `@PreAuthorize` is an authorization bypass, not a defense-in-depth gap; severity follows what the annotations were the only gate for
- [ ] **Drift sweep** - every new or modified endpoint is covered by a matcher or `@PreAuthorize`, **and the rule is right for the endpoint**: a `permitAll` matcher satisfies "has a rule" while authorizing nothing, so state what the rule permits, not that one exists
- [ ] **IDOR** - lookups scope through the principal (`findByIdAndOwnerId(id, principalId)`), not `findById(id)` + post-hoc check; an owner id accepted from the request body or a query parameter is client-declared and cannot authorize
- [ ] **Per-element filtering** - collection returns use `@PostFilter` or filter at the query layer
- [ ] **Tenant isolation** - queries scope by `tenantId` at repository layer (Hibernate `@Filter`, `@TenantId`, or query parameter)
- [ ] **Default-deny** - `.anyRequest().authenticated()` (or stricter) closes each chain after its allowlist; no trailing `.permitAll()`. The last chain must be matcher-less, closing with `anyRequest()` and permitting `/error`; without one, an unmatched path runs with no security filters (Critical when a controller path is unmatched)
- [ ] **CSRF** - enabled for stateful sessions; `csrf(AbstractHttpConfigurer::disable)` only for stateless JWT APIs with documented rationale
- [ ] **CORS** - `CorsConfigurationSource` with explicit origins (never `*` for credentialed); minimal methods/headers

### Step 8 - Input Validation and Mass Assignment

- [ ] **Bean Validation** on every `@RequestBody` DTO (`@NotNull`, `@Size`, `@Email`, `@Pattern`); `@Valid` on the controller parameter
- [ ] **Records / immutable DTOs** for input - Jackson uses the constructor, defeating mass-assignment
- [ ] **No entities as `@RequestBody` or in responses** - Jackson on a JPA entity binds fields the API never intended inbound, and serializes internal fields outbound

  ```java
  // bad: attacker submits {"role":"ADMIN"} and is promoted
  void update(@RequestBody User user) { repo.save(user); }
  // good
  void update(@Valid @RequestBody UserUpdateRequest req) { ... }
  ```

- [ ] **No privilege-bearing fields in user-facing DTOs** - `role`, `admin`, `ownerId`, `userId`, `tenantId`, `status`. Admin-only paths use a separate DTO and `@PreAuthorize("hasRole('ADMIN')")`
- [ ] **Declared-but-unread controls** - a DTO field or header that advertises a security step (`currentPassword`, `otp`, `confirmToken`, `Idempotency-Key`) that no service path reads. The contract promises step-up verification the code never performs
- [ ] **Separate response DTOs** strip `passwordHash`, `mfaSecret`, `apiKeyHash`, `resetToken`. `@JsonIgnore` on entity fields is brittle - rename or accidental removal silently re-exposes
- [ ] **Password change** validates current password before applying new; rate-limited per user
- [ ] **File uploads** (`MultipartFile`):
  - Content-based type detection (Apache Tika), not `getContentType()` or extension
  - Size limit appropriate to the endpoint - Boot ships 1MB/10MB defaults, so absence of `spring.servlet.multipart.max-file-size` is not absence of a limit
  - Stored outside webroot; `Content-Disposition: attachment` to block inline HTML/SVG
  - Filename via `Path.resolve(name).normalize()` + `startsWith(baseDir)`
- [ ] **Process execution** - no `Runtime.exec` / `ProcessBuilder` with interpolated input; allowlist + tokenized arguments

### Step 9 - Spring-Specific OWASP Sweep

Every row below gets one verdict from the Output Format's `OWASP Sweep` enum. In subagent mode the sweep is a discovery checklist: publish what it surfaces as findings (a `Control absent` verdict as a Low `[Recommend]` finding at the build file) and return no sweep section.

**A diff review scopes every claim to what was read.** A finding asserting that a control is *absent* - no rate limiting, no `@EnableMethodSecurity`, no matcher - is a service-wide claim: raise it only when you read the surface that would hold it; otherwise the row is `Not assessable - <what you could not read>`. A defect you did read, inside the diff or not, is a finding; verification attributes and labels it.

| Risk                          | Spring-specific check                                                                                                                                |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control (A01)   | Steps 6-7 satisfied; no implicit `permitAll`; method security actually enabled                                                                        |
| Cryptographic Failures (A02)  | `BCryptPasswordEncoder` / `Argon2PasswordEncoder` for passwords; no `MD5`/`SHA-1` for auth; secret-bearing tokens stored hashed; TLS via `server.ssl.*` or upstream LB; HSTS |
| Injection (A03)               | Derived queries or `@Query` with named params; no string concat in JPQL, native SQL, or `EntityManager.createNativeQuery`; `Sort.by(field)` validated against an allowlist |
| Insecure Design (A04)         | `@EnableMethodSecurity` on; default-deny matcher chain; declared controls actually wired                                                              |
| Security Misconfiguration (A05) | Actuator exposure minimal in prod; `heapdump` and `threaddump` never reachable unauthenticated. `/actuator/env` masks values by default since Boot 3 (`show-values: NEVER`), so an exposed `env` leaks the property and source inventory, not secret values. `shutdown` access defaults to none (below Boot 3.4: disabled); exposure alone does not open it. DevTools `developmentOnly`. H2 console disabled outside dev |
| Vulnerable Components (A06)   | Each pinned version from Step 4 against the declared Boot version's BOM: a direct pin below the managed version, or one with an advisory you can name (library, version, CVE), is a finding, never `Not assessable`. A dependency-CVE gate in CI (OWASP dependency-check, Snyk, Dependabot) enforced, else `Control absent`. The resolved transitive tree is `Not assessable` without the scan output |
| Auth Failures (A07)           | Step 6 satisfied; rate limiting on credential-verifying and mail-sending endpoints                                                                    |
| Data Integrity (A08)          | No `ObjectInputStream.readObject` on untrusted input; Jackson default-typing off; untrusted YAML never parsed by SnakeYAML below 2.0 (Boot < 3.2 manages 1.33) without `SafeConstructor`, nor by a `LoaderOptions` whose `TagInspector` allows global tags                                        |
| Logging & Monitoring (A09)    | Logback masks `password`, `token`, `creditCard`, `ssn`, `apiKey`; **and personal data** - email, phone, address, government id - is not logged in the clear; security events (login fail, `AccessDenied`) logged; no entity serialization in `log.info` |
| SSRF (A10)                    | `RestClient` / `WebClient` validate the target host against an allowlist and reject private ranges (`127.0.0.0/8`, `10/8`, `172.16/12`, `192.168/16`, `169.254/16`, `::1`). Resolve once, validate the resolved address, then connect to that address via a pinned resolver or custom socket factory - re-resolving at connect time is what opens the DNS-rebind window, not what closes it |

Then one row each for the Spring-specific extras: **open redirect** (`sendRedirect` on user input, allowlisted), **SSTI** (no Thymeleaf `${...}` on user-controlled template strings; SpEL never receives user input as an expression), **XSS** (no `th:utext` on user input), **SPA CSRF** (`csrf.spa()` on Security 7; on Security 6, `CookieCsrfTokenRepository.withHttpOnlyFalse()` alone keeps the deferred XOR token, so no cookie is written on the first GET - it also needs a handler resolving the raw header value and a step that loads the token: the XOR delegate's `setCsrfRequestAttributeName(null)` or a filter calling `getToken()`).

### Step 10 - Verify and Reconcile

Subagent runs skip this step - the parent verifies and reconciles its merged set once. Standalone runs apply review-finding-verify inline: Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and `Annotation` columns. An audit has no diff: run the claim-confirmation pass only - no attribution, no de-escalation, no annotation but `_(unverified: <reason>)_` - since every audit finding is pre-existing and de-escalating would strip `[Must]` from findings exploitable today.

**Round 2+.** Project every tier of the prior report (the file at `report_path`) into reconcile's parse shape: one `## High-Impact Findings` section; per finding a `### [<Label>] <file:line>` heading from its Label line (no Label line: the bold label opening the block; a trailing `_(carried from round <N>)_` kept as its own group) and the bare `file:line` prefix of its Location line, a `_(pre-existing)_` annotation kept as its own group (verify's combined `_(pre-existing; newly reachable via ...)_` splits into `_(pre-existing)_ _(newly reachable via ...)_`), and its Issue as the `Issue:` line. A prior finding whose path is absent from the name-status is projected with `_(pre-existing)_`, so an `Unverified` or one-hop finding in an untouched file is never closed as `Addressed` without being read. Then Use skill: `review-prior-findings-reconcile` with that projection, the diff, `git diff --name-status <base_ref>...<head_ref>`, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files` when the name-status has a `D`. An audit, or any round whose prior checkpoint's `base_sha` equals its `head_sha` (an audit or trunk run), builds the comparison table directly - never call reconcile, which would mark every finding in an untouched file `Addressed`. Its rows: re-derived -> `Still open`, site read and smell absent -> `Addressed`, file gone or a `[Praise]` row -> `Obsolete`, site not reached -> `Needs re-check`. `Still open` and `Needs re-check` rows carry into their prior tier at their prior label, marked `_(carried from round <N>)_` (`<N>` = the round the finding was first raised; a finding already carrying the group keeps it, never a second), each republishing its prior block with the prior Location annotation kept (it skips verify, so the annotation is not re-derived), and into Next Steps; a finding this round re-derives publishes once. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and publishes as `[Must]` when it was `[Blocker]`, `[High]`, or `[Critical]`, else `[Recommend]`.

### Step 11 - Write Report

**Subagent mode:** write no file. Return exactly `## Findings` (the tier sections and complete finding blocks: Label, Location, Issue, Attack scenario - the parent folds it into Issue - and Fix, plus `Impact` and `System Risk` on every `[Must]`), then `## Next Steps`, then one trailing line `Coverage: <what you read>`, which the parent puts in a Notes bullet. No Summary, `OWASP Sweep`, `Prior Round Reconciliation`, or `Recommendations`.

Standalone: Use skill: `review-report-writer` with `report_type: review-security`, `report_body`, `branch` (the handle's `head_short_name`; an audit's assembled `branch`), `base_ref` / `head_ref` as the handle emitted them (audit: `HEAD`), `base_sha` / `head_sha` and `round` / `prior_head_sha` from the Step 3 round gate, `mode: full`, `scope: +sec`, `depth` as run (audits pass `deep`), `stack = java-spring-boot`, and `pr_url` when the request carried a PR URL, else `prior_checkpoint.pr_url` when present. Emit the report body in chat, then the writer's confirmation line.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown; never wrap the whole report in a code fence. Every italic line, brace annotation, bracketed placeholder, and enum listing inside the fence is a fill rule addressed to you, not content: act on it, never print it.

**Severity assignment:** Critical = exploitable now for auth/authz bypass or data compromise (IDOR, matcher-order bypass, client-declared owner id, inert method security that was the only role gate, injection on a reachable path, unauthenticated `heapdump`, MD5 password hashing). High = exploitable with preconditions or exposes sensitive internals (partially validated JWT - signature and expiry but not issuer or audience, committed credential, credentialed any-origin CORS with cookie sessions (Medium on a bearer-only API), a pinned dependency with a named reachable CVE, open redirect, missing rate limiting on an auth or mail-sending endpoint, a security test weakened to pass). Medium = defense-in-depth gap with no direct exploit path (missing `@PreAuthorize` behind a correct matcher, undocumented `csrf(AbstractHttpConfigurer::disable)` rationale, secret-bearing token stored unhashed). Low = hardening polish (headers, cookie flags on non-sensitive paths, a pin below the managed version with no named advisory). A control the contract advertises but no code performs (a `currentPassword` or OTP field nothing verifies) is High. Labels: Critical/High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when it sits on an endpoint that accepts unauthenticated requests; a Medium build-file or config-only gap stays `[Recommend]`. Low -> `[Recommend]`.

Headings are severity tiers; a finding stays in its tier after verify changes its label. The Label line carries the verified Label (the severity mapping only where verify did not run); Next Steps copies each finding's Label line, never re-derives it. Overall counts tiers. The Label line holds only the label and the carried marker; any other annotation goes on the Location line, which on an audit carries only `_(unverified: <reason>)_`.

```markdown
## Spring Boot Security Review Summary

- **Stack Detected:** Java <version> / Spring Boot <version> _(append `- below the floor (<Boot 3.x | Java < 21>)` when either is, and `- past OSS end` when the spring.io support table says so)_
- **Auth:** <securityMatcher, or catch-all>: <Form Login | HTTP Basic | OAuth2 Resource Server (JWT) | OAuth2 Client | Custom | none>{; the next chain in the same form}
- **Authorization:** SecurityFilterChain matchers | @PreAuthorize / @PostAuthorize | both | Custom _(append `- annotations present but inert` when method security is not enabled)_
- **Coverage:** <what was read; on a diff review, "diff and the security surface it touches"; on an audit, which chains and controllers were read in full and which were not>
- **Round:** <N>   {round 2+ only}
- **Overall Posture:** Clean | Issues Found - [<C> Critical / <H> High / <M> Medium / <L> Low]
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}   {diff review}
- **Findings verified:** <N> confirmed, <U> unverified, <K> dropped - inline (no diff)   {audit, instead}

[2-3 sentence assessment; call out Spring-specific risks like inert method security, a `WebSecurityConfigurerAdapter` leftover, or exposed Actuator.]

## Findings

### Critical

1. **Label:** [Must] | [Recommend]{ _(carried from round <N>)_}

   **Location:** [file:line; `file#member` when the supplied diff has no hunk headers]{ the verify Annotation verbatim}

   **Issue:** [vulnerability in Spring terms - e.g., "`@RequestBody` binds entity directly in OrderController#update, allowing mass assignment of `ownerId`"]

   **Attack scenario:** [how the attacker exploits this]

   **Impact:** [what the attacker gains or the user loses]

   **System Risk:** [required on every `[Must]`: why this is system-level rather than a local bug]

   **Fix:** [specific Spring remediation with code]

### High

[Same block; `Impact` and `System Risk` optional on `[Recommend]`; numbering continues across tiers]

### Medium

[Same block]

### Low

[Same block]

_Omit empty severity sections._

## Prior Round Reconciliation   {round 2+ standalone only}

[table, note line and tally from `review-prior-findings-reconcile`; when Step 10 built it instead, its comparison table]

## OWASP Sweep

One line per A01-A10 row plus one each for open redirect, SSTI, XSS, and SPA CSRF. Each carries exactly one verdict; A06 alone may pair two (`Findings <n>; Control absent - <control>`):

- `Finding <n>` (or `Findings <n>, <m>`) - the findings above that cover it, an absent control on an exploitable surface included
- `No issues found` - the relevant construct is present in scope and was checked clean
- `Control absent - <control>` - the risk surface exists and its control is not in the repo, with no exploit path from code alone (no CI dependency-CVE gate); also a Recommendations entry
- `Not in scope for this diff` - the diff contains no such construct (diff reviews only)
- `Not applicable - <construct absent>` - the service has no such construct at all (no deserialization, no outbound HTTP client, no SPA)
- `Not assessable - <reason>` - the evidence needed is outside what a code review can see

Rows sharing one verdict may be collapsed onto a single line (`A03, A08: Not applicable - no dynamic SQL, no deserialization`).

## Recommendations

[Prioritized hardening not tied to a specific finding]

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: dependencies] - [one-line action]

_Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting, dep upgrade, threat-model). Order Must > Recommend. Omit if no security issues._
```

## Self-Check

- [ ] Step 1 - behavioral principles loaded
- [ ] Step 2 - stack confirmed Spring Boot (else delegated out); Boot and Java versions read from the build file; every cited construct and fix binds on them (Security 6.x holdovers deprecated, not removed)
- [ ] Step 3 - standalone: `report_type: review-security` passed or audit fields assembled; round decided before any surface read, or the stop line printed; diff and log read once
- [ ] Step 4 - security surface read (filter chains in matcher order, JWT converter/decoder beans, and config in full, changed controllers, method-security enablement, build deps and pinned versions, modified tests); prior revision consulted when annotations or matchers were removed and the prior revision was reachable
- [ ] Step 5 - `spring-security-patterns` consulted
- [ ] Step 6 - auth rows run for the mechanism actually in use, JWT authorities mapping included; inapplicable rows treated as N/A, not findings
- [ ] Step 7 - authorization drift sweep complete, judging what each rule permits rather than that a rule exists; matcher-less catch-all chain checked
- [ ] Step 8 - Bean Validation on every `@RequestBody`; no entity as input or output DTO; declared-but-unread controls checked; file-upload / process-execution rows where applicable
- [ ] Step 9 - standalone: every sweep row carries exactly one enum verdict; subagent: run as a checklist, no sweep returned
- [ ] Step 10 - standalone: `review-finding-verify` ran inline (claim-confirmation only on an audit) and filled the tally; round 2+: prior findings projected and reconciled (audit, or an audit or trunk-run prior: comparison table, no reconcile call); subagent: skipped
- [ ] Step 11 - standalone: report written via `review-report-writer` with every field from the round gate, confirmation printed; subagent: findings, Next Steps, and the coverage line returned, no file written
- [ ] Every finding sits in its severity tier and carries an attack scenario, a concrete Spring fix, and its verified Label; every `[Must]` carries Impact and System Risk
- [ ] Next Steps tagged `[Implement]` / `[Delegate]` and ordered Must > Recommend
- [ ] Coverage stated honestly, including what a diff review did not read and what an audit did not reach

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git
- Vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `{\"role\":\"ADMIN\"}` and gains admin via mass assignment")
- Generic advice when a Spring idiom applies (say "add `@PreAuthorize(\"hasRole('ADMIN')\")`", not "add an authorization check")
- Suggesting `csrf(AbstractHttpConfigurer::disable)` to fix a failing form test - send a CSRF token instead
- Recommending a downgrade from a Spring Security default (`changeSessionId`, `show-values: NEVER`) because a checklist names the older setting
- Widening `@PreAuthorize` (e.g., `hasRole('ADMIN')` to `permitAll`) without an explicit security note
- Conflating security with perf or general review
