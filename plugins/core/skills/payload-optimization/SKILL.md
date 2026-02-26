---
name: payload-optimization
description: API response size and serialization efficiency. Auto-detects project stack and adapts payload optimization to the detected ecosystem.
metadata:
  category: performance
  tags: [payload, api, serialization, compression, multi-stack]
user-invocable: false
---

# Payload Optimization

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Reducing bandwidth usage for high-traffic APIs
- Minimizing response times for large datasets
- Improving mobile and slow network performance

## Universal Principles (All Stacks)

- Return only required fields in responses
- Avoid deeply nested objects
- Avoid large lists without pagination
- Use projection queries to fetch only needed fields
- Use compression (gzip) when applicable
- Maintain stable response schema
- Avoid breaking changes in contracts
- Never expose ORM entities / model objects directly — always use response DTOs / serializers / structs

---

## Optimization Patterns

### Response Shaping

The universal pattern for avoiding over-fetching:

```
// Bad — returning the full entity/model with all fields
GET /orders/{id} → return entity directly (exposes all columns + internal fields)

// Good — returning only the fields the client needs
GET /orders/{id} → return shaped response with selected fields only
```

Principles:

- Use dedicated response objects separate from data layer entities
- Include only the fields the consumer needs
- Exclude internal fields (audit timestamps, soft-delete flags, internal IDs) unless explicitly needed

### Query-Level Projection

- Select only needed columns in database queries (not `SELECT *`)
- Load only required associations/relationships (avoid eager-loading everything)
- Use the ORM's projection capabilities to fetch partial records

### Serialization Control

- Exclude null or empty fields from JSON output when appropriate
- Use conditional serialization for fields that are only relevant in certain contexts
- Control field visibility per response context (list view vs detail view)

## Stack-Specific Guidance

After loading stack-detect, apply payload optimization using the idioms of the detected ecosystem:

- Use the framework's serialization mechanism for response shaping (DTOs/records, serializer classes, response structs with field tags, etc.)
- Use the ORM's projection or select API for query-level optimization
- Apply the framework's conditional serialization features (e.g., JSON views, serializer contexts, field exclusion tags)
- For eager-loading, use the ecosystem's standard approach to load only needed associations

If the detected stack is unfamiliar, apply the universal principles above and recommend the user consult their framework's serialization documentation.

---

## Avoid (All Stacks)

- Exposing ORM entities / model objects in API responses
- Deep nesting in response schemas
- Unpaginated collection endpoints
- Over-fetching from the database when only a subset of fields is needed
- Chatty APIs requiring multiple round-trips for data available in one query
