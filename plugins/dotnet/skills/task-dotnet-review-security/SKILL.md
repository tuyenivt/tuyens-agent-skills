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

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# .NET Security Review

## Purpose

.NET-aware security review that names ASP.NET Core authentication middleware (`AddAuthentication().AddJwtBearer(...)`, `AddAuthorization(options => options.AddPolicy(...))`), JWT validation parameters (`TokenValidationParameters` - `ValidateIssuer`, `ValidateAudience`, `ValidateLifetime`, `ValidateIssuerSigningKey`, signing algorithm allowlist), FluentValidation input validation, EF Core parameterization (`FromSqlInterpolated` vs `FromSqlRaw($"...")`), password hashing (`Microsoft.AspNetCore.Identity.PasswordHasher<T>` (PBKDF2), `BCrypt.Net-Next`, `Konscious.Security.Cryptography.Argon2`), .NET-specific risks (`Process.Start` injection, path traversal via `Path.Combine` without `Path.GetFullPath` + base check, mass assignment via `[FromBody] DomainEntity` or `JsonSerializer.Deserialize<DomainEntity>`, `unsafe` blocks, deserialization attacks via `BinaryFormatter` / `XmlSerializer`, `Newtonsoft.Json` `TypeNameHandling.All` RCE), and .NET dependency hygiene (`dotnet list package --vulnerable`, NuGet Audit, GitHub Dependabot) directly instead of routing through the generic backend security adapter. Produces findings with attack scenarios and concrete .NET-specific remediations.

This workflow is the stack-specific delegate of `task-code-review-security` for .NET. The core workflow's contract (invocation, diff resolution, output format) is preserved so callers see a stable shape.

## When to Use

- Reviewing a .NET / ASP.NET Core PR for security regressions
- Pre-deployment hardening pass on auth, authz, file upload, payment, or PII-handling code
- Periodic strong-validation and middleware drift sweep across endpoints
- Auditing a JWT flow, a new authorization policy, or new `unsafe` / crypto usage

**Not for:**

- Performance review (use `task-code-review-perf` or `task-dotnet-review-perf`)
- General code review (use `task-code-review` or `task-dotnet-review`)
- Production incident triage (use `/task-oncall-start`)

**Depth.** This workflow always runs at full depth - there is no `quick` / `standard` / `deep` knob. Security review has cliff-edged consequences (auth bypass, RCE) that do not benefit from a "light" mode. If callers want a shallower pass, they should scope by file, not by depth.

## Severity Rubric

Use these definitions to keep severity consistent across runs - do not invent your own scale.

| Severity     | Definition                                                                                                                                                                                                                                                             |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Critical** | Unauthenticated RCE, authentication bypass, mass data exfiltration, working SQL injection on a production code path (`db.Database.ExecuteSqlRaw($"... {userInput}")`, `FromSqlRaw($"... {userInput}")`), `Process.Start("cmd.exe", $"/c {userInput}")`, secrets / signing keys committed in source, JWT `none` algorithm accepted, `BinaryFormatter.Deserialize` on untrusted input, `Newtonsoft.Json` `TypeNameHandling.All` on untrusted input, `unsafe` block with attacker-controlled inputs producing UB. Must fix before deploy; blocks merge. |
| **High**     | Authenticated privilege escalation, IDOR with sensitive data, SSRF reaching cloud metadata or internal services, mass assignment via `[FromBody] DomainEntity` granting admin, missing `[Authorize]` on user-data endpoint, path traversal via `Path.Combine` without `Path.GetFullPath` + base check, missing CSRF token on cookie-auth POST. Must fix before merge. |
| **Medium**   | Hardening gap with a mitigating control elsewhere (e.g., missing CORS allowlist when a reverse proxy enforces origin), missing FluentValidation rules on a non-critical endpoint, weak rate limiting on a non-critical endpoint, debug exposure on a non-prod profile (Hangfire dashboard with default `LocalRequestsOnlyAuthorizationFilter` reachable from cluster network), `dotnet list package --vulnerable` advisory not yet exploited. Should fix this PR or the next one. |
| **Low**      | Defense-in-depth nice-to-have, dependency advisory below the actively-exploited threshold, hardening recommendations without a concrete current attack scenario.                                                                                                       |

**Combined-finding rule.** When two or more findings *compose* on the same code path into a worse threat than either alone, file them as a single finding at the elevated severity and cite each component. Examples:

