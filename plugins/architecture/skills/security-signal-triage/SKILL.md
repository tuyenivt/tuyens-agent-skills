---
name: security-signal-triage
description: Investigate a security signal or attack indicator: confirm it, map affected resources, success vs attempt, containment ladder by owner.
metadata:
  category: ops
  tags: [security, signal, attack, oncall, datadog, containment]
user-invocable: false
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Security Signal Triage

Decides whether an attack had an effect, what it reached, whether it is still happening, and which lever stops it - without touching the signal itself.

## When to Use

- A security signal from App and API Protection (AAP), Cloud SIEM, or a WAF: injection payloads, credential stuffing, scanner sweeps, token abuse, privilege probing
- A suspicious access pattern with no signal: one actor reading many accounts, a login succeeding after a burst of failures
- Not for vulnerability remediation, dependency CVEs, or compliance review

## Inputs

Required: a signal URL, ID, or pasted signal, or for a suspicious access pattern the monitor or log evidence that shows it. Optional: the actor (IP, user, token), the targeted service or endpoint, a trace ID. Evidence already in the input counts - fetch only what is missing.

## Rules

- Confirm before any rung above 1: scanner noise - sweeps answered 404 or blocked - is the common case, and a revoke or disable on noise is harm this skill caused
- The signal is read-only: never archive, mute, re-rate, or assign it. A tuning - a detection-rule threshold, a suppression, or an AAP passlist entry (formerly exclusion filter) - is named as an action only on a scanner-noise verdict, and never loosens a rule that matched a real payload, blocked or in monitoring mode
- Every rung emitted names the owner of its lever from the Step 4 ladder and an ETA in minutes; a lever the code path shows broken is named as broken in the item; only rungs whose When holds are emitted
- Preserve before a session or token purge (rung 3): it deletes the rows that show what the actor held - snapshot them, and export the actor's log window by IP and by touched account from 60 min before first seen; rotation and disable delete nothing
- Escalation floor, stated so nothing below it is argued case by case: succeeded access to a revenue or auth path, any data read or export by the actor, a valid credential in the actor's hands, code execution or SSRF reaching an internal host, or an Exploit Prevention detection (a rule naming exploitation), blocked or not, escalates to the security owner now; other blocked attempts and scanner noise never do
- A check that only an unreachable system would answer is `Not run`, never skipped silently; a row the signal type cannot have (auth on an unauthenticated sweep, qualification on a non-AAP signal) is `n/a`

## Patterns

### Step 1 - Evidence

Use skill: `ops-observability-fetch`: `security_signal` per signal URL or ID; `log_window` for the actor from 60 min before the signal's first event to now, on the targeted service and on the service that authenticates its callers; `trace` when a trace ID is held; `deploy_event` for the targeted service when the endpoint is new or recently changed, since a fresh route is the usual hole. A paste that carries statuses, auth outcomes, or an executed statement is that evidence (`Source: user-paste`), not `Not run`. Synthesize into the Evidence bullets with sources named.

### Step 2 - Effect

`Access succeeded` is decided by effect evidence alone. Services often run AAP in monitoring mode, so an unblocked 2xx is the normal answer to an attack the application handled safely: it proves nothing either way.

