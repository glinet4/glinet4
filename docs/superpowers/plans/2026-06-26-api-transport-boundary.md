# API/Transport Boundary, Typing & CI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `gli4py`'s monolithic `GLinet(Consumer)` into a composed transport + API/protocol layer, add typed responses with `py.typed`, and stand up CI — the foundation for HA-core readiness (issues #3, #4, #5).

**Architecture:** Extract a `GLinetTransport(uplink.Consumer)` that owns all I/O (uplink client, request methods, sid, login). `GLinet` becomes a plain class that *composes* a transport, delegates I/O to it, and keeps protocol logic (firmware-version VPN routing) and orchestration (client filtering, wifi reshaping, tailscale state machines). The public method surface and dict-return contract are unchanged; transport-mocked unit tests replace the hardware-only coverage gap.

**Tech Stack:** Python ≥3.11, uplink (aiohttp backend), pydantic (lazy-import guard only), semver, passlib, pytest + pytest-asyncio, ruff, mypy, uv, hatchling.

## Global Constraints

- Python floor: `requires-python = ">=3.11"`. CI matrix: `["3.11", "3.12", "3.13"]`.
- License: `GPL-3.0-or-later`.
- Workflow: branch off `dev` → PR into `dev` (one PR per "PR group" below).
- **No change to the public method surface or the dict-return contract.** `GLinet(base_url=...)`, `GLinet(client=AiohttpClient(session=...))`, `GLinet(sid=...)`, `.login()`, `.router_reachable()`, `.logged_in`, `.sid`, and every existing `router_*` / `wifi_*` / `wireguard_*` / `tailscale_*` method (including `_tailscale_status` and `_tailscale_get_config`, which the live tests call) must keep working with identical signatures and return shapes.
- TypedDicts are **annotations only** — methods still return plain `dict`s at runtime.
- Pydantic stays solely as the existing lazy-import guard (`_ = pydantic.BaseModel`); no response validation.
- `NEW_VPN_CLIENT_VERSION` stays importable from `gli4py.glinet` (the live tests import it).
- Keep the existing `pylint`, `codeql`, `dependency-review`, and `python-publish` workflows.
- Build backend: hatchling; wheel package = `gli4py`.
- All commands run via uv (`uv run pytest`, `uv run ruff`, `uv run mypy`); `uv sync` after dependency changes.

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `gli4py/_transport.py` | Create | `GLinetTransport(Consumer)` — uplink client, `request`/`request_long_timeout`, non-mutating payload builders, `sid`, `login`/`_challenge`/`_get_sid`/`router_reachable`. The only I/O unit. |
| `gli4py/glinet.py` | Rewrite | `GLinet` — composes a transport; raw API methods + orchestration helpers; protocol routing; back-compat constructor + delegating `sid`/`logged_in`/`login`/`router_reachable`. |
| `gli4py/enums.py` | Modify | `TailscaleConnection`: `Enum` → `IntEnum`. |
| `gli4py/_types.py` | Create | `TypedDict` response models. |
| `gli4py/py.typed` | Create | PEP 561 marker. |
| `gli4py/__init__.py` | Modify | Re-export `TailscaleConnection` and response types. |
| `pyproject.toml` | Modify | Drop `requests` runtime dep; add `ruff`/`mypy` dev deps + config; ship `py.typed`. |
| `tests/test_transport.py` | Create | Transport unit tests (builders, construction, login, reachability). |
| `tests/test_glinet_unit.py` | Create | GLinet orchestration unit tests against a mocked transport. |
| `.github/workflows/ci.yml` | Create | pytest + ruff (Task 4); mypy --strict gate (Task 8). |

---

## PR GROUP 1 — #3: API/transport boundary + mocked tests

### Task 1: Create `GLinetTransport`

**Files:**
- Create: `gli4py/_transport.py`
- Test: `tests/test_transport.py`

**Interfaces:**
- Consumes: `gli4py.error_handling.{APIClientError, AuthenticationError, raise_for_status}`; uplink `{AiohttpClient, Body, Consumer, json, post, response_handler, timeout}`.
- Produces:
  - `GLinetTransport(sid: str | None = None, client: AiohttpClient | None = None, **kwargs)`
  - `@staticmethod build_sid_payload(method: str, params: list, sid: str | None = None) -> dict` (non-mutating; result `params == [sid, *params]`)
  - `@staticmethod build_no_auth_payload(method: str, params: dict) -> dict`
  - `async request(data) -> Any`, `async request_long_timeout(data) -> Any`
  - `async login(username: str, password: str) -> None` (sets `sid`, `_logged_in`)
  - `async router_reachable(username: str = "root") -> bool`
  - `property logged_in -> bool`, attribute `sid: str | None`

- [ ] **Step 1: Write the failing transport tests**

Create `tests/test_transport.py`:

```python
"""Unit tests for the GLinet transport/auth layer (no hardware)."""

from unittest.mock import AsyncMock

import pytest

from gli4py._transport import GLinetTransport
from gli4py.error_handling import APIClientError


def test_build_sid_payload_shape():
    payload = GLinetTransport.build_sid_payload("call", ["system", "get_info"], "SID")
    assert payload == {
        "method": "call",
        "jsonrpc": "2.0",
        "params": ["SID", "system", "get_info"],
        "id": 0,
    }


def test_build_sid_payload_does_not_mutate_caller_list():
    params = ["system", "get_info"]
    GLinetTransport.build_sid_payload("call", params, "SID")
    assert params == ["system", "get_info"]


def test_build_no_auth_payload_shape():
    payload = GLinetTransport.build_no_auth_payload("challenge", {"username": "root"})
    assert payload == {
        "method": "challenge",
        "jsonrpc": "2.0",
        "params": {"username": "root"},
        "id": 0,
    }


def test_construction_defaults():
    transport = GLinetTransport(base_url="http://192.168.8.1/rpc")
    assert transport.sid is None
    assert transport.logged_in is False


def test_construction_with_sid_is_logged_in():
    transport = GLinetTransport(sid="SID", base_url="http://192.168.8.1/rpc")
    assert transport.sid == "SID"
    assert transport.logged_in is True


@pytest.fixture
def transport():
    return GLinetTransport(base_url="http://192.168.8.1/rpc")


async def test_router_reachable_true(transport):
    transport.request = AsyncMock(return_value={"alg": 1, "salt": "s", "nonce": "n"})
    assert await transport.router_reachable() is True


async def test_router_reachable_false_on_api_error(transport):
    transport.request = AsyncMock(side_effect=APIClientError("boom"))
    assert await transport.router_reachable() is False


async def test_login_md5_sets_sid(transport):
    transport.request = AsyncMock(
        side_effect=[
            {"alg": 1, "salt": "abc", "nonce": "xyz", "hash-method": "md5"},
            {"sid": "SESSION"},
        ]
    )
    await transport.login("root", "password")
    assert transport.sid == "SESSION"
    assert transport.logged_in is True


async def test_login_sha256_sets_sid(transport):
    transport.request = AsyncMock(
        side_effect=[
            {"alg": 5, "salt": "abc", "nonce": "xyz", "hash-method": "sha256"},
            {"sid": "S2"},
        ]
    )
    await transport.login("root", "pw")
    assert transport.sid == "S2"


async def test_login_unsupported_alg_raises_keyerror(transport):
    transport.request = AsyncMock(
        side_effect=[{"alg": 99, "salt": "abc", "nonce": "xyz", "hash-method": "md5"}]
    )
    with pytest.raises(KeyError):
        await transport.login("root", "pw")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_transport.py -v`
