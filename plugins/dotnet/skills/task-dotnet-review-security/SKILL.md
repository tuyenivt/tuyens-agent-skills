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

.NET-aware security review naming ASP.NET Core auth middleware, JWT `TokenValidationParameters`, FluentValidation, EF Core parameterization, `IPasswordHasher` / BCrypt / Argon2, and .NET-specific deserialization / process / path risks directly. Findings include an attack scenario and a concrete .NET remediation.

Stack-specific delegate of `task-code-review-security` for .NET / ASP.NET Core.

## When to Use

- .NET / ASP.NET Core PR for security regressions
- Pre-deployment hardening on auth, authz, file upload, payment, PII paths
- Validation / middleware drift sweep across endpoints
- Auditing a JWT flow, new authorization policy, or new `unsafe` / crypto usage

**Not for:**

- Performance (`task-code-review-perf` or `task-dotnet-review-perf`)
- General review (`task-code-review` or `task-dotnet-review`)
- Incident triage (`/task-oncall-start`)

This workflow always runs at full depth - security review has cliff-edged consequences (auth bypass, RCE). Scope by file, not by depth.

## Severity Rubric

| Severity     | Definition                                                                                                                                                                                                                                                |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauthenticated RCE; auth bypass; mass data exfiltration; working SQL injection (`FromSqlRaw($"...{input}")`, `ExecuteSqlRaw($"...{input}")`); `Process.Start` shell injection; JWT `alg: none` accepted; signing key committed; `BinaryFormatter` / `TypeNameHandling.All` on untrusted input; `unsafe` block with attacker-controlled inputs. Blocks merge. |
| **High**     | Authenticated privilege escalation; IDOR on sensitive data; SSRF to metadata / internal services; mass assignment via `[FromBody] DomainEntity`; missing `[Authorize]` on user-data endpoint; `Path.Combine` without canonical base check; missing CSRF on cookie-auth POST. Must fix before merge. |
| **Medium**   | Hardening gap with mitigating control elsewhere; missing FluentValidation on non-critical endpoint; weak rate limit on non-critical endpoint; debug surface reachable on non-prod profile only; `dotnet list package --vulnerable` advisory not yet exploited. Fix this PR or next. |
| **Low**      | Defense-in-depth nice-to-have; advisory below actively-exploited threshold; hardening without a concrete current attack scenario.                                                                                                                          |

**Combined-finding rule.** If the realistic exploit requires both findings on the *same action* to land, file them as one finding at the elevated severity citing each component. If either is exploitable alone, file separately. Example: missing `[Authorize]` (High) + `[FromBody] User` mass assignment (High) on the same action = **Critical** unauthenticated admin override.

**Same-action gate.** If co-location is not obvious from the diff (e.g., the IDOR is in `GetOrder`, the entity leak is in `UpdateOrder`), file separately and add `Note: combine if both land on the same action` to the lower-severity entry. Do not silently merge.

## Invocation

| Invocation                              | Meaning                                                         |
| --------------------------------------- | --------------------------------------------------------------- |
| `/task-dotnet-review-security`          | Current branch vs base; fails fast on trunk                     |
| `/task-dotnet-review-security <branch>` | `<branch>` vs base (3-dot diff)                                 |
| `/task-dotnet-review-security pr-<N>`   | PR head fetched into `pr-<N>` (user runs fetch first)           |

When invoked as a subagent of `task-code-review-security` or `task-dotnet-review`, the parent passes the precondition handle + pre-read diff and commit log; Step 3 below is skipped.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed stack from a parent. If not .NET / ASP.NET Core, stop and tell the user to invoke `/task-code-review-security`.

Record `Data Access` (EF Core / Dapper / mixed), `JWT Library` (typically `Microsoft.AspNetCore.Authentication.JwtBearer`), and `Password Hash` library for the Summary.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent.

If precondition check stops with a fail-fast message, surface verbatim and stop. No state-changing git.

### Step 4 - Read the Security Surface

