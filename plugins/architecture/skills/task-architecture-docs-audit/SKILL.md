---
name: task-architecture-docs-audit
description: Inventory all architecture artifacts (ADRs, design docs, runbooks, diagrams), detect stale content, conflicts between documents, and coverage gaps, then produce a prioritized remediation plan.
metadata:
  category: architecture
  tags: [architecture, documentation, audit, adr, consistency, docs-repo]
  type: workflow
user-invocable: true
---

# Architecture Docs Audit

## Purpose

Give architects a clear picture of what documentation exists, what is accurate, and what needs attention:

- **Inventory** - enumerate all architecture artifacts (ADRs, design docs, runbooks, diagrams)
- **Staleness detection** - identify documents that no longer reflect the current system
- **Conflict detection** - find contradictions between documents covering the same decision space
- **Gap detection** - identify what should exist but does not
- **Remediation plan** - prioritized list of actions ordered by impact

This skill reads documents. It does not modify any files.

## When to Use

- When joining a project and needing to assess the health of its architecture documentation
- Before a major architecture change to understand the current documented baseline
- Periodically (quarterly) as a documentation health check
- When conflicting information in docs is causing confusion or incorrect decisions
- After a significant system change to identify which docs have gone stale

## Inputs

| Input          | Required | Description                                                           |
| -------------- | -------- | --------------------------------------------------------------------- |
| Docs repo path | Yes      | Root path of the architecture docs repo (or subdirectory to scope)    |
| System context | No       | Brief description of the current system state to compare docs against |
| Focus area     | No       | Specific domain, service, or decision to prioritize in the audit      |
| Known issues   | No       | Docs or decisions already known to be stale or conflicting            |

## Workflow

### Step 1 - Discover Artifacts

Scan the docs repo and build an artifact inventory. Look for:

**ADRs** - files in `docs/adr/`, `adr/`, `docs/decisions/`, or any directory with sequentially numbered markdown files (e.g., `0001-*.md`)

**Design documents** - markdown files with titles containing: "design", "architecture", "proposal", "spec", "RFC", "system", "service"

**Runbooks** - markdown files in `runbooks/`, `ops/`, `playbooks/`, or with titles containing: "runbook", "playbook", "incident", "on-call"

**Diagrams** - `.png`, `.svg`, `.drawio`, `.puml`, `.d2` files, or markdown files containing Mermaid blocks

**Decision registers** - single files tracking multiple decisions (e.g., `DECISIONS.md`, `ARCHITECTURE.md`)

For each artifact found, record:

| Field  | What to Extract                                                        |
| ------ | ---------------------------------------------------------------------- |
| Path   | File path relative to repo root                                        |
| Type   | ADR / Design doc / Runbook / Diagram / Decision register / Other       |
| Title  | H1 heading or filename                                                 |
| Date   | Last modified date or date in frontmatter/content                      |
| Status | For ADRs: Proposed / Accepted / Deprecated / Superseded (from content) |
| Scope  | Which system/service/domain it covers (from content)                   |

### Step 2 - Build System Landscape

Use skill: `architecture-landscape` to extract a landscape from the docs content.

Read the design docs and ADRs to build a picture of:

- What systems exist according to the docs
- What technology decisions have been documented
- What integration points are described

This landscape becomes the reference against which staleness and conflicts are detected.

### Step 3 - Staleness Detection

If `System context` was provided as input, use it as the primary reference for staleness detection; use the landscape from Step 2 as secondary context only. If no system context was provided, staleness detection is limited to internal signals (date gaps, broken references, superseded status, version mismatches); flag this limitation in the output Summary.

For each artifact, assess staleness using these signals:

| Signal                       | Staleness Indicator                                                            |
| ---------------------------- | ------------------------------------------------------------------------------ |
| Date gap                     | Last updated >12 months ago for active systems                                 |
| Technology mismatch          | Doc mentions a tech that the landscape shows as replaced                       |
| Status not updated           | ADR status is "Proposed" but references decisions made >6 months ago           |
| Superseded reference missing | A newer ADR overrides this one but the old one isn't marked Superseded         |
| Broken internal references   | Doc links to another doc or system that no longer exists                       |
| Version mismatch             | Doc specifies a framework/library version that the landscape shows as upgraded |

Classify each artifact:

- **Current** - content reflects the known system state
- **Likely stale** - date or content signals suggest it may be outdated; needs human verification
- **Stale** - clear evidence it does not reflect current state
- **Unknown** - insufficient context to determine (note what information is missing)

### Step 4 - Conflict Detection

Use skill: `architecture-proposal-compare` when two or more documents cover the same decision space with differing conclusions.

Use the Recommendation field from `architecture-proposal-compare` to populate the 'More authoritative' and 'Recommendation' fields in the Conflicts section. The full comparison matrix is optional context; focus on the conflict resolution recommendation.

Scan for conflicts:

**Technology conflicts** - two docs specify different technologies for the same concern (e.g., one ADR says "use Kafka", a design doc says "use RabbitMQ" for the same event bus)

**Architecture conflicts** - two docs describe incompatible structural decisions (e.g., one doc shows Service A calling Service B directly; another shows an event-driven integration between them)

**Status conflicts** - an ADR marked Accepted contradicts a newer design doc without the ADR being marked Superseded

**Scope conflicts** - two docs claim data ownership or responsibility for the same domain entity

