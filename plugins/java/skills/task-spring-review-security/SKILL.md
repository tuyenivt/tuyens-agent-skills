---
name: task-spring-review-security
description: "Spring Boot security review: Spring Security 6 SecurityFilterChain, OAuth2/JWT, @PreAuthorize, Bean Validation, CSRF, OWASP Top 10."
agent: java-security-engineer
metadata:
  category: backend
  tags: [java, spring-boot, security, spring-security, oauth2, jwt, owasp, workflow]
  type: workflow
user-invocable: true
---

# Spring Boot Security Review

Spring-aware security review naming Spring Security 6.x `SecurityFilterChain`, OAuth2 Resource Server, JWT, method security, Bean Validation, and Spring Security Crypto idioms directly. Findings include an attack scenario and a concrete Spring remediation.

Stack-specific delegate of `task-code-review-security` for Java / Spring Boot.

## When to Use

- Spring Boot PR for security regressions
- Pre-deployment hardening on auth, authz, file upload, payment, PII paths
- Validation / method-security drift sweep across controllers
- Auditing an OAuth2 / JWT flow or new `@PreAuthorize`

**Not for:**
- Performance (`task-code-review-perf` or Spring delegate)
- General review (`task-code-review`)
- Incident triage (`/task-oncall-start`)

## Invocation

| Invocation                              | Meaning                                                         |
| --------------------------------------- | --------------------------------------------------------------- |
| `/task-spring-review-security`          | Current branch vs base; fails fast on trunk                     |
| `/task-spring-review-security <branch>` | `<branch>` vs base (3-dot diff)                                 |
| `/task-spring-review-security pr-<N>`   | PR head fetched into `pr-<N>` (user runs fetch first)           |

When invoked as a subagent, the parent passes the precondition handle + pre-read diff and commit log; Step 3 below is skipped.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed stack from a parent. If not Spring Boot, stop and tell the user to invoke `/task-code-review-security`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent.

If precondition check stops with a fail-fast message, surface verbatim and stop. No state-changing git.

### Step 4 - Read the Security Surface

- Every `SecurityFilterChain` `@Bean` (typically `SecurityConfig.java`). **Read the matcher chain top-to-bottom** - matcher order matters; a misordered `permitAll` ahead of an authenticated rule is a real vulnerability
- Every changed `@RestController` / `@Controller` - `@RequestBody` types (entity vs DTO), `@PreAuthorize` / `@PostAuthorize` annotations added or removed
- `application.yml` and per-profile - `management.endpoints.web.exposure.include`, `spring.security.*`, `server.servlet.session.*`, `server.ssl.*`
- `build.gradle(.kts)` / `pom.xml` - `spring-boot-starter-security`, `spring-boot-starter-oauth2-resource-server`, `spring-boot-devtools` (must be `developmentOnly` / `runtime optional`)
- Modified tests - a green test obtained by disabling security or removing `@PreAuthorize` is a finding, not a fix

When the diff removes a security annotation or relaxes a matcher, `git log -p` the prior revision to confirm what was protected before - blame is the authoritative answer to "did this weaken authorization."

### Step 5 - OWASP Quick Check (Spring Lens)

Use skill: `spring-security-patterns` for canonical patterns.

