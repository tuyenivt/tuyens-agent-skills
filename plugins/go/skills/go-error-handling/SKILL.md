---
name: go-error-handling
description: "Go error patterns: explicit returns, wrapping with %w, sentinel errors, custom error types, errors.Is/As, Gin error middleware. Never swallow errors."
user-invocable: false
---

Cover: always check errors (never \_), wrap with fmt.Errorf("context: %w", err),
sentinel errors (var ErrNotFound), custom error types (ValidationError),
errors.Is/As for checking, error chain (repo→service→handler mapping to HTTP),
Gin error middleware (c.Error + centralized handler), panic vs error
(panic only for programmer bugs), anti-patterns (❌ swallowing, ❌ log+return,
❌ string matching, ❌ panic for flow control)
