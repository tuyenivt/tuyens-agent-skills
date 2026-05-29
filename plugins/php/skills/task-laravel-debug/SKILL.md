---
name: task-laravel-debug
description: Debug Laravel errors: classify exceptions, find root cause, minimal before/after fixes for Eloquent, controllers, jobs, migrations, Pest failures.
agent: php-architect
metadata:
  category: backend
  tags: [php, laravel, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

## When to Use

- Debugging Laravel errors from stack traces or messages
- Classifying Eloquent, controller, queue, migration, or test failures
- Tracing data-flow issues (value sent but stored as null)
- NOT for: production incident triage (use `/task-oncall-start`), perf profiling, infra/deploy issues

## Workflow

### STEP 1 - INTAKE

Use skill: `stack-detect` to confirm Laravel. Ask for the full stack trace, the source file, and expected behavior. Identify the first application-code frame (skip `vendor/`) and read it.

**Partial input:** With only a description, search the codebase and ask clarifying questions. With only an error message, check `storage/logs/laravel.log` and match the classification table first. **Production-only:** diff `APP_ENV`, `APP_DEBUG`, config/route caching between envs. **Intermittent:** likely race condition or pool exhaustion; check `DB_POOL` and traffic correlation.

**"No error, just wrong behavior"** (value missing in DB, email never arrives): reframe as boundary loss - at which layer does the value disappear? Trace: Form Request `rules()` -> `validated()` vs `all()` -> `$fillable` -> `casts()`/mutators -> `prepareForValidation()` -> DB column. Same shape for jobs: dispatch -> `afterCommit()` -> broker -> `handle()` -> side effect. Identify the lossy boundary before reading code.

### STEP 2 - CLASSIFY

Match the error to one category, then load the relevant atomic skill. Exception classes below omit the `Illuminate\` / `Symfony\Component\HttpKernel\Exception\` prefix.

### Eloquent / Database Errors

- `QueryException` `SQLSTATE[23000]`:
  - `1062` duplicate entry -> unique constraint. Find the index in the message.
  - `1452` FK violation -> referenced parent missing or FK column NULL. Check that the referenced row exists and the FK column is populated (from `validated()`, `auth()->id()`, or route param).
  - `1364` NULL on NOT NULL column. Same trace as above.
  - Use skill: `laravel-eloquent-patterns`.
- `QueryException` `SQLSTATE[HY000]` -> connection/pool; check `config/database.php`.
- `ModelNotFoundException` -> `findOrFail()` on missing record; check route model binding or query.
- `MassAssignmentException` -> field not in `$fillable`. Use skill: `laravel-security-patterns`.
- N+1 (Debugbar / `preventLazyLoading`) -> missing `with()` eager load. Use skill: `laravel-eloquent-patterns`.
- `RelationNotFoundException` -> relationship method missing or misspelled.

### Controller / HTTP Errors

- `ValidationException` (422) -> Form Request rejected input; read `rules()`. Use skill: `laravel-api-patterns`.
- `AuthorizationException` (403) -> policy denied; check policy method and user state. Use skill: `laravel-security-patterns`.
- `NotFoundHttpException` (404) -> route or model binding missing; run `php artisan route:list`. Use skill: `laravel-api-patterns`.
- `MethodNotAllowedHttpException` (405) -> wrong HTTP method.
- `TokenMismatchException` (419) -> CSRF mismatch; check session driver and middleware.

### Data Flow Errors (No Exception)

- Value sent but stored as null -> check `$fillable`, `validated()` vs `all()`, cast/mutator. Use skill: `laravel-security-patterns`.
- Unexpected value transformation -> check `casts()`, accessor/mutator, `prepareForValidation()`. Use skill: `laravel-eloquent-patterns`.
- Related data not saving -> check relationship method type and FK column convention.

### Queue / Job Errors

- `MaxAttemptsExceededException` -> retries exhausted; check `$tries`, `$backoff`, original exception. Use skill: `laravel-queue-patterns`.
- Silent failure -> check `failed_jobs` and the job's `failed()` method.
- Stale data -> job dispatched before DB commit; check `afterCommit()`.
- `TimeoutExceededException` -> exceeded `$timeout`; check blocking operations in `handle()`.

### Migration Errors

- `SQLSTATE[42S01]` table exists -> migration re-run without rollback; check `php artisan migrate:status`.
- `SQLSTATE[42S22]` column not found -> order issue or missing column; check migration timestamps.
- Lock timeout -> DDL on large table. Use skill: `laravel-migration-safety`.

### Artisan / Config Errors

- `Target class [X] does not exist` -> missing service-provider binding or controller namespace.
- `Call to undefined method` -> wrong method, missing trait, or wrong import.
- Config caching -> `env()` called outside config files; run `php artisan config:clear`. Use skill: `laravel-security-patterns`.

### Test Errors

- `RefreshDatabase` not applied -> missing trait on test or `Pest.php` config. Use skill: `laravel-testing-patterns`.
- `Mockery\Exception\InvalidCountException` -> mock expectation unmet; check `shouldReceive` count.
- `assertDatabaseHas` failure -> wrong table, column, or value format.

### STEP 3 - LOCATE

Read stack trace top-down, find the first application-code frame, open that file, and trace the data path controller -> service -> model. For queue errors, check whether the job was dispatched inside a DB transaction. For FK violations, check `SHOW CREATE TABLE` (or the migration) to identify which FK fired.

### STEP 4 - ROOT CAUSE

Explain **why**, not just what. State confidence: **HIGH** (reproduced/obvious), **MEDIUM** (pattern match), **LOW** (multiple possible causes).

```
ROOT CAUSE: [HIGH] QueryException 1452 at OrderController.php:25 because
$request->all() passes user_id=null (Form Request didn't extract it).
$fillable accepts it; FK constraint orders.user_id -> users.id rejects.
```

### STEP 5 - FIX

Provide minimal before/after addressing root cause, not symptoms.

```php
// BEFORE
$order = Order::create($request->all());

// AFTER - server-set FK from authenticated user
$order = Order::create([
    ...$request->validated(),
    'user_id' => $request->user()->id,
]);
```

### STEP 6 - PREVENTION

Add one guard so this class of error cannot recur - Pest test exercising the path, model config (`preventSilentlyDiscardingAttributes`, `preventLazyLoading`) in dev, PHPStan/Psalm rule, or Form Request on the endpoint.

## Output Format

```
## Error Classification
Category: {Eloquent/Database | Controller/HTTP | Queue/Job | Migration | Artisan/Config | Test | Data Flow}
Error Type: [specific exception or symptom]

## Root Cause
Confidence: {HIGH | MEDIUM | LOW}
File: [file:line]
[Why the error occurs - cause, not symptom]

## Fix
[Before/after code blocks - minimal change addressing root cause]

## Affected Files
[Files modified by the fix]

## Prevention
Type: {test | model-config | static-analysis | form-request}
[Specific guard to prevent recurrence]
```

## Self-Check

- [ ] STEP 1: Stack trace or error description obtained; Laravel confirmed
- [ ] STEP 2: Error classified into a category; relevant atomic skill loaded
- [ ] STEP 3: Failing source file located; data path traced through layers
- [ ] STEP 4: Root cause explained with confidence level and `file:line`
- [ ] STEP 5: Minimal before/after fix provided addressing root cause
- [ ] STEP 6: Prevention guard added

## Avoid

- `$guarded = []` to "fix" MassAssignmentException (security hole)
- `try/catch` that silently swallows exceptions
- `APP_DEBUG=true` in production
- CSRF `$except` for non-webhook routes
- `sync` queue driver as a "fix" for queue failures
