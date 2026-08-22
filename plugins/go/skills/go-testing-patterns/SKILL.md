---
name: go-testing-patterns
description: "Go testing: table-driven, httptest, testcontainers-go, testify, interface mocking, t.Parallel, fixtures, benchmarks, testing/synctest."
metadata:
  category: backend
  tags: [go, testing, httptest, testcontainers, testify, benchmarks]
user-invocable: false
---

# Go Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing a test strategy for a Go service
- Writing handler / service / repository / webhook / async tests
- Reviewing tests for coverage, brittleness, or speed

## Rules

- Table-driven for any function with multiple cases
- `require` halts on failure (setup); `assert` continues (post-conditions)
- `t.Parallel()` on every independent test. Independence is a property you build: a fixture must generate its own value for every unique-constrained column, and isolation must be per-test (a transaction rolled back in `t.Cleanup`). TRUNCATE between tests is not parallel-safe - it deletes a sibling's rows mid-assertion
- Mock via consumer-defined interfaces; never mock concrete types or the DB
- Integration tests run against the same engine as production, via `testcontainers-go`. A different engine (SQLite standing in for Postgres) does not reproduce DDL, FK enforcement, `FOR UPDATE`, or error codes. When the production engine is unknown, say so and treat the substitution as unresolved rather than acceptable
- Test public behavior; testing a private function suggests bad package design
- No wall-clock waiting for synchronization - inject a clock, use channels, `testing/synctest`, or testcontainers wait strategies. `time.Sleep`, `assert.Eventually`, and a hand-rolled poll loop are the same defect at different sizes
- `go test -race` on every package that uses goroutines, channels, or shared state

## Patterns

### Table-Driven

```go
func TestPaymentTransition(t *testing.T) {
    t.Parallel()
    tests := []struct {
        name      string
        from, to  string
        wantErr   bool
        errTarget error
    }{
        {"pending->processing", "pending", "processing", false, nil},
        {"processing->completed", "processing", "completed", false, nil},
        {"pending->completed (skip)", "pending", "completed", true, ErrInvalidTransition},
        {"completed->pending (reverse)", "completed", "pending", true, ErrInvalidTransition},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            t.Parallel()
            err := NewPaymentService(mockRepo(tt.from)).Transition(t.Context(), "pay_123", tt.to)
            if tt.wantErr {
                require.Error(t, err)
                assert.ErrorIs(t, err, tt.errTarget)
            } else {
                require.NoError(t, err)
            }
        })
    }
}
```

### Handler Tests (httptest)

```go
func TestGetUser_NotFound(t *testing.T) {
    t.Parallel()
    mockSvc := &MockUserService{
        GetUserFn: func(ctx context.Context, id string) (*User, error) { return nil, ErrNotFound },
    }
    r := gin.New()
    r.Use(ErrorHandler())
    r.GET("/users/:id", GetUser(mockSvc))

    w := httptest.NewRecorder()
    req := httptest.NewRequest(http.MethodGet, "/users/999", nil)
    r.ServeHTTP(w, req)

    assert.Equal(t, http.StatusNotFound, w.Code)
}
```

### Webhook Tests (Signature)

```go
tests := []struct {
    name, sigHeader string
    wantStatus      int
}{
    {"valid", computeStripeSignature(t, payload, secret), http.StatusOK},
    {"invalid", "invalid", http.StatusUnauthorized},
    {"missing", "", http.StatusUnauthorized},
}
```

Compute signatures dynamically with the provider's test helpers; never hardcode (timestamps must match).

### Interface Mocking

Function-field structs are simplest; for larger projects use `mockery` / `gomock`.

```go
type MockUserRepository struct {
    FindByIDFn func(ctx context.Context, id string) (*User, error)
    SaveFn     func(ctx context.Context, u *User) error
}
func (m *MockUserRepository) FindByID(ctx context.Context, id string) (*User, error) {
    return m.FindByIDFn(ctx, id)
}
func (m *MockUserRepository) Save(ctx context.Context, u *User) error { return m.SaveFn(ctx, u) }
```

### Fixtures (functional options)

```go
// Every unique-constrained column gets a fresh value, so two parallel tests
// using the bare fixture can never collide on a unique index.
func newTestPayment(opts ...func(*Payment)) *Payment {
    p := &Payment{
        ID: "pay_" + uuid.NewString(), Amount: 1000, Currency: "usd", Status: "pending",
        IdempotencyKey: "idk_" + uuid.NewString(), CreatedAt: time.Now(),
    }
    for _, opt := range opts { opt(p) }
    return p
}

func withStatus(s string) func(*Payment) { return func(p *Payment) { p.Status = s } }
func withAmount(a int64) func(*Payment)  { return func(p *Payment) { p.Amount = a } }

p := newTestPayment(withStatus("completed"), withAmount(5000))
```

