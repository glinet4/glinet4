# Phase 1 — Quick wins (tech-debt remediation, target 0.1.2)

Tracking: glinet4/glinet4#13 (phase) / #19 (umbrella). Source assessment: ~/dev/oss/GLINET4-TECHDEBT.md.

## Global Constraints

- All changes are NON-BREAKING: no public method renamed, removed, or re-signatured; no exception type changed. Phase 2+ owns breaking work.
- Conventional commit per task (`test:`, `fix:`, `ci:`, `docs:`) — release-please parses the squash body, so subjects must be accurate.
- Every task must leave the full gate green in the worktree: `uv sync && uv run pytest -q` (live suite auto-skips — no `.env` here) and `uvx prek run --all-files`.
- `mypy --strict` stays green (`uv run mypy glinet4`).
- Do not touch `.github/workflows/publish.yml` (release pipeline) beyond what a task explicitly states.
- Match existing code style; sparse comments only where the code can't say it.

## Task 1: Unit-test the error contract and wire ERROR_CODES into it

**Files:** `glinet4/error_handling.py`, `glinet4/error_codes.py`, new `tests/test_error_handling.py`.

`error_handling.raise_for_status` (lines 32-66) has 0% unit coverage and `error_codes.ERROR_CODES` (dict of code→message, error_codes.py:3) is imported nowhere. TDD: write the tests first against current behavior, then wire ERROR_CODES in without changing any raised exception TYPE.

1. `tests/test_error_handling.py`: table-driven tests over a stub `aiohttp.ClientResponse` (mock `.json()`, `.text()`, `.status`) covering every branch: non-2xx → `UnsuccessfulRequest`; JSON-parse failure → `UnsuccessfulRequest`; missing `result`+`error` → the current builtin `ConnectionError` (assert current behavior; Phase 2 changes it — leave a one-line comment saying so); `error.code == -1` → `TokenError`; `-32000` → `AuthenticationError`; other negative codes → `NonZeroResponse`; happy path returns the response. Include a case asserting the exception MESSAGE includes the router-supplied message.
2. Wire `ERROR_CODES` into `raise_for_status` so known codes append their catalog description to the exception message (e.g. `-32601` → method-not-found text). Unknown codes behave exactly as today. Exception types unchanged.
3. Add a test asserting a known catalog code (e.g. -32601) surfaces its catalog text and an unknown code still raises `NonZeroResponse`.

Commit: `test: cover raise_for_status; fix: surface ERROR_CODES descriptions in errors` — two commits, one per type (`test:` first proving current behavior, then `fix:`).

## Task 2: Live-suite guard rework

**Files:** `tests/test_glinet.py` only.

The 9 disruptive tests open with `assert PERFORM_DISTRUPTIVE_TESTS, "…set PERFORM_DISTRUPTIVE_TESTS to True…"` (lines 153, 208, 252, 298, 490, 527, 610, 620, 630) — they FAIL instead of skipping, the constant name has a typo (DISTRUPTIVE), and the message names a variable that isn't the real control (the env var is `GLINET_RUN_DISRUPTIVE`, line 26).

1. Rename the constant `PERFORM_DISTRUPTIVE_TESTS` → `PERFORM_DISRUPTIVE_TESTS`.
2. Define once: `disruptive = pytest.mark.skipif(not PERFORM_DISRUPTIVE_TESTS, reason="Disruptive live tests are disabled; set GLINET_RUN_DISRUPTIVE=1 to run them.")` and decorate the 9 tests, removing the 9 asserts.
3. Delete the `print(router.sid)` at line ~88.
4. Verification: the live module must still import cleanly and skip wholesale without credentials — `uv run pytest tests/test_glinet.py -q` in this worktree must report only skips/collected-no-run, zero failures.

Commit: `fix: skip disruptive live tests instead of failing, correct the guard env var`.

## Task 3: CI coverage gate, py3.14 leg, ruff families, pylint config home

