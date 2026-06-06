---
name: task-code-review-security
description: Security review entry point: OWASP Top 10 baseline. Detects stack and dispatches to stack-specific security review workflow.
metadata:
  category: review
  tags: [security, owasp, vulnerabilities, auth, multi-stack, router]
  type: workflow
user-invocable: true
---

# Security Review (Router)

Detects the project stack and delegates to the matching stack-specific security review (`task-{stack}-review-security`). For unknown stacks, runs a minimal generic OWASP Top 10 review.

## When to Use

- Dedicated security audits, pre-pentest hardening
- Authentication / authorization flow review
- Input handling, file upload, secrets handling assessment

**Not for:** General review (`task-code-review`), performance (`task-code-review-perf`), observability gaps (`task-code-review-observability`).

## Invocation

`/task-code-review-security [<branch> | pr-<N>] [quick | standard | deep] [--base <branch>]`

When invoked as a subagent by `task-code-review`, the parent passes the precondition handle and read-once diff/log; forward to the dispatched stack workflow.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Dispatch to Stack Workflow

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

Forward arguments and stop. **If matched, skip Steps 4-5.**

### Step 4 - Generic Fallback (unknown stack only)

Use skill: `review-precondition-check` when running standalone (skip if the parent supplied a handle). Read diff and commit log once.

**Cover every OWASP Top 10 category explicitly.** State "No issues found" per category when clean - do not silently skip.

| Category                      | Must check                                                                                                              |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Broken Access Control         | Auth enforced on every endpoint (route/method level, not spot-checked); no IDOR; tenant isolation                       |
| Cryptographic Failures        | No weak algorithms; proper key management; password hashing via BCrypt/Argon2/scrypt; TLS enforced                      |
| Injection                     | Parameterized queries; no SQL string concat; no shell-out with user input; ORM query builders                           |
| Insecure Design               | Authorization model defined; threat model considered; rate limiting on sensitive endpoints                              |
| Security Misconfiguration     | Secure headers (CORS, CSP, HSTS); admin/debug endpoints disabled or auth-gated in prod; error responses do not leak     |
| Vulnerable Components         | Dependencies scanned for known CVEs                                                                                     |
| Identification and Auth       | JWT/session validation (signature, expiry, audience); CSRF protection for session-based auth; no credentials in VCS     |
| Data Integrity Failures       | Deserialization inputs validated; CI/CD pipeline integrity; signed artifacts where applicable                           |
| Logging and Monitoring        | Auth failures and access-denied events logged; no sensitive data in logs                                                |
| SSRF                          | External URLs validated and allowlisted; no user-controlled fetch targets                                               |

**Input and file handling (cross-cutting).** All user input validated through the framework's standard mechanism. Path traversal via `../` is Critical - normalize paths and verify within an allowed base. File uploads: validate by magic bytes (not extension), enforce per-file and total body size limits. Shell calls: never pass user-controlled data.

**Cloud storage (S3, GCS, Azure Blob).** Buckets private by default; signed URLs with short expiry; `Content-Disposition: attachment` on served files; malware scanning for uploads.

**Data protection.** No sensitive data in logs, client-side state, or URLs. Encryption at rest for sensitive fields. Secrets in a secret manager, not env vars or code.

Every finding states an attack scenario, not just a code observation.

### Step 5 - Write Report

Use skill: `review-report-writer` with `report_type: review-security`.

## Output Format

When Step 3 dispatched: the stack workflow owns the output. When fallback ran:

```markdown
## Security Review Summary

**Stack Detected:** unknown (generic fallback applied)
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low counts]

## Findings

### Critical

- **Location:** [file:line]
- **Issue:** [vulnerability]
- **Attack scenario:** [how an attacker exploits it]
- **Fix:** [specific remediation]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit severity sections with no findings. If all are omitted, state "No security issues found."_

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: dependencies] - [one-line action]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran
- [ ] Step 3: if matched, stack workflow ran with arguments forwarded; Steps 4-5 skipped
- [ ] Step 4: if no match, every OWASP category explicitly addressed (including clean ones); auth enforcement verified end-to-end (not spot-checked); no credentials in code/config; every finding states an attack scenario
- [ ] Step 5: report written via `review-report-writer` (fallback path only)

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Vulnerabilities reported without an attack scenario
- Silently skipping OWASP categories that look clean
- Recommendations that conflict with the framework's built-in security model
- Treating the fallback as equivalent to a stack workflow
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
