---
name: python-django-overengineering-review
description: Django/DRF necessity review - serializer validators duplicating ORM/DB, defensive None after .get(), single-impl service classes, signal abuse.
metadata:
  category: backend
  tags: [python, django, drf, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack. Use only when the detected framework is Django. For FastAPI, use `python-fastapi-overengineering-review`.

## When to Use

- Reviewing a Django diff that adds DRF serializer validators, defensive `None` guards, service classes, ABCs, or new signals
- Phase D of `task-python-review` when Django is detected: catching code that is correct, performant, and safe - but does not need to exist

## Rules

- Every finding cites the constraint that makes the code redundant: FK name, `null=False` field, unique index, model field validator, DRF serializer rule, type annotation, or framework guarantee.
- Severity:
  - **Default `[Suggestion]`.** Cite the constraint, recommend the edit.
  - **`[High]`** when a measurable cost is present: extra SELECT in a hot path, bare `except` defeating DRF's exception handler, single-impl `ABC` forcing two-file refactors, or a `post_save` signal hiding async dispatch / external side effects from the call site. Cite the cost in the `Cost:` field.
  - **`[Question]`** when justification is plausible but not visible in the diff.
- A redundancy with **visible** justification is not a finding. Skip it. Classic cases: DRF validation on a ViewSet serializer (owns 400 + field errors); defense-in-depth across multiple write paths (HTTP + Celery + management command + admin); `ABC` with a planned second implementer or a `pytest` substitution.

## Patterns

### Category 1: Redundant validation vs Django ORM / DB constraints

The Django validation stack: **type annotation → DRF serializer field (`required`, `max_length`, `validators=[...]`) → Django model field constraints (`null=False`, `validators=[...]`) → DB schema**. DRF returns 400 before the view body runs. `ModelSerializer` infers `required=True` from `null=False`, and runs model-field validators during `is_valid()`. Restating them is dead code.

#### Serializer `required=True` / `validate_<field>` duplicating model rules

```python
# Bad - ModelSerializer infers required=True from null=False; validate_customer re-checks it.
# validate_quantity re-runs MinValueValidator(1) that the model field already applies.
class OrderItem(models.Model):
    quantity = models.IntegerField(validators=[MinValueValidator(1)])

class OrderItemSerializer(serializers.ModelSerializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all(), required=True)

    class Meta:
        model = OrderItem
        fields = ["customer", "quantity"]

    def validate_customer(self, value):
        if value is None: raise serializers.ValidationError("customer required")
        return value
    def validate_quantity(self, value):
        if value < 1: raise serializers.ValidationError("quantity must be >= 1")
        return value

# Good - let ModelSerializer infer the rules
class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["customer", "quantity"]
```

#### Manual unique-check before `save()`

`[High]` - races and adds a SELECT per write; `unique=True` and the DB unique index decide anyway. `UniqueValidator` does the same SELECT (same race) but produces a clean field-level error - pair it with the unique index, don't use it in place of one.

```python
# Bad
if User.objects.filter(email=req.email).exists():
    raise ValidationError("email taken")
User.objects.create(email=req.email)

# Good - the unique constraint is authoritative; translate the IntegrityError
try:
    User.objects.create(email=req.email)
except IntegrityError as e:
    raise DuplicateEmailError() from e
```

### Category 2: Defensive code for impossible states

`Model.objects.get()`, DRF serializer binding, and Python's type system signal absence by raising or by returning typed results. Re-checking what one already proved is dead code; broad `except` can hide regressions that should crash loudly.

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

```python
# Bad - imperative shape; allocates the exception path unnecessarily
try:
    return Order.objects.get(id=order_id)
except Order.DoesNotExist:
    return None

# Good - the queryset already encodes "may be absent"
return Order.objects.filter(id=order_id).first()
```

#### `if x:` truthiness on a typed value

```python
# Bad - status is non-blank CharField; always truthy on a persisted row
if order.status:
    process(order.status)
```

Truthiness checks paper over the absence question. Prefer `is None` for nullable, drop the check for non-nullable types.

#### `bare except` / `except Exception` defeating DRF's exception handler

`[High]`. Bare `except` catches `KeyboardInterrupt` and `SystemExit`. `except Exception` masks `TypeError`, `AttributeError`, `DatabaseError`, and defeats `EXCEPTION_HANDLER` mapping - typed errors become opaque 500s.

```python
# Bad
try:
    return service.fulfill(order_id)
except Exception as e:
    logger.error("fulfillment failed", exc_info=e)
    return Response({"error": "something went wrong"}, status=500)

# Good - name the failures the call can raise; let the rest reach the DRF handler
try:
    return service.fulfill(order_id)
except InsufficientStock as e:
    raise APIException(detail=str(e), code="insufficient_stock")
except PaymentDeclined as e:
    raise APIException(detail=str(e), code="payment_declined")
```

### Category 3: Premature abstraction

#### Single-impl `ABC` / service class wrapping one ORM call / `BaseService` parent

`[High]` when the abstraction forces refactors to touch two files for no behavioral reason.

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

Django's manager methods, model methods, and querysets are the idiomatic abstraction layer. An extra repository layer is justified only when the codebase explicitly hides Django (clean-architecture style) or a non-Django backend is planned. `BaseService[T]` for two children falls in the same anti-pattern - inline until 3+ consumers share genuine cross-cutting behavior.

#### `post_save` signal hiding business logic

`[High]` when the signal triggers async work or external side effects. Signals belong to genuinely cross-cutting concerns (audit, search index sync, cache invalidation); business logic belongs to an explicit service call so control flow is visible at the call site.

```python
# Bad - email + Celery dispatch hidden in a signal; bulk_create silently skips signals
@receiver(post_save, sender=Order)
def on_order_saved(sender, instance, created, **kwargs):
    if created:
        send_confirmation_email(instance)
        FulfillmentTask.delay(instance.id)

# Good - explicit at the service call
def create_order(payload) -> Order:
    order = Order.objects.create(**payload)
    send_confirmation_email(order)
    FulfillmentTask.delay(order.id)
    return order
```

#### Custom `Result[T]` / redundant serializer chains

```python
# Bad - hand-rolled Result wraps a one-line read
@dataclass
class Result(Generic[T]):
    value: T | None
    error: str | None

def find_order(order_id: int) -> Result[Order]:
    order = Order.objects.filter(id=order_id).first()
    return Result(value=order, error=None if order else "not found")

# Good - the absence is already in the type system
def find_order(order_id: int) -> Order | None:
    return Order.objects.filter(id=order_id).first()
```

```python
# Bad - InternalOrderSerializer -> ServiceOrderSerializer -> OrderResponseSerializer
class InternalOrderSerializer(serializers.ModelSerializer): ...
class ServiceOrderSerializer(serializers.ModelSerializer): ...
class OrderResponseSerializer(serializers.ModelSerializer): ...

# Good - one response serializer
class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["id", "total", "status"]
```

Keep `Result[T]` only when callers branch on multiple distinct failure modes carrying data beyond a string.

## Output Format

Findings contribute to the consuming workflow's unified output. One block per finding:

```
### [Suggestion | High | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `validate_quantity` re-running `MinValueValidator(1)`}
- Redundant because: {FK name | `null=False` field | unique index | model validator | DRF rule | framework guarantee}
- Cost: {extra SELECT per save | masked exception | speculative surface area | signal-hidden side effect} _(required for `[High]`; omit otherwise)_
- Recommendation: {concrete edit}
- Justified when: {one-line note if a legitimate reason might apply; otherwise omit}
```

For each of the three categories with no findings, state `No <category> findings.` so the consuming workflow knows the check ran.

## Avoid

- Flagging DRF serializer validators on ViewSet DTOs - that layer owns user-facing error messages
- Flagging `UniqueValidator` when a DB unique constraint also exists - the validator gives a clean field error; both have a role
- Flagging `ABC` / `Protocol` before checking for a test fake or a planned second implementer
- Flagging signals categorically - audit logs, search index sync, cache invalidation are legitimate signal uses
- Recommending removal of `select_related` / `prefetch_related` - those are N+1 prevention, not redundancy
- Confusing "duplicated" with "defense in depth" when multiple write paths bypass the serializer (HTTP + Celery + management command + admin)
