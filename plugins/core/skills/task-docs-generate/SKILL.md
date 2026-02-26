---
name: task-docs-generate
description: Documentation generation (README, API docs, ADRs) for any stack. Auto-detects project stack from CLAUDE.md and adapts documentation patterns to the detected ecosystem.
metadata:
  category: review
  tags: [documentation, readme, api-docs, adr, multi-stack]
  type: workflow
---

# Documentation Generator

## When to Use

- Documentation creation (README, API docs, ADR)
- Documentation review and improvement
- Code comments and doc generation
- Runbooks and guides

## Workflow

### Step 1 — Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Step 2 — Focus Areas

- **Audience**: Who is reading, what they need
- **Purpose**: What readers will accomplish
- **Examples**: Working, tested examples
- **Maintenance**: Can it be kept updated

### Step 3 — Documentation Types

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

#### ADR

```markdown
# ADR-NNN: Title

## Status

Proposed | Accepted | Deprecated

## Context

What is the issue?

## Decision

What did we decide?

## Consequences

Positive and negative results.
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

### Step 4 — Stack-Specific Documentation Patterns

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

## Checklist

- [ ] Audience is clear
- [ ] Purpose stated
- [ ] Examples work
- [ ] No jargon without explanation
- [ ] Can be maintained alongside code changes

## Avoid

- Documentation without seeing the code first
- Marketing language in technical docs
- Documenting obvious code (self-documenting is better)
- Stale examples that no longer work
- Applying documentation conventions from one stack to another
