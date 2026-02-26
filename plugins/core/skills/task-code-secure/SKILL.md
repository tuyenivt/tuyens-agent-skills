---
name: task-code-secure
description: Security review covering OWASP Top 10, auth, and stack-specific vulnerabilities. Auto-detects project stack from CLAUDE.md and adapts security checks to the detected language and framework.
metadata:
  category: review
  tags: [security, owasp, vulnerabilities, auth, multi-stack]
  type: workflow
---

# Code Secure

## When to Use

- Security reviews of code changes
- Pre-deployment security checks
- Vulnerability assessment
- Authentication and authorization review

## Workflow

### Step 1 — Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Step 2 — OWASP Quick Check (All Stacks)

| Risk                      | Check                                                 |
| ------------------------- | ----------------------------------------------------- |
| Broken Access Control     | Auth on all endpoints                                 |
| Injection                 | Parameterized queries, no string concatenation in SQL |
| Cryptographic Failures    | No weak algorithms, proper key management             |
| Security Misconfiguration | Secure headers (CORS, CSP, HSTS)                      |
| SSRF                      | Validate/allowlist external URLs                      |
| XSS                       | Output encoding, no raw HTML injection                |

### Step 3 — Framework-Specific Security Review

After loading stack-detect, apply security checks specific to the detected ecosystem:

**Authentication & Authorization:**

- Verify the framework's auth mechanism is properly configured (security filters, auth middleware, before-action hooks, etc.)
- Check method/route-level authorization enforcement
- Verify JWT or session token validation (signature, expiry, audience)
- Ensure password hashing uses a strong algorithm (BCrypt, Argon2, scrypt)
- No credentials in code, config files, or version control

**Input Validation:**

- Verify the framework's standard validation mechanism is applied to all user input
- No raw SQL concatenation — use parameterized queries or the ORM's query builder
- Validate and sanitize all user-provided data before use

**Common Vulnerability Patterns:**

- CSRF protection is enabled for session-based auth (using the framework's built-in mechanism)
- CORS is configured restrictively
- Error responses do not leak stack traces or internal details
- No command injection via user-controlled input passed to system calls
- TLS enforced in production
- Framework-specific admin/debug endpoints are secured or disabled in production

If the detected stack is unfamiliar, apply the OWASP checks from Step 2 and recommend the user consult their framework's security documentation.

### Step 4 — Data Protection (All Stacks)

- Sensitive data not logged (passwords, tokens, PII)
- Encryption for sensitive fields at rest
- Secure headers configured (CORS, CSP, HSTS)
- Secrets in secret manager (not env vars or code)
- No sensitive data in client-side state or URLs

## Rules

- Always validate at system boundaries (user input, external APIs)
- Never trust client-side data
- Log security events without sensitive data
- Follow principle of least privilege

## Output Format

```markdown
## Summary

**Stack Detected:** [language / framework]
[Security posture assessment]

## Findings by Severity

### Critical | High | Medium | Low

- **Location:** [file:line]
- **Issue:** [vulnerability]
- **Impact:** [attack scenario]
- **Fix:** [specific remediation]

## Recommendations

[Prioritized security improvements]
```

## Key Skills Reference

- Use skill: `observability` for security event logging
- Use skill: `resiliency` for timeout and circuit breaker patterns
- Use skill: `idempotency` for replay attack prevention
- Use skill: `api-guidelines` for API security conventions

## Avoid

- Ignoring framework-specific security features
- Storing secrets in code or environment variables
- Disabling security features for convenience
- Logging sensitive data (passwords, tokens, PII)
- Applying security patterns from one framework to another
