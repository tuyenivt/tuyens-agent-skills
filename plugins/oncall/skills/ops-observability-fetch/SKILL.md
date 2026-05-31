---
name: ops-observability-fetch
description: Fetch oncall evidence (issues, metrics, logs, traces, deploys, monitors) via observability MCPs - Sentry/Datadog/Honeycomb/Grafana/etc. Normalizes output; falls back to paste-mode.
metadata:
  category: ops
  tags: [oncall, observability, evidence, mcp, sentry, datadog]
user-invocable: false
---

# Ops Observability Fetch

Transport-agnostic evidence gathering for oncall workflows. Detects available MCP servers, parses tool URLs, emits normalized evidence blocks. Falls back to paste prompts when no transport is available.

## Capabilities and URL Recognition

| Capability      | Inputs                                | URL pattern (auto-fetch trigger)                                                          |
| --------------- | ------------------------------------- | ----------------------------------------------------------------------------------------- |
| `fetch_issue`   | issue ID or URL                       | `*.sentry.io/.../issues/{id}` (numeric); short-IDs like `PROJ-123` need org+project slugs |
| `fetch_monitor` | monitor ID or URL                     | `app.datadoghq.*/monitors/{id}`                                                           |
| `fetch_trace`   | trace ID or URL                       | `app.datadoghq.*/apm/trace/{id}` (or vendor equivalent)                                   |
| `query_logs`    | service, window, filters / corr. ID   | `app.datadoghq.*/logs?query=...&from_ts=...&to_ts=...` (extract query + window)           |
| `query_metrics` | metric name(s), window, filters       | none (metrics require a named metric)                                                     |
| `list_deploys`  | service(s), window                    | none                                                                                      |

**Dashboard URLs** (`*/dashboard/*`) are never auto-fetched - they aggregate many tiles. Ask which metric/panel.

**Self-hosted variants** (`sentry.{company}.com`, `datadog.{company}.internal`) match on path, not host.

## Rules

- **Detect transport once per invocation; do not narrate the probe.** Cache the result silently.
- **URL recognition runs before asking for paste.** If input contains a recognized URL, auto-fetch.
- **Never invent values.** Unknown fields stay `unknown`; missing transport returns `Source: unavailable` with a paste prompt.
- **Source tag uses roles, not vendor names:** `mcp` (any MCP transport), `user-paste`, `unavailable`. Name the vendor in the block's `Tool:` line when relevant.
- **Emit only blocks the consumer asked for or the input directly anchors.** Do not pad with speculative blocks.
- **Output starts with the first block.** No preamble paragraph, no transport-status narration.
- **Window required** for `query_metrics`, `query_logs`, `list_deploys`. Other capabilities carry their own context.

## Transport Detection

Probe MCP tool namespaces by prefix and verb (`mcp__sentry__*`, `mcp__datadog__*`, `mcp__honeycomb__*`, etc.). Match capabilities to verbs (`get_issue`, `query_metrics`, `search_logs`, `get_monitor`, `get_trace`, `list_deployments`). If two transports expose the same capability, prefer the one named in the project's `CLAUDE.md` under `## Observability`; otherwise ask once.

## Fallback to Paste-Mode

When a capability is unavailable, emit the block with `Source: unavailable` and a paste prompt naming the tool and the diagnostic minimum fields the block requires. Keep it minimal - do not list every optional field.

## Output

Each block carries `Source:`, `Tool:` (when known), and only the fields the capability returned or the paste requires. Consumers parse by block type.

```
### error_event
Source: {mcp | user-paste | unavailable}
Tool: {sentry | rollbar | bugsnag | ...}
ID: {issue or event id}
Message: {short title}
Stack (top frame): {file:line - function}
Release: {tag}
Environment: {prod/staging/...}
First seen / Last seen: {ISO timestamps}
Event count: {N}
Affected users: {N}
Tags: {key=value, ...}

### metric_series
Source: ...
Tool: {datadog | grafana | newrelic | ...}
Metric: {name}
Window: {start} to {end}
Filters: {scope}
Points: {ts=value, ...} OR {p50=.., p99=.., max=..}
Baseline delta: {+N% vs prior 7d | no baseline}
Anomaly: {yes/no}

### log_window
Source: ...
Tool: {datadog | cloudwatch | loki | splunk | ...}
Service: {name}
Window: {start} to {end}
Filters: {query string}
Correlation IDs present: {yes/no/partial}
Lines: {count returned of total matched}
Sample: {timestamp level message, ...}

### deploy_event
Source: ...
Tool: {datadog | sentry-releases | gh-releases | ...}
Timestamp: {ISO}
Service: {name}
Commit: {sha}
Author: {name}
Environment: {prod/staging/...}

### monitor_state
Source: ...
Tool: {datadog | pagerduty | ...}
ID: {monitor id}
Name: {monitor name}
Status: {OK | Alert | Warn | No Data}
Threshold: {expression}
Current value: {value}
Last triggered: {ISO}

### trace
Source: ...
Tool: {datadog-apm | honeycomb | jaeger | ...}
Trace ID: {id}
Duration: {ms}
Services traversed: {a -> b -> c}
Error spans: {N, with service:operation list}
Slowest span: {service:operation, {ms}}
```

Omit fields the capability did not return. For unavailable blocks, keep only the fields the paste prompt needs.

## Avoid

- Narrating the transport probe or listing every MCP namespace checked
- Emitting blocks the user did not request and the input does not anchor
- Auto-fetching dashboard URLs without a named metric
- Filling unknown fields with plausible-looking values
- Re-probing transport between capability calls in the same invocation
