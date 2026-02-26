---
name: spring-jpa-performance
description: JPA query optimization and N+1 prevention
metadata:
  category: backend
  tags: [jpa, hibernate, performance, queries]
user-invocable: false
---

# JPA Performance

## When to Use

- Optimizing data access layer queries
- Preventing N+1 query problems
- Reducing memory footprint of large result sets

## Rules

- Default LAZY for all associations
- Avoid EAGER fetching without explicit need
- Use fetch join selectively for specific queries
- Prefer projection over entity for read-only queries
- Detect and eliminate N+1 queries
- Keep entities small, avoid heavy logic inside entities
- Add indexes on WHERE/ORDER BY/JOIN columns (see core plugin's `db-indexing` for general index strategy)

## Pattern

Bad - Causes N+1 queries:

```java
List<User> users = userRepository.findAll(); // 1 query
for (User u : users) {
    System.out.println(u.getOrders()); // N additional queries
}
```

Good - Fetch join prevents N+1:

```java
@Query("SELECT DISTINCT u FROM User u LEFT JOIN FETCH u.orders")
List<User> findAllWithOrders();
```

## Avoid

- EAGER fetching on @OneToMany relationships
- SELECT \* without specific column projection
