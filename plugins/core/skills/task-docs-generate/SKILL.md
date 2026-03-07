---
name: task-docs-generate
description: Documentation generation (README, API docs, code comments, runbooks) for any stack. Auto-detects project stack from CLAUDE.md and adapts documentation patterns to the detected ecosystem.
metadata:
  category: review
  tags: [documentation, readme, api-docs, multi-stack]
  type: workflow
user-invocable: true
---

# Documentation Generator

> For Architecture Decision Records, use `/task-adr-create` instead - it produces a complete, trade-off-documented ADR with alternatives analysis.

## When to Use

- README creation or improvement
- API endpoint documentation
- Code comments and inline doc generation
- Runbooks and operational guides
- Contributor setup guides

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Step 2 - Focus Areas

- **Audience**: Who is reading, what they need
- **Purpose**: What readers will accomplish
- **Examples**: Working, tested examples
- **Maintenance**: Can it be kept updated

### Step 3 - Documentation Debt Signals

Before writing documentation, assess the current state. Documentation debt is often the riskiest kind because it erodes team velocity silently.

| Signal                                        | Severity | Action                                      |
| --------------------------------------------- | -------- | ------------------------------------------- |
| README describes a setup that no longer works | High     | Fix first - new contributors are blocked    |
| API docs missing for public endpoints         | High     | Add before the next consumer onboards       |
| No runbook for on-call scenarios              | High     | On-call engineers debug blind               |
| Code comments describe _what_, not _why_      | Medium   | Rewrite to document intent and decisions    |
| Architecture docs don't match current design  | Medium   | Update or add ADR explaining the divergence |
| Changelog absent or stale                     | Medium   | Consumers can't evaluate upgrade risk       |
| No contributor setup guide                    | Low      | Slows onboarding; fix before next hire      |

Surface the top debt items before generating new documentation. Fixing stale docs is higher-value than adding new ones.

### Step 4 - Documentation Types

#### README

```markdown
# Project Name

Brief description.

## Quick Start

[Build and run commands for the detected stack's build tool]

## Prerequisites

[Runtime and tool requirements for the detected ecosystem]

## Installation

Step-by-step.

## Usage

Examples.

## Configuration

| Property | Description | Default |
```

#### API Docs

```markdown
# Endpoint Name

**Method:** GET/POST
**Path:** /api/v1/resource

## Request

| Param | Type | Required |

## Response

\`\`\`json
{ "id": 1 }
\`\`\`

## Errors

| Status | Description |
```

#### Runbook

A runbook is an operational procedure for an on-call engineer responding to an alert at 2am. Write for someone who knows the system exists but didn't build it.

```markdown
# Runbook: [Service or Operation Name]

## Purpose

[What this runbook covers and when to use it - be specific: "High error rate on /api/orders", not "Orders service issues"]

## Prerequisites

[Access, tools, and credentials required. Include where to get access if not obvious.]

## Symptoms

[What the alert or incident looks like. Log lines, metrics, error messages.]

## Steps

1. [Step with exact command or action - no ambiguous instructions]
2. [Step]

## Verification

[How to confirm the operation succeeded - specific metric, log line, or health check]

## Rollback

[How to undo if something goes wrong]

## Escalation

[Who to page if this runbook doesn't resolve the issue]
```

**Runbook quality bar:** An on-call engineer with no context on this service should be able to execute this runbook without asking anyone. If any step requires tribal knowledge, document that knowledge inline.

#### API Changelog

For public or consumed APIs, generate a changelog entry per version or release:

```markdown
## [v2.1.0] - [date]

### Added

- `GET /api/v2/users/{id}/preferences` - Returns user preference settings

### Changed

- `POST /api/v2/orders` - `address` field is now an object `{street, city, country}` instead of a string. Old string format accepted until [deprecation date].

### Deprecated

- `GET /api/v1/users` - Use `GET /api/v2/users` instead. v1 removed [date].

### Breaking Changes

- [None] or [explicit list - breaking changes require a version bump and migration guide]
```

