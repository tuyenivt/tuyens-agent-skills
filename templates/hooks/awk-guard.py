#!/usr/bin/env python
"""PreToolUse guard for awk inside Bash commands.

Prompt hooks cannot approve anything - they return only {ok, reason}, where ok:false blocks and ok:true merely declines to block.
Only a command hook can emit permissionDecision:"allow", which is the one thing that skips the prompt. So the awk gate has to be a command hook.

Decision table:
  deny    the awk program can execute a command or rewrite files in place
  allow   awk is present and EVERY segment of the command is a read-only reader
  silent  anything else - exit 0 and defer to the normal permission rules

A hook "allow" is terminal for the WHOLE Bash call, not just the awk fragment, so the allow branch validates every segment.
Every whitelisted head except awk is already covered by a Bash(...) allow rule in the shipped settings, so the only permission this hook widens is awk itself.
"""

import json
import re
import sys

AWK = {"awk", "gawk", "mawk", "nawk"}

READ_ONLY = AWK | {
    "cat", "head", "tail", "wc", "ls", "tree", "pwd", "find", "file",
    "grep", "egrep", "fgrep", "sed", "cut", "tr", "sort", "uniq", "nl",
    "echo", "printf", "basename", "dirname", "realpath", "which",
    "date", "diff", "comm", "jq", "yq", "git", "true", ":",
}

GIT_READ = {
    "log", "status", "diff", "show", "blame", "ls-files", "ls-tree",
    "check-ignore", "rev-parse", "rev-list", "shortlog", "cat-file", "describe",
}

FIND_WRITE = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fls",
              "-fprint", "-fprint0", "-fprintf"}

HARD_DENY = [
    (re.compile(r"\bsystem\s*\("), "awk system() executes a shell command"),
    (re.compile(r"\|\s*&?\s*getline"), "awk getline reads from a command pipeline"),
    (re.compile(r"(?:^|\s)-i\s+inplace\b|--include\s*=\s*inplace\b"),
     "gawk -i inplace rewrites files in place"),
]

# Constructs that are not provably safe: fall through to the ask rule.
SOFT = [
    re.compile(r"\bgetline\s*<"),
    re.compile(r"\bclose\s*\("),
    re.compile(r"\bENVIRON\b"),
    re.compile(r"/dev/(?:stdout|stderr|fd)\b"),
    re.compile(r"(?:^|\s)-f[\s=]"),      # program body lives in a file we cannot read
]

PRINT = re.compile(r"\bprintf?\b")
SED_WRITE = re.compile(r"(?:^|[;}/])\s*w\s|/[a-zA-Z0-9]*w(?:\s|$|;|})")


def split_command(cmd):
    """Split on shell operators outside quotes.

    Returns a list of segments (each a list of raw words), or None when the
    command contains a redirection, subshell, or substitution - none of which
    this hook is willing to reason about.
    """
    segs, cur, word = [], [], ""
    quote = None
    i, n = 0, len(cmd)
    while i < n:
        c = cmd[i]
        if quote:
            word += c
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "'\"":
            quote = c
            word += c
            i += 1
            continue
        if c == "`" or (c == "$" and i + 1 < n and cmd[i + 1] == "("):
            return None
        if c in "<>()":
            return None
        if c in ";&|\n":
            if word:
                cur.append(word)
                word = ""
            if cur:
                segs.append(cur)
                cur = []
            while i < n and cmd[i] in ";&|\n":
                i += 1
            continue
        if c.isspace():
            if word:
                cur.append(word)
                word = ""
            i += 1
            continue
        word += c
        i += 1
    if quote:
        return None
    if word:
        cur.append(word)
    if cur:
        segs.append(cur)
    return segs


def unquote(word):
    if len(word) >= 2 and word[0] == word[-1] and word[0] in "'\"":
        return word[1:-1]
    return word


def has_output_redirect(text):
    """True when print/printf is followed by an unparenthesised > or |.

    In awk that is output redirection; a genuine comparison inside a print
    statement has to be parenthesised, so parenthesis depth separates them.
    """
    for m in PRINT.finditer(text):
        depth = 0
        j = m.end()
        while j < len(text):
            c = text[j]
            if c == "(":
                depth += 1
            elif c == ")":
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0:
                if c in ">|":
                    return True
                if c in ";}\n":
                    break
            j += 1
    return False


def segment_is_read_only(words):
    head = unquote(words[0])
    if "=" in head and "/" not in head:
        return False                      # FOO=bar prefix assignment
    head = head.rsplit("/", 1)[-1]
    if head not in READ_ONLY:
        return False
    rest = [unquote(w) for w in words[1:]]
    if head == "git":
        return bool(rest) and rest[0] in GIT_READ
    if head == "sed":
        if any(w.startswith("-i") or w.startswith("--in-place") for w in rest):
            return False
        return not any(SED_WRITE.search(w) for w in rest)
    if head == "tail":
        return not any(
            w == "--follow" or
            (w.startswith("-") and not w.startswith("--") and "f" in w)
            for w in rest
        )
    if head == "find":
        return not any(w in FIND_WRITE for w in rest)
    return True


def emit(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if data.get("tool_name") != "Bash":
        return 0
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not cmd.strip():
        return 0

    segs = split_command(cmd)
    if segs is None:
        return 0
    heads = [unquote(s[0]).rsplit("/", 1)[-1] for s in segs if s]
    if not any(h in AWK for h in heads):
        return 0                          # not an awk command; not our business

    for pattern, reason in HARD_DENY:
        if pattern.search(cmd):
            emit("deny", "Blocked: %s. Use sed, cut, grep, sort, or the Edit "
                         "tool instead." % reason)
            return 0

    if any(p.search(cmd) for p in SOFT) or has_output_redirect(cmd):
        return 0
    if not all(segment_is_read_only(s) for s in segs if s):
        return 0

    emit("allow", "read-only awk pipeline (every segment is a reader)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
