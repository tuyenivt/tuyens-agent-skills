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

Kotlin-aware security review for Spring Security 6.x Kotlin DSL `SecurityFilterChain`, OAuth2 Resource Server, JWT, method security, Bean Validation on `data class` DTOs, sealed-class result hierarchies, coroutine `SecurityContext` propagation. Findings with attack scenarios and concrete Kotlin remediations. Stack-specific delegate of `task-code-review-security`.

## When to Use

- Kotlin / Spring Boot PR for security regressions
- Pre-deployment hardening on auth / authz / file upload / payment / PII
- Periodic strong-validation and method-security drift sweep
- Auditing OAuth2 / JWT flow or new `@PreAuthorize`

**Not for:** perf review (`task-kotlin-review-perf`), general review (`task-kotlin-review`), incidents (`/task-oncall-start`).

## Invocation

| Invocation                              | Meaning                                       |
| --------------------------------------- | --------------------------------------------- |
| `/task-kotlin-review-security`          | Current branch vs base                         |
| `/task-kotlin-review-security <branch>` | `<branch>` vs base (3-dot)                     |
| `/task-kotlin-review-security pr-<N>`   | PR head in `pr-<N>`                            |
| `/task-kotlin-review-security sweep`    | Whole-surface sweep (periodic validation / method-security drift). Skips Step 3; Step 4 reads all controllers / `SecurityFilterChain`s / config, not just changed ones. Allowed on trunk - read-only. |

When invoked as a subagent of `task-kotlin-review` or `task-code-review-security`, Step 3 skipped (parent passes the precondition handle).

## Workflow

### Step 1 - Behavioral principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm stack

Use skill: `stack-detect`. Accept pre-confirmed.

### Step 3 - Resolve diff

Use skill: `review-precondition-check`. Read once. Skip if parent passed handle, or in `sweep` mode (no diff - Steps 4-7 apply to the whole security surface; findings still cite `file:line`).

### Step 4 - Read the security surface

- Every `SecurityFilterChain` `@Bean` (typically `SecurityConfig.kt`); matcher chain top-to-bottom - **order matters**, misordered `permitAll` ahead of an authenticated rule is a real vulnerability
- Every changed `@RestController` / `@Controller` - `@RequestBody` types (entity vs DTO), `@PreAuthorize` / `@PostAuthorize` adds/removes
- `application.yml` per-profile - `management.endpoints.web.exposure.include`, `spring.security.*`, `server.servlet.session.*`, `server.ssl.*`
- `build.gradle.kts` - `spring-boot-starter-security`, `spring-boot-starter-oauth2-resource-server`, `spring-boot-devtools` must be `developmentOnly`
- Any modified test - a green test from disabled security or removed `@PreAuthorize` is a finding, not a fix

When the diff removes a security annotation or relaxes a matcher, `git log -p` the prior revision.

### Step 5 - OWASP quick check (Kotlin / Spring lens)

Use skill: `kotlin-spring-security-patterns` for canonical patterns.

| Risk                       | Kotlin / Spring check                                                                                                                                                                          |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control      | Every endpoint authorizes via DSL `authorize(...)` or `@PreAuthorize` / `@PostAuthorize`. No implicit `permitAll`.                                                                              |
| Injection                  | Derived queries or `@Query` with named parameters. **No string interpolation in JPQL** (Kotlin templates `"where x = $userInput"` = SQL injection).                                            |
| Cryptographic Failures     | `BCryptPasswordEncoder` / `Argon2PasswordEncoder` for passwords; Vault for secrets at rest; no MD5 / SHA-1 for auth.                                                                            |
| Security Misconfig         | `SecurityFilterChain` explicit; HTTPS-only via `requiresSecure` / upstream LB; headers via DSL `headers { }`.                                                                                   |
| SSRF                       | `WebClient` / `RestClient` validates hostnames against an allowlist **and rejects private/loopback IPs after DNS resolution** (DNS-rebinding defense). Reject these literal ranges: `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16` (AWS IMDS), `::1`, `fc00::/7`. Resolve once + pin IP, or re-check via `ClientHttpRequestInterceptor`. |
| XSS                        | Thymeleaf auto-escapes - no `th:utext` on user input. JSON responses set `application/json` to block sniff XSS.                                                                                 |
| Insecure Design            | `@EnableMethodSecurity` on and used; default-deny via `authorize(anyRequest, authenticated)`.                                                                                                   |
| Vulnerable Components      | `./gradlew dependencyCheckAnalyze` clean; `./gradlew dependencyUpdates` reviewed.                                                                                                               |
| Data Integrity Failures    | No `ObjectInputStream.readObject` on untrusted input; Jackson typed-deserialization off; SnakeYAML uses `SafeConstructor`.                                                                       |
| Logging & Monitoring       | Logback pattern excludes sensitive fields; `@JsonIgnore` on PII / secret fields; no `log.info("user={}", user)` serializing entity. Security events (login fail, AccessDenied) logged.         |

### Step 6 - Authentication / authorization / vulnerabilities

Use skill: `kotlin-spring-security-patterns`.

**Authentication / token discipline:**

