---
name: go-idioms
description: "Go language idioms: iota enums, struct tags, functional options, generics, type-safe IDs, embedding, defer rules, Stringer/Marshaler, go:embed."
metadata:
  category: backend
  tags: [go, idioms, generics, options, iota, embedding, defer, struct-tags]
user-invocable: false
---

# Go Idioms

> Load `Use skill: stack-detect` first. Error idioms live in `go-error-handling`; concurrency idioms in `go-concurrency`. This skill owns language-level shape decisions for writing new code.

## When to Use

- Implementing a new package, type, or constructor and deciding which Go idiom fits
- Reviewing whether code reads as Go vs Java/Python translated into Go
- Choosing between generics, interface, and concrete impl; between `type` alias and new type; between embedding and composition

## Rules

- `iota` for enum-like state groups; pair with a `String()` method (stringer-generated) so logs are readable
- Functional options (`WithTimeout(d)`-style) for constructors with > 2 optional knobs; positional struct config for the rest
- Generics where they collapse repetitive type-switched code; never to abstract a single concrete type
- New type (`type UserID int64`) over `type` alias when the boundary matters (compile-time prevents passing `OrderID` where `UserID` is expected)
- Embedding for forwarding (`io.Reader` into a wrapper), not for inheritance; if you wanted overrides, use composition + method dispatch
- Implement `String()`, `MarshalJSON`, `UnmarshalJSON`, `Value`/`Scan` (`database/sql`) for types that cross boundaries (logs, JSON, DB)
- `go:embed` for SQL migrations, templates, static assets - ship them in the binary
- Exported identifiers have a doc comment starting with the identifier name; unexported only when non-obvious

## Patterns

### `iota` enums + Stringer

```go
type OrderStatus int

const (
    StatusPending OrderStatus = iota
    StatusPaid
    StatusShipped
    StatusCancelled
)

//go:generate stringer -type=OrderStatus
// stringer generates: func (i OrderStatus) String() string { ... }
```

For bit flags, `1 << iota`:

```go
type Perm uint
const (
    PermRead Perm = 1 << iota
    PermWrite
    PermAdmin
)
```

DB / JSON crossing: implement `Value()` and `Scan()` so the enum survives the boundary:

```go
func (s OrderStatus) Value() (driver.Value, error) { return s.String(), nil }
func (s *OrderStatus) Scan(v any) error            { /* parse string -> enum */ }
```

### Struct tag conventions

One struct often carries tags for multiple consumers - keep the order consistent so they scan top-to-bottom:

```go
type User struct {
    ID        int64  `json:"id"          gorm:"primaryKey"             db:"id"`
    Email     string `json:"email"       gorm:"uniqueIndex;not null"   db:"email"     validate:"required,email"`
    Password  string `json:"-"           gorm:"not null"               db:"password"`
    CreatedAt time.Time `json:"created_at" gorm:"autoCreateTime"     db:"created_at"`
}
```

- `json:"-"` to drop a field from JSON (passwords, internal IDs)
- `json:",omitempty"` only when the zero value is semantically "absent" (often surprising for `int`)
- `mapstructure:"..."` only when the field is read from `viper` / `envconfig`; do not use `mapstructure.Decode(req.Body, &domain)` (see `go-security-patterns`)

### Functional options

```go
type Server struct {
    addr     string
    timeout  time.Duration
    logger   *slog.Logger
}

type Option func(*Server)

func WithTimeout(d time.Duration) Option { return func(s *Server) { s.timeout = d } }
func WithLogger(l *slog.Logger) Option   { return func(s *Server) { s.logger = l } }

func New(addr string, opts ...Option) *Server {
    s := &Server{addr: addr, timeout: 30 * time.Second, logger: slog.Default()}
    for _, opt := range opts { opt(s) }
    return s
}

srv := New(":8080", WithTimeout(5*time.Second), WithLogger(customLog))
```

Use when there are more than 2-3 optional parameters and defaults make sense. For 1-2 knobs, a `Config` struct is simpler.

### Generics: when they help

Generics earn their keep when they collapse code that was previously written via `interface{}` + type switch:

```go
// Bad - generics for a single concrete type (no callers benefit)
type Repo[T any] struct{ db *gorm.DB }
func (r *Repo[T]) Find(id int64) (*T, error) { ... }
// only ever instantiated as Repo[Order]

// Good - generic helper used across many types
func MapSlice[T, U any](in []T, f func(T) U) []U {
    out := make([]U, len(in))
    for i, v := range in { out[i] = f(v) }
    return out
}
ids := MapSlice(users, func(u User) int64 { return u.ID })
```

