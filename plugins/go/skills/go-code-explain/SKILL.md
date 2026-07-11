---
name: go-code-explain
description: Go / Gin code explanation signals - goroutines, channels, context, defer, error wrapping, interfaces, GORM/sqlx semantics for task-code-explain.
metadata:
  category: backend
  tags: [explanation, code-understanding, go, gin, goroutines, context]
user-invocable: false
---

# Go Code Explain (atomic)

> Load `Use skill: stack-detect` first. Composed by `task-code-explain` when the stack is Go.

## When to Use

- A workflow needs Go-specific signals: goroutine ownership, channel direction, context propagation, defer ordering, error wrapping chains, interface satisfaction
- Target uses goroutines, channels, `context.Context`, Gin handlers, GORM, sqlx

## Rules

- Note whether the function takes `context.Context` first - context drives cancellation, deadlines, and request-scoped values across goroutine boundaries
- For each goroutine spawn, name what owns its lifetime (parent ctx, `done` channel, `WaitGroup`); unowned = leak
- Note channel direction (`chan<-`, `<-chan`, `chan`) and capacity (unbuffered vs buffered)
- Surface error wrapping (`%w`) and unwrap chains (`errors.Is/As`); bare `if err != nil { return err }` loses the call site
- Interface satisfaction is structural - read the methods, no `implements` keyword

## Signals to Surface

### Goroutines and Channels

| Construct                 | What to flag                                                                            |
| ------------------------- | --------------------------------------------------------------------------------------- |
| `go fn()`                 | No context propagation -> leak when request is cancelled                                |
| Unbuffered channel        | Send blocks until receive; deadlock if no rendezvous                                    |
| `select` no `default`     | All cases blocking deadlocks; needs `time.After` or `ctx.Done()` arm                    |
| `close(ch)`               | Close from sender only; double-close panics; receiver-close panics                      |
| `for range ch`            | Loops until close; if sender never closes, blocks forever                               |
| `sync.WaitGroup`          | `Add(1)` must precede `go fn()`, not inside the goroutine                               |
| `sync.Mutex`              | Missing `Unlock` (use `defer`); copying a struct with a mutex is a `go vet` error       |
| `sync/atomic`             | Mixing atomic and non-atomic on the same value is a race                                |
| `errgroup.Group`          | `Wait()` returns first error; `WithContext` cancels siblings on first failure           |
| `go func(){...}()` in loop | Pre-1.22 shares one loop variable (pass as arg); 1.22+ per-iteration - check the go.mod `go` directive |

### Context Propagation

- `WithCancel`/`WithTimeout`/`WithDeadline` - call `cancel()` (usually via `defer`) or leak the context tree
- `ctx.Done()` channel closes on cancel/deadline; use in `select` to abort
- `ctx.Value(key)` - key should be a private type (`type ctxKey struct{}`) to avoid collisions
- DB drivers, `http.Client`, Gin all support context
- Request ctx is cancelled when the handler returns. Work that must outlive the response needs `context.WithoutCancel(ctx)` (1.21+); `context.Background()` also detaches but drops request values/trace. Propagating the request ctx into a post-response goroutine cancels it immediately

### Defer

- Runs LIFO at function return
- Arguments evaluate at the `defer` statement, not at call time
- `defer rows.Close()` after `db.Query` is mandatory to avoid connection leaks
- `defer` inside a loop accumulates until function return

### Error Handling

- `fmt.Errorf("ctx: %w", err)` wraps; `errors.Is(err, target)` / `errors.As(err, &target)` traverse the chain
- `errors.New(...)` sentinels are comparable via `==` only when not wrapped
- Custom types implement `Error() string`; `errors.As` extracts
- `panic` for unrecoverable bugs; `recover` only inside `defer`

### Interfaces

- Structural typing: a type satisfies an interface by having the methods
- An interface holding `(*T)(nil)` is **not** equal to `nil` (type info present)
- Type assertion `v, ok := iface.(T)` and type switch `switch v := iface.(type)` are the safe forms

### Generics (1.18+)

- `func Map[T, U any](s []T, f func(T) U) []U`; constraints via `any` / `comparable` / interface
- Methods cannot introduce new type parameters

### Gin Specifics

- `c.JSON(200, obj)` serializes via `encoding/json`; `json:"..."` tags control field names
- `c.ShouldBindJSON(&obj)` parses body using struct tags + `binding:"required"`
- Middleware: `c.Next()` runs the next handler; omitting it stops the chain
- `c.Request.Context()` is the request's context - propagate to DB and downstream
- Goroutines that read the gin context must use `c.Copy()` - the original is invalid after handler returns

### GORM Specifics

- `db.Find(&users)` populates a slice; `db.First(&user)` errors with `gorm.ErrRecordNotFound`
- Soft delete: `gorm.DeletedAt` makes `Delete()` set `deleted_at`; queries auto-filter unless `Unscoped()`
- Hooks (`BeforeCreate`, etc.) fire inside the transaction
- **No lazy loading** - relations are zero-valued unless `Preload`ed
- `db.Transaction(func(tx) error {...})` commits on nil return, rolls back on error

### sqlx Specifics

- `db.Get(&user, "...")` single row; `db.Select(&users, "...")` slice
- `db:"column"` tags map columns
- `Get`/`GetContext` return `sql.ErrNoRows` on empty result - check with `errors.Is`
- Use `?` / `$1` placeholders - concatenation is SQL injection
- `defer tx.Rollback()` after `Begin` (no-op if committed)

### HTTP Client

- Default `http.Client` has no timeout - always set one
- `defer resp.Body.Close()` is mandatory
- Safe for concurrent use - create once, share

## Output

Inject signals into `task-code-explain` sections:

**Flow Context:**
- Whether the function takes `context.Context`
- Goroutine spawn points and ownership
- Channel directions and capacity
- Gin middleware chain order; DB transaction boundary

**Non-Obvious Behavior:**
- Goroutines outliving the request
- Unbuffered channel deadlocks
- Closing a channel from the wrong side
- `defer` arg evaluation at defer time
- Interface holding a typed nil != `nil`
- Loop-variable capture in goroutines (pre-1.22 vs 1.22+)
- GORM soft-delete auto-filter
- Default `http.Client` no timeout
- Gin context invalidation after handler return (need `c.Copy()`)

**Key Invariants:**
- Goroutines need an owner
- Only the sender closes channels
- `defer` is LIFO
- Rows / response bodies need `Close()`

**Change Impact Preview:**
- New `go fn()` without ctx propagation: leaks if request is cancelled
- `time.Sleep` in a goroutine without `select`-on-`ctx.Done()`: uncancellable
- `db.First` -> `db.Find`: error semantics change
- New GORM hook: fires on every save in the transaction
- Removing `defer rows.Close()`: connection leak under load

## Avoid

- Treating goroutines as fire-and-forget without explaining ownership
- Glossing over context cancellation
- Confusing buffered vs unbuffered channels
- Describing GORM as having lazy loading (it doesn't)
- "Go has no exceptions" without mentioning `panic`/`recover`