- `Program.cs` / `Startup.cs` - middleware order (`UseExceptionHandler` -> `UseHsts` -> `UseHttpsRedirection` -> `UseRouting` -> `UseCors` -> `UseAuthentication` -> `UseAuthorization` -> `MapControllers`), `AddAuthentication().AddJwtBearer(...)`, `AddAuthorization(...)`, `AddCors`, rate limiter, `UseHangfireDashboard` / `UseSwaggerUI` gating
- JWT bearer config: `JwtBearerOptions.TokenValidationParameters` (algorithm allowlist, issuer, audience, lifetime)
- Every changed action - `[Authorize]` / `[AllowAnonymous]` / `[Authorize(Policy=...)]`, request DTO type, FluentValidation validator, ownership check in handler
- Every changed query - parameterization (`FromSqlInterpolated` / LINQ vs `FromSqlRaw($"...")`)
- `Migrations/` - new PII / auth columns, missing `NOT NULL` on tenant FKs, `migrationBuilder.Sql("GRANT ...")`, audit columns that imply new sensitive fields the response DTO may now leak
- `appsettings*.json`, `IConfiguration` reads for `Jwt:Key`, allowed origins; `.csproj` / `Directory.Packages.props` for package versions

When the diff removes a middleware or relaxes auth, `git log -p` the prior revision - blame is the authoritative answer to "did this weaken authorization."

### Step 5 - OWASP Triage (.NET Lens)

Use skill: `dotnet-security-patterns` for canonical patterns.

Mark each category `yes` (signal present in diff) or `no signal in diff`. Steps 6-10 produce the actual findings.

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

### Step 6 - Authentication

- [ ] **JWT signing key** sourced from env / Vault / `dotnet user-secrets`, never committed. Any literal `SymmetricSecurityKey(Encoding.UTF8.GetBytes("..."))` in source is Critical (anyone with repo read access can forge tokens). HS256 ≥ 256-bit; RS256 / ES256 preferred for cross-service
- [ ] **Algorithm allowlist explicit**: `TokenValidationParameters.ValidAlgorithms = new[] { SecurityAlgorithms.RsaSha256 }`. Default handler historically accepted any `alg`, including `none`
- [ ] **All `Validate*` parameters `true`**: `ValidateIssuer`, `ValidateAudience`, `ValidateLifetime`, `ValidateIssuerSigningKey`; `ValidIssuer` / `ValidAudience` / `IssuerSigningKey` set; `ClockSkew = TimeSpan.FromSeconds(30)` (default 5 min is loose). Any `Validate* = false` in the diff is at minimum High
- [ ] **Access token life** 5-15 min; refresh tokens rotated and revocable via DB / Redis denylist (track `jti` or refresh GUID)
- [ ] **Password hashing**: `IPasswordHasher<TUser>` (PBKDF2), `BCrypt.Net-Next` (work factor ≥ 11), or `Konscious.Security.Cryptography.Argon2`. Never `MD5` / `SHA*` for passwords. Compare with `CryptographicOperations.FixedTimeEquals`
- [ ] **Middleware order**: `UseAuthentication()` before `UseAuthorization()`; `[Authorize]` on protected actions
- [ ] **Brute-force protection** on `/auth/login`, `/auth/refresh`, `/auth/reset-password` via `AddRateLimiter` (`FixedWindowLimiter` / `SlidingWindowLimiter` / `TokenBucketLimiter`), stricter than global
- [ ] **Cookie sessions** (when used): `Secure`, `HttpOnly`, `SameSite=Lax`; data protection keys persisted with rotation

### Step 7 - Authorization