Expected: collection/`ModuleNotFoundError: No module named 'gli4py._transport'`.

- [ ] **Step 3: Create `gli4py/_transport.py`**

```python
"""Transport and authentication layer for the GL.iNet router API.

This module owns everything that touches the network: the uplink client, the
JSON-RPC request methods, session-id (``sid``) state, and the challenge-response
login flow with its CPU-bound password hashing. It is the only place in the
package that performs I/O — the API layer (``gli4py.glinet.GLinet``) composes a
``GLinetTransport`` and never imports uplink or talks to the client directly.
"""

import asyncio
import hashlib
from typing import Any

from passlib.hash import md5_crypt, sha256_crypt, sha512_crypt
from uplink import (
    AiohttpClient,
    Body,
    Consumer,
    json,
    post,
    response_handler,
    timeout,
)

from .error_handling import APIClientError, AuthenticationError, raise_for_status


class GLinetTransport(Consumer):
    """JSON-RPC transport for the GL.iNet API.

    Owns the uplink client, request methods, ``sid`` state and the login flow.
    """

    def __init__(
        self,
        sid: str | None = None,
        client: AiohttpClient | None = None,
        **kwargs: Any,
    ) -> None:
        self.sid: str | None = sid
        self._logged_in: bool = sid is not None
        client = client or AiohttpClient()
        super().__init__(client=client, **kwargs)

    @staticmethod
    def build_sid_payload(method: str, params: list, sid: str | None = None) -> dict:
        """Build an authenticated JSON-RPC payload.

        Does not mutate ``params``: the session id is prepended into a new list.
        """
        return {
            "method": method,
            "jsonrpc": "2.0",
            "params": [sid, *params],
            "id": 0,
        }

    @staticmethod
    def build_no_auth_payload(method: str, params: dict) -> dict:
        """Build an unauthenticated JSON-RPC payload (challenge / login)."""
        return {
            "method": method,
            "jsonrpc": "2.0",
            "params": params,
            "id": 0,
        }

    @response_handler(raise_for_status)
    @json
    @post("")
    @timeout(2)
    async def request(self, data: Body) -> Any:
        """Make a JSON-RPC request to the router (2s timeout)."""

    @response_handler(raise_for_status)
    @json
    @post("")
    @timeout(5)
    async def request_long_timeout(self, data: Body) -> Any:
        """Make a JSON-RPC request to the router (5s timeout)."""

    async def _challenge(self, username: str) -> dict:
        """Request a login challenge to start the login process."""
        challenge_data = self.build_no_auth_payload("challenge", {"username": username})
        return await self.request(challenge_data)

    async def _get_sid(self, username: str, hsh: str) -> dict:
        """Exchange the computed hash for a session id."""
        login_data = self.build_no_auth_payload(
            "login", {"username": username, "hash": hsh}
        )
        return await self.request(login_data)

    async def router_reachable(self, username: str = "root") -> bool:
        """Return True if the router answers a login challenge."""
        try:
            res = await self._challenge(username)
            if res:
                return True
        except APIClientError:
            return False
        return False

    async def login(self, username: str, password: str) -> None:
        """Log in via challenge-response and store the session id."""

        def _compute_hash(
            alg: int,
            salt: str,
            nonce: str,
            hash_method: str,
            username: str,
            password: str,
        ) -> str:
            """Synchronous helper for CPU-bound hashing."""
            if alg == 1:  # MD5
                cipher_password = md5_crypt.using(salt=salt).hash(password)
            elif alg == 5:  # SHA-256
                cipher_password = sha256_crypt.using(salt=salt, rounds=5000).hash(
                    password
                )
            elif alg == 6:  # SHA-512
                cipher_password = sha512_crypt.using(salt=salt, rounds=5000).hash(
                    password
                )
            else:
                raise ValueError(
                    "Router requested unsupported hashing algorithm for cipher password"
                )

            data = f"{username}:{cipher_password}:{nonce}"
            if hash_method == "md5":
                return hashlib.md5(data.encode()).hexdigest()
            if hash_method == "sha256":
                return hashlib.sha256(data.encode()).hexdigest()
            if hash_method == "sha512":
                return hashlib.sha512(data.encode()).hexdigest()
            raise ValueError(
                "Router requested unsupported hashing algorithm for hash"
            )

        try:
            res = await self._challenge(username)
            alg = res["alg"]
            salt = res["salt"]
            nonce = res["nonce"]
            hash_method = res.get("hash-method", "md5")
            hsh = await asyncio.to_thread(
                _compute_hash, alg, salt, nonce, hash_method, username, password
            )
            res = await self._get_sid(username, hsh)
            if "sid" in res:
                self.sid = res["sid"]
                self._logged_in = True
        except (KeyError, ValueError) as e:
            raise KeyError("Parameter Exception:") from e
        except AuthenticationError as e:
            raise AuthenticationError("Authentication failed during login") from e
        except APIClientError as e:
            raise APIClientError(
                f"An unexpected error of type {type(e).__name__} has occurred during login"
            ) from e

    @property
    def logged_in(self) -> bool:
        """Whether a successful login has stored a session id."""
        return self._logged_in
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_transport.py -v`
Expected: PASS (11 passed). If `AuthenticationError`/`APIClientError` ordering matters, note `AuthenticationError` is a subclass of `APIClientError` and is caught first — keep that order.

