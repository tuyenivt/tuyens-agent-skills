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

| Detected stack       | Delegate to                    | Plugin    |
| -------------------- | ------------------------------ | --------- |
| Java / Spring Boot   | `task-spring-review-security`  | `java`    |
| Python               | `task-python-review-security`  | `python`  |
| Ruby / Rails         | `task-rails-review-security`   | `ruby`    |
| Node.js / TypeScript | `task-node-review-security`    | `node`    |
| Go / Gin             | `task-go-review-security`      | `go`      |
| React / Next.js      | `task-react-review-security`   | `react`   |
| C# / Unity           | `task-unity-review-security`   | `unity`   |
| Dart / Flutter       | `task-flutter-review-security` | `flutter` |

Dispatch keys on the detection's primary `Language` / `Framework` pair; a secondary stack in `Additional` never dispatches. A row matches when both its language and its framework match - a trailing version never blocks a match (`Spring Boot 4.1`, `Unity 6000.3.21f1`), while another language or framework does (Kotlin / Spring Boot and Java / Micronaut take the fallback). Python matches under any framework; Node.js / TypeScript matches Language `JavaScript` or `TypeScript` with a server framework (NestJS, Express, Fastify, Koa, Hono) or `unknown`; a Framework naming Next.js (`React (Next.js)`, `Next.js 16.3 (App Router)`) takes the React row, and every other frontend framework (Vite, CRA, React Router, Remix, Vue, Angular, Svelte) matches no row. Exactly one outcome follows, its one-line announcement printed in chat before anything else and never part of `report_body`:

- Matched and installed: `Dispatching to task-rails-review-security.` (substitute the target); invoke it with the arguments unchanged and stop - Steps 4-5 do not run.
- Matched, plugin not installed: `task-rails-review-security is provided by the ruby plugin, which is not installed - running the generic security review.` (substitute target and plugin); run Steps 4-5.
- No row: `No stack security workflow for <Language> / <Framework> - running the generic security review.`; run Steps 4-5.

### Step 4 - Generic Fallback (no dispatch)

Use skill: `review-precondition-check` with `argument` (the invocation's target, if any), `base` (from `--base`, if given), and `report_type: review-security` when running standalone (skip it when the parent supplied a handle); on failure, surface its message verbatim and stop; on success, print each handle `notes` entry in chat, one line each, before the report body. Standalone, capture `base_sha` / `head_sha` via `git rev-parse <base_ref>` / `git rev-parse <head_ref>`. Depth `standard` (default): review diff hunks plus immediate context; `deep`: read each touched file in full. A defect the diff did not introduce, found in that read, is drafted like any other and verification attributes it; a file the diff does not touch is read only to confirm what a finding depends on, and a defect in it is drafted only when the diff newly reaches it.

**Round gate (standalone only).** The handle's `prior_checkpoint` is this lens's checkpoint (`review-security-<sanitized head_short_name>.md`) frontmatter, or `legacy` when that is missing, unparseable, or another lens's or branch's. When it is a valid block whose `head_sha` equals the captured `head_sha`, whose `base_ref` equals the handle's, and whose `depth` the requested depth does not exceed (`deep` exceeds `standard`), print `No new commits since prior security review.` and stop - no review, no report. Otherwise a valid block gives `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; absent or `legacy` gives `round: 1` and no `prior_head_sha` (Step 5 overwrites a legacy file). Then read `git diff <base_ref>...<head_ref>` and `git log <base_ref>..<head_ref>` once.

**Cover every OWASP Top 10 category explicitly.** State "No issues found" per category when clean - do not silently skip.

| Category (OWASP Top 10:2025)               | Must check                                                                                                              |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| A01 Broken Access Control                  | Auth enforced on every endpoint (route/method level, not spot-checked); no IDOR; tenant isolation; CSRF protection on state-changing requests under session/cookie auth; SSRF - external URLs allowlisted, no user-controlled fetch targets |
| A02 Security Misconfiguration              | Secure headers (CORS, CSP, HSTS); admin/debug endpoints disabled or auth-gated in prod                                  |
| A03 Software Supply Chain Failures         | Dependency manifest/lockfile changes checked against known CVEs; a compromised dependency, build, CI/CD or distribution channel; no dependency changes -> `No issues found` |
| A04 Cryptographic Failures                 | No weak algorithms; proper key management; password hashing via BCrypt/Argon2/scrypt; TLS enforced                      |
| A05 Injection                              | Parameterized queries; no SQL string concat; no shell-out with user input; ORM query builders; output encoding or template auto-escape on every user-supplied value rendered to HTML (XSS is Injection) |
| A06 Insecure Design                        | Authorization model defined; threat model considered; rate limiting on sensitive endpoints                              |
| A07 Authentication Failures                | JWT/session validation (signature, expiry, audience); no credentials in VCS                                             |
| A08 Software or Data Integrity Failures    | Deserialization inputs validated; an artifact, update, or CI-pulled code used without signature or checksum verification |
| A09 Security Logging and Alerting Failures | Auth failures and access-denied events logged and alertable; no sensitive data in logs                                  |
| A10 Mishandling of Exceptional Conditions  | Error paths handled explicitly; no fail-open on exception; abnormal conditions do not bypass authz or leave partial state; error responses and stack traces leak no internals |

**Input and file handling (cross-cutting).** All user input validated through the framework's standard mechanism. Path traversal via `../` on an unauthenticated input is Critical (High behind authentication) - normalize paths and verify within an allowed base. File uploads: validate by magic bytes (not extension), enforce per-file and total body size limits. Shell calls: never pass user-controlled data. Every finding is single-homed: when two rows match, it counts under the more specific one - a committed secret fits A04 key management and A07 no-credentials-in-VCS, and homes in A07; a compromised dependency homes in A03, an unverified artifact in A08; cross-cutting and cloud-storage findings fold into the closest row. The coverage list counts each finding once, under its home row - other matching rows stay `No issues found`.

**Cloud storage (S3, GCS, Azure Blob).** Buckets private by default; signed URLs with short expiry; `Content-Disposition: attachment` on served files; malware scanning for uploads.

**Data protection.** No sensitive data in logs, client-side state, or URLs. Encryption at rest for sensitive fields. Secrets in a secret manager, not env vars or code.

Every finding states an attack scenario, not just a code observation. **Severity:** Critical = exploitable now without authentication, or direct credential/financial compromise (injection on reachable input, path traversal, auth bypass); High = exploitable with a common precondition (authenticated user crossing tenancy, on-path attacker, misset env flag) or a secret committed to VCS; Medium = weakens defenses or needs an unlikely precondition (missing rate limit, unsigned webhook, verbose errors); Low = defense-in-depth hardening with no concrete attack path. Sensitive data exposed to log or storage readers at scale is High; when exploitation needs two independent preconditions, rate one tier lower. Severity sets the initial intent: Critical/High -> `[Must]`, Medium/Low -> `[Recommend]`; where `review-finding-verify` publishes a different `Label`, the published label governs every slot naming one.

**Verify findings (standalone only).** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, taking each row's `file:line` (a `-` cell - verify's `no cite` row - publishes at `<path>:1` of the file the drafted claim names, else of the touched file whose hunk raised it, keeping `_(unverified: no cite)_`; never a directory), `Label`, and `Annotation` columns. The Summary's `Findings verified:` line is the atomic's Summary form of its tally, which counts its table only; the verify table stays internal.