- Missing `[Authorize]` on a user-data endpoint (High, alone) + mass assignment via `[FromBody] User` (High, alone) on the *same action* = **Critical** unauthenticated admin override (anyone on the internet can `POST /admin/users/{id}` with `{"role": "admin"}`).
- Missing ownership check (High, alone) + EF Core entity returned via `Ok(user)` exposing `PasswordHash` (medium, alone) on the *same action* = **Critical** account takeover (any authenticated user reads any other user's password hash).
- Missing `[Authorize]` on `[HttpGet("{id}")]` action (High, alone) + `return Ok(order)` returning the EF Core entity directly (High, alone) on the *same action* = **Critical** unauthenticated entity exposure (anonymous users read any order including every entity column - audit, soft-delete, internal flags, and any sensitive column added later when the schema evolves). File as one Critical with both component citations; rationale: rubric clause "mass data exfiltration" plus authorization bypass.
- SSRF (High, alone) + reachable from an unauthenticated endpoint (High, alone) = **Critical** unauth SSRF.

The rule of thumb: if the realistic exploit path requires both findings to land for the attack to succeed, they are one finding. If either finding is exploitable on its own, file them separately at their independent severities.

**Same-action co-location.** Combining findings requires confirming both land on the *same code path* (same action method, or same controller with shared `[Authorize]` attribute). When the diff doesn't make co-location obvious - e.g., the IDOR is in `GetOrder` but the entity leak appears on a different action in the same controller - file the findings separately at their independent severities and add a one-line `Note: Combined-finding rule applies if both land on the same action; verify and merge before merge` to the lower-severity entry. Do not silently merge or silently keep separate.

## Invocation

Mirrors `task-code-review-security`:

| Invocation                              | Meaning                                                                                               |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-dotnet-review-security`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-dotnet-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-dotnet-review-security pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review-security` (the core dispatcher passes the precondition-check handle plus the already-read diff and commit log), Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect` to confirm .NET / ASP.NET Core. If invoked as a delegate of `task-code-review-security` or as a subagent of `task-dotnet-review` (parent already detected .NET), accept the pre-confirmed stack and skip re-detection. If the detected stack is not .NET, stop and tell the user to invoke `/task-code-review-security` instead.

Detect data access (EF Core / Dapper / mixed), JWT library (`Microsoft.AspNetCore.Authentication.JwtBearer` typically), and password hashing (`Microsoft.AspNetCore.Identity.PasswordHasher<T>` PBKDF2, `BCrypt.Net-Next`, `Konscious.Security.Cryptography.Argon2`). Record `Data Access`, `JWT Library`, `Password Hash` for the Summary block.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review-security` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message, surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - Read the Security Surface

Before applying the OWASP and authn/authz checklists, open the files that actually wire security so findings cite real lines:

- `Program.cs` (or `Startup.cs` for legacy projects) - confirm middleware order (`UseExceptionHandler` → `UseHsts` → `UseHttpsRedirection` → `UseRouting` → `UseCors` → `UseAuthentication` → `UseAuthorization` → `MapControllers`) and `AddAuthentication().AddJwtBearer(...)` / `AddAuthorization(options => options.AddPolicy(...))` registration
- JWT bearer config: `JwtBearerOptions.TokenValidationParameters` - signing algorithm allowlist, issuer, audience, lifetime validation
- Authorization policies: `AuthorizationOptions.AddPolicy(...)` definitions, `IAuthorizationHandler` / `AuthorizationHandler<TRequirement, TResource>` for resource-based authz
- CORS setup (`AddCors`, `UseCors(...)` policy) for origin allowlist
- Rate limiter (.NET 7+ `AddRateLimiter(...)` / Polly v8 `RateLimiter`, or `AspNetCoreRateLimit` library) for auth-endpoint rate limits
- Every changed action - look for `[Authorize]` / `[AllowAnonymous]` / `[Authorize(Policy = "...")]` attributes, ownership checks in handler/service body, request DTO type, FluentValidation validators
- Every changed DTO record with FluentValidation `AbstractValidator<T>` or `[ApiController]` auto-validation context
- Every changed query for parameterization (`db.Orders.Where(o => o.Id == id)` / `FromSqlInterpolated($"...{id}")` parameterized; `FromSqlRaw($"... {id}")` is not)
- Every changed file under `Migrations/` for schema-level security: new tables / columns holding PII or auth state (sensitive-column inventory drift), missing `NOT NULL` on identity / tenant columns, missing FK constraints on tenant scoping columns, `migrationBuilder.Sql("GRANT ...")` widening role privileges, audit-column additions that imply new sensitive fields the response DTO may now leak. Migration content is part of the security surface, not just schema-evolution
- Config: `appsettings.json`, `appsettings.{Environment}.json`, `IConfiguration` reads for `Jwt:Key`, allowed origins, env var loading via `IOptions<T>`
- `.csproj` / `Directory.Packages.props` for package versions; recent CVE-affected packages (`dotnet list package --vulnerable`)
- `appsettings.Development.json` for documented config (without real secrets); `dotnet user-secrets` for local dev secret storage

When the diff removes a middleware or relaxes auth, also `git log -p` the prior revision of those lines to confirm what was protected before. The blame trail is the authoritative answer to "did this change weaken authorization."

### Step 4 - OWASP Triage (.NET Lens)

This step is a **triage pass**, not a separate findings list. Run through the OWASP categories below and produce a single output: a list of categories that show signal in this diff (e.g., `Broken Access Control: yes`, `Injection: yes`, `SSRF: yes`, `Insecure Design: no`). Steps 5-9 then produce the actual findings; do **not** repeat them here.

The triage output funnels which downstream steps must run carefully versus which can be fast-passed. If a category shows no signal, explicitly state `No signal in diff` for that category in the Summary.

| Risk                          | .NET-specific check                                                                                                                                                                                                                                                                                                                                                       |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Every action has explicit `[Authorize]` / `[AllowAnonymous]` (or controller-level `[Authorize]` with action-level `[AllowAnonymous]` for opt-outs); ownership check in the handler / service body for per-owner data via `IAuthorizationService` resource-based auth or inline `WHERE OwnerId = User.GetUserId()` in repository. Empty / missing is a finding.            |
| Injection                     | EF Core uses parameterized LINQ by default; `FromSqlInterpolated($"... WHERE id = {id}")` parameterizes interpolated holes; `FromSqlRaw($"... WHERE id = {id}")` is **not** parameterized. Dapper: `connection.QueryAsync<T>("... WHERE id = @id", new { id })` is parameterized. `Process.Start("convert", new[] { input })` (arg-list) is fine; `Process.Start("cmd.exe", $"/c {input}")` is RCE. |
| Cryptographic Failures        | Password hashing via `IPasswordHasher<T>` (ASP.NET Core Identity, PBKDF2 default), `BCrypt.Net-Next` (cost ≥ 11), or `Konscious.Security.Cryptography.Argon2`. Never `MD5`, `SHA1`, raw `SHA256` for passwords (use only as non-security checksums). JWT signing key from env / Vault, not hardcoded. `RandomNumberGenerator.Create()` (CSPRNG) for tokens / nonces, not `Random` for security-sensitive randomness.                              |
| Security Misconfiguration     | Security headers via middleware or `NWebsec` library: HSTS (`UseHsts()`), `X-Frame-Options`, `X-Content-Type-Options`, CSP; CORS origin allowlist (not `AllowAnyOrigin().AllowCredentials()` - this combination is rejected by the framework but flag any near-misses); no `app.UseDeveloperExceptionPage()` in prod; Hangfire / Swagger UI not exposed without auth in prod. |
| SSRF                          | `HttpClient.GetAsync(userControlledUrl)` validates hostname against allowlist; rejects RFC1918, link-local, cloud metadata before request.                                                                                                                                                                                                                                |
| XSS                           | Razor / Blazor auto-escape `@variable`; `@Html.Raw(...)` flagged. Manual `Response.WriteAsync($"<div>{user}</div>")` is XSS-prone - flag.                                                                                                                                                                                                                              |
| Insecure Design (A04)         | Default-deny: controllers carry `[Authorize]` at the controller level with explicit `[AllowAnonymous]` opt-outs on public actions; or `services.AddAuthorization(options => options.FallbackPolicy = new AuthorizationPolicyBuilder().RequireAuthenticatedUser().Build())` for app-wide default-deny.                                                                                                                                                                          |
| Vulnerable Components (A06)   | `dotnet list package --vulnerable` clean for affected; `dotnet list package --deprecated` checked; NuGet Audit (`<NuGetAudit>true</NuGetAudit>` in `Directory.Packages.props`, .NET 8+) enabled in CI; Dependabot / Renovate active. No pinned-but-stale package with known CVE in `packages.lock.json`.                                                                                                                                                                                  |
| Data Integrity Failures (A08) | `JsonSerializer.Deserialize<T>(stream)` on untrusted input bounded by `RequestSizeLimit` / `[RequestFormLimits]`; `BinaryFormatter.Deserialize` flagged as Critical (deprecated and disabled by default in .NET 5+, but legacy code may re-enable); `XmlSerializer.Deserialize` on untrusted XML flagged for XXE if `XmlReaderSettings.DtdProcessing != DtdProcessing.Prohibit`; `Newtonsoft.Json.JsonConvert.DeserializeObject` with `TypeNameHandling.All` / `Auto` / `Objects` is RCE. Mass assignment: `[FromBody] DomainEntity` or `JsonSerializer.Deserialize<DomainEntity>(body)` flagged. |
| Logging & Monitoring (A09)    | Serilog / `ILogger` does not log `password`, `token`, `Authorization` header, `Cookie` header. Auth events logged. Sentry / Application Insights `BeforeSend` strips PII (when wired).                                                                                                                                                                                    |

### Step 5 - Authentication

- [ ] **JWT signing**: HS256 secret in env / Vault, never committed; minimum 256-bit. RS256 / ES256 with key pair preferred for cross-service. `Microsoft.AspNetCore.Authentication.JwtBearer` is standard; `JwtBearerOptions.Authority` for OIDC discovery
- [ ] **No hardcoded signing key in source**: any `IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes("literal"))` with the literal in `Program.cs` / `Startup.cs` is `Critical` per rubric clause "secrets / signing keys committed in source" - anyone with read access to the repo can forge tokens for any user. Sourced from env / Vault / `dotnet user-secrets` (dev) only
- [ ] **`alg: none` rejected**: `JwtBearerOptions.TokenValidationParameters.ValidAlgorithms = new[] { SecurityAlgorithms.RsaSha256 }` (or whatever the expected algorithm is) - never accept any algorithm; the default `JwtSecurityTokenHandler` historically accepted any algorithm in `alg` header. Set the allowlist explicitly
- [ ] **JWT validation parameters all `true`**: `ValidateIssuer = true`, `ValidateAudience = true`, `ValidateLifetime = true`, `ValidateIssuerSigningKey = true`. Set `ValidIssuer`, `ValidAudience`, `IssuerSigningKey` explicitly. `ClockSkew = TimeSpan.FromSeconds(30)` (default is 5 minutes - tightens token expiry precision). **Quick-scan rule:** every `Validate* = false` in the diff is at minimum `High`; the combination `ValidateIssuer = false` + `ValidateAudience = false` together with a hardcoded HS256 signing key is `Critical` (any signed JWT for any audience is accepted, and the attacker controls the signing key from the source repo)
- [ ] **Access token lifetime** short (5-15 min); refresh token rotation; refresh tokens revocable via DB / Redis denylist (track `jti` claim or refresh-token GUID)
- [ ] **Password hashing**: `IPasswordHasher<TUser>` (ASP.NET Core Identity, PBKDF2 with adaptive iteration count), `BCrypt.Net-Next` `BCrypt.HashPassword(pw, workFactor: 11)`, or `Konscious.Security.Cryptography.Argon2`. Never `MD5.HashData(pw)` / `SHA256.HashData(pw)` for passwords. Use `CryptographicOperations.FixedTimeEquals` for hash comparison
- [ ] **JWT bearer middleware wired correctly**: `services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme).AddJwtBearer(...)` registered; `app.UseAuthentication()` placed BEFORE `app.UseAuthorization()` in the pipeline; `[Authorize]` attribute on protected actions
- [ ] **Brute-force protection**: rate limiter on `/auth/login`, `/auth/refresh`, `/auth/reset-password` via .NET 7+ built-in `AddRateLimiter(...)` (`FixedWindowLimiter`, `SlidingWindowLimiter`, or `TokenBucketLimiter`); configured stricter than global limit
- [ ] **No `_logger.LogInformation("token: {Token}", token)`** that leaks JWTs to logs
- [ ] **Session cookies (when used instead of bearer JWT)**: `Secure = true` in prod, `HttpOnly = true`, `SameSite = SameSiteMode.Lax`; signed/encrypted via the data protection API (`services.AddDataProtection()...PersistKeysToFileSystem(...)` with key rotation)

### Step 6 - Authorization

- [ ] **Authorization drift sweep**: every new action added in the diff has `[Authorize]` (or `[Authorize(Policy = "...")]`) OR explicitly carries `[AllowAnonymous]`. No bare action without one of the two attributes when the controller does not carry `[Authorize]`
- [ ] **Policy-based authorization** centralized via `services.AddAuthorization(options => options.AddPolicy("CanEditOrders", p => p.RequireRole("Admin").RequireClaim("permission", "orders:write")))`, applied via `[Authorize(Policy = "CanEditOrders")]`; not inline `if (!User.IsInRole("admin")) return Forbid();` scattered in actions (easy to miss on new endpoints)
- [ ] **Resource-based authorization** for per-owner data: `IAuthorizationService.AuthorizeAsync(User, order, "OrderOwnerOrAdmin")` with an `AuthorizationHandler<OrderOwnerOrAdminRequirement, Order>` checking `order.OwnerId == context.User.GetUserId()` - more reliable than inline checks
- [ ] **IDOR**: lookups scope through the principal in the query (`db.Orders.Where(o => o.Id == orderId && o.OwnerId == User.GetUserId())`) rather than `Where(o => o.Id == orderId)` then a separate ownership check. Better: every domain query takes `OwnerId` / `TenantId` in its repository signature
- [ ] **Tenant isolation**: multi-tenant apps scope queries by `TenantId` via EF Core global query filters (`modelBuilder.Entity<Order>().HasQueryFilter(o => o.TenantId == _tenantContext.TenantId)`) or at the repository layer (every query includes the `Where` clause), not at the controller layer alone
- [ ] **CORS**: `services.AddCors(options => options.AddPolicy("Default", b => b.WithOrigins("https://app.example.com").AllowCredentials().WithMethods(...).WithHeaders(...)))` allowlist (not `AllowAnyOrigin().AllowCredentials()` - the framework throws on this combination, but be alert for `SetIsOriginAllowed(_ => true)` workarounds); methods and headers minimal
- [ ] **CSRF / antiforgery**: not required for stateless JWT-bearer APIs; required for cookie-session apps - `services.AddAntiforgery()` and `[ValidateAntiForgeryToken]` (or `AutoValidateAntiforgeryTokenAttribute` filter) on cookie-auth POST / PUT / DELETE actions

### Step 7 - Input Validation and Mass Assignment

- [ ] **`[ApiController]` auto-validation OR FluentValidation explicit**: with `[ApiController]`, model state validation runs automatically and returns 400 ValidationProblemDetails when invalid; with FluentValidation, the validator is registered via `services.AddValidatorsFromAssemblyContaining<...>()` and invoked via `validator.ValidateAsync(req, ct)`. Bare `[FromBody] JsonElement` / `JObject` body means anything-goes input
- [ ] **FluentValidation rules on every DTO field**: `RuleFor(x => x.Email).NotEmpty().EmailAddress()`, `RuleFor(x => x.Quantity).GreaterThan(0)`, custom validators for domain rules. Missing rules means anything-goes input
- [ ] **No `[FromBody] JsonElement` / `[FromBody] JObject` / `[FromBody] Dictionary<string, object>`**: extract a typed record - never read fields by string key from a free-form JSON value
- [ ] **No privilege-bearing fields in user-facing input DTOs**: `Role`, `IsAdmin`, `OwnerId`, `UserId`, `TenantId`, `IsActive`, `Verified` - server-set only. If present in `CreateOrderRequest` record, reject and require an admin-only path with a separate DTO
- [ ] **No identity / cache-key fields in user-facing input DTOs**: `Id`, `CreatedAt`, `UpdatedAt`, and any field used as a key in an in-process cache (`IMemoryCache.Get<T>(id)`) - if the client controls the id and the server also caches by id, the client can write arbitrary entries into the cache and read other users' data on the next lookup. This is the cache-poisoning shape; treat it as a mass-assignment finding even when the field looks innocuous
- [ ] **No `[FromBody] DomainEntity` / `JsonSerializer.Deserialize<DomainEntity>(body)` directly into a domain entity**: this is mass-assignment. Define a request DTO record, validate it, then map to the domain entity with explicit field assignment
- [ ] **Response DTOs (not entities) returned from actions**: `Ok(OrderResponse.From(order))` maps explicitly, dropping internal fields (`PasswordHash`, `InternalAuditLog`, `IsTest`)
- [ ] **`[FromRoute] Guid id` for path params**: validates and converts in one call; raw `[FromRoute] string id` returns a string with no validation
- [ ] **`[FromQuery] ListFilters filters`** with FluentValidation rules for query strings
- [ ] **GUID / Ulid path params parsed strongly**: never trust the raw string format; rely on the model binder type
- [ ] **File uploads (`IFormFile`)**:
  - File type validated by content (magic bytes via `FileTypeChecker` library or manual `ReadOnlySpan<byte>` check), not just `IFormFile.ContentType` (client-controlled) or extension
  - Per-file size limit enforced via `[RequestSizeLimit(5 * 1024 * 1024)]` action attribute or globally via `services.Configure<FormOptions>(o => { o.MultipartBodyLengthLimit = 5 * 1024 * 1024; })`; Kestrel limit `services.Configure<KestrelServerOptions>(o => o.Limits.MaxRequestBodySize = ...)`
  - Saved files stored outside the webroot; `Content-Disposition: attachment` on serve
  - Filename sanitized via `Path.GetFileName(file.FileName)` AND the resulting save path canonicalized (`Path.GetFullPath(Path.Combine(baseDir, name))`) and checked: `savedPath.StartsWith(baseDir, StringComparison.Ordinal)`. Never `Path.Combine(baseDir, userInput)` without normalization
  - Virus scan pipeline or accepted-risk documented for user uploads
- [ ] **Path traversal**: `var candidate = Path.Combine(baseDir, userInput); var canonical = Path.GetFullPath(candidate); if (!canonical.StartsWith(baseDir, StringComparison.Ordinal)) throw new SecurityException();` - reject otherwise. `Path.Combine` alone does NOT prevent `../` traversal (it preserves trailing absolute paths and does not resolve `..`)
- [ ] **Process execution**: `Process.Start(new ProcessStartInfo("convert") { ArgumentList = { userInput, "/tmp/out" } })` is safe (arg-list, no shell); `Process.Start("cmd.exe", $"/c convert {userInput}")` or `Process.Start("/bin/sh", $"-c \"... {userInput}\"")` is RCE. Strict allowlist of allowed binaries

### Step 8 - Common .NET Vulnerability Patterns

- [ ] **SQL injection via raw query**: `db.Database.ExecuteSqlRaw($"UPDATE ... WHERE id={userInput}")` - flagged as critical; `FromSqlRaw($"... {userInput}")` is the same. Use `FromSqlInterpolated($"... WHERE id = {userInput}")` (parameterizes interpolated holes), `FromSqlRaw("... WHERE id = {0}", userInput)` (explicit parameter), or LINQ. Even `FromSqlInterpolated($"... WHERE name LIKE {$"%{input}%"}")` is fine - the inner string is the parameter, not part of the SQL
- [ ] **Dapper SQL injection**: `connection.QueryAsync<T>($"... WHERE id = {userInput}")` is SQL injection. `connection.QueryAsync<T>("... WHERE id = @id", new { id = userInput })` is parameterized
- [ ] **Command injection**: `Process.Start("cmd.exe", $"/c convert {userInput}")` or any concatenation of user input into a shell-interpreted string is RCE; use `Process.Start(new ProcessStartInfo("convert") { ArgumentList = { userInput, "/tmp/out" } })` (arg-list, no shell)
- [ ] **`BinaryFormatter.Deserialize` on untrusted input**: deserialization gadgets are well-documented; `BinaryFormatter` is deprecated and obsolete from .NET 5+. Any reintroduction is Critical
- [ ] **`Newtonsoft.Json` `TypeNameHandling.All` / `Auto` / `Objects` on untrusted input**: instantiates arbitrary types named in `$type` field - RCE via gadget chains. Use `TypeNameHandling.None` (default) or migrate to `System.Text.Json` which doesn't have this feature
- [ ] **`XmlSerializer.Deserialize` on untrusted XML**: XXE if `XmlReaderSettings.DtdProcessing != DtdProcessing.Prohibit` and `XmlResolver != null`. Set both for untrusted XML
- [ ] **`DataContractSerializer` / `XmlReader` defaults**: same XXE concern - set `DtdProcessing = DtdProcessing.Prohibit` on `XmlReaderSettings`
- [ ] **Templates with user-supplied template source**: Razor's `RazorEngine` / `RazorLight` with user-controlled template source is SSTI / RCE-adjacent; templates must come from disk or a trusted constant
- [ ] **`unsafe` package usage**: every `unsafe { ... }` block in the diff must have a `// SAFETY:` comment justifying the invariants. Audit for memory-safety violations; legitimate uses exist (P/Invoke, `Span<T>` interop) but most are smells
- [ ] **HTTP client with `ServerCertificateCustomValidationCallback` returning `true`**: `new HttpClientHandler { ServerCertificateCustomValidationCallback = (_, _, _, _) => true }` flagged unless behind a documented test fixture
- [ ] **Open redirect**: `return Redirect(userInput);` validated against an allowlist or `Url.IsLocalUrl(target)` check
- [ ] **`RandomNumberGenerator` (NOT `Random` for security-sensitive randomness)**: `RandomNumberGenerator.GetBytes(buffer)` / `RandomNumberGenerator.GetInt32(...)` is OS-backed CSPRNG; `Random` is fast but not designed for adversarial settings. For tokens / nonces / secrets use `RandomNumberGenerator`
- [ ] **`CryptographicOperations.FixedTimeEquals` for HMAC / signature comparison**: `==` on `byte[]` or `string.Equals` is timing-attack vulnerable. Stripe / GitHub / Slack webhook signature verification must use `CryptographicOperations.FixedTimeEquals(actual, expected)`
- [ ] **`Jwt:Key` / signing key** sourced from env / Vault / `dotnet user-secrets` (dev), never committed; rotated when leaked
- [ ] **Debug exposure**: `app.UseDeveloperExceptionPage()` not in prod (use `app.UseExceptionHandler(...)`); `app.UseSwagger() / app.UseSwaggerUI()` gated behind `if (env.IsDevelopment())` or behind auth in non-dev; Hangfire dashboard `app.UseHangfireDashboard("/hangfire", new DashboardOptions { Authorization = new[] { ... } })` - default `LocalRequestsOnlyAuthorizationFilter` is reachable from cluster network
- [ ] **SSRF depth**: when a user-controlled value flows into an outbound URL or hostname, the allowlist must reject (a) cloud metadata IP `169.254.169.254` and IPv6 equivalent, (b) localhost / `127.0.0.0/8` / `::1`, (c) private RFC1918 ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), (d) link-local `169.254.0.0/16`. Resolve the host **after** parsing (DNS rebinding bypasses string-only allowlists - re-resolve at request time and re-check). `Uri` parsing quirks: backslash, IPv4-in-IPv6 (`::ffff:127.0.0.1`) all defeat naive checks
- [ ] **Background-worker payload trust boundary**: MassTransit / Hangfire jobs serialize to bytes in the queue; consumer `JsonSerializer.Deserialize(payload)` on input from any source that can publish to the queue is implicit trust. If the queue is reachable from untrusted inputs (webhook → background job), validate inside the handler before acting on payload fields
- [ ] **HTTP request smuggling / desync** (Kestrel behind nginx / ALB): Kestrel's parser is strict by default; flag custom HTTP/1.1 parsing or proxy / forwarder middleware that re-emits headers without validation
- [ ] **Webhook signature verification**: Stripe / GitHub / Slack webhooks - signature verified via `CryptographicOperations.FixedTimeEquals(...)` (not `==`, not `Equals` on `byte[]`). Read raw body via `Request.EnableBuffering()` + read stream before any model binding (binding consumes the body)
- [ ] **`dotnet list package --vulnerable` / NuGet Audit integration**: project runs `dotnet list package --vulnerable --include-transitive` (or `<NuGetAudit>true</NuGetAudit>` in .NET 8+) in CI for known CVEs; flag unaddressed High/Critical findings

