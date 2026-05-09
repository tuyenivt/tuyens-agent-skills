---
name: task-kotlin-review-security
description: Kotlin / Spring Boot security review: Kotlin DSL SecurityFilterChain, OAuth2/JWT, method security, CSRF, coroutine SecurityContext, OWASP Top 10.
agent: kotlin-security-engineer
metadata:
  category: backend
  tags: [kotlin, spring-boot, security, spring-security, oauth2, jwt, owasp, kotlin-dsl, workflow]
  type: workflow
user-invocable: true
---

# Kotlin / Spring Boot Security Review

## Purpose

Kotlin-aware security review that names Spring Security 6.x Kotlin DSL `SecurityFilterChain`, OAuth2 Resource Server, JWT, method security (`@PreAuthorize`), Bean Validation on `data class` DTOs, sealed-class result hierarchies, and coroutine `SecurityContext` propagation directly. Produces findings with attack scenarios and concrete Kotlin-specific remediations.

This workflow is the stack-specific delegate of `task-code-review-security` for Kotlin / Spring Boot.

## When to Use

- Reviewing a Kotlin/Spring Boot PR for security regressions
- Pre-deployment hardening pass on auth, authz, file upload, payment, or PII-handling code
- Periodic strong-validation and method-security drift sweep
- Auditing OAuth2 / JWT auth flow or new `@PreAuthorize` annotations

**Not for:**

- Performance review (use `task-kotlin-review-perf`)
- General code review (use `task-kotlin-review`)
- Production incident triage (use `/task-oncall-start`)

## Invocation

| Invocation                              | Meaning                                                             |
| --------------------------------------- | ------------------------------------------------------------------- |
| `/task-kotlin-review-security`          | Review current branch vs its base                                   |
| `/task-kotlin-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                          |
| `/task-kotlin-review-security pr-<N>`   | Review a PR head fetched into local branch `pr-<N>`                 |

When invoked as a subagent of `task-code-review-security`, Step 3 (diff resolution) is skipped.

## Workflow

### Step 1 - Load Behavioral Principles (mandatory, first)

Use skill: `behavioral-principles`. Load these rules first - they govern every subsequent step.

### Step 2 - Confirm Stack

Use skill: `stack-detect` to confirm Kotlin / Spring Boot. If invoked as a delegate of `task-code-review-security` or as a subagent of `task-kotlin-review` (parent already detected Kotlin/Spring), accept the pre-confirmed stack and skip re-detection. If not, stop and tell the user to invoke `/task-code-review-security` instead.

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check`. On approval, read diff and commit log once. Skip if invoked as subagent and parent passed the handle.

### Step 4 - Read the Security Surface

Open files that actually wire security:

- Every `SecurityFilterChain` `@Bean` (typically `SecurityConfig.kt`); read the matcher chain top-to-bottom - matcher order matters; misordered `permitAll` ahead of authenticated rule is a real vulnerability
- Every changed `@RestController` and `@Controller` - look for `@RequestBody` types (`@Entity` vs `data class` DTO), `@PreAuthorize` / `@PostAuthorize` annotations added or removed
- `application.yml` and per-profile variants - `management.endpoints.web.exposure.include`, `spring.security.*`, `server.servlet.session.*`, `server.ssl.*`
- `build.gradle.kts` - confirm `spring-boot-starter-security` (and `spring-boot-starter-oauth2-resource-server` if JWT), and that `spring-boot-devtools` is `developmentOnly`
- Any modified test - a green test obtained by disabling security or removing `@PreAuthorize` is a finding, not a fix

When the diff removes a security annotation or relaxes a matcher, also `git log -p` the prior revision.

### Step 5 - OWASP Quick Check (Kotlin/Spring Lens)

Apply OWASP Top 10 with Kotlin/Spring framing. Use skill: `kotlin-spring-security-patterns` for canonical patterns.

