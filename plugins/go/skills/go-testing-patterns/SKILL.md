---
name: go-testing-patterns
description: "Go testing: table-driven, httptest, testcontainers-go, testify, interface mocking, t.Parallel, fixtures, benchmarks, testing/synctest."
metadata:
  category: backend
  tags: [go, testing, httptest, testcontainers, testify, benchmarks]
user-invocable: false
---

# Go Testing Patterns

> Load `Use skill: stack-detect` first. This skill reads `Database` - the production engine the integration rule binds to; the Go version is the `go` directive in `go.mod` (a `## Tech Stack` `Language:` line may carry a version; the directive wins when they differ). Baseline: Go 1.25+ (`t.Context`, `b.Loop`, `synctest.Test`), testcontainers-go v0.35+ (`postgres.Run`, `BasicWaitStrategies`, `TerminateContainer`, `CleanupContainer`), testify v1.10+, stripe-go v82.1+ (`stripe.NewClient`).

## When to Use

- Designing a test strategy for a Go service
- Writing handler / service / repository / webhook / async tests
- Reviewing tests for coverage, brittleness, or speed

## Rules

- Table-driven for any function with multiple cases
- `require` halts on failure (setup); `assert` continues (post-conditions)
- `t.Parallel()` on every independent test. Independence is a property you build: a fixture must generate its own value for every unique-constrained column, and isolation must be per-test (a transaction rolled back in `t.Cleanup`, or a per-test database cloned with `CREATE DATABASE ... TEMPLATE` - PostgreSQL; MySQL has no template databases, so clone by schema dump, and its lock wait is `innodb_lock_wait_timeout`). TRUNCATE between tests is not parallel-safe - it deletes a sibling's rows mid-assertion
- Mock via consumer-defined interfaces; never mock concrete types or the DB. A handler that takes a concrete service type cannot be tested in isolation - extract the interface at the handler
- Integration tests run against the same engine as production, via `testcontainers-go`. A different engine (SQLite standing in for Postgres) does not reproduce DDL, FK enforcement, `FOR UPDATE`, or error codes. When the production engine is unknown, say so and treat the substitution as unresolved rather than acceptable
- Test public behavior; testing a private function suggests bad package design
- No wall-clock waiting for synchronization - inject a clock, use channels, `testing/synctest`, or testcontainers wait strategies. `time.Sleep`, `assert.Eventually`, and a hand-rolled poll loop are the same defect at different sizes. A deadline on the code under test's `ctx` is a bound, not a wait, and is fine
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

A Gin DTO validates through `binding:` tags on `ShouldBind*`; a bare `validator.New().Struct(req)` reads `validate:` tags, finds none, and passes everything - test validation through the handler, not the validator.

### Webhook Tests (Signature)

```go
tests := []struct {
    name, sigHeader string
    wantStatus      int
}{
    {"valid", computeStripeSignature(t, payload, secret), http.StatusOK},
    {"invalid", "invalid", http.StatusBadRequest},
    {"missing", "", http.StatusBadRequest},
}
```

Compute signatures dynamically with the provider's test helpers (stripe-go: `webhook.GenerateTestSignedPayload`) over the exact bytes the handler will read; never hardcode - `ConstructEvent` rejects a `t=` older than the 300s `DefaultTolerance`, so a captured signature fails within minutes. A test that signs a re-marshaled body passes against a handler that re-marshals too, and both fail against the provider - sign the raw body.

### Interface Mocking

Function-field structs are simplest; for larger projects use `mockery` / `gomock`; `testify/mock` is a hand-written mock with expectations.

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

