# Design: Productionize gli4py for HA core — API/transport boundary, typing, CI

- **Date:** 2026-06-26
- **Status:** Approved (design); pending implementation plan
- **Issues:** #3 (P0, API/transport boundary), #4 (P1, full typing + `py.typed`), #5 (P1, CI: tests + mypy-strict + ruff)
- **Parent epic:** #1 (Productionize gli4py for Home Assistant core)
- **Target branch:** `dev` (branch off `dev` → PR into `dev`)

## 1. Goal & scope

Move gli4py toward Home Assistant core readiness by establishing a clean
internal boundary, adding first-class typing, and standing up CI. This is the
foundational phase that unblocks everything else on the roadmap.

**In scope (this phase):**

- **#3** — Establish a clean API/transport boundary (the P0 foundation).
- **#4** — Full type hints + `py.typed` (typed responses).
- **#5** — CI: run tests + add `mypy --strict` and `ruff`.

**Explicitly out of scope:**

- **#2** — New API endpoints (OpenVPN/Tor/MultiWAN/etc.). Separate phase, built on
  top of this boundary.
- **#6** — Websession injection verify/docs.
- **#7** — Cut 1.0 + PyPI publish automation.
- **#8** — Packaging metadata polish (the SPDX license fix already landed in #9).
- Adopting pydantic for response validation, or any change to the public method
  surface / dict-return contract.
- Any Home Assistant / entity logic in the library (there is none today — keep it
  that way).

The three issues are specced together as one phase but land as a **reviewable PR
sequence into `dev`** (see §8).

## 2. Current state (problem)

`gli4py/glinet.py` is a single ~535-line `GLinet(Consumer)` class that conflates
three concerns:

1. **Transport / session / auth** — the uplink `Consumer`, `AiohttpClient`,
   `_request` / `_request_long_timeout`, `gen_sid_payload` / `gen_no_auth_payload`,
   `sid` management, and challenge-response `login()` with CPU-bound hashing run via
   `asyncio.to_thread`.
2. **Raw API methods** — one method per RPC (`router_info`, `router_get_status`,
   `router_get_load`, `connected_to_internet`, `list_all_clients`, the `wifi`
   getters/setters, `wireguard_*`, `tailscale_*`).
3. **Orchestration / shaping** — `connected_clients` (online-filter + re-key by
   MAC), `wifi_ifaces_get` (reshape + key redaction), firmware-version VPN routing
   (`vpn-client` ≥4.8 vs `wg-client`), and the recursive `tailscale_start` /
   `tailscale_stop` connection state machines.

Concrete defects this phase removes:

- **`requests` coupling on an async path:** `from requests import Response,
  exceptions` (glinet.py:9); `_request*` annotated `-> Response` (a `requests`
  type) but actually returning parsed JSON dicts via `raise_for_status`; `login()`
  catches/re-raises `requests.exceptions.RequestException` (glinet.py:158-159) on a
  path that is really async aiohttp/uplink. `requests` is even a declared runtime
  dependency it does not need to be.
- **Caller-mutating payload helper:** `gen_sid_payload` does
  `params.insert(0, sid)` on the caller's list (glinet.py:51).
- **Typing bugs:** `list[dict[str, any]]` uses the lowercase builtin `any`
  (glinet.py:332, 337); `TailscaleConnection` is a plain `Enum` though it maps
  integer status codes.
- **No isolation for testing/typing:** adding endpoints or types means editing one
  giant class; the only tests are 22 live tests against real hardware
  (`tests/test_glinet.py`), so there is no CI coverage and no mockable seam.

## 3. Target architecture (composition)

`GLinet` stops being a `uplink.Consumer` subclass. It **composes** a transport and
delegates all I/O to it.

