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

**Not for:** performance (`task-code-review-perf`), general review (`task-code-review`).

## Invocation

| Invocation                              | Meaning                                                |
| --------------------------------------- | ------------------------------------------------------ |
| `/task-spring-review-security`          | Current branch vs base; on trunk, routes to the audit path below |
| `/task-spring-review-security <branch>` | `<branch>` vs base (3-dot diff)                        |
| `/task-spring-review-security pr-<N>`   | PR head fetched into `pr-<N>` (user runs fetch first)  |

**Whole-service audit** (pre-deployment hardening, pen-test prep, or drift sweep with no feature branch): when Step 3 fails fast on trunk, do not stop - skip the diff gate and run every remaining step, Step 4 onward, against the full security surface at `HEAD`. No diff scoping; findings cite current code. `branch` = the current branch name, `base_ref` = `head_ref` = `HEAD`, `base_sha` = `head_sha` = `git rev-parse HEAD`.

Audits are unbounded by nature, so bound them by exposure: every `SecurityFilterChain` and every internet-reachable controller in full, then authenticated controllers, then internal ones. State in the Summary's `Coverage` field what you read and what you did not - a truncated audit that says so is useful; one that reads as complete is not.

When invoked as a subagent, the parent passes the precondition handle plus pre-read diff and commit log; Step 3 is skipped.

**Depth:** `standard` (default) scopes Steps 4-9 to the diff. `deep` (user-passed or parent-promoted) additionally runs the audit-scope pass over the full security surface. The whole-service audit path is `deep` by nature.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed stack from a parent. If not Spring Boot (standalone only): stop and tell the user to invoke `/task-code-review-security`; as a subagent, return the mismatch to the parent instead.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent. On fail-fast on trunk, switch to the whole-service audit path; on any other fail-fast, surface the message verbatim and stop. No state-changing git.

### Step 4 - Read the Security Surface

- Every `SecurityFilterChain` `@Bean` - read matchers top-to-bottom. A broad `permitAll` placed above a narrower authenticated rule shadows it and is a real vulnerability; a narrow allowlist above a trailing `anyRequest().authenticated()` is the correct shape, not a finding
- Every changed `@RestController` / `@Controller` - `@RequestBody` types (entity vs DTO), `@PreAuthorize` / `@PostAuthorize` added or removed, and whether `@EnableMethodSecurity` is anywhere in the application context (without it, every `@PreAuthorize` in the codebase is inert)
- `application.yml` and per-profile - `management.endpoints.web.exposure.include`, `spring.security.*`, `server.servlet.session.*`, `server.ssl.*`
- `build.gradle(.kts)` / `pom.xml` - `spring-boot-starter-security`, `spring-boot-starter-oauth2-resource-server`, `spring-boot-devtools` (must be `developmentOnly` / `runtime optional`)
- Modified tests - a green test obtained by disabling security, removing `@PreAuthorize`, or swapping an authenticated request for an anonymous one is a finding, not a fix

When the diff removes a security annotation or relaxes a matcher, consult the prior revision via `git log -p` to confirm what was protected before. When the prior revision is unreachable (subagent mode, shallow clone, audit path), review the present state only and say so on the finding rather than asserting a regression you cannot see.

At `deep`, the bullets read repo-wide, bounded by the exposure order above. On the audit path there is no prior revision, so skip that check; a `deep` diff review still consults it.

### Step 5 - Apply Canonical Patterns

Use skill: `spring-security-patterns`. Where it and a checklist row below disagree on the current idiom, the atomic wins.

### Step 6 - Authentication

Run the rows that match the mechanism in use; a resource server issues no tokens and has no credential endpoint, so token-issuance and login rows are N/A there rather than findings.

