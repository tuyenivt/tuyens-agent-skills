---
name: go-code-explain
description: Go / Gin code explanation signals: goroutines, channels, context, defer, error wrapping, interface satisfaction, struct tags, GORM/sqlx.
metadata:
  category: backend
  tags: [explanation, code-understanding, go, gin, goroutines, context]
user-invocable: false
---

# Go Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is Go.

## When to Use

- A workflow needs Go-specific signals: goroutine ownership, channel direction, context propagation and cancellation, defer ordering, error wrapping chains, interface satisfaction by structural typing.
- Target uses goroutines, channels, `context.Context`, Gin handlers, GORM queries, or `sqlx` queries.

## Rules

- Identify whether the function takes a `context.Context` first - context drives cancellation, deadlines, and request-scoped values across goroutine boundaries.
- For each goroutine spawned, name what owns its lifetime (parent context cancellation, explicit `done` channel, `sync.WaitGroup`) - unowned goroutines are leaks.
- Identify channel direction (`chan<-`, `<-chan`, `chan`) and capacity (unbuffered vs buffered) - these change blocking semantics.
- Surface error wrapping (`fmt.Errorf("...: %w", err)`) and unwrap chains (`errors.Is`, `errors.As`) - bare `if err != nil { return err }` loses the call site.
- Identify interface satisfaction by reading the methods, not by an `implements` keyword - structural typing means the satisfaction is implicit.

## Patterns

### Goroutines and Channels

| Construct                            | Behavior                                                                                          | What to flag                                                                                                                                |
| ------------------------------------ | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `go fn()`                            | Spawns a goroutine; no return value visible to caller                                              | Without context propagation, the goroutine outlives the request - leak                                                                       |
| Unbuffered channel                   | Send blocks until receive; receive blocks until send                                              | Common deadlock source - sender and receiver must rendezvous                                                                                 |
| Buffered channel                     | Send blocks when buffer full; receive blocks when empty                                            | Capacity matters; a buffer of 1 is **not** the same as a queue                                                                               |
| `select { case ... }`                | Multiplexes channel ops; `default` makes it non-blocking                                          | Without `default`, all cases blocking causes deadlock; `time.After` or `ctx.Done()` cases prevent it                                         |
| `close(ch)`                          | Subsequent receives return zero value + `ok=false`                                                | Closing a channel from the receiver side or twice panics; only the sender should close                                                       |
| `for range ch`                       | Iterates until channel is closed                                                                  | If sender never closes, the loop blocks forever                                                                                              |
| `sync.WaitGroup`                     | Counts active goroutines; `Wait()` blocks until counter is zero                                    | `wg.Add(1)` must be called **before** `go fn()`, not inside the goroutine                                                                    |
| `sync.Mutex` / `sync.RWMutex`        | Mutual exclusion                                                                                  | Forgetting `Unlock` (especially without `defer`) causes deadlocks; copying a struct that contains a mutex is a `go vet` error                |
| `sync/atomic`                        | Lock-free primitives                                                                              | Mixing atomic and non-atomic access on the same value is a data race                                                                         |

### Context Propagation

- `ctx, cancel := context.WithCancel(parent)` - call `cancel()` (usually via `defer cancel()`) or leak the context tree.
- `ctx, cancel := context.WithTimeout(parent, 5*time.Second)` - similar; cancel even if timeout fires (idempotent).
- `ctx.Done()` returns a channel that closes when context is cancelled or deadline expires; use in `select` to abort work.
- `ctx.Value(key)` for request-scoped values; key should be a private type to avoid collisions: `type ctxKey struct{}`.
- DB drivers, HTTP clients, and Gin all support context. Passing `context.Background()` (or `context.TODO()`) to a handler-spawned goroutine breaks request cancellation.

### Defer Ordering

- `defer` calls run in **LIFO** order at function return.
- `defer` evaluates its arguments at the defer statement, not at call time:
  ```go
  i := 0
  defer fmt.Println(i)  // prints 0
  i = 5
  ```
- `defer rows.Close()` after `db.Query(...)` - common pattern; missing this leaks DB connections.
- `defer` inside a loop accumulates - if the loop runs 1000 times, 1000 deferred calls fire at function return. Move work into a helper or use explicit cleanup.

### Error Handling

- `if err != nil { return err }` is idiomatic but loses the call site context.
- `fmt.Errorf("doing X: %w", err)` wraps; `errors.Is(err, target)` and `errors.As(err, &target)` traverse the chain.
- `errors.New("...")` for sentinel errors; comparable with `==` only if not wrapped.
- Custom error types: implement `Error() string`. `errors.As` extracts when the chain contains the type.
- `panic` is for unrecoverable bugs; `recover` only inside `defer`. Web frameworks usually have a panic-recovery middleware.

### Interfaces (Structural Typing)

