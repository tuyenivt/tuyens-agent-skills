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

**Not for:** General review (`task-code-review`), performance (`task-code-review-perf`), observability gaps (`task-code-review-observability`), reliability (`task-code-review-reliability`).

## Invocation

`/task-code-review-security [<branch> | pr-<N>] [standard | deep] [--base <branch>]`

When invoked as a subagent by `task-code-review` (extra scope), the parent supplies the detected stack (the full stack-detect output, including `Stack Type`), precondition handle, read-once diff/log, and active depth: skip Steps 2-3 (Step 1 still applies), run Step 4 on the supplied diff, return the subagent envelope defined in Output Format, and skip Step 5 - the parent owns the report. Read-once covers the diff and log; at `deep`, touched files may still be read in full.

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
| React / Next.js / Vite | `task-react-review-security` |

A row matches only when the detected framework matches it (Java / Micronaut does not match Java / Spring Boot - use the fallback); a row named by language alone (Python) matches that language under any framework; the Node.js / TypeScript row matches Language `JavaScript` or `TypeScript` with a server framework (NestJS, Express, Fastify, Koa, Hono) or none; `React (...)` takes the React row, and another frontend framework (Vue, Angular, Svelte) matches no row. Announce the dispatch in one line (`Dispatching to task-rails-review-security.` - substitute the target), forward the arguments unchanged, and stop. **If matched, skip Steps 4-5.** If the matched workflow does not resolve (stack plugin not installed), announce it in one line (`task-rails-review-security is provided by the ruby plugin, which is not installed - running the generic security review.` - substitute the row's target and its plugin: `java`, `python`, `ruby`, `node`, `go`, `react`) and run Steps 4-5 instead. A detected stack matching no row at all falls through to the Step 4 generic fallback - announce it in one line (`No stack security workflow for <stack> - running the generic security review.`, `<stack>` = the detection's Language / Framework pair), then run it.

### Step 4 - Generic Fallback (no dispatch)

Use skill: `review-precondition-check` with the invocation's target, any `--base` override, and `report_type: review-security` when running standalone (skip if the parent supplied a handle); on failure, surface its message verbatim and stop. Depth `standard` (default): review diff hunks plus immediate context; `deep`: read each touched file in full.

