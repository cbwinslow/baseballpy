## ADDED Requirements

### Requirement: Architecture Boundaries Are Tested
An automated test MUST enforce: only `core/http.py` imports `httpx`; sinks import no network libraries; sources import no database drivers; only `sources/retrosheet/_chadwick_adapter.py` imports `chadwickpy`; no bare `except:` or swallowing `except Exception` in `src/`.

### Requirement: No Silent Coercion
Coercion helpers MUST raise `CoercionError` on non-null unparseable input; callers MUST quarantine rather than substitute NULL silently.

### Requirement: Documented Public API
Every public module, class and function MUST have a docstring (enforced by ruff `D1`).
