---
name: go-migration-safety
description: "Safe migration patterns with golang-migrate and PostgreSQL. File naming, up/down pairs, zero-downtime DDL, embedding in Go binary, CI validation. Never use GORM AutoMigrate in production."
user-invocable: false
---

Cover: golang-migrate file naming ({version}\_{desc}.up.sql/.down.sql),
every up has matching down, zero-downtime DDL (same rules as foundation),
CLI usage, embedding with embed package, CI validation (up→down→up),
application startup migration sequencing, anti-patterns (❌ AutoMigrate,
❌ down that drops without backup, ❌ mixing DDL+DML)