- [ ] `SecurityFilterChain` Kotlin DSL `@Bean`; no `WebSecurityConfigurerAdapter`
- [ ] OAuth2: explicit `JwtDecoder` with issuer + audience validators; signature algorithm pinned; `alg: none` rejected; HMAC secret never defaults
- [ ] Form login / Basic: `BCryptPasswordEncoder` strength ≥ 10; no `NoOpPasswordEncoder` outside tests
- [ ] Session cookie `Secure` + `HttpOnly` + `SameSite=Lax|Strict`; session fixation enabled
- [ ] Refresh-token rotation; short access TTL (5-15 min); revocable refresh tokens
- [ ] Rate limiting (Bucket4j / Resilience4j) on `/login`, `/oauth/token`, password reset
- [ ] No credentials in `application.yml` - env / Vault / Secrets Manager / Spring Cloud Config
- [ ] Actuator: `management.endpoints.web.exposure.include` minimal in prod; sensitive endpoints behind a separate `SecurityFilterChain`
- [ ] Kotlin SpEL escaping: `@Value("\${...}")` and `@PreAuthorize("hasRole('ADMIN')")` use literal SpEL

**Authorization / IDOR / tenant isolation:**

- [ ] `@EnableMethodSecurity` active; **drift sweep** - every new endpoint has a matcher or `@PreAuthorize` (or documented `permitAll`)
- [ ] Defense-in-depth: service-method `@PreAuthorize` alongside matchers
- [ ] **IDOR**: scoped lookups (`findByIdAndOwnerId(id, principal.id): Order?`) over `findById(id)` + post-fetch check
- [ ] **Collection IDOR**: list endpoints filter at the query layer; `@PostFilter` is defense-in-depth, not primary
- [ ] **Tenant isolation**: queries scoped at the repository (`@Filter` / `@TenantId` / parameter), not controller-only
- [ ] Default-deny `authorize(anyRequest, authenticated)` after explicit allowlist
- [ ] CSRF for stateful; `csrf { disable() }` only for stateless JWT with rationale; CORS origins explicit (no `"*"` for credentialed)

**Input validation and mass assignment:**

- [ ] Bean Validation on every `@RequestBody` `data class` with **`@field:` target** (`@field:NotNull` / `@field:Size` / `@field:Pattern`) - without `@field:` annotations are silently ignored
- [ ] Immutable `data class` DTOs for input - no `var`; entities never accepted as `@RequestBody`
- [ ] **Privilege-bearing fields** (`role`, `admin`, `ownerId`, `tenantId`, `approved`, server-controlled `status`) absent from user DTOs; admin-only paths if needed
- [ ] **Response DTOs strip server-only fields** (`passwordHash`, `lastLoginIp`, `mfaSecret`, `paymentMethodToken`); flag controllers returning `<Entity>`
- [ ] **Password-change**: requires current password; rate-limited; complexity via `@field:Pattern`; consider history check
- [ ] **File uploads** (`MultipartFile`): content-type via Apache Tika; size limits; outside webroot; filename `Path.normalize().startsWith(baseDir)`
- [ ] **Path traversal** on any user-controlled file path
- [ ] **Process execution**: no `Runtime.exec` / `ProcessBuilder` with interpolated user input

**Common patterns:**

- [ ] **SQL injection** via dynamic sort: `Sort.by(sortField)` validated against allowlist; no JPQL string interpolation (Kotlin `"... where x = $userInput"` = same vulnerability)
- [ ] **Open redirect**: `response.sendRedirect(userInput)` validated against allowlist
- [ ] **SSTI**: no Thymeleaf `${...}` on user-controlled templates; SpEL never receives user input as expression
- [ ] **DevTools**: `spring-boot-devtools` is `developmentOnly`
- [ ] **Spring4Shell-class**: `DataBinder` not bound to `Class` / `ClassLoader` properties; dep-check clean
- [ ] **H2 console** disabled in non-dev
- [ ] **Coroutine `SecurityContext`**: `SecurityContextHolder.getContext()` does not survive `suspend` dispatcher switches - use `ReactiveSecurityContextHolder.awaitFirstOrNull()`, `@AuthenticationPrincipal`, or pass explicitly
- [ ] **`JwtDecoder.decode(...)` inside `suspend`**: the decoder is blocking and blocks the JVM thread mid-suspension. Either keep auth filtering in the servlet chain (non-suspend), wrap in `withContext(Dispatchers.IO)`, or rely on Virtual Threads to absorb the block (`spring.threads.virtual.enabled=true`)

**Messaging security** (when diff touches Kafka / RabbitMQ / webhooks):

Use skill: `kotlin-spring-messaging-patterns`.

- [ ] Webhook handlers verify signature **before** parsing payload (Stripe / GitHub `X-*-Signature`)
- [ ] Message payloads are `data class` / records - never JPA entities (leaks schema and lazy state)
- [ ] Consumer idempotency by stable dedup key; replay does not double-charge
- [ ] DLT / DLQ access restricted to ops; raw payloads scrubbed of PII before logging
- [ ] Kafka client TLS + SASL (`security.protocol: SASL_SSL`); RabbitMQ TLS; credentials from Vault / env
- [ ] `kafka.consumer.group-id` namespaced per environment to prevent cross-env consumption
- [ ] `@KafkaListener` / `@RabbitListener` not on `private` / `final` methods (silently bypassed)

