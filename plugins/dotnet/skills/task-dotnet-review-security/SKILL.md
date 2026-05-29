---
name: task-dotnet-review-security
description: ".NET / ASP.NET Core security review: JWT auth, FluentValidation, EF Core parameterization, mass assignment, secrets, OWASP Top 10."
agent: dotnet-security-engineer
metadata:
  category: backend
  tags: [dotnet, aspnet-core, security, jwt, owasp, dotnet-audit, workflow]
  type: workflow
user-invocable: true
---

# .NET Security Review

Stack-specific delegate of `task-code-review-security` for .NET / ASP.NET Core. Names ASP.NET Core auth middleware, JWT `TokenValidationParameters`, FluentValidation, EF Core parameterization, `IPasswordHasher` / BCrypt / Argon2, and .NET-specific deserialization / process / path risks directly. Findings include an attack scenario and a concrete .NET remediation.

## When to Use

- .NET / ASP.NET Core PR for security regressions
- Pre-deployment hardening on auth, authz, file upload, payment, PII paths
- Validation / middleware drift sweep across endpoints
- Auditing a JWT flow, new authorization policy, or new `unsafe` / crypto usage

**Not for:** performance (`task-dotnet-review-perf`); general review (`task-dotnet-review`); incident triage (`/task-oncall-start`).

This workflow always runs at full depth - security review has cliff-edged consequences (auth bypass, RCE). Scope by file, not by depth.

## Severity Rubric

| Severity     | Definition |
| ------------ | ---------- |
| **Critical** | Unauthenticated RCE; auth bypass; mass data exfiltration; working SQL injection (`FromSqlRaw($"...{input}")`, `ExecuteSqlRaw($"...{input}")`); `Process.Start` shell injection; JWT `alg: none` accepted; signing key committed; `BinaryFormatter` / `TypeNameHandling.All` on untrusted input; `unsafe` block with attacker-controlled inputs. Blocks merge. |
| **High**     | Authenticated privilege escalation; IDOR on sensitive data; SSRF to metadata / internal services; mass assignment via `[FromBody] DomainEntity`; missing `[Authorize]` on user-data endpoint; `Path.Combine` without canonical base check; missing CSRF on cookie-auth POST. Must fix before merge. |
| **Medium**   | Hardening gap with mitigating control elsewhere; missing FluentValidation on non-critical endpoint; weak rate limit on non-critical endpoint; debug surface reachable on non-prod profile only; `dotnet list package --vulnerable` advisory not yet exploited. Fix this PR or next. |
| **Low**      | Defense-in-depth nice-to-have; advisory below actively-exploited threshold; hardening without a concrete current attack scenario. |

**Combined-finding rule.** If the realistic exploit requires both findings on the *same action* to land, file as one finding at the elevated severity citing each component. If either is exploitable alone, file separately. Example: missing `[Authorize]` (High) + `[FromBody] User` mass assignment (High) on the same action = **Critical** unauthenticated admin override.

**Same-action gate.** If co-location is not obvious from the diff (e.g., IDOR in `GetOrder`, entity leak in `UpdateOrder`), file separately and add `Note: combine if both land on the same action` to the lower-severity entry. Never silently merge.

## Invocation

| Invocation                              | Meaning                                                         |
| --------------------------------------- | --------------------------------------------------------------- |
| `/task-dotnet-review-security`          | Current branch vs base; fails fast on trunk                     |
| `/task-dotnet-review-security <branch>` | `<branch>` vs base (3-dot diff)                                 |
| `/task-dotnet-review-security pr-<N>`   | PR head fetched into `pr-<N>` (user runs fetch first)           |

When invoked as a subagent of `task-code-review-security` or `task-dotnet-review`, the parent passes the precondition handle + pre-read diff and commit log; Step 3 is skipped.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. If not .NET / ASP.NET Core, stop and route to `/task-code-review-security`. Accept parent's pre-confirmed stack.

Record `Data Access` (EF Core / Dapper / mixed), `JWT Library` (typically `Microsoft.AspNetCore.Authentication.JwtBearer`), `Password Hash` library.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. If precondition stops, surface verbatim and stop. No state-changing git. Skip when running as subagent.

### Step 4 - Read the Security Surface

- `Program.cs` / `Startup.cs` - middleware order (`UseExceptionHandler` -> `UseHsts` -> `UseHttpsRedirection` -> `UseRouting` -> `UseCors` -> `UseAuthentication` -> `UseAuthorization` -> `MapControllers`), `AddAuthentication().AddJwtBearer(...)`, `AddAuthorization(...)`, `AddCors`, rate limiter, `UseHangfireDashboard` / `UseSwaggerUI` gating
- JWT bearer config: `JwtBearerOptions.TokenValidationParameters` (algorithm allowlist, issuer, audience, lifetime)
- Every changed action - `[Authorize]` / `[AllowAnonymous]` / `[Authorize(Policy=...)]`, request DTO type, FluentValidation validator, ownership check in handler
- Every changed query - parameterization (`FromSqlInterpolated` / LINQ vs `FromSqlRaw($"...")`)
- `Migrations/` - new PII / auth columns, missing `NOT NULL` on tenant FKs, `migrationBuilder.Sql("GRANT ...")`, audit columns that imply new sensitive fields the response DTO may now leak
- `appsettings*.json`, `IConfiguration` reads for `Jwt:Key`, allowed origins; `.csproj` / `Directory.Packages.props` for package versions

