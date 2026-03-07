---
name: task-oncall-handoff
description: Generate a structured on-call handoff - incident summary, open alerts, known flaky areas, and context the incoming engineer needs to start effectively. Run at the end of an on-call shift.
metadata:
  category: ops
  tags: [oncall, handoff, incident, reliability, ops]
  type: workflow
user-invocable: true
---

# On-Call Handoff

## Purpose

Structured on-call handoff that transfers critical context from the outgoing to the incoming engineer:

- **Incident summary** -- what happened this shift, current status, and any unresolved tails
- **Open alerts and known issues** -- what the incoming engineer will see immediately
- **Known flaky areas** -- recent instability patterns that may recur
- **Deferred work** -- investigations or mitigations started but not completed
- **Context to start effectively** -- what the incoming engineer must know to be effective from minute one

This skill produces a handoff document. It does not investigate incidents (use `/task-incident-root-cause` for that) or write postmortems (use `/task-incident-postmortem` for that).

## When to Use

- At the end of an on-call shift (daily, weekly, or per-rotation handoff)
- After a significant incident to ensure the resolution is fully handed off
- When handing off mid-shift due to escalation, PTO, or geographic rotation
- As part of sprint retrospective input when on-call burden is being reviewed

## Inputs

| Input              | Required | Description                                                     |
| ------------------ | -------- | --------------------------------------------------------------- |
| Shift period       | Yes      | Start and end time of the handoff window                        |
| Incidents          | No       | List of incidents that occurred - titles, severity, status      |
| Open alerts        | No       | Alerts currently firing or recently resolved                    |
| Known issues       | No       | Ongoing instability, flaky components, or workarounds in effect |
| Deferred work      | No       | Investigations or mitigations started but not completed         |
| Slack/ticket links | No       | Links to incident channels, tickets, or runbooks for reference  |

Handle partial inputs gracefully. When incident data is sparse, produce a template the outgoing engineer can fill in, with prompts for each required section.

## Rules

- Every incident from the shift must appear in the summary with current status
- Open alerts must distinguish between known-and-expected and unexpected
- Known flaky areas must include the workaround if one exists
- Deferred work must be specific enough that the incoming engineer can pick it up
- Do not write a postmortem in the handoff - that is a separate document
- Omit empty sections in output

## Handoff Model

### Step 1 - Shift Overview

Summarize the shift at a high level:

- Shift period and systems in scope
- Overall stability rating: Quiet / Elevated / Incident / Major Incident
- Number of pages or alerts received
- Number of incidents opened

### Step 2 - Incident Summary

For each incident during the shift:

| Field          | Content                                                                  |
| -------------- | ------------------------------------------------------------------------ |
| Title          | Short description of the incident                                        |
| Severity       | SEV1 / SEV2 / SEV3 (or equivalent team classification)                   |
| Timeline       | When it started, when it was detected, when it was resolved (if at all)  |
| Root cause     | Brief description if known; "under investigation" if not                 |
| Current status | Resolved / Monitoring / Open / Deferred to postmortem                    |
| Tail items     | Any work remaining - e.g., "RCA in progress", "mitigation not permanent" |
| References     | Links to incident ticket, Slack thread, runbook used                     |

If root cause is unknown or unconfirmed, state that explicitly.

Use skill: `failure-classification` to categorize incident types for pattern recognition across shifts.

### Step 3 - Open Alerts and Known Issues

List all currently firing alerts and known issues:

For each open alert:

- Alert name and system
- Whether it is known-and-expected (expected state, no action needed) or unexpected (requires attention)
- Any active workaround or mitigation
- Escalation criteria (when to page someone)

For each known issue:

- What is broken or degraded
- Current workaround in effect
- Owner or team responsible for the permanent fix
- ETA for resolution (if known)

### Step 4 - Flaky Areas and Recurrence Risk

Identify areas that showed instability during the shift and may recur:

| Area                | What Happened       | Recurrence Risk | Mitigation                   |
| ------------------- | ------------------- | --------------- | ---------------------------- |
| {service/component} | {brief description} | Low/Medium/High | {workaround or watch signal} |

Include:

- Services or jobs that had elevated error rates even without a full incident
- Recurring alerts that fired multiple times during the shift
- Flaky tests or deployments that caused repeated alerts

### Step 5 - Deferred Work

List investigations or mitigations started but not completed:

For each deferred item:

- What was started and how far it got
- What the incoming engineer needs to know to continue
- Priority (continue immediately / pick up after current incidents stabilize / low priority)
- Relevant links (tickets, Slack threads, notes)

