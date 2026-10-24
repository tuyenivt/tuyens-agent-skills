---
name: python-django-overengineering-review
description: Django/DRF necessity review - serializer validators duplicating ORM/DB, defensive None after .get(), single-impl service classes, signal abuse.
metadata:
  category: backend
  tags: [python, django, drf, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack. Use only when the detected `Framework:` is Django; otherwise the deliverable is the single line Output Format gives for the detected framework.

## When to Use

- Reviewing a Django diff that adds DRF serializer validators, defensive `None` guards, service classes, ABCs, or new signals
- Phase D of `task-python-review` when Django is detected: catching code that is correct, performant, and safe - but does not need to exist. Defects seen on the way (N+1 queries, f-string SQL, missing pagination) belong to the sibling lenses, never to a necessity finding.

## Rules

- Every finding cites the constraint that makes the code redundant - one `Redundant because:` value from Output Format, named concretely (the FK, the unique index, the model field rule a `ModelSerializer` infers, the single implementer). No citation, no finding.
- Label ladder, applied in order:
  1. The constraint is not visible in the diff or the repo (unique index not shown, model field not read) -> `[Recommend]`, asking the author to confirm it.
  2. The constraint is visible and a measurable cost is present -> `[Must]`, with `Cost:` filled: an extra SELECT per write on a hot path (`extra SELECT per write`); a bare `except` / `except Exception` that defeats DRF's exception handler (`masked exception`); an `ABC` / `BaseService[T]` with a single implementer and no test fake or planned second implementer (`two-file refactor`); a `post_save` signal that dispatches async work or external side effects (`signal-hidden side effect`).
  3. Otherwise -> `[Recommend]`.
- "Single implementer" and "no test fake" are confirmed by search (`tests/`, `conftest.py`, subclasses), never assumed; a fake that exists but no test imports counts as absent and is named in the finding.
- A redundancy with visible justification emits no block: a comment naming the second implementer (noted as stale if it never landed), a second write path that bypasses the serializer (Celery task, management command, admin, `bulk_create`), a validator that adds a rule or user-facing message the mirrored model rule lacks - on any serializer, read-only or not.
- `file:line` comes from the diff; for a PR described in prose with no diff on disk, write `file:n/a` and quote the line in `Code:`.

## Patterns

### Category 1: Redundant validation vs Django ORM / DB constraints

The stack: **type annotation -> DRF serializer field (`required`, `max_length`, `validators=[...]`) -> Django model field (`null=False`, `validators=[...]`) -> DB schema**. Generic `create()` / `update()` call `is_valid(raise_exception=True)` and return 400 before `perform_create()` or `save()`. `ModelSerializer` infers `required=True` from `null=False, blank=False` with no default, and copies model validators (`MinValueValidator` -> `min_value`, `unique=True` -> `UniqueValidator`). Restating them is dead code; a custom message goes in `extra_kwargs`, not a validator.

#### Serializer `validate_<field>` re-running inferred model rules

```python
# Bad - validate_quantity re-runs MinValueValidator(1) that ModelSerializer already applies
class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem  # quantity = IntegerField(validators=[MinValueValidator(1)])
        fields = ["customer", "quantity"]

    def validate_quantity(self, value):
        if value < 1: raise serializers.ValidationError("quantity must be >= 1")
        return value

# Good - let ModelSerializer infer the rule; keep the wording via extra_kwargs
class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["customer", "quantity"]
        extra_kwargs = {"quantity": {"error_messages": {"min_value": "quantity must be >= 1"}}}
```

#### Manual unique-check before `save()`

Races and adds a SELECT per write; `unique=True` and the DB unique index decide anyway. Label per the ladder - `[Must]` once the index is visible and the write is on a hot path. `UniqueValidator` does the same SELECT (same race) but yields a clean field-level error - pair it with the index, never in place of one.

```python
# Bad
if User.objects.filter(email=req.email).exists():
    raise ValidationError("email taken")
User.objects.create(email=req.email)

# Good - the unique constraint is authoritative; an inner atomic() keeps the outer transaction usable
try:
    with transaction.atomic():
        User.objects.create(email=req.email)
except IntegrityError as e:
    raise DuplicateEmailError() from e
```

### Category 2: Defensive code for impossible states

`Model.objects.get()`, DRF serializer binding, permission classes, and Python's type system signal absence by raising or by returning typed results. Re-checking what one already proved is dead code; broad `except` hides regressions that should crash loudly.

#### `if obj is None` after `Model.objects.get()`

`get()` raises `Model.DoesNotExist` (or `MultipleObjectsReturned`); it never returns `None`.

```python
# Bad
order = Order.objects.get(id=order_id)
if order is None:                        # unreachable; get() raises DoesNotExist
    raise Http404("order not found")

# Good - get_object_or_404 in views; filter().first() in services that want a nullable return
order = get_object_or_404(Order, id=order_id)
```

#### `try: get() except DoesNotExist: return None` instead of `filter().first()`

Only on a unique lookup (pk or `unique=True` field) - `Redundant because: framework guarantee`; on a non-unique lookup `get()` is the stricter check (`MultipleObjectsReturned`) and stays.

```python
# Bad - imperative shape; allocates the exception path unnecessarily
try: return Order.objects.get(id=order_id)
except Order.DoesNotExist: return None

# Good - the queryset already encodes "may be absent"
return Order.objects.filter(id=order_id).first()
```

#### Re-checking a guarantee the framework already enforced

```python
# Bad - IsAuthenticated ran before the view body; request.user is never None or AnonymousUser here
class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    def perform_create(self, serializer):
        if self.request.user is None: raise PermissionDenied()
        serializer.save(owner=self.request.user)
```

`if order.status:` on a `blank=False` CharField is **not** redundant: `blank` is validation only (`full_clean()`, forms, serializer `allow_blank`), never a DB constraint, and `create()` stores `''`. It is a finding only with a DB `CheckConstraint` on the column, cited.

#### `bare except` / `except Exception` defeating DRF's exception handler

Category 2, `Redundant because: exception propagation`, `Cost: masked exception`, labelled per the ladder. Bare `except` catches `KeyboardInterrupt` and `SystemExit`; `except Exception` masks `TypeError`, `AttributeError`, `DatabaseError`, and defeats `EXCEPTION_HANDLER` mapping - typed errors become opaque 500s.

```python
# Bad
try: return service.fulfill(order_id)
except Exception as e:
    logger.error("fulfillment failed", exc_info=e)
    return Response({"error": "something went wrong"}, status=500)

# Good - typed APIException subclasses carry the status; a bare APIException is itself a 500
class InsufficientStockError(APIException):
    status_code = 409; default_code = "insufficient_stock"

try: return service.fulfill(order_id)
except InsufficientStock as e: raise InsufficientStockError(detail=str(e))
```

### Category 3: Premature abstraction

#### Single-impl `ABC` / service class wrapping one ORM call / `BaseService` parent

```python
# Bad - one ABC with one implementer; or a class wrapping a single .filter().first()
class OrderRepository(ABC):
    @abstractmethod
    def find(self, order_id: int) -> Order | None: ...

class DjangoOrderRepository(OrderRepository):
    def find(self, order_id: int) -> Order | None:
        return Order.objects.filter(id=order_id).first()

# Good - a module-level function until a second implementer is needed
def get_order(order_id: int) -> Order | None:
    return Order.objects.filter(id=order_id).first()
```

Managers, model methods and querysets are Django's abstraction layer. An extra repository layer is justified only when the codebase explicitly hides Django (clean-architecture style) or a non-Django backend is planned. `BaseService[T]` with one child is the same finding - inline until 3+ consumers share genuine cross-cutting behaviour. `Redundant because: single implementer`; once the search in Rules confirms no test fake or planned second implementer, ladder step 2 gives `[Must]` with `Cost: two-file refactor`.

#### `post_save` signal hiding business logic

Category 3, `Redundant because: hidden side effect`. Signals belong to cross-cutting concerns (audit, search index sync, cache invalidation); business logic belongs to an explicit service call so control flow is visible at the call site.

```python
# Bad - email + Celery dispatch hidden in a signal; bulk_create silently skips signals
@receiver(post_save, sender=Order)
def on_order_saved(sender, instance, created, **kwargs):
    if created:
        send_confirmation_email(instance)
        FulfillmentTask.delay(instance.id)

# Good - explicit at the service call, dispatched after commit
def create_order(payload) -> Order:
    with transaction.atomic():
        order = Order.objects.create(**payload)
        transaction.on_commit(lambda: send_confirmation_email(order))
        FulfillmentTask.delay_on_commit(order.id)       # Celery 5.4+ DjangoTask (default under the Django fixup unless task_cls is custom); else on_commit(lambda: ...delay(...))
    return order
```

#### Custom `Result[T]` / redundant serializer chains

```python
# Bad - hand-rolled Result wraps a one-line read
T = TypeVar("T")
@dataclass
class Result(Generic[T]):
    value: T | None; error: str | None

def find_order(order_id: int) -> Result[Order]:
    order = Order.objects.filter(id=order_id).first()
    return Result(value=order, error=None if order else "not found")

# Good - the absence is already in the type system
def find_order(order_id: int) -> Order | None:
    return Order.objects.filter(id=order_id).first()
```

```python
# Bad - InternalOrderSerializer -> ServiceOrderSerializer -> OrderResponseSerializer, same fields
class InternalOrderSerializer(serializers.ModelSerializer): ...
class ServiceOrderSerializer(serializers.ModelSerializer): ...
class OrderResponseSerializer(serializers.ModelSerializer): ...

# Good - one response serializer
class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["id", "total", "status"]
```

Keep `Result[T]` only when callers branch on multiple distinct failure modes carrying data beyond a string; otherwise cite `Redundant because: exception propagation` - raised exceptions and `T | None` already carry the failure. Same-field serializer chains are `Redundant because: duplicate schema`.

## Output Format

Blocks join the consuming workflow's unified output ordered `[Must]` first; invoked standalone, the same ordered blocks are the whole deliverable. A redundancy with visible justification emits no block. When the detected framework is FastAPI, the whole deliverable is one line, `Handed off to python-fastapi-overengineering-review`; for any other non-Django framework it is `Not applicable - not a Django project`. No blocks and no `No <category> findings.` lines follow either.

```
### [Must | Recommend] {file:line | file:n/a}

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `validate_quantity` re-running `MinValueValidator(1)`}
- Redundant because: {FK name | `null=False` field | unique index | model validator | DRF rule | permission class | type annotation | framework guarantee | single implementer | hidden side effect | duplicate schema | exception propagation}
- Cost: {extra SELECT per write | masked exception | two-file refactor | signal-hidden side effect} {only for [Must]}
- Recommendation: {concrete edit}
- Justified when: {the legitimate reason that would keep it} {only when one might apply}
```

After the blocks, one line per category with no findings: `No <category> findings.` - so the consuming workflow knows the check ran.

## Avoid

- Recommending removal of `select_related` / `prefetch_related` - those are N+1 prevention, not redundancy
