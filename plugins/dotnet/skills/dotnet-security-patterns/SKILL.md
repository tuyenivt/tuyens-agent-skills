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
- Validate JWT issuer, audience, lifetime, and signing key; pin accepted algorithms via `ValidAlgorithms` (rejecting `alg: none` alone does not stop RS256->HS256 confusion); set `ClockSkew` to zero or a few seconds (default is 5 min).
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
            ValidAlgorithms = ["HS256"], ClockSkew = TimeSpan.Zero, // ["RS256"] with an asymmetric key
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

// Good - resource-based handler; ownership depends on the loaded entity, so authorize imperatively.
// (A RequireAssertion policy can't see the entity: ctx.Resource is null under attribute-based [Authorize(Policy)].)
public sealed class OwnerOrAdminHandler : AuthorizationHandler<OwnerOrAdminRequirement, Document>
{
    protected override Task HandleRequirementAsync(
        AuthorizationHandlerContext ctx, OwnerOrAdminRequirement req, Document doc)
    {
        if (ctx.User.IsInRole("Admin") ||
            ctx.User.FindFirstValue(ClaimTypes.NameIdentifier) == doc.OwnerId.ToString())
            ctx.Succeed(req);
        return Task.CompletedTask;
    }
}
builder.Services.AddScoped<IAuthorizationHandler, OwnerOrAdminHandler>();

// In the action, after loading the entity:
var result = await _authz.AuthorizeAsync(User, doc, "OwnerOrAdmin");
if (!result.Succeeded) return Forbid();
```

### Secrets out of source

```csharp
// Bad - appsettings.json checked into git
// { "Jwt": { "Key": "super-secret-signing-key" } }

// Good - dev: dotnet user-secrets set "Jwt:Key" "..."; prod: AZURE_KEYVAULT_URI / env var
var key = builder.Configuration["Jwt:Key"]
    ?? throw new InvalidOperationException("Jwt:Key not configured");
```

### Antiforgery on cookie auth

Cookie-auth state-mutating endpoints need antiforgery; bearer/JWT endpoints do not (the token is not auto-attached by the browser).

```csharp
builder.Services.AddControllersWithViews(o => o.Filters.Add<AutoValidateAntiforgeryTokenAttribute>());
// JS clients: read the XSRF cookie, send it back as the X-XSRF-TOKEN header
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
