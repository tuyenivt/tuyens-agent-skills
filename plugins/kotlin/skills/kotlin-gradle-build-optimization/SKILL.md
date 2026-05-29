---
name: kotlin-gradle-build-optimization
description: Gradle Kotlin DSL build optimization for Spring Boot: version catalogs, build/config cache, parallel execution, kotlin-jpa/spring/allopen plugins.
metadata:
  category: backend
  tags: [kotlin, gradle, build, spring-boot, multi-module, performance]
user-invocable: false
---

# Kotlin Gradle Build Optimization

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Setting up a new Kotlin / Spring Boot Gradle project or migrating from Maven
- Optimizing slow Gradle builds
- Structuring multi-module Kotlin projects
- Diagnosing JPA / Spring proxy issues caused by missing compiler plugins

## Rules

- Kotlin DSL (`.gradle.kts`) for new projects.
- Centralize versions in `gradle/libs.versions.toml`.
- Parallel execution + build cache on by default.
- Convention plugins in `build-logic/`, not `allprojects {}` / `subprojects {}`.
- Spring Boot plugin only on application modules.
- `implementation()` by default. `api()` only when types appear in the public API.
- `kotlin("plugin.spring")` for projects using `@Component` / `@Service` / `@Configuration` / `@Transactional`.
- `kotlin("plugin.jpa")` for projects with JPA `@Entity` / `@Embeddable` / `@MappedSuperclass`.
- Exclude `mockito-core` from `spring-boot-starter-test` when using springmockk.

## Patterns

### Required Kotlin compiler plugins

Kotlin classes are `final` by default with no no-arg constructors. JPA and Spring proxies need both:

```kotlin
plugins {
    kotlin("plugin.spring")   // opens @Component / @Service / @Configuration / @Transactional
    kotlin("plugin.jpa")      // no-arg constructors for @Entity / @Embeddable / @MappedSuperclass
}
```

Missing - symptoms: `No default constructor for entity` (JPA), `BeanNotOfRequiredTypeException` / `could not initialize proxy` on `@Transactional` (Spring AOP).

### Version catalog

`gradle/libs.versions.toml`:

```toml
[versions]
kotlin = "2.0.21"
spring-boot = "3.5.0"
mockk = "1.13.13"
kotest = "5.9.1"
springmockk = "4.0.2"
testcontainers = "1.20.4"

[libraries]
spring-boot-starter-web = { module = "org.springframework.boot:spring-boot-starter-web" }
spring-boot-starter-data-jpa = { module = "org.springframework.boot:spring-boot-starter-data-jpa" }
spring-boot-starter-test = { module = "org.springframework.boot:spring-boot-starter-test" }
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
```

Usage:

```kotlin
plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kotlin.spring)
    alias(libs.plugins.kotlin.jpa)
    alias(libs.plugins.spring.boot)
}

dependencies {
    implementation(libs.spring.boot.starter.web)
    implementation(libs.jackson.module.kotlin)
    implementation(libs.kotlin.reflect)

    testImplementation(libs.spring.boot.starter.test) {
        exclude(module = "mockito-core")     // springmockk replaces Mockito
    }
    testImplementation(libs.mockk)
    testImplementation(libs.springmockk)
}
```

### Diagnose slow builds

```bash
./gradlew build --scan        # task durations, cache hit rate, dependency timings
./gradlew build --profile     # local HTML at build/reports/profile/
```

Read the scan's Performance tab first. Common findings: low cache hit rate (no remote cache), `compileKotlin` dominates (incremental off), test forks per class.

### Build performance

```properties
# gradle.properties
org.gradle.parallel=true
org.gradle.caching=true
org.gradle.configuration-cache=true
org.gradle.daemon.idletimeout=600000
org.gradle.jvmargs=-Xmx2g -XX:+UseG1GC
kotlin.daemon.jvmargs=-Xmx2g
```

### Multi-module

```kotlin
// settings.gradle.kts
rootProject.name = "my-app"
include("app", "domain", "infrastructure")
includeBuild("build-logic")
```

Convention plugin `build-logic/src/main/kotlin/kotlin-conventions.gradle.kts`:

```kotlin
plugins { kotlin("jvm") }

kotlin {
    jvmToolchain(21)
    compilerOptions { freeCompilerArgs.addAll("-Xjsr305=strict") }
}

tasks.withType<Test> {
    useJUnitPlatform()
    maxParallelForks = (Runtime.getRuntime().availableProcessors() / 2).coerceAtLeast(1)
}
```

Application module:

```kotlin
plugins {
    id("kotlin-conventions")
    alias(libs.plugins.kotlin.spring)
    alias(libs.plugins.kotlin.jpa)
    alias(libs.plugins.spring.boot)
}
dependencies { implementation(project(":domain")) }
```

Library module:

```kotlin
plugins { id("kotlin-conventions"); `java-library` }
// No Spring Boot plugin - libraries don't produce bootJar
dependencies {
    api(libs.spring.boot.starter.data.jpa)      // api() only when types leak into public API
    implementation(libs.kotlinx.coroutines.reactor)
}
```

### Boot JAR with layers

```kotlin
tasks.bootJar {
    mainClass.set("com.example.ApplicationKt")
    layered { enabled.set(true) }
}
```

### Remote build cache

Wire in `settings.gradle.kts` for cross-machine task-output sharing:

```kotlin
buildCache {
    local { isEnabled = true }
    remote<HttpBuildCache> {
        url = uri("https://gradle-cache.example.com/cache/")
        isPush = System.getenv("CI") == "true"    // CI populates; devs only read
        credentials {
            username = providers.gradleProperty("buildCacheUser").orNull
            password = providers.gradleProperty("buildCachePass").orNull
        }
    }
}
```

5-10x speedup on cold builds hitting populated caches.

### CI + static analysis

```kotlin
plugins {
    id("io.gitlab.arturbosch.detekt") version "1.23.7"
    id("org.jlleitschuh.gradle.ktlint") version "12.1.1"
}
detekt { buildUponDefaultConfig = true; config.setFrom("$rootDir/config/detekt/detekt.yml") }
```

```bash
./gradlew detekt ktlintCheck check --parallel --build-cache --no-daemon
```

`--no-daemon` on CI - the daemon wastes memory in ephemeral runners.

## Output Format

```
Optimization: {version catalog | build cache | configuration cache | parallel | convention plugin | dependency scope | kotlin-spring/jpa plugin}
File: {path}
Change: {description}
Impact: {build time | dependency management | maintainability | proxy correctness}
```

## Avoid

- Groovy DSL for new Kotlin projects
- `allprojects {}` / `subprojects {}` - use convention plugins
- Manual `open` on `@Entity` / `@Service` - use the Gradle plugins
- Applying Spring Boot plugin to library modules
- Default `api()` - prefer `implementation()`
- CI builds with the Gradle daemon
- Hardcoded versions in `build.gradle.kts`
- `mockito-core` and `springmockk` both on the test classpath
