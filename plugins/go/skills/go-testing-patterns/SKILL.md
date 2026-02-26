---
name: go-testing-patterns
description: "Go testing: table-driven tests, httptest for Gin handlers, testcontainers-go for integration, testify (assert/require), interface mocking, t.Parallel, benchmarks, and testing/synctest."
user-invocable: false
---

Cover with code examples: table-driven test pattern, httptest + gin.CreateTestContext
for handler tests, testcontainers-go for PostgreSQL, testify assert vs require,
mocking via interfaces (define in consumer, mock in test), t.Parallel for
independent tests, t.Cleanup for teardown, TestMain for suite setup,
benchmarks, testing/synctest for deterministic concurrency tests, anti-patterns
(❌ no t.Parallel, ❌ testing private funcs, ❌ mocking DB instead of testcontainers,
❌ time.Sleep for async assertions)