### Step 9 - Data Protection

- [ ] **PII / sensitive fields encrypted** at rest (`System.Security.Cryptography.AesGcm` for column encryption with proper nonce management, AWS KMS / Azure Key Vault for key management, or DB-native column encryption like SQL Server Always Encrypted / PostgreSQL `pgcrypto`)
- [ ] **No EF Core entity returned from action responses**: `Ok(user)` where `user: User` (an EF Core entity) leaks every property the entity defines - `PasswordHash`, `RecoveryToken`, `MfaSecret`, soft-delete columns, internal audit fields, and any sensitive column added later. Actions map to a response DTO record (`OrderResponse.From(o)`) that names exactly the public fields. This is both a Step 7 concern (mass-assignment shape on the way in) and a Step 9 concern (data leak on the way out) - check both directions
- [ ] **Serilog / `ILogger` redaction**: structured logger never logs `password`, `token`, `Authorization`, `Cookie`, `credit_card`, `ssn`, `api_key`. Serilog `Destructure.ByTransforming<User>(u => new { u.Id, u.TenantId })` or custom `IDestructuringPolicy` to drop sensitive fields
- [ ] **No sensitive data in URLs** (use POST body, headers, or signed tokens) - URLs hit logs, browser history, referrer headers
- [ ] **TLS enforcement**: HTTPS-only via `app.UseHttpsRedirection()` and `app.UseHsts()` (prod); Kestrel HTTPS endpoint configured
- [ ] **Database backups** encrypted; access controlled
- [ ] **Secrets management**: env vars from a secret store (Azure Key Vault / AWS Secrets Manager / HashiCorp Vault / `dotnet user-secrets` for dev), never `appsettings.json` / `appsettings.Production.json` committed with real secrets; `IOptions<JwtOptions>` typed config struct loaded once at startup so missing-at-startup fails fast


### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Rules

- Always validate at system boundaries (`[FromBody]` / `[FromQuery]` / `[FromRoute]` / `[FromForm]` extractors, MassTransit / Hangfire job payloads, external API responses, webhook payloads)
- Never disable middleware to silence a failing test - fix the test
- Never widen authorization (e.g., moving an action out of an authed controller, removing `[Authorize]` from an action) without an explicit security review note
- Log security events (login failure, permission denied, validation failure) without sensitive data
- Follow principle of least privilege - default-deny via `services.AddAuthorization(options => options.FallbackPolicy = ...RequireAuthenticatedUser().Build())` with explicit `[AllowAnonymous]` opt-outs

## Self-Check

**Verifiable from the diff (must check):**

- [ ] Stack confirmed as .NET / ASP.NET Core; data-access mix, JWT library, password hash library recorded before any specific check applied
- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent)
- [ ] Security surface (Program.cs / middleware order, JWT bearer config, authorization policies, settings, changed controllers / actions, DTOs) read directly before applying checklists; prior revision consulted when middleware was removed
- [ ] OWASP triage (Step 4) produced one signal verdict per category (`yes` / `no signal in diff`); not duplicated as standalone findings
- [ ] **Authorization drift sweep**: every new action in the diff has `[Authorize]` / `[AllowAnonymous]` (or controller-level coverage)
- [ ] DTO validation reviewed; mass-assignment fields, FluentValidation rules, separate request vs response DTOs confirmed for changed schemas
- [ ] File upload, path traversal, and process-execution checks run if the diff touches uploads / file paths / `Process.Start`
- [ ] SQL parameterization, command injection, runtime-template SSTI, `BinaryFormatter` / `Newtonsoft.Json` `TypeNameHandling` deserialization, `unsafe`, `ServerCertificateCustomValidationCallback`, open redirect checked when the diff touches them
- [ ] Severity rubric applied consistently (Critical / High / Medium / Low matches the rubric, not invented)
- [ ] Every finding includes an attack scenario, "regression risk" rationale (for test-coverage gaps), or "topology-dependent" framing (for infra-flavored findings) - not just "input not validated"
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Critical > High > Medium > Low (omitted only when no security issues exist)