When the diff removes a middleware or relaxes auth, `git log -p` the prior revision - blame is the authoritative answer to "did this weaken authorization."

### Step 5 - Apply .NET Security Patterns

Use skill: `dotnet-security-patterns` for canonical guidance on auth, authz, validation, mass assignment, SQL injection, unsafe deserializers, SSRF depth, path traversal, process execution, CSPRNG, constant-time compare, debug exposure, secrets, TLS, and data protection.

Apply its rules against the diff. The atomic owns the patterns; this workflow owns the **gates** below.

**Workflow gates (always evaluated):**

- [ ] **Authorization drift sweep** - every new action has `[Authorize]` / `[Authorize(Policy=...)]` OR explicit `[AllowAnonymous]` when the controller is not `[Authorize]`-decorated. Missing -> High
- [ ] **Mass-assignment fields** - request DTO does not include `Role`, `IsAdmin`, `OwnerId`, `UserId`, `TenantId`, `IsActive`, `Verified`, `Id`, `CreatedAt`, or any field used as an `IMemoryCache` key (cache-key fields are mass assignment even when innocuous: client writes attacker payload, victim reads on next lookup)
- [ ] **Response shape** - actions return DTO records, not EF entities (`Ok(user)` leaks every column added later)
- [ ] **JWT validation parameters** - all `Validate*` flags `true`, `ValidAlgorithms` allowlist set, `ClockSkew` <= 30s. Any `Validate* = false` in the diff -> at minimum High
- [ ] **Signing key sourcing** - no literal `SymmetricSecurityKey(Encoding.UTF8.GetBytes("..."))` in source -> Critical when present
- [ ] **Middleware order** - `UseAuthentication()` before `UseAuthorization()`
- [ ] **Same-action combined-finding rule** applied per the rubric

### Step 6 - OWASP Triage (.NET Lens)

Mark each category `yes` (signal present in diff) or `no signal in diff`. This populates the Output Format table; the actual findings come from Step 5.

| Risk                          | .NET-specific signal in diff                                                                                                                                                  |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | New action without `[Authorize]` / `[AllowAnonymous]`; missing ownership check in handler                                                                                     |
| Injection                     | `FromSqlRaw($"...{input}")` / `ExecuteSqlRaw($"...{input}")` / Dapper `$"...{input}"`; `Process.Start("cmd.exe", $"/c {input}")` shell-out                                    |
| Cryptographic Failures        | Hardcoded `SymmetricSecurityKey(Encoding.UTF8.GetBytes("literal"))`; `MD5` / `SHA1` / raw `SHA256` for passwords; `Random` for tokens                                          |
| Security Misconfiguration     | `SetIsOriginAllowed(_ => true)` + `AllowCredentials`; `UseDeveloperExceptionPage` in prod; Hangfire / Swagger UI exposed without auth; missing HSTS                            |
| SSRF                          | `HttpClient.GetAsync(userControlledUrl)` without hostname allowlist (no RFC1918 / link-local / `169.254.169.254` rejection, no re-resolve at request time)                     |
| XSS                           | `@Html.Raw(...)` on user content; `Response.WriteAsync($"<div>{user}</div>")`                                                                                                  |
| Insecure Design (A04)         | Controllers default-allow rather than `FallbackPolicy = RequireAuthenticatedUser()` with explicit `[AllowAnonymous]` opt-outs                                                  |
| Vulnerable Components (A06)   | `packages.lock.json` change with stale CVE; `dotnet list package --vulnerable` / `<NuGetAudit>true</NuGetAudit>` not in CI                                                     |
| Data Integrity Failures (A08) | `[FromBody] DomainEntity` / `JsonSerializer.Deserialize<DomainEntity>(body)` (mass assignment); `BinaryFormatter.Deserialize`; `Newtonsoft.Json` `TypeNameHandling.All/Auto/Objects`; `XmlSerializer` / `XmlReader` without `DtdProcessing.Prohibit`; `unsafe` |
| Logging & Monitoring (A09)    | `ILogger` logs `password` / `token` / `Authorization` / `Cookie`; missing auth-event logging; Sentry / Application Insights without PII-stripping `BeforeSend`                  |

### Step 7 - Note Out-of-Diff Audits

Note as "flag for separate audit" when not visible in diff: `dotnet list package --vulnerable` cleanliness; Sentry / Application Insights `BeforeSend` PII strip; password-hash work factor in config; CORS / rate-limit / secure-header middleware when not in diff.

### Step 8 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`. Write to the report file; print confirmation.

## Self-Check