- [ ] **Step 5: Commit**

```bash
git add gli4py/_transport.py tests/test_transport.py
git commit -m "feat: extract GLinetTransport (transport + auth + non-mutating payloads)"
```

---

### Task 2: Rewire `GLinet` to compose the transport

**Files:**
- Rewrite: `gli4py/glinet.py`
- Modify: `pyproject.toml` (remove `requests` runtime dependency)
- Test: `tests/test_glinet_unit.py`

**Interfaces:**
- Consumes: `GLinetTransport` (Task 1) — `request`, `request_long_timeout`, `build_sid_payload`, `sid`, `logged_in`, `login`, `router_reachable`.
- Produces:
  - `GLinet(sid=None, client=None, **kwargs)` — composes `self._transport`; holds `self._firmware_version: Version | None`.
  - delegating `property sid` (get/set), `property logged_in`, `async login`, `async router_reachable`.
  - `_payload(method: str, params: list) -> dict` (private helper → `self._transport.build_sid_payload(method, params, self.sid)`).
  - All existing API/orchestration methods, now delegating I/O to `self._transport`.
  - module constant `NEW_VPN_CLIENT_VERSION = Version(4, 8, 0, 0)`.

- [ ] **Step 1: Write the failing smoke tests**

Create `tests/test_glinet_unit.py`:

```python
"""Unit tests for GLinet's API/orchestration layer against a mocked transport."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from semver import Version

from gli4py.glinet import GLinet


@pytest.fixture
def glinet():
    g = GLinet(base_url="http://192.168.8.1/rpc")
    g._transport = MagicMock()
    g._transport.request = AsyncMock()
    g._transport.request_long_timeout = AsyncMock()
    g._transport.sid = "SID"
    return g


def test_construction_preserves_public_surface():
    g = GLinet(base_url="http://192.168.8.1/rpc")
    assert g.logged_in is False
    assert g.sid is None


async def test_router_info_delegates_and_caches_firmware(glinet):
    glinet._transport.request.return_value = {
        "model": "mt6000",
        "firmware_version": "4.8.0",
        "mac": "aa:bb:cc",
    }
    res = await glinet.router_info()
    assert res["model"] == "mt6000"
    assert glinet._firmware_version == Version.parse("4.8.0")
    glinet._transport.request.assert_awaited_once()
```

- [ ] **Step 2: Run the smoke tests to verify they fail**

Run: `uv run pytest tests/test_glinet_unit.py -v`
Expected: `test_router_info_delegates_and_caches_firmware` FAILS — the current `GLinet.router_info` calls `self._request(...)` (a real uplink method, ignoring the injected `_transport`), so the mock is never used and the call errors / does not await the mock.

- [ ] **Step 3: Rewrite `gli4py/glinet.py`**

Replace the entire file with:

```python
"""Asynchronous client for the GL.iNet router API.

``GLinet`` is the API/protocol layer: thin methods that build JSON-RPC params,
delegate I/O to a :class:`gli4py._transport.GLinetTransport`, and shape the
responses. It owns protocol knowledge (firmware-version VPN routing) and
higher-level orchestration (client filtering, wifi reshaping, the tailscale
connection state machines) but performs no I/O itself.
"""

import asyncio
from typing import Any

import pydantic
from semver import Version
from uplink import AiohttpClient

from gli4py.enums import TailscaleConnection

from ._transport import GLinetTransport
from .error_handling import APIClientError

# Force Pydantic to resolve its lazy imports to prevent HA event loop blocking
_ = pydantic.BaseModel

# typical base url http://192.168.8.1/rpc
NEW_VPN_CLIENT_VERSION = Version(4, 8, 0, 0)


class GLinet:
    """A Python client for the GL.iNet API (API/protocol layer)."""

    def __init__(
        self,
        sid: str | None = None,
        client: AiohttpClient | None = None,
        **kwargs: Any,
    ) -> None:
        self._transport = GLinetTransport(sid=sid, client=client, **kwargs)
        self._firmware_version: Version | None = None

    # --- session / auth delegation -------------------------------------------

    @property
    def sid(self) -> str | None:
        """The current session id (delegated to the transport)."""
        return self._transport.sid

    @sid.setter
    def sid(self, value: str | None) -> None:
        self._transport.sid = value

    @property
    def logged_in(self) -> bool:
        """Whether the client has a valid session (delegated to the transport)."""
        return self._transport.logged_in

    async def login(self, username: str, password: str) -> None:
        """Log in to the router and store the session id."""
        await self._transport.login(username, password)

    async def router_reachable(self, username: str = "root") -> bool:
        """Return True if the router answers a login challenge."""
        return await self._transport.router_reachable(username)

    # --- payload helper ------------------------------------------------------

    def _payload(self, method: str, params: list) -> dict:
        """Build an authenticated JSON-RPC payload for the current session."""
        return self._transport.build_sid_payload(method, params, self.sid)

    # --- raw API methods (one per RPC) ---------------------------------------

    async def router_info(self) -> dict:
        """Retrieve router information; caches the firmware version."""
        response = await self._transport.request(
            self._payload("call", ["system", "get_info"])
        )
        if "firmware_version" in response:
            self._firmware_version = Version.parse(response["firmware_version"])
        else:
            raise ValueError("No firmware version found in router info")
        return response

    async def router_get_status(self) -> dict[str, list[dict[str, Any]]]:
        """Retrieve router status, with wifi passwords redacted."""
        response: dict[str, list[dict[str, Any]]] = await self._transport.request(
            self._payload("call", ["system", "get_status"])
        )
        if "wifi" in response:
            for i, _ in enumerate(response["wifi"]):
                response["wifi"][i]["passwd"] = None
        return response

    async def router_get_load(self) -> dict:
        """Retrieve router load information."""
        return await self._transport.request(
            self._payload("call", ["system", "get_load"])
        )

    async def router_mac(self) -> dict:
        """Retrieve the router's MAC address."""
        return await self._transport.request(
            self._payload("call", ["macclone", "get_mac"])
        )

    async def router_reboot(self, delay: int = 0) -> dict:
        """Reboot the router."""
        return await self._transport.request(
            self._payload("call", ["system", "reboot", {"delay": delay}])
        )

    async def ping(self, address) -> bool:
        """Ping an address from the router; True if reachable."""
        result = await self._transport.request_long_timeout(
            self._payload("call", ["diag", "ping", {"addr": address}])
        )
        return not result == []

    async def connected_to_internet(self) -> dict:
        """Return the upstream/edge-router connectivity status."""
        return await self._transport.request(
            self._payload("call", ["edgerouter", "get_status"])
        )

    async def list_all_clients(self) -> dict:
        """Get all clients known to the router."""
        return await self._transport.request(
            self._payload("call", ["clients", "get_list"])
        )

    async def list_static_clients(self) -> dict:
        """Get all statically-bound clients."""
        return await self._transport.request(
            self._payload("call", ["lan", "get_static_bind_list"])
        )

    async def _wifi_config_get(self) -> dict:
        """Retrieve the raw wifi configuration."""
        return await self._transport.request(
            self._payload("call", ["wifi", "get_config"])
        )

    async def _wifi_config_set(self, config: dict) -> dict:
        """Apply a wifi configuration change."""
        return await self._transport.request(
            self._payload("call", ["wifi", "set_config", config])
        )

    # --- higher-level orchestration helpers ----------------------------------

    async def connected_clients(self) -> dict:
        """Return online clients keyed by MAC address."""
        clients = {}
        all_clients = await self.list_all_clients()
        for client in all_clients["clients"]:
            if client["online"] is True:
                clients[client["mac"]] = client
        return clients

    async def wifi_ifaces_get(self, redact_keys=True) -> dict[str, dict[str, Any]]:
        """Return wifi interfaces keyed by name; keys redacted unless asked."""
        wifi_config = await self._wifi_config_get()
        return {
            iface.get("name"): {
                **iface,
                "key": None if redact_keys else iface.get("key"),
            }
            for dev in wifi_config.get("res", [])
            for iface in dev.get("ifaces")
        }

    async def wifi_iface_set_enabled(self, iface_name: str, enabled: bool) -> dict:
        """Enable/disable a wifi interface by name."""
        ifaces = await self.wifi_ifaces_get()
        if iface_name in ifaces:
            return await self._wifi_config_set(
                {"enabled": enabled, "iface_name": iface_name}
            )
        raise ValueError("iface_name does not exist")

    # --- VPN: WireGuard (firmware-version routing is protocol knowledge) ------

    async def wireguard_client_list(self) -> list[dict[str, Any]]:
        """List configured WireGuard client peers."""
        response: dict = await self._transport.request(
            self._payload("call", ["wg-client", "get_all_config_list"])
        )
        configs: list[dict[str, Any]] = []
        for item in response["config_list"]:
            if item["peers"] == []:
                continue
            for peer in item["peers"]:
                configs.append(
                    {
                        "name": f'{item["group_name"]}/{peer["name"]}',
                        "group_id": item["group_id"],
                        "peer_id": peer["peer_id"],
                    }
                )
        return configs

    async def wireguard_client_state(self) -> list[dict[str, Any]]:
        """Return WireGuard client status, normalised to a list."""
        if self._firmware_version is None:
            await self.router_info()
        target_call = (
            "vpn-client"
            if self._firmware_version >= NEW_VPN_CLIENT_VERSION
            else "wg-client"
        )
        response = await self._transport.request(
            self._payload("call", [target_call, "get_status"])
        )
        if self._firmware_version < NEW_VPN_CLIENT_VERSION:
            return [response]
        return response.get("status_list", [])

    async def wireguard_client_start(
        self, group_id: int, peer_or_tunnel_id: int
    ) -> dict:
        """Start a WireGuard client."""
        return await self._wireguard_set_client_enabled(
            group_id, peer_or_tunnel_id, True
        )

    async def wireguard_client_stop(self, peer_or_tunnel_id: int) -> dict:
        """Stop a WireGuard client."""
        return await self._wireguard_set_client_enabled(-1, peer_or_tunnel_id, False)

    async def _wireguard_set_client_enabled(
        self, group_id: int, peer_or_tunnel_id: int, enabled: bool
    ) -> dict:
        """Enable/disable a WireGuard client, routing by firmware version."""
        if self._firmware_version is None:
            await self.router_info()
        if self._firmware_version >= NEW_VPN_CLIENT_VERSION:
            tunnel_id = peer_or_tunnel_id
            return await self._transport.request(
                self._payload(
                    "call",
                    [
                        "vpn-client",
                        "set_tunnel",
                        {"enabled": enabled, "tunnel_id": tunnel_id},
                    ],
                )
            )
        peer_id = peer_or_tunnel_id
        if enabled:
            return await self._transport.request(
                self._payload(
                    "call",
                    ["wg-client", "start", {"group_id": group_id, "peer_id": peer_id}],
                )
            )
        return await self._transport.request(
            self._payload("call", ["wg-client", "stop"])
        )

    # --- VPN: Tailscale ------------------------------------------------------

    async def _tailscale_get_config(self) -> dict | bool:
        """Return the tailscale config, or False if unavailable."""
        try:
            result = await self._transport.request(
                self._payload("call", ["tailscale", "get_config"])
            )
        except APIClientError:
            return False
        return result

    async def _tailscale_set_config(self, config_updates: dict[str, Any]) -> dict:
        """Merge updates into the tailscale config and apply them."""
        current_config: dict[str, Any] = await self._transport.request(
            self._payload("call", ["tailscale", "get_config"])
        )
        new_config = current_config | config_updates
        return await self._transport.request(
            self._payload("call", ["tailscale", "set_config", new_config])
        )

    async def _tailscale_status(self) -> dict:
        """Return the raw tailscale status."""
        return await self._transport.request(
            self._payload("call", ["tailscale", "get_status"])
        )

    async def tailscale_connection_state(self) -> TailscaleConnection:
        """Return the tailscale connection state."""
        state: dict = dict(await self._tailscale_status())
        if not state:
            return TailscaleConnection.DISCONNECTED
        return TailscaleConnection(state.get("status", 0))

    async def tailscale_configured(self) -> bool:
        """Return True if tailscale is configured."""
        try:
            if await self._tailscale_status() != []:
                return True
        except APIClientError:
            return False
        if await self._tailscale_get_config() is False:
            return False
        return True

    async def tailscale_start(self, depth: int = 0) -> bool:
        """Start tailscale, retrying until connected."""
        if depth > 10:
            raise ConnectionError(
                "Tailscale attempted to connect 10 times with no success"
            )
        response: dict | list = await self._tailscale_status()
        if isinstance(response, list) and response == []:
            await self._tailscale_set_config({"enabled": True})
            if depth > 0:
                await asyncio.sleep(0.3)
            depth += 1
            return await self.tailscale_start(depth)
        status: int = response.get("status", 0)
        if status == 3:
            return True
        if status == 4:
            await asyncio.sleep(3)
            status = (await self._tailscale_status())["status"]
            if status != 3:
                raise ConnectionError(
                    "Did not try to start tailscale as device reported 'Connecting' "
                    f"and then 3 seconds later {TailscaleConnection(status).name}"
                )
            return True
        if status in [1, 2]:
            raise ConnectionAbortedError(
                "Connection not attempted as authorisation is not complete, due to "
                f"{TailscaleConnection(status).name}"
            )
        raise ConnectionError(f"Unknown connection status: {status}")

    async def tailscale_stop(self, depth: int = 0) -> bool:
        """Stop tailscale, retrying until disconnected."""
        if depth > 10:
            raise ConnectionError(
                "Tailscale attempted to disconnect 10 times with no success"
            )
        response: dict | list = await self._tailscale_status()
        if isinstance(response, list) and response == []:
            return True
        status: int = response.get("status", 0)
        if status in [3, 4]:
            await self._tailscale_set_config({"enabled": False})
            if depth > 0:
                await asyncio.sleep(0.3)
            depth += 1
            return await self.tailscale_stop(depth)
        if status in [1, 2]:
            raise ConnectionAbortedError(
                "Disconnection not attempted as tailscale authorisation is not "
                f"complete, due to {TailscaleConnection(status).name}. Therefore "
                "tailscale was already not connected"
            )
```

