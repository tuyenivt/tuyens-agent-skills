---
name: task-go-debug
description: "Debug Go errors. Paste a panic stack trace, error log, or describe unexpected behavior. Classifies error, identifies root cause, suggests fix."
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

## Success Criteria

A well-executed debug session passes all of these. Use as a self-check before presenting the fix.

### Completeness

- [ ] Error is classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line
- [ ] A concrete before/after code fix is provided - no vague suggestions
- [ ] A prevention step is included (test, `go vet` check, or race detector guidance)

### Correctness

- [ ] The fix addresses the root cause, not the symptom
- [ ] Confidence level is stated - LOW confidence lists what additional info would help
- [ ] The fix is minimal - no unrelated refactoring
- [ ] Go idioms are preserved - errors wrapped with `%w`, no global state introduced

### Staff-Level Signal

- [ ] The "why" is explained - a developer understands how to avoid this class of bug
- [ ] For concurrency bugs, `go test -race` is referenced as the verification step
- [ ] For goroutine leaks, the fix includes the cancellation or completion path, not just the symptom fix

## After This Skill

If the output needed significant adjustment - root cause was wrong, Go idioms were violated in the fix, or a goroutine leak was missed - run `/task-skill-feedback` to log what changed and why.
