# Code Review — Factory Control Bot v2.0

**Reviewer**: O3 (OpenAI) via zen MCP
**Date**: 2026-02-21
**Scope**: Provider layer, orchestrator core, services
**Files Reviewed**: 8 files (registry.py, fallback_chain.py, clink_adapter.py, state_machine.py, quality_gate.py, information_barrier.py, factory_orchestrator.py, model_router.py)

---

## Issue #1 [HIGH] — Missing Advisory Locks on State Transitions

**File**: `app/services/factory_orchestrator.py`
**Lines**: 307-335 (`_transition_phase`)

The orchestrator reads state in one session, validates the transition, then writes in another session. No `pg_try_advisory_lock()` is used, violating the spec requirement for serialized concurrent access. Two concurrent calls to `advance_phase()` for the same run could both read RUNNING and both try to transition.

**Fix**: Wrap state reads + writes in a single session with `SELECT ... FOR UPDATE` or use advisory locks per run_id.

---

## Issue #2 [MEDIUM] — Recursive Phase Advance Could Overflow Stack

**File**: `app/services/factory_orchestrator.py`
**Line**: 393 (`_move_to_next_phase`)

After a phase PASSES, `_move_to_next_phase` calls `advance_phase()` recursively if the next phase is ungated. Since phases 0, 2, 4, 5, 6 are all ungated, a chain of 5 fast ungated phases creates a 5-deep recursive call stack. While unlikely to overflow Python's default 1000-frame limit, it's fragile.

**Fix**: Replace recursion with a `while` loop in `advance_phase`.

---

## Issue #3 [MEDIUM] — Non-Atomic DB Operations in handle_gate_result

**File**: `app/services/factory_orchestrator.py`
**Lines**: 191-265

`handle_gate_result` performs: (1) read state, (2) update scores, (3) transition phase, (4) possibly update retry count — each in separate DB sessions. If the process crashes between steps, state becomes inconsistent.

**Fix**: Use a single session with explicit transaction for all operations.

---

## Issue #4 [MEDIUM] — Provider API Keys Not Validated During Init

**File**: `app/providers/registry.py`
**Method**: `initialize()`

Providers are registered if their API key env var is non-empty, but no health check or key validation is performed. A provider with an invalid key will be registered as "enabled" and only fail at first request.

**Fix**: Run a lightweight health check during `initialize()` or at least catch first-call errors gracefully.

---

## Issue #5 [MEDIUM] — Clink Adapter Subprocess Content Handling

**File**: `app/providers/clink_adapter.py`
**Method**: `chat_completion()`

Message content is passed to CLI tools via stdin. While stdin is generally safe from command injection, the content formatting should ensure no control characters or escape sequences could affect the CLI tool's behavior.

**Fix**: Sanitize message content before passing to subprocess stdin.

---

## Issue #6 [LOW] — ProviderRegistry Missing `__contains__` Method

**File**: `app/services/model_router.py`
**Line**: 265

Uses `preferred_provider in self._registry` but ProviderRegistry doesn't implement `__contains__`. This will raise a TypeError at runtime.

**Fix**: Add `__contains__` to ProviderRegistry or use `self._registry.get_provider()` with try/except.

---

## Issue #7 [LOW] — CircuitBreaker Memory Leak

**File**: `app/providers/fallback_chain.py`
**Class**: `CircuitBreaker`

`_failures` dict entries for recovered providers are never removed. Over time with many providers, this dict grows. Not a critical issue since the number of providers is bounded.

**Fix**: Clear `_failures[provider]` in `record_success()` (already done, but `_open_until` cleanup only happens on next `is_open()` check).

---

## Issue #8 [LOW] — Model Router Registry Access Pattern

**File**: `app/services/model_router.py`
**Lines**: 265, 281, 293

Multiple uses of `provider in self._registry` which depends on `__contains__` existing on the registry.

**Fix**: Use a dedicated `has_provider()` method or try/except.

---

## Summary

| Severity | Count |
|----------|-------|
| HIGH | 1 |
| MEDIUM | 4 |
| LOW | 3 |
| **Total** | **8** |