| Module | Responsibility |
|---|---|
| `gli4py/_transport.py` (new) | `GLinetTransport(Consumer)` — the **only** unit that does I/O. Owns the uplink `AiohttpClient`, `_request` / `_request_long_timeout` (uplink-decorated), the non-mutating payload builders, `sid` state, and auth (`login`, `_challenge`, `_get_sid`, `router_reachable`, CPU-bound hashing via `asyncio.to_thread`). Returns parsed dicts via `raise_for_status`. No `requests` types. |
| `gli4py/glinet.py` | `GLinet` — composes a `GLinetTransport`. Holds `_firmware_version` (protocol state). **Raw API methods** (one per RPC) build params and call the transport. **Higher-level helpers** (`connected_clients`, `wifi_ifaces_get`, wireguard firmware routing, `tailscale_start` / `tailscale_stop` state machines, `tailscale_connection_state`, `tailscale_configured`) are kept as a clearly-named group, visually/structurally distinct from the raw RPC methods. |
| `gli4py/_types.py` (new) | `TypedDict` definitions for response shapes (router_info / status / clients / wifi / wireguard / tailscale). |
| `gli4py/enums.py` | `TailscaleConnection` changed `Enum` → `IntEnum`. |
| `gli4py/error_handling.py` | Largely unchanged (already aiohttp-based); types tightened as needed. |
| `gli4py/py.typed` (new) | PEP 561 marker; included in the built wheel via hatch packaging config. |

### Boundary contract

- The transport exposes a small surface the API layer depends on — e.g.
  `request(payload, *, long_timeout=False) -> dict` (or two methods mirroring the
  current `_request` / `_request_long_timeout`), plus payload builders and the auth
  methods. The exact method names are an implementation detail for the plan, but
  the API layer must not import uplink or touch the client directly.
- **Protocol logic stays in the library.** Firmware-version VPN routing is protocol
  knowledge, not HA logic — it stays in `GLinet` (the API/protocol layer), driven by
  `_firmware_version`.
- **Orchestration stays in the library** as higher-level helpers (retries, shaping,
  state machines) distinct from the raw API methods. The integration stays thin.

### Back-compat constructor (hard requirement)

`GLinet` must keep its existing construction and public surface:

- `GLinet(sid=None, client=None, base_url=None, **kwargs)` builds the transport
  internally. `GLinet(base_url="http://192.168.8.1/rpc")` (used by the live tests)
  and `GLinet(client=AiohttpClient(session=...))` (used by the HA integration for
  websession injection) both keep working.
- `login()` stays callable on `GLinet` (delegates to the transport).
- `sid` and `logged_in` become properties on `GLinet` that delegate to the transport,
  preserving attribute access for existing consumers.
- If any external caller uses `gen_sid_payload` / `gen_no_auth_payload` directly,
  retain thin (optionally deprecated) shims that forward to the transport builders.

## 4. Bug fixes folded into the boundary work

These are corrected as part of the extraction, not deferred:

- Remove `from requests import Response, exceptions`; drop `requests` from runtime
  dependencies in `pyproject.toml`; change `login()` to catch the real
  aiohttp/custom exceptions instead of `requests.exceptions.RequestException`.
- Replace `gen_sid_payload`'s `params.insert(0, sid)` with a non-mutating builder
  (`build_sid_payload`) that composes a fresh params list.
- Fix `list[dict[str, any]]` → a proper type (`Any` / a TypedDict).
- Change `TailscaleConnection` to `IntEnum`.

## 5. Typing (#4)

- Add `gli4py/py.typed` (PEP 561) so consumers get the types — HA Platinum
  `strict-typing` requirement. Include it in the hatch wheel build.
- Define `TypedDict` response models in `_types.py` for router_info / status /
  clients / wifi / wireguard / tailscale, and annotate the API methods with them.
  **Returns stay plain dicts at runtime** — this preserves the public surface and
  the integration's dict-based consumption/mocking
  (e.g. `response["wifi"][i]["passwd"]`).
- Pydantic remains only the existing lazy-import guard (`_ = pydantic.BaseModel`);
  no response validation is introduced.
- Goal: `mypy --strict gli4py` is clean and enforced in CI.

## 6. Testing strategy (transport-mocked unit tests)

The composition boundary makes the transport injectable, so `GLinet`'s own
parsing/shaping/state-machine logic can be tested without hardware by feeding canned
raw-RPC dicts through a fake/mock transport.

These are a **different layer** from the HA integration's tests (which mock the
`GLinet` client's parsed outputs to test the coordinator/entities), so the suites do
not overlap: raw-RPC fixtures here vs parsed-output fixtures there. Do **not** rebuild
the integration's tests in this repo.

Coverage contract (each is a unit test against a mocked transport):

- `router_get_status()` redacts wifi passwords.
- `connected_clients()` filters offline clients and keys online clients by MAC.
- `wifi_ifaces_get()` reshapes per-device iface data and redacts keys by default
  (and exposes them when `redact_keys=False`).