- [ ] **Authorization drift sweep**: every new action has `[Authorize]` (or `[Authorize(Policy=...)]`) OR explicit `[AllowAnonymous]` when the controller is not `[Authorize]`-decorated
- [ ] **Policy-based**: `AddPolicy("CanEditOrders", p => p.RequireRole("Admin").RequireClaim("permission","orders:write"))`, applied via `[Authorize(Policy="CanEditOrders")]`. Not inline `if (!User.IsInRole(...))` scattered across actions
- [ ] **Resource-based** for per-owner data: `IAuthorizationService.AuthorizeAsync(User, order, "OrderOwnerOrAdmin")` with an `AuthorizationHandler<TRequirement, Order>`
- [ ] **IDOR**: lookups scope through principal in the query (`Where(o => o.Id == id && o.OwnerId == User.GetUserId())`) rather than `Where(o => o.Id == id)` + post-hoc check
- [ ] **Tenant isolation** via EF Core global query filters (`HasQueryFilter(o => o.TenantId == _tenantContext.TenantId)`) or at the repository layer, not the controller
- [ ] **CORS**: `WithOrigins("https://app.example.com").AllowCredentials()` allowlist; flag `SetIsOriginAllowed(_ => true)` workarounds
- [ ] **CSRF / antiforgery**: not required for stateless bearer JWT; required for cookie-session apps via `AddAntiforgery` + `[ValidateAntiForgeryToken]` / `AutoValidateAntiforgeryTokenAttribute` on POST/PUT/DELETE

### Step 8 - Input Validation and Mass Assignment

- [ ] **`[ApiController]` auto-validation OR FluentValidation** registered via `AddValidatorsFromAssemblyContaining<...>()`. Bare `[FromBody] JsonElement` / `JObject` / `Dictionary<string,object>` is anything-goes
- [ ] **FluentValidation rules on every DTO field**: `RuleFor(x => x.Email).NotEmpty().EmailAddress()`, `RuleFor(x => x.Quantity).GreaterThan(0)`
- [ ] **No domain entity as input**: `[FromBody] DomainEntity` or `JsonSerializer.Deserialize<DomainEntity>(body)` is mass assignment. Define a typed request DTO record, validate, then map with explicit field assignment. Privileged fields (`Role`, `IsAdmin`, `OwnerId`, `UserId`, `TenantId`, `IsActive`, `Verified`) and identity/cache-key fields (`Id`, `CreatedAt`, plus any field used as an `IMemoryCache` key) must never appear in user-facing DTOs - the cache-key case is mass assignment even when the field looks innocuous (client writes attacker payload, victim reads it on next lookup)
- [ ] **Response DTOs (not entities)**: `Ok(OrderResponse.From(order))` maps explicitly, dropping `PasswordHash`, `RecoveryToken`, `MfaSecret`, soft-delete flags, internal audit fields, and any sensitive column added later
- [ ] **Typed model binding**: `[FromRoute] Guid id` / `[FromQuery] ListFilters filters` (with validator) - never `[FromRoute] string id`
- [ ] **File uploads** (`IFormFile`): content-based type check (magic bytes via `FileTypeChecker`, not `ContentType` or extension); size limit via `[RequestSizeLimit]` and Kestrel `MaxRequestBodySize`; stored outside webroot with `Content-Disposition: attachment`; filename canonicalized (see path traversal); virus scan or accepted-risk documented
- [ ] **Path traversal**: canonicalize and check base.

```csharp
// BAD
var path = Path.Combine(baseDir, userInput); // ../ not resolved
// GOOD
var canonical = Path.GetFullPath(Path.Combine(baseDir, userInput));
if (!canonical.StartsWith(baseDir, StringComparison.Ordinal)) throw new SecurityException();
```

- [ ] **Process execution**: arg-list form is safe; shell form is RCE.

```csharp
// BAD - RCE
Process.Start("cmd.exe", $"/c convert {userInput}");
// GOOD - arg-list, no shell
Process.Start(new ProcessStartInfo("convert") { ArgumentList = { userInput, "/tmp/out" } });
```

### Step 9 - Common .NET Vulnerability Patterns