**Requires repo / infra access (check if visible, otherwise note as "could not verify from diff alone - flag for separate audit"):**

- [ ] Authentication step run for the auth mechanism in use (JWT bearer via `Microsoft.AspNetCore.Authentication.JwtBearer`) - applies when the auth module is in scope
- [ ] CORS, rate limiting, secure-header middleware, debug exposure verified - applies when middleware / config are in scope
- [ ] Password hashing config reviewed (`IPasswordHasher<T>` / BCrypt cost ≥ 11 / Argon2 params) - skip if hashing config not in diff
- [ ] Sentry / Application Insights `BeforeSend` strips PII - skip if telemetry init not in diff
- [ ] `dotnet list package --vulnerable` / NuGet Audit clean - run separately; this workflow does not execute tools
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Output Format

```markdown
## .NET Security Review Summary

**Stack Detected:** .NET <version> / ASP.NET Core <version>
**Data Access:** EF Core <version> | Dapper <version> | mixed
**JWT Library:** Microsoft.AspNetCore.Authentication.JwtBearer | none
**Password Hash:** IPasswordHasher (PBKDF2) | BCrypt.Net-Next | Konscious Argon2 | none
**Authorization:** policy-based + resource-based + ownership checks | inline checks | none
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment of the overall security posture, calling out any .NET-specific risks like missing `[Authorize]` on an action, mass assignment via `[FromBody] User`, raw SQL via `FromSqlRaw($"...")`, exposed Hangfire / Swagger UI in prod, `ServerCertificateCustomValidationCallback` returning true, or `unsafe` block without SAFETY comment.]

## OWASP Triage

_The Step 4 verdicts. One row per category, `yes` (signal present, see Findings) or `no signal in diff`._

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

- **Location:** [file:line, or comma-separated list for multi-site findings]
- **Issue:** [vulnerability described in .NET terms - e.g., "OrdersController.Update binds the request body directly into a domain entity via `[FromBody] Order request`; client can submit `{ \"OwnerId\": \"00000000-0000-0000-0000-000000000999\" }` and override the server-assigned owner via mass assignment because there is no separate request DTO with explicit fields"]
- **Attack scenario:** [one of: (a) concrete exploit walkthrough; (b) "Regression risk: the next refactor silently removes one of these protections" — for test-coverage / monitoring gaps; (c) "Topology-dependent: depends on whether the reverse proxy strips X-Forwarded-Proto correctly" — for infra-flavored findings. Pick one and label which. Do NOT invent an exploit when the realistic threat is regression or topology.]
- **Severity rationale:** [tier] per rubric - [which clause from the Severity Rubric applies]
- **Fix:** [specific .NET remediation with code example - separate request DTO record + explicit field copy, `Where(o => o.Id == id && o.OwnerId == User.GetUserId())`, `[Authorize(Policy = "...")]`, etc.]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit severity sections with no findings. If all sections are omitted, state "No security issues found."_

