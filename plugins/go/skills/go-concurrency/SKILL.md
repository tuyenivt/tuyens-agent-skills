---
name: go-concurrency
description: "Go concurrency patterns: goroutine lifecycle, channels, context cancellation, errgroup, worker pools, sync primitives (including WaitGroup.Go), and common concurrency bugs."
user-invocable: false
---

Cover: goroutine lifecycle (owner + termination path), context cancellation,
errgroup for coordinated goroutines, worker pool pattern with code example,
channel ownership (sender closes), sync.Mutex (small critical sections),
sync.Once, sync.Pool, atomic package, sync.WaitGroup.Go for safer
goroutine launch accounting, go vet waitgroup analyzer, anti-patterns
(❌ goroutine without context, ❌ fire-and-forget goroutine, ❌ closing from receiver,
❌ defer in loop without function wrap)