| Risk                          | Kotlin/Spring-specific check                                                                                                                                                                            |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Every endpoint declares authorization explicitly via `SecurityFilterChain` matcher (Kotlin DSL `authorize(...)`) or `@PreAuthorize` / `@PostAuthorize`. No implicit `permitAll`.                        |
| Injection                     | Repository methods use derived queries or `@Query` with named parameters. No string-template interpolation in JPQL or native SQL (`@Query("... where x = $userInput")` is SQL injection in Kotlin too). |
| Cryptographic Failures        | Spring Security `BCryptPasswordEncoder` (or `Argon2PasswordEncoder`) for passwords; Jasypt / Spring Cloud Config Vault for secrets at rest; no `MessageDigest.getInstance("MD5"/"SHA-1")` for auth.     |
| Security Misconfiguration     | `SecurityFilterChain` explicit; HTTPS-only via `requiresChannel().requiresSecure()` or upstream LB; security headers via Kotlin DSL `headers { }`.                                                      |
| SSRF                          | `WebClient` / `RestClient` calls validate hostnames against an allowlist before request; no `URI.create(userInput)` with unvalidated URI. The validator must reject private/loopback ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, `127.0.0.0/8`, `::1`, fc00::/7) *after DNS resolution* (defense against DNS-rebinding) - resolving once and pinning the IP for the request, or using a custom `ClientHttpRequestInterceptor` that re-checks. Hostname-string allowlists alone are insufficient. |
| XSS                           | Thymeleaf auto-escapes - no `th:utext` on user input. JSON responses set `Content-Type: application/json` to block sniff XSS.                                                                            |
| Insecure Design               | Method security (`@EnableMethodSecurity`) enabled and used; default-deny via `authorizeHttpRequests { authorize(anyRequest, authenticated) }`.                                                          |
| Vulnerable Components         | `./gradlew dependencyCheckAnalyze` (OWASP dep-check) clean; `./gradlew dependencyUpdates` reviewed; no Gradle entries with known CVEs.                                                                  |
| Data Integrity Failures       | No `ObjectInputStream.readObject` on untrusted input; Jackson typed-deserialization disabled (`enableDefaultTyping` off); SnakeYAML uses `SafeConstructor`.                                              |
| Logging & Monitoring          | Logback pattern excludes sensitive fields; `@JsonIgnore` on PII / secret fields in DTOs; no `log.info("user={}", user)` that serializes the entity. Security events (login fail, AccessDenied) logged. |

### Step 6 - Authentication (Spring Security 6.x / OAuth2 / JWT)

- [ ] **`SecurityFilterChain`** is explicit and version-current; `WebSecurityConfigurerAdapter` does not exist (removed in 6.x)
- [ ] **OAuth2 Resource Server**: `oauth2ResourceServer { jwt { } }` configured with explicit `JwtDecoder`; signature algorithm pinned; `JwtAuthenticationConverter` maps claims to authorities consistently
- [ ] **JWT issuer / audience** validated (`JwtValidators.createDefaultWithIssuer`, custom audience validator); not just signature
- [ ] **JWT no `alg: none`**: `JwtDecoder` rejects unsigned tokens; HMAC secret never falls back to a hardcoded default
- [ ] **Refresh token rotation**: short access-token lifetime (5-15 min); refresh tokens revocable
- [ ] **Form login / Basic auth**: `BCryptPasswordEncoder` minimum strength 10; no `NoOpPasswordEncoder` outside tests
- [ ] **Session fixation** protection enabled (default in Boot 3+); session cookie `Secure`, `HttpOnly`, `SameSite=Lax|Strict`
- [ ] **Brute-force protection**: rate limiting (Bucket4j, Resilience4j) on `/login`, `/oauth/token`, password reset
- [ ] **No credentials in `application.yml` committed to git** - secrets via env vars, Vault, AWS Secrets Manager, or Spring Cloud Config
- [ ] **Actuator endpoints** restricted: `management.endpoints.web.exposure.include` minimal in prod; remaining endpoints behind `ROLE_ACTUATOR`
- [ ] **Kotlin string-template SpEL escaping**: `@PreAuthorize("hasRole('ADMIN')")` uses literal SpEL; `@Value("\${prop}")` escapes the `$` to avoid Kotlin string-template collision

### Step 7 - Authorization (Method Security / `@PreAuthorize` / Custom)

- [ ] **`@EnableMethodSecurity`** active; `@PreAuthorize` on every service method that touches user-owned resources (defense in depth alongside controller-level matchers)
- [ ] **Authorization drift sweep**: every new controller endpoint added in the diff has a corresponding `SecurityFilterChain` matcher OR a `@PreAuthorize` (or explicit `permitAll` with rationale)
- [ ] **IDOR**: lookups in user-facing services scope through the principal (`repository.findByIdAndOwnerId(id, principal.id)`) returning `Order?` rather than `repository.findById(id)` followed by an authorization check (which leaks existence via 403 vs 404)
- [ ] **List endpoints / IDOR at the collection level**: list-returning endpoints (`GET /orders`) must filter by the principal at the query level (`findAllByOwnerId(principal.id, pageable)`) rather than fetching all and filtering in memory, and must not rely on `@PostFilter("filterObject.ownerId == authentication.principal.id")` alone for large collections - `@PostFilter` is an in-memory filter and pages already constrained by the DB fetch. Use both: query-level filter for correctness/perf, `@PostFilter` only as a defense-in-depth check on small inner collections
- [ ] **Tenant isolation**: multi-tenant apps scope queries by `tenantId` in the repository layer (Hibernate `@Filter`, `@TenantId` in 6.x, or query-method parameter) - never rely on controller-level filtering alone
- [ ] **Default-deny** in `SecurityFilterChain`: `authorize(anyRequest, authenticated)` after explicit allowlist; no trailing `permitAll`
- [ ] **CSRF**: enabled by default for stateful sessions; explicitly disabled (`csrf { disable() }`) only for stateless JWT APIs with documented rationale
- [ ] **CORS**: `CorsConfigurationSource` bean with explicit allowed origins (not `"*"` for credentialed requests)

