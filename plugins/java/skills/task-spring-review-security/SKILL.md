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

**Not for:** performance (`task-code-review-perf`), general review (`task-code-review`), incident triage (`/task-oncall-start`).

## Invocation

| Invocation                              | Meaning                                                |
| --------------------------------------- | ------------------------------------------------------ |
| `/task-spring-review-security`          | Current branch vs base; fails fast on trunk            |
| `/task-spring-review-security <branch>` | `<branch>` vs base (3-dot diff)                        |
| `/task-spring-review-security pr-<N>`   | PR head fetched into `pr-<N>` (user runs fetch first)  |

**Whole-service audit** (pre-deployment hardening, pen-test prep, or drift sweep with no feature branch): when Step 3 fails fast on trunk, do not stop - skip the diff gate and run Steps 4-9 against the full security surface at `HEAD` (no diff scoping; findings cite current code).

When invoked as a subagent, the parent passes the precondition handle plus pre-read diff and commit log; Step 3 is skipped.

**Depth:** `standard` (default) scopes Steps 4-9 to the diff. `deep` (user-passed or parent-promoted) additionally runs the audit-scope pass over the full security surface - audit-grade coverage on top of the diff review. The whole-service audit path is `deep` by nature.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed stack from a parent. If not Spring Boot (standalone only): stop and tell the user to invoke `/task-code-review-security`; as a subagent, return the mismatch to the parent instead.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent. On fail-fast on trunk, switch to the whole-service audit path (Invocation section); on any other fail-fast, surface the message verbatim and stop. No state-changing git.

### Step 4 - Read the Security Surface

- Every `SecurityFilterChain` `@Bean` - read matchers top-to-bottom; a `permitAll` ordered before an authenticated rule is a real vulnerability
- Every changed `@RestController` / `@Controller` - `@RequestBody` types (entity vs DTO), `@PreAuthorize` / `@PostAuthorize` added or removed
- `application.yml` and per-profile - `management.endpoints.web.exposure.include`, `spring.security.*`, `server.servlet.session.*`, `server.ssl.*`
- `build.gradle(.kts)` / `pom.xml` - `spring-boot-starter-security`, `spring-boot-starter-oauth2-resource-server`, `spring-boot-devtools` (must be `developmentOnly` / `runtime optional`)
- Modified tests - a green test obtained by disabling security or removing `@PreAuthorize` is a finding, not a fix

When the diff removes a security annotation or relaxes a matcher, consult the prior revision via `git log -p` to confirm what was protected before.

Audit mode / `deep`: the bullets read repo-wide - every `SecurityFilterChain`, every controller, the full test suite and config; skip the prior-revision check (no diff to compare).

### Step 5 - Apply Canonical Patterns

Use skill: `spring-security-patterns`.

### Step 6 - Authentication

- [ ] **`SecurityFilterChain` explicit and current** - `WebSecurityConfigurerAdapter` removed in 6.x; flag 5.x migrations
- [ ] **OAuth2 Resource Server** - `oauth2ResourceServer().jwt()` with explicit `JwtDecoder`; signature algorithm pinned; `JwtAuthenticationConverter` maps claims consistently
- [ ] **JWT validation** - issuer and audience verified (`JwtValidators.createDefaultWithIssuer` + custom audience validator); decoder rejects `alg: none`; HMAC secret never falls back to a hardcoded default
- [ ] **Refresh-token rotation** - short access-token life (5-15 min); refresh tokens revocable
- [ ] **Form / Basic login** - `BCryptPasswordEncoder` strength >=10; `DaoAuthenticationProvider` + `UserDetailsService`; no `NoOpPasswordEncoder` outside tests
- [ ] **Session** - `sessionFixation().migrateSession()`; cookies `Secure`, `HttpOnly`, `SameSite=Lax|Strict`
- [ ] **Brute-force protection** - Bucket4j / Resilience4j on `/login`, `/oauth/token`, password reset
- [ ] **No credentials in committed config** - env vars, Vault, AWS Secrets Manager, Spring Cloud Config

### Step 7 - Authorization

- [ ] **`@EnableMethodSecurity`** active; `@PreAuthorize` on every service method touching user-owned resources (defense-in-depth alongside matchers)
- [ ] **Drift sweep** - every new endpoint has a matcher or `@PreAuthorize` (or explicit `permitAll` with rationale)
- [ ] **IDOR** - lookups scope through the principal (`findByIdAndOwnerId(id, principalId)`), not `findById(id)` + post-hoc check
- [ ] **Per-element filtering** - collection returns use `@PostFilter` or filter at the query layer
- [ ] **Tenant isolation** - queries scope by `tenantId` at repository layer (Hibernate `@Filter`, `@TenantId`, or query parameter)
- [ ] **Default-deny** - `.anyRequest().authenticated()` after the explicit allowlist; no trailing `.permitAll()`
- [ ] **CSRF** - enabled for stateful sessions; `csrf().disable()` only for stateless JWT APIs with documented rationale
- [ ] **CORS** - `CorsConfigurationSource` with explicit origins (never `*` for credentialed); minimal methods/headers

