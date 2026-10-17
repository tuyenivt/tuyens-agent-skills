---
name: go-overengineering-review
description: Go necessity review - binding/service guards duplicating GORM/DB, defensive nil after non-nil constructors, single-impl interfaces at the impl.
metadata:
  category: backend
  tags: [go, gin, gorm, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

# Go Overengineering Review

> Load `Use skill: stack-detect` first. This skill reads `Framework`, `Database` and `ORM`: Category 1's GORM-specific checks (`gorm` tags, `TranslateError`) apply only when `ORM` is GORM - stack-detect leaves `ORM` empty for sqlx/pgx - while its binding and DB-constraint checks apply to any module; the driver is the `go.mod` require line (pgx v5 vs lib/pq). The framework guarantees it cites are Gin's (`binding:` tags validate on `ShouldBind*`; `gin.Recovery()` only when installed); under Echo there are no binding tags and no default recover, so a presence check or a `recover()` is not redundant "because the framework" - cite a different constraint or do not flag. Driver codes are PostgreSQL on pgx v5; lib/pq is `*pq.Error` with `Code pq.ErrorCode`, MySQL `*mysql.MySQLError` `Number` 1062 / 1452, SQLite enforces FKs only with `PRAGMA foreign_keys = ON`.

## When to Use

- Reviewing a Go diff that adds `binding:` / `validate:` tags, defensive nil checks, interfaces, or new abstractions
- Catching code that is correct, performant, and safe but does not need to exist

## Rules

- Every finding cites the constraint making the code redundant: FK name, `uniqueIndex`, `binding:` tag, framework guarantee, compile-time contract, or a repo fact (call sites, existing implementations, a mock file). When multiple constraints stack (e.g., binding + FK + "only HTTP write path"), list them comma-separated in `Redundant because:`
- **Label.** `[Recommend]` is the default. `[Must]` when the code costs something at runtime or actively misleads - an extra query per request, a silently swallowed error, a `recover()` or guard that reports success on failure, a process-killing `log.Fatal` on a request path, a naked `go fn()` with no owner - **or** when it is a premature abstraction whose maintenance cost is concrete: parallel definitions to keep in sync, an indirect call on every path, lost IDE jump-to-impl (a single-impl interface at the implementation, a `Result[T]` shadowing `(T, error)`, a pass-through layer). `Cost:` names that cost; a runtime cost that is also a security exposure (an fd leak on a user path) is named as both
- **Justification is repo-visible, not diff-visible.** A second implementation, a mock file, an Asynq or CLI call site, a worker pool, and an idempotency probe that returns the stored result on replay all live outside the hunks or are justified on their face. Check the repo before flagging; if you cannot, say which fact you could not verify and label `[Recommend]`, never `[Must]`. Confirmed justification is not a finding
- A redundancy outside the PR hunks that the hunks build on (the interface the new service wraps) is reported with `pre-existing` on the heading line, never silently skipped

## Patterns

### Category 1: Redundant Validation vs GORM / DB Constraints

Validation stack: **Gin `binding:` tag -> service guard -> GORM column tag -> DB schema**. `ShouldBindJSON` returns the validation error inside the handler, which writes the 400 before any service call; the DB is authoritative.

#### Manual presence check after `binding:"required"`

```go
// Bad - binding:"required,gt=0" already rejected CustomerID == 0
if err := c.ShouldBindJSON(&req); err != nil { ... }
if req.CustomerID == 0 {                      // dead
    c.JSON(400, gin.H{"error": "customer_id required"})
    return
}
```

#### Existence probe before a write the DB already constrains

`[Must]` - races (two concurrent requests pass the SELECT) and adds a query per write. The same shape appears against a unique index and against a foreign key; both are the constraint doing the work twice.

```go
// Bad
var existing User
if err := db.Where("email = ?", req.Email).First(&existing).Error; err == nil {
    return ErrEmailTaken
}
db.Create(&User{Email: req.Email})

// Good - let the constraint decide, map its error (pgx v5 shown; see the header for other drivers)
if err := db.Create(&User{Email: req.Email}).Error; err != nil {
    var pgErr *pgconn.PgError
    if errors.As(err, &pgErr) {
        switch pgErr.Code {
        case "23505": return ErrEmailTaken       // unique_violation
        case "23503": return ErrCustomerNotFound // foreign_key_violation
        }
    }
    return fmt.Errorf("create user: %w", err)
}
```

With `gorm.Config{TranslateError: true}` (GORM v1.25.1+ for the FK sentinel, with a dialector release that maps the FK code) the driver error is replaced by `gorm.ErrDuplicatedKey` / `gorm.ErrForeignKeyViolated` - match those with `errors.Is`; `errors.As(&pgErr)` never fires.

#### Service-layer presence guard duplicating binding + FK

```go
// Bad - binding:"gt=0" enforced presence on the only write path; the FK rejects an unknown customer
func (s *OrderService) Create(ctx context.Context, customerID, total int64) error {
    if customerID <= 0 { return errors.New("customer_id required") }   // dead
    return s.repo.Create(ctx, &Order{CustomerID: customerID, Total: total})
}
```

`gorm:"not null"` on a non-pointer `int64` never rejects `0` (GORM writes `0`, which is not NULL) - cite the binding tag or the FK, not the column tag. Justified when a non-HTTP write path (Asynq, cron, gRPC, a CLI) reaches the service without going through the binder.

### Category 2: Defensive Code for Impossible States

A guard on a dependency that wiring guarantees is `[Recommend]`; `[Must]` only when it reports success on failure or kills the process on a request path. `log.Fatal` at startup is fail-fast, not a finding.

#### Nil check on a non-nil-returning constructor

```go
// Bad - NewOrderService cannot return nil
svc := NewOrderService(repo)
if svc == nil { log.Fatal("nil service") }    // unreachable
```

`[Recommend]` when it sits in wiring code - unreachable, dead, not costly. `[Must]` when it sits on a request path and its branch would kill the process (`log.Fatal`, `os.Exit`): unreachable today, process-fatal the day a refactor makes it reachable, and it misleads every reader about what the constructor can return.

Legitimate when the constructor returns `(T, error)` and the caller hasn't checked the error.

#### Nil guard on a dependency the constructor never assigns

```go
// Bad - s.asynq is never set by NewOrderService, so this block is dead and the enqueue silently never happens
if s.asynq != nil {
    s.asynq.Enqueue(task)
}
```

`[Must]` - the guard hides a wiring bug as a feature. Either the dependency is required (constructor parameter, no guard) or the behaviour is optional by design (name the option).

#### `if err != nil { return nil }` silently swallowing

`[Must]`. Reports success on failure.

```go
// Bad
order, err := s.repo.Find(ctx, id)
if err != nil { return nil, nil }              // swallows error

// Good
if err != nil { return nil, fmt.Errorf("fulfill order %d: %w", id, err) }
```

#### `recover()` in business code

```go
// Bad - converts a programmer bug into a logged line and a nil error: the caller sees success
defer func() { if r := recover(); r != nil { log.Printf("panic: %v", r) } }()
```

`recover()` is legitimate in framework / middleware (`gin.Recovery()`, which exists only when installed with `gin.Default()` or `r.Use`). In business code let panics surface: `[Must]` when the recover logs and returns success, `[Recommend]` when it converts the panic into a returned error (redundant with the middleware, but not misleading).

### Category 3: Premature Abstraction

#### Single-impl interface at the implementation side

`[Must]` when the interface lives in the same package as its only implementer and no test mock exists. Idiom: interfaces belong to the consumer.

```go
// Bad - interface and only impl in repository; no test mock
package repository
type OrderRepository interface { Find(ctx context.Context, id int64) (*Order, error) }
type gormOrderRepository struct{ db *gorm.DB }

// Good - export the struct; consumer declares its interface
package repository
type OrderRepository struct{ db *gorm.DB }

package service
type orderRepo interface { Find(ctx context.Context, id int64) (*repository.Order, error) }
```

Justified when: a test mock lives next to the interface, 2+ concrete impls exist, or the interface is a documented public API.

#### `BaseRepository` embedded by one or two children

Inline until 3+ repositories share genuine cross-cutting behavior.

#### `Result[T]` over `(T, error)`

```go
// Bad - generic wrapper duplicating the idiomatic (T, error); every caller unpacks it by hand
func (s *OrderService) Find(ctx context.Context, id int64) Result[*Order] { ... }

// Good
func (s *OrderService) Find(ctx context.Context, id int64) (*Order, error) { ... }
```

#### Naked `go fn()` wrapping a sequential call

`[Must]` - no owner at shutdown, unbounded concurrency, the error is dropped, and a panic in the goroutine crashes the process (`gin.Recovery()` covers only the handler goroutine).

```go
// Bad
if err := s.repo.Save(ctx, order); err != nil { return err }
go s.notifier.Notify(ctx, order)               // fire-and-forget; the error return is lost

// Good - call directly, or dispatch to a tracked async system with a retry policy
if err := s.notifier.Notify(ctx, order); err != nil { return fmt.Errorf("notify: %w", err) }
```

Justified when dispatched to a tracked async system - a worker pool, Asynq, an outbox - with its own retry policy. An `errgroup` waited inside the request is synchronous fan-out, not async dispatch, and has no retry.

#### Pure pass-through layer

A type whose every method only forwards to one dependency. `Redundant because:` the consumer can hold the dependency directly - the layer adds an indirect call and a parallel API to keep in sync (`[Must]`, maintenance cost).

```go
// Bad - middleman: all 5 methods look like this
func (s *WarehouseService) GetByID(ctx context.Context, id int64) (*Item, error) {
    return s.repo.GetByID(ctx, id)
}
```

Justified when sibling methods on the same type carry real logic (API consistency), or the same PR introduces a cross-cutting concern (authz, tx boundary) into the layer.

#### Generic type with one instantiation

`Repo[T]` / `Service[T]` instantiated once or twice. `Redundant because:` single instantiation - inline the concrete type (bad/good pair in go-idioms). `[Must]` when it is embedded or adds an indirect call on every path (`BaseRepository[T]`), `[Recommend]` otherwise.

#### Speculative struct tags

Tags for a consumer the module never uses (`mapstructure:` with no viper; `db:` with no sqlx, pgx `RowToStructByName` or scany) - one finding per struct, listing the tags. Config keys nothing reads are Category 4.

#### Custom error type when a sentinel `var Err... = errors.New(...)` would do

Common AI-generated overspecification: every distinct error becomes its own struct type even when no caller inspects fields beyond identity. A package-level sentinel is shorter and matches via `errors.Is`.

```go
// Bad - struct type with no fields callers read; only matched by identity
type notFoundError struct{}
func (notFoundError) Error() string { return "not found" }
func NotFound() error { return notFoundError{} }

if _, ok := err.(notFoundError); ok { ... }

// Good - sentinel; matched via errors.Is
var ErrNotFound = errors.New("not found")
if errors.Is(err, ErrNotFound) { ... }
```

Justified when callers genuinely read fields off the error (`*ValidationError` carrying field names, `*ExternalError` carrying status code). The smell is field-less structs that exist only to be type-asserted.

### Category 4: Dead Code

Exported types, methods, request fields or config keys that nothing reads (`ListByOrder` with no caller, an `Attachments` field the handler never uses, a `staleError` never returned). `Redundant because:` no reader - name the grep that proved it; grep first, since background jobs and CLI commands often read indirectly. `[Recommend]`, unless the dead path also hides a defect (an unused field that opens files is both dead and a leak - cite the leak as `Cost:` and label `[Must]`).

## Output Format

Emit one block per finding, ordered `[Must]` first, then `[Recommend]`; within a label, in-hunk findings by file in the order the input listed them then line, then `pre-existing` blocks by path, then owned-by blocks; the consuming workflow merges them. Every finding carries exactly one label:

```
### [{Must | Recommend}] {file:line | file:start-end | file:<symbol>}{ pre-existing}

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction | Dead Code}
- Code: {one-line citation}
- Redundant because: {constraint(s) making the code dead; comma-separate when stacked}
- Cost: {required for [Must]; omit otherwise}
- Recommendation: {concrete edit}
- Justified when: {one-line note if legitimate reason might apply; otherwise omit}
```

`pre-existing` marks a finding outside the PR hunks that the hunks build on; Close with one line `Checked, not flagged: <abstractions whose justification the repo confirmed>` (or `none`). Cite `file:line` when the input carries line numbers, `file:<symbol>` when it does not; a range is `file:start-end`. One shape at several sites is one block citing the first site, with the rest named on the `Code:` line. For each category with zero findings, emit exactly: `No <category> findings.` (using the category name from the enum) so the workflow knows the check ran; omit the line for categories that have at least one finding. A defect this skill does not own (an aborting `BindJSON`, an unparameterised query, a missing transaction) is still reported, never dropped: one block per such defect, sorted per the order above, labelled by the criteria above, with its `Redundant because:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- Flagging `binding:` tags on Gin request structs (that layer owns 400 responses)
- Flagging interfaces declared at the consumer (idiomatic)
- Flagging `if err != nil { return err }` (idiomatic; the smell is `return nil` - silent swallow)
- Flagging `gorm:"not null;uniqueIndex"` (schema definition)
- Removing `recover()` in Gin middleware (legitimate use)
- Flagging `context.Context` first param
- Confusing "duplicated" with defense-in-depth across multiple write paths (HTTP + Asynq + cron + CLI)
- Flagging a goroutine that submits to a worker pool / Asynq / outbox (tracked dispatch, not naked)
- Citing a Gin guarantee (`Recovery()`, `binding:`) against an Echo or net/http module