| Row                   | Effect shown (`yes`)                                                                                                       | No effect (`no`)                                                                                                                                  |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Qualification and rule | `Qualification: harmful`, or a `Rule` naming exploitation, on a request not marked blocked                                 | `Qualification: safe`                                                                                                                             |
| Blocking and status   | -                                                                                                                          | every request either marked blocked (`Outcome: blocked`; AAP's block response is configurable, so the mark decides, not the status) or answered 401 or 403 by the auth layer, 302 to login, 404 on a nonexistent path, or 429 |
| Auth outcome          | a login success for the actor's IP or token after a burst of failures                                                      | failures only                                                                                                                                     |
| Payload reach         | the payload in an executed statement or outbound URL (a log line, a pasted statement), or data the payload asked for in the response, or another account's data returned to the actor | -                                                                                                                                                 |

`yes` on any effect row. `no` when no row shows effect and one anchor that fits the attack holds: every request blocked or rejected (Blocking row), failures only on a login attack (Auth row), or `Qualification: safe` (AAP rated every trace None successful). `unknown` otherwise - a `-` cell or an unknown qualification never blocks `no`. A blocked Exploit Prevention hit shows no effect but proves the route vulnerable: it is the hole in Step 3 and an escalation trigger. An edge WAF block leaves no trace on the targeted service (the AWS WAF integration surfaces it under service `aws.waf`).

Volume decides nothing about effect; it separates **targeted** (sustained against one account or endpoint, many times that account's or endpoint's baseline, from one actor or many) from **sweep** (everything else - typically one pass across many paths by a scanner).

```
Bad:  SQL injection signal from 203.0.113.9 -> Confirmed - uncontained; rotate the DB credentials
Good: SQL injection signal from 203.0.113.9; every request marked blocked, one-pass sweep across 380 paths
      -> False positive / scanner noise; containment: existing block holds; tune: suppress notifications for the sweep pattern - detection-rule owner; escalation: Not met - no effect shown
```

### Step 3 - Resources and Verdict

- Source actor: IP, user, or token from the signal and logs; ASN or geography when the signal or paste gives it
- Targets: endpoints and hosts from the signal; the handler behind each route and the tables or data classes it reads or writes, from the code path when the repo is readable; a route the code path or an Exploit Prevention hit shows exploitable is the hole, named whether or not the actor reached it
- Accounts: every account the actor authenticated to or read, from the auth and access logs in the window; "none" when no auth succeeded
- Data: what those accounts and handlers expose - the data class, not a row count, unless the logs give one
- Time window: first to last event across the signal and logs; `continuing` when the latest event - the actor's, or the signal's pattern on the targeted endpoint when the actor is unknown - falls in the last 5 minutes of the latest window held (that window's end, not the current time, is the reference) - an activity flag, independent of the verdict, and what Step 4 means by attempts still arriving (with Time window `unknown`, they count as arriving)

Verdict, the only statement of it:

- `Confirmed - uncontained` - `yes`, and no lever stops the actor yet; silence alone is not containment
- `Confirmed - contained` - `yes`, and a lever now stops the actor
- `Attempted - blocked` - `no`, and targeted or carrying an Exploit Prevention detection; the label covers an attempt blocked, rejected, or handled safely, and the Containment record says which
- `False positive / scanner noise` - `no`, not targeted, and no Exploit Prevention detection
- `Insufficient evidence` - `unknown` after every applicable row ran or was `Not run`, with what would settle it in Remaining Uncertainty

### Step 4 - Containment Ladder

Ordered by blast radius on legitimate users; take the lowest rung that stops the harm shown, then every rung the harm already reached requires. Rung 1 needs no confirmation; every other rung needs a `Confirmed` verdict. AAP levers reach the service only through Remote Configuration; without it, block at the edge.

| Rung | Lever                                                                                                                                                                                          | Owner                                | When                                                                                                                                    |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | Rate limit the actor, or the endpoint when the actor is unknown                                                                                                                                                                           | edge or platform                     | attempts still arriving on any verdict above noise, `Insufficient evidence` included                                                |
| 2    | Block the source: IP/CIDR or authenticated user in the AAP Denylist, user agent via an In-App WAF custom rule, ASN or token fingerprint at the edge; or switch the service's AAP policy from monitoring to blocking | SRE or platform                      | confirmed and the actor not yet blocked                                                                                                 |
| 3    | Revoke tokens and sessions for the touched accounts and force their credential reset, through the session store and token library the code path shows                                         | application                          | an auth success for the actor                                                                                                           |
| 4    | Rotate the secrets the actor could have read                                                                                                                                                   | application, plus the secret's owner | a config, key, or credential among the exposed data                                                                                     |
| 5    | Disable the targeted route or feature, or the touched accounts                                                                                                                                 | application or product               | a hole usable by any caller who can reach the route, authenticated users included, or abuse rungs 1-3 did not stop; the fix itself is the owning engineer's |

On `Attempted - blocked` and scanner noise no rung above 1 is emitted, and Containment records what already stops the attempt: `existing block holds` when the Blocking row anchors `no` and at least one request was marked blocked, otherwise `no effect - <why>` (a rejection or safe handling), ` - nothing further` appended when the record is the only Containment item. Rung 1 sits beside that record on `Attempted - blocked` while attempts still arrive; noise adds the tuning item (notification-side, the block untouched) with its owner. `Insufficient evidence` with nothing arriving records `nothing further - <what would settle it>`.

### Step 5 - Escalation

Apply the floor from Rules. The line carries the trigger met - a met trigger decides whatever else is unknown - or the floor not crossed; `Unknown` when no trigger is met and the deciding evidence is `Not run`, or Access succeeded is `unknown` on a path the floor names, with what would settle it.

## Output Format

```markdown
## Security Signal Triage: {one-line description}

Verdict: {Confirmed - uncontained | Confirmed - contained | Attempted - blocked | False positive / scanner noise | Insufficient evidence}

Access succeeded: {yes | no | unknown} - {the effect row that decides it, or what would}

Source actor: {ip(s), user, or token; ASN or geography when given | unknown}

Affected resources: {endpoints, accounts, and data classes reached or targeted | none reached - no effect shown}{; hole: <route>, fix with <owner>}

Time window: {first to last event{, continuing} | unknown - <what would establish it>}

### Evidence
- {observation with source - signal field, log line, trace, code path}
- {each check that could not be run: "Not run - <what was inaccessible>"; a row the signal type cannot have: "n/a - <row>"}

### Containment
- [ ] {lever{ (broken: <why> - use <alternative>)} - owner - ETA in minutes | existing block holds{ - nothing further} | no effect - <why>{ - nothing further} | nothing further - <what would settle it> | tune: <threshold, suppression, or passlist entry> - <owner>}

### Evidence Preserved
- [ ] {capture to perform before rung 3 - session or token rows snapshotted, actor log window exported by IP and by account | nothing to preserve - rung 3 not recommended}

### Escalation
{Escalate to the security owner now - <trigger met> | Not met - <floor not crossed> | Unknown - <what would decide>}

### Remaining Uncertainty
- {every Not run check and every inference the evidence could not settle, each with what would resolve it; or "None - investigation conclusive"}
```

## Self-Check

- [ ] behavioral-principles loaded; Step 1: signal fetched, actor logs pulled to now on both services, pasted, or marked Not run
- [ ] Step 2: every row read, marked Not run, or n/a; Access succeeded set from effect rows only; targeted or sweep decided
- [ ] Step 3: actor, targets, accounts, data classes, hole, and Time window set; Verdict follows the Access succeeded value
- [ ] Step 4: only triggered rungs emitted, each with lever, owner, and ETA in minutes; rungs above 1 only on a Confirmed verdict; capture item ahead of rung 3
- [ ] Step 5: Escalation line states the trigger met or the floor not crossed
- [ ] Every Not run check reaches Remaining Uncertainty

## Avoid

- Setting Access succeeded from an unblocked 2xx, a DB service in `Services traversed`, or the rule's own severity
