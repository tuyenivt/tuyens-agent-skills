---
name: go-gin-patterns
description: "Gin web framework patterns: routing groups, middleware, request binding with validation, consistent JSON responses, pagination, graceful shutdown, health endpoints."
user-invocable: false
---

Cover: routing groups (/api/v1), custom middleware, ShouldBindJSON/ShouldBindQuery,
go-playground/validator tags, consistent response envelope {data, error, meta},
pagination (page/size → LIMIT/OFFSET), graceful shutdown (signal handling),
health endpoints (/health, /ready), anti-patterns (❌ business logic in handlers,
❌ c.JSON in services, ❌ global gin.Default, ❌ host:port string concatenation instead of net.JoinHostPort)