### Step 7 - Data protection

- [ ] **PII encrypted at rest** (Jasypt / Vault / DB column encryption)
- [ ] **Logback masking** for `password` / `token` / `creditCard` / `ssn` / `apiKey`; `@JsonIgnore` on same DTO fields
- [ ] **No sensitive data in URLs** (POST body, headers, signed tokens)
- [ ] **TLS enforcement**: `server.ssl.enabled=true` or LB; HSTS via DSL
- [ ] **Database backups** encrypted; access controlled
- [ ] **Secrets**: Vault / Secrets Manager / env-var - never `application-prod.yml` committed

### Step 8 - Write report

**Subagent carve-out:** when spawned by a parent review (`task-kotlin-review` / `task-code-review-security`), do **not** call `review-report-writer` - the parent owns the single report and passes no checkpoint fields. Return the findings inline (Output Format below) for the parent to synthesize, and skip the rest of this step.

Standalone: Use skill: `review-report-writer` with `report_type: review-security`. Print confirmation.

## Rules

- Validate at system boundaries (`@RequestBody`, external API responses, message payloads)
- Never disable CSRF or method security to silence a failing test - fix the test
- Never widen `@PreAuthorize` without an explicit security review note
- Log security events (login fail, access denied, validation fail) without sensitive data
- Default-deny

## Output Format

```markdown
## Kotlin / Spring Boot Security Review Summary

**Stack Detected:** Kotlin <version> / Spring Boot <version>
**Auth:** Spring Security Form Login | OAuth2 Resource Server (JWT) | OAuth2 Client | Custom | Hybrid
**Authorization:** SecurityFilterChain matchers | @PreAuthorize / @PostAuthorize | Custom
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]
**OWASP Sweep:** [categories with findings: list] | remaining categories clean

[2-3 sentence assessment, calling out Kotlin-specific risks: missing `@PreAuthorize`, `data class` JPA entity in `@RequestBody`, `SecurityContextHolder` inside `suspend`, exposed Actuator endpoints]

## Findings

Severity -> intent label: Critical / High = `[Must]`, Medium = `[Recommend]`, Low = `[Recommend]` (or `[Question]` when the fix needs author input). Apply in Next Steps and when returning findings to a parent review.

### Critical
- **Location:** [file:line]
- **Issue:** [vulnerability in Kotlin/Spring terms]
- **Attack scenario:** [how an attacker exploits this]
- **Fix:** [Kotlin remediation with code]

### High / Medium / Low
[Same structure]

_Omit empty severities. If all empty: "No security issues found."_

## Recommendations
[Prioritized hardening]

## Next Steps
1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope] - [one-line action]
3. **[Implement]** [Recommend] file:line - [one-line action]
```

## Self-Check

- [ ] `behavioral-principles` loaded
- [ ] Stack confirmed
- [ ] `review-precondition-check` ran (or handle received, or `sweep` mode)
- [ ] Diff and log read once; reused
- [ ] For `pr-ref`, fetch command surfaced
- [ ] When `head_matches_current` was false, user approval obtained
- [ ] Security surface read directly; prior revision consulted when annotations/matchers removed
- [ ] OWASP Top 10 reviewed with Kotlin/Spring framing
- [ ] `kotlin-spring-security-patterns` consulted
- [ ] Authn discipline reviewed (Spring Security 6.x / OAuth2 / JWT); session, refresh, rate limit, secrets, Actuator, SpEL escape
- [ ] Authz drift sweep; IDOR / collection IDOR / tenant scoping at query layer
- [ ] Bean Validation on every `@RequestBody`; entities not accepted as input; `@field:` target verified; privilege-bearing fields absent; response DTOs strip server-only fields
- [ ] File upload, path traversal, process exec, password-change current-password checks if applicable
- [ ] CSRF, CORS, rate limiting, open redirect, SSTI, DevTools / H2 verified
- [ ] Coroutine `SecurityContext` reviewed for `suspend` touching auth
- [ ] Every finding includes attack scenario
- [ ] OWASP Sweep line filled: categories with findings listed, rest declared clean
- [ ] Next Steps ordered Must > Recommend > Question
- [ ] Standalone: report written + confirmation printed. Subagent: findings returned inline, `review-report-writer` not called

## Avoid

- State-changing git
- Reporting vulnerabilities without attack scenario
- Leaving OWASP categories unaccounted for - every category is either in the findings or covered by the OWASP Sweep clean declaration
- Generic security advice when a Kotlin / Spring idiom applies
- Suggesting `csrf { disable() }` to fix a failing form submission
- Disabling `@EnableMethodSecurity` to silence a missing-`@PreAuthorize` warning
- Conflating with general or perf review
- Recommending `WebSecurityConfigurerAdapter`
- Omitting `@field:` target for Bean Validation on data classes
- Forgetting to escape `$` in SpEL
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
