---
name: task-code-review-security
description: Security review entry point: OWASP Top 10 baseline. Detects stack and dispatches to stack-specific security review workflow.
metadata:
  category: review
  tags: [security, owasp, vulnerabilities, auth, multi-stack, router]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Security Review (Router)

This skill is a thin dispatcher. It detects the project stack and delegates to the matching stack-specific skill (e.g., `task-spring-review-security`, `task-rails-review-security`, `task-react-review-security`). The stack workflow names ecosystem-specific security idioms directly (Rails: Devise / Pundit / strong params; Spring Security: filter chain, method security; FastAPI: dependency-injected auth).

For unknown stacks, this skill falls back to a minimal generic OWASP Top 10 review.

## When to Use

- Dedicated security audits, pre-pentest hardening
- Authentication / authorization flow review
- Input handling, file upload, secrets handling assessment

**Not for:** General code review (use `task-code-review`), performance issues (use `task-code-review-perf`), observability gaps (use `task-code-review-observability`).

## Invocation

Accepts the same diff-targeting arguments as `task-code-review`. When invoked as a subagent of `task-code-review`, the parent passes the precondition handle plus the read-once diff/log; this is forwarded to the dispatched stack workflow.

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect`.

### Step 2 - Dispatch to Stack Workflow

| Detected stack       | Delegate to                    |
| -------------------- | ------------------------------ |
| Java / Spring Boot   | `task-spring-review-security`  |
| Kotlin / Spring Boot | `task-kotlin-review-security`  |
| Python               | `task-python-review-security`  |
| Ruby / Rails         | `task-rails-review-security`   |
| Node.js / TypeScript | `task-node-review-security`    |
| Go / Gin             | `task-go-review-security`      |
| Rust / Axum          | `task-rust-review-security`    |
| .NET / ASP.NET Core  | `task-dotnet-review-security`  |
| PHP / Laravel        | `task-laravel-review-security` |
| React                | `task-react-review-security`   |
| Vue                  | `task-vue-review-security`     |
| Angular              | `task-angular-review-security` |

If matched, forward arguments and stop. Do not run Step 3.

### Step 3 - Generic Fallback (unknown stack only)

Use skill: `review-precondition-check` if running standalone. Read diff and commit log once.

**OWASP Top 10 quick check:**

| Risk                          | Check                                                                                                       |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Auth enforced on all endpoints; no direct object reference without access check                             |
| Injection                     | Parameterized queries; no SQL string concatenation; no shell-out with user input                            |
| Cryptographic Failures        | No weak algorithms; proper key management; password hashing via BCrypt/Argon2/scrypt                        |
| Security Misconfiguration     | Secure headers (CORS, CSP, HSTS); admin/debug endpoints secured or disabled in production                   |
| SSRF                          | External URLs validated/allowlisted                                                                         |
| XSS                           | Output encoding; no raw HTML injection                                                                      |
| Insecure Design               | Authorization model defined; threat model considered                                                        |
| Vulnerable Components         | Dependencies checked for known CVEs                                                                         |
| Data Integrity Failures       | Deserialization inputs validated; CI/CD pipeline integrity                                                  |
| Logging & Monitoring Failures | Security events logged (auth failures, access denied); no sensitive data in logs                            |

**Auth and authz:**

- Verify auth mechanism is properly configured (filters, middleware, decorators)
- Method/route-level authorization enforced, not just spot-checked
- JWT/session token validation: signature, expiry, audience
- No credentials in code, config files, or version control

**Input validation:**

- All user input validated via the framework's standard mechanism
- No raw SQL concatenation - parameterized queries or ORM query builders
- File path operations: validate and normalize paths; check result is within allowed base directory (path traversal via `../` is Critical)
- File uploads: validate by magic bytes, not just extension; enforce per-file and total request body size limits
- Shell/system calls: never pass user-controlled data; prefer API alternatives

**Common vulnerabilities:**

- CSRF protection enabled for session-based auth
- CORS configured restrictively
- Error responses do not leak stack traces or internal details
- TLS enforced in production

**Cloud storage** (S3, GCS, Azure Blob, equivalent):

- Bucket access policy is private; no public read unless explicitly required
- Signed URLs with short expiry (minutes); `Content-Disposition: attachment` on served files
- Virus/malware scanning pipeline for uploads

**Data protection:**

- Sensitive data not logged (passwords, tokens, full PII)
- Encryption at rest for sensitive fields
- Secrets in secret manager, not env vars or code
- No sensitive data in client-side state or URLs

**Step 4 - Write Report:** Use skill: `review-report-writer` with `report_type: review-security`.

## Output Format

When dispatched (Step 2 matched): the stack-specific workflow owns the output.

When fallback runs (Step 3):

```markdown
## Security Review Summary

**Stack Detected:** unknown (generic fallback applied)
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low count]

## Findings

### Critical

- **Location:** [file:line]
- **Issue:** [vulnerability description]
- **Attack scenario:** [how an attacker exploits this]
- **Fix:** [specific remediation]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit severity sections with no findings. If all are omitted, state "No security issues found."_

## Next Steps

1. **[Implement]** [Critical] file:line - [one-line action]
2. **[Delegate]** [High] [scope: dependencies] - [one-line action]
```

## Self-Check

- [ ] `behavioral-principles` loaded before any other step
- [ ] `stack-detect` ran at Step 1
- [ ] If a stack matched, the dispatched workflow ran and Step 3 was skipped
- [ ] If no stack matched, every OWASP Top 10 category checked - not just the ones with obvious findings
- [ ] Auth enforcement verified on every endpoint, not spot-checked
- [ ] No secrets, tokens, or credentials found in code or config files
- [ ] Every finding states an attack scenario, not just a code observation
- [ ] Review report written to file via `review-report-writer`

## Avoid

- Running both Step 2 dispatch and Step 3 fallback
- Reporting vulnerabilities without an attack scenario
- Skipping OWASP categories that appear clean - explicitly state "No issues found" per category
- Recommending security measures that conflict with the framework's built-in security model
- Treating the fallback as a full equivalent of a stack workflow - install the matching language plugin when one exists
