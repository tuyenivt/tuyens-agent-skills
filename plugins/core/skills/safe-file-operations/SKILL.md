---
name: safe-file-operations
description: Cross-platform shell operations - always use Unix/bash commands, never Windows commands
metadata:
  category: ops
  tags: [file-operations, git, cross-platform, bash, safety, shell]
user-invocable: false
---

# Safe File & Shell Operations

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Running ANY shell command (file operations, build tools, scripts, etc.)
- Removing, moving, or renaming files in a git repository
- Running build tools (Gradle, Maven, npm, etc.)
- Executing project scripts or developer tools
- Performing any operation that needs to work across Git Bash (Windows), macOS, and Linux

## Golden Rule

> **Always use Unix/Linux bash commands. Never use Windows-specific commands.**
>
> Most developers use bash or Git Bash. Git Bash is the common denominator across all platforms. Every command you run must work in a standard bash shell.

## Rules

### Never Use Windows Commands

- **Never** use `cmd /c`, `cmd.exe`, or `cmd /k` to run commands
- **Never** use PowerShell commands (`Remove-Item`, `Get-Content`, `New-Item`, `Move-Item`, `Get-ChildItem`, `Set-Location`, `Write-Output`)
- **Never** use `.\script.bat` or `.\script.ps1` - use `./script.sh` or the Unix equivalent
- **Never** use backslash `\` as path separator in commands - use forward slash `/`
- **Never** use `type` (Windows) to display file content - use `cat`
- **Never** use `dir` - use `ls`
- **Never** use `del` - use `rm` or `git rm`
- **Never** use `md` - use `mkdir -p`
- **Never** use `move` - use `mv` or `git mv`
- **Never** use `copy` - use `cp`
- **Never** use `cls` - use `clear`
- **Never** use `set VAR=value` (Windows syntax) - use `export VAR=value`

### Build Tools

- **Gradle**: Use `./gradlew` (Unix wrapper), never `.\gradlew.bat` or `gradlew.bat`
- **Maven**: Use `./mvnw` (Unix wrapper), never `.\mvnw.cmd` or `mvnw.cmd`
- **npm/pnpm/yarn**: These work the same everywhere, just use them directly
- **Scripts**: Use `./script.sh`, never `.\script.bat` or `.\script.ps1`

### File Operations

- **Always prefer `git rm`** over `rm`, `del`, or `Remove-Item` for tracked files
- `git rm` works cross-platform and stages the deletion automatically
- For untracked files, use `rm` (POSIX) - works in Git Bash on Windows
- **Always prefer `git mv`** over `mv`, `move`, or `Move-Item`
- `git mv` preserves git history and stages the change automatically
- Use `mkdir -p` for creating nested directories (works in Git Bash)

### Checking Before Deleting

- Use `git clean -n` (dry-run) to preview what would be deleted
- Use `git status` to review staged/unstaged changes before operations

## Pattern

Bad - Windows-specific commands:

```bash
# Windows cmd/PowerShell - won't work in Git Bash or Linux/macOS
cmd /c gradlew.bat bootRun
.\gradlew.bat test
.\mvnw.cmd clean install
del src/old-file.java
Remove-Item src/old-file.java
move src/old.java src/new.java
md -Force src/new-folder
type README.md
dir src/
copy file1.txt file2.txt
set JAVA_HOME=C:\jdk
```

Good - Unix/bash commands (work everywhere including Git Bash):

```bash
# Build tools - always use Unix wrappers
./gradlew bootRun
./gradlew test
./mvnw clean install
npm run build

# File operations
rm src/temp-file.txt
cat README.md
ls -la src/
cp file1.txt file2.txt
export JAVA_HOME=/c/jdk

# Remove tracked files (stages deletion automatically)
git rm src/old-file.java
git rm -r src/old-folder/

# Remove tracked files but keep in working directory
git rm --cached src/file-to-untrack.java

# Move/rename files (preserves history)
git mv src/OldName.java src/NewName.java
git mv src/old-folder/ src/new-folder/

# Preview what git clean would delete (safe dry-run)
git clean -n

# Remove untracked files (after reviewing with -n)
git clean -f

# Create directories (cross-platform)
mkdir -p src/main/java/com/example/service
```

Good - Safe deletion workflow:

```bash
# 1. Check status first
git status

# 2. For tracked files - use git rm
git rm src/deprecated-service.java

# 3. For untracked files - preview first, then remove
git clean -n  # See what would be deleted
git clean -f  # Actually delete (after confirming)

# 4. Verify the result
git status
```

## Command Reference

| Operation             | Use This            | NOT This                              |
| --------------------- | ------------------- | ------------------------------------- |
| Run Gradle            | `./gradlew task`    | `.\gradlew.bat`, `cmd /c gradlew`     |
| Run Maven             | `./mvnw goal`       | `.\mvnw.cmd`, `cmd /c mvnw`           |
| Run script            | `./script.sh`       | `.\script.bat`, `.\script.ps1`        |
| Delete tracked file   | `git rm file`       | `rm`, `del`, `Remove-Item`            |
| Delete untracked file | `rm file`           | `del`, `Remove-Item`                  |
| Move/rename file      | `git mv old new`    | `move`, `Move-Item`                   |
| Create directory      | `mkdir -p dir`      | `md`, `New-Item`                      |
| Preview deletions     | `git clean -n`      | -                                     |
| List files            | `ls -la`            | `dir`, `Get-ChildItem`                |
| Show file content     | `cat file`          | `type`, `Get-Content`                 |
| Copy file             | `cp src dest`       | `copy`, `Copy-Item`                   |
| Set env variable      | `export VAR=value`  | `set VAR=value`, `$env:VAR = "value"` |
| Path separator        | `/` (forward slash) | `\` (backslash)                       |

## Avoid

- `cmd /c`, `cmd.exe`, `cmd /k` - Windows command prompt
- `powershell`, `pwsh` - PowerShell execution
- `.\file.bat`, `.\file.ps1` - Windows script execution
- `del`, `Remove-Item`, `move`, `Move-Item`, `md`, `New-Item` - Windows/PowerShell commands
- `.\gradlew.bat`, `.\mvnw.cmd` - Windows build tool wrappers
- `type`, `dir`, `copy`, `cls`, `set` - Windows cmd builtins
- `rm` on tracked files without using `git rm` - loses git tracking
- `git clean -f` without first running `git clean -n` - may delete wanted files
- Backslash `\` as path separator in commands
- Any command that doesn't work in a standard bash shell
