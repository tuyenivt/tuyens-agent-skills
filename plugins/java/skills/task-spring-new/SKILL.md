---
name: task-spring-new
description: Create new Spring Boot 3.5+ API endpoint with controller, service, repository
metadata:
  category: backend
  tags: [spring-boot, java, rest-api, jpa]
  type: workflow
---

# Spring New Endpoint

## When to Use

- Creating new Spring Boot 3.5+ REST API endpoints
- Scaffolding controller, service, repository, and DTOs
- Applying modern Java 21+ and Spring Boot patterns

## Implementation

Generate complete, production-ready code for Spring Boot 3.5+ / Java 21+:

1. **Controller** - REST endpoints with `@Valid`, proper status codes
2. **Service** - Business logic with `@Transactional`
3. **Repository** - Spring Data JPA with custom queries if needed
4. **DTOs** - Request/Response records with validation
5. **Entity** - JPA entity if needed

## Pattern (Java 21+ / Spring Boot 3.5+)

```java
@RestController
@RequestMapping("/api/v1/{resources}")
@RequiredArgsConstructor  // Lombok for DI
@Slf4j                    // Lombok for logging
public class ResourceController {
    private final ResourceService service;

    @GetMapping("/{id}")
    public ResourceResponse getById(@PathVariable Long id) {
        // No ResponseEntity needed - @RestController handles serialization
        return service.getById(id);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)  // Use @ResponseStatus instead of ResponseEntity
    public ResourceResponse create(@Valid @RequestBody CreateRequest request) {
        var response = service.create(request);  // Use var when type is obvious
        log.info("Created resource: {}", response.id());
        return response;
    }

    // ResponseEntity OK when returning different status codes in same method
    @GetMapping("/{id}/optional")
    public ResponseEntity<ResourceResponse> findById(@PathVariable Long id) {
        return service.findById(id)
            .map(ResponseEntity::ok)
            .orElse(ResponseEntity.notFound().build());
    }
}

@Service
@Transactional(readOnly = true)
@RequiredArgsConstructor
@Slf4j
public class ResourceService {
    private final ResourceRepository repository;

    public ResourceResponse getById(Long id) {
        var entity = repository.findById(id)
            .orElseThrow(() -> new ResourceNotFoundException(id));
        return toResponse(entity);
    }

    // For thread-safety, use skill: concurrency-model
}

// Java 21+ Records for DTOs
public record CreateRequest(
    @NotBlank String name,
    @NotNull @Positive Long amount
) {}

public record ResourceResponse(
    Long id,
    String name,
    Instant createdAt
) {}
```

## Key Skills Reference

For detailed patterns, reference these skills:

- Use skill: `spring-jpa-performance` for optimal data access patterns
- Use skill: `spring-exception-handling` for centralized error handling
- Use skill: `spring-transaction` for transaction management
- Use skill: `spring-security-patterns` for endpoint security configuration
- Use skill: `spring-test-integration` for test slice selection

**Virtual Threads Configuration:**

- Enable in `application.yml`: `spring.threads.virtual.enabled: true`
- Connection pool: 10-40 connections (not 100+)
- Virtual threads excel at I/O-bound operations

## Rules

- Constructor injection only (use `@RequiredArgsConstructor` if Lombok available)
- Records for all DTOs (Java 21+)
- `@Transactional(readOnly = true)` by default on service classes
- Never expose JPA entities in API responses
- No `synchronized` blocks (Virtual Thread compatible)
- Use `var` for local variables when type is obvious
- Use `@ResponseStatus` instead of `ResponseEntity` when possible

## Checklist

- [ ] Constructor injection (no @Autowired fields) - use `@RequiredArgsConstructor` if Lombok available
- [ ] Validation on request DTOs (Jakarta Validation - `jakarta.validation` in Spring Boot 3.x/4)
- [ ] Proper HTTP status codes - use `@ResponseStatus` instead of `ResponseEntity` when possible
- [ ] Pagination for list endpoints
- [ ] Entity not exposed in responses (use DTOs)
- [ ] No `synchronized` blocks (Virtual Thread compatible)
- [ ] Records for immutable DTOs
- [ ] Use `var` for local variables when type is obvious
- [ ] Use `@Slf4j` for logging if Lombok available

## Avoid

- `@Autowired` field injection
- Exposing JPA entities in API responses
- `synchronized` blocks (breaks Virtual Threads)
- `ResponseEntity` when a single status code suffices
- `@MockBean` (deprecated since Spring Boot 3.4.0, use `@MockitoBean`)