| Risk                          | Spring-specific check                                                                                                                                                                                  |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Broken Access Control         | Every endpoint declares authorization via `SecurityFilterChain` matcher or `@PreAuthorize` / `@PostAuthorize`. No implicit `permitAll`.                                                                |
| Injection                     | Repository methods use derived queries or `@Query` with named parameters. No string concat in JPQL / native SQL. No `entityManager.createNativeQuery(... + userInput + ...)`.                          |
| Cryptographic Failures        | `BCryptPasswordEncoder` (or `Argon2PasswordEncoder`) for passwords; Jasypt / Vault for secrets at rest; no `MessageDigest.getInstance("MD5"/"SHA-1")` for auth.                                        |
| Security Misconfiguration     | `SecurityFilterChain` explicit (no reliance on Spring Boot 1.x defaults); HTTPS via `requiresChannel().requiresSecure()` or upstream LB; security headers via `HeadersConfigurer`.                     |
| SSRF                          | `RestClient` / `WebClient` validate hostnames against an allowlist before request; no `RestTemplate.exchange(URI.create(userInput), ...)`. Allowlist alone is insufficient when DNS resolves to private IPs - also reject `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16` (cloud metadata), `::1` after resolution; re-resolve before connect (DNS-rebind). |
| XSS                           | Thymeleaf auto-escapes - no `th:utext` on user input; no manual `Model.addAttribute(..., rawHtml)` rendered as `th:utext`. JSON responses set `Content-Type: application/json` to block sniff XSS.     |
| Insecure Design (A04)         | `@EnableMethodSecurity` enabled; default-deny via `authorizeHttpRequests().anyRequest().authenticated()`.                                                                                              |
| Vulnerable Components (A06)   | OWASP dep-check (`./gradlew dependencyCheckAnalyze`) clean; no entries with known CVEs.                                                                                                                |
| Data Integrity Failures (A08) | No `ObjectInputStream.readObject` on untrusted input; Jackson typed-deserialization disabled (`enableDefaultTyping` off); SnakeYAML uses `SafeConstructor`.                                            |
| Logging & Monitoring (A09)    | Logback excludes sensitive fields; `@JsonIgnore` on PII / secret fields; no `log.info("user={}", user)` serializing the entity. Security events (login fail, AccessDenied) logged.                      |

### Step 6 - Authentication

- [ ] **`SecurityFilterChain`** explicit and current - `WebSecurityConfigurerAdapter` does not exist (removed in 6.x); flag 5.x migrations
- [ ] **OAuth2 Resource Server** - `oauth2ResourceServer().jwt()` with explicit `JwtDecoder`; signature algorithm pinned; `JwtAuthenticationConverter` maps claims consistently
- [ ] **JWT issuer / audience validated** (`JwtValidators.createDefaultWithIssuer`, custom audience validator) - not just signature
- [ ] **JWT no `alg: none`** - decoder rejects unsigned tokens; HMAC secret never falls back to a hardcoded default
- [ ] **Refresh token rotation** - short access-token life (5-15 min); refresh tokens revocable; revocation list or JWT introspection at the gateway
- [ ] **Form / Basic login** - `BCryptPasswordEncoder` strength ≥10; `DaoAuthenticationProvider` with `UserDetailsService`; no `NoOpPasswordEncoder` outside tests
- [ ] **Session fixation** - `sessionFixation().migrateSession()` (Boot 3+ default); cookie `Secure`, `HttpOnly`, `SameSite=Lax|Strict`
- [ ] **Brute-force protection** - Bucket4j / Resilience4j on `/login`, `/oauth/token`, password reset
- [ ] **No credentials in committed config** - env vars, Vault, AWS Secrets Manager, Spring Cloud Config; `master.key`-equivalent gitignored
- [ ] **Actuator endpoints** - `management.endpoints.web.exposure.include` minimal in prod; remaining behind `ROLE_ACTUATOR`

### Step 7 - Authorization

Use skill: `spring-security-patterns`.

- [ ] **`@EnableMethodSecurity`** active; `@PreAuthorize` on every service method touching user-owned resources (defense-in-depth alongside controller matchers)
- [ ] **Authorization drift sweep** - every new controller endpoint has a matching matcher or `@PreAuthorize` (or explicit `permitAll` with rationale)
- [ ] **IDOR** - lookups scope through the principal (`findByIdAndOwnerId(id, principalId)`) rather than `findById(id)` + post-hoc check (leaks existence via 403 vs 404)
- [ ] **Per-element filtering** - collection returns use `@PostFilter` or filter at the query layer
- [ ] **Tenant isolation** - queries scope by `tenantId` at repository layer (Hibernate `@Filter`, `@TenantId`, or query parameter) - never controller-only
- [ ] **Default-deny** in `SecurityFilterChain` - `.anyRequest().authenticated()` after explicit allowlist; no trailing `.permitAll()`
- [ ] **CSRF** - enabled for stateful sessions; `csrf().disable()` only for stateless JWT APIs with documented rationale
- [ ] **CORS** - `CorsConfigurationSource` with explicit origins (never `*` for credentialed); minimal methods/headers

