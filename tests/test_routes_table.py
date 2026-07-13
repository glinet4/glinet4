"""Table-driven coverage for GLinet's trivial pattern-A/B route getters.

Phase 4, Task 3. Roughly two dozen route methods share one of two boilerplate
shapes:

  Pattern A (bare passthrough):   payload -> transport.request -> return as-is
  Pattern B (single-key unwrap):  payload -> transport.request -> response.get(key, default)

Each used to get its own copy-pasted test in test_glinet_unit.py (RPC-pair
assertion + return-value assertion, repeated ~30 times). This module drives
all of them from one declarative table + one parametrized test instead.

Deliberately NOT here (kept as dedicated tests in test_glinet_unit.py /
test_state_machines.py, because they do something beyond the two patterns
above):

- router_info, router_status: cache firmware / redact wifi passwords
- router_mac, wan_upstream_router_detected, tailscale_auth_url: isinstance
  guards that reshape/raise, not a plain ``.get(key, default)``
- tailscale_exit_node_list, flow_stats_top_apps: dict-vs-list envelope
  branching (non-trivial unwrap)
- wifi_ifaces: reshaping + key redaction
- ping: response-string parsing
- connected_clients, blocked_client_macs, tailscale_connection_state,
  tailscale_configured, wireguard_client_list/_state/_start/_stop,
  tailscale_start/_stop: orchestration, filtering, or firmware-routed state
  machines
- every mutator (client_set_blocked, wifi_iface_set_enabled, led_set_enabled,
  network_acceleration_set, flow_stats_set_enabled, flow_stats_clear,
  tailscale_set_exit_node, router_reboot): not a getter
- router_load, static_clients_list: trivial pattern-A/B getters too, but their
  only tests already live in test_state_machines.py (out of this task's file
  scope) -- left untouched rather than duplicated here.
"""
# pylint: disable=missing-function-docstring,protected-access,redefined-outer-name

from typing import Any, NamedTuple

import pytest

# The shared transport-mocked `glinet` fixture lives in conftest.py.


class RouteCase(NamedTuple):
    """One trivial-getter call: RPC params, canned response, expected return."""

    case_id: str
    method: str
    params: list[Any]
    response: Any
    expected: Any


def _a(method: str, params: list[Any], sample: Any) -> RouteCase:
    """Pattern A: the response is returned exactly as received."""
    return RouteCase(method, method, params, sample, sample)


def _b(case_id: str, method: str, params: list[Any], key: str, value: Any) -> RouteCase:
    """Pattern B happy path: the response wraps ``value`` under ``key``."""
    return RouteCase(case_id, method, params, {key: value}, value)


def _b_missing(case_id: str, method: str, params: list[Any], default: Any) -> RouteCase:
    """Pattern B default-fallback: the wrapper key is absent from the response."""
    return RouteCase(case_id, method, params, {}, default)