- A type satisfies an interface if it has all the required methods - no `implements` declaration.
- Empty interface `interface{}` (or `any` in Go 1.18+) accepts any value.
- Interface variables are pointer-to-data + type info; checking `if v == nil` on an interface holding a `(*T)(nil)` returns `false` because the type info is not nil.
- Type assertion `v, ok := iface.(ConcreteType)` - safe form.
- Type switch `switch v := iface.(type) { case ConcreteType: ... }` - branching on concrete type.

### Generics (Go 1.18+)

- `func Map[T, U any](s []T, f func(T) U) []U`: type parameter `T any` is unconstrained; constrained via interface types or `comparable`.
- Type parameters cannot be used in method receivers' type sets (no `func (m Map[T]) Foo() {}` with new type params on the method).

### Gin Specifics

- `c.JSON(200, obj)`: serializes `obj` via `encoding/json`; struct tags `json:"name"` control field names.
- `c.Bind(&obj)` / `c.BindJSON(&obj)`: parses request body using struct tags + `binding:"required"` for validation.
- Middleware: `func(c *gin.Context) { ...; c.Next() }`. `c.Next()` runs the next handler; without it, the chain stops.
- `c.Set("key", val)` and `c.Get("key")` for context-scoped data within the request.
- `c.Request.Context()` is the request's context.Context - propagate this to DB calls and downstream HTTP.
- Goroutines spawned from a handler should use a copy: `cCp := c.Copy()` - the original is invalidated after the handler returns.

### GORM Specifics

- `db.Find(&users)` populates a slice; `db.First(&user)` populates a single record (errors with `gorm.ErrRecordNotFound` if no rows).
- Soft delete: `gorm.DeletedAt` column makes `Delete()` set `deleted_at` instead of issuing DELETE; queries auto-filter unless `Unscoped()`.
- Hooks: `BeforeCreate`, `AfterUpdate`, etc., are methods on the model; fire inside the transaction.
- Associations with `Preload("Posts")` for eager loading; without it, lazy loading **does not exist** in GORM - relations are zero-valued.
- Transactions: `db.Transaction(func(tx *gorm.DB) error { ... })` - return error rolls back; nil commits.

### sqlx Specifics

- `db.Get(&user, "SELECT ...")` for single row; `db.Select(&users, "SELECT ...")` for slice.
- Struct tags `db:"column_name"` map columns to fields.
- Always use `?` (or `$1` for Postgres) parameter placeholders - string concatenation is SQL injection.
- `tx.Commit()` / `tx.Rollback()`: forgetting either is a connection leak; use `defer tx.Rollback()` after `Begin` (no-op if already committed).

### HTTP Client Specifics

- Default `http.Client` has no timeout - **always** set one or set `Transport` with timeouts.
- `defer resp.Body.Close()` after `http.Get` - missing leaks connections in the connection pool.
- `http.Client` is safe for concurrent use; create once and share.

## Output Format

This atomic produces signals consumed by `task-code-explain`. Inject the following:

**Into "Flow Context":**

- Whether the function takes `context.Context`
- Goroutine spawn points and what owns each lifetime
- Channel directions and capacity
- For Gin: middleware chain order
- For DB: transaction boundary

**Into "Non-Obvious Behavior":**

- Goroutines outliving the request (no context cancellation)
- Unbuffered channel deadlocks
- Closing a channel from the wrong side or twice
- `defer` arguments evaluated at defer time, not call time
- Interface holding a typed nil not equaling `nil`
- GORM soft delete auto-filtering queries
- Default `http.Client` having no timeout
- Gin context invalidation after handler return (need `c.Copy()`)

**Into "Key Invariants":**

- Goroutines need a lifetime owner (context, channel, WaitGroup)
- Only the sender should close a channel
- `defer` fires in LIFO order at function return
- DB rows / HTTP response body must be `Close()`d

**Into "Change Impact Preview":**

- Spawning a new goroutine without context propagation: leaks if request is cancelled
- Adding a `time.Sleep` inside a goroutine without `select`-on-`ctx.Done()`: cannot be cancelled
- Switching from `db.First` to `db.Find`: error semantics change (`ErrRecordNotFound` no longer raised)
- Adding a GORM hook: fires on every save in the transaction
- Removing a `defer rows.Close()`: connection leak under load

## Avoid

- Treating goroutines as cheap fire-and-forget without explaining lifetime ownership
- Glossing over context cancellation - it is the primary cancellation mechanism
- Confusing buffered and unbuffered channels - they have completely different blocking semantics
- Recommending `time.After` in long-running selects without explaining its allocation cost (per call)
- Describing GORM as having lazy loading - it doesn't, relations are zero unless `Preload`ed
- Saying "Go has no exceptions" without explaining `panic`/`recover` and where they actually appear