- [ ] **SQL injection**: `FromSqlRaw($"...{input}")` / `ExecuteSqlRaw($"...{input}")` / Dapper `QueryAsync($"...{input}")` is injection. Use `FromSqlInterpolated($"... WHERE id = {id}")`, `FromSqlRaw("... WHERE id = {0}", id)`, LINQ, or Dapper `QueryAsync("... WHERE id = @id", new { id })`
- [ ] **Unsafe deserializers on untrusted input**: any reintroduction of `BinaryFormatter.Deserialize` (Critical; deprecated since .NET 5); `Newtonsoft.Json` `TypeNameHandling.All` / `Auto` / `Objects` (RCE via `$type` gadget chains - use `TypeNameHandling.None` or `System.Text.Json`); `XmlSerializer` / `XmlReader` / `DataContractSerializer` without `XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit, XmlResolver = null }` (XXE)
- [ ] **SSTI**: `RazorLight` / `RazorEngine` with user-controlled template source. Templates from disk or trusted constants only
- [ ] **`unsafe` blocks**: every `unsafe { ... }` in the diff has a `// SAFETY:` comment justifying invariants. Most are smells (P/Invoke, `Span<T>` interop excepted)
- [ ] **`HttpClientHandler.ServerCertificateCustomValidationCallback = (_, _, _, _) => true`**: flag unless behind a documented test fixture
- [ ] **Open redirect**: `Redirect(userInput)` validated against allowlist or `Url.IsLocalUrl(target)`
- [ ] **CSPRNG for tokens / nonces / secrets**: `RandomNumberGenerator.GetBytes(...)` / `GetInt32(...)`, never `Random`
- [ ] **Constant-time comparison**: `CryptographicOperations.FixedTimeEquals(actual, expected)` for HMAC / webhook signatures - never `==`, `Equals`, or `SequenceEqual` on `byte[]`
- [ ] **Debug exposure**: `UseDeveloperExceptionPage` not in prod; `UseSwagger` / `UseSwaggerUI` gated by `env.IsDevelopment()` or auth; `UseHangfireDashboard` with an explicit `Authorization` filter (default `LocalRequestsOnlyAuthorizationFilter` is reachable from cluster network)
- [ ] **SSRF depth**: when user input flows into an outbound URL, reject (a) `169.254.169.254` (cloud metadata) and IPv6 equivalent, (b) localhost / `127.0.0.0/8` / `::1`, (c) RFC1918 (`10/8`, `172.16/12`, `192.168/16`), (d) link-local `169.254/16`. Re-resolve at request time (DNS rebinding); guard against `Uri` parsing quirks (backslash, `::ffff:127.0.0.1`)
- [ ] **Background-worker payload trust**: MassTransit / Hangfire consumers validate payloads inside the handler when the queue is reachable from untrusted inputs (webhook -> job)
- [ ] **Webhook signature verification**: read raw body via `Request.EnableBuffering()` before model binding consumes it; compare with `FixedTimeEquals`
- [ ] **NuGet hygiene**: `dotnet list package --vulnerable --include-transitive` in CI, or `<NuGetAudit>true</NuGetAudit>` (.NET 8+); flag unaddressed High/Critical CVEs

### Step 10 - Data Protection

- [ ] **PII / sensitive fields encrypted at rest** (`AesGcm` with proper nonce management, AWS KMS / Azure Key Vault, or DB-native column encryption)
- [ ] **No EF entity returned from actions**: `Ok(user)` leaks every property the entity defines and every column added later. Map to a response DTO record that names exactly the public fields
- [ ] **`ILogger` / Serilog redaction**: never log `password`, `token`, `Authorization`, `Cookie`, `credit_card`, `ssn`, `api_key`. Serilog `Destructure.ByTransforming<User>(u => new { u.Id, u.TenantId })`
- [ ] **No sensitive data in URLs** (POST body, headers, or signed tokens) - URLs hit logs, browser history, referrer headers
- [ ] **TLS enforcement**: `UseHttpsRedirection()` + `UseHsts()` (prod); Kestrel HTTPS endpoint configured
- [ ] **Secrets management**: Azure Key Vault / AWS Secrets Manager / HashiCorp Vault / `dotnet user-secrets` (dev). Never committed `appsettings.Production.json`. `IOptions<JwtOptions>` loaded once at startup so missing-at-startup fails fast