### Step 8 - Input Validation and Mass Assignment

- [ ] **Bean Validation (`jakarta.validation`)** on every `@RequestBody` `data class`: `@field:NotNull`, `@field:Size`, `@field:Email`, `@field:Pattern` etc. (Kotlin annotation site target `@field:` is required for Bean Validation to reach the property's backing field); `@Valid` on the controller parameter
- [ ] **Constructor / `data class` DTOs** for input - immutable, no `var` properties; avoids the "mass assignment" class of bugs because Jackson uses the constructor
- [ ] **No privilege-bearing fields in user-facing input DTOs**: `role`, `admin`, `ownerId`, `userId`, `tenantId`, `accountId`, `approved`, `status` (when status is server-controlled) - these flip authorization or ownership and must be set by the server; if they appear in a `@RequestBody` `data class`, require an admin-only controller path
- [ ] **No exposing entities directly** as `@RequestBody` - always a `data class` DTO; Jackson on a JPA entity can populate fields the API never intended to accept
- [ ] **Response DTO sensitive-field stripping**: response `data class` types must not contain server-only fields. Returning the JPA entity or a wide internal `data class` from a controller leaks fields that were never intended for the API surface (`passwordHash`, `lastLoginIp`, `internalNotes`, `mfaSecret`, `paymentMethodToken`, `auditTrail`). Define a separate response `data class` per endpoint (or use a Spring Data projection) and verify by inspecting the JSON shape. Flag any controller method whose return type is `<Entity>` or whose response includes a property whose name suggests credentials/auditing/internal state
- [ ] **Password-change endpoints**: must require the current password (not just an authenticated session); enforce complexity via Bean Validation `@field:Pattern` or a `Validator`; rate-limit (Bucket4j / RateLimiter on the endpoint key, not just the user); and ideally check against a small password-history list to prevent immediate reuse. Flag any password-change path that lacks current-password verification - it lets a hijacked session permanently take over the account
- [ ] **File uploads** (`MultipartFile`):
  - File type validated by content (Apache Tika `Tika.detect`), not just `contentType` (client-controlled)
  - Per-file size limit (`spring.servlet.multipart.max-file-size`) and total request size enforced
  - Saved files stored outside the webroot; `Content-Disposition: attachment` on serve
  - Filename sanitized via `Path.normalize()` and base-directory check
- [ ] **Path traversal**: `Path.resolve(userInput).normalize().startsWith(baseDir)` check on any user-controlled file operation
- [ ] **Process execution**: no `Runtime.exec`, `ProcessBuilder` with interpolated user input - use API alternatives or strict allowlist + tokenized arguments

### Step 9 - Common Kotlin/Spring Boot Vulnerability Patterns

- [ ] **CSRF token** on state-changing form requests; for SPAs, `CookieCsrfTokenRepository.withHttpOnlyFalse()` so JS can read the token
- [ ] **CORS**: explicit origins (no `"*"` for credentialed endpoints)
- [ ] **Rate limiting**: Bucket4j, Resilience4j RateLimiter, or upstream LB on `/login`, `/password`, `/signup`, `/oauth/token`, expensive search
- [ ] **SQL injection via dynamic sort / filter**: `Sort.by(sortField)` validated against an allowlist; no JPQL string interpolation (Kotlin string templates `"... where x = $userInput"` are exactly the same vulnerability as Java string concatenation)
- [ ] **Open redirect**: `response.sendRedirect(userInput)` validated against an allowlist
- [ ] **Server-side template injection**: no Thymeleaf `${...}` evaluation on user-controlled template strings; SpEL evaluator never receives user input as the expression
- [ ] **Mass assignment via JSON**: `@RequestBody` uses `data class` DTOs, not entities
- [ ] **Spring Boot Actuator exposure**: `info`, `health` only (or behind auth) in prod; `env`, `heapdump`, `loggers`, `mappings` never public
- [ ] **DevTools**: `spring-boot-devtools` is `developmentOnly` in Gradle - never shipped to prod
- [ ] **Spring4Shell-class CVEs**: `DataBinder` not bound to `Class` / `ClassLoader` properties; recent dep-check passes
- [ ] **H2 console** disabled in non-dev profiles
- [ ] **Coroutine SecurityContext**: `SecurityContextHolder.getContext()` does not propagate across `suspend` dispatcher switches - use `ReactiveSecurityContextHolder.getContext().awaitFirstOrNull()` or pass principal as a method parameter; flag any `suspend` service relying on `SecurityContextHolder`

### Step 10 - Data Protection

- [ ] **PII / sensitive fields encrypted** at rest (Jasypt, Spring Vault, or DB-native column encryption)
- [ ] **Logback / Logstash encoder masking** for sensitive keys (`password`, `token`, `creditCard`, `ssn`, `apiKey`); `@JsonIgnore` on the same DTO fields
- [ ] **No sensitive data in URLs** (use POST body, headers, or signed tokens)
- [ ] **TLS enforcement**: `server.ssl.enabled=true` or HTTPS-only at the LB; HSTS header set via Kotlin DSL `headers { httpStrictTransportSecurity { } }`
- [ ] **Database backups** encrypted; access controlled
- [ ] **Secrets management**: Spring Cloud Config + Vault, AWS Secrets Manager, or env-var injection - never `application-prod.yml` committed


### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Rules

- Always validate at system boundaries (controller `@RequestBody`, external API responses, message payloads)
- Never disable CSRF or method security to silence a failing test - fix the test
- Never widen `@PreAuthorize` without an explicit security review note
- Log security events (login failure, access denied, validation failure) without sensitive data
- Follow principle of least privilege - default-deny in `SecurityFilterChain`

## Self-Check

- [ ] `behavioral-principles` loaded as Step 1 before stack detection or any other delegation
- [ ] Stack confirmed as Kotlin / Spring Boot
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow)
- [ ] Diff and commit log were read once and reused
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced
- [ ] When `head_matches_current` was false, explicit user approval was obtained
- [ ] Security surface (SecurityFilterChain bean, controllers, application.yml management/security keys, build.gradle.kts dependencies, modified tests) read directly; prior revision consulted when annotations or matchers were removed
- [ ] OWASP Top 10 reviewed with Kotlin/Spring framing - every category checked
- [ ] `kotlin-spring-security-patterns` consulted for canonical patterns
- [ ] Authentication step run for the auth mechanism in use (Spring Security 6.x / OAuth2 / JWT)
- [ ] **Authorization drift sweep**: every new controller endpoint has a matching matcher or `@PreAuthorize`
- [ ] Bean Validation reviewed on every `@RequestBody`; entities are never accepted as input DTOs; `@field:` site target verified
- [ ] File upload, path traversal, and process-execution checks run if applicable
- [ ] CSRF, CORS, rate limiting, open redirect, Actuator exposure, DevTools gating verified
- [ ] Coroutine `SecurityContext` propagation reviewed for any `suspend` service touching auth
- [ ] Every finding includes an attack scenario - not just "input not validated"
- [ ] If no findings: explicitly state "No issues found" per category
- [ ] Next Steps section produced ordered Critical > High > Medium > Low
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## Kotlin / Spring Boot Security Review Summary

