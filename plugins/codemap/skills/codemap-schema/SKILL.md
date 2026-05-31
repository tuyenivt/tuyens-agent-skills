---
name: codemap-schema
description: Canonical codemap graph schema - 12 node types, 14 edge types, 6 layer enum, JSON shapes. Loaded by every task-codemap-* workflow.
metadata:
  category: core
  tags: [codemap, schema, knowledge-graph, contract]
user-invocable: false
---

# Codemap Schema

Single source of truth for `.codemap/graph.json` and its sibling artifacts. Every codemap workflow loads this before producing or consuming graph data.

## When to Use

- Producing graph data in `task-codemap` (full build or sync).
- Reading graph data in `task-codemap-ask`, `task-codemap-guide`, `task-codemap-explain`.
- Validating an existing graph (via `codemap-validate`).

## Rules

1. **IDs are stable and globally unique.** Same logical entity yields the same ID across rebuilds. No line numbers in IDs - they shift on every refactor.
2. **Every node has a one-sentence English `summary`.** Describe intent, not signature. If genuinely unknown, write `unknown - <reason>`.
3. **Closed enums.** `type`, `complexity`, `layer` use only the listed values. Extending the schema means editing this skill, not improvising locally.
4. **No dangling edges.** Edges referencing missing endpoints are dropped at merge.
5. **English only.** `summary`, `tags`, `name` are English regardless of source language.

## Patterns

### Top-level shape

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-05-30T12:00:00Z",
  "gitCommitHash": "abc1234",
  "rootPath": ".",
  "stack": { "language": "Go", "framework": "Gin", "stackType": "backend" },
  "nodes": [ ... ],
  "edges": [ ... ],
  "layers": [ ... ]
}
```

### Node schema

```json
{
  "id": "function:src/auth/login.ts:authenticate",
  "type": "function",
  "name": "authenticate",
  "filePath": "src/auth/login.ts",
  "lineRange": [42, 87],
  "summary": "Validates credentials, issues a JWT, and writes an audit log entry.",
  "tags": ["auth", "jwt", "audit"],
  "complexity": "moderate",
  "layer": "service"
}
```

| Field | Required for | Notes |
| --- | --- | --- |
| `id` | all | Format `<type>:<path>[:<name>]`. Stable across rebuilds. |
| `type` | all | One of the 12 node types. |
| `name` | all | Symbol for code; basename for files; short label for abstract nodes. |
| `filePath` | code, config, document | Repo-relative, forward slashes. Omit for `concept`/`service`/`schema`. |
| `lineRange` | `function`, `class`, `endpoint` | `[start, end]`, 1-based, inclusive. |
| `summary` | all | One English sentence. |
| `tags` | all | 1-5 short kebab-case tags. |
| `complexity` | code nodes | `simple` / `moderate` / `complex`. |
| `layer` | assigned in layer phase | One of the 6 layer values. Omit when no clear layer. |

### Node type enum (12)

| Type | Example |
| --- | --- |
| `file` | `src/auth/login.ts` |
| `function` | `authenticate()` (free function or method) |
| `class` | `UserRepository` (class, struct, interface, trait) |
| `module` | `auth/` (package, namespace, folder cluster) |
| `concept` | `JWT`, `Idempotency Key` (no single source location) |
| `config` | `application.yml`, `next.config.ts` |
| `document` | `README.md`, `ARCHITECTURE.md` |
| `service` | `Stripe API`, `Notification Service` (external/internal deployed) |
| `endpoint` | `POST /login` (HTTP route, gRPC method, GraphQL resolver, CLI cmd) |
| `table` | `users`, `audit_logs` (DB table or collection) |
| `schema` | `UserDTO` (OpenAPI, JSON schema, protobuf message) |
| `resource` | `email-queue` (queue, topic, bucket, cron) |

### Edge schema

```json
{ "source": "<id>", "target": "<id>", "type": "calls", "weight": 0.7 }
```

`weight` is optional `0.0-1.0` (defaults to `1.0`). `source` and `target` must reference existing nodes.

### Edge type enum (14)

| Type | Meaning |
| --- | --- |
| `imports` | Source imports/requires target |
| `exports` | Source declares target as its public surface |
| `calls` | Function source invokes function target |
| `extends` | Class source extends class/interface target |
| `implements` | Class source implements interface target |
| `uses` | Generic dependency without tighter category (DI, instantiation, type reference) |
| `depends_on` | Module/service-level dependency |
| `reads_from` | Source reads data target (table, schema, config) |
| `writes_to` | Source writes data target |
| `tested_by` | Source code/function is tested by target |
| `documents` | Document target describes source |
| `configures` | Config source configures target |
| `routes_to` | Endpoint source routes to handler target |
| `belongs_to` | Source is owned by container target (function -> file, file -> module) |

### Layer enum (6)

| Layer | Meaning |
| --- | --- |
| `entry` | Bootstrap, CLI, server start, route registration |
| `api` | HTTP/gRPC/GraphQL surface - controllers, handlers, routers |
| `service` | Use-cases, application services, orchestration |
| `domain` | Pure domain model, entities, value objects, invariants |
| `data` | Repositories, ORM, DAOs, raw queries, migrations |
| `infra` | External integrations, queues, observability, config loading |

Nodes with no clear layer (docs, generated code) omit the field.

### Guides shape (`.codemap/guides.json`)

```json
{
  "schemaVersion": 1,
  "guides": [
    {
      "name": "request-lifecycle",
      "title": "Request lifecycle: login -> JWT",
      "depth": "basic",
      "steps": [
        { "order": 1, "nodeId": "endpoint:POST /login", "narration": "..." }
      ]
    }
  ]
}
```

`depth`: `basic` (5-8 steps) or `full` (10-20 steps). Every `nodeId` must exist in `graph.json`.

### Meta shape (`.codemap/meta.json`)

```json
{
  "schemaVersion": 1,
  "builtAt": "2026-05-30T12:00:00Z",
  "gitCommitHash": "abc1234",
  "analyzedFiles": 412,
  "version": "0.1.0"
}
```

### Config shape (`.codemap/config.json`)

```json
{ "schemaVersion": 1, "autoUpdate": false, "scope": null }
```

`scope: null` means full repo; otherwise a relative subdirectory path.

## Output Format

No artifact. When referencing a node in any output, backtick-wrap the full ID (e.g., ``function:src/auth/login.ts:authenticate``) so users can grep.

## Avoid

- Inventing types or edges outside the enums - extend this skill instead.
- Embedding source code in `summary` - intent only.
- Line numbers in `id` - they break stability.
- Free-form fields not listed in the schema.