### Step 8 - Input Validation and Mass Assignment

- [ ] **Bean Validation** on every `@RequestBody` DTO (`@NotNull`, `@Size`, `@Email`, `@Pattern`); `@Valid` on the controller parameter
- [ ] **Records / immutable DTOs** for input - Jackson uses the constructor, defeating mass-assignment
- [ ] **No entities as `@RequestBody`** - always a DTO/record; Jackson on a JPA entity populates fields the API never intended

  ```java
  // bad: attacker submits {"role":"ADMIN"} and is promoted
  void update(@RequestBody User user) { repo.save(user); }
  // good
  void update(@Valid @RequestBody UserUpdateRequest req) { ... }
  ```

- [ ] **No privilege-bearing fields in user-facing DTOs** - `role`, `admin`, `ownerId`, `userId`, `tenantId`, `status`. Admin-only paths use a separate DTO and `@PreAuthorize("hasRole('ADMIN')")`
- [ ] **Separate response DTOs** strip `passwordHash`, `mfaSecret`, `apiKeyHash`, `resetToken`. `@JsonIgnore` on entity fields is brittle - rename or accidental removal silently re-exposes
- [ ] **Password change** validates current password before applying new; rate-limited per user
- [ ] **File uploads** (`MultipartFile`):
  - Content-based type detection (Apache Tika), not `getContentType()` or extension
  - Size limit (`spring.servlet.multipart.max-file-size`)
  - Stored outside webroot; `Content-Disposition: attachment` to block inline HTML/SVG
  - Filename via `Path.resolve(name).normalize()` + `startsWith(baseDir)`
- [ ] **Process execution** - no `Runtime.exec` / `ProcessBuilder` with interpolated input; allowlist + tokenized arguments

### Step 9 - Spring-Specific OWASP Sweep

Cover each category. State "No issues found" per category that is clean - never silently skip. Diff reviews scope every claim to the diff and the security surface it touches; service-wide claims belong to audit mode / `deep` only. Results land in the Output Format's `OWASP Sweep` section.

| Risk                          | Spring-specific check                                                                                                                                |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control (A01)   | Steps 6-7 satisfied; no implicit `permitAll`                                                                                                         |
| Cryptographic Failures (A02)  | `BCryptPasswordEncoder` / `Argon2PasswordEncoder` for passwords; no `MD5`/`SHA-1` for auth; TLS via `server.ssl.*` or upstream LB; HSTS              |
| Injection (A03)               | Derived queries or `@Query` with named params; no string concat in JPQL / native SQL; `Sort.by(field)` validated against allowlist                   |
| Insecure Design (A04)         | `@EnableMethodSecurity` on; default-deny matcher chain                                                                                               |
| Security Misconfiguration (A05) | Actuator: only `info`, `health` (or behind `ROLE_ACTUATOR`) in prod; `env`, `heapdump`, `loggers`, `mappings` never public. DevTools `developmentOnly`. H2 console disabled outside dev |
| Vulnerable Components (A06)   | `./gradlew dependencyCheckAnalyze` clean; Spring4Shell-class CVEs - `DataBinder` not bound to `Class` / `ClassLoader`                                |
| Auth Failures (A07)           | Step 6 satisfied; brute-force protection on auth endpoints                                                                                           |
| Data Integrity (A08)          | No `ObjectInputStream.readObject` on untrusted input; Jackson default-typing off; SnakeYAML `SafeConstructor`                                        |
| Logging & Monitoring (A09)    | Logback masks `password`, `token`, `creditCard`, `ssn`, `apiKey`; security events (login fail, `AccessDenied`) logged; no entity serialization in `log.info` |
| SSRF (A10)                    | `RestClient` / `WebClient` validate hostnames against allowlist; reject private ranges (`127.0.0.0/8`, `10/8`, `172.16/12`, `192.168/16`, `169.254/16`, `::1`) after resolution; re-resolve before connect (DNS-rebind) |

Plus Spring-specific: open redirect (`response.sendRedirect(userInput)` allowlisted), SSTI (no Thymeleaf `${...}` on user-controlled template strings; SpEL never receives user input as expression), XSS (no `th:utext` on user input), CSRF token on SPAs via `CookieCsrfTokenRepository.withHttpOnlyFalse()`.

### Step 10 - Write Report

**Subagent mode:** if invoked by `task-spring-review`, do not write a file - return the findings in this skill's Output Format for the parent to merge (the parent owns the report; `review-report-writer` rejects subagent writes and the parent passes no checkpoint fields). Skip the rest of this step.