### Integration (testcontainers-go)

```go
//go:build integration

// Gate container-backed tests with a build tag, not `testing.Short()`. A
// TestMain that starts a container runs before m.Run() parses flags, so
// testing.Short() reads false there and `go test -short ./...` still boots
// Postgres. The tag is the only gate that works for both.
func TestUserRepo_Integration(t *testing.T) {
    ctx := context.Background()

    pg, err := postgres.Run(ctx, "postgres:16-alpine", // Run added in v0.32.0, which deprecated RunContainer
        postgres.WithDatabase("testdb"),
        postgres.WithUsername("test"),
        postgres.WithPassword("test"),
        testcontainers.WithWaitStrategy(
            wait.ForLog("database system is ready to accept connections").WithOccurrence(2)),
    )
    require.NoError(t, err)
    t.Cleanup(func() { pg.Terminate(ctx) })

    connStr, err := pg.ConnectionString(ctx, "sslmode=disable")
    require.NoError(t, err)
    db := setupTestDB(t, connStr) // runs migrations
    repo := NewUserRepository(db)

    t.Run("creates and retrieves", func(t *testing.T) {
        u := &User{Name: "Alice", Email: "alice@example.com"}
        require.NoError(t, repo.Save(ctx, u))
        got, err := repo.FindByID(ctx, u.ID)
        require.NoError(t, err)
        assert.Equal(t, "Alice", got.Name)
    })
}
```

### Idempotent Upsert Integration

```go
t.Run("duplicate returns existing", func(t *testing.T) {
    p := newTestPayment()
    first, _ := repo.CreateIdempotent(ctx, p)
    dup := newTestPayment(withAmount(9999))
    dup.IdempotencyKey = p.IdempotencyKey
    second, err := repo.CreateIdempotent(ctx, dup)
    require.NoError(t, err)
    assert.Equal(t, first.ID, second.ID)
    assert.Equal(t, first.Amount, second.Amount) // original wins
})
```

### TestMain (shared container)

One container per test function costs minutes at suite scale. Share it per package, and isolate each test in a transaction rolled back in `t.Cleanup` - that is the only isolation compatible with `t.Parallel()`. A test that must commit (a `FOR UPDATE SKIP LOCKED` claim needs two committed sessions) keeps its own committed rows, drops `t.Parallel()`, and cleans up explicitly. It must also be a **top-level** test: Go resumes paused parallel tests only after every sequential top-level test returns, so a non-parallel subtest under a parallel parent still runs alongside the parallel set. Give the claiming sessions a `SET LOCAL lock_timeout` too - without `SKIP LOCKED` the second claimer blocks rather than returning, and the test hangs CI instead of failing red.

`go test` runs one binary per package, so per-package sharing still starts one container per integration package. To get one for the whole suite, read a `TEST_DATABASE_URL` when CI provides a service container and fall back to `testcontainers-go` only when it is unset.

```go
var testDB *sqlx.DB // package-shared

func TestMain(m *testing.M) {
    gin.SetMode(gin.TestMode)
    ctx := context.Background()
    pg, err := postgres.Run(ctx, "postgres:16-alpine")
    if err != nil { log.Fatal(err) }
    testDB = mustSetupDB(pg) // migrations run once
    code := m.Run()
    _ = testcontainers.TerminateContainer(pg)
    os.Exit(code)
}
```

### Benchmarks

```go
func BenchmarkHashPassword(b *testing.B) {
    for b.Loop() { // Go 1.24+
        _, _ = HashPassword("secret")
    }
}
// go test -bench=. -benchmem ./...
```

### Outbound HTTP Client

```go
srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
    paths <- r.URL.Path // buffered chan, not a captured var: the handler runs on the server goroutine
    w.WriteHeader(tt.status)
    io.WriteString(w, tt.body)
}))
t.Cleanup(srv.Close) // fires even when a require aborts the subtest

c := NewClient(srv.URL, WithHTTPClient(srv.Client())) // never a hardcoded host:port
```

An SDK that resolves its own endpoint needs its backend overridden too, or the test silently calls the real API. Cover the error mappings (4xx, 5xx, malformed body, context deadline), not just the happy path.

### Async Handler (at-least-once redelivery)

Queue delivery is at-least-once, so every handler needs a test that runs it twice. Coverage percentage never reveals this gap - the line ran, the scenario did not.

