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

- One serializer per action (create / update / list / detail) - never reuse a single fat serializer
- Eager load in `get_queryset()` with `select_related` (FK/OneToOne) and `prefetch_related` (M2M/reverse FK)
- `exists()` over `count() > 0`; `iterator()` for large result sets
- DB-level constraints (`UniqueConstraint`, `CheckConstraint`) - not just `clean()`
- `TextChoices` for status/enum fields - never bare `CharField`
- `select_for_update()` on concurrent state transitions, by PK, inside `transaction.atomic()`
- Business logic in services or model methods - never in views or serializer `create()`/`update()`
- Dispatch side effects via `transaction.on_commit()` - never inside `perform_create` before commit

## Patterns

### ViewSet with Action Serializers

```python
class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOrderOwner]

    def get_serializer_class(self):
        return {
            "create": OrderCreateSerializer,
            "list": OrderListSerializer,
        }.get(self.action, OrderDetailSerializer)

    def get_queryset(self):
        return (
            Order.objects.for_user(self.request.user)
            .select_related("customer")
            .prefetch_related("items__product")
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        OrderService.cancel(self.get_object())
        return Response(status=204)
```

### Serializer Validation

```python
class OrderCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["total", "items"]

    def validate_total(self, value):
        if value <= 0:
            raise serializers.ValidationError("Total must be positive")
        return value

    def validate(self, attrs):
        if not attrs.get("items"):
            raise serializers.ValidationError({"items": "At least one item required"})
        return attrs
```

Avoid `depth=N` for nested reads - declare explicit nested serializer classes. `ModelSerializer` does not support writable nested input out of the box; override `create()` and `bulk_create` the children inside `transaction.atomic()`:

```python
class OrderCreateSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = ["items"]

    def create(self, validated_data):
        items = validated_data.pop("items")
        with transaction.atomic():
            order = Order.objects.create(user=self.context["request"].user, **validated_data)
            OrderItem.objects.bulk_create([OrderItem(order=order, **i) for i in items])
        return order
```

`bulk_create` skips per-row signals - acceptable for child rows whose side effects fire from the order. Scope owned resources in `get_queryset()` (`for_user(self.request.user)`), not just object permissions, so list and detail are both filtered.

### QuerySet Optimization

```python
Order.objects.select_related("customer")               # FK / OneToOne - JOIN
Order.objects.prefetch_related("items__product")       # M2M / reverse FK - 2 queries

if Order.objects.filter(status="pending").exists(): ...  # LIMIT 1, no COUNT
Order.objects.values_list("id", flat=True)              # skip model instantiation
Order.objects.aggregate(total=Sum("total"), n=Count("id"))  # DB-level
```

`get_queryset()` runs for both filtering and detail retrieval - keep it cheap. `select_for_update()` does not lock rows pulled by `prefetch_related` - lock those separately.

### Model: Abstract Base + Manager + TextChoices

```python
class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class OrderQuerySet(models.QuerySet):
    def pending(self): return self.filter(status=OrderStatus.PENDING)
    def for_user(self, user): return self.filter(user=user)

class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"

class Order(TimestampedModel):
    objects = OrderQuerySet.as_manager()
    total = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(total__gte=0), name="order_total_non_negative"),
        ]
```

Reserve signals for truly decoupled cross-app side effects; prefer explicit service calls.

### Concurrent State Transitions

```python
with transaction.atomic():
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status == OrderStatus.PENDING:
        order.status = OrderStatus.CANCELLED
        order.save(update_fields=["status", "updated_at"])
```

### Filtering, Pagination, Routing

```python
# filters.py
class OrderFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=OrderStatus.choices)
    created_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")

    class Meta:
        model = Order
        fields = ["status", "created_after"]

# views.py
class OrderViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_class = OrderFilter
    ordering_fields = ["created_at", "total"]
    ordering = ["-created_at"]
    search_fields = ["customer__name"]

# settings.py
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 20,
}

# urls.py
router = DefaultRouter()
router.register("orders", OrderViewSet, basename="order")
urlpatterns = [path("api/", include(router.urls))]
```

### Permissions

```python
class IsOrderOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.user == request.user
```

Compose with `IsAuthenticated`; throttle auth endpoints with `UserRateThrottle` / `ScopedRateThrottle`.

### Post-Commit Side Effects

```python
def perform_create(self, serializer):
    order = serializer.save()
    transaction.on_commit(lambda: send_order_email.delay(order.id))
```

Celery/webhook dispatch inside `perform_create` before commit can race the transaction - the worker may read a row that does not yet exist.

## Output Format

```
Pattern: {ViewSet | Serializer | QuerySet | Model | Filter | Permission | Locking}
Model/View: {name}
Change: {description}
Queries: {before} -> {after}
```

## Avoid

- Fat views - extract to services or model methods
- N+1 in serializers - eager load in `get_queryset()`
- Signals for business logic - hard to trace, test, debug
- `raw()` SQL without parameterization
- `Model.objects.all()` without pagination
- `depth=N` on nested serializers - declare explicit classes
