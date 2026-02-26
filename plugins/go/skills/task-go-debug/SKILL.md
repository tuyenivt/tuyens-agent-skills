---
name: task-go-debug
description: "Debug Go errors. Paste a panic stack trace, error log, or describe unexpected behavior. Classifies error, identifies root cause, suggests fix."
agent: go-architect
---

STEP 1 — INTAKE: panic trace, error log, test failure

STEP 2 — CLASSIFY:

- panic: nil dereference → trace the nil
- context.DeadlineExceeded → timeout config
- sql: connection refused → DB connectivity, pool config
- sql: too many connections → SetMaxOpenConns
- data race (-race flag) → concurrent access, missing mutex
- goroutine leak (NumGoroutine growing) → context not cancelled
- Build error → module/import/type issue

STEP 3 — LOCATE: read stack trace, open source at goroutine creation point

STEP 4 — ROOT CAUSE: WHY, confidence level

STEP 5 — FIX: minimal before/after

STEP 6 — PREVENTION: test, vet check, race detector

- Prefer sync.WaitGroup.Go over manual Add/Done when possible
- Run go vet (especially waitgroup + hostport analyzers)
- For flaky async tests, replace time.Sleep with testing/synctest

OUTPUT: 🐛 → 📍 → 🔧 → 🛡️