## Recommendations

[Prioritized hardening that is not a specific finding - e.g., "Add `AddRateLimiter` policy on /auth/login", "Migrate password hashing from BCrypt cost 10 to Argon2id", "Move Jwt:Key from appsettings.json to Azure Key Vault", "Enable `<NuGetAudit>true</NuGetAudit>` in CI", "Default-deny via `FallbackPolicy = RequireAuthenticatedUser()`"]

## Next Steps

Prioritized action list. Each item tagged `[Implement]` (localized fix - apply directly) or `[Delegate]` (cross-cutting hardening, dependency upgrade, or threat-model exercise worth spawning a subagent for). Order: Critical > High > Medium > Low.

1. **[Implement]** [Critical] file:line - [one-line action, e.g., "Replace `[FromBody] Order request` with a typed `UpdateOrderRequest` record + explicit field copy in OrdersController.Update"]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action, e.g., "Run `dotnet list package --vulnerable` and upgrade flagged packages - spawn dependency-review subagent"]
3. **[Implement]** [Medium] file:line - [one-line action]

_Omit this section if no security issues were found._
```

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting vulnerabilities without an attack scenario ("input not validated" vs "attacker submits `{\"Role\":\"Admin\"}` and gains admin via mass assignment because action binds directly into `User` entity")
- Skipping OWASP categories that appear clean - explicitly state "No issues found" per category
- Recommending generic security advice when a .NET idiom applies (say "apply policy-based authorization via `[Authorize(Policy = \"...\")]` and a registered policy + handler", not "add an authorization check")
- Suggesting `app.UseDeveloperExceptionPage()` left enabled in prod - leaks stack traces; flag if prod config inherits dev
- Suggesting `FromSqlRaw($"...")` as acceptable - parameterize via `FromSqlInterpolated` or `FromSqlRaw("... {0}", input)`
- Suggesting `ServerCertificateCustomValidationCallback = (_, _, _, _) => true` outside test fixtures
- Suggesting `Random` for tokens / nonces / secrets - use `RandomNumberGenerator`
- Suggesting `==` or `string.Equals` on `byte[]` for HMAC / signature comparison - use `CryptographicOperations.FixedTimeEquals`
- Suggesting `[FromBody] JsonElement` / `[FromBody] JObject` over typed `[FromBody] CreateRequest` records with FluentValidation - bare JsonElement is anything-goes
- Suggesting `[FromBody] DomainEntity` or `JsonSerializer.Deserialize<DomainEntity>(body)` as acceptable - mass-assignment vector
- Suggesting `BinaryFormatter` re-enablement on untrusted input - deprecated and gadget-rich
- Suggesting `Newtonsoft.Json.TypeNameHandling.All / Auto / Objects` on untrusted input - RCE
- Disabling middleware to silence a failing test - fix the test
- Conflating security review with general code quality or performance review - delegate those to their workflows
- Approving Hangfire / Swagger UI exposed in prod without auth filter
- Approving `XmlSerializer` / `XmlReader` on untrusted XML without `DtdProcessing = DtdProcessing.Prohibit`
- Approving `unsafe` blocks without `// SAFETY:` comments justifying the invariants
