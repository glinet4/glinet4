# Phase 2 — Error contract + session lifecycle (opens the 0.2.0 breaking series)

Tracking: glinet4/glinet4#14 (phase) / #19 (umbrella). Source: ~/dev/oss/GLINET4-TECHDEBT.md Phase 2, plus the Phase-1 review notes on issue #14.

## Global Constraints

- This phase MAY break: exception types raised on error paths may change, and callers catching builtins will need updates. It must NOT break: any public method name, parameter, or success-path return shape. The HA integration lockstep happens at the 0.2.0 cut (Phase 4), not now.
- Every raising path in the package must raise from the `APIClientError` hierarchy after this phase — `except APIClientError` becomes a complete safety net. Builtin exceptions may still propagate only for genuine programmer errors (e.g. `TypeError` on wrong argument types).
- Conventional commits per task; breaking commits use the `!` marker (e.g. `fix!:`) with a `BREAKING CHANGE:` footer describing exactly what a caller must change.
- Full gate green per task: `uv run pytest -q` (passes+skips only), `uvx prek run --all-files`, `uv run mypy glinet4` strict, coverage gate ≥85 (`uv run pytest -q --cov=glinet4 --cov-fail-under=85`).
- Docstrings updated wherever raised-exception types change.

## Task 1: Release-please pre-major bump config

**Files:** `release-please-config.json`.

Before any breaking commit lands on main, release-please must be told how to version 0.x breaking changes, or the first `fix!:` will propose 1.0.0.

1. Add to the "." package config: `"bump-minor-pre-major": true` (breaking → 0.2.0) and `"bump-patch-for-minor-pre-major": true` (plain feat → 0.1.x while pre-1.0).
2. Validate the file against the release-please config schema (`uvx check-jsonschema --schemafile https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json release-please-config.json`).

Commit: `chore: version 0.x breaking changes as minor bumps (release-please)`. No tests to run beyond prek + the schema check.

## Task 2: Disambiguate err_code -1 and check body-level err_code

**Files:** `glinet4/error_handling.py`, `glinet4/glinet.py` (network_acceleration_set docstring/annotation only), `tests/test_error_handling.py`.

The router answers JSON-RPC error code -1 for BOTH "not logged in" AND feature conflicts (NAT-acceleration vs Parental Control/QoS/SQM/DPI on `set_netnat_config` — see the docstring at glinet.py:246-252). `raise_for_status` (error_handling.py) maps every -1 to `TokenError`, so an HA-style "on TokenError → re-login and retry" loops forever on a feature conflict. Separately, some firmware reports errors INSIDE `result` as a body-level `err_code` key, which `raise_for_status` returns unexamined.

