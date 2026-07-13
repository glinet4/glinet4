# Changelog

## [0.2.3](https://github.com/glinet4/glinet4/compare/v0.2.2...v0.2.3) (2026-07-13)


### Features

* wrap the network, multi-WAN, and traffic-shaping read surface ([#33](https://github.com/glinet4/glinet4/issues/33)) ([7bde1de](https://github.com/glinet4/glinet4/commit/7bde1debadafabe791e6c836783192b0f86dccc6))

## [0.2.2](https://github.com/glinet4/glinet4/compare/v0.2.1...v0.2.2) (2026-07-13)


### Features

* wrap the VPN read surface (OpenVPN, WireGuard server, tunnel state) ([#31](https://github.com/glinet4/glinet4/issues/31)) ([b92d1c0](https://github.com/glinet4/glinet4/commit/b92d1c0ae5dcd9e0538e46b14cf7de78fef3900c))

## [0.2.1](https://github.com/glinet4/glinet4/compare/v0.2.0...v0.2.1) (2026-07-12)


### Bug Fixes

* derive router_mac from system info — fw 4.9 removed the macclone RPC ([#28](https://github.com/glinet4/glinet4/issues/28)) ([0f7c78f](https://github.com/glinet4/glinet4/commit/0f7c78f7e66e12a528b2c159f9a329ce0d4d6f1e))
* let login() propagate APIClientError subclasses unwrapped ([#30](https://github.com/glinet4/glinet4/issues/30)) ([e845b76](https://github.com/glinet4/glinet4/commit/e845b76a4eed6e4ae5bc51914ae5bbddf750c6a9))

## [0.2.0](https://github.com/glinet4/glinet4/compare/v0.1.2...v0.2.0) (2026-07-12)


### ⚠ BREAKING CHANGES

* API consolidation — mixins, renames, keyword-only mutators, typed returns (phase 4) ([#27](https://github.com/glinet4/glinet4/issues/27))
* renames (old names deleted, no aliases): router_get_status → router_status; router_get_load → router_load; list_all_clients → clients_list; list_static_clients → static_clients_list; wifi_ifaces_get → wifi_ifaces; connected_to_internet → wan_upstream_router_detected. Signature changes: client_set_blocked(mac, blocked) → client_set_blocked(mac, *, blocked) -> None (was -> Any); wifi_iface_set_enabled(iface_name, enabled) → wifi_iface_set_enabled(iface_name, *, enabled) -> None (was -> Any); wifi_ifaces(*, redact_keys=True) (flag now keyword-only); led_set_enabled(*, enabled) -> None (was -> Any); network_acceleration_set(*, enabled) -> None (was -> Any); flow_stats_set_enabled(enabled, stat_type="app", period="day") → flow_stats_set_enabled(*, enabled, stat_type="app", period="day") -> None (was -> Any); flow_stats_clear() -> None (was -> Any); tailscale_set_exit_node(ip) → tailscale_set_exit_node(*, exit_node_ip=None) -> None (param renamed ip → exit_node_ip, now optional; was -> Any); tailscale_start(depth=0) → tailscale_start() (retry depth internal; still -> bool); tailscale_stop(depth=0) → tailscale_stop() (retry depth internal; still -> bool); wireguard_client_start(group_id, peer_or_tunnel_id) → wireguard_client_start(*, group_id, peer_or_tunnel_id) -> dict[str, Any] (was -> Any); wireguard_client_stop(peer_or_tunnel_id) -> dict[str, Any] (was -> Any; params unchanged); router_reboot(delay=0) -> None (was -> Any); router_mac() -> str (was -> Any; raises UnexpectedResponse when absent); wan_upstream_router_detected() -> bool (the edgerouter probe detects an upstream/edge router — double-NAT indicator — not internet reachability; use ping() for reachability); router_load() -> RouterLoad (new exported TypedDict); static_clients_list() -> list[StaticClient] (now unwraps the static_bind_list envelope; new exported TypedDict). Mutators annotated -> None now discard the router's empty acknowledgement.
* replace uplink with a plain-aiohttp transport (phase 3) ([#26](https://github.com/glinet4/glinet4/issues/26))
* the client: constructor parameter is removed (uplink's AiohttpClient type no longer exists — construct with session= or let the client own its session; formerly-swallowed uplink kwargs like converters=/hooks= now raise TypeError); the deprecated GLinet.gen_sid_payload/gen_no_auth_payload shims are deleted (use the transport's build_sid_payload/build_no_auth_payload); network-level failures (timeout expiry, DNS failure, connection refused — any aiohttp.ClientError) now raise glinet4.error_handling.UnsuccessfulRequest with the original as __cause__, so `except aiohttp.ClientError` / `except asyncio.TimeoutError` around glinet4 calls no longer match; request timeouts are now actually enforced — uplink silently ignored the previous @timeout decorators (historical effective timeout ~300s) — with live-evidence defaults of 10s (request) / 60s (long path) configurable per instance via request_timeout=/long_timeout=; uplink and pydantic are no longer dependencies (transitives requests/six/uritemplate/pydantic-core etc. are gone from the tree — declare them directly if you relied on them); the aiohttp floor rises to >=3.10.
* error contract and session lifecycle (phase 2) ([#24](https://github.com/glinet4/glinet4/issues/24))
* err_code -1 responses whose message indicates a feature conflict now raise FeatureConflictError (previously TokenError) — re-auth loops must catch it; dict results carrying a non-zero body-level err_code now raise NonZeroResponse/FeatureConflictError instead of returning the envelope; envelope-shape violations raise UnexpectedResponse (previously builtin ConnectionError); tailscale start/stop failures raise RetryExhausted or UnexpectedResponse (previously builtin ConnectionError/ConnectionAbortedError); wifi_iface_set_enabled, router_info, and the wireguard firmware gate raise UnexpectedResponse (previously ValueError); login() lets AuthenticationError/TokenError propagate unwrapped with catalog text (previously re-wrapped, and hashing failures no longer masquerade as KeyError — they raise UnexpectedResponse with __cause__); GLinet's first positional parameter is now the required base_url and the first positional argument no longer binds to sid — pass sid= by keyword.

### Features

* session lifecycle — close(), async context manager, aiohttp session injection, positional base_url ([438c0e3](https://github.com/glinet4/glinet4/commit/438c0e33ad9c7480db051e41ecd9c2ad44767378))


### Bug Fixes

* API consolidation — mixins, renames, keyword-only mutators, typed returns (phase 4) ([#27](https://github.com/glinet4/glinet4/issues/27)) ([4f353ff](https://github.com/glinet4/glinet4/commit/4f353ff577a0f359cc7d073efe4baeffbfa27f4f))
* error contract and session lifecycle (phase 2) ([#24](https://github.com/glinet4/glinet4/issues/24)) ([438c0e3](https://github.com/glinet4/glinet4/commit/438c0e33ad9c7480db051e41ecd9c2ad44767378))
* replace uplink with a plain-aiohttp transport (phase 3) ([#26](https://github.com/glinet4/glinet4/issues/26)) ([be7b5f5](https://github.com/glinet4/glinet4/commit/be7b5f57d421954ef909f93bf65c7e3656062014))


### Miscellaneous Chores

* version 0.x breaking changes as minor bumps (release-please) ([438c0e3](https://github.com/glinet4/glinet4/commit/438c0e33ad9c7480db051e41ecd9c2ad44767378))


### Tests

* parametrized route table; live-validated 45/45 non-disruptive on real hardware. New exports: RouterLoad, StaticClient. RPC (service, method) pair set byte-identical before/after (55 pairs); README table verified against introspection (57 route methods). ([4f353ff](https://github.com/glinet4/glinet4/commit/4f353ff577a0f359cc7d073efe4baeffbfa27f4f))
* pin the JSON-RPC wire envelope and connector-pool invariants across the rewrite ([be7b5f5](https://github.com/glinet4/glinet4/commit/be7b5f57d421954ef909f93bf65c7e3656062014))

## [0.1.2](https://github.com/glinet4/glinet4/compare/v0.1.1...v0.1.2) (2026-07-12)


### Bug Fixes

* phase 1 tech-debt quick wins — error surfacing, firmware tolerance, guardrails ([#20](https://github.com/glinet4/glinet4/issues/20)) ([e83f77c](https://github.com/glinet4/glinet4/commit/e83f77cf3cd468eab8c5765c1a228e0ab9129daf))

## [0.1.1](https://github.com/glinet4/glinet4/compare/v0.1.0...v0.1.1) (2026-07-12)


### Bug Fixes

* import NetworkAcceleration so the `__all__` export resolves — `from glinet4 import NetworkAcceleration` raised ImportError in 0.1.0 ([#1](https://github.com/glinet4/glinet4/issues/1)) ([38ea8da](https://github.com/glinet4/glinet4/commit/38ea8dabe6acaa398b0b98d1e78a1a2f5f5a9f22))


### Documentation

* PyPI/license badges, project footer, GL.iNet branding ([b965916](https://github.com/glinet4/glinet4/commit/b965916a143a043ff70240d5bebc8babd7a3d733))
* theme-aware logo header ([762d216](https://github.com/glinet4/glinet4/commit/762d2168b740fdcc2dadba09f943dc3a641feca0))

## 0.1.0 (2026-07-11)

Initial PyPI release. `glinet4` is a rebrand/fork of
[HarvsG/gli4py](https://github.com/HarvsG/gli4py) (GPL-3.0); see
[NOTICE](NOTICE) for full attribution.
