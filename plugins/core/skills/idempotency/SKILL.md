---
name: idempotency
description: Idempotency key pattern for safe retries. Auto-detects project stack and adapts idempotency implementation to the detected ecosystem.
metadata:
  category: integration
  tags: [idempotency, retries, integration, safety, multi-stack]
user-invocable: false
---

# Idempotency

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- POST operations with side effects
- Retryable operations in unreliable networks
- Event consumption and message processing

## Universal Principles (All Stacks)

- Idempotent operations must return same result on repeated calls
- Store idempotency state safely (database)
- Use idempotency keys to track processed requests
- Expire idempotency keys with appropriate TTL
- Support natural business keys when applicable
- Use deduplication table for at-most-once semantics

---

## Idempotency Pattern

The universal pattern for idempotency is the same across all stacks:

### Request-Level Idempotency

1. Client sends an `Idempotency-Key` header with a unique key
2. Server checks if the key has been processed before
3. If already processed: return cached response
4. If new: execute the operation, store the result keyed by the idempotency key, return result
5. Wrap the check and execution in a single transaction to prevent race conditions

### Implementation Principles

- Store idempotency records in the database with a unique constraint on the key
- Wrap both the idempotency check and the business operation in a single transaction
- Return the cached response for duplicate keys
- Set a TTL on idempotency records (e.g., 24-48 hours) to prevent unbounded growth
- Use database-level uniqueness (`INSERT ... ON CONFLICT` or equivalent) for atomicity

### Event/Message Idempotency

For message consumers and event handlers:

- Use a deduplication table keyed by message ID or natural business key
- Check-and-insert atomically within the processing transaction
- Consider consumer group semantics of the message broker

## Stack-Specific Guidance

After loading stack-detect, apply idempotency patterns using the idioms of the detected ecosystem:

- Use the framework's transaction management to wrap the idempotency check and business operation
- Use the ecosystem's standard approach for unique constraints and conflict handling
- For HTTP endpoints, implement as middleware or a reusable service that wraps the business logic
- For background job frameworks, leverage built-in deduplication if available, or implement at the application layer

If the detected stack is unfamiliar, apply the universal principles above and recommend the user consult their framework's transaction management documentation.

---

## Avoid (All Stacks)

- Relying on client retries without server-side protection
- Ignoring idempotency for POST operations
- Missing natural business keys where applicable
- Infinite idempotency key retention (use TTL)
- Idempotency check outside the transaction boundary (race condition)