- [ ] **`SecurityFilterChain` explicit and current** - `WebSecurityConfigurerAdapter` removed in 6.x; flag 5.x migrations
- [ ] **OAuth2 Resource Server** - `issuer-uri` (or `jwk-set-uri`) configured, with `spring.security.oauth2.resourceserver.jwt.audiences` set so audience is actually validated; a `JwtAuthenticationConverter` only where claim mapping needs code
- [ ] **JWT validation** - issuer and audience verified, not just signature and expiry; HMAC secret never falls back to a hardcoded default. `NimbusJwtDecoder` cannot be configured to accept `alg: none`, so do not raise that against a Boot resource server - it is a concern for hand-rolled jjwt/java-jwt decoding
- [ ] **Token and secret generation** - unguessable source. `UUID.randomUUID()` is v4 over `SecureRandom` and is not a weak-randomness finding; `Math.random()`, `new Random()`, timestamps, and sequential ids are
- [ ] **Refresh-token rotation** (authorization servers only) - short access-token life (5-15 min); refresh tokens revocable
- [ ] **Form / Basic login** - `BCryptPasswordEncoder` (its no-arg default strength of 10 meets the bar) or `Argon2PasswordEncoder`; `DaoAuthenticationProvider` + `UserDetailsService`; no `NoOpPasswordEncoder` outside tests
- [ ] **Session** - Spring Security 6 defaults `sessionFixation` to `changeSessionId()`, which is correct on Servlet 3.1+; flag only an explicit downgrade. Cookies `Secure`, `HttpOnly`, `SameSite=Lax|Strict`
- [ ] **Brute-force protection** - rate limiting on any endpoint that verifies a credential or sends outbound mail/SMS: `/login`, token endpoints, password reset, email change, MFA challenge
- [ ] **No credentials in committed config** - env vars, Vault, AWS Secrets Manager, Spring Cloud Config

### Step 7 - Authorization

- [ ] **`@EnableMethodSecurity` active** - present-but-inert `@PreAuthorize` is an authorization bypass, not a defense-in-depth gap; severity follows what the annotations were the only gate for
- [ ] **Drift sweep** - every new or modified endpoint is covered by a matcher or `@PreAuthorize`, **and the rule is right for the endpoint**: a `permitAll` matcher satisfies "has a rule" while authorizing nothing, so state what the rule permits, not that one exists
- [ ] **IDOR** - lookups scope through the principal (`findByIdAndOwnerId(id, principalId)`), not `findById(id)` + post-hoc check; an owner id accepted from the request body or a query parameter is client-declared and cannot authorize
- [ ] **Per-element filtering** - collection returns use `@PostFilter` or filter at the query layer
- [ ] **Tenant isolation** - queries scope by `tenantId` at repository layer (Hibernate `@Filter`, `@TenantId`, or query parameter)
- [ ] **Default-deny** - `.anyRequest().authenticated()` closes the chain after the explicit allowlist; no trailing `.permitAll()`
- [ ] **CSRF** - enabled for stateful sessions; `csrf().disable()` only for stateless JWT APIs with documented rationale
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

Cover each row and report a verdict for each; never silently drop one. Results land in the Output Format's `OWASP Sweep` section, whose enum has four values - use the one that is true rather than overclaiming. In subagent mode the sweep is a discovery checklist rather than an artifact: run it, publish whatever it surfaces as findings, and return no sweep section.

**A diff review scopes every claim to the diff and the security surface it touches.** A finding asserting that a control is *absent* - no rate limiting, no `@EnableMethodSecurity`, no matcher - is a service-wide claim, so raise it only when you actually read the surface that would hold it. Otherwise carry it as `Not assessable - <what you could not read>` on the sweep row, or state the limit inline on the finding. Service-wide claims made without service-wide reading belong to audit mode / `deep`.

| Risk                          | Spring-specific check                                                                                                                                |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control (A01)   | Steps 6-7 satisfied; no implicit `permitAll`; method security actually enabled                                                                        |
| Cryptographic Failures (A02)  | `BCryptPasswordEncoder` / `Argon2PasswordEncoder` for passwords; no `MD5`/`SHA-1` for auth; secret-bearing tokens stored hashed; TLS via `server.ssl.*` or upstream LB; HSTS |
| Injection (A03)               | Derived queries or `@Query` with named params; no string concat in JPQL, native SQL, or `EntityManager.createNativeQuery`; `Sort.by(field)` validated against an allowlist |
| Insecure Design (A04)         | `@EnableMethodSecurity` on; default-deny matcher chain; declared controls actually wired                                                              |
| Security Misconfiguration (A05) | Actuator exposure minimal in prod; `heapdump` and `threaddump` never reachable unauthenticated. `/actuator/env` masks values by default since Boot 3 (`show-values: NEVER`), so an exposed `env` leaks the property and config-source inventory rather than the secrets themselves - write the accurate impact. DevTools `developmentOnly`. H2 console disabled outside dev |
| Vulnerable Components (A06)   | A dependency-CVE gate exists in CI (OWASP dependency-check, Snyk, GitHub Dependabot alerts) and is enforced. A review does not run the project's build - report whether the gate is configured, and mark the row `Not assessable` when the scan output is not in front of you |
| Auth Failures (A07)           | Step 6 satisfied; rate limiting on credential-verifying and mail-sending endpoints                                                                    |
| Data Integrity (A08)          | No `ObjectInputStream.readObject` on untrusted input; Jackson default-typing off; SnakeYAML `SafeConstructor`                                        |
| Logging & Monitoring (A09)    | Logback masks `password`, `token`, `creditCard`, `ssn`, `apiKey`; **and personal data** - email, phone, address, government id - is not logged in the clear; security events (login fail, `AccessDenied`) logged; no entity serialization in `log.info` |
| SSRF (A10)                    | `RestClient` / `WebClient` validate the target host against an allowlist and reject private ranges (`127.0.0.0/8`, `10/8`, `172.16/12`, `192.168/16`, `169.254/16`, `::1`). Resolve once, validate the resolved address, then connect to that address via a pinned resolver or custom socket factory - re-resolving at connect time is what opens the DNS-rebind window, not what closes it |

