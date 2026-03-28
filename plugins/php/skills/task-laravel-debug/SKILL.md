---
name: task-laravel-debug
description: Debug Laravel application errors by classifying exceptions, locating root causes, and providing minimal before/after fixes. Covers Eloquent, controllers, queue jobs, migrations, and Pest test failures. Paste a stack trace or describe the unexpected behavior. Not for production incident triage (use task-incident-root-cause for that).
agent: php-architect
metadata:
  category: backend
  tags: [php, laravel, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
---

## STEP 1 - INTAKE

Ask for: full stack trace, the source file where the error originates, and what the user expected to happen. If a stack trace is provided, identify the first application-code frame (skip vendor frames) and read that file.

**If partial input**: If the user provides only a description without a stack trace, search the codebase for the relevant file/function and ask clarifying questions. If only an error message is given (no stack trace), check `storage/logs/laravel.log` and match against the classification table below before asking for more context.

## STEP 2 - CLASSIFY

Match the error to one of these categories, then load the relevant atomic skill:

### Eloquent / Database Errors

- `Illuminate\Database\QueryException` with `SQLSTATE[23000]` -> constraint violation (unique, FK, NOT NULL). Check which column from the error message. Use skill: `laravel-eloquent-patterns`.
- `Illuminate\Database\QueryException` with `SQLSTATE[HY000]` -> connection issue, pool exhausted. Check `config/database.php` connection settings.
- `Illuminate\Database\Eloquent\ModelNotFoundException` -> `findOrFail()` on missing record. Check route model binding or query logic.
- `Illuminate\Database\Eloquent\MassAssignmentException` -> field not in `$fillable`. Use skill: `laravel-security-patterns`.
- N+1 query detection (via Debugbar or `preventLazyLoading`) -> missing `with()` eager loading. Use skill: `laravel-eloquent-patterns` (section 2).
- `Illuminate\Database\Eloquent\RelationNotFoundException` -> relationship method missing or misspelled on model.

### Controller / HTTP Errors

- `Illuminate\Validation\ValidationException` (422) -> form request rules rejected input. Read the `rules()` method and check the failing field.
- `Illuminate\Auth\Access\AuthorizationException` (403) -> policy denied access. Check the policy method and the user's state.
- `Symfony\Component\HttpKernel\Exception\NotFoundHttpException` (404) -> route not found or route model binding failed. Run `php artisan route:list` to verify.
- `Symfony\Component\HttpKernel\Exception\MethodNotAllowedHttpException` (405) -> wrong HTTP method for the route. Check `routes/api.php`.
- `Illuminate\Session\TokenMismatchException` (419) -> CSRF token mismatch. Check session driver and middleware config.

### Queue / Job Errors

- `MaxAttemptsExceededException` -> all retries exhausted. Check `$tries`, `$backoff`, and the original exception. Use skill: `laravel-queue-patterns`.
- Job silently fails -> check `failed_jobs` table and `failed()` method on job class.
- Job processes stale data -> job dispatched before DB commit. Check if `afterCommit()` is used. Use skill: `laravel-queue-patterns`.
- `Illuminate\Queue\TimeoutExceededException` -> job exceeded `$timeout`. Check for blocking operations in `handle()`.

### Migration Errors

- `SQLSTATE[42S01] Table already exists` -> migration re-run without rollback. Check migration status with `php artisan migrate:status`.
- `SQLSTATE[42S22] Column not found` -> migration order issue or missing column. Check migration timestamp ordering.
- Lock timeout during migration -> DDL on large table. Use skill: `laravel-migration-safety`.

### Artisan / Config Errors

- `Target class [X] does not exist` -> missing binding in service provider or controller namespace issue. Check `app/Providers/` and route file namespaces.
- `Call to undefined method` -> wrong method name, missing trait, or wrong class imported.
- Config caching issues -> `env()` called outside config files. Run `php artisan config:clear`. Use skill: `laravel-security-patterns` (section 9).

### Test Errors

- `RefreshDatabase` not applied -> missing trait on test class or `Pest.php` config. Use skill: `laravel-testing-patterns`.
- `Mockery\Exception\InvalidCountException` -> mock expectation not met. Check `shouldReceive` count matches actual calls.
- Database assertion failure (`assertDatabaseHas`) -> wrong table name, column name, or value format.

## STEP 3 - LOCATE

1. Read the stack trace top-to-bottom; find the first application-code frame (skip `vendor/` frames)
2. Open that source file and read the failing function
3. Trace the data path: where does the problematic value originate? Follow it through controller -> service -> model
4. For queue errors: check if the job was dispatched inside a DB transaction

## STEP 4 - ROOT CAUSE

Explain **why** the error occurs, not just what it is. State confidence: **HIGH** (reproduced or obvious from code), **MEDIUM** (likely based on pattern match), **LOW** (multiple possible causes).

```
ROOT CAUSE: [HIGH/MEDIUM/LOW confidence]
The MassAssignmentException occurs because `Order::create($request->all())`
includes the `is_admin` field which is not in `$fillable` on the Order model
at app/Models/Order.php:12. The controller at app/Http/Controllers/
OrderController.php:25 should use $request->validated() instead of
$request->all() to pass only validated fields.
```

## STEP 5 - FIX

Provide before/after code. Fix must be minimal and address root cause, not symptoms.

```php
// BEFORE (mass assignment risk - passes all request data)
public function store(StoreOrderRequest $request): OrderResource
{
    $order = Order::create($request->all());
    return new OrderResource($order);
}

// AFTER (only validated fields passed)
public function store(StoreOrderRequest $request): OrderResource
{
    $order = Order::create($request->validated());
    return new OrderResource($order);
}
```

## STEP 6 - PREVENTION

Add a guard so this class of error cannot recur:

- **Pest test** that exercises the exact code path
- **Model config** (`preventSilentlyDiscardingAttributes`, `preventLazyLoading`) in development
- **Static analysis** rule (PHPStan, Psalm) if applicable
- **Form Request** enforcement for all write endpoints

## Avoid

- Do not add `$guarded = []` to "fix" MassAssignmentException (security vulnerability)
- Do not use `try/catch` to silently swallow exceptions
- Do not add `APP_DEBUG=true` in production to get better error messages
- Do not bypass CSRF with `$except` array unless it's a webhook endpoint
- Do not use `sync` queue driver as a "fix" for queue job failures

## Output Format

```
## Error Classification
[Category]: [specific error type]

## Root Cause (confidence: HIGH/MEDIUM/LOW)
[Why the error occurs, referencing specific file:line]

## Fix
[Before/after code blocks]

## Prevention
[Test, model config, or static analysis rule to prevent recurrence]
```

## Self-Check

- [ ] Error classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal, addresses root cause not symptom
- [ ] Mass assignment addressed by proper `$fillable`, not by `$guarded = []`
- [ ] Prevention step included (Pest test, model config, or static analysis rule)
- [ ] For queue jobs: `afterCommit()` and idempotency addressed; for Eloquent: eager loading checked
