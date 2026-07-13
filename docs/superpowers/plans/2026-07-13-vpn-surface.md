# API surface wave — VPN completion (OpenVPN client/server, WireGuard server, tunnel state)

Context: the capture (`~/dev/oss/gli4py/docs/devices/mt6000_4.9.0.json`, gitignored real-device data — READ-ONLY, never copy its values into committed code) shows 77 available read-safe methods the library doesn't wrap. The largest coherent gap is VPN: the library has WireGuard *client* control but no OpenVPN at all, no WireGuard *server*, and no peer/tunnel state. This wave closes it with 16 read-only getters that have real captured payloads.

Excluded deliberately (return only `{err_code, err_msg}` on real fw 4.9 — they need params or aren't usable as bare getters): `ovpn-client`/`wg-client` `check_config`, `get_config_list`, `get_recommend_config`, `get_third_config`. Note this in the report; do not wrap them.

## Global Constraints

- ADDITIVE ONLY. No existing method/type/signature changes. This releases as a patch (`feat:` under pre-1.0 config) — nothing breaking.
- Every new method is a read-only getter following the established pattern in `glinet4/_routes/vpn.py` (pattern A/B: `_payload("call", [SERVICE, RPC, {}])` → typed return; unwrap a single envelope key where the payload nests one).
- Every return type is a TypedDict in `glinet4/_types.py` (`total=False`), exported via `glinet4/__init__.py` imports + `__all__` (the exports guardrail test enforces consistency).
- Derive field names and types from the CAPTURE, not from guesses. Where a field's meaning is unclear, name the TypedDict field exactly as the router does and let the docstring say what's unknown.
- Full gate green per task: `uv run pytest -q` (passes+skips only), `uvx prek run --all-files`, `uv run mypy glinet4` strict (zero `type: ignore`), coverage ≥85.
- The RPC surface test will see the new pairs; they're in the catalog already (they came from it), so it stays green with no allowlist edits. If a pair is somehow absent, STOP and report rather than editing the allowlist.
- Naming follows the post-0.2.0 convention (noun-first, no `get_`/`list_` prefixes): e.g. `openvpn_server_status`, `wireguard_server_peers`.
- Controller runs the live suite against real hardware afterward — all calls are read-only, so add live tests for the new methods (assert shape, not values).

## Task 1: OpenVPN server + client

**Files:** `glinet4/_routes/vpn.py`, `glinet4/_types.py`, `glinet4/__init__.py`, `tests/test_routes_table.py` (the parametrized table — new trivial getters belong there), `tests/test_glinet.py` (live shape assertions), `README.md` (API table rows).

Methods (service → RPC → proposed name):
- `ovpn-server get_status` → `openvpn_server_status() -> OpenVpnServerStatus` (fields incl. initialization, log, rx_bytes, tx_bytes, status, tunnel_ip — read the capture for the full set)
- `ovpn-server get_config` → `openvpn_server_config() -> OpenVpnServerConfig` (access_scope, auth, cipher, client_auth, client_to_client, dh, …)
- `ovpn-server get_setting` → `openvpn_server_setting() -> OpenVpnServerSetting` (local_access, masq)
- `ovpn-server get_user_list` → `openvpn_server_users() -> list[OpenVpnUser]` (unwrap `user_list`)
- `ovpn-server get_route_list` → `openvpn_server_routes() -> VpnRouteRules` (ipv4_route_rules, ipv6_route_rules — shared type with wg-server's identical shape; define ONE `VpnRouteRules` and reuse)
- `ovpn-client get_group_list` → `openvpn_client_groups() -> list[OpenVpnClientGroup]` (unwrap `groups`)
- `ovpn-client get_all_config_list` → `openvpn_client_configs() -> list[OpenVpnClientConfig]` (unwrap `config_list`)

Note for the docstrings: on the reference device (fw 4.9, OpenVPN unconfigured) several of these return empty/zeroed structures — that is the shape, not an error. Say so.

Commit: `feat: wrap the OpenVPN server and client read surface`.

## Task 2: WireGuard server + tunnel state

**Files:** same set.

- `wg-server get_status` → `wireguard_server_status() -> WireguardServerStatus` (peers, server)
- `wg-server get_config` → `wireguard_server_config() -> WireguardServerConfig` (address_v4, address_v6, amnezia, initialization, local_access, obfuscation, …)
- `wg-server get_setting` → `wireguard_server_setting() -> WireguardServerSetting` (client_to_client, local_access, masq)
- `wg-server get_peer_list` → `wireguard_server_peers() -> list[WireguardPeer]` (unwrap `peers`; the capture's peer record has name/peer_id/public_key/private_key/presharedkey_enable/allowed_ips/client_ip/dns/end_point/mtu/persistent_keepalive — type them all; these are the owner's own credentials returned to the owner, which is fine for a library, but DO note in the docstring that the peer record carries key material so callers shouldn't log it wholesale)
- `wg-server get_route_list` → `wireguard_server_routes() -> VpnRouteRules` (reuse Task 1's type)
- `wg-client get_group_list` → `wireguard_client_groups() -> list[WireguardClientGroup]` (unwrap `groups`)
- `wg-client get_all_config_list` → `wireguard_client_configs() -> list[WireguardClientConfigEntry]` (unwrap `config_list`; NOTE a `WireguardClientConfig` TypedDict already exists for a different shape — do not collide, and do not change the existing one)
- `vpn-client get_status` → `vpn_client_status() -> VpnClientStatus` (mode, status_list)
- `vpn-client get_tunnel` → `vpn_client_tunnels() -> VpnClientTunnels` (default_tunnels, global_enabled, tunnels)

Commit: `feat: wrap the WireGuard server and VPN tunnel-state read surface`.

## Task 3: Docs + surface bookkeeping

- Regenerate the README API-coverage table by introspection (the established script pattern from Phase 1 — do not hand-edit rows).
- Confirm `tests/test_rpc_surface.py` passes unchanged (new pairs come from the catalog); report the new sent-pair count.
- Update the registry's `covered_by` data? NO — that lives in glinet4-registry; out of scope here. Note it as a follow-up in the report.

Commit: `docs: regenerate the API table for the VPN surface`.
