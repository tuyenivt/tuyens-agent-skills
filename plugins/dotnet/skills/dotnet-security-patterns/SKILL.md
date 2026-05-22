---
name: dotnet-security-patterns
description: Configure JWT bearer auth, policy-based authorization, and OWASP hardening for ASP.NET Core 8 APIs with secure defaults.
metadata:
  category: backend
  tags: [security, jwt, authentication, authorization, owasp, aspnet-core]
user-invocable: false
---

# Security Patterns

## When to Use

- Configuring JWT bearer authentication in ASP.NET Core 8
- Defining policy-based or role-based authorization
- Hardening API endpoints against OWASP Top 10
- Securing secrets and connection strings

## Rules

- Set a `RequireAuthenticatedUser` fallback policy; mark public endpoints `[AllowAnonymous]` explicitly.
- Validate JWT issuer, audience, lifetime, and signing key; reject `alg: none`.
- Use policies (`[Authorize(Policy = "...")]`) for authorization; do not branch on `IsInRole` or claim values inside controllers/services.
- Load secrets from environment variables, User Secrets, or a vault - never from `appsettings.json`.
- Enable HTTPS redirection and HSTS in production.
- Set cookies `HttpOnly`, `Secure`, `SameSite=Strict` or `Lax`; enable antiforgery on cookie-authenticated state-mutating endpoints.
- Use short-lived access tokens (5-15 min) with refresh tokens; JWTs cannot be revoked once issued.

## Patterns

### JWT bearer with full validation

```csharp
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(o =>
    {
        o.MapInboundClaims = false; // preserve external claim names (Auth0, Azure AD)
        o.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true, ValidateAudience = true,
            ValidateLifetime = true, ValidateIssuerSigningKey = true,
            ValidIssuer   = builder.Configuration["Jwt:Issuer"],
            ValidAudience = builder.Configuration["Jwt:Audience"],
            IssuerSigningKey = new SymmetricSecurityKey(
                Encoding.UTF8.GetBytes(builder.Configuration["Jwt:Key"]!))
        };
    });
```

Use asymmetric keys (RSA/ECDSA public key in `IssuerSigningKey`) when validation runs in services that do not mint tokens.

### Fallback policy + explicit public endpoints

```csharp
builder.Services.AddAuthorizationBuilder()
    .SetFallbackPolicy(new AuthorizationPolicyBuilder()
        .RequireAuthenticatedUser().Build());

app.MapHealthChecks("/health").AllowAnonymous(); // fallback applies to everything otherwise
```

### Policy over inline role/claim checks

Bad - authorization logic leaks into the controller:

```csharp
public async Task<IActionResult> Delete(Guid id)
{
    if (!User.IsInRole("Admin")) return Forbid();
    ...
}
```

Good - declarative policy, testable in isolation:

```csharp
builder.Services.AddAuthorization(o =>
    o.AddPolicy("OwnerOrAdmin", p => p.RequireAssertion(ctx =>
        ctx.User.IsInRole("Admin") ||
        ctx.User.FindFirstValue(ClaimTypes.NameIdentifier) == ctx.Resource?.ToString())));

[Authorize(Policy = "OwnerOrAdmin")]
[HttpDelete("{id}")] public Task<IActionResult> Delete(Guid id, ...) { ... }
```

### Secrets out of source

Bad - `appsettings.json` checked into git:

```json
{ "Jwt": { "Key": "super-secret-signing-key" } }
```

Good - environment / User Secrets / vault, bound via configuration:

```csharp
// dotnet user-secrets set "Jwt:Key" "..."   (dev)
// AZURE_KEYVAULT_URI / env var              (prod)
var key = builder.Configuration["Jwt:Key"]
    ?? throw new InvalidOperationException("Jwt:Key not configured");
```

## Output Format

When applied during review or implementation, report findings as:

```
Finding: <one-line description>
Severity: {Critical | High | Medium | Low}
Rule: <which Rule was violated>
Location: <file:line or "Program.cs">
Fix: <code-level remediation, reference Pattern by name>
```

## Avoid

- `[AllowAnonymous]` without justification in code review.
- Returning stack traces or token-parsing details from auth failures.
- Disabling antiforgery on cookie-auth state-mutating endpoints.
- JWTs without `exp`; long-lived (>1h) access tokens.
- Mandating a specific validation library; `[ApiController]` + DataAnnotations or FluentValidation are both acceptable.
