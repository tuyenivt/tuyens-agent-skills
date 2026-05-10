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

### Step 6 - Authentication, Authorization, and Common Vulnerability Patterns

Use skill: `kotlin-spring-security-patterns` for canonical `SecurityFilterChain` (Kotlin DSL), OAuth2/JWT, method security, CORS, CSRF, headers, `@AuthenticationPrincipal`, `AuthorizationManager`, and coroutine `SecurityContext` propagation.

Review-scoped scan (every check below should already have its canonical pattern in `kotlin-spring-security-patterns`; this list is what the *diff* must satisfy):

**Authentication / token discipline:**

- [ ] `SecurityFilterChain` Kotlin DSL `@Bean`; no `WebSecurityConfigurerAdapter` (removed in 6.x)
- [ ] OAuth2 Resource Server: explicit `JwtDecoder` with issuer + audience validators; signature algorithm pinned; `alg: none` rejected; HMAC secret never defaults
- [ ] Form login / Basic: `BCryptPasswordEncoder` strength ≥ 10; no `NoOpPasswordEncoder` outside tests
- [ ] Session cookie `Secure` + `HttpOnly` + `SameSite=Lax|Strict`; session fixation enabled (default in Boot 3+)
- [ ] Refresh-token rotation; short access-token TTL (5-15 min); revocable refresh tokens
- [ ] Brute-force / rate limiting (Bucket4j, Resilience4j) on `/login`, `/oauth/token`, password reset
- [ ] No credentials in `application.yml` committed - env vars, Vault, AWS Secrets Manager, Spring Cloud Config
- [ ] Actuator: `management.endpoints.web.exposure.include` minimal in prod; sensitive endpoints behind a separate `SecurityFilterChain`
- [ ] Kotlin SpEL escaping: `@Value("\${...}")` and `@PreAuthorize("hasRole('ADMIN')")` use literal SpEL (Kotlin string templates collide with `${...}`)

**Authorization / IDOR / tenant isolation:**

- [ ] `@EnableMethodSecurity` active; **authorization drift sweep** - every new controller endpoint has a `SecurityFilterChain` matcher OR `@PreAuthorize` (or `permitAll` with rationale)
- [ ] Service-method `@PreAuthorize` for defense-in-depth alongside matchers
- [ ] **IDOR**: scoped repository lookups (`findByIdAndOwnerId(id, principal.id): Order?`) - never `findById(id)` then post-fetch authorization check (leaks existence)
- [ ] **Collection-level IDOR**: list endpoints filter at the query layer (`findAllByOwnerId(principal.id, pageable)`); `@PostFilter` only as a defense-in-depth check, not as primary enforcement
- [ ] **Tenant isolation**: queries scoped by `tenantId` at the repository layer (Hibernate `@Filter`, `@TenantId`, query-method parameter) - never controller-only
- [ ] Default-deny: `authorize(anyRequest, authenticated)` after explicit allowlist
- [ ] CSRF enabled for stateful sessions; `csrf { disable() }` only for stateless JWT APIs with rationale; CORS origins explicit (no `"*"` for credentialed)

**Input validation and mass assignment:**

- [ ] Bean Validation on every `@RequestBody` `data class` with **`@field:`** site target (`@field:NotNull` / `@field:Size` / `@field:Pattern`) - without `@field:` the annotation is silently ignored
- [ ] Immutable `data class` DTOs for input - no `var`; entities never accepted as `@RequestBody` (mass assignment risk)
- [ ] **Privilege-bearing fields** (`role`, `admin`, `ownerId`, `tenantId`, `approved`, server-controlled `status`) absent from user-facing request DTOs; admin-only paths if needed
- [ ] **Response DTOs strip server-only fields** (`passwordHash`, `lastLoginIp`, `mfaSecret`, `paymentMethodToken`, `internalNotes`); flag controller return types of `<Entity>`
- [ ] **Password-change endpoints**: require current password; rate-limited; complexity via `@field:Pattern` or `Validator`; consider password-history check
- [ ] **File uploads** (`MultipartFile`): content-type detected via Apache Tika; size limits enforced; stored outside webroot; filename normalized via `Path.normalize().startsWith(baseDir)`
- [ ] **Path traversal** check on any user-controlled file path
- [ ] **Process execution**: no `Runtime.exec` / `ProcessBuilder` with interpolated user input

**Common Kotlin/Spring vulnerability patterns:**

- [ ] **SQL injection** via dynamic sort / filter: `Sort.by(sortField)` validated against allowlist; **no JPQL string interpolation** (Kotlin string templates `"... where x = $userInput"` are the same vulnerability as Java string concat)
- [ ] **Open redirect**: `response.sendRedirect(userInput)` validated against allowlist
- [ ] **Server-side template injection**: no Thymeleaf `${...}` on user-controlled templates; SpEL never receives user input as the expression
- [ ] **DevTools**: `spring-boot-devtools` is `developmentOnly` in Gradle
- [ ] **Spring4Shell-class CVEs**: `DataBinder` not bound to `Class` / `ClassLoader` properties; dep-check clean
- [ ] **H2 console** disabled in non-dev profiles
- [ ] **Coroutine `SecurityContext`**: `SecurityContextHolder.getContext()` does not survive `suspend` dispatcher switches - use `ReactiveSecurityContextHolder.getContext().awaitFirstOrNull()`, `@AuthenticationPrincipal`, or pass principal explicitly

### Step 7 - Data Protection

- [ ] **PII / sensitive fields encrypted** at rest (Jasypt, Spring Vault, or DB-native column encryption)
- [ ] **Logback / Logstash encoder masking** for sensitive keys (`password`, `token`, `creditCard`, `ssn`, `apiKey`); `@JsonIgnore` on the same DTO fields
- [ ] **No sensitive data in URLs** (use POST body, headers, or signed tokens)
- [ ] **TLS enforcement**: `server.ssl.enabled=true` or HTTPS-only at the LB; HSTS header set via Kotlin DSL `headers { httpStrictTransportSecurity { } }`
- [ ] **Database backups** encrypted; access controlled
- [ ] **Secrets management**: Spring Cloud Config + Vault, AWS Secrets Manager, or env-var injection - never `application-prod.yml` committed


### Step 8 - Write Report

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
- [ ] Authn discipline reviewed for the mechanism in use (Spring Security 6.x / OAuth2 / JWT); session, refresh, brute-force, secrets, Actuator exposure, SpEL-escape verified
- [ ] **Authorization drift sweep**: every new controller endpoint has a matching matcher or `@PreAuthorize`; IDOR / collection-IDOR / tenant scoping checked at the query layer
- [ ] Bean Validation reviewed on every `@RequestBody`; entities never accepted as input DTOs; `@field:` site target verified; privilege-bearing fields absent; response DTOs strip server-only fields
- [ ] File upload, path traversal, process-execution, password-change current-password checks run if applicable
- [ ] CSRF, CORS, rate limiting, open redirect, SSTI, DevTools / H2-console gating verified
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