Standalone: use skill: `review-report-writer` with `report_type: review-security` and these inputs: `branch`, `base_ref`, `base_sha`/`head_sha` (`git rev-parse` the refs Step 3 resolved; whole-service audit: both = `HEAD`), `scope: +sec`, `depth` as run (`standard` | `deep` - see Invocation; audits pass `deep`), `stack = java-spring-boot`, and `mode`/`round` via your own lookup of `review-security-<branch>.md` (`review-precondition-check` keys prior checkpoints to `review-<branch>.md`, so its lookup never finds this report): exists with valid frontmatter -> increment its `round` and pass its `head_sha` as `prior_head_sha`; else `mode: full`, `round: 1`. Write to the report file before ending; print confirmation.

## Self-Check

- [ ] Step 1 - behavioral principles loaded
- [ ] Step 2 - stack confirmed Spring Boot (else delegated out)
- [ ] Step 3 - precondition handle obtained (or received from parent, or audit path taken on trunk); diff and commit log read once and reused
- [ ] Step 4 - security surface read (filter chain, controllers, config, build deps, modified tests); prior revision consulted when annotations / matchers were removed
- [ ] Step 5 - `spring-security-patterns` consulted
- [ ] Step 6 - auth checks run for the mechanism in use (form / OAuth2 / JWT)
- [ ] Step 7 - authorization drift sweep complete; every new endpoint has a matcher or `@PreAuthorize`
- [ ] Step 8 - Bean Validation on every `@RequestBody`; no entity as input DTO; file-upload / process-execution checks where applicable
- [ ] Step 9 - every OWASP row addressed in the OWASP Sweep section; clean categories explicitly marked "No issues found"
- [ ] Step 10 - standalone: report written via `review-report-writer`, confirmation printed; subagent: findings returned to parent, no file written
- [ ] Every finding includes an attack scenario and a concrete Spring fix
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Must > Recommend > Question (omit if none)

## Output Format

**Severity assignment:** Critical = exploitable now for auth/authz bypass or data compromise (IDOR, matcher-order bypass, unvalidated JWT, injection on a reachable path, MD5 password hashing). High = exploitable with preconditions or exposes sensitive internals (public `heapdump`/`env`, open redirect, missing brute-force protection on auth endpoints). Medium = defense-in-depth gap with no direct exploit path (missing `@PreAuthorize` behind a correct matcher, undocumented `csrf().disable()` rationale). Low = hardening polish (headers, cookie flags on non-sensitive paths). Intent labels follow severity: Critical/High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one line on an exposed path; Low -> `[Recommend]` or `[Question]`.

```markdown
## Spring Boot Security Review Summary

**Stack Detected:** Java <version> / Spring Boot <version>
**Auth:** Spring Security Form Login | OAuth2 Resource Server (JWT) | OAuth2 Client | Custom | Hybrid
**Authorization:** SecurityFilterChain matchers | @PreAuthorize / @PostAuthorize | Custom
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment; call out Spring-specific risks like missing `@PreAuthorize`, deprecated `WebSecurityConfigurerAdapter`, or exposed Actuator.]

## Findings

### Critical

1. **Location:** [file:line]
   **Issue:** [vulnerability in Spring terms - e.g., "`@RequestBody` binds entity directly in OrderController#update, allowing mass assignment of `ownerId`"]
   **Attack scenario:** [how the attacker exploits this]
   **Fix:** [specific Spring remediation with code]

### High / Medium / Low
[Same numbered-block structure; numbering continues across tiers]

_Omit empty severity sections. If all omitted, state "No security issues found."_

## OWASP Sweep

- A01 Broken Access Control: [Finding <n> | No issues found]
- ... [one line per Step 9 table row A01-A10, plus one for the Spring-specific extras (open redirect / SSTI / XSS / SPA CSRF)]

## Recommendations

[Prioritized hardening not tied to a specific finding]

## Next Steps

Prioritized, each tagged `[Implement]` (localized) or `[Delegate]` (cross-cutting, dep upgrade, threat-model). Order: Must > Recommend > Question.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: dependencies] - [one-line action]

_Omit if no security issues._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git
- Vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `{\"role\":\"ADMIN\"}` and gains admin via mass assignment")
- Silently skipping clean OWASP categories - state "No issues found" per category
- Generic advice when a Spring idiom applies (say "add `@PreAuthorize(\"hasRole('ADMIN')\")`", not "add an authorization check")
- Suggesting `csrf().disable()` to fix a failing form test - send a CSRF token instead
- Disabling `@EnableMethodSecurity` or removing `@PreAuthorize` to silence warnings
- Recommending `WebSecurityConfigurerAdapter` (removed in 6.x) - use `SecurityFilterChain`
- Widening `@PreAuthorize` (e.g., `hasRole('ADMIN')` to `permitAll`) without an explicit security note
- Conflating security with perf or general review
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