### Step 6 - Incoming Engineer Briefing

Surface the three to five most important things the incoming engineer must know immediately:

- What is the current system state? Stable / degraded / recovering?
- Are there any time-sensitive items (deployments scheduled, migrations running, rollbacks in progress)?
- What is the highest-risk area to watch in the next few hours?
- Are there any escalation paths or contacts the incoming engineer should know about?
- Any unusual context this shift (traffic spike, dependency outage, external event)?

## Output

```markdown
# On-Call Handoff

**Shift:** {start datetime} to {end datetime}
**Outgoing:** {name or team}
**Incoming:** {name or team}
**Overall Rating:** {Quiet | Elevated | Incident | Major Incident}

---

## Shift Overview

- Pages / alerts received: {count}
- Incidents opened: {count}
- Incidents resolved: {count}
- Incidents still open: {count}

---

## Incidents This Shift

### {Incident Title} - {Severity} - {Resolved | Open | Monitoring}

- **Timeline**: Started {time} | Detected {time} | Resolved {time or "ongoing"}
- **Root cause**: {brief description or "under investigation"}
- **Impact**: {what users or systems were affected}
- **Tail items**: {remaining work - RCA, permanent fix, monitoring period}
- **References**: {links to ticket, Slack, runbook}

[Repeat per incident]

---

## Open Alerts

| Alert        | System    | Status             | Action Needed                                             |
| ------------ | --------- | ------------------ | --------------------------------------------------------- |
| {Alert name} | {Service} | Known / Unexpected | None (expected noise) / Watch for X / Page if Y           |

---

## Known Issues and Workarounds

| Issue         | System    | Workaround   | Owner  | ETA                 |
| ------------- | --------- | ------------ | ------ | ------------------- |
| {description} | {service} | {what to do} | {team} | {date or "unknown"} |

---

## Flaky Areas - Watch List

| Area      | Pattern         | Recurrence Risk   | Mitigation                   |
| --------- | --------------- | ----------------- | ---------------------------- |
| {service} | {what happened} | {Low/Medium/High} | {watch signal or workaround} |

---

## Deferred Work

### {Item Name}

- **Status**: {how far investigation got}
- **Priority**: {Continue immediately | After current incidents stabilize | Low}
- **Context**: {what the incoming engineer needs to know to continue}
- **References**: {links}

---

## Briefing for Incoming Engineer

1. **Current system state**: {Stable | Degraded | Recovering} - {one sentence context}
2. **Highest-risk area to watch**: {component or service and why}
3. **Time-sensitive items**: {any scheduled deployments, migrations, or rollbacks in progress}
4. **Key contacts**: {who to escalate to for specific systems if needed}
5. **Unusual context**: {anything non-standard about current conditions}

---

## Quick Reference

- On-call runbook: {link or "see team wiki"}
- Incident channel: {Slack channel or link}
- Escalation contact: {name or rotation}
```

### Output Constraints

- Every incident must appear with current status - none silently omitted
- Open alerts must distinguish known-expected from unexpected
- Deferred work must be specific enough to hand off without a conversation
- Briefing section must be at the end - incoming engineer reads it first
- Do not write postmortem content - reference the incident ticket instead

## Success Criteria

A well-executed handoff passes all of these.

### Completeness

- [ ] Every incident from the shift listed with status
- [ ] All currently firing alerts categorized (known vs unexpected)
- [ ] All known workarounds documented
- [ ] All deferred work has enough context to hand off
- [ ] Briefing section covers the most time-sensitive context

### Handoff Quality

- [ ] Incoming engineer can start immediately without needing to ask the outgoing engineer questions
- [ ] It is clear which open items require immediate action vs monitoring
- [ ] Flaky areas give a watch signal, not just a description of what happened

### Ops Utility

- [ ] Handoff can be posted to Slack or wiki without editing
- [ ] Incident pattern recognition is possible across multiple handoffs
- [ ] On-call burden is visible (number of pages, severity distribution)

## Avoid

- Writing postmortem content in the handoff (use `/task-incident-postmortem` for that)
- Vague deferred work ("investigate the memory issue") without enough context to hand off
- Omitting resolved incidents - the incoming engineer needs the full picture
- Skipping known-and-expected alert classification (causes alarm fatigue)
- Long narrative prose - tables and bullets are faster to scan during an active incident

## Key Skills Reference

- Use skill: `failure-classification` for incident type categorization and pattern recognition

## After This Skill

If the output needed significant adjustment - incidents were missed, the briefing was unclear, or deferred work was not specific enough - run `/task-skill-feedback` to log what changed and why.
