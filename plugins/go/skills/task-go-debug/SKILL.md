---
name: task-go-debug
description: Debug Go application errors - panics, context errors, SQL connectivity, data races, and goroutine leaks. Paste a stack trace or describe the unexpected behavior. Not for production incident analysis with blast radius assessment (use task-incident-root-cause for that).
agent: go-architect
metadata:
  category: backend
  tags: [go, gin, debug, troubleshooting, stack-trace, workflow]
  type: workflow
user-invocable: true
---

STEP 1 - INTAKE: panic trace, error log, test failure

STEP 2 - CLASSIFY:

- panic: nil dereference → trace the nil
- context.DeadlineExceeded → timeout config
- sql: connection refused → DB connectivity, pool config
- sql: too many connections → SetMaxOpenConns
- data race (-race flag) → concurrent access, missing mutex
- goroutine leak (NumGoroutine growing) → context not cancelled
- Build error → module/import/type issue
- Asynq task stuck in retry loop → load go-messaging-patterns, check idempotency and error classification
- Asynq worker not processing → Redis connectivity, queue name mismatch, handler not registered
- Kafka consumer lag growing → consumer group offset issue, handler error causing reprocess loop

STEP 3 - LOCATE: read stack trace, open source at goroutine creation point

STEP 4 - ROOT CAUSE: WHY, confidence level

STEP 5 - FIX: minimal before/after

STEP 6 - PREVENTION: test, vet check, race detector

- Prefer sync.WaitGroup.Go over manual Add/Done when possible
- Run go vet (especially waitgroup + hostport analyzers)
- For flaky async tests, replace time.Sleep with testing/synctest

OUTPUT: 🐛 → 📍 → 🔧 → 🛡️

## Self-Check

- [ ] Error classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal and addresses root cause, not symptom
- [ ] Go idioms preserved - errors wrapped with `%w`, no global state introduced
- [ ] Prevention step included (test, `go vet`, or race detector guidance)
- [ ] For concurrency bugs, `go test -race` referenced; for goroutine leaks, cancellation path included

> Run `/task-skill-feedback` if output needed significant correction.
