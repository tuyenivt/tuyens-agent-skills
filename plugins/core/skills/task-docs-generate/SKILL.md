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

### Step 3 - Documentation Types

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

```markdown
# Runbook: [Service or Operation Name]

## Purpose

[What this runbook covers and when to use it]

## Prerequisites

[Access, tools, or context required]

## Steps

1. [Step with exact command or action]
2. [Step]

## Verification

[How to confirm the operation succeeded]

## Rollback

[How to undo if something goes wrong]
```

### Step 4 - Stack-Specific Documentation Patterns

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
- [ ] Runbooks are actionable at 2am by an on-call engineer who didn't write the service
- [ ] ADR requests are redirected to `/task-adr-create` - not handled here

## Avoid

- Documentation without seeing the code first
- Marketing language in technical docs
- Documenting obvious code (self-documenting is better)
- Stale examples that no longer work
- Applying documentation conventions from one stack to another
- Writing ADRs here - use `/task-adr-create` for decision records