For each conflict found:

- State which documents conflict
- State specifically what they disagree on
- State which document appears more recent or authoritative
- Recommend: update the older doc, create a new ADR to resolve, or flag for human decision

### Step 5 - Gap Detection

Based on the landscape and artifact inventory, identify what is missing:

**Missing ADRs** - significant technology choices visible in the landscape with no corresponding ADR (e.g., a major database choice or framework with no decision record)

**Missing design docs** - systems or services in the landscape with no design documentation

**Missing runbooks** - services without operational runbooks, especially for on-call-relevant failure scenarios

**Missing diagrams** - systems described in text with no visual documentation

For each gap, assess priority:

- **Critical** - missing ADR or design doc for a major architectural change that has already happened (the system diverged from docs with no recorded rationale); or missing incident runbook for a frequently-paged service
- **High** - gap creates confusion or risk during incidents or onboarding
- **Medium** - gap reduces velocity but no immediate safety risk
- **Low** - nice to have; lower priority than fixing stale or conflicting docs

For minimal doc inventories (fewer than 5 artifacts), suppress Low-priority gap warnings to avoid overwhelming a nascent documentation culture. Focus on Critical and High gaps only.

### Step 6 - Produce Remediation Plan

Order all findings by impact. Group into three action categories:

**Effort estimation:** High = more than 5 Fix Now items or any critical runbook gap; Medium = 2-4 Fix Now items; Low = Fix Soon and Fix Eventually items only.

**Fix now** (staleness or conflicts causing active confusion or incorrect decisions)
**Fix soon** (stale docs or gaps that slow down onboarding or architecture work)
**Fix eventually** (low-priority gaps and polish)

When uncertain between Fix Now and Fix Soon, ask: would an on-call engineer or new team member make a wrong decision today because of this gap or conflict? If yes, Fix Now.

## Output

```markdown
# Architecture Docs Audit

Audited: {path}
Date: {today}
Artifacts found: {count} ({ADRs: N, Design docs: N, Runbooks: N, Diagrams: N, Other: N})

## System Landscape (from docs)

{Output from architecture-landscape atomic - systems, stacks, integrations}

## Artifact Inventory

| Path   | Type       | Title   | Date   | Status   | Scope    | Health       |
| ------ | ---------- | ------- | ------ | -------- | -------- | ------------ |
| {path} | ADR        | {title} | {date} | Accepted | {system} | Current      |
| {path} | Design doc | {title} | {date} | -        | {system} | Likely stale |
| {path} | Runbook    | {title} | {date} | -        | {system} | Stale        |

## Conflicts

### Conflict: {Short description}

- **Documents**: {doc A path} vs {doc B path}
- **What conflicts**: {specific disagreement}
- **More authoritative**: {which and why}
- **Recommendation**: {action}

[Repeat per conflict]

## Gaps

| Missing                  | Scope     | Priority | Rationale                                           |
| ------------------------ | --------- | -------- | --------------------------------------------------- |
| ADR for {decision}       | {system}  | High     | Major decision with no documented rationale         |
| Design doc for {service} | {service} | Medium   | Service has no architecture documentation           |
| Runbook for {scenario}   | {service} | High     | On-call engineers have no guidance for this failure |

## Remediation Plan

### Fix Now

- [ ] **Resolve conflict**: {doc A} vs {doc B} - {specific action}
- [ ] **Mark stale**: {path} - add deprecation notice and link to {newer doc}
- [ ] **Create runbook**: {scenario} for {service} - on-call risk

### Fix Soon

- [ ] **Create ADR**: Document the decision to use {technology} for {concern}
- [ ] **Update**: {path} - {what is outdated}

### Fix Eventually

- [ ] **Create design doc**: {service} - low onboarding friction now, grows with team

## Summary

- Total artifacts: {N}
- Current: {N} ({%})
- Likely stale: {N}
- Stale: {N}
- Conflicts: {N}
- High-priority gaps: {N}
- Estimated remediation effort: {Low / Medium / High}
```

## Rules

- Read files, do not modify them
- Never invent artifacts - only report what is found
- Staleness assessment must cite the specific signal, not just assert "this is old"
- Conflict detection must quote or specifically reference the conflicting claims
- Gap assessment must be grounded in the landscape - do not flag gaps for hypothetical systems
- If a docs repo is very large (>50 artifacts), ask the user to scope to a focus area

## Self-Check

- [ ] Artifact inventory covers all file types searched (ADR, design, runbook, diagram)
- [ ] Staleness classification cites a specific signal for each non-Current artifact
- [ ] Every conflict names both documents and the specific disagreement
- [ ] Gap recommendations are ordered by priority with rationale
- [ ] Remediation plan is actionable - each item specifies what to do, not just that a problem exists
- [ ] System landscape section includes System Inventory, Integration Map, and Cross-System Risks from `architecture-landscape` output
- [ ] Remediation plan is grouped into Fix Now / Fix Soon / Fix Eventually; Fix Now is populated when any Stale or Conflict finding exists

## Avoid

- Flagging every old document as stale - date alone is not sufficient; stable systems have stable docs
- Recommending deletion of any document - flag as stale and recommend archival or update
- Producing a list of problems without a remediation plan
- Treating missing documentation as uniformly bad - prioritize by operational and onboarding impact
- Generating new documentation content - this skill audits, it does not write
