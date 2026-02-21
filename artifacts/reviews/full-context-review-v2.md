# Full Context Review — Factory Control Bot v2.0

**Reviewer**: Gemini 2.5 Pro (Google) via zen MCP
**Date**: 2026-02-21
**Scope**: Orchestrator phase executors (0-7), model scanner
**Files Reviewed**: 6 files (phases 1, 4, 5, 6, 7 + model_scanner.py)

---

## Issue #1 [HIGH] — Information Barrier is Logical Only

**File**: `app/orchestrator/phases/phase4_implementation.py`

The information barrier between implementer and tester is enforced only at the prompt construction level. The barrier checks what files to include in prompts but doesn't prevent file system access. Since all code lives in the same directory, any phase executor with file access could read any file.

**Impact**: The barrier is effective for LLM-based agents (they only see what's in their prompt), but not for any direct file operations within the phase executor.

**Fix**: For the current architecture (LLM agents via API), this is acceptable. Document that the barrier is prompt-level, not OS-level. For higher assurance, consider separate Docker containers per role.

---

## Issue #2 [HIGH] — Fix Cycle Hash Collision Could Trigger Premature Escalation

**File**: `app/orchestrator/phases/phase6_testing.py`

The fix cycle detects repeated failures by hashing error output. If different test failures produce similar error messages (e.g., "AssertionError: expected True"), they hash identically, causing the "same failure 3 times" detector to escalate prematurely.

**Fix**: Include the test file name and line number in the hash, not just the error message.

---

## Issue #3 [MEDIUM] — Git Merge in Phase 7 Has No Conflict Recovery

**File**: `app/orchestrator/phases/phase7_release.py`

The git merge from dev to main is done via subprocess. If merge conflicts occur, the subprocess fails and the exception propagates, leaving the repository in a conflicted state on the main branch.

**Fix**: Add conflict detection and automatic abort: `git merge --abort` on failure. Log the conflict details for manual resolution.

---

## Issue #4 [MEDIUM] — Phase 5 Silently Truncates Code Beyond Budget

**File**: `app/orchestrator/phases/phase5_review.py`

The review phase collects all source files into a prompt string with a ~200K character budget. If the codebase exceeds this limit, files are silently dropped. The reviewer has no indication that it's reviewing an incomplete codebase.

**Fix**: Log which files were included/excluded. Add a header note to the review prompt: "Note: {N} files were excluded due to context limits."

---

## Issue #5 [MEDIUM] — Fragile Clarification Detection

**File**: `app/orchestrator/phases/phase1_requirements.py`

Clarification detection uses `word_count < 50` as a heuristic. A short but complete specification (e.g., "Build a CLI that prints hello world") would be incorrectly flagged as needing clarification.

**Fix**: Use a more nuanced heuristic: check for the presence of key spec sections (user roles, data entities, endpoints) rather than raw word count.

---

## Issue #6 [MEDIUM] — Model Scanner Probe Doesn't Validate Response Quality

**File**: `app/services/model_scanner.py`
**Method**: `probe_model()`

The probe sends a test completion and checks for a non-error response, but doesn't validate the response content. A model that returns empty or garbage content would get a passing probe score.

**Fix**: Add a basic content validation (e.g., response must contain at least 5 words, or match an expected pattern for the test prompt).

---

## Issue #7 [LOW] — LLM Output Parsing Silently Fails

**File**: `app/orchestrator/phases/phase4_implementation.py`
**Method**: `_write_code_files()`

Parses `### FILE: <path>` markers from LLM output. If the LLM doesn't follow this format, no files are written but no error or warning is raised.

**Fix**: Log a warning if no files were extracted from the LLM output.

---

## Issue #8 [LOW] — deploy.sh Fence Stripping Could Corrupt

**File**: `app/orchestrator/phases/phase7_release.py`

The deploy.sh content is extracted by stripping markdown fences. If the LLM includes nested code fences within the script, the stripping logic could produce a corrupted script.

**Fix**: Use a more robust extraction: find the first ` ```bash ` or ` ```sh ` fence and extract until its closing fence.

---

## Issue #9 [LOW] — asyncio.gather Doesn't Handle Partial Failures

**File**: `app/orchestrator/phases/phase2_brainstorm.py`

`asyncio.gather()` for concurrent model calls doesn't use `return_exceptions=True`. If one model times out, the entire brainstorm phase fails.

**Fix**: Add `return_exceptions=True` and filter out exceptions from the results.

---

## Summary

| Severity | Count |
|----------|-------|
| HIGH | 2 |
| MEDIUM | 4 |
| LOW | 3 |
| **Total** | **9** |
