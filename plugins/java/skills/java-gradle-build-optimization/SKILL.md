---
name: java-gradle-build-optimization
description: Gradle build optimization for Spring Boot multi-module projects. Covers version catalogs, build cache, configuration cache, parallel execution, and common Gradle anti-patterns.
metadata:
  category: backend
  tags: [gradle, build, spring-boot, multi-module, performance]
user-invocable: false
---

# Gradle Build Optimization

## When to Use

- Setting up a new Spring Boot Gradle project or migrating from Maven
- Optimizing slow Gradle builds (local or CI)
- Structuring a multi-module Spring Boot project
- Standardizing dependency versions across modules
- Configuring CI/CD pipelines for Gradle projects

## Rules

- Use Kotlin DSL (`.gradle.kts`) for all new projects
- Centralize dependency versions in `gradle/libs.versions.toml`
- Enable parallel execution and build cache by default
- Use convention plugins instead of `allprojects {}` / `subprojects {}`
- Apply Spring Boot plugin only to application modules, never library modules
- Minimize `api()` dependency scope — prefer `implementation()`
- Commit Gradle wrapper files (`gradlew`, `gradle-wrapper.jar`) to version control

## Pattern

### Version Catalog

Define `gradle/libs.versions.toml`:

```toml
[versions]
spring-boot = "3.5.0"
java = "21"

[libraries]
spring-boot-starter-web = { module = "org.springframework.boot:spring-boot-starter-web" }
spring-boot-starter-data-jpa = { module = "org.springframework.boot:spring-boot-starter-data-jpa" }
spring-boot-starter-test = { module = "org.springframework.boot:spring-boot-starter-test" }
spring-boot-starter-actuator = { module = "org.springframework.boot:spring-boot-starter-actuator" }

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
spring-dependency-management = { id = "io.spring.dependency-management", version = "1.1.7" }
```

Usage in `build.gradle.kts`:

```kotlin
dependencies {
    implementation(libs.spring.boot.starter.web)
    implementation(libs.spring.boot.starter.data.jpa)
    testImplementation(libs.spring.boot.starter.test)
}
```

### Build Performance

Configure `gradle.properties`:

```properties
org.gradle.parallel=true
org.gradle.caching=true
org.gradle.configuration-cache=true
org.gradle.daemon.idletimeout=600000
org.gradle.jvmargs=-Xmx2g -XX:+UseG1GC
```

### Multi-Module Structure

Root `settings.gradle.kts`:

```kotlin
rootProject.name = "my-app"

include("app", "domain", "infrastructure")

// Include build-logic for convention plugins
includeBuild("build-logic")
```

Convention plugin in `build-logic/src/main/kotlin/java-conventions.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<Test> {
    useJUnitPlatform()
    maxParallelForks = Runtime.getRuntime().availableProcessors().div(2).coerceAtLeast(1)
    jvmArgs("-Djdk.virtualThreadScheduler.parallelism=4")
}
```

Application module `app/build.gradle.kts`:

```kotlin
plugins {
    id("java-conventions")
    alias(libs.plugins.spring.boot)
    alias(libs.plugins.spring.dependency.management)
}

dependencies {
    implementation(project(":domain"))
    implementation(project(":infrastructure"))
    implementation(libs.spring.boot.starter.web)
}
```

Library module `domain/build.gradle.kts`:

```kotlin
plugins {
    id("java-conventions")
    `java-library`
}

// No Spring Boot plugin — this is a library module
dependencies {
    api(libs.spring.boot.starter.data.jpa) // api() only when types leak into public API
    implementation(libs.spring.boot.starter.web) // implementation() for internal usage
}
```

### api() vs implementation() Scope

| Scope              | When to Use                                                  |
| ------------------ | ------------------------------------------------------------ |
| `implementation()` | Default — dependency is internal to the module               |
| `api()`            | Only when dependency types appear in the module's public API |

Bad — leaks all transitive dependencies:

```kotlin
api(project(":infrastructure")) // Exposes everything from infrastructure
```

Good — minimal exposure:

```kotlin
implementation(project(":infrastructure")) // Only this module sees infrastructure types
```

### Spring Boot-Specific Configuration

Boot JAR with layered JARs for Docker:

```kotlin
tasks.bootJar {
    mainClass.set("com.example.Application")
    layered {
        enabled.set(true)
    }
}
```

GraalVM native image support:

```kotlin
tasks.processAot {
    enabled = true
}
tasks.processTestAot {
    enabled = true
}
```

### Dependency Management

BOM import via `platform()`:

```kotlin
dependencies {
    implementation(platform(libs.spring.boot.starter.web))
}
```

Strict dependency resolution:

```kotlin
configurations.all {
    resolutionStrategy {
        failOnVersionConflict()
    }
}
```

Dependency locking for reproducible builds:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
// Generate: ./gradlew dependencies --write-locks
// Inspect:  ./gradlew dependencies --scan
```

### CI/CD Optimization

Recommended CI build command:

```bash
./gradlew build --parallel --build-cache --no-daemon
```

Pipeline stage separation:

```bash
# Stage 1: compile + unit tests
./gradlew check --parallel --build-cache --no-daemon

# Stage 2: integration tests
./gradlew integrationTest --parallel --build-cache --no-daemon
```

CI cache directories:

```yaml
# GitHub Actions example
- uses: actions/cache@v4
  with:
    path: |
      ~/.gradle/caches
      ~/.gradle/wrapper
    key: gradle-${{ hashFiles('**/*.gradle.kts', 'gradle/libs.versions.toml') }}
```

Use `--no-daemon` in CI — daemon wastes memory in ephemeral runners.

## Avoid

- ❌ Groovy DSL (`.gradle`) for new projects — use Kotlin DSL (`.gradle.kts`)
- ❌ `allprojects {}` / `subprojects {}` blocks — use convention plugins in `build-logic/`
- ❌ Force-resolving all configurations at configuration time — delays build startup
- ❌ Publishing internal modules as JARs when `project()` dependency suffices
- ❌ Applying Spring Boot plugin to library modules — only application modules need `bootJar`
- ❌ Using `api()` by default — prefer `implementation()`, use `api()` only for public API types
- ❌ Running CI builds with Gradle daemon — use `--no-daemon` for ephemeral runners
- ❌ Hardcoding dependency versions in `build.gradle.kts` — centralize in version catalog