> **Two intentional corrections** (the only behavioural changes in this otherwise mechanical move):
> 1. `list[dict[str, any]]` → `list[dict[str, Any]]` (the lowercase `any` builtin was a bug; #4).
> 2. `TailscaleConnection[status].name` → `TailscaleConnection(status).name` in the tailscale error paths. The original used name-lookup (`[]`) on an int, which raises `KeyError` instead of the intended `ConnectionError`/`ConnectionAbortedError`; value-lookup (`()`) is what the surrounding code intends. The Task 3 abort test exercises this path.
>
> The `requests` import, `requests.exceptions` catch in `login`, and the `-> Response` annotations are gone (moved/dropped). `gen_sid_payload`/`gen_no_auth_payload` are removed (now `build_*` on the transport).

- [ ] **Step 4: Remove the `requests` runtime dependency**

In `pyproject.toml`, delete the `"requests>=2.27.1",` line from `[project.dependencies]` and trim the now-stale comment so the block reads:

```toml
# Runtime dependencies.
dependencies = [
    "uplink>=0.10.0",
    "libpass>=1.8.0",
    "semver>=3.0.0",
    "aiohttp>=3.8.4",
    "pydantic>=2.0",
]
```

Then resync:

Run: `uv sync`
Expected: lockfile updates; `requests` may remain only as a transitive dependency of uplink.

- [ ] **Step 5: Run the smoke tests to verify they pass**

Run: `uv run pytest tests/test_glinet_unit.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Verify nothing else imports the removed symbols**

Run: `uv run python -c "import gli4py; from gli4py.glinet import GLinet, NEW_VPN_CLIENT_VERSION; print('ok')"`
Expected: `ok` (no `ImportError`). Also confirm no lingering references:
Run: `grep -rn "gen_sid_payload\|gen_no_auth_payload\|from requests\|_request(" gli4py/`
Expected: no matches in `gli4py/`.

- [ ] **Step 7: Commit**

```bash
git add gli4py/glinet.py pyproject.toml uv.lock tests/test_glinet_unit.py
git commit -m "refactor: GLinet composes GLinetTransport; drop requests coupling"
```

---

### Task 3: Orchestration characterization tests

**Files:**
- Modify: `tests/test_glinet_unit.py` (append)

**Interfaces:**
- Consumes: the `glinet` fixture (Task 2) — a `GLinet` with a `MagicMock` transport whose `request`/`request_long_timeout` are `AsyncMock`s.

- [ ] **Step 1: Append the orchestration tests**

Add to `tests/test_glinet_unit.py`:

```python
from gli4py.enums import TailscaleConnection


async def test_router_get_status_redacts_wifi_passwords(glinet):
    glinet._transport.request.return_value = {
        "system": {"uptime": 1},
        "wifi": [
            {"ssid": "x", "passwd": "secret"},
            {"ssid": "y", "passwd": "secret2"},
        ],
    }
    res = await glinet.router_get_status()
    assert res["wifi"][0]["passwd"] is None
    assert res["wifi"][1]["passwd"] is None


async def test_connected_clients_filters_offline_and_keys_by_mac(glinet):
    glinet._transport.request.return_value = {
        "clients": [
            {"mac": "AA", "online": True},
            {"mac": "BB", "online": False},
            {"mac": "CC", "online": True},
        ]
    }
    clients = await glinet.connected_clients()
    assert set(clients.keys()) == {"AA", "CC"}
    assert clients["AA"] == {"mac": "AA", "online": True}


async def test_wifi_ifaces_get_reshapes_and_redacts_by_default(glinet):
    glinet._transport.request.return_value = {
        "res": [
            {"ifaces": [{"name": "wifi2g", "ssid": "S", "enabled": True, "key": "secret"}]},
        ]
    }
    ifaces = await glinet.wifi_ifaces_get()
    assert ifaces["wifi2g"]["key"] is None
    assert ifaces["wifi2g"]["ssid"] == "S"


async def test_wifi_ifaces_get_exposes_keys_when_not_redacted(glinet):
    glinet._transport.request.return_value = {
        "res": [{"ifaces": [{"name": "wifi2g", "key": "secret"}]}]
    }
    ifaces = await glinet.wifi_ifaces_get(redact_keys=False)
    assert ifaces["wifi2g"]["key"] == "secret"


async def test_wireguard_client_state_new_firmware_returns_status_list(glinet):
    glinet._firmware_version = Version(4, 8, 0)
    glinet._transport.request.return_value = {
        "status_list": [{"name": "A", "enabled": True}]
    }
    assert await glinet.wireguard_client_state() == [{"name": "A", "enabled": True}]


async def test_wireguard_client_state_old_firmware_wraps_single_object(glinet):
    glinet._firmware_version = Version(4, 7, 0)
    glinet._transport.request.return_value = {"name": "A", "status": 1}
    assert await glinet.wireguard_client_state() == [{"name": "A", "status": 1}]


async def test_wireguard_client_list_flattens_peers_and_skips_empty(glinet):
    glinet._transport.request.return_value = {
        "config_list": [
            {"group_name": "G1", "group_id": 1, "peers": []},
            {"group_name": "G2", "group_id": 2, "peers": [{"name": "P", "peer_id": 9}]},
        ]
    }
    assert await glinet.wireguard_client_list() == [
        {"name": "G2/P", "group_id": 2, "peer_id": 9}
    ]


async def test_tailscale_connection_state_disconnected_on_empty(glinet):
    glinet._transport.request.return_value = []
    assert await glinet.tailscale_connection_state() == TailscaleConnection.DISCONNECTED


async def test_tailscale_connection_state_connected(glinet):
    glinet._transport.request.return_value = {"status": 3}
    assert await glinet.tailscale_connection_state() == TailscaleConnection.CONNECTED


async def test_tailscale_start_already_connected(glinet):
    glinet._transport.request.return_value = {"status": 3}
    assert await glinet.tailscale_start() is True


async def test_tailscale_start_enables_when_empty_then_connects(glinet):
    glinet._transport.request.side_effect = [
        [],                      # _tailscale_status: not configured/disabled
        {"wan_enabled": False},  # _tailscale_set_config -> get_config
        {"ok": True},            # _tailscale_set_config -> set_config
        {"status": 3},           # recursion: now connected
    ]
    assert await glinet.tailscale_start() is True


async def test_tailscale_start_connecting_then_connected(glinet, monkeypatch):
    async def _no_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr("gli4py.glinet.asyncio.sleep", _no_sleep)
    glinet._transport.request.side_effect = [
        {"status": 4},  # connecting
        {"status": 3},  # connected after the (patched) 3s wait
    ]
    assert await glinet.tailscale_start() is True


async def test_tailscale_start_aborts_when_login_required(glinet):
    glinet._transport.request.return_value = {"status": 1}
    with pytest.raises(ConnectionAbortedError):
        await glinet.tailscale_start()


async def test_tailscale_stop_when_already_empty_returns_true(glinet):
    glinet._transport.request.return_value = []
    assert await glinet.tailscale_stop() is True


async def test_tailscale_stop_disables_when_connected(glinet):
    glinet._transport.request.side_effect = [
        {"status": 3},           # _tailscale_status: connected
        {"wan_enabled": True},   # _tailscale_set_config -> get_config
        {"ok": True},            # _tailscale_set_config -> set_config
        [],                      # recursion: now empty -> True
    ]
    assert await glinet.tailscale_stop() is True
```

- [ ] **Step 2: Run the full unit suite to verify it passes**

Run: `uv run pytest tests/test_glinet_unit.py tests/test_transport.py -v`
Expected: PASS (all green). The live module is skipped: `uv run pytest -v` shows `tests/test_glinet.py` skipped (no `GLINET_PASSWORD`).

- [ ] **Step 3: Commit**

```bash
git add tests/test_glinet_unit.py
git commit -m "test: characterization tests for GLinet orchestration via mocked transport"
```

---

## PR GROUP 2 — #5 (partial): CI with pytest + ruff

### Task 4: ruff config + CI workflow

**Files:**
- Modify: `pyproject.toml` (add ruff dev dep + config)
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: the unit test suites from Tasks 1–3.
- Produces: `ci.yml` job `test` running ruff + pytest on `dev`/`master`.

- [ ] **Step 1: Add ruff to dev deps and configure it**

In `pyproject.toml`, add `"ruff>=0.6",` to `[dependency-groups].dev`, and append:

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

Run: `uv sync`
Expected: `ruff` installed into the dev environment.

- [ ] **Step 2: Run ruff and fix what it reports**

Run: `uv run ruff check .`
Expected: either clean, or a small list of fixable issues. Apply safe fixes:
Run: `uv run ruff check . --fix && uv run ruff format .`
Then re-run `uv run ruff check .` and `uv run ruff format --check .` — both must be clean. Re-run `uv run pytest -v` to confirm formatting did not break tests.

- [ ] **Step 3: Create `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [dev, master]
  pull_request:
    branches: [dev, master]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v6
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: uv sync
      - name: Ruff lint
        run: uv run ruff check .
      - name: Ruff format check
        run: uv run ruff format --check .
      - name: Run tests
        run: uv run pytest -v
```

> The live tests in `tests/test_glinet.py` self-skip without `GLINET_PASSWORD`, so CI runs only the mocked suites — no hardware needed.

- [ ] **Step 4: Validate the workflow locally**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -v`
Expected: all green (live tests skipped). Optionally lint the YAML with `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .github/workflows/ci.yml gli4py tests
git commit -m "ci: run pytest + ruff on dev/master"
```

---

## PR GROUP 3 — #4: typing + py.typed, then the mypy --strict gate

### Task 5: `TailscaleConnection` → `IntEnum`

**Files:**
- Modify: `gli4py/enums.py`
- Test: `tests/test_enums.py` (create)

**Interfaces:**
- Produces: `TailscaleConnection(IntEnum)` — members compare equal to their int values.

- [ ] **Step 1: Write the failing test**

Create `tests/test_enums.py`:

```python
"""Unit tests for gli4py enums."""

from gli4py.enums import TailscaleConnection


def test_tailscale_connection_is_int_enum():
    assert TailscaleConnection.CONNECTED == 3
    assert int(TailscaleConnection.CONNECTING) == 4
    assert TailscaleConnection(0) is TailscaleConnection.DISCONNECTED
    # value-lookup used by the tailscale error paths
    assert TailscaleConnection(1).name == "LOGIN_REQUIRED"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_enums.py -v`
Expected: `test_tailscale_connection_is_int_enum` FAILS at `TailscaleConnection.CONNECTED == 3` (plain `Enum` members are not equal to ints).

- [ ] **Step 3: Change the base class**

In `gli4py/enums.py`, change the import and base class:

```python
"""This module defines enums for various states and types used in the GL-inet API client."""

from enum import IntEnum


class TailscaleConnection(IntEnum):
    """Enum representing the connection states of Tailscale."""

    DISCONNECTED = 0
    LOGIN_REQUIRED = 1
    AUTHORIZATION_REQUIRED = 2
    CONNECTED = 3
    CONNECTING = 4
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_enums.py tests/test_glinet_unit.py -v`
Expected: PASS (the tailscale tests still pass — `IntEnum` members remain equality-compatible with the enum comparisons).

- [ ] **Step 5: Commit**

```bash
git add gli4py/enums.py tests/test_enums.py
git commit -m "feat: make TailscaleConnection an IntEnum"
```

---

### Task 6: `py.typed` marker + wheel packaging

**Files:**
- Create: `gli4py/py.typed` (empty)
- Modify: `pyproject.toml` (hatch wheel `force-include` / package data)

**Interfaces:**
- Produces: a built wheel that contains `gli4py/py.typed`.

- [ ] **Step 1: Create the marker**

Create `gli4py/py.typed` as an empty file:

```bash
: > gli4py/py.typed
```

- [ ] **Step 2: Ensure hatch ships it**

In `pyproject.toml`, under the existing wheel target, add `force-include` so the marker is packaged:

```toml
[tool.hatch.build.targets.wheel]
packages = ["gli4py"]

[tool.hatch.build.targets.wheel.force-include]
"gli4py/py.typed" = "gli4py/py.typed"
```

- [ ] **Step 3: Build the wheel and verify the marker is present**

Run:
```bash
uv build
uv run python -c "import zipfile, glob; z = zipfile.ZipFile(sorted(glob.glob('dist/*.whl'))[-1]); names = z.namelist(); print('gli4py/py.typed' in names, names)"
```
Expected: prints `True` followed by the wheel contents including `gli4py/py.typed`.

- [ ] **Step 4: Commit**

```bash
git add gli4py/py.typed pyproject.toml
git commit -m "feat: ship py.typed (PEP 561) in the wheel"
```

---

### Task 7: TypedDict response models + `mypy --strict` clean

**Files:**
- Create: `gli4py/_types.py`
- Modify: `gli4py/glinet.py` (return-type annotations), `gli4py/__init__.py` (re-export), `pyproject.toml` (mypy dev dep + config)
- Test: relies on `mypy --strict` as the gate (no new runtime tests; existing suites must stay green)

**Interfaces:**
- Produces: `gli4py/_types.py` with TypedDicts; `mypy --strict gli4py` clean.

- [ ] **Step 1: Create `gli4py/_types.py`**

```python
"""Typed response shapes for the GL.iNet API.

These are ``TypedDict``s, not pydantic models: methods still return plain dicts
at runtime. They exist so consumers (and ``mypy --strict``) get response types.
``total=False`` is used where the router omits keys depending on firmware/state.
"""

from typing import Any, TypedDict


class RouterInfo(TypedDict, total=False):
    """``system get_info`` — at least ``model``/``firmware_version``/``mac``."""

    model: str
    firmware_version: str
    mac: str


class WifiNetwork(TypedDict, total=False):
    """A wifi entry inside router status (``passwd`` is redacted to None)."""

    ssid: str
    passwd: str | None


class RouterStatus(TypedDict, total=False):
    """``system get_status``."""

    service: list[dict[str, Any]]
    network: list[dict[str, Any]]
    system: dict[str, Any]
    wifi: list[WifiNetwork]


class Client(TypedDict, total=False):
    """A single client from ``clients get_list``."""

    mac: str
    online: bool


class WifiIface(TypedDict, total=False):
    """A reshaped wifi interface from :meth:`GLinet.wifi_ifaces_get`."""

    enabled: bool
    encryption: str
    hidden: bool
    guest: bool
    ssid: str
    name: str
    key: str | None


class WireguardClientConfig(TypedDict):
    """A flattened WireGuard peer from :meth:`GLinet.wireguard_client_list`."""

    name: str
    group_id: int
    peer_id: int


class WireguardClientStatus(TypedDict, total=False):
    """A WireGuard client status entry."""

    name: str
    enabled: bool
    status: int
    group_id: int
    peer_id: int
    tunnel_id: int
    rx_bytes: int
    tx_bytes: int


class TailscaleStatus(TypedDict, total=False):
    """``tailscale get_status``."""

    login_name: str
    status: int
    address_v4: str


class TailscaleConfig(TypedDict, total=False):
    """``tailscale get_config``."""

    enabled: bool
    wan_enabled: bool
    lan_enabled: bool
    lan_ip: str
```

- [ ] **Step 2: Annotate API method return types**

Update `gli4py/glinet.py` return annotations to use the TypedDicts (bodies unchanged — the transport returns `Any`, which is assignable to any TypedDict, so no casts are needed). Apply this exact mapping:

| Method | New return annotation |
|---|---|
| `router_info` | `-> RouterInfo` |
| `router_get_status` | `-> RouterStatus` |
| `list_all_clients` | `-> dict[str, list[Client]]` |
| `connected_clients` | `-> dict[str, Client]` |
| `wifi_ifaces_get` | `-> dict[str, WifiIface]` |
| `wireguard_client_list` | `-> list[WireguardClientConfig]` |
| `wireguard_client_state` | `-> list[WireguardClientStatus]` |
| `_tailscale_status` | `-> TailscaleStatus | list` |
| `_tailscale_get_config` | `-> TailscaleConfig | bool` |

Add the import at the top of `glinet.py`:

```python
from ._types import (
    Client,
    RouterInfo,
    RouterStatus,
    TailscaleConfig,
    TailscaleStatus,
    WifiIface,
    WireguardClientConfig,
    WireguardClientStatus,
)
```

Worked example — `connected_clients` becomes:

```python
    async def connected_clients(self) -> dict[str, Client]:
        """Return online clients keyed by MAC address."""
        clients: dict[str, Client] = {}
        all_clients = await self.list_all_clients()
        for client in all_clients["clients"]:
            if client["online"] is True:
                clients[client["mac"]] = client
        return clients
```

Worked example — `wifi_ifaces_get` gains a typed default param:

```python
    async def wifi_ifaces_get(self, redact_keys: bool = True) -> dict[str, WifiIface]:
        ...
```

- [ ] **Step 3: Add mypy as a dev dependency and configure strict mode**

In `pyproject.toml`, add `"mypy>=1.11",` to `[dependency-groups].dev`, and append:

```toml
[tool.mypy]
python_version = "3.11"
strict = true
files = ["gli4py"]
```

Run: `uv sync`
Expected: `mypy` installed.

- [ ] **Step 4: Run mypy and resolve remaining errors**

Run: `uv run mypy gli4py`
Expected initially: a small number of errors. Resolve them with these concrete rules (do **not** silence with blanket ignores):

- **Missing parameter annotations** (e.g. `ping(self, address)`): add types — `async def ping(self, address: str) -> bool:`.
- **Untyped `**kwargs`**: annotate as `**kwargs: Any` (already done in `__init__`s).
- **`response.get(...)` / indexing on `Any`**: no action — the transport returns `Any`, which mypy accepts. If a local is annotated as a concrete `dict` and then indexed with a missing key type, relax that local's annotation to the TypedDict or `Any`.
- **uplink's untyped decorators on `request`/`request_long_timeout`**: if mypy reports the decorated method as untyped, add a targeted `# type: ignore[misc]` on the `async def request` / `async def request_long_timeout` lines only.

Iterate `uv run mypy gli4py` until it reports `Success: no issues found`.

- [ ] **Step 5: Re-export the public types**

Update `gli4py/__init__.py`:

```python
"""gli4py - A Python library for GL.iNet routers"""

from ._types import (
    Client,
    RouterInfo,
    RouterStatus,
    TailscaleConfig,
    TailscaleStatus,
    WifiIface,
    WireguardClientConfig,
    WireguardClientStatus,
)
from .enums import TailscaleConnection
from .glinet import GLinet

__all__ = [
    "GLinet",
    "TailscaleConnection",
    "Client",
    "RouterInfo",
    "RouterStatus",
    "TailscaleConfig",
    "TailscaleStatus",
    "WifiIface",
    "WireguardClientConfig",
    "WireguardClientStatus",
]
```

- [ ] **Step 6: Verify the whole suite + types are green**

Run: `uv run mypy gli4py && uv run ruff check . && uv run ruff format --check . && uv run pytest -v`
Expected: mypy `Success: no issues found`; ruff clean; pytest all green (live skipped).

- [ ] **Step 7: Commit**

```bash
git add gli4py/_types.py gli4py/glinet.py gli4py/__init__.py pyproject.toml uv.lock
git commit -m "feat: TypedDict response models; mypy --strict clean"
```

---

### Task 8: Add the `mypy --strict` gate to CI

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: the strict-clean state from Task 7.

- [ ] **Step 1: Add a mypy step to `ci.yml`**

Insert this step in the `test` job, immediately after "Ruff format check":

```yaml
      - name: Mypy (strict)
        run: uv run mypy gli4py
```

- [ ] **Step 2: Verify locally**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy gli4py && uv run pytest -v`
Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: enforce mypy --strict"
```

---

## Self-Review

**1. Spec coverage**

| Spec requirement | Task |
|---|---|
| Transport in a separate documented unit; API layer doesn't touch uplink | Task 1, Task 2 |
| No `requests` types on async path; `requests` dropped from runtime deps | Task 2 (steps 3–4, 6) |
| `build_sid_payload` non-mutating | Task 1 (test + impl) |
| Each API/orchestration method unit-tested vs mocked transport | Task 3 (+ Task 1 transport) |
| Public surface + dict-return contract unchanged | Global Constraints; Task 2 step 6; live tests preserved |
| `py.typed` shipped in wheel | Task 6 |
| TypedDict response models | Task 7 |
| `TailscaleConnection` is `IntEnum` | Task 5 |
| lowercase `any` fixed | Task 2 step 3 (note) |
| CI: pytest + ruff on dev/master | Task 4 |
| CI: `mypy --strict` | Task 7 (clean) + Task 8 (gate) |
| Keep pylint/codeql/dep-review/publish | Global Constraints (untouched) |
| PR sequencing (strict gate after typing) | PR groups 1→2→3; Task 8 last |

No uncovered spec requirements.

**2. Placeholder scan:** No `TBD`/`TODO`/"handle edge cases"/"similar to". The Task 7 mypy-fix step lists concrete rules per error class rather than "fix errors" — acceptable because the exact error set depends on the resolver, but each rule is a concrete instruction with the code to apply.

**3. Type consistency:** `GLinetTransport.build_sid_payload(method, params, sid)` is used identically in Task 1 (def) and Task 2 (`_payload` caller). `request`/`request_long_timeout` names match between transport def (Task 1), GLinet callers (Task 2), and the mocked-transport fixture (Tasks 2–3). TypedDict names in `_types.py` (Task 7) match the import lists in `glinet.py` and `__init__.py`. The `glinet` test fixture mocks exactly the transport attributes the rewritten `GLinet` calls (`request`, `request_long_timeout`, `build_sid_payload`, `sid`).

---

## Execution Handoff

Two execution options once you pick up implementation:

1. **Subagent-Driven (recommended)** — a fresh subagent per task with two-stage review between tasks (uses `superpowers:subagent-driven-development`).
2. **Inline Execution** — work the tasks in this session with checkpoints (uses `superpowers:executing-plans`).