// Gate container-backed tests with a build tag. testing.Short() cannot be read in TestMain
// before m.Run() without an explicit flag.Parse() (it panics "Short called before Parse"),
// and -short still compiles and links the package; the tag keeps it out of the unit run entirely.
func TestUserRepo_Integration(t *testing.T) {
    t.Parallel() // owns its container, so it is independent - the per-package form is TestMain below
    ctx := t.Context() // CleanupContainer brings its own teardown context

    pg, err := postgres.Run(ctx, "postgres:16-alpine",
        postgres.WithDatabase("testdb"),
        postgres.WithUsername("test"),
        postgres.WithPassword("test"),
        testcontainers.WithWaitStrategy(
            wait.ForLog("database system is ready to accept connections").WithOccurrence(2)),
    )
    testcontainers.CleanupContainer(t, pg) // before require: Run can return a container AND an error
    require.NoError(t, err)

    connStr, err := pg.ConnectionString(ctx, "sslmode=disable")
    require.NoError(t, err)
    db := setupTestDB(t, connStr) // runs migrations
    repo := NewUserRepository(db)

    t.Run("creates and retrieves", func(t *testing.T) {
        u := &User{Name: "Alice", Email: "alice+" + t.Name() + "@example.com"} // unique per test
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
    first, err := repo.CreateIdempotent(ctx, p)
    require.NoError(t, err) // setup: a dropped error here panics on first.ID below
    dup := newTestPayment(withAmount(9999))
    dup.IdempotencyKey = p.IdempotencyKey
    second, err := repo.CreateIdempotent(ctx, dup)
    require.NoError(t, err)
    assert.Equal(t, first.ID, second.ID)
    assert.Equal(t, first.Amount, second.Amount) // original wins
})
```

### TestMain (shared container)

Keyset paging is an integration test: seed more than one page with duplicate sort keys, walk every page, assert no overlap and no gap; a plan assertion runs `EXPLAIN (FORMAT JSON)` (MySQL: `EXPLAIN FORMAT=JSON`) and asserts the index name. Contention is an integration test too: N goroutines released by one channel barrier against committed rows, errors collected under a mutex, then assert exactly one success and the invariant (`SUM(refunds) <= captured`).

One container per test function costs minutes at suite scale. Share it per package, and isolate each test in a transaction rolled back in `t.Cleanup` - compatible with `t.Parallel()`, as is a per-test database cloned from a migrated template. A test that must commit (a `FOR UPDATE SKIP LOCKED` claim needs two committed sessions) keeps its own committed rows, drops `t.Parallel()`, and cleans up explicitly. It must also be a **top-level** test: Go resumes paused parallel tests only after every sequential top-level test returns, so a non-parallel subtest under a parallel parent still runs alongside the parallel set. Give the claiming sessions a `SET LOCAL lock_timeout` too (MySQL: `SET SESSION innodb_lock_wait_timeout = 1`) - without `SKIP LOCKED` the second claimer blocks rather than returning, and the test hangs CI instead of failing red.

`go test` runs one binary per package, so per-package sharing still starts one container per integration package. To get one for the whole suite, read a `TEST_DATABASE_URL` when CI provides a service container and fall back to `testcontainers-go` only when it is unset.

```go
//go:build integration

var testDB *sqlx.DB // package-shared

func TestMain(m *testing.M) {
    gin.SetMode(gin.TestMode)
    ctx := context.Background()
    pg, err := postgres.Run(ctx, "postgres:16-alpine",
        postgres.BasicWaitStrategies()) // v0.35+; the module sets no readiness wait of its own
    if err != nil { _ = testcontainers.TerminateContainer(pg); log.Fatal(err) } // Run can return a container AND an error
    testDB = mustSetupDB(pg) // migrations run once
    code := m.Run()
    _ = testcontainers.TerminateContainer(pg) // v0.34+
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

An SDK that resolves its own endpoint needs its backend overridden too (stripe-go v82.1+: `stripe.NewClient(key, stripe.WithBackends(...))` pointed at the test server), or the test silently calls the real API. Cover the error mappings (4xx, 5xx, malformed body, context deadline - the deadline case asserts the indeterminate classification, not a retry), not just the happy path. A Kafka producer is tested against `franz-go/pkg/kfake` (in-process broker), asserting the record landed once.

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

Also assert the permanent-failure path wraps `asynq.SkipRetry` - Asynq then archives the task at once instead of retrying it through the whole budget - and that a malformed payload takes that path.

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
go test -race -shuffle=on -p 4 -parallel 4 ./...                 # unit; integration packages are excluded by their build tag
go test -tags=integration -race -p 2 -parallel 4 ./...           # integration, container-backed
```

`-p` caps concurrently running package binaries, `-parallel` caps tests that called `t.Parallel()` inside one binary (top-level and subtests alike) - a `-race` OOM is usually the first. `-shuffle=on` surfaces order dependence. Dropping `-race` to fix an OOM removes the only check that the added parallelism is safe; cap `-p` instead.

## Edge Cases

- testcontainers: use `MappedPort()` / `ConnectionString()`, never hardcode ports
- `t.Cleanup` runs LIFO - register container teardown before DB close
- `gin.SetMode(gin.TestMode)` in the package's one `TestMain` to suppress debug noise; when the integration `TestMain` sits behind `//go:build integration`, the unit suite needs its own under `//go:build !integration` (a package declares only one), or the mode is set in an `init()` of an untagged test file
- `t.Context()` (Go 1.24+) over `context.Background()` in tests - but it is already cancelled when `t.Cleanup` funcs run, so container/DB teardown needs its own context

## Output Format

Emit these headings, in this order, for the engagement:

| Engagement | Headings |
|------------|----------|
| Design | `## Test Strategy` with `### Coverage`, `### Fixtures`, `### Mocks`; code for the key tests follows under `### <Test>` headings in `Coverage` order; existing tests kept as-is append `(existing)`, replaced ones `, replaces <name>`, to the `Key Scenarios` cell (Coverage) or the `Strategy` cell (Mocks); existing tests handed with the brief that violate a Rule emit `## Findings` first |
| Review | `## Findings`, then `## Test Strategy` describing the suite as it exists today |
| Triage (slow / flaky) | two opening lines `**Failing:**` and `**First fix:**`, then `## Findings`, then `## Fix Order` - numbered, isolation (per-test DB or rollback, tag gates) before parallelism, container consolidation before `-race` tuning, since several fixes are prerequisites for others - then `## Test Strategy` as it exists today |

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

Cell values: `Layer` is `handler | middleware | service | repository | worker | client | ci` - `client` for outbound HTTP and producer tests. `Type` is `unit | handler | integration | job | benchmark | validation` - `validation` for a test that exercises DTO binding only, `integration` also for schema, query-plan and contention assertions, `unit` for a test of a test-local helper; table-driven is a style, named in `Key Scenarios`, not a `Type`. `Count` is test functions / subtest cases (`3 / 14`; a function with no subtests is `1 / 0`); for tests the design proposes, a delta (`+2 / +9`); when the inventory was not supplied, deltas only. `Strategy` is `function-field fake | hand-written mock | generated mock | real (container) | real (in-process broker) | real (substitute engine) | httptest server | not mocked` - `hand-written mock` covers `testify/mock`, `real (in-process broker)` is `kfake` or `miniredis`, `real (substitute engine)` is SQLite standing in for Postgres and is always paired with a finding, `not mocked` a concrete dependency used as-is (its `Interface` cell names the type). `Package` is the package that declares the interface - the consumer. `Builder` is `none (literal)` when tests construct the value inline. A table with no rows emits one row reading `(none)` with the reason, never an empty table. A cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries. `**Failing:**` names the symptoms; `**First fix:**` the one change the others depend on.

Every finding carries exactly one label:

```
## Findings

### [{Must | Recommend}] {file:line | file:start-end | file:<symbol>}

- Defect: {what the test fails to catch, or what makes it fail spuriously}
- Rule: {the testing rule violated}
- Fix: {rewritten test code; for a CI or Makefile finding the corrected line; for an owned-by block the production change in one clause}
```

`[Must]` when a test passes while the behavior it names is broken, fails without a code change (a timing wait, a captured signature), panics on its own failure path, races, leaks state into other tests, or a CI or Makefile setting masks failures (dropping `-race`, `-short` that never skips); `[Recommend]` otherwise. A missing test cites the production symbol as `<test file>:<missing Test...>`. Cite `file:line` when the input carries line numbers (a workflow file or Makefile is a file like any other), `file:<symbol>` when it does not; a range is `file:start-end`. Order `[Must]` first, then by file in the order the input listed them, then line. With no findings, `## Findings` holds the single line `None.` One root cause at several sites (TRUNCATE in every test) is one heading citing the first site, with the rest named on the `Defect:` line; one failure signature with one cause is one finding. A defect in the production code that a test exposes (a signature over the wrong bytes, a goroutine that outlives the request) is still reported, never dropped: one block per such defect after the owned findings, in the same file-then-line order, labelled by the criteria above, with its `Rule:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- `time.Sleep` for sync
- Testing private functions
- Mocking the database
- Missing `t.Parallel()`
- Shared global state across tests
- Hardcoded webhook signatures
- `testing.Short()` as the container gate - use the build tag
