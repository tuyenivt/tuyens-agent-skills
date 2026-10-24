---
name: python-django-patterns
description: "Django/DRF REST API patterns: ViewSets with action serializers, QuerySet optimization (select_related/prefetch_related), constraints, permissions."
metadata:
  category: backend
  tags: [python, django, drf, viewsets, serializers, queryset]
user-invocable: false
---

# Django/DRF Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building or extending Django + DRF REST APIs
- Designing ViewSets, serializers, model managers, or QuerySet optimization
- Fixing N+1 queries, missing constraints, or fat-view code smells
- Reviewing DRF code for structural, performance, or security issues

## Rules

- One serializer per action (create / update / list / detail), `update` and `partial_update` included - never one fat serializer
- Eager load in `get_queryset()` with `select_related` (FK/OneToOne) and `prefetch_related` (M2M/reverse FK); an overridden `list()` calls `self.paginate_queryset()` or pagination is bypassed
- `exists()` over `count() > 0`; `annotate(Count(...))` over per-row `.count()`; `iterator(chunk_size=2000)` for large result sets (required after `prefetch_related`)
- DB-level constraints (`UniqueConstraint`, `CheckConstraint(condition=...)`) - not just `clean()`
- `TextChoices` for status/enum fields - never bare `CharField`
- `select_for_update()` on concurrent state transitions, by PK, inside `transaction.atomic()`; the loser re-reads the new state and gets 409
- Business rules (pricing, state transitions, side effects) in services or model methods - never in views; serializer `create()`/`update()` only map validated nested data to rows
- Dispatch side effects via `transaction.on_commit()` - never before commit, or the worker may read a row that does not exist yet; under `ATOMIC_REQUESTS=True` it fires after the request transaction

## Patterns

### ViewSet with Action Serializers

```python
class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOrderOwner]
    filterset_fields = ["status"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        return {
            "create": OrderCreateSerializer,
            "update": OrderUpdateSerializer,
            "partial_update": OrderUpdateSerializer,
            "list": OrderListSerializer,
        }.get(self.action, OrderDetailSerializer)

    def get_queryset(self):
        return (
            Order.objects.visible_to(self.request.user)
            .select_related("customer")
            .prefetch_related("items__product")
            .annotate(item_count=Count("items"))
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        OrderService.cancel(self.get_object().pk)      # raises OrderConflict (409) when not cancellable
        return Response(status=204)
```

Scope owned resources in `get_queryset()` (`visible_to`), not only in object permissions, so list and detail filter alike. Domain errors are `APIException` subclasses with a `status_code`; bare `APIException` is 500.

### Serializer Validation and Nested Writes

`ModelSerializer` infers `required`, `max_length`, `min_value` and `UniqueValidator` from the model - declare only what the model lacks. Nested writes need the child serializer plus a `create()` override; undeclared, DRF builds a `PrimaryKeyRelatedField` re-parenting existing children:

```python
class OrderCreateSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = ["customer", "reference", "total", "items"]

    def validate(self, attrs):
        if not attrs["items"]:
            raise serializers.ValidationError({"items": "At least one item required"})
        return attrs

    def create(self, validated_data):
        items = validated_data.pop("items")
        with transaction.atomic():
            order = Order.objects.create(user=self.context["request"].user, **validated_data)
            OrderItem.objects.bulk_create([OrderItem(order=order, **i) for i in items])
        return order
```

`bulk_create` skips per-row signals - fine for child rows. A client-supplied FK (`customer`) is scoped to the caller like `get_queryset()`: `get_fields()` narrows `fields["customer"].queryset`.

### QuerySet Optimization

```python
Order.objects.select_related("customer")               # FK / OneToOne - JOIN
Order.objects.prefetch_related("items__product")       # one extra query per relation (2 here)
Order.objects.annotate(n_items=Count("items"))        # one aggregate column

if Order.objects.filter(status="pending").exists(): ...  # LIMIT 1, no COUNT
Order.objects.values_list("id", flat=True)              # skip model instantiation
Order.objects.aggregate(total=Sum("total"), n=Count("id"))  # DB-level
```

`get_queryset()` runs for list and detail alike - keep it cheap; `select_for_update()` does not lock prefetched rows.

### Model: Abstract Base + Manager + TextChoices

```python
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class OrderQuerySet(models.QuerySet):
    def pending(self): return self.filter(status=OrderStatus.PENDING)
    def visible_to(self, user): return self if user.is_staff else self.filter(user=user)

class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"

class Order(TimestampedModel):
    objects = OrderQuerySet.as_manager()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    customer = models.ForeignKey("Customer", on_delete=models.PROTECT, related_name="orders")
    reference = models.CharField(max_length=32)
    total = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])  # DRF infers min_value from validators, never from constraints
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    # OrderItem.order = ForeignKey(Order, related_name="items"); Refund.order = OneToOneField(Order, related_name="refund")

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(total__gte=0), name="order_total_non_negative"),
            models.UniqueConstraint(fields=["customer", "reference"], name="order_reference_unique_per_customer"),
        ]
```

A new constraint ships as its own migration: CHECK as `NOT VALID` + `VALIDATE`, UNIQUE via `CREATE UNIQUE INDEX CONCURRENTLY` + `USING INDEX` (`python-migration-safety`).

### Concurrent State Transitions

```python
class OrderConflict(APIException):
    status_code = 409

with transaction.atomic():
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != OrderStatus.PENDING:
        raise OrderConflict(f"cannot cancel order in state {order.status}")   # the second concurrent click lands here -> 409
    order.status = OrderStatus.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    Refund.objects.create(order=order, amount=order.total)                    # one refund per order: OneToOneField makes refund.order unique
    transaction.on_commit(lambda: send_order_email.delay(order.pk))
```

### Filtering, Pagination, Permissions

```python
# DEFAULT_PAGINATION_CLASS defaults to None: without it a ViewSet does not paginate
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend", "rest_framework.filters.OrderingFilter"],
}

class IsOrderOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_staff or obj.user == request.user
```

A custom range parameter (`created_after`) needs a `FilterSet` with `DateTimeFilter(field_name="created_at", lookup_expr="gte")`; `filterset_fields = {"created_at": ["gte"]}` gives `created_at__gte` without one.

## Output Format

When authoring, emit this block plus the code it describes, one block per Pattern the change touches (a model with its constraints is one Model block; a fix spanning Patterns emits one block each). When reviewing, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit one block per deviation with `Change` as the required fix; `Queries` is `n/a` when the query count does not change.

```
Pattern: {ViewSet | Serializer | QuerySet | Model | Filter | Pagination | Permission | Locking | Transaction | Service | Signal}

Model/View: {name}

Change: {description}

Queries: {before -> after | n/a}
```

## Avoid

- Signals for business logic - hard to trace, test, debug
- `fields = "__all__"`, `depth=N`, or reading `self.initial_data` in `create()` - declare fields and use `validated_data`
