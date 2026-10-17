---
name: code-review
description: Review a code change (a diff, a patch file, or uncommitted changes) for bugs, security issues, and missing tests, and give a clear verdict. Use when the user asks to review, check, or look over code changes, a diff, a patch, or a pull request.
---

# Code review

Review the change the user points you at. Read the diff first, then read the surrounding code it touches so you understand the context, not just the changed lines.

## What to look for, in priority order

1. Security: injection (SQL, shell, path), secrets in code, missing authorization checks, unsafe deserialization.
2. Correctness: logic errors, off-by-one, wrong error handling, race conditions, unhandled None or null, broken edge cases.
3. Tests: behavior changes without a matching test change, tests that do not exercise the new path.
4. Maintainability: only mention it if it clearly hurts, such as duplicated logic or misleading names. Do not comment on formatting or style.

Do not invent problems. If the change is sound, say so. A review that flags nothing is a valid review.

## Output format

Use exactly this structure:

```
## Findings

- [BLOCKER] path/to/file.py:42 - one sentence on what is wrong and why it matters
- [MAJOR] path/to/file.py:57 - ...
- [MINOR] path/to/file.py:10 - ...

## Verdict: REQUEST CHANGES
```

Rules:

- Each finding is one bullet with a severity tag, a file path with a line number from the diff, and one or two sentences. Suggest a fix in the same bullet when it is short.
- Severity: BLOCKER for security issues and bugs that break the feature. MAJOR for bugs on edge cases or missing tests for changed behavior. MINOR for everything else worth mentioning.
- If there are no findings, write `No findings.` under Findings.
- The last line is always `## Verdict: APPROVE` or `## Verdict: REQUEST CHANGES`. Any BLOCKER or MAJOR finding means REQUEST CHANGES.
