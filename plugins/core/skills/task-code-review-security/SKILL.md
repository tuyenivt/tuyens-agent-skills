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

Detects the project stack and delegates to the matching stack-specific security review (`task-{stack}-review-security`). When no stack workflow matches (unknown or unsupported stack), runs a minimal generic OWASP Top 10 review.

## When to Use

- Dedicated security audits, pre-pentest hardening
- Authentication / authorization flow review
- Input handling, file upload, secrets handling assessment

Scope is the resolved branch diff vs base (PR-shaped, per `review-precondition-check`) - not a whole-codebase audit.

**Not for:** General review (`task-code-review`), performance (`task-code-review-perf`), observability gaps (`task-code-review-observability`).

## Invocation

`/task-code-review-security [<branch> | pr-<N>] [standard | deep] [--base <branch>]`

When invoked as a subagent by `task-code-review` (extra scope), the parent supplies the detected stack, precondition handle, and read-once diff/log: skip Steps 2-3, run Step 4 on the supplied diff, return findings per Output Format, and skip Step 5 - the parent owns the report.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Dispatch to Stack Workflow

| Detected stack       | Delegate to                    |
| -------------------- | ------------------------------ |
| Java / Spring Boot   | `task-spring-review-security`  |
| Python               | `task-python-review-security`  |
| Ruby / Rails         | `task-rails-review-security`   |
| Node.js / TypeScript | `task-node-review-security`    |
| Go / Gin             | `task-go-review-security`      |

A row matches only when the detected framework matches it (Java / Micronaut does not match Java / Spring Boot - use the fallback). Forward arguments and stop. **If matched, skip Steps 4-5.** If the matched workflow does not resolve (stack plugin not installed), state that and run Steps 4-5 instead.

### Step 4 - Generic Fallback (no dispatch)

Use skill: `review-precondition-check` when running standalone (skip if the parent supplied a handle). Read diff and commit log once. Depth `standard` (default): review diff hunks plus immediate context; `deep`: read each touched file in full.

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

Every finding states an attack scenario, not just a code observation. Next Steps map severity to intent: Critical/High -> `[Must]`, Medium/Low -> `[Recommend]`; `[Question]` only when the fix depends on the author's answer.

### Step 5 - Write Report

Standalone only - subagent runs return findings to the parent instead. Use skill: `review-report-writer` with `report_type: review-security` and every required input: `report_body`, `branch` (from the handle), refs from the precondition handle, SHAs via `git rev-parse`, `stack` from `stack-detect` (kebab-case `<language>-<framework>`, or `unknown`), `depth` from the invocation (default `standard`), `scope: +sec`, and `mode: full`, `round: 1` - unless `review-security-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha`. (The handle's `prior_checkpoint` is keyed to the general review report - do not use it here.)

## Output Format

When Step 3 dispatched: the stack workflow owns the output. When fallback ran:

```markdown
## Security Review Summary

**Stack Detected:** [stack-detect result, or unknown] (generic fallback applied)
**Overall Posture:** Clean | Issues Found - [Critical/High/Medium/Low counts]

## OWASP Coverage

[One line per Top 10 category: `<Category>: No issues found | <N> finding(s)`]

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

_Omit severity sections with no findings. If all are omitted, state "No security issues found." and omit Next Steps._

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: dependencies] - [one-line action]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran
- [ ] Step 3: if matched and installed, stack workflow ran with arguments forwarded; Steps 4-5 skipped
- [ ] Step 4: if not dispatched, every OWASP category in the coverage list (including clean ones); auth enforcement verified end-to-end (not spot-checked); no credentials in code/config; every finding states an attack scenario
- [ ] Step 5: report written via `review-report-writer` with all required inputs (standalone fallback only; subagent runs return findings to the parent)

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Writing a report when invoked as a subagent - the parent owns it
- Chaining `mode`/`round` off the general review's checkpoint instead of `review-security-<branch>.md`
- Vulnerabilities reported without an attack scenario
- Silently skipping OWASP categories that look clean
- Recommendations that conflict with the framework's built-in security model
- Treating the fallback as equivalent to a stack workflow
- Emitting labels outside `[Must]` / `[Recommend]` / `[Question]`