### Step 8 - Input Validation and Mass Assignment

- [ ] **Bean Validation** on every `@RequestBody` DTO (`@NotNull`, `@Size`, `@Email`, `@Pattern`); `@Valid` on the controller parameter
- [ ] **Records / immutable DTOs** for input - no setters; Jackson uses the constructor, defeating mass-assignment
- [ ] **No privilege-bearing fields in user-facing DTOs** - `role`, `admin`, `ownerId`, `userId`, `tenantId`, `accountId`, `approved`, `status` (state-machine controlled by server). If they appear in a `@RequestBody` record, require admin-only path with a separate DTO and `@PreAuthorize("hasRole('ADMIN')")`
- [ ] **No exposing entities as `@RequestBody`** - always a DTO/record; Jackson on a JPA entity can populate fields the API never intended
- [ ] **Response DTOs strip server-side sensitive fields** - a separate `UserResponse` record that does *not* contain `passwordHash`, `password`, `mfaSecret`, `apiKeyHash`, `resetToken`, internal audit fields, soft-delete flags. `@JsonIgnore` on entity fields is brittle - a field rename or accidental annotation removal silently re-exposes; a separate response record is the durable defense
- [ ] **Password change** - validates the *current* password before applying the new one (defeats session-hijack-then-change); minimum length / complexity at the DTO boundary; rate-limited per user; previous N hashes optionally retained
- [ ] **File uploads** (`MultipartFile`):
  - Content-based type detection (Apache Tika), not `getContentType()` or extension
  - Per-file and total size limit (`spring.servlet.multipart.max-file-size`)
  - Stored outside webroot; `Content-Disposition: attachment` to prevent inline rendering of HTML/SVG
  - Filename via `Path.normalize` + base-directory check
  - Virus scan or accepted-risk documented
- [ ] **Path traversal** - `Path.resolve(userInput).normalize().startsWith(baseDir)` on any user-controlled file op
- [ ] **Process execution** - no `Runtime.exec` / `ProcessBuilder` with interpolated input; allowlist + tokenized arguments

### Step 9 - Common Spring Boot Vulnerability Patterns

- [ ] **CSRF token** on state-changing form requests; SPAs use `CookieCsrfTokenRepository.withHttpOnlyFalse()` so JS can read the token
- [ ] **Rate limiting** - Bucket4j / Resilience4j or upstream LB on `/login`, `/password`, `/signup`, `/oauth/token`, expensive search
- [ ] **SQL injection via dynamic sort / filter** - `Sort.by(sortField)` validated against an allowlist; no `entityManager.createQuery("... order by " + userField)`
- [ ] **Open redirect** - `response.sendRedirect(userInput)` validated against an allowlist; Spring MVC `redirect:` with user input guarded
- [ ] **Server-side template injection** - no Thymeleaf `${...}` on user-controlled template strings; SpEL never receives user input as the expression
- [ ] **Spring Boot Actuator exposure** - `info`, `health` only (or behind auth) in prod; `env`, `heapdump`, `loggers`, `mappings` never public
- [ ] **DevTools** - `developmentOnly` in Gradle / `<scope>runtime>` `optional` in Maven; never in prod
- [ ] **Spring4Shell-class CVEs** - `DataBinder` not bound to `Class` / `ClassLoader` properties; recent dep-check passes
- [ ] **H2 console** (`spring.h2.console.enabled`) disabled outside dev

### Step 10 - Data Protection

