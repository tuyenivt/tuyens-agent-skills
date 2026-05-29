---
name: go-overengineering-review
description: Go necessity review - binding/service guards duplicating GORM/DB, defensive nil after non-nil constructors, single-impl interfaces at the impl.
metadata:
  category: backend
  tags: [go, gin, gorm, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Reviewing a Go diff that adds `binding:` / `validate:` tags, defensive nil checks, interfaces, or new abstractions
- Catching code that is correct, performant, and safe but does not need to exist

## Rules

- Every finding cites the constraint making the code redundant: FK name, `gorm:"not null"`, `uniqueIndex`, `binding:` tag, framework guarantee, compile-time contract
- Severity:
  - **`[Suggestion]`** (default). Cite the constraint, recommend the edit
  - **`[High]`** when measurable cost is present. Cite the cost in `Cost:`. Triggers: extra SELECT in a hot path; silent error swallow via `if err != nil { return nil }`; single-impl interface declared at the implementation; naked `go fn()` wrapping a sequential call
  - **`[Question]`** when justification is plausible but not visible in the diff
- A redundancy with **visible** justification is not a finding

## Patterns

### Category 1: Redundant Validation vs GORM / DB Constraints

Validation stack: **Gin `binding:` tag -> service guard -> GORM column tag -> DB schema**. Binding returns 400 before the handler runs; DB is authoritative.

#### Manual presence check after `binding:"required"`

```go
// Bad - binding:"required,gt=0" already rejected CustomerID == 0
if err := c.ShouldBindJSON(&req); err != nil { ... }
if req.CustomerID == 0 {                      // dead
    c.JSON(400, gin.H{"error": "customer_id required"})
    return
}
```

#### Manual unique-check before `db.Create`

`[High]` - races (two concurrent requests pass the SELECT) and adds a query per write.

```go
// Bad
var existing User
if err := db.Where("email = ?", req.Email).First(&existing).Error; err == nil {
    return ErrEmailTaken
}
db.Create(&User{Email: req.Email})

// Good - let the unique index decide
if err := db.Create(&User{Email: req.Email}).Error; err != nil {
    var pgErr *pgconn.PgError
    if errors.As(err, &pgErr) && pgErr.Code == "23505" { return ErrEmailTaken }
    return fmt.Errorf("create user: %w", err)
}
```

#### Service-layer presence guard duplicating binding + `gorm:"not null"`

```go
// Bad - column is gorm:"not null"; binding:"gt=0" enforced presence; no non-HTTP write path
func (s *OrderService) Create(ctx context.Context, customerID, total int64) error {
    if customerID <= 0 { return errors.New("customer_id required") }   // dead
    return s.repo.Create(ctx, &Order{CustomerID: customerID, Total: total})
}
```

Justified when a non-HTTP write path (Asynq, cron, gRPC) reaches the service without going through Gin.

### Category 2: Defensive Code for Impossible States

#### Nil check on a non-nil-returning constructor

```go
// Bad - NewOrderService cannot return nil
svc := NewOrderService(repo)
if svc == nil { log.Fatal("nil service") }    // unreachable
```

Legitimate when the constructor returns `(T, error)` and the caller hasn't checked the error.

#### `if err != nil { return nil }` silently swallowing

`[High]`. Reports success on failure.

```go
// Bad
order, err := s.repo.Find(ctx, id)
if err != nil { return nil, nil }              // swallows error

// Good
if err != nil { return nil, fmt.Errorf("fulfill order %d: %w", id, err) }
```

#### `recover()` in business code

```go
// Bad - swallows panics that should surface; Gin Recovery() already covers them
defer func() { if r := recover(); r != nil { err = fmt.Errorf("panic: %v", r) } }()
```

`recover()` is legitimate in framework / middleware. In business code, let panics surface.

### Category 3: Premature Abstraction

#### Single-impl interface at the implementation side

`[High]` when the interface lives in the same package as its only implementer and no test mock exists. Idiom: interfaces belong to the consumer.

```go
// Bad - interface and only impl in repository; no test mock
package repository
type OrderRepository interface { Find(ctx, id) (*Order, error) }
type gormOrderRepository struct{ db *gorm.DB }

// Good - export the struct; consumer declares its interface
package repository
type OrderRepository struct{ db *gorm.DB }

package service
type orderRepo interface { Find(ctx, id) (*Order, error) }
```

Justified when: a test mock lives next to the trait, 2+ concrete impls exist, or the trait is a documented public API.

#### `BaseRepository` embedded by one or two children

Inline until 3+ repositories share genuine cross-cutting behavior.

#### `Result[T]` over `(T, error)`

```go
// Bad - generic wrapper duplicating the idiomatic (T, error)
func (s *OrderService) Find(ctx, id) Result[*Order]

// Good
func (s *OrderService) Find(ctx, id) (*Order, error)
```

#### Naked `go fn()` wrapping a sequential call

`[High]` - goroutine leaks (no `WaitGroup` / `errgroup`), error swallowed.

```go
// Bad
if err := s.repo.Save(ctx, order); err != nil { return err }
go s.notifier.Notify(order)                    // fire-and-forget

// Good - call directly, or dispatch to Asynq / worker pool with retry
if err := s.notifier.Notify(ctx, order); err != nil { return fmt.Errorf("notify: %w", err) }
```

Justified when dispatched to a tracked async system (worker pool, Asynq, errgroup with retry).

#### Speculative struct tags / config keys

Flag `envconfig` keys declared but never read. Grep first - background jobs and CLI commands often read indirectly.

## Output Format

One block per finding; consuming workflow merges them:

```
### [Suggestion | High | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation}
- Redundant because: {constraint making the code dead}
- Cost: {required for [High]; omit otherwise}
- Recommendation: {concrete edit}
- Justified when: {one-line note if legitimate reason might apply; otherwise omit}
```

For each category with no findings, state `No <category> findings.` so the workflow knows the check ran.

## Avoid

- Flagging `binding:` tags on Gin request structs (that layer owns 400 responses)
- Flagging interfaces declared at the consumer (idiomatic)
- Flagging `if err != nil { return err }` (idiomatic; the smell is `return nil` - silent swallow)
- Flagging `gorm:"not null;uniqueIndex"` (schema definition)
- Removing `recover()` in Gin middleware (legitimate use)
- Flagging `context.Context` first param
- Confusing "duplicated" with defense-in-depth across multiple write paths (HTTP + Asynq + cron + CLI)
- Flagging a goroutine that submits to a worker pool / Asynq / errgroup (tracked dispatch, not naked)
