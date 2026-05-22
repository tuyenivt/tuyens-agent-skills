---
name: java-gradle-build-optimization
description: "Gradle for Spring Boot multi-module: Kotlin DSL, version catalog, build cache, configuration cache, convention plugins, scope hygiene."
metadata:
  category: backend
  tags: [gradle, build, spring-boot, multi-module, performance]
user-invocable: false
---

# Gradle Build Optimization

> Load `Use skill: stack-detect` first to determine the project stack. If the build tool is Maven, stop and use a Maven-focused skill.

## When to Use

- New Spring Boot Gradle project / migration from Maven
- Optimizing slow Gradle builds (local or CI)
- Multi-module structure with shared conventions
- Standardizing dependency versions
- Resolving Boot-managed version conflicts via BOM / `platform()`

## Rules

- Kotlin DSL (`.gradle.kts`) for new projects
- All dependency versions in `gradle/libs.versions.toml`
- Parallel + build cache on by default
- Convention plugins in `build-logic/` - never `allprojects {}` / `subprojects {}`
- Spring Boot plugin only on application modules
- `implementation()` by default; `api()` only when types appear in the module's public API
- Commit `gradlew` / `gradle-wrapper.jar`
- CI uses `--no-daemon` (ephemeral runners)

## Patterns

### Version catalog

`gradle/libs.versions.toml`:

```toml
[versions]
spring-boot = "3.5.0"
java = "21"

[libraries]
spring-boot-starter-web = { module = "org.springframework.boot:spring-boot-starter-web" }
spring-boot-starter-data-jpa = { module = "org.springframework.boot:spring-boot-starter-data-jpa" }
spring-boot-starter-test = { module = "org.springframework.boot:spring-boot-starter-test" }

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
spring-dependency-management = { id = "io.spring.dependency-management", version = "1.1.7" }
```

```kotlin
dependencies {
    implementation(libs.spring.boot.starter.web)
    testImplementation(libs.spring.boot.starter.test)
}
```

### `gradle.properties` for build speed

```properties
org.gradle.parallel=true
org.gradle.caching=true
org.gradle.configuration-cache=true
# Some Spring Boot / JPA plugins are not configuration-cache compatible.
# Start with problems=warn; flip to fail once the build is green.
org.gradle.configuration-cache.problems=warn
org.gradle.daemon.idletimeout=600000
org.gradle.jvmargs=-Xmx2g -XX:+UseG1GC
```

### Multi-module via convention plugin

`build-logic/src/main/kotlin/java-conventions.gradle.kts`:

```kotlin
plugins { java }

java { toolchain { languageVersion.set(JavaLanguageVersion.of(21)) } }

tasks.withType<Test> {
    useJUnitPlatform()
    maxParallelForks = (Runtime.getRuntime().availableProcessors() / 2).coerceAtLeast(1)
    jvmArgs("-Djdk.virtualThreadScheduler.parallelism=4")
}
```

Application module:

```kotlin
plugins {
    id("java-conventions")
    alias(libs.plugins.spring.boot)
    alias(libs.plugins.spring.dependency.management)
}
dependencies {
    implementation(project(":domain"))
    implementation(libs.spring.boot.starter.web)
}
```

Library module - no Spring Boot plugin (it would produce an unwanted `bootJar`):

```kotlin
plugins {
    id("java-conventions")
    `java-library`
}
dependencies {
    api(libs.spring.boot.starter.data.jpa)         // types leak into public API
    implementation(libs.spring.boot.starter.web)   // internal use only
}
```

### `api()` vs `implementation()`

```kotlin
// Bad - leaks transitive types
api(project(":infrastructure"))

// Good - only this module sees infrastructure types
implementation(project(":infrastructure"))
```

### Dependency management

```kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:3.5.0"))
}

configurations.all {
    resolutionStrategy { failOnVersionConflict() }
}

dependencyLocking { lockAllConfigurations() }
// ./gradlew dependencies --write-locks
```

### Spring Boot specifics

```kotlin
tasks.bootJar {
    mainClass.set("com.example.Application")
    layered { enabled.set(true) }
}

// GraalVM native
tasks.processAot { enabled = true }
tasks.processTestAot { enabled = true }
```

### CI

```bash
./gradlew check --parallel --build-cache --no-daemon                # compile + unit
./gradlew integrationTest --parallel --build-cache --no-daemon      # integration
```

GitHub Actions cache:

```yaml
- uses: actions/cache@v4
  with:
    path: |
      ~/.gradle/caches
      ~/.gradle/wrapper
    key: gradle-${{ hashFiles('**/*.gradle.kts', 'gradle/libs.versions.toml') }}
```

## Output Format

```
Optimization: {version-catalog | build-cache | configuration-cache | parallel | convention-plugin | scope | bom-platform | locking | layered-jar | ci-cache}
File: {repo path}
Change: {one-line diff}
Priority: {High | Medium | Low}
Effort: {Trivial | Small | Medium | Large}
Expected Impact: {clean delta | incremental delta | maintainability}
Risk: {None | Plugin-incompat | Behavior-change}
```

Aggregate: `Aggregate: estimated total clean-build reduction (%)`.

## Avoid

- Groovy DSL for new projects
- `allprojects {}` / `subprojects {}` blocks
- Spring Boot plugin on library modules
- `api()` by default
- Hardcoded versions in `build.gradle.kts`
- Gradle daemon in CI
