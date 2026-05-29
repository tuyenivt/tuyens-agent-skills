---
name: dotnet-security-patterns
description: Configure JWT bearer auth, policy-based authorization, and OWASP hardening for ASP.NET Core 8 APIs with secure defaults.
metadata:
  category: backend
  tags: [security, jwt, authentication, authorization, owasp, aspnet-core]
user-invocable: false
---

## When to Use

Configuring JWT bearer auth, policy-based authorization, OWASP Top 10 hardening, or secret management in ASP.NET Core 8.

## Rules

- Set a `RequireAuthenticatedUser` fallback policy; mark public endpoints `[AllowAnonymous]` explicitly.
- Validate JWT issuer, audience, lifetime, and signing key; reject `alg: none`.
- Authorize via policies (`[Authorize(Policy = "...")]`); do not branch on `IsInRole` or claim values inside controllers/services.
- Load secrets from environment variables, User Secrets, or a vault - never `appsettings.json`.
- Enable HTTPS redirection and HSTS in production.
- Cookies: `HttpOnly`, `Secure`, `SameSite=Strict` or `Lax`; enable antiforgery on cookie-auth state-mutating endpoints.
- Short-lived access tokens (5-15 min) with refresh tokens; JWTs cannot be revoked once issued.

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

```csharp
// Bad - authorization leaks into controller, untestable in isolation
public async Task<IActionResult> Delete(Guid id)
{
    if (!User.IsInRole("Admin")) return Forbid();
    ...
}

// Good - declarative policy
builder.Services.AddAuthorization(o =>
    o.AddPolicy("OwnerOrAdmin", p => p.RequireAssertion(ctx =>
        ctx.User.IsInRole("Admin") ||
        ctx.User.FindFirstValue(ClaimTypes.NameIdentifier) == ctx.Resource?.ToString())));

[Authorize(Policy = "OwnerOrAdmin")]
[HttpDelete("{id}")] public Task<IActionResult> Delete(Guid id, ...) { ... }
```

### Secrets out of source

```csharp
// Bad - appsettings.json checked into git
// { "Jwt": { "Key": "super-secret-signing-key" } }

// Good - dev: dotnet user-secrets set "Jwt:Key" "..."; prod: AZURE_KEYVAULT_URI / env var
var key = builder.Configuration["Jwt:Key"]
    ?? throw new InvalidOperationException("Jwt:Key not configured");
```

## Output Format

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
- JWTs without `exp`; access tokens >1h.
- Storing signing keys, connection strings, or API keys in `appsettings.json`.
