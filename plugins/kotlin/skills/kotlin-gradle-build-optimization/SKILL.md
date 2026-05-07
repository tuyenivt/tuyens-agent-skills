---
name: kotlin-gradle-build-optimization
description: Gradle Kotlin DSL build optimization for Kotlin/Spring Boot multi-module projects. Covers version catalogs, build cache, configuration cache, parallel execution, kotlin-jpa / kotlin-spring / kotlin-allopen plugins, and common Gradle anti-patterns.
metadata:
  category: backend
  tags: [kotlin, gradle, build, spring-boot, multi-module, performance]
user-invocable: false
---

# Kotlin Gradle Build Optimization

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Setting up a new Kotlin/Spring Boot Gradle project or migrating from Maven
- Optimizing slow Gradle builds (local or CI)
- Structuring a multi-module Kotlin/Spring Boot project
- Standardizing dependency versions across modules
- Configuring CI/CD pipelines for Kotlin/Gradle projects
- Diagnosing JPA / Spring proxy issues caused by missing Kotlin compiler plugins

## Rules

- Use Kotlin DSL (`.gradle.kts`) for all new projects - the natural fit for Kotlin codebases
- Centralize dependency versions in `gradle/libs.versions.toml`
- Enable parallel execution and build cache by default
- Use convention plugins instead of `allprojects {}` / `subprojects {}`
- Apply Spring Boot plugin only to application modules, never library modules
- Minimize `api()` dependency scope - prefer `implementation()`
- Commit Gradle wrapper files (`gradlew`, `gradle-wrapper.jar`) to version control
- Always configure `kotlin("plugin.spring")` for projects using `@Component` / `@Service` / `@Configuration` / `@Transactional`
- Always configure `kotlin("plugin.jpa")` for projects with JPA `@Entity` / `@Embeddable` / `@MappedSuperclass`

## Patterns

### Required Kotlin Compiler Plugins

Kotlin classes are `final` by default and have no no-arg constructors. JPA and Spring proxies require both. These plugins fix it at compile time:

```kotlin
// build.gradle.kts
plugins {
    kotlin("jvm") version "..."
    kotlin("plugin.spring") version "..."   // opens @Component, @Service, @Configuration, @Transactional, etc.
    kotlin("plugin.jpa") version "..."      // generates no-arg constructors for @Entity, @Embeddable, @MappedSuperclass
    id("org.springframework.boot") version "..."
    id("io.spring.dependency-management") version "..."
}

// Optional: extend allopen for custom annotations
allOpen {
    annotation("jakarta.persistence.Entity")
    annotation("jakarta.persistence.MappedSuperclass")
    annotation("jakarta.persistence.Embeddable")
}
```

Without `kotlin-jpa`: `org.hibernate.InstantiationException: No default constructor for entity`
Without `kotlin-spring`: `BeanNotOfRequiredTypeException` or `could not initialize proxy` on `@Transactional` classes.

### Version Catalog

Define `gradle/libs.versions.toml`:

```toml
[versions]
kotlin = "2.0.21"
spring-boot = "3.5.0"
java = "21"
mockk = "1.13.13"
kotest = "5.9.1"
springmockk = "4.0.2"
testcontainers = "1.20.4"

[libraries]
spring-boot-starter-web = { module = "org.springframework.boot:spring-boot-starter-web" }
spring-boot-starter-data-jpa = { module = "org.springframework.boot:spring-boot-starter-data-jpa" }
spring-boot-starter-test = { module = "org.springframework.boot:spring-boot-starter-test" }
spring-boot-starter-actuator = { module = "org.springframework.boot:spring-boot-starter-actuator" }
jackson-module-kotlin = { module = "com.fasterxml.jackson.module:jackson-module-kotlin" }
kotlin-reflect = { module = "org.jetbrains.kotlin:kotlin-reflect" }
kotlinx-coroutines-reactor = { module = "org.jetbrains.kotlinx:kotlinx-coroutines-reactor" }
mockk = { module = "io.mockk:mockk", version.ref = "mockk" }
springmockk = { module = "com.ninja-squad:springmockk", version.ref = "springmockk" }
kotest-runner = { module = "io.kotest:kotest-runner-junit5", version.ref = "kotest" }
kotest-assertions = { module = "io.kotest:kotest-assertions-core", version.ref = "kotest" }
testcontainers-postgresql = { module = "org.testcontainers:postgresql", version.ref = "testcontainers" }
turbine = { module = "app.cash.turbine:turbine", version = "1.2.0" }

[plugins]
kotlin-jvm = { id = "org.jetbrains.kotlin.jvm", version.ref = "kotlin" }
kotlin-spring = { id = "org.jetbrains.kotlin.plugin.spring", version.ref = "kotlin" }
kotlin-jpa = { id = "org.jetbrains.kotlin.plugin.jpa", version.ref = "kotlin" }
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
spring-dependency-management = { id = "io.spring.dependency-management", version = "1.1.7" }
```

Usage in `build.gradle.kts`:

```kotlin
plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kotlin.spring)
    alias(libs.plugins.kotlin.jpa)
    alias(libs.plugins.spring.boot)
    alias(libs.plugins.spring.dependency.management)
}

dependencies {
    implementation(libs.spring.boot.starter.web)
    implementation(libs.spring.boot.starter.data.jpa)
    implementation(libs.jackson.module.kotlin)
    implementation(libs.kotlin.reflect)
    implementation(libs.kotlinx.coroutines.reactor)

    testImplementation(libs.spring.boot.starter.test) {
        exclude(module = "mockito-core") // springmockk replaces Mockito
    }
    testImplementation(libs.mockk)
    testImplementation(libs.springmockk)
    testImplementation(libs.kotest.runner)
    testImplementation(libs.kotest.assertions)
    testImplementation(libs.testcontainers.postgresql)
}
```

### Build Performance

Configure `gradle.properties`:

```properties
org.gradle.parallel=true
org.gradle.caching=true
org.gradle.configuration-cache=true
org.gradle.configuration-cache.problems=warn
org.gradle.daemon.idletimeout=600000
org.gradle.jvmargs=-Xmx2g -XX:+UseG1GC

# Kotlin daemon JVM args
kotlin.daemon.jvmargs=-Xmx2g
```

### Multi-Module Structure

Root `settings.gradle.kts`:

```kotlin
rootProject.name = "my-app"

include("app", "domain", "infrastructure")

includeBuild("build-logic")
```

Convention plugin in `build-logic/src/main/kotlin/kotlin-conventions.gradle.kts`:

```kotlin
plugins {
    kotlin("jvm")
}

kotlin {
    jvmToolchain(21)
    compilerOptions {
        freeCompilerArgs.addAll("-Xjsr305=strict") // strict null-safety on Java interop
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
    id("kotlin-conventions")
    alias(libs.plugins.kotlin.spring)
    alias(libs.plugins.kotlin.jpa)
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
    id("kotlin-conventions")
    `java-library`
}

// No Spring Boot plugin - this is a library module
dependencies {
    api(libs.spring.boot.starter.data.jpa) // api() only when types leak into public API
    implementation(libs.kotlinx.coroutines.reactor)
}
```

### api() vs implementation() Scope

| Scope              | When to Use                                                  |
| ------------------ | ------------------------------------------------------------ |
| `implementation()` | Default - dependency is internal to the module               |
| `api()`            | Only when dependency types appear in the module's public API |

### Spring Boot-Specific Configuration

Boot JAR with layered JARs for Docker:

```kotlin
tasks.bootJar {
    mainClass.set("com.example.ApplicationKt")
    layered { enabled.set(true) }
}
```

GraalVM native image support:

```kotlin
tasks.processAot { enabled = true }
tasks.processTestAot { enabled = true }
```

### Dependency Management

BOM import via `platform()`:

```kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:3.5.0"))
}
```

Strict dependency resolution:

```kotlin
configurations.all {
    resolutionStrategy { failOnVersionConflict() }
}
```

Dependency locking for reproducible builds:

```kotlin
dependencyLocking { lockAllConfigurations() }
// Generate: ./gradlew dependencies --write-locks
```

### Detekt and Ktlint Wiring

```kotlin
plugins {
    id("io.gitlab.arturbosch.detekt") version "1.23.7"
    id("org.jlleitschuh.gradle.ktlint") version "12.1.1"
}

detekt {
    config.setFrom("$rootDir/config/detekt/detekt.yml")
    buildUponDefaultConfig = true
}
```

CI gate:

```bash
./gradlew detekt ktlintCheck check --parallel --build-cache --no-daemon
```

### CI/CD Optimization

Recommended CI build command:

```bash
./gradlew build --parallel --build-cache --no-daemon
```

Pipeline stage separation:

```bash
./gradlew check --parallel --build-cache --no-daemon       # compile + unit + detekt
./gradlew integrationTest --parallel --build-cache --no-daemon
```

CI cache directories:

```yaml
- uses: actions/cache@v4
  with:
    path: |
      ~/.gradle/caches
      ~/.gradle/wrapper
    key: gradle-${{ hashFiles('**/*.gradle.kts', 'gradle/libs.versions.toml') }}
```

Use `--no-daemon` in CI - daemon wastes memory in ephemeral runners.

## Output Format

```
Optimization: {version catalog | build cache | configuration cache | parallel | convention plugin | dependency scope | kotlin-spring/jpa plugin}
File: {file path}
Change: {description}
Impact: {build time | dependency management | maintainability | proxy correctness}
```

## Avoid

- Groovy DSL (`.gradle`) for new Kotlin projects - use Kotlin DSL (`.gradle.kts`)
- `allprojects {}` / `subprojects {}` blocks - use convention plugins in `build-logic/`
- Manual `open` modifiers on `@Entity` / `@Service` / `@Component` classes - use `kotlin("plugin.spring")` and `kotlin("plugin.jpa")`
- Force-resolving all configurations at configuration time - delays build startup
- Publishing internal modules as JARs when `project()` dependency suffices
- Applying Spring Boot plugin to library modules - only application modules need `bootJar`
- Using `api()` by default - prefer `implementation()`, use `api()` only for public API types
- Running CI builds with Gradle daemon - use `--no-daemon` for ephemeral runners
- Hardcoding dependency versions in `build.gradle.kts` - centralize in version catalog
- Forgetting to exclude `mockito-core` when using `springmockk` - the test runtime ends up with both