1. Add `FeatureConflictError(NonZeroResponse)` to the hierarchy, exported from the package (`__init__.py` imports + `__all__` — the Task-1-of-Phase-1 exports test will enforce consistency; note it only auto-checks `_types` TypedDicts, so add the exception to the exports test's expected-names logic if needed).
2. In the code -1 branch: inspect the router-supplied error message; if it matches conflict phrasing (the mt6000 conflict response message — derive the discriminator from the real captured payload; the capture file with raw values is at /home/shaunes/dev/oss/gli4py/docs/devices/mt6000_4.9.0.json on the MAIN checkout (gitignored, read-only for you) — find the `set_netnat_config`/acceleration conflict entry; if the capture lacks it, use the documented conflict semantics from glinet.py:246-252 and match on a conservative substring like "conflict" case-insensitively, with a comment naming the source of truth), raise `FeatureConflictError`; otherwise `TokenError` as today. The discriminator MUST be a module-level constant with a comment, not an inline literal.
3. After the happy-path `result` extraction: if the result body is a dict containing a non-zero `err_code`, raise `NonZeroResponse` (or `FeatureConflictError` when the message discriminator matches) instead of returning it. TDD: pin current pass-through behavior first? No — this IS the behavior change; write the new tests RED against current code, then implement.
4. Tests: conflict-message -1 → `FeatureConflictError`; plain -1 → `TokenError` (unchanged); body-level err_code non-zero → raises with the message; body-level err_code 0 or absent → returns result unchanged (regression guard for every existing getter). Assert `FeatureConflictError` is caught by `except NonZeroResponse` and `except APIClientError` (hierarchy contract).

Commit: `fix!: distinguish feature conflicts from auth failures on err_code -1` with BREAKING CHANGE footer: callers catching TokenError for conflict handling must catch FeatureConflictError; responses carrying body-level err_code now raise instead of returning.

## Task 3: Consolidate the exception taxonomy

**Files:** `glinet4/error_handling.py`, `glinet4/glinet.py`, `glinet4/_transport.py`, `tests/test_error_handling.py`, `tests/test_glinet_unit.py`.

Raising paths outside the hierarchy today: `raise_for_status` raises builtin `ConnectionError` for unexpected envelope shapes (error_handling.py, the branch Task-1-of-Phase-1 pinned); `tailscale_start`/`tailscale_stop` raise builtin `ConnectionError`/`ConnectionAbortedError` including recursion-depth exhaustion (glinet.py ~675-729); `wifi_iface_set_enabled` and `router_info` raise `ValueError`; `login` wraps both KeyError and ValueError into `KeyError("Parameter Exception:")` (_transport.py:147-152) so a hashing failure masquerades as a KeyError; `_require_firmware_version` (added in Phase 1) raises `ValueError`.

1. Add to the hierarchy: `UnexpectedResponse(APIClientError)` (envelope/shape violations) and `RetryExhausted(APIClientError)` (bounded-retry loops gave up).
2. Replace: envelope-shape `ConnectionError` → `UnexpectedResponse`; tailscale depth/status failures → `RetryExhausted` (keep the messages informative: attempts made, last status); `wifi_iface_set_enabled` unknown-iface `ValueError` → `UnexpectedResponse`; `router_info` missing-firmware `ValueError` → `UnexpectedResponse`; `_require_firmware_version` `ValueError` → `UnexpectedResponse` (update its Phase-1 tests); `login`'s wrap → let `AuthenticationError` variants pass through untouched AND stop converting hashing `ValueError` into `KeyError` — hashing/unsupported-alg failures become `UnexpectedResponse` with the original as `__cause__`. Also fix the -32000 catalog-text shadowing on the login path (issue #14 comment): login's re-raise must preserve or include the caught exception's message rather than replacing it with the generic "Authentication failed during login".
3. Export the new exception types (`__init__.py` + `__all__`).
4. Update the Phase-1 pinned tests (the ConnectionError pin comment says exactly this moment arrives) and every unit test asserting the old builtin types. Docstrings on all touched methods updated to name the new types.

Commit: `fix!: raise APIClientError subclasses everywhere (UnexpectedResponse, RetryExhausted)` with a BREAKING CHANGE footer enumerating each old→new type change.

## Task 4: Session lifecycle — close(), context manager, session injection, explicit base_url

**Files:** `glinet4/_transport.py`, `glinet4/glinet.py`, `tests/test_transport.py`, `tests/test_glinet_unit.py`, `README.md` (quickstart only).

Today `GLinetTransport.__init__` auto-creates uplink's `AiohttpClient()`; nothing exposes close, so teardown rides `__del__` (RuntimeError under a running loop, py3.12+ deprecation). The constructor takes `client: AiohttpClient | None` (leaking the uplink type into the public API) and `base_url` only via invisible `**kwargs`.

1. `GLinetTransport`: accept and store an optional `aiohttp.ClientSession`; when given, build the uplink client around it and NEVER close it (caller-owned); when not given, create the session lazily and own it. Add `async def close()` (idempotent; closes only owned sessions) and `__aenter__`/`__aexit__`.
2. `GLinet`: add explicit `base_url: str` as the FIRST constructor parameter (keep `**kwargs` passthrough working so existing `GLinet(base_url=...)` callers are unaffected — the change is additive discoverability, and positional `GLinet("http://192.168.8.1/rpc")` must now work); add `session: aiohttp.ClientSession | None = None` keyword; add `async def close()` and `__aenter__`/`__aexit__` delegating to the transport. Keep the `client:` parameter working but schedule its removal note for Phase 3 (transport rewrite) — do not remove it now.
3. Move the pydantic import-warming hack (glinet.py:57-58 and its import) into `_transport.py` next to the uplink machinery it exists for, so glinet.py's docstring claim of uplink-freeness becomes true.
4. Tests: close() closes an owned session (mock aiohttp session, assert `.close()` awaited once); close() does NOT close an injected session; double-close is safe; `async with GLinet(...)` enters/exits and closes; positional base_url constructs; injected-session construction routes requests through it (transport-level test with the existing characterization-mock pattern).
5. README quickstart: switch to `async with GLinet("http://192.168.8.1/rpc") as router:` and remove any now-stale caveat. (Resolves the first #14 review note.)

Commit: `feat: session lifecycle — close(), async context manager, aiohttp session injection` (NOT breaking: purely additive; existing construction patterns keep working — verify with the existing unit suite untouched-and-green before your own tests).

## Task 5: Failure-state-machine tests

**Files:** `tests/test_glinet_unit.py` (or a new `tests/test_state_machines.py` if test_glinet_unit.py would grow past ~1000 lines — your call, report it).

The recursive retry state machines and firmware-routing branches identified as untested-anywhere in the assessment, now testable against the Phase-2 taxonomy:

1. `tailscale_start`: depth-limit exhaustion → `RetryExhausted` (assert attempts/depth in message); connecting-then-failed → `RetryExhausted`; unknown-status → `UnexpectedResponse`; retry-sleep path executes (patch `asyncio.sleep`, assert called, no real sleeping).
2. `tailscale_stop`: same coverage for its branches.
3. `_wireguard_set_client_enabled` firmware routing: fw < 4.8 → `wg-client` RPC path; fw ≥ 4.8 → `vpn-client` path; unparseable firmware → `UnexpectedResponse` from `_require_firmware_version` (mock sequences via the existing `side_effect` transport pattern).
4. `network_acceleration_set` conflict path: transport returns the captured conflict shape → `FeatureConflictError` surfaces to the caller.
5. `flow_stats_clear`, `list_static_clients`, `router_get_load`, `router_mac`, `connected_to_internet`, `_tailscale_get_config`, `tailscale_configured` happy paths (the live-only coverage gaps) — one focused test each with realistic payloads.
6. Transport: sha512 login branch and the login exception paths reworked in Task 3 (_transport.py sha512 + wrap branches).

Coverage after this task should clear ~93% (report the number). Commit: `test: cover retry state machines, firmware routing, and live-only paths`.