Then one row each for the Spring-specific extras: **open redirect** (`sendRedirect` on user input, allowlisted), **SSTI** (no Thymeleaf `${...}` on user-controlled template strings; SpEL never receives user input as an expression), **XSS** (no `th:utext` on user input), **SPA CSRF** (`CookieCsrfTokenRepository.withHttpOnlyFalse()`).

### Step 10 - Verify Findings

Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and inline provenance annotation.

Two carve-outs. **Subagent runs skip this** - the parent verifies the merged set once. **A whole-service audit has no diff**: run the claim-confirmation pass only and skip attribution and de-escalation, since every finding in an audit is untouched pre-existing code and de-escalating on that basis would strip `[Must]` from findings that are exploitable today. Record the tally as `inline (no diff)`.

### Step 11 - Write Report

**Subagent mode:** if invoked by `task-spring-review`, do not write a file. Return exactly these, and nothing else:

- `## Findings`, complete finding blocks. Every finding carries its label and citation; every `[Must]` also carries the `Impact` and `System Risk` lines the parent's report format requires.
- `## Next Steps`, which the parent merges.
- A single trailing line `Coverage: <what you read>` so the parent can size the claim - this replaces the Summary field, which subagents do not return.

Do not return the Summary block, `OWASP Sweep`, or `Recommendations`. Skip the rest of this step.

Standalone: use skill: `review-report-writer` with `report_type: review-security` and every field the writer requires - `report_body`, `branch`, `base_ref`, `head_ref`, `base_sha`, `head_sha`, `mode: full`, `scope: +sec`, `depth` as run (audits pass `deep`), `stack = java-spring-boot`, and `round` via your own lookup of `review-security-<branch>.md` with the writer's filename sanitization applied to `<branch>` - a branch containing `/` does not name a file, and `review-precondition-check` keys prior checkpoints to `review-<branch>.md`, a different report. Exists with valid frontmatter -> increment its `round` and pass its `head_sha` as `prior_head_sha`; else `round: 1`. Write the report file before ending; print confirmation.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown; never wrap the whole report in a code fence. Every italic line, bracketed placeholder, and enum listing inside the fence is a fill rule addressed to you, not content: act on it, never print it.

**Severity assignment:** Critical = exploitable now for auth/authz bypass or data compromise (IDOR, matcher-order bypass, client-declared owner id, inert method security that was the only role gate, injection on a reachable path, unauthenticated `heapdump`, MD5 password hashing). High = exploitable with preconditions or exposes sensitive internals (partially validated JWT - signature and expiry but not issuer or audience, committed credential, open redirect, missing rate limiting on an auth or mail-sending endpoint, a security test weakened to pass). Medium = defense-in-depth gap with no direct exploit path (missing `@PreAuthorize` behind a correct matcher, undocumented `csrf().disable()` rationale, secret-bearing token stored unhashed). Low = hardening polish (headers, cookie flags on non-sensitive paths). A control the contract advertises but no code performs - a `currentPassword` or OTP field nothing verifies - is High, not Medium: callers and reviewers both believe a step exists that does not. Labels: Critical/High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the finding sits on a surface an attacker can reach; a build-file or config-only gap with no reachable surface stays `[Recommend]`. Low -> `[Recommend]`.

