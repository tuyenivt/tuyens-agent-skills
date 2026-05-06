---
name: task-spring-review-security
description: Spring Boot security review for Spring Security 6.x SecurityFilterChain, OAuth2/JWT, method security, validation, CSRF, and Java-aware OWASP Top 10. Use when reviewing a Spring Boot PR for security regressions or auditing an auth flow. Stack-specific override of task-code-review-security, invoked when stack-detect resolves to Java/Spring Boot.
agent: java-security-engineer
metadata:
  category: backend
  tags: [java, spring-boot, security, spring-security, oauth2, jwt, owasp, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Spring Boot Security Review

## Purpose

Spring-aware security review that names Spring Security 6.x `SecurityFilterChain`, OAuth2 Resource Server, JWT, method security (`@PreAuthorize`), Bean Validation, and Spring Security Crypto idioms directly instead of routing through the generic backend security adapter. Produces findings with attack scenarios and concrete Spring-specific remediations.

This workflow is the stack-specific delegate of `task-code-review-security` for Java / Spring Boot. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a Spring Boot PR for security regressions
- Pre-deployment hardening pass on auth, authz, file upload, payment, or PII-handling code
- Periodic strong-validation and method-security drift sweep across controllers
- Auditing an OAuth2 / JWT auth flow or a new `@PreAuthorize` annotation

**Not for:**

- Performance review (use `task-code-review-perf` or its Spring delegate)
- General code review (use `task-code-review`)
- Production incident triage (use `/task-oncall-start`)

## Invocation

Mirrors `task-code-review-security`:

| Invocation                              | Meaning                                                                                               |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-spring-review-security`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-spring-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-spring-review-security pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-security` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect` to confirm Java / Spring Boot. If the detected stack is not Spring Boot, stop and tell the user to invoke `/task-code-review-security` instead.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-security` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Security Surface

Before applying the OWASP and authn/authz checklists, open the files that actually wire security so findings cite real lines:

- Every `SecurityFilterChain` `@Bean` (typically `SecurityConfig.java`, `WebSecurityConfig.java`); read the request matcher chain top-to-bottom - matcher order matters and a misordered `permitAll` ahead of an authenticated rule is a real vulnerability
- Every changed `@RestController` and `@Controller` - look for `@RequestBody` types (entity vs DTO/record), `@PreAuthorize` / `@PostAuthorize` annotations added or removed
- `application.yml` and per-profile variants - `management.endpoints.web.exposure.include`, `spring.security.*`, `server.servlet.session.*`, `server.ssl.*`
- `build.gradle(.kts)` / `pom.xml` - confirm `spring-boot-starter-security` (and `spring-boot-starter-oauth2-resource-server` if JWT), and that `spring-boot-devtools` is `developmentOnly`/`runtime optional`
- Any test that was modified in the diff - a green test obtained by disabling security or removing `@PreAuthorize` is a finding, not a fix

When the diff removes a security annotation or relaxes a matcher, also `git log -p` the prior revision of those lines to confirm what was protected before. The blame trail is the authoritative answer to "did this change weaken authorization."

### Step 4 - OWASP Quick Check (Spring Lens)

Apply the OWASP Top 10 with Spring-specific framing. Use skill: `spring-security-patterns` for canonical Spring patterns referenced below.

| Risk                          | Spring-specific check                                                                                                                                                                                  |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Broken Access Control         | Every endpoint declares authorization explicitly via `SecurityFilterChain` matcher or `@PreAuthorize` / `@PostAuthorize`. No implicit `permitAll`.                                                     |
| Injection                     | Repository methods use derived queries or `@Query` with named parameters. No string concatenation in JPQL or native SQL. No `entityManager.createNativeQuery(... + userInput + ...)`.                  |
| Cryptographic Failures        | Spring Security `BCryptPasswordEncoder` (or `Argon2PasswordEncoder`) for passwords; Jasypt / Spring Cloud Config Vault for secrets at rest; no `MessageDigest.getInstance("MD5"/"SHA-1")` for auth.    |
| Security Misconfiguration     | `SecurityFilterChain` explicit (no reliance on Spring Boot 1.x defaults); HTTPS-only via `requiresChannel().requiresSecure()` or upstream LB; security headers via `HeadersConfigurer`.                |
| SSRF                          | `RestClient` / `WebClient` calls validate hostnames against an allowlist before request; no `RestTemplate.exchange(URI.create(userInput), ...)` with unvalidated URI.                                  |
| XSS                           | Thymeleaf auto-escapes - no `th:utext` on user input; no manual `Model.addAttribute(..., rawHtml)` rendered as `th:utext`. JSON responses set `Content-Type: application/json` to block sniff XSS.     |
| Insecure Design (A04)         | Method security (`@EnableMethodSecurity`) enabled and used; default-deny via `authorizeHttpRequests().anyRequest().authenticated()`.                                                                   |
| Vulnerable Components (A06)   | `./gradlew dependencyCheckAnalyze` (OWASP dep-check) clean; `./gradlew dependencyUpdates` reviewed; no Gradle / Maven entries with known CVEs.                                                         |
| Data Integrity Failures (A08) | No `ObjectInputStream.readObject` on untrusted input; `Jackson` typed-deserialization disabled (`enableDefaultTyping` off); SnakeYAML uses `SafeConstructor`.                                          |
| Logging & Monitoring (A09)    | Logback pattern excludes sensitive fields; `@JsonIgnore` on PII / secret fields in DTOs; no `log.info("user={}", user)` that serializes the entity. Security events (login fail, AccessDenied) logged. |

### Step 5 - Authentication (Spring Security 6.x / OAuth2 / JWT)

- [ ] **`SecurityFilterChain`** is explicit and version-current - the deprecated `WebSecurityConfigurerAdapter` does not exist (removed in 6.x); migrations from 5.x flagged
- [ ] **OAuth2 Resource Server**: `oauth2ResourceServer().jwt()` configured with explicit `JwtDecoder`; signature algorithm pinned; `JwtAuthenticationConverter` maps claims to authorities consistently
- [ ] **JWT issuer / audience** validated (`JwtValidators.createDefaultWithIssuer`, custom audience validator); not just signature
- [ ] **JWT no `alg: none`**: `JwtDecoder` rejects unsigned tokens; HMAC secret never falls back to a hardcoded default
- [ ] **Refresh token rotation**: short access-token lifetime (5-15 min); refresh tokens revocable; revocation list or JWT introspection at the gateway
- [ ] **Form login / Basic auth**: `BCryptPasswordEncoder` minimum strength 10; `DaoAuthenticationProvider` configured with `UserDetailsService`; no `NoOpPasswordEncoder` outside tests
- [ ] **Session fixation** protection enabled (`sessionManagement().sessionFixation().migrateSession()` - the default in Boot 3+); session cookie `Secure`, `HttpOnly`, `SameSite=Lax|Strict`
- [ ] **Brute-force protection**: rate limiting (Bucket4j, Resilience4j) on `/login`, `/oauth/token`, password reset
- [ ] **No credentials in `application.properties` / `application.yml` committed to git** - secrets via env vars, Vault, AWS Secrets Manager, or Spring Cloud Config; `master.key`-equivalent files gitignored
- [ ] **Actuator endpoints** (`/actuator/env`, `/actuator/heapdump`, `/actuator/loggers`) restricted: `management.endpoints.web.exposure.include` minimal in prod; remaining endpoints behind `ROLE_ACTUATOR`

### Step 6 - Authorization (Method Security / `@PreAuthorize` / Custom)

- [ ] **`@EnableMethodSecurity`** active; `@PreAuthorize` on every service method that touches user-owned resources (defense in depth alongside controller-level matchers)
- [ ] **Authorization drift sweep**: every new controller endpoint added in the diff has a corresponding `SecurityFilterChain` matcher OR a `@PreAuthorize` (or explicit `permitAll` with rationale)
- [ ] **IDOR (Insecure Direct Object Reference)**: lookups in user-facing services scope through the principal (`repository.findByIdAndOwnerId(id, principal.getId())` returning `Optional`) rather than `repository.findById(id)` followed by an authorization check (which leaks existence via 403 vs 404). For SpEL-based authorization, `@PostAuthorize("returnObject.ownerId == authentication.principal.id")` works for single-object reads but not collection reads.
- [ ] **Tenant isolation**: multi-tenant apps scope queries by `tenantId` in the repository layer (Hibernate `@Filter`, `@TenantId` in 6.x, or query-method parameter) - never rely on controller-level filtering alone
- [ ] **Default-deny** in `SecurityFilterChain`: `.anyRequest().authenticated()` after explicit allowlist; no trailing `.permitAll()`
- [ ] **CSRF**: enabled by default for stateful sessions; explicitly disabled (`csrf().disable()`) only for stateless JWT APIs with documented rationale
- [ ] **CORS**: `CorsConfigurationSource` bean with explicit `setAllowedOrigins` (not `"*"` for credentialed requests); `setAllowedMethods` and `setAllowedHeaders` minimal

### Step 7 - Input Validation and Mass Assignment

- [ ] **Bean Validation (`jakarta.validation`)** on every `@RequestBody` DTO: `@NotNull`, `@Size`, `@Email`, `@Pattern` etc.; `@Valid` on the controller parameter
- [ ] **Constructor / record DTOs** for input - immutable, no setters; avoids the "mass assignment" class of bugs because Jackson uses the constructor
- [ ] **No privilege-bearing fields in user-facing input DTOs**: `role`, `admin`, `ownerId`, `userId`, `tenantId`, `accountId`, `approved`, `status` (when status is a state-machine controlled by server logic) - these flip authorization or ownership and must be set by the server; if they appear in a `@RequestBody` record, require admin-only controller path with a separate DTO and `@PreAuthorize("hasRole('ADMIN')")`
- [ ] **No exposing entities directly** as `@RequestBody` - always a DTO/record; Jackson on a JPA entity can populate fields the API never intended to accept
- [ ] **File uploads** (`MultipartFile`):
  - File type validated by content (Apache Tika `Tika.detect`), not just `getContentType()` (client-controlled) or extension
  - Per-file size limit (`spring.servlet.multipart.max-file-size`) and total request size enforced
  - Saved files stored outside the webroot; `Content-Disposition: attachment` on serve to prevent inline rendering of HTML/SVG
  - Filename sanitized via `Path.normalize` and base-directory check before write
  - Virus scan pipeline or accepted-risk documented for user uploads
- [ ] **Path traversal**: `Path.resolve(userInput).normalize().startsWith(baseDir)` check on any user-controlled file operation
- [ ] **Process execution**: no `Runtime.exec`, `ProcessBuilder` with interpolated user input - use API alternatives or strict allowlist + tokenized arguments

### Step 8 - Common Spring Boot Vulnerability Patterns

- [ ] **CSRF token** on state-changing form requests; for SPAs, use `CookieCsrfTokenRepository.withHttpOnlyFalse()` so JS can read the token
- [ ] **CORS**: explicit origins (no `"*"` for credentialed endpoints)
- [ ] **Rate limiting**: Bucket4j, Resilience4j RateLimiter, or upstream LB / API gateway on `/login`, `/password`, `/signup`, `/oauth/token`, expensive search
- [ ] **SQL injection via dynamic sort / filter**: `Sort.by(sortField)` validated against an allowlist; no `entityManager.createQuery("... order by " + userField)`
- [ ] **Open redirect**: `response.sendRedirect(userInput)` validated against an allowlist; Spring MVC `redirect:` view with user-controlled destination guarded
- [ ] **Server-side template injection**: no Thymeleaf `${...}` expression evaluation on user-controlled template strings; SpEL evaluator never receives user input as the expression
- [ ] **Mass assignment via JSON**: `@RequestBody` uses DTOs / records, not entities (see Step 7)
- [ ] **Spring Boot Actuator exposure**: `info`, `health` only (or behind auth) in prod; `env`, `heapdump`, `loggers`, `mappings` never public
- [ ] **DevTools**: `spring-boot-devtools` is `developmentOnly` in Gradle / `<scope>runtime>` with `optional` in Maven - never shipped to prod
- [ ] **Spring4Shell-class CVEs**: `DataBinder` not bound to `Class` / `ClassLoader` properties; recent dep-check passes
- [ ] **H2 console** (`spring.h2.console.enabled`) disabled in non-dev profiles

### Step 9 - Data Protection

- [ ] **PII / sensitive fields encrypted** at rest (Jasypt, Spring Vault, or DB-native column encryption)
- [ ] **Logback / Logstash encoder masking** for sensitive keys (`password`, `token`, `creditCard`, `ssn`, `apiKey`); `@JsonIgnore` on the same DTO fields
- [ ] **No sensitive data in URLs** (use POST body, headers, or signed tokens)
- [ ] **TLS enforcement**: `server.ssl.enabled=true` or HTTPS-only at the LB; HSTS header set via `HeadersConfigurer`
- [ ] **Database backups** encrypted; access controlled
- [ ] **Secrets management**: Spring Cloud Config + Vault, AWS Secrets Manager, or env-var injection from a secret store - never `application-prod.yml` committed

## Rules

- Always validate at system boundaries (controller `@RequestBody`, external API responses, message payloads)
- Never disable CSRF or method security to silence a failing test - fix the test
- Never widen `@PreAuthorize` (e.g., from `hasRole('ADMIN')` to `permitAll`) without an explicit security review note
- Log security events (login failure, access denied, validation failure) without sensitive data
- Follow principle of least privilege - default-deny in `SecurityFilterChain`

## Self-Check

- [ ] Stack confirmed as Java / Spring Boot before any Spring-specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced (not executed by the workflow) and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
- [ ] Security surface (SecurityFilterChain bean, changed controllers, application.yml management/security keys, build dependencies, modified tests) read directly before applying checklists; prior revision consulted when annotations or matchers were removed
- [ ] OWASP Top 10 reviewed with Spring framing (Step 4) - every category checked, none silently skipped
- [ ] `spring-security-patterns` consulted for canonical Spring patterns
- [ ] Authentication step run for the auth mechanism in use (Spring Security 6.x form login / OAuth2 / JWT)
- [ ] **Authorization drift sweep**: every new controller endpoint in the diff has a matching `SecurityFilterChain` matcher or `@PreAuthorize`
- [ ] Bean Validation reviewed on every `@RequestBody`; entities are never accepted as input DTOs
- [ ] File upload, path traversal, and process-execution checks run if applicable
- [ ] CSRF, CORS, rate limiting, open redirect, Actuator exposure, and DevTools gating verified
- [ ] Every finding includes an attack scenario - not just "input not validated"
- [ ] If no findings: explicitly state "No issues found" per category - do not omit sections silently
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Critical > High > Medium > Low (omitted only when no security issues exist)

## Output Format

```markdown
## Spring Boot Security Review Summary

**Stack Detected:** Java <version> / Spring Boot <version>
**Auth:** Spring Security Form Login | OAuth2 Resource Server (JWT) | OAuth2 Client | Custom | Hybrid
**Authorization:** SecurityFilterChain matchers | @PreAuthorize / @PostAuthorize | Custom
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment of the overall security posture, calling out any Spring-specific risks like missing `@PreAuthorize`, deprecated `WebSecurityConfigurerAdapter` patterns, or exposed Actuator endpoints.]

## Findings

### Critical

- **Location:** [file:line]
- **Issue:** [vulnerability described in Spring terms - e.g., "@RequestBody binds entity directly in OrderController#update, allowing mass assignment of `ownerId`"]
- **Attack scenario:** [how an attacker exploits this - e.g., "Attacker submits `{\"ownerId\": 999}` and reassigns the order to themselves via mass assignment"]
- **Fix:** [specific Spring remediation with code example - DTO record, `@PreAuthorize`, BCrypt encoder, etc.]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit severity sections with no findings. If all sections are omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening that is not a specific finding - e.g., "Add Bucket4j rate limit on /oauth/token", "Migrate from `WebSecurityConfigurerAdapter` (already removed) to `SecurityFilterChain` bean", "Move secrets from `application-prod.yml` to Vault"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting hardening, dependency upgrade, or threat-model exercise worth spawning a subagent for). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action, e.g., "Replace OrderController @RequestBody Order with OrderUpdateRequest record (no `ownerId`)"]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action, e.g., "Run OWASP dependency-check and upgrade flagged libraries - spawn dependency-review subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if no security issues were found._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `{\"role\":\"ADMIN\"}` and gains admin via mass assignment")
- Skipping OWASP categories that appear clean - explicitly state "No issues found" per category
- Recommending generic security advice when a Spring idiom applies (say "add `@PreAuthorize(\"hasRole('ADMIN')\")`", not "add an authorization check")
- Suggesting `csrf().disable()` as a fix for a failing form submission - validate the test sends a CSRF token instead
- Disabling `@EnableMethodSecurity` to silence a missing `@PreAuthorize` warning - add the missing annotation
- Conflating security review with general code quality or performance review - delegate those to their workflows
- Recommending `WebSecurityConfigurerAdapter` patterns (removed in Spring Security 6) - always use `SecurityFilterChain` beans