**Round gate (standalone only).** Before reviewing, decide the round from the handle: with `report_type: review-security` passed, its `report_path` is this lens's checkpoint (`review-security-<sanitized head_short_name>.md`) and its `prior_checkpoint` is that file's frontmatter - or `legacy` when the frontmatter is missing, unparseable, or belongs to another lens or branch. If `prior_checkpoint` is a valid block, its `head_sha` equals `git rev-parse <head_ref>`, and the requested depth does not exceed its `depth` (`deep` exceeds `standard`), print `No new commits since prior security review.` and stop - no review, no report. Otherwise set `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (the Step 5 write overwrites the file) -> `round: 1`, no `prior_head_sha`. Then read the diff and commit log once.

**Cover every OWASP Top 10 category explicitly.** State "No issues found" per category when clean - do not silently skip.

| Category (OWASP Top 10:2025)               | Must check                                                                                                              |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| A01 Broken Access Control                  | Auth enforced on every endpoint (route/method level, not spot-checked); no IDOR; tenant isolation; SSRF - external URLs allowlisted, no user-controlled fetch targets |
| A02 Security Misconfiguration              | Secure headers (CORS, CSP, HSTS); admin/debug endpoints disabled or auth-gated in prod; error responses do not leak     |
| A03 Software Supply Chain Failures         | Dependency manifest/lockfile changes checked against known CVEs; build, CI/CD and distribution integrity; no dependency changes -> `No issues found` |
| A04 Cryptographic Failures                 | No weak algorithms; proper key management; password hashing via BCrypt/Argon2/scrypt; TLS enforced                      |
| A05 Injection                              | Parameterized queries; no SQL string concat; no shell-out with user input; ORM query builders; output encoding or template auto-escape on every user-supplied value rendered to HTML (XSS is Injection) |
| A06 Insecure Design                        | Authorization model defined; threat model considered; rate limiting on sensitive endpoints                              |
| A07 Authentication Failures                | JWT/session validation (signature, expiry, audience); CSRF protection for session-based auth; no credentials in VCS     |
| A08 Software or Data Integrity Failures    | Deserialization inputs validated; CI/CD pipeline integrity; signed artifacts where applicable                           |
| A09 Logging and Alerting Failures          | Auth failures and access-denied events logged and alertable; no sensitive data in logs                                  |
| A10 Mishandling of Exceptional Conditions  | Error paths handled explicitly; no fail-open on exception; abnormal conditions do not bypass authz or leave partial state |

**Input and file handling (cross-cutting).** All user input validated through the framework's standard mechanism. Path traversal via `../` on an unauthenticated input is Critical (High behind authentication) - normalize paths and verify within an allowed base. File uploads: validate by magic bytes (not extension), enforce per-file and total body size limits. Shell calls: never pass user-controlled data. Every finding is single-homed: when two OWASP rows match, count it under the more specific row - a committed secret fits both A04 key management and A07 no-credentials-in-VCS, and A07 is the more specific, so it homes there; cross-cutting and cloud-storage findings likewise fold into the closest row. The coverage list counts each finding once, under its home row - other matching rows stay `No issues found`.

**Cloud storage (S3, GCS, Azure Blob).** Buckets private by default; signed URLs with short expiry; `Content-Disposition: attachment` on served files; malware scanning for uploads.

**Data protection.** No sensitive data in logs, client-side state, or URLs. Encryption at rest for sensitive fields. Secrets in a secret manager, not env vars or code.

Every finding states an attack scenario, not just a code observation. **Severity:** Critical = exploitable now without authentication, or direct credential/financial compromise (injection on reachable input, path traversal, auth bypass); High = exploitable with a common precondition (authenticated user crossing tenancy, on-path attacker, misset env flag) or a secret committed to VCS; Medium = weakens defenses or needs an unlikely precondition (missing rate limit, unsigned webhook, verbose errors); Low = defense-in-depth hardening with no concrete attack path. Sensitive data exposed to log or storage readers at scale is High; when exploitation needs two independent preconditions, rate one tier lower. Severity assigns each finding an initial intent (Critical/High -> `[Must]`, Medium/Low -> `[Recommend]`); where `review-finding-verify` publishes a different `Label`, the published label governs every slot naming one. A defect outside this lens that would break the build, or corrupt or expose data, becomes an `out of lens` line (shape in Output Format). Next Steps carry each finding published label and tag each step `[Implement]` (localized fix) or `[Delegate]` (cross-cutting, platform, or dependency-owned).

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` and `Annotation` columns; the Summary's `Findings verified:` line is the Summary form the atomic prescribes, filled from its tally (`<N> confirmed, <M> reattributed, <U> unverified, <K> dropped`, plus its false-positive/resolved split when emitted) - the verify table itself stays internal. On round 2+, after verification, re-project the prior report's findings (the file at the handle's `report_path`) into reconcile's parse shape - a `## High-Impact Findings` section, one `### [Label] file:line` heading per finding from its label line (or, when the prior report wrote no label line, the label its severity section maps to under this lens's severity rule - reconcile's verbatim rule has nothing to preserve there) and the `file:line` prefix of its Location line (trailing component prose stays out of the heading), keeping a `_(pre-existing)_` annotation on the heading (reconcile splits untouched files on it; verify's combined `_(pre-existing; newly reachable via ...)_` is written as two groups, `_(pre-existing)_ _(newly reachable via ...)_`), with its Issue line as the smell - then Use skill: `review-prior-findings-reconcile` with that projection, the diff, `git diff --name-status <base_ref>...<head_ref>`, and `head_sha`. Its table and tally render as `## Prior Round Reconciliation` between Findings and Next Steps; unresolved rows carry into their prior severity sections at their prior label, noted `_(carried from round <N>)_` (`<N>` = the prior report's own `round`) after the label on its label line, its prior Location annotation kept; the reconciliation table row and its Next Steps entry are its only other appearances. A prior label outside `[Must]` / `[Recommend]` (`[Blocker]`, `[High]`, `[Question]` in a legacy report) stays verbatim in that table, which reconcile owns, and maps before it is published in a findings section: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; `[Suggestion]`, `[Nitpick]`, `[Question]`, `[Medium]`, `[Low]`, and any unrecognised label -> `[Recommend]`; `[Praise]` rows are never carried. A carried finding this round's own pass re-derives publishes once, in the findings sections, not twice. The table preserves each prior citation exactly; the published finding carries the corrected `file:line` when verification found the prior cite stale. Subagent runs skip both - the parent verifies and reconciles its own merged set once.

### Step 5 - Write Report

Standalone only - subagent runs return findings to the parent instead. Use skill: `review-report-writer` with `report_type: review-security` and every required input: `report_body`, `branch` (the handle's `head_short_name`), refs from the precondition handle, SHAs via `git rev-parse`, `pr_url` when the request text carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` when present, `stack` from `stack-detect` (kebab-case `<language>-<framework>`, versions dropped; drop a segment reported unknown; `unknown` only when detection failed entirely), `depth` from the invocation (default `standard`), `scope: +sec`, `mode: full`, and `round` plus `prior_head_sha` from the Step 4 round gate.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

When Step 3 dispatched: the stack workflow owns the output. Subagent runs return the `## OWASP Coverage` list plus the `## Findings` heading, its severity sections, and any `out of lens` lines only - Summary, Prior Round Reconciliation, Next Steps, and the report file are standalone-only. In every mode each finding block opens with its label on its own line, `**[Must]**` or `**[Recommend]**`, before `Location`, and empty severity sections are omitted. A finding sits in the section matching its **severity**; its label line and its Next Steps entry carry its **published label**. The two diverge whenever verification de-escalated a pre-existing finding - a `**[Recommend]**` inside `### Critical` is correct, not a mismatch to fix. A defect outside this lens that would break the build, or corrupt or expose data gets one line at the end of `## Findings` marked `out of lens`, so it is not silently dropped; anything else outside the lens is left to `task-code-review`. Verify annotations (the Annotation column: `_(pre-existing)_`, `_(pre-existing; newly reachable via ...)_`, `_(unverified: ...)_`, `_(mechanism: ...)_`) sit on the `Location` line (standalone only - subagent runs skip verification). A clean run in either mode returns all-clean Coverage rows plus `## Findings` containing `No security issues found.`. Standalone runs emit the report body in chat, then the writer's confirmation line. When fallback ran standalone:

```markdown
## Security Review Summary

- **Stack Detected:** [kebab-case `<language>-<framework>`, versions dropped - the same string passed as the writer `stack` input; or `unknown`] (generic fallback: no stack workflow) | (generic fallback: `<plugin>` plugin not installed)
- **Depth:** standard | deep
- **Overall Posture:** Clean | Issues Found - <C> Critical / <H> High / <M> Medium / <L> Low
- **Round:** [N]   {round 2+ only}
- **Findings verified:** [from `review-finding-verify`'s tally, in its Summary form: `<N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}`]

## OWASP Coverage

[One `- ` bullet per Top 10 category, in A01-A10 order: `- <Category>: No issues found | 1 finding | <N> findings`. Bullets, not bare lines - ten stacked `Label: value` lines collapse into one paragraph in the emitted report.]

## Findings

### Critical

**[Must | Recommend]**{ _(carried from round <N>)_}
- **Location:** [file:line]{ the verify Annotation, standalone only}
- **Issue:** [vulnerability]
- **Attack scenario:** [how an attacker exploits it]
- **Fix:** [specific remediation for the detected stack]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

_Omit severity sections with no findings. If all are omitted, state "No security issues found." (before any `out of lens` line) and omit Next Steps._

- **out of lens:** file:line - [the defect in one sentence, and the lens that owns it]   {only when a defect outside this lens would break the build or corrupt or expose data}

## Prior Round Reconciliation

[table and tally from `review-prior-findings-reconcile` - round 2+ standalone runs only; omit the section otherwise]

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: dependencies] - [one-line action]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (subagent runs: loaded, or rules inlined in the spawning prompt)
- [ ] Step 2: `stack-detect` ran (subagent runs: parent-supplied detection accepted instead)
- [ ] Step 3: if matched and installed, dispatch announced and stack workflow ran with arguments forwarded, Steps 4-5 skipped; if not installed or no row matched, the announcement printed and fallback ran (skipped entirely on subagent runs)
- [ ] Step 4: if not dispatched, SHAs captured; round gate decided from the handle (`report_type: review-security`) before the diff was read; `out of lens` lines emitted for qualifying defects outside the lens; every OWASP category in the coverage list (including clean ones); auth enforcement verified end-to-end (not spot-checked); no credentials in code/config; every finding states an attack scenario and a rubric-based severity; prior findings projected into reconcile's parse shape and reconciled on round 2+; the round gate, `review-finding-verify` (whose tally fills the `Findings verified:` Summary line) and reconciliation are standalone-only - subagent runs skip all three
- [ ] Step 5: report written via `review-report-writer` with all required inputs, or the round-gate stop line printed, or a precondition failure surfaced verbatim with no report written (standalone fallback only; subagent runs return findings to the parent)

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Writing a report when invoked as a subagent - the parent owns it
- Chaining `round` / `prior_head_sha` off the general review's checkpoint instead of `review-security-<branch>.md` (`mode` is always `full`, never chained)
- Vulnerabilities reported without an attack scenario
- Silently skipping OWASP categories that look clean
- Recommendations that conflict with the framework's built-in security model
- Treating the fallback as equivalent to a stack workflow
- Emitting labels outside `[Must]` / `[Recommend]` in the findings sections (the reconciliation table preserves prior labels verbatim)