- [ ] Step 1 - behavioral principles loaded
- [ ] Step 2 - stack confirmed; data-access, JWT library, password-hash library recorded
- [ ] Step 3 - `review-precondition-check` ran (or handle received); diff and commit log read once; explicit approval obtained when `head_matches_current` was false
- [ ] Step 4 - security surface read; prior revision consulted when middleware was removed
- [ ] Step 5 - `dotnet-security-patterns` applied; workflow gates (drift sweep, mass-assignment fields, response shape, JWT params, signing key, middleware order, combined-finding rule) evaluated
- [ ] Step 6 - OWASP triage produced one verdict per category; not duplicated as standalone findings
- [ ] Step 7 - out-of-diff audits flagged
- [ ] Step 8 - report written via `review-report-writer`; confirmation printed
- [ ] Every finding includes an attack scenario, regression-risk rationale (test-coverage gaps), or topology-dependent framing (infra-flavored) - labeled which
- [ ] Severity rubric applied consistently; combined-finding rule applied only when both land on the same action
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Critical > High > Medium > Low (omitted only when no findings)

## Output Format

```markdown
## .NET Security Review Summary

**Stack Detected:** .NET <version> / ASP.NET Core <version>
**Data Access:** EF Core <version> | Dapper <version> | mixed
**JWT Library:** Microsoft.AspNetCore.Authentication.JwtBearer | none
**Password Hash:** IPasswordHasher (PBKDF2) | BCrypt.Net-Next | Konscious Argon2 | none
**Authorization:** policy-based + resource-based + ownership checks | inline | none
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment; call out .NET-specific risks: missing `[Authorize]`, `[FromBody] DomainEntity` mass assignment, `FromSqlRaw($"...")`, Hangfire / Swagger UI exposed, `ServerCertificateCustomValidationCallback = true`, `unsafe` without SAFETY comment.]

## OWASP Triage

| Category                  | Verdict                 |
| ------------------------- | ----------------------- |
| Broken Access Control     | yes / no signal in diff |
| Injection                 | yes / no signal in diff |
| Cryptographic Failures    | ...                     |
| Security Misconfiguration | ...                     |
| SSRF                      | ...                     |
| XSS                       | ...                     |
| Insecure Design           | ...                     |
| Vulnerable Components     | ...                     |
| Data Integrity Failures   | ...                     |
| Logging & Monitoring      | ...                     |

## Findings

### Critical

- **Location:** [file:line]
- **Issue:** [vulnerability in .NET terms - e.g., "OrdersController.Update binds `[FromBody] Order request` (EF entity); client submits `{\"OwnerId\":\"...999\"}` and overrides server-assigned owner because no separate request DTO is used"]
- **Attack scenario:** [one of: (a) concrete exploit walkthrough; (b) "Regression risk: ..." for test-coverage / monitoring gaps; (c) "Topology-dependent: ..." for infra-flavored findings. Label which.]
- **Severity rationale:** [tier] per rubric - [which clause applies]
- **Fix:** [.NET remediation with code - typed request DTO + explicit copy, `Where(o => o.Id == id && o.OwnerId == User.GetUserId())`, `[Authorize(Policy="...")]`, etc.]

### High
[Same structure]

### Medium
[Same structure]

### Low
[Same structure]

_Omit empty severity sections. If all omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening not tied to a specific finding - "Add `AddRateLimiter` on /auth/login", "Migrate to Argon2id", "Move `Jwt:Key` to Azure Key Vault", "Enable `<NuGetAudit>true</NuGetAudit>`", "Default-deny via `FallbackPolicy = RequireAuthenticatedUser()`"]

## Next Steps

Prioritized, each tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting hardening, dep upgrade, threat-model). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action, e.g., "Replace `[FromBody] Order` with typed `UpdateOrderRequest` record + explicit field copy"]
2. **[Delegate]** [High] [scope: dependencies] - [e.g., "Run `dotnet list package --vulnerable` and upgrade flagged packages"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit if no security issues._
```

## Avoid

- State-changing git from this workflow
- Vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `{\"Role\":\"Admin\"}` and gains admin via mass assignment because action binds into `User` entity")
- Skipping OWASP categories that appear clean - explicitly state "no signal in diff"
- Generic security advice when a .NET idiom applies (say `[Authorize(Policy="...")]` + registered policy + handler, not "add an authorization check")
- Recommending `FromSqlRaw($"...")`, `[FromBody] DomainEntity`, `BinaryFormatter`, `TypeNameHandling.All/Auto/Objects`, `==` on `byte[]` for HMAC, `Random` for tokens, `ServerCertificateCustomValidationCallback = true` outside test fixtures, `XmlSerializer` without `DtdProcessing.Prohibit`, or `unsafe` without `// SAFETY:` comment
- Approving Hangfire / Swagger UI exposed in prod without auth, or `UseDeveloperExceptionPage` left enabled in prod
- Disabling middleware to silence a failing test - fix the test
- Conflating security review with code quality or performance review - delegate
