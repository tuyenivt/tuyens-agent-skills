---
name: python-django-patterns
description: "Django/DRF patterns: ViewSets, serializers, QuerySet optimization, signals (sparingly), management commands, Django REST Framework permissions, and project organization."
user-invocable: false
---

## 1. VIEWSETS & SERIALIZERS

- ModelViewSet for full CRUD, custom actions via @action
- Separate serializers: CreateSerializer, UpdateSerializer, ListSerializer, DetailSerializer
- SerializerMethodField for computed fields
- Nested serializers with depth control (explicit, not depth=N)

```python
class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        if self.action == "list":
            return OrderListSerializer
        return OrderDetailSerializer

    def get_queryset(self):
        return (
            Order.objects.filter(user=self.request.user)
            .select_related("customer")
            .prefetch_related("items__product")
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        OrderService.cancel(order)
        return Response(OrderDetailSerializer(order).data)
```

```python
class OrderCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["total", "items"]

class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    total_display = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["id", "total", "total_display", "status", "items", "created_at"]

    def get_total_display(self, obj):
        return f"${obj.total:.2f}"
```

## 2. QUERYSET OPTIMIZATION

- `select_related` (FK, OneToOne - SQL JOIN) vs `prefetch_related` (M2M, reverse FK - 2 queries)
- `only()` and `defer()` for partial field loading
- `values()` and `values_list()` to avoid model instantiation
- `exists()` over `count() > 0`
- `iterator()` for large result sets
- `annotate`/`aggregate` for DB-level computation
- `select_for_update()` for concurrent update safety

```python
# select_related: FK / OneToOne (single JOIN)
Order.objects.select_related("customer")

# prefetch_related: M2M / reverse FK (separate query)
Order.objects.prefetch_related("items__product")

# Efficient existence check
if Order.objects.filter(status="pending").exists():
    ...

# DB-level aggregation
from django.db.models import Sum, Count
Order.objects.aggregate(
    total_revenue=Sum("total"),
    order_count=Count("id"),
)

# Concurrent update safety (e.g., order cancellation)
from django.db import transaction

with transaction.atomic():
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status == "pending":
        order.status = "cancelled"
        order.save(update_fields=["status", "updated_at"])
```

## 3. MODEL PATTERNS

- Abstract base models for shared fields (created_at, updated_at)
- Custom managers for reusable QuerySets
- Model.clean() for cross-field validation
- Constraints (UniqueConstraint, CheckConstraint) at DB level
- Signals: use ONLY for truly decoupled side effects, prefer explicit calls

```python
class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class OrderQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(status="pending")

    def for_user(self, user):
        return self.filter(user=user)

class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"

class Order(TimestampedModel):
    objects = OrderQuerySet.as_manager()
    total = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING,
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(total__gte=0),
                name="order_total_non_negative",
            ),
        ]
```

## 4. FILTERING, PAGINATION, AND ROUTER WIRING

Use `django-filter` for declarative queryset filtering and DRF's built-in pagination.

```python
# filters.py
import django_filters

class OrderFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=OrderStatus.choices)
    created_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    min_total = django_filters.NumberFilter(field_name="total", lookup_expr="gte")

    class Meta:
        model = Order
        fields = ["status", "created_after", "min_total"]

# views.py
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter

class OrderViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_class = OrderFilter
    ordering_fields = ["created_at", "total"]
    ordering = ["-created_at"]
    search_fields = ["customer__name"]
```

```python
# settings.py - pagination
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 20,
}
```

```python
# urls.py - router wiring
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("orders", OrderViewSet, basename="order")

urlpatterns = [
    path("api/", include(router.urls)),
]
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
        """Cross-field validation."""
        if not attrs.get("items"):
            raise serializers.ValidationError({"items": "Order must have at least one item"})
        return attrs
```

## 5. DRF PERMISSIONS

- IsAuthenticated, IsAdminUser, custom permission classes
- Object-level permissions via has_object_permission
- Throttling: UserRateThrottle, ScopedRateThrottle

```python
class IsOrderOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.user == request.user

class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOrderOwner]
```

## 6. ANTI-PATTERNS

- ❌ Fat views (extract to services or model methods)
- ❌ N+1 in serializers (prefetch in `get_queryset`)
- ❌ Signals for business logic (hard to trace, test, debug)
- ❌ `raw()` SQL without parameterization
- ❌ `Model.objects.all()` without pagination
- ❌ `depth=N` on nested serializers (use explicit nested serializer classes)
- ❌ Business logic in serializer `create()`/`update()` (use service layer)
- ❌ Bare `CharField` for status fields (use `TextChoices`)
- ❌ Missing `select_for_update()` on concurrent state transitions