**Files:** `pyproject.toml`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml`.

1. Add `pytest-cov` to the dev dependency group (`uv add --dev pytest-cov`, commits pyproject+lock).
2. ci.yml test matrix: add `"3.14"`; change the pytest step to `uv run pytest -v --cov=glinet4 --cov-fail-under=85` (85 is a floor under today's 87%; do not chase a higher number).
3. Ruff: extend `select` with `ASYNC`, `PT`, `RET`, `SIM`, `PL`; add `ignore` entries `PLR2004`, `PLR0913` (mirroring the ha repo's rationale); add `[tool.ruff.lint.per-file-ignores]` with `"tests/**" = ["PLR2004"]` plus whatever the run actually requires — enable, run `uv run ruff check .`, fix the small findings (2 known: SIM103, SIM201; plus PLR5501), never blanket-ignore a family repo-wide to dodge a fixable finding.
4. Pylint: move the disable list from the prek hook's inline `--disable=…` (.pre-commit-config.yaml:35) into `[tool.pylint.messages_control]` in pyproject.toml — deduplicated (`too-many-public-methods` appears twice), `import-error` dropped (deps resolve under `uv run`), each disable given a one-line reason comment, uplink-specific disables (`abstract-method`, `overridden-final-method`) kept with a "remove with uplink (Phase 3)" note. Hook entry becomes bare `uv run pylint` + existing types/serial settings. `uvx prek run --all-files` must stay green — if dropping `import-error` breaks the hook, investigate; only restore it with a comment explaining exactly why.

Commit: `ci: coverage gate, py3.14 matrix leg, broader ruff families, pylint config in pyproject`.

## Task 4: Export guardrails, tolerant firmware parse, registry surface test

**Files:** `glinet4/__init__.py`, `glinet4/glinet.py`, new `tests/test_exports.py`, new `tests/test_rpc_surface.py`, new `tests/data/rpc_catalog.json`.

1. `tests/test_exports.py`: assert `set(glinet4.__all__)` == the names imported in `__init__.py` and that every public TypedDict defined in `glinet4._types` (public = no leading underscore) is exported. This currently FAILS for `WifiNetwork` (_types.py:19, embedded in RouterStatus but unexported) — add `WifiNetwork` to the imports and `__all__` to make it pass.
2. Tolerant firmware parse: `router_info()` (glinet.py:127-136) currently does `Version.parse(response["firmware_version"])` unconditionally and strict semver raises on non-3-segment strings (e.g. "4.7.0.1"), bricking the first call every consumer makes. Change: attempt the parse; on `ValueError`, retry with `Version.parse(v, optional_minor_and_patch=True)`-style coercion of the first three numeric segments; if still unparseable, store `None` and only raise — with the original string in the message — from the code path that genuinely needs the version (`wireguard_client_state`'s `NEW_VPN_CLIENT_VERSION` gate, glinet.py:541-545). Type of the cached attribute becomes `Version | None`; mypy strict must stay green. Add a comment on `NEW_VPN_CLIENT_VERSION` noting `Version(4, 8, 0, 0)` is semver prerelease `4.8.0-0`, so 4.8.0-beta firmware intentionally routes to the new API. Unit tests: 3-segment ok, 4-segment coerced, garbage → router_info succeeds but the wireguard gate raises with a clear message.
3. Registry surface test: `tests/data/rpc_catalog.json` — a committed, NAMES-ONLY catalog `{"service": ["method", …]}` extracted from the local capture at `/home/shaunes/dev/oss/gli4py/docs/devices/mt6000_4.9.0.json` (main checkout, not this worktree — read it there; it is gitignored because raw VALUES may be unsanitized: commit ONLY service/method name pairs, no values, no signatures). `tests/test_rpc_surface.py`: statically extract every `(service, method)` pair `glinet4/glinet.py` sends (the `[MODULE, RPC, …]` payload literals — AST or regex over the source) and assert each exists in the catalog; on miss, fail with the pair and a hint to update the catalog from a fresh capture. If a legitimately-sent pair is absent from the mt6000 capture (device-specific method), record it in an explicit `KNOWN_UNCATALOGUED` allowlist in the test with a comment.

Commits: `test: guard __all__ exports against drift` (+ the WifiNetwork fix inside), `fix: tolerate non-semver firmware strings in router_info`, `test: assert every RPC pair exists in the captured device catalog`.

## Task 5: Docs and packaging bundle

**Files:** `README.md`, `examples.md` (delete), `pyproject.toml`, new `CONTRIBUTING.md`, new `SECURITY.md`, `CHANGELOG.md`.

1. README: regenerate the API-coverage table from `GLinet`'s actual public methods (script it ad-hoc; the table currently omits ~12 shipped methods: flow_stats_*, network_acceleration*, adguard/tor/zerotier_config, client_set_blocked, blocked_client_macs, tailscale_set_exit_node). Add a Quickstart section right after the badges: `GLinet(base_url="http://192.168.8.1/rpc")` → `await login(user, password)` → one getter call, in an `asyncio.run` snippet — this is currently discoverable only from tests. Fix the registry link (line ~57 points at shauneccles/glinet-registry → glinet4/glinet4-registry) and remove the stale fork-era "Dev setup alongside HA" section + HarvsG todo link (lines ~32-37, 60), replacing with a pointer to CONTRIBUTING.md. Add a "Versioning & stability" paragraph: pre-1.0, breaking changes land in minor bumps, changelog is authoritative.
2. Delete `examples.md` (2021-era fork content advertising nonexistent `async_*` methods and pre-4.8 shapes). The README quickstart replaces it.
3. pyproject: add the classifier block — Development Status :: 4 - Beta; Intended Audience :: Developers; Framework :: AsyncIO; Operating System :: OS Independent; Programming Language :: Python :: 3 :: Only / 3.11 / 3.12 / 3.13 / 3.14 (3.14 valid once Task 3's CI leg exists); Topic :: System :: Networking; Topic :: Home Automation; Typing :: Typed. NO `License ::` classifiers (PEP 639 SPDX already set). Add `keywords = ["gl-inet", "glinet", "router", "openwrt", "json-rpc", "async", "home-assistant"]`.
4. `CONTRIBUTING.md`: adapt the skeleton from /home/shaunes/dev/oss/ha-glinet4-integration/CONTRIBUTING.md to THIS repo: uv setup, `uvx prek install`, conventional squash-merge PR titles (release-please), live-suite rules (copy the .env.example flow; disruptive tests only with GLINET_RUN_DISRUPTIVE=1 against hardware you own; never against a router others depend on), how to submit device captures via glinet4-profiler → glinet4-registry.
5. `SECURITY.md`: ~10 lines — supported versions (latest 0.x), private disclosure via GitHub security advisories, note that the library talks to LAN devices over HTTP by design and the sid token is LAN-visible.
6. CHANGELOG.md: prepend a `## 0.1.0 (2026-07-11)` section under the 0.1.1 entry: initial PyPI release; rebrand/fork provenance one-liner (derived from HarvsG/gli4py, GPL-3.0, see NOTICE).

Commit: `docs: quickstart, regenerated API table, classifiers, CONTRIBUTING/SECURITY, changelog backfill`.