```go
func TestSettle_DuplicateDeliveryIsIdempotent(t *testing.T) {
    t.Parallel()
    var sent int // handler is invoked synchronously here, so no atomic is needed
    h := NewSettleHandler(NewRepo(txFor(t)), mailerFunc(func(context.Context, string) error {
        sent++
        return nil
    }))
    task := asynq.NewTask(TypeSettle, mustJSON(t, SettlePayload{EventID: uuid.NewString()}))

    require.NoError(t, h.ProcessTask(t.Context(), task))
    require.NoError(t, h.ProcessTask(t.Context(), task), "redelivery must ack, not error")
    assert.Equal(t, 1, sent, "receipt emailed twice on redelivery")
}
```

Also assert the permanent-failure path wraps `asynq.SkipRetry`, or a malformed payload retries to the dead-letter queue.

### Deterministic Time

Inject a clock for anything that expires, debounces, or rate-limits. It runs in microseconds, tests the exact boundary that a sleep can only approximate, and works on every Go version.

```go
type Clock interface{ Now() time.Time }

type fakeClock struct { // mutex because the code under test may read Now() from another goroutine under -race
    mu  sync.Mutex
    now time.Time
}
func (c *fakeClock) Now() time.Time { c.mu.Lock(); defer c.mu.Unlock(); return c.now }
func (c *fakeClock) Advance(d time.Duration) { c.mu.Lock(); defer c.mu.Unlock(); c.now = c.now.Add(d) }

clk := &fakeClock{now: time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)}
rl := NewRateLimiter(5, time.Second, WithClock(clk))
clk.Advance(time.Second) // no wall-clock wait, and the boundary is exact
```

`testing/synctest` is the alternative when the code under test blocks on real timers rather than reading a clock. `synctest.Test(t, ...)` is stable in Go 1.25; on Go 1.24 only `synctest.Run(func(){...})` exists, behind `GOEXPERIMENT=synctest`. Neither helps when the goroutine blocks on I/O rather than time.

```go
synctest.Test(t, func(t *testing.T) { // Go 1.25+
    calls := 0
    fn := Debounce(func() { calls++ }, 100*time.Millisecond)
    fn(); fn(); fn()
    time.Sleep(150 * time.Millisecond) // virtual time inside the bubble - returns instantly
    synctest.Wait()
    assert.Equal(t, 1, calls)
})
```

### CI Invocation

```bash
go test -race -short -shuffle=on -p 4 -parallel 4 ./...      # unit; -short skips container tests
go test -tags=integration -race -p 2 -parallel 4 ./...       # integration, container-backed
```

`-p` caps concurrently running package binaries, `-parallel` caps `t.Parallel()` subtests inside one binary - a `-race` OOM is usually the first. `-shuffle=on` surfaces order dependence. Dropping `-race` to fix an OOM removes the only check that the added parallelism is safe; cap `-p` instead.

## Edge Cases

- testcontainers: use `MappedPort()` / `ConnectionString()`, never hardcode ports
- `t.Cleanup` runs LIFO - register container teardown before DB close
- `gin.SetMode(gin.TestMode)` in `TestMain` to suppress debug noise
- `t.Context()` (Go 1.24+) over `context.Background()` in tests - but it is already cancelled when `t.Cleanup` funcs run, so container/DB teardown needs its own context

## Output Format

Designing a suite emits `## Test Strategy`. Reviewing tests or triaging a slow or flaky suite emits `## Findings` first, then the strategy tables describing the suite **as it exists today**.

```
## Test Strategy

### Coverage
| Layer | Type | Count | Key Scenarios |
|-------|------|-------|---------------|

### Fixtures
| Fixture | Builder | Variants |
|---------|---------|----------|

### Mocks
| Interface | Package | Strategy |
|-----------|---------|----------|
```

Cell values: `Type` is `unit | table-driven | handler | integration | job | benchmark`. `Count` is test functions / subtest cases (`3 / 14`); when the inventory was not supplied, state the delta you are proposing rather than an absolute. `Strategy` is `function-field fake | generated mock | real (container) | httptest server | not mocked`. A table with no rows emits one row reading `(none)` with the reason, never an empty table.

```
## Findings

### [Must] file:line

- Defect: {what the test fails to catch, or what makes it fail spuriously}
- Rule: {the testing rule violated}
- Fix: {rewritten test code}
```

`[Must]` when a test passes while the behavior it names is broken, panics on its own failure path, races, or leaks state into other tests; `[Recommend]` otherwise. Order `[Must]` first. For a triage engagement, close with a fix order - isolation before parallelism, container consolidation before `-race` tuning - since several fixes are prerequisites for others.

## Avoid

- `time.Sleep` for sync
- Testing private functions
- Mocking the database
- Missing `t.Parallel()`
- Shared global state across tests
- Hardcoded webhook signatures
