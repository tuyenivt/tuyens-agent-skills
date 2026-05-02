---
name: task-code-review-security
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

**Not for:** General PR review (use `task-code-review`), performance issues (use `task-code-review-perf`), observability gaps (use `task-code-review-observability`).

## Invocation

Accepts the same diff-targeting arguments as `task-code-review`:

| Invocation                            | Meaning                                                                                               |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/task-code-review-security`          | Review current branch vs its base - fails fast if on a trunk branch; switch to a feature branch first |
| `/task-code-review-security <branch>` | Review `<branch>` vs its base (3-dot diff)                                                            |
| `/task-code-review-security pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` (user runs the fetch first)                       |

When invoked as a subagent of `task-code-review`, the parent passes the precondition-check handle plus the already-read diff and commit log; Step 2 below is skipped and this workflow reuses the parent's read-once artifacts.

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). On approval, read the diff and commit log once via `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>`, then reuse them for all subsequent steps. Skip this step entirely if running as a subagent of `task-code-review` and the parent passed the handle plus pre-read artifacts.

If `review-precondition-check` stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

### Step 3 - OWASP Quick Check (All Stacks)

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

### Step 4 - Framework-Specific Security Review

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

If the detected stack is unfamiliar, apply the OWASP checks from Step 3 and recommend the user consult their framework's security documentation.

**Cloud Storage (when file storage is S3, GCS, Azure Blob, or equivalent):**

- Bucket/container access policy is private; no public read unless explicitly required
- Signed URLs scoped to specific objects with short expiry (minutes, not hours)
- Content-Disposition: attachment header set on served files to prevent browser rendering of uploaded HTML/SVG
- Virus/malware scanning pipeline for uploaded files (or document the accepted risk)

### Step 5 - Data Protection (All Stacks)

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

- [ ] `review-precondition-check` ran (or its handle was received from the parent workflow); `base_ref`, `head_ref`, `current_branch`, `head_matches_current` captured
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all steps - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced (not executed by the workflow) and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran (skipped when invoked as a subagent - the parent already gated)
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

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reporting vulnerabilities without an attack scenario ("input is not validated" vs "attacker can inject SQL via the search parameter")
- Skipping OWASP categories that appear clean - explicitly state "No issues found" per category
- Recommending security measures that conflict with the framework's built-in security model
- Conflating security review with general code quality review - stay focused on vulnerabilities
- Suggesting overly complex security measures for low-risk surfaces