- [ ] **PII / sensitive fields encrypted** at rest (Jasypt, Spring Vault, or DB-native column encryption)
- [ ] **Logback masking** for `password`, `token`, `creditCard`, `ssn`, `apiKey`; `@JsonIgnore` on the same DTO fields
- [ ] **No sensitive data in URLs** (use POST body, headers, signed tokens)
- [ ] **TLS enforcement** - `server.ssl.enabled=true` or HTTPS at LB; HSTS via `HeadersConfigurer`
- [ ] **Database backups** encrypted; access controlled
- [ ] **Secrets management** - Vault, AWS Secrets Manager, env-var injection - never `application-prod.yml` committed

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`. Write to the report file before ending; print confirmation.

## Rules

- Validate at system boundaries (controller `@RequestBody`, external API responses, message payloads)
- Never disable CSRF / method security to silence a failing test - fix the test
- Never widen `@PreAuthorize` (e.g., `hasRole('ADMIN')` to `permitAll`) without an explicit security note
- Log security events without sensitive data
- Default-deny in `SecurityFilterChain`

## Self-Check

- [ ] Behavioral principles loaded as Step 1
- [ ] Stack confirmed before Spring-specific checks
- [ ] `review-precondition-check` ran (or handle received); refs captured
- [ ] Diff and commit log read once and reused - no mid-review re-issuing
- [ ] For `pr-ref` mode, user-run fetch surfaced; local ref existed
- [ ] When `head_matches_current` was false, explicit approval obtained (skipped as subagent)
- [ ] Security surface (SecurityFilterChain, changed controllers, management/security keys, build deps, modified tests) read; prior revision consulted when annotations or matchers were removed
- [ ] OWASP Top 10 reviewed with Spring framing - every category checked, none silently skipped
- [ ] `spring-security-patterns` consulted for canonical patterns
- [ ] Auth step run for the mechanism in use (form / OAuth2 / JWT)
- [ ] **Authorization drift sweep** - every new endpoint has a matching matcher or `@PreAuthorize`
- [ ] Bean Validation on every `@RequestBody`; entities never accepted as input DTOs
- [ ] File upload, path traversal, process execution checks run if applicable
- [ ] CSRF, CORS, rate limiting, open redirect, Actuator exposure, DevTools gating verified
- [ ] Every finding includes an attack scenario - not just "input not validated"
- [ ] If no findings in a category: state "No issues found" per category
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Critical > High > Medium > Low (omit if none)
- [ ] Report written via `review-report-writer`; confirmation printed

## Output Format

```markdown
## Spring Boot Security Review Summary

**Stack Detected:** Java <version> / Spring Boot <version>
**Auth:** Spring Security Form Login | OAuth2 Resource Server (JWT) | OAuth2 Client | Custom | Hybrid
**Authorization:** SecurityFilterChain matchers | @PreAuthorize / @PostAuthorize | Custom
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment; call out Spring-specific risks like missing `@PreAuthorize`, deprecated `WebSecurityConfigurerAdapter`, or exposed Actuator.]

## Findings

### Critical
- **Location:** [file:line]
- **Issue:** [vulnerability in Spring terms - e.g., "`@RequestBody` binds entity directly in OrderController#update, allowing mass assignment of `ownerId`"]
- **Attack scenario:** [how the attacker exploits this]
- **Fix:** [specific Spring remediation with code]

### High
[Same structure]

### Medium
[Same structure]

### Low
[Same structure]

_Omit empty severity sections. If all omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening not tied to a specific finding]

## Next Steps

Prioritized, each tagged `[Implement]` (localized) or `[Delegate]` (cross-cutting, dep upgrade, threat-model). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit if no security issues._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git from this workflow
- Vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `{\"role\":\"ADMIN\"}` and gains admin via mass assignment")
- Skipping OWASP categories that appear clean - explicitly state "No issues found"
- Generic security advice when a Spring idiom applies (say "add `@PreAuthorize(\"hasRole('ADMIN')\")`", not "add an authorization check")
- Suggesting `csrf().disable()` as a fix for a failing form - validate the test sends a CSRF token instead
- Disabling `@EnableMethodSecurity` to silence a missing `@PreAuthorize` warning
- Conflating security with perf or general review
- Recommending `WebSecurityConfigurerAdapter` (removed) - use `SecurityFilterChain`