**Stack Detected:** Kotlin <version> / Spring Boot <version>
**Auth:** Spring Security Form Login | OAuth2 Resource Server (JWT) | OAuth2 Client | Custom | Hybrid
**Authorization:** SecurityFilterChain matchers | @PreAuthorize / @PostAuthorize | Custom
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment, calling out Kotlin-specific risks like missing `@PreAuthorize`, `data class` JPA entity in `@RequestBody`, `SecurityContextHolder` inside `suspend`, exposed Actuator endpoints.]

## Findings

### Critical

- **Location:** [file:line]
- **Issue:** [vulnerability described in Kotlin/Spring terms]
- **Attack scenario:** [how an attacker exploits this]
- **Fix:** [specific Kotlin remediation with code example]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit severity sections with no findings. If all sections are omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening - e.g., "Add Bucket4j rate limit on /oauth/token", "Replace SecurityContextHolder access in OrderService.kt:42 with ReactiveSecurityContextHolder", "Move secrets from application-prod.yml to Vault"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` or `[Delegate]`. Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action, e.g., "Replace `@RequestBody Order` with `@RequestBody OrderUpdateRequest data class`"]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit if no security issues found._
```

## Avoid

- Running state-changing git commands from this workflow
- Reporting vulnerabilities without an attack scenario
- Skipping OWASP categories that appear clean - explicitly state "No issues found"
- Recommending generic security advice when a Kotlin/Spring idiom applies
- Suggesting `csrf { disable() }` as a fix for a failing form submission
- Disabling `@EnableMethodSecurity` to silence a missing `@PreAuthorize` warning
- Conflating security review with general code quality or performance review
- Recommending `WebSecurityConfigurerAdapter` patterns - use Kotlin DSL `SecurityFilterChain`
- Omitting the `@field:` site target for Bean Validation annotations on data classes
- Forgetting to escape `$` in SpEL strings - Kotlin string templates collide with `${...}` SpEL syntax