```markdown
## Spring Boot Security Review Summary

- **Stack Detected:** Java <version> / Spring Boot <version>
- **Auth:** one line per `SecurityFilterChain`, naming its matcher and mechanism (Form Login | HTTP Basic | OAuth2 Resource Server (JWT) | OAuth2 Client | Custom | none)
- **Authorization:** SecurityFilterChain matchers | @PreAuthorize / @PostAuthorize | both | Custom _(append `- annotations present but inert` when `@EnableMethodSecurity` is absent)_
- **Coverage:** <what was read; on a diff review, "diff and the security surface it touches"; on an audit, which chains and controllers were read in full and which were not>
- **Overall Posture:** Clean | Issues Found - [<C> Critical / <H> High / <M> Medium / <L> Low]
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff) _(drop the parenthetical when K is 0. On an audit, attribution did not run: write `<N> confirmed, <K> dropped - inline (no diff)` and omit the reattributed count.)_

[2-3 sentence assessment; call out Spring-specific risks like inert method security, deprecated `WebSecurityConfigurerAdapter`, or exposed Actuator.]

## Findings

### Critical

1. **[Must]**

   **Location:** [file:line] _(carry verification's annotation verbatim: `_(pre-existing)_`, `_(pre-existing; newly reachable via <file:line>)_`, or `_(unverified: <reason>)_`; use `file#member` when the supplied diff has no hunk headers)_

   **Issue:** [vulnerability in Spring terms - e.g., "`@RequestBody` binds entity directly in OrderController#update, allowing mass assignment of `ownerId`"]

   **Attack scenario:** [how the attacker exploits this]

   **Impact:** [what the attacker gains or the user loses]

   **System Risk:** [required on every `[Must]`: why this is system-level rather than a local bug]

   **Fix:** [specific Spring remediation with code]

### High / Medium / Low

[Same numbered-block structure; `[Recommend]` on Medium and Low unless the escalation rule fires; `Impact` and `System Risk` optional below `[Must]`; numbering continues across tiers]

_Omit empty severity sections._

## OWASP Sweep

One line per A01-A10 row plus one each for open redirect, SSTI, XSS, and SPA CSRF. Each carries exactly one verdict:

- `Finding <n>` (or `Findings <n>, <m>`) - the findings above that cover it
- `No issues found` - the relevant construct is present in scope and was checked clean
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
- [ ] Step 2 - stack confirmed Spring Boot (else delegated out)
- [ ] Step 3 - precondition handle obtained, received from parent, or audit path taken on trunk; diff and commit log read once and reused where one exists
- [ ] Step 4 - security surface read (filter chains in matcher order, controllers, method-security enablement, config, build deps, modified tests); prior revision consulted when annotations or matchers were removed and the prior revision was reachable
- [ ] Step 5 - `spring-security-patterns` consulted
- [ ] Step 6 - auth rows run for the mechanism actually in use; inapplicable rows treated as N/A, not findings
- [ ] Step 7 - authorization drift sweep complete, judging what each rule permits rather than that a rule exists
- [ ] Step 8 - Bean Validation on every `@RequestBody`; no entity as input or output DTO; declared-but-unread controls checked; file-upload / process-execution rows where applicable
- [ ] Step 9 - every sweep row carries one of the four verdicts
- [ ] Step 10 - `review-finding-verify` ran with the correct carve-out (skipped as subagent; claim-confirmation only on an audit); tally recorded in Summary when a Summary is produced
- [ ] Step 11 - standalone: report written via `review-report-writer` with every required field and a sanitized round-lookup filename, confirmation printed; subagent: findings, Next Steps, and the coverage line returned, no file written
- [ ] Every finding includes an attack scenario, a concrete Spring fix, and exactly one label; every `[Must]` carries Impact and System Risk
- [ ] Next Steps tagged `[Implement]` / `[Delegate]` and ordered Must > Recommend
- [ ] Coverage stated honestly, including what a diff review did not read and what an audit did not reach

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git
- Vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `{\"role\":\"ADMIN\"}` and gains admin via mass assignment")
- Writing `No issues found` for a construct the diff does not contain - that is `Not in scope`, and the difference is what makes the sweep trustworthy
- Generic advice when a Spring idiom applies (say "add `@PreAuthorize(\"hasRole('ADMIN')\")`", not "add an authorization check")
- Suggesting `csrf().disable()` to fix a failing form test - send a CSRF token instead
- Recommending a downgrade from a Spring Security 6 default (`changeSessionId`, `show-values: NEVER`) because a checklist names the older setting
- Recommending `WebSecurityConfigurerAdapter` (removed in 6.x) - use `SecurityFilterChain`
- Widening `@PreAuthorize` (e.g., `hasRole('ADMIN')` to `permitAll`) without an explicit security note
- Conflating security with perf or general review