CASES: list[RouteCase] = [
    # --- system ---------------------------------------------------------
    _b(
        "router_unixtime",
        "router_unixtime",
        ["system", "get_unixtime", {}],
        "time",
        1782705193,
    ),
    _a(
        "router_disk_info",
        ["system", "disk_info", {}],
        {
            "root": {"free": 7237193728, "total": 7697334272, "used": 460140544},
            "tmp": {"free": 510251008, "total": 518713344, "used": 8462336},
        },
    ),
    _a(
        "router_usb_info",
        ["system", "get_usb_info", {}],
        [{"label": "USB Port", "value": "usb2.0"}],
    ),
    _a(
        "router_timezone_config",
        ["system", "get_timezone_config", {}],
        {
            "autotimezone_enabled": True,
            "localtime": 1782741193,
            "timestamp": 1782705193,
            "timezone": "ChST-10",
            "tzoffset": "+1000",
            "zonename": "Pacific/Guam",
        },
    ),
    # --- wan --------------------------------------------------------------
    _a(
        "wan_cable_state",
        ["network", "check_wan_cable", {}],
        {"cable_enabled": True, "cable_inserted": True, "macclone_enabled": False},
    ),
    _a(
        "wan_status",
        ["cable", "get_status"],
        {
            "ipv4": {"dns": ["192.0.2.53"], "gateway": "192.0.2.1", "ip": "192.0.2.10/24"},
            "mode": 0,
            "protocol": "dhcp",
            "status": 1,
        },
    ),
    _b(
        "wan_info_happy",
        "wan_info",
        ["lan", "get_wan_info"],
        "wan_info",
        [
            {
                "info": {
                    "broadcast": "192.0.2.255",
                    "ipaddr": "192.0.2.10",
                    "netmask": "255.255.255.0",
                    "network": "192.0.2.0",
                    "prefix": 24,
                },
                "interface": "wan",
            }
        ],
    ),
    _b_missing("wan_info_missing_key", "wan_info", ["lan", "get_wan_info"], []),
    _b(
        "ethernet_ports_status_happy",
        "ethernet_ports_status",
        ["cable", "get_ports_status"],
        "ports",
        [{"duplex": "full", "name": "WAN", "speed": 1000}],
    ),
    _b_missing(
        "ethernet_ports_status_missing_key",
        "ethernet_ports_status",
        ["cable", "get_ports_status"],
        [],
    ),
    _b(
        "network_mode",
        "network_mode",
        ["netmode", "get_mode"],
        "mode",
        "router",
    ),
    _b(
        "network_interfaces_status_happy",
        "network_interfaces_status",
        ["system", "get_network_status"],
        "network",
        [
            {"interface": "wan", "online": True, "up": True},
            {"interface": "modem_1_1_2_6", "online": True, "up": False},
        ],
    ),
    _b_missing(
        "network_interfaces_status_missing_key",
        "network_interfaces_status",
        ["system", "get_network_status"],
        [],
    ),
    _a(
        "wan_speed",
        ["clients", "get_wan_speed", {}],
        {"speed_rx": 4582, "speed_tx": 2926},
    ),
    # --- clients ------------------------------------------------------------
    _a(
        "clients_speed",
        ["clients", "get_speed", {}],
        {"speed_rx": 4473, "speed_tx": 2775},
    ),
    _a(
        "clients_status",
        ["clients", "get_status", {}],
        {"auto_remove_offline": False, "cable_total": 3, "wireless_total": 12},
    ),
    _a(
        "clients_list",
        ["clients", "get_list"],
        {"clients": [{"mac": "AA:BB:CC:DD:EE:FF", "online": True}]},
    ),
    # --- wifi -----------------------------------------------------------
    _b(
        "wifi_status_happy",
        "wifi_status",
        ["wifi", "get_status", {}],
        "res",
        [
            {"band": "2g", "channel": 6, "name": "mt798611", "state": "ready"},
            {"band": "5g", "channel": 149, "name": "mt798612", "state": "ready"},
        ],
    ),
    _b_missing("wifi_status_missing_key", "wifi_status", ["wifi", "get_status", {}], []),
    _b(
        "wifi_mlo_config",
        "wifi_mlo_config",
        ["wifi", "get_mlo_config", {}],
        "res",
        {"encryptions": ["none"], "ifaces": [], "random_bssid": False},
    ),
    # --- firewall -------------------------------------------------------
    _b(
        "firewall_port_forward_list_happy",
        "firewall_port_forward_list",
        ["firewall", "get_port_forward_list", {}],
        "res",
        [
            {
                "dest": "lan",
                "dest_ip": "192.0.2.20",
                "dest_port": "32400",
                "enabled": True,
                "id": "cfg013837",
                "name": "plex",
                "proto": "tcpudp",
                "src": "wan",
                "src_dport": "32400",
            }
        ],
    ),
    _b_missing(
        "firewall_port_forward_list_missing_key",
        "firewall_port_forward_list",
        ["firewall", "get_port_forward_list", {}],
        [],
    ),
    _a(
        "firewall_dmz",
        ["firewall", "get_dmz", {}],
        {"enabled": False},
    ),
    _a(
        "firewall_wan_access",
        ["firewall", "get_wan_access", {}],
        {
            "enable_https": False,
            "enable_ping": False,
            "enable_ssh": False,
            "enable_whitelist": False,
            "whitelist": [],
        },
    ),
    _b(
        "firewall_rule_list",
        "firewall_rule_list",
        ["firewall", "get_rule_list", {}],
        "res",
        [{"id": "cfg1", "name": "block-x", "enabled": True}],
    ),
    # --- services -------------------------------------------------------
    _a(
        "flow_stats_rule",
        ["flow_statistics", "get_statistics_rule", {}],
        {"enable": False, "type": "app", "time": "day"},
    ),
    _a(
        "network_acceleration",
        ["network", "get_netnat_config", {}],
        {"dpi_enabled": True, "enable": False, "qos_enabled": False, "actype": 1},
    ),
    _a(
        "adguard_config",
        ["adguardhome", "get_config", {}],
        {"enabled": True, "dns_enabled": True},
    ),
    _a(
        "tor_config",
        ["tor", "get_config", {}],
        {"enable": False, "countries": [], "manual": False},
    ),
    _a(
        "zerotier_config",
        ["zerotier", "get_config", {}],
        {"enabled": False, "wan_enabled": False, "lan_enabled": False},
    ),
    _a(
        "led_config",
        ["led", "get_config", {}],
        {"led_enable": False},
    ),
    _a(
        "firmware_check_online",
        ["upgrade", "check_firmware_online", {}],
        {
            "current_compile_time": "2026-05-20 10:00:00",
            "current_type": "release",
            "current_version": "4.9.0",
        },
    ),
    _a(
        "upgrade_config",
        ["upgrade", "get_config", {}],
        {"prompt": False, "upgrade_enable": True},
    ),
    # --- OpenVPN server / client ------------------------------------------
    _a(
        "openvpn_server_status",
        ["ovpn-server", "get_status"],
        {
            "initialization": False,
            "log": "",
            "rx_bytes": 0,
            "status": 0,
            "tunnel_ip": "",
            "tx_bytes": 0,
        },
    ),
    _a(
        "openvpn_server_config",
        ["ovpn-server", "get_config"],
        {
            "access_scope": 1,
            "auth": "SHA256",
            "cipher": "AES-256-GCM",
            "client_auth": 1,
            "client_to_client": False,
            "dh": "-----BEGIN DH PARAMETERS-----...",
            "end": "10.9.0.100",
            "hmac": False,
            "initialization": False,
            "local_access": False,
            "lzo": False,
            "mask": "255.255.255.0",
            "mode": "tun",
            "port": 1194,
            "proto": "udp",
            "start": "10.9.0.2",
            "subnetv4": "10.9.0.0",
            "subnetv6": "fd00:db8:0:456::0/64",
            "tap_address": "10.9.0.1",
            "tap_mask": "255.255.255.0",
            "verb": "3",
        },
    ),
    _a(
        "openvpn_server_setting",
        ["ovpn-server", "get_setting"],
        {"local_access": False, "masq": True},
    ),
    _b(
        "openvpn_server_users_happy",
        "openvpn_server_users",
        ["ovpn-server", "get_user_list"],
        "user_list",
        [{"name": "alice"}],
    ),
    _b_missing(
        "openvpn_server_users_missing_key",
        "openvpn_server_users",
        ["ovpn-server", "get_user_list"],
        [],
    ),
    _a(
        "openvpn_server_routes",
        ["ovpn-server", "get_route_list"],
        {"ipv4_route_rules": [], "ipv6_route_rules": []},
    ),
    _b(
        "openvpn_client_groups_happy",
        "openvpn_client_groups",
        ["ovpn-client", "get_group_list"],
        "groups",
        [
            {
                "askpass": "",
                "askpass_exist": False,
                "auth_type": 1,
                "client_count": 0,
                "group_id": 1001,
                "group_name": "ExampleVPN",
                "group_type": 1,
                "password": "example-secret",
                "procedure": 1,
                "show": False,
                "username": "",
                "work_mode": "modern",
            }
        ],
    ),
    _b_missing(
        "openvpn_client_groups_missing_key",
        "openvpn_client_groups",
        ["ovpn-client", "get_group_list"],
        [],
    ),
    _b(
        "openvpn_client_configs_happy",
        "openvpn_client_configs",
        ["ovpn-client", "get_all_config_list"],
        "config_list",
        [{"config_id": 1, "name": "sample-profile"}],
    ),
    _b_missing(
        "openvpn_client_configs_missing_key",
        "openvpn_client_configs",
        ["ovpn-client", "get_all_config_list"],
        [],
    ),
    # --- WireGuard server / client, VPN client tunnel state ----------------
    _a(
        "wireguard_server_status",
        ["wg-server", "get_status"],
        {
            "peers": [
                {
                    "latest_handshake": 1783200000,
                    "name": "Example Phone",
                    "private_ip": "10.11.0.2/32",
                    "public_ip": "203.0.113.7",
                    "rx_bytes": 12345,
                    "tx_bytes": 54321,
                }
            ],
            "server": {
                "initialization": True,
                "log": "",
                "rx_bytes": 12345,
                "status": 1,
                "tunnel_ip": "10.11.0.1/24",
                "tx_bytes": 54321,
            },
        },
    ),
    _a(
        "wireguard_server_config",
        ["wg-server", "get_config"],
        {
            "address_v4": "10.11.0.1/24",
            "address_v6": "fd00:db8:0:def::1/64",
            "amnezia": "",
            "initialization": True,
            "local_access": False,
            "obfuscation": 0,
            "port": 51820,
            "private_key": "example-server-private-key",
            "public_key": "example-server-public-key",
        },
    ),
    _a(
        "wireguard_server_setting",
        ["wg-server", "get_setting"],
        {"client_to_client": False, "local_access": True, "masq": True},
    ),
    _b(
        "wireguard_server_peers_happy",
        "wireguard_server_peers",
        ["wg-server", "get_peer_list"],
        "peers",
        [
            {
                "allowed_ips": "0.0.0.0/0",
                "client_ip": "10.11.0.2/24",
                "deprecated": 0,
                "dns": "10.11.0.1",
                "enabled": True,
                "end_point": "",
                "mtu": 1420,
                "name": "Example Phone",
                "peer_id": 4242,
                "persistent_keepalive": 25,
                "presharedkey_enable": False,
                "private_key": "example-peer-private-key",
                "public_key": "example-peer-public-key",
            }
        ],
    ),
    _b_missing(
        "wireguard_server_peers_missing_key",
        "wireguard_server_peers",
        ["wg-server", "get_peer_list"],
        [],
    ),
    _a(
        "wireguard_server_routes",
        ["wg-server", "get_route_list"],
        {"ipv4_route_rules": [], "ipv6_route_rules": []},
    ),
    _b(
        "wireguard_client_groups_happy",
        "wireguard_client_groups",
        ["wg-client", "get_group_list"],
        "groups",
        [
            {
                "auth_type": 1,
                "group_id": 2002,
                "group_name": "ExampleWgVPN",
                "group_type": 1,
                "password": "example-secret",
                "peer_count": 0,
                "procedure": 1,
                "show": False,
                "username": "",
            }
        ],
    ),
    _b_missing(
        "wireguard_client_groups_missing_key",
        "wireguard_client_groups",
        ["wg-client", "get_group_list"],
        [],
    ),
    _b(
        "wireguard_client_configs_happy",
        "wireguard_client_configs",
        ["wg-client", "get_all_config_list"],
        "config_list",
        [{"config_id": 1, "name": "sample-wg-profile"}],
    ),
    _b_missing(
        "wireguard_client_configs_missing_key",
        "wireguard_client_configs",
        ["wg-client", "get_all_config_list"],
        [],
    ),
    _a(
        "vpn_client_status",
        ["vpn-client", "get_status"],
        {"mode": 0, "status_list": []},
    ),
    _a(
        "vpn_client_tunnels",
        ["vpn-client", "get_tunnel"],
        {
            "default_tunnels": [
                {
                    "enabled": True,
                    "from": {"type": "default"},
                    "id": "cfg0example",
                    "killswitch": False,
                    "name": "example default policy",
                    "to": {
                        "domain_list": "",
                        "domain_list_len": 0,
                        "manual": True,
                        "type": "default",
                    },
                    "tunnel_id": 100,
                    "via": {"via": "novpn"},
                }
            ],
            "global_enabled": False,
            "tunnels": [],
        },
    ),
    # --- DNS / ARP / LAN / IPv6 / DDNS ---------------------------------------
    _a(
        "dns_config",
        ["dns", "get_config"],
        {
            "controld_id": "",
            "controld_type": 1,
            "force_dns": False,
            "manual_list": [],
            "mode": "auto",
            "nextdns_id": "",
            "override_vpn": True,
            "proto": "",
            "proto_manual": "",
            "provider": "",
            "proxy_list": [],
            "rebind_protection": False,
            "secure_manual_list": [],
            "server_auto": ["wan 198.51.100.10,198.51.100.20"],
            "servers_list": [],
        },
    ),
    _a(
        "dns_providers",
        ["dns", "get_info"],
        [
            {
                "provider": "example-filter-vendor",
                "server_list": [
                    {
                        "address": ["198.51.100.1", "198.51.100.2"],
                        "address6": ["2001:db8::1", "2001:db8::2"],
                        "description": "Unfiltered",
                        "name": "p0",
                        "url_doh": "https://doh.example.com/p0",
                        "url_doq": "quic://p0.example.com",
                        "url_dot": "tls://p0.example.com",
                    }
                ],
                "sup_proto": ["dot", "doh", "doq"],
            },
            {"provider": "example-account-vendor", "sup_proto": ["dot", "doh"]},
        ],
    ),
    _b(
        "arp_table_happy",
        "arp_table",
        ["network", "get_arp_list"],
        "entries",
        [
            {"device": "br-lan", "ip": "192.168.8.50", "mac": "AA:BB:CC:DD:EE:01"},
            {"device": "eth1", "ip": "203.0.113.5", "mac": "AA:BB:CC:DD:EE:02"},
        ],
    ),
    _b_missing("arp_table_missing_key", "arp_table", ["network", "get_arp_list"], []),
    _b(
        "lan_interfaces_happy",
        "lan_interfaces",
        ["lan", "get_config_list"],
        "interfaces",
        [
            {
                "ap_isolate": 0,
                "dns": [],
                "enable": 1,
                "end": "192.168.8.254",
                "gateway": "",
                "interface": "lan",
                "ip": "192.168.8.1",
                "leasetime": "720m",
                "lpr": [],
                "netmask": "255.255.255.0",
                "start": "192.168.8.20",
            },
            {
                "ap_isolate": 1,
                "dns": [],
                "enable": 0,
                "end": "192.168.9.249",
                "gateway": "",
                "interface": "guest",
                "ip": "192.168.9.1",
                "leasetime": "12h",
                "lpr": [],
                "netmask": "255.255.255.0",
                "start": "192.168.9.100",
                "transfer_enable": 0,
            },
        ],
    ),
    _b_missing("lan_interfaces_missing_key", "lan_interfaces", ["lan", "get_config_list"], []),
    _a(
        "ipv6_config",
        ["ipv6", "get_ipv6"],
        {"enable": False, "lan_dns_mode": True, "lan_mode": "nat6"},
    ),
    _a(
        "ddns_config",
        ["ddns", "get_config"],
        {"device_id": "example-device-id", "enable_ddns": True},
    ),
    _a(
        "ddns_status",
        ["ddns", "get_status"],
        {
            "ddns": "203.0.113.9",
            "ips": [
                {"interface": "wan", "ip": ["203.0.113.9"]},
                {"interface": "wan6", "ip": []},
            ],
            "status": 0,
        },
    ),
]


@pytest.mark.parametrize("case", CASES, ids=[c.case_id for c in CASES])
async def test_trivial_route_getter(glinet, case: RouteCase) -> None:
    glinet._transport.request.return_value = case.response
    result = await getattr(glinet, case.method)()
    assert result == case.expected
    glinet._transport.build_sid_payload.assert_called_once_with("call", case.params, "SID")