Constraints worth knowing: `comparable` for map keys / equality, `~T` (underlying type) for "any type whose underlying is T":

```go
type Ordered interface { ~int | ~int64 | ~float64 | ~string }
func Max[T Ordered](a, b T) T { if a > b { return a }; return b }
```

If your generic function calls a method, define an interface constraint instead - generics aren't a substitute for interfaces.

### Type-safe IDs

```go
// Bad - any int64 can be passed; mixing OrderID and UserID compiles
func Charge(orderID, userID int64) error
Charge(userID, orderID) // silently wrong

// Good - new types catch the swap at compile time
type OrderID int64
type UserID  int64
func Charge(orderID OrderID, userID UserID) error
```

`type UserID = int64` (with `=`) is an **alias**, identical to `int64` - no safety. Drop the `=` to create a new type.

### Embedding vs composition

Embedding forwards methods of the embedded type to the outer:

```go
type LoggingDB struct {
    *gorm.DB // forwards Find, Create, ... to outer
}

func (l *LoggingDB) Find(out any, where ...any) *gorm.DB {
    start := time.Now()
    res := l.DB.Find(out, where...)
    slog.Info("db.find", "dur", time.Since(start))
    return res
}
```

Embedding is **forwarding**, not inheritance - there is no virtual dispatch. If you wanted to override behavior seen by an embedded method calling a sibling method, use composition (hold the dependency as a field) instead.

### `defer` rules

Arguments to a deferred call evaluate **at the defer statement**, but the call runs at function return:

```go
i := 1
defer fmt.Println("deferred:", i) // prints "deferred: 1"
i = 2
```

`for { defer x }` is a common bug - defers accumulate until the enclosing **function** returns, not the loop iteration:

```go
// Bad - file handles leak until DoWork returns
func DoWork(paths []string) {
    for _, p := range paths {
        f, _ := os.Open(p)
        defer f.Close() // all stay open until DoWork returns
        process(f)
    }
}

// Good - wrap each iteration so defer scopes to the inner func
for _, p := range paths {
    func() {
        f, _ := os.Open(p)
        defer f.Close()
        process(f)
    }()
}
```

LIFO order: last `defer` runs first.

### Stringer / Marshaler / Unmarshaler

When a type crosses a boundary (log, JSON, DB), implement the interface the consumer uses - it's the only way to control rendering at the call site:

| Boundary | Interface |
|----------|-----------|
| `fmt.Println` / `slog` (via `%v`) | `String() string` |
| `slog.LogValuer` (redaction) | `LogValue() slog.Value` |
| `encoding/json` | `MarshalJSON() ([]byte, error)` / `UnmarshalJSON([]byte) error` |
| `database/sql` | `Value() (driver.Value, error)` / `Scan(v any) error` |
| `encoding.TextMarshaler` (env, YAML, query strings) | `MarshalText` / `UnmarshalText` |

`LogValue()` on a secret-holding type redacts it from every `slog` call without per-call effort:

```go
type Token string
func (t Token) LogValue() slog.Value { return slog.StringValue("[REDACTED]") }
```

### `go:embed`

```go
import _ "embed"

//go:embed migrations/*.sql
var migrationsFS embed.FS

//go:embed templates/email/welcome.html
var welcomeTemplate string
```

Ships SQL migrations, HTML/email templates, OpenAPI specs, default config inside the binary. Eliminates "where is the file in prod" class of bugs.

## Output Format

When invoked from an implementation workflow, emit decisions per concern:

```
| Concern | Decision | Rationale |
|---------|----------|-----------|
| Status field | iota + Stringer + Value/Scan | DB and log crossing |
| ID types | `type UserID int64`, `type OrderID int64` | compile-time swap detection |
| Server config | functional options | 4 optional knobs |
| Embedded file | `go:embed migrations/*.sql` | ship in binary |
```

When invoked from a review workflow, emit one finding block per non-idiomatic shape:

```
### [Severity] file:line

- Code: {one-line citation}
- Non-idiomatic because: {what the Go idiom is}
- Recommendation: {concrete edit}
```

## Avoid

- `type FooID = int64` (alias) when you want type safety - use `type FooID int64`
- Generics with one concrete instantiation - inline the type
- Functional options for 0-2 knobs - struct config is simpler
- `defer f.Close()` inside `for` - wrap in an inner func
- Embedding to "inherit" - Go has no virtual dispatch; use composition
- `init()` doing real work - constructor injection is the Go answer
- `interface{}` / `any` to silence a type error - find the actual type
- Stringer hand-written when `go generate stringer -type=...` exists
- `time.Sleep` for synchronization - channels or `testing/synctest`
- `panic` in library or service code (only `main` for unrecoverable startup)