### Step 11 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`. Write to the report file before ending; print confirmation.

## Self-Check

- [ ] Behavioral principles loaded as Step 1
- [ ] Stack confirmed as .NET / ASP.NET Core; data-access, JWT library, password-hash library recorded
- [ ] `review-precondition-check` ran (or handle received); refs captured; diff and commit log read once and reused
- [ ] When `head_matches_current` was false, explicit approval obtained (skipped as subagent)
- [ ] Security surface (Program.cs / middleware order, JWT config, policies, settings, changed controllers, DTOs) read; prior revision consulted when middleware was removed
- [ ] OWASP triage produced one verdict per category (`yes` / `no signal in diff`); not duplicated as standalone findings
- [ ] Authentication checks run for the auth mechanism in use
- [ ] **Authorization drift sweep**: every new action has `[Authorize]` / `[AllowAnonymous]` (or controller-level coverage)
- [ ] DTO validation, mass-assignment fields, separate request vs response DTOs confirmed; file upload / path traversal / `Process.Start` checks run when touched
- [ ] SQL parameterization, unsafe deserializers, SSTI, `unsafe`, `ServerCertificateCustomValidationCallback`, open redirect, CSPRNG, constant-time compare, debug exposure, SSRF depth, webhook signature checked when the diff touches them
- [ ] Data protection: no EF entity in responses; logger redaction; TLS / HSTS; secrets sourcing reviewed when in scope
- [ ] Severity rubric applied consistently; combined-finding rule applied only when both findings land on the same action
- [ ] Every finding includes an attack scenario, regression-risk rationale (test-coverage gaps), or topology-dependent framing (infra-flavored) - labeled which
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered Critical > High > Medium > Low (omitted only when no findings)
- [ ] Report written via `review-report-writer`; confirmation printed

**Could not verify from diff alone** - note as "flag for separate audit" when not visible: `dotnet list package --vulnerable` clean; Sentry / Application Insights `BeforeSend` strips PII; password-hash work factor in config; CORS / rate-limit / secure-header middleware when not in diff.

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

[Prioritized hardening not tied to a specific finding - e.g., "Add `AddRateLimiter` on /auth/login", "Migrate to Argon2id", "Move `Jwt:Key` to Azure Key Vault", "Enable `<NuGetAudit>true</NuGetAudit>`", "Default-deny via `FallbackPolicy = RequireAuthenticatedUser()`"]

## Next Steps

Prioritized, each tagged `[Implement]` (localized fix) or `[Delegate]` (cross-cutting hardening, dep upgrade, threat-model). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action, e.g., "Replace `[FromBody] Order` with typed `UpdateOrderRequest` record + explicit field copy"]
2. **[Delegate]** [High] [scope: dependencies] - [e.g., "Run `dotnet list package --vulnerable` and upgrade flagged packages"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit if no security issues._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git from this workflow
- Vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `{\"Role\":\"Admin\"}` and gains admin via mass assignment because action binds into `User` entity")
- Skipping OWASP categories that appear clean - explicitly state "No issues found"
- Generic security advice when a .NET idiom applies (say `[Authorize(Policy="...")]` + registered policy + handler, not "add an authorization check")
- Recommending `FromSqlRaw($"...")` as acceptable - parameterize via `FromSqlInterpolated` or positional args
- Recommending `[FromBody] DomainEntity`, `BinaryFormatter`, `TypeNameHandling.All/Auto/Objects`, `==` on `byte[]` for HMAC, `Random` for tokens, `ServerCertificateCustomValidationCallback = true` outside test fixtures, `XmlSerializer` without `DtdProcessing.Prohibit`, or `unsafe` without `// SAFETY:` comment
- Approving Hangfire / Swagger UI exposed in prod without auth filter
- Approving `UseDeveloperExceptionPage` left enabled in prod
- Disabling middleware to silence a failing test - fix the test
- Conflating security review with code quality or performance review - delegate to those workflows
