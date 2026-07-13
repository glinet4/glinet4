# API surface wave 2 — network services, multi-WAN, and traffic shaping

Follows the VPN wave (16 methods, shipped in 0.2.2). Source of truth: the real device capture at `~/dev/oss/gli4py/docs/devices/mt6000_4.9.0.json` (gitignored REAL device data — READ it to derive shapes, NEVER copy its values into committed code, tests, or docstrings; unit fixtures must be synthetic).

18 read-only getters, all `status: available` with real payloads on fw 4.9.

## Global Constraints

- ADDITIVE ONLY. No existing method/type/signature/behavior changes. Releases as a patch (`feat:` under the pre-1.0 config).
- Follow the conventions the VPN wave established: getters live in the right `_routes/` module; TypedDicts in `_types.py` (`total=False`) exported via `__init__.py` imports + `__all__` (exports guardrail enforces); trivial getters' tests go as rows in `tests/test_routes_table.py` (assert call shape AND return); live shape-only tests in `tests/test_glinet.py`.
- **Where the capture has ZERO records for an envelope's list, type the entries `list[dict[str, Any]]` — never an empty TypedDict** (a zero-field TypedDict blocks field access under strict mypy; this was settled in the VPN wave).
- Derive every field from the capture. Do not invent fields. Where a field's meaning is unclear, name it exactly as the router does and say so in the docstring.
- Naming: noun-first, no `get_`/`list_` prefixes (post-0.2.0 convention).
- Full gate green per task: `uv run pytest -q` (passes+skips), `uvx prek run --all-files`, `uv run mypy glinet4` strict (zero `type: ignore`), coverage ≥85.
- The RPC surface test must stay green with NO allowlist edits (pairs come from the catalog). If a pair is missing, STOP and report.
- Controller live-verifies against real hardware afterward — all calls are read-only, so add live shape assertions.

## Task 1: Network services (7 methods) — `_routes/`: put DNS/ARP/LAN/IPv6/DDNS where they fit the existing module map (wan.py or a new `network.py` if the grouping is cleaner — justify in the report; if you add a module, wire it into the `GLinet` mixin composition and the rpc-surface extractor's file walk exactly as the existing ones are)

- `dns get_config` → `dns_config() -> DnsConfig` (controld_id, controld_type, force_dns, manual_list, mode, nextdns_id, override_vpn, …)
- `dns get_info` → `dns_providers() -> list[DnsProvider]` (the capture's value is a LIST of 9 provider records — read one to type it; NOTE its `server_list[].address` entries are vendor DoH/DoT resolver IPs, i.e. public IPs that are *vendor constants*, not user data; type them, don't sanitize)
- `network get_arp_list` → `arp_table() -> list[ArpEntry]` (unwrap `entries`)
- `lan get_config_list` → `lan_interfaces() -> list[LanInterface]` (unwrap `interfaces`)
- `ipv6 get_ipv6` → `ipv6_config() -> Ipv6Config` (enable, lan_dns_mode, lan_mode, …)
- `ddns get_config` → `ddns_config() -> DdnsConfig` (device_id, enable_ddns)
- `ddns get_status` → `ddns_status() -> DdnsStatus` (ddns, ips, status)

**Privacy note for docstrings:** `arp_table()` and `lan_interfaces()` return the caller's own LAN clients (MACs, IPs, hostnames). That's correct for a library — the router is returning the owner their own data — but the docstrings should note the records are identifying, so callers don't log them wholesale (same pattern as the VPN wave's key-material warnings).

Commit: `feat: wrap the DNS, ARP, LAN, IPv6, and DDNS read surface`.

## Task 2: Multi-WAN, repeater, tethering (7 methods)

- `kmwan get_config` → `multiwan_config() -> MultiWanConfig` (interfaces, mode)
- `kmwan get_status` → `multiwan_status() -> MultiWanStatus` (interfaces)
- `repeater get_config` → `repeater_config() -> RepeaterConfig` (auto, dfs_support, macaddr, smart_reconnect)
- `repeater get_status` → `repeater_status() -> RepeaterStatus` (portal_info, state, state_s)
- `repeater get_saved_ap_list` → `repeater_saved_aps() -> list[dict[str, Any]] | list[SavedAp]` (unwrap `res` — check whether the capture has records; if empty, use `dict[str, Any]` per the constraint)
- `tethering get_status` → `tethering_status() -> TetheringStatus` (devices, status)
- `tethering get_config` → SKIP unless the capture shows a usable shape: its value is an empty list `[]` on this device, which is not a typable envelope. Investigate and report; if it's genuinely a bare empty list, wrap it as `list[dict[str, Any]]` with a docstring noting the shape is unknown, or omit it and say why.

Commit: `feat: wrap the multi-WAN, repeater, and tethering read surface`.

## Task 3: Traffic shaping (4 methods) + docs

- `qos get_config` → `qos_config() -> QosConfig` (enable, mode)
- `qos get_client_list` → `qos_clients() -> list[QosClient]` (unwrap `clients`)
- `qos get_device_group` → `qos_device_groups() -> list[QosDeviceGroup]` (unwrap `group`)
- `sqm get_config` → `sqm_config() -> SqmConfig` (download, enable, qdisc, upload)

**Important context to put in docstrings:** QoS/SQM are the features that CONFLICT with NAT acceleration — the library already models this (see `network_acceleration_set`'s docstring and `FeatureConflictError`). Cross-reference them: a caller checking whether acceleration can be enabled will want `qos_config()`/`sqm_config()` to see what's on.

Then: regenerate the README API-coverage table by introspection (73 rows before this wave → confirm the new count), verify `tests/test_rpc_surface.py` green and report the new sent-pair count (68 before).

Commit: `feat: wrap the QoS and SQM read surface` + `docs: regenerate the API table for the network surface`.
