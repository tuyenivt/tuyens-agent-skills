---
name: task-code-secure-review
description: Security review for a PR, feature, or codebase - OWASP Top 10, injection, broken auth, XSS, CSRF, secrets exposure, and authorization gaps. Use for dedicated security audits, pre-pentest hardening, reviewing auth flows, or assessing input handling and file uploads.
metadata:
  category: review
  tags: [security, owasp, vulnerabilities, auth, multi-stack]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Code Secure Review

## Purpose

Security-focused review targeting OWASP Top 10 vulnerabilities, authentication/authorization gaps, input validation, data protection, and framework-specific security patterns. Produces findings with attack scenarios and specific remediations.

## When to Use

- Security reviews of code changes
- Pre-deployment security checks
- Vulnerability assessment
- Authentication and authorization review

**Not for:** General PR review (use `task-code-review`), performance issues (use `task-code-perf-review`), observability gaps (use `task-code-observability-review`).

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Step 2 - OWASP Quick Check (All Stacks)

| Risk                          | Check                                                                                                       |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Auth on all endpoints                                                                                       |
| Injection                     | Parameterized queries, no string concatenation in SQL                                                       |
| Cryptographic Failures        | No weak algorithms, proper key management                                                                   |
| Security Misconfiguration     | Secure headers (CORS, CSP, HSTS)                                                                            |
| SSRF                          | Validate/allowlist external URLs                                                                            |
| XSS                           | Output encoding, no raw HTML injection                                                                      |
| Insecure Design (A04)         | Authorization model defined; no direct object references without access check                               |
| Vulnerable Components (A06)   | Dependencies checked for known CVEs; no outdated packages with security patches available                   |
| Data Integrity Failures (A08) | Deserialization inputs validated; CI/CD pipeline integrity                                                  |
| Logging & Monitoring (A09)    | Security events logged (login failures, access denied, input validation failure); no sensitive data in logs |

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
- **File path operations**: validate and normalize paths (use `path.resolve()` or equivalent, then check result is within an allowed base directory) - path traversal via `../` sequences in filenames is Critical
- **File upload handling**: validate file types by magic bytes (not just extension), enforce per-file size limits and total request body size limits in middleware (e.g., multer `fileSize`, Spring `MaxUploadSize`, ASP.NET `RequestSizeLimit`)
- **Shell/system calls**: never pass user-controlled data to `exec`, `spawn`, or equivalent; prefer API-based alternatives over shelling out

**Common Vulnerability Patterns:**

- CSRF protection is enabled for session-based auth (using the framework's built-in mechanism)
- CORS is configured restrictively
- Error responses do not leak stack traces or internal details
- No command injection via user-controlled input passed to system calls
- TLS enforced in production
- Framework-specific admin/debug endpoints are secured or disabled in production

If the detected stack is unfamiliar, apply the OWASP checks from Step 2 and recommend the user consult their framework's security documentation.

**Cloud Storage (when file storage is S3, GCS, Azure Blob, or equivalent):**

- Bucket/container access policy is private; no public read unless explicitly required
- Signed URLs scoped to specific objects with short expiry (minutes, not hours)
- Content-Disposition: attachment header set on served files to prevent browser rendering of uploaded HTML/SVG
- Virus/malware scanning pipeline for uploaded files (or document the accepted risk)

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

## Avoid

- Reporting vulnerabilities without an attack scenario ("input is not validated" vs "attacker can inject SQL via the search parameter")
- Skipping OWASP categories that appear clean - explicitly state "No issues found" per category
- Recommending security measures that conflict with the framework's built-in security model
- Conflating security review with general code quality review - stay focused on vulnerabilities
- Suggesting overly complex security measures for low-risk surfaces
