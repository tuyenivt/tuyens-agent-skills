---
name: dotnet-security-patterns
description: Configure JWT bearer authentication, policy-based authorization, and OWASP hardening for ASP.NET Core APIs with secure defaults.
metadata:
  category: backend
  tags: [security, jwt, authentication, authorization, owasp, aspnet-core]
user-invocable: false
---

# Security Patterns

## When to Use

- Configuring JWT bearer authentication in ASP.NET Core 8
- Defining policy-based or role-based authorization
- Hardening API endpoints against OWASP Top 10 vulnerabilities
- Securing sensitive configuration (secrets, connection strings)

## Rules

- Every endpoint must have an explicit auth rule - `[Authorize]` or `[AllowAnonymous]`; never rely on "default deny"
- Use policy-based authorization over role strings in business logic
- Store secrets in environment variables or a vault - never in `appsettings.json`
- Enable HTTPS redirection and HSTS in production
- Validate JWT issuer, audience, and signing key - reject tokens with `none` algorithm
- Use `FluentValidation` + `[ApiController]` for input validation to prevent injection
- Set `SameSite=Strict` or `Lax` for cookies; set `HttpOnly` and `Secure` flags

## Pattern

JWT bearer setup (.NET 8):

```csharp
builder.Services
    .AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer           = true,
            ValidateAudience         = true,
            ValidateLifetime         = true,
            ValidateIssuerSigningKey = true,
            ValidIssuer              = builder.Configuration["Jwt:Issuer"],
            ValidAudience            = builder.Configuration["Jwt:Audience"],
            IssuerSigningKey         = new SymmetricSecurityKey(
                Encoding.UTF8.GetBytes(builder.Configuration["Jwt:Key"]!))
        };
    });
```

Policy-based authorization:

```csharp
builder.Services.AddAuthorization(options =>
{
    options.AddPolicy("AdminOnly", policy => policy.RequireRole("Admin"));
    options.AddPolicy("OwnerOrAdmin", policy =>
        policy.RequireAssertion(ctx =>
            ctx.User.IsInRole("Admin") ||
            ctx.User.FindFirstValue(ClaimTypes.NameIdentifier) == ctx.Resource?.ToString()));
});

// Controller usage
[Authorize(Policy = "AdminOnly")]
[HttpDelete("{id}")]
public async Task<IActionResult> Delete(Guid id, CancellationToken ct) { ... }
```

Global require-auth fallback:

```csharp
builder.Services.AddAuthorizationBuilder()
    .SetFallbackPolicy(new AuthorizationPolicyBuilder()
        .RequireAuthenticatedUser()
        .Build());
```

## Avoid

- Hard-coding secrets in source code or `appsettings.json`
- `[AllowAnonymous]` without explicit justification in code review
- Returning detailed error messages (stack traces) from auth failures
- Disabling CSRF protection on state-mutating endpoints
- JWT tokens without expiry (`exp` claim)

## Edge Cases

- **Symmetric vs asymmetric keys**: `SymmetricSecurityKey` is simpler but requires the same secret on all services. For microservices or third-party identity providers, use asymmetric keys (RSA/ECDSA) with `TokenValidationParameters.IssuerSigningKey` set to the public key only.
- **Fallback policy + health checks**: The `SetFallbackPolicy(RequireAuthenticatedUser)` applies to ALL endpoints including health checks. Explicitly map health check endpoints with `[AllowAnonymous]` or use `RequireAuthorization()` selectively on endpoint groups instead.
- **Claims from external providers**: When using external identity providers (Auth0, Azure AD), claim types differ from the defaults. Configure `MapInboundClaims = false` on `JwtBearerOptions` and use the actual claim names from the token.
- **Token refresh**: JWTs are stateless - you cannot revoke them. Use short-lived access tokens (5-15 minutes) paired with refresh tokens stored securely. Implement a token revocation check for sensitive operations if needed.