#### Document the Why (Inline Architecture Comments)

Code comments should document decisions, not restate code. The "why" is what rots fastest and is hardest to reconstruct later.

**When to add inline architectural comments:**

- Non-obvious algorithm choices ("We use exponential backoff here because this endpoint rate-limits at 10 req/s under load")
- Intentional workarounds ("This null check exists because [external API] returns null instead of 404 for [edge case] - see issue #1234")
- Constraint explanations ("Cannot use async here - [library] requires synchronous access to its internal state")
- Historical context ("This was split from [OtherClass] in 2024 to resolve [problem] - do not re-merge without revisiting [concern]")

**When NOT to add comments:**

- When the code is self-explanatory (`// increment counter` above `count++`)
- When a better name would make the comment unnecessary
- When the comment just restates the type signature

### Step 6 - Stack-Specific Documentation Patterns

After loading stack-detect, apply documentation patterns appropriate to the detected ecosystem:

- **Code documentation**: Use the ecosystem's standard doc comment format (e.g., JavaDoc, YARD, GoDoc, docstrings, rustdoc, ExDoc)
- **Configuration reference**: Document the framework's configuration mechanism (properties files, YAML, environment variables, etc.)
- **Contributor setup**: Include test setup, container dependencies, and development environment instructions specific to the detected toolchain
- **Build and task documentation**: Document the project's build tool targets/tasks and common developer workflows

If the detected stack is unfamiliar, apply generic documentation templates and recommend the user consult their ecosystem's documentation conventions.

## Key Skills Reference

- Use skill: `api-guidelines` for API design, REST endpoint patterns, and documentation standards
- Use skill: `coding-standards` for code comment guidelines

## Principles

- Audience first
- Show, don't tell
- Simple words, short sentences
- Examples must work and be tested

## Rules

- Identify audience and purpose before writing
- Structure information clearly with progressive disclosure
- Provide working examples for every concept
- Keep documentation maintainable and close to the code
- For ADRs, redirect to `/task-adr-create`

## Checklist

- [ ] Audience is clear
- [ ] Purpose stated
- [ ] Examples work
- [ ] No jargon without explanation
- [ ] Can be maintained alongside code changes

## Success Criteria

A well-generated documentation output passes all of these. Use as a self-check before presenting.

### Completeness

- [ ] Audience and purpose are identified before any content is written
- [ ] Every code or command example is real and runnable - not invented or approximate
- [ ] Stack-detected toolchain is reflected in Quick Start commands and contributor setup
- [ ] For runbooks: Steps, Verification, and Rollback sections are all present

### Quality

- [ ] No marketing language or filler ("powerful", "seamlessly", "robust")
- [ ] No documentation of self-evident code - comments add meaning the code doesn't convey
- [ ] Jargon is either avoided or explained inline for the stated audience
- [ ] Documentation can be maintained alongside code - it doesn't duplicate what the code already expresses

### Staff-Level Signal (for tech lead review)

- [ ] A new team member could use the README to run the project locally without asking anyone
- [ ] API docs include error responses, not just the happy path
- [ ] Runbooks are actionable at 2am by an on-call engineer who didn't write the service - no tribal knowledge required
- [ ] Documentation debt signals are surfaced before new docs are written
- [ ] API changelog entries distinguish additive changes from breaking changes clearly
- [ ] Inline comments document decisions and constraints, not what the code does
- [ ] ADR requests are redirected to `/task-adr-create` - not handled here

## Avoid

- Documentation without seeing the code first
- Marketing language in technical docs
- Documenting obvious code (self-documenting is better)
- Stale examples that no longer work
- Applying documentation conventions from one stack to another
- Writing ADRs here - use `/task-adr-create` for decision records

## After This Skill

If the output needed significant adjustment - wrong doc type generated, examples were stale, or key sections were missing - run `/task-skill-feedback` to log what changed and why.
