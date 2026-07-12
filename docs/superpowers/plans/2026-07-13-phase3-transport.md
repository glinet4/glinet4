# Phase 3 — Transport rewrite: drop uplink (0.2.0 series)

Tracking: glinet4/glinet4#15 (phase) / #19 (umbrella). Source: ~/dev/oss/GLINET4-TECHDEBT.md Phase 3. Context: uplink is effectively unmaintained (39-month release gap, py3.14 UserWarning uplink#349) and drags `requests`+`six`+`uritemplate` into an async-only library; pydantic is a required dep used only for an import-warming hack. The transport boundary (`_transport.py`) already isolates all of it.

## Global Constraints

- The transport's CONTRACT to glinet.py is frozen: `request(payload)`, `request_long_timeout(payload)`, `build_sid_payload`/`build_no_auth_payload`, `login(...)`, `sid` property, `close()`, `__aenter__`/`__aexit__` — same signatures, same return/raise semantics (the Phase-2 error contract: everything through `raise_for_status`, every raise inside APIClientError). glinet.py should need NO changes beyond the `client:` parameter removal.
- Caller-visible breaking changes in this phase (must appear in the final squash BREAKING CHANGE footer, tracked in the ledger as they land): `client:` constructor parameter removed (uplink type — no longer exists); `gen_sid_payload`/`gen_no_auth_payload` deprecated shims deleted; uplink/pydantic no longer installed as dependencies (import fallout for anyone relying on transitives).
- NON-negotiable behavior preservation: challenge-response login flow byte-identical (same hashing, same payloads on the wire); 2s default request timeout and 5s long timeout preserved as DEFAULTS (now per-instance configurable); session ownership/lifecycle semantics from Phase 2 preserved (owned vs injected, close idempotency, no exception swallowing in __aexit__).
- Full gate green per task: `uv run pytest -q` (passes+skips only), `uvx prek run --all-files`, `uv run mypy glinet4` strict, coverage ≥85. After Task 2, mypy must pass with ZERO `type: ignore` comments in the package and ZERO `ignore_missing_imports` overrides except (if kept) passlib.
- Conventional commits; breaking pieces carry `!` + BREAKING CHANGE footers (belt-and-braces even though the squash footer is authoritative).

## Task 1: Rewrite GLinetTransport on plain aiohttp

**Files:** `glinet4/_transport.py`, `glinet4/glinet.py` (client: param removal only), `tests/test_transport.py`, `tests/test_glinet_unit.py` (only where uplink internals were poked).

1. Rewrite `_transport.py`: an owned-or-injected `aiohttp.ClientSession`, POSTing JSON payloads to `base_url` with `aiohttp.ClientTimeout`; responses fed to the existing `error_handling.raise_for_status` unchanged. Constructor: `base_url: str`, `session: aiohttp.ClientSession | None = None`, `sid: str | None = None`, `request_timeout: float = 2`, `long_timeout: float = 5`, `ssl: bool | ssl.SSLContext = True` (passed to the request call, letting self-signed HTTPS users opt out). Lazy owned-session creation (aiohttp sessions must be created inside a running loop — the Phase-2 tests pin sync construction working); ownership/close/idempotency semantics identical to Phase 2 (now trivially, since WE hold the session — no uplink internals to poke). Keep `login()` and the payload builders exactly as they are (they don't touch uplink).
2. Delete the pydantic import-warming hack entirely (it existed for uplink's converter machinery).
3. `glinet.py`: remove the `client:` parameter and the `AiohttpClient` import. Everything else untouched.
4. Tests: adapt only what pokes uplink internals — the lifecycle tests that set `_client._session`/`_auto_created_session` now target the transport's own session attribute (simpler); the injected-session routing test now mocks `session.request`/`session.post` directly (it must still prove requests FLOW through the injected session and the JSON payload shape on the wire is unchanged — assert the exact posted JSON for one sid call and one no-auth call, this is the wire-contract regression net). Add: ssl kwarg passthrough test (assert the session call receives ssl=False when configured); per-instance timeout test (assert ClientTimeout carries the configured values).
5. TDD where the contract is pinned: wire-shape tests first against the OLD transport (GREEN), then rewrite and keep them GREEN unmodified — they are characterization tests; say explicitly in the report that they ran green on both sides of the rewrite.

Commit: `fix!: replace uplink with a plain-aiohttp transport` (footer: `client:` parameter removed; construct with `session=` or let the client own its session).

## Task 2: Dependency, typing, and shim cleanup

**Files:** `pyproject.toml`, `uv.lock`, `glinet4/glinet.py`, `glinet4/_transport.py`, `tests/test_glinet_unit.py`, `stubs/` (new, if chosen).

1. pyproject: remove `uplink` and `pydantic` from dependencies; raise `aiohttp>=3.10` (first cp312-complete line; lock already resolves 3.14.x). `uv lock` refresh. Verify with `uv pip list`-equivalent in a fresh sync that uplink/requests/six/uritemplate/pydantic are gone from the runtime tree (report the before/after package counts).
2. mypy: delete the uplink override; for passlib either add a 10-line `.pyi` stub (mypy_path/stubs dir) for the three crypt functions or keep a narrowly-scoped override with a comment — implementer's choice, report it. Remove every remaining `# type: ignore` in the package (there should be none needed post-uplink; if one is genuinely required, justify it in the report).
3. Delete `gen_sid_payload`/`gen_no_auth_payload` from glinet.py and their tests (deprecated shims; zero consumers — verified in the assessment).
4. Grep sweep: no `uplink` or `pydantic` reference remains anywhere in glinet4/, tests/, README.md, CONTRIBUTING.md (docs mention allowed only as historical changelog content).

Commit: `fix!: drop uplink and pydantic from dependencies; delete deprecated payload shims` (footer: transitive deps gone; shims deleted).

## Task 3: Wire-truth verification against the live capture

**Files:** tests only (new `tests/test_wire_contract.py` or extension of test_transport.py — implementer's call).

Using the payload shapes recorded in the main checkout's capture (/home/shaunes/dev/oss/gli4py/docs/devices/mt6000_4.9.0.json — read-only, NAMES and structural shapes only, no values committed) and the existing rpc_catalog: one parametrized test asserting the new transport serializes `build_sid_payload`/`build_no_auth_payload` requests into the exact JSON-RPC envelope the old uplink stack sent (`{"jsonrpc": "2.0", "id": ..., "method": "call", "params": [sid, module, rpc, params]}` — derive the truth from the CURRENT code before the rewrite lands, not from memory). If Task 1's characterization tests already cover exactly this, this task collapses into extending them with the id-field and header (Content-Type) assertions and a short report section proving wire equivalence — don't duplicate.

Commit: `test: pin the JSON-RPC wire envelope across the transport rewrite`.