- `wireguard_client_state()` selects `vpn-client` vs `wg-client` by firmware version
  and normalizes the pre-4.8 single-object response into a list.
- `wireguard_client_list()` flattens peers and skips configs with no peers.
- `tailscale_start()` / `tailscale_stop()` state machines, with patched
  `asyncio.sleep` and mocked status/config transitions (incl. the depth/retry paths).
- `tailscale_connection_state()` maps status codes, including empty → `DISCONNECTED`.
- Transport-level: `build_sid_payload` does not mutate the caller's params; `login()`
  computes the correct hash per algorithm (md5 / sha256 / sha512) and `hash-method`,
  and sets `sid` on success; `raise_for_status` error-code mapping (-1 → `TokenError`,
  -32000 → `AuthenticationError`, other negatives → `NonZeroResponse`).

Tooling: pytest + pytest-asyncio (already configured; `asyncio_mode = "auto"`). The
live tests stay opt-in and skip without `GLINET_PASSWORD`. A small helper to capture
raw RPC from the live tests to seed fixtures (mirroring the integration's
`capture_fixtures.py`, one layer down) is **optional / later** and not blocking.

## 7. CI (#5)

Add a new `ci.yml` workflow:

- **Triggers:** push + pull_request to **`dev` and `master`**. This closes a real gap —
  `codeql.yml` and `dependency-review.yml` currently only trigger on `master`, but the
  contribution flow is `dev`-based.
- **Setup:** `astral-sh/setup-uv`, Python matrix `[3.11, 3.12, 3.13]`
  (`requires-python >= 3.11`), `uv sync`.
- **Jobs:** `pytest` (the mocked unit suite; live tests auto-skip without creds) ·
  `ruff check` + `ruff format --check` · `mypy --strict gli4py`.
- **Config:** add `ruff` and `mypy` configuration to `pyproject.toml`, aligning with
  Home Assistant core tooling where reasonable; add `ruff` and `mypy` to the dev
  dependency group.
- **Retain:** `pylint`, `codeql`, `dependency-review`, `python-publish` unchanged
  (optionally extend their triggers to `dev` as a follow-up).

## 8. PR sequencing into `dev`

Ordered to avoid a red-CI chicken-and-egg — `mypy --strict` cannot be enforced before
the typing it checks exists:

1. **#3** — transport extraction (composition) + `requests` removal + non-mutating
   payload builder + the mocked-transport unit suite (§6).
2. **#5 (partial)** — CI running `pytest` + `ruff` on `dev` / `master`. Gates tests and
   formatting immediately.
3. **#4** — `TypedDict` models + `py.typed` + `IntEnum` + lowercase-`any` fix; **then
   enable the `mypy --strict` gate** in CI.

## 9. Risks & mitigations

- **`GLinet` is no longer `isinstance` of `uplink.Consumer`.** Anything relying on
  Consumer methods or `isinstance` checks would break. Mitigated by the back-compat
  constructor, delegating `sid` / `logged_in` properties, and keeping `login()` on
  `GLinet`. The HA integration uses only the documented method surface.
- **`mypy --strict` on a previously-untyped ~535-line module is substantial work.**
  Isolated as its own PR (#4) so it does not block the structural refactor.
- **Live tests cannot run in CI**, so the mocked suite must genuinely cover the logic.
  The §6 coverage contract is the explicit checklist for that.
- **Hidden caller mutation of payload params** is removed; verify no call site relied
  on the old in-place `insert` behavior (current call sites pass fresh literals).

## 10. Acceptance criteria

- Transport and API concerns live in separate, documented modules; orchestration
  helpers are clearly named and distinct from raw API methods.
- No `requests` types on the async path; `requests` removed from runtime dependencies.
- `build_sid_payload` is non-mutating.
- Every API/orchestration method is unit-tested against a mocked transport; the suite
  runs green in CI without hardware.
- Public method surface and dict-return contract are unchanged; `GLinet(base_url=...)`,
  `GLinet(client=...)`, `.login()`, `.logged_in`, and `.sid` all still work.
- `py.typed` is shipped in the wheel; response shapes are `TypedDict`s;
  `TailscaleConnection` is an `IntEnum`; the lowercase `any` bug is fixed.
- CI runs `pytest` + `ruff` (check + format) + `mypy --strict` green on PRs to `dev`
  and `master`; `pylint` / `codeql` / `dependency-review` retained.
