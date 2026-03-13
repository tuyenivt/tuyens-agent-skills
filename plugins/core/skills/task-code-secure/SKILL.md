---
name: task-code-secure
description: Security review for a PR, feature, or codebase - OWASP Top 10, injection vulnerabilities, broken auth, XSS, CSRF, insecure file handling, secrets exposure, and authorization gaps. Use when you need a dedicated security audit: pre-pentest hardening, reviewing auth flows, assessing file upload or user input handling, or checking for IDOR and privilege escalation. Not for general PR review (use task-code-review or task-code-review-advanced) and not for performance issues (use task-code-perf-review).
metadata:
  category: review
  tags: [security, owasp, vulnerabilities, auth, multi-stack]
  type: workflow
user-invocable: true
---

# Code Secure

## When to Use

- Security reviews of code changes
- Pre-deployment security checks
- Vulnerability assessment
- Authentication and authorization review

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Step 2 - OWASP Quick Check (All Stacks)

| Risk                      | Check                                                 |
| ------------------------- | ----------------------------------------------------- |
| Broken Access Control     | Auth on all endpoints                                 |
| Injection                 | Parameterized queries, no string concatenation in SQL |
| Cryptographic Failures    | No weak algorithms, proper key management             |
| Security Misconfiguration | Secure headers (CORS, CSP, HSTS)                      |
| SSRF                      | Validate/allowlist external URLs                      |
| XSS                       | Output encoding, no raw HTML injection                |

### Step 3 - Framework-Specific Security Review

After loading stack-detect, apply security checks specific to the detected ecosystem:

**Authentication & Authorization:**

- Verify the framework's auth mechanism is properly configured (security filters, auth middleware, before-action hooks, etc.)
- Check method/route-level authorization enforcement
- Verify JWT or session token validation (signature, expiry, audience)
- Ensure password hashing uses a strong algorithm (BCrypt, Argon2, scrypt)
- No credentials in code, config files, or version control

**Input Validation:**

- Verify the framework's standard validation mechanism is applied to all user input
- No raw SQL concatenation - use parameterized queries or the ORM's query builder
- Validate and sanitize all user-provided data before use

**Common Vulnerability Patterns:**

- CSRF protection is enabled for session-based auth (using the framework's built-in mechanism)
- CORS is configured restrictively
- Error responses do not leak stack traces or internal details
- No command injection via user-controlled input passed to system calls
- TLS enforced in production
- Framework-specific admin/debug endpoints are secured or disabled in production

If the detected stack is unfamiliar, apply the OWASP checks from Step 2 and recommend the user consult their framework's security documentation.

### Step 4 - Data Protection (All Stacks)

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

## Self-Check

- [ ] Every OWASP Top 10 category checked - not just the ones with obvious findings
- [ ] Auth enforcement verified on every endpoint, not just spot-checked
- [ ] No secrets, tokens, or credentials found in code or config files
- [ ] Data protection checks run: PII logging, encryption at rest, secure headers
- [ ] Framework-specific checks applied for the detected stack
- [ ] Every finding states an attack scenario, not just a code observation
- [ ] If no findings: explicitly state "No issues found" per category - do not omit sections silently

## Output Format

```markdown
## Security Review Summary

**Stack Detected:** [language / framework]
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

[2-3 sentence assessment of the overall security posture]

## Findings

### Critical

- **Location:** [file:line]
- **Issue:** [vulnerability description]
- **Attack scenario:** [how an attacker exploits this]
- **Fix:** [specific remediation with code example if applicable]

### High

- **Location:** [file:line]
- **Issue:** [vulnerability description]
- **Attack scenario:** [how an attacker exploits this]
- **Fix:** [specific remediation]

### Medium

[Same structure]

### Low

[Same structure]

_Omit severity sections with no findings. If all sections are omitted, state "No security issues found."_

## Recommendations

[Prioritized improvements that are not specific findings but would strengthen the overall posture - e.g., "Add rate limiting to all auth endpoints", "Enable HSTS in production config"]
```