**Reconcile (round 2+, standalone only).** After verification, project the prior report (the file at the handle's `report_path`) into reconcile's parse shape: a `## High-Impact Findings` section, one `### [Label] file:line` heading per finding - the label from its label line (with none, the label its severity section maps to under this lens's rule), the bare `file:line` prefix of its Location line, then its annotations as separate `_(...)_` groups (`_(pre-existing; newly reachable via X)_` splits into `_(pre-existing)_ _(newly reachable via X)_`; a label line's `_(carried from round <N>)_` follows as its own group) - each followed by an `Issue:` line with its Issue text. Use skill: `review-prior-findings-reconcile` with that projection, the diff, `git diff --name-status <base_ref>...<head_ref>`, and `head_sha`; its output (table, any note lines, tally) renders verbatim as `## Prior Round Reconciliation`. A `Still open` or `Needs re-check` row this round's pass did not re-derive publishes in its prior severity section at its prior label - `[Blocker]`, `[High]`, `[Critical]` map to `[Must]`, any other label outside `[Must]` / `[Recommend]` to `[Recommend]`, and `[Praise]` is never carried - noted `_(carried from round <N>)_` (`<N>` = the prior report's own `round`) after the label line's label, its Location the right side of reconcile's cell when that cell extends the prior cite with ` -> <new path>:<line>` (reconcile's rename form), else the prior `file:line`, its prior annotations kept except a prior `_(carried from round ...)_`, which this note replaces. A row this round re-derives - this round's pass drafted a finding on the same construct - publishes once, as this round's finding. The table keeps prior labels and citations verbatim.

### Step 5 - Write Report

Standalone only. Use skill: `review-report-writer` with `report_type: review-security`, `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` from the handle, `base_sha` / `head_sha` from Step 4, `scope: +sec`, `depth` (default `standard`), `stack` (`<language>-<framework>` from `stack-detect`, versions dropped, lowercased, `#` written `sharp` and `+` written `p`, then each run of characters outside `[a-z0-9]` one `-`, leading and trailing `-` stripped (`python-fastapi`, `Vue (Nuxt)` on TypeScript -> `typescript-vue-nuxt`, `C#` / `Unity 6000.3.21f1` -> `csharp-unity`); a segment reported `unknown` dropped; `unknown` when both are), `mode: full`, `round` plus `prior_head_sha` from the round gate, and `pr_url` when the request carried a PR/MR URL, else `prior_checkpoint.pr_url` when present.

## Output Format

The fence delimits the template for display only; emit `report_body` as raw Markdown, never wrapped in a code fence. When Step 3 dispatched, the stack workflow owns the output.

Subagent runs return only `## OWASP Coverage` and `## Findings` with its severity sections and `out of lens` lines - no Summary, reconciliation, Next Steps, or file - and their Locations carry no verify annotation; the parent verifies and reconciles its merged set once.

Each finding block opens with its label line, `**[Must]**` or `**[Recommend]**`, before `Location`. A finding sits in the section of its **severity**; its label line and Next Steps entry carry its **published label** - a `**[Recommend]**` inside `### Critical` after verify de-escalated a pre-existing finding is correct. Empty severity sections are omitted, and within a section `[Must]` comes first, then by `file:line`; with none left, `## Findings` contains `No security issues found.` and Next Steps is omitted. Location is required; a multi-line construct cites its first line, and a two-site finding cites its first site and names the other after it. A standalone finding on a file absent from `git diff --name-status <base_ref>...<head_ref>` whose Annotation has no group opening `pre-existing` gets `_(pre-existing)_`, written first - the next round's reconcile reads it as provenance.

An `out of lens` line closes `## Findings` for each defect outside this lens that would break the build, or corrupt or expose data, naming its owner (`task-code-review` when no lens owns it); anything else outside the lens is left to `task-code-review`. These lines count in no Summary tally; `Overall Posture` counts every published finding, carried ones included.

Next Steps (standalone only): one entry per published finding, `[Must]` first, then by `file:line`. `[Implement]` when the fix is local to the change; `[Delegate]` with `[scope: <owner>]` when another owner (dependencies, platform, infra) must act. Either tag takes either label, and both keep the `file:line`.

Standalone runs emit the report body in chat, then the writer's confirmation line. When fallback ran standalone:

```markdown
## Security Review Summary

- **Stack Detected:** [the writer `stack` string] (generic fallback: no stack workflow | generic fallback: `<plugin>` plugin not installed)
- **Depth:** standard | deep
- **Overall Posture:** Clean | Issues Found - <C> Critical / <H> High / <M> Medium / <L> Low
- **Round:** [N]   {round 2+ only}
- **Findings verified:** [`review-finding-verify`'s Summary form: `<N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}`]

## OWASP Coverage

[One `- ` bullet per Top 10 category, in A01-A10 order: `- <Category>: No issues found | 1 finding | <N> findings`. Bullets, not bare lines - ten stacked `Label: value` lines collapse into one paragraph in the emitted report.]

## Findings

### Critical

**[Must | Recommend]**{ _(carried from round <N>)_}
- **Location:** [file:line]{ the verify Annotation groups, standalone only}
- **Issue:** [vulnerability]
- **Attack scenario:** [how an attacker exploits it]
- **Fix:** [specific remediation for the detected stack]

### High

[Same structure]

### Medium

[Same structure]

### Low

[Same structure]

- **out of lens:** file:line - [the defect in one sentence] - owner: [lens or `task-code-review`]   {one per such defect}

## Prior Round Reconciliation

[reconcile's output verbatim - table, any note lines, tally]   {round 2+ standalone runs only}

## Next Steps   {when at least one published finding}

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] file:line [scope: dependencies] - [one-line action]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (subagent runs: loaded, or rules inlined in the spawning prompt)
- [ ] Step 2: `stack-detect` ran (subagent runs: parent-supplied detection accepted instead)
- [ ] Step 3: exactly one announcement printed before any output; on dispatch the arguments were forwarded and Steps 4-5 skipped (skipped entirely on subagent runs)
- [ ] Step 4: precondition called with `argument` / `base` / `report_type`; SHAs captured and the round gate decided (head, base and depth compared) before the diff was read; every OWASP category in the coverage list, clean ones included; auth enforcement verified end-to-end; no credentials in code/config; every finding has an attack scenario and a rubric-based severity; qualifying `out of lens` lines emitted; findings published with verify's `file:line`, `Label`, `Annotation`; round 2+ prior findings projected, reconciled, and carried; precondition, SHA capture, gate, verify and reconcile skipped on subagent runs
- [ ] Step 5: report written via `review-report-writer` with all required inputs, or the round-gate stop line printed, or a precondition failure surfaced verbatim with no report written (standalone fallback only)

## Avoid

- Writing a report when invoked as a subagent - the parent owns it
- Chaining `round` / `prior_head_sha` off the general review's checkpoint instead of `review-security-<branch>.md` (`mode` is always `full`, never chained)
- Vulnerabilities reported without an attack scenario
- Silently skipping OWASP categories that look clean
- Recommendations that conflict with the framework's built-in security model
- Treating the fallback as equivalent to a stack workflow
- Emitting labels outside `[Must]` / `[Recommend]` in the findings sections (the reconciliation table preserves prior labels verbatim)
