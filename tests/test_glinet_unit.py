"""Unit tests for GLinet's API/orchestration layer against a mocked transport."""
# pylint: disable=missing-function-docstring,protected-access,redefined-outer-name

from unittest.mock import AsyncMock

import pytest
from semver import Version

from glinet4.enums import TailscaleConnection
from glinet4.error_handling import RetryExhausted, UnexpectedResponse
from glinet4.glinet import GLinet

# The shared transport-mocked `glinet` fixture lives in conftest.py.


def test_construction_preserves_public_surface():
    g = GLinet(base_url="http://192.168.8.1/rpc")
    assert g.logged_in is False
    assert g.sid is None


# --- Phase 2, Task 4: session lifecycle -----------------------------------


def test_positional_base_url_constructs():
    # Phase 2, Task 4: base_url is now the explicit first positional parameter
    # (previously it silently bound to `sid` and requests would go nowhere).
    g = GLinet("http://192.168.8.1/rpc")
    assert g._transport.base_url == "http://192.168.8.1/rpc"


async def test_async_context_manager_delegates_close_to_transport():
    g = GLinet(base_url="http://192.168.8.1/rpc")
    g._transport.close = AsyncMock()
    async with g as ctx:
        assert ctx is g
    g._transport.close.assert_awaited_once()


async def test_async_context_manager_does_not_swallow_exceptions():
    g = GLinet(base_url="http://192.168.8.1/rpc")
    g._transport.close = AsyncMock()
    with pytest.raises(ValueError, match="boom"):
        async with g:
            raise ValueError("boom")
    g._transport.close.assert_awaited_once()


async def test_close_delegates_to_transport():
    g = GLinet(base_url="http://192.168.8.1/rpc")
    g._transport.close = AsyncMock()
    await g.close()
    g._transport.close.assert_awaited_once()


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


async def test_router_info_accepts_3_segment_semver(glinet):
    glinet._transport.request.return_value = {"firmware_version": "4.9.0"}
    await glinet.router_info()
    assert glinet._firmware_version == Version.parse("4.9.0")


async def test_router_info_coerces_4_segment_version(glinet):
    # Some firmware reports a 4th build segment; coerce to the first three.
    glinet._transport.request.return_value = {"firmware_version": "4.7.0.1"}
    await glinet.router_info()
    assert glinet._firmware_version == Version(4, 7, 0)


async def test_router_info_tolerates_unparseable_version(glinet):
    # router_info() must succeed even when the version is garbage; only a
    # caller that actually needs the parsed version should raise.
    glinet._transport.request.return_value = {
        "model": "mt6000",
        "firmware_version": "not-a-version",
    }
    res = await glinet.router_info()
    assert res["model"] == "mt6000"
    assert glinet._firmware_version is None


async def test_wireguard_client_state_raises_clear_error_on_unparseable_firmware(glinet):
    glinet._transport.request.return_value = {"firmware_version": "not-a-version"}
    with pytest.raises(UnexpectedResponse, match="not-a-version"):
        await glinet.wireguard_client_state()


async def test_wireguard_client_start_raises_clear_error_on_unparseable_firmware(glinet):
    glinet._transport.request.return_value = {"firmware_version": "not-a-version"}
    with pytest.raises(UnexpectedResponse, match="not-a-version"):
        await glinet.wireguard_client_start(group_id=1, peer_or_tunnel_id=2)


async def test_router_status_redacts_wifi_passwords(glinet):
    glinet._transport.request.return_value = {
        "system": {"uptime": 1},
        "wifi": [
            {"ssid": "x", "passwd": "secret"},
            {"ssid": "y", "passwd": "secret2"},
        ],
    }
    res = await glinet.router_status()
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


async def test_wifi_ifaces_reshapes_and_redacts_by_default(glinet):
    glinet._transport.request.return_value = {
        "res": [
            {"ifaces": [{"name": "wifi2g", "ssid": "S", "enabled": True, "key": "secret"}]},
        ]
    }
    ifaces = await glinet.wifi_ifaces()
    assert ifaces["wifi2g"]["key"] is None
    assert ifaces["wifi2g"]["ssid"] == "S"


async def test_wifi_ifaces_exposes_keys_when_not_redacted(glinet):
    glinet._transport.request.return_value = {
        "res": [{"ifaces": [{"name": "wifi2g", "key": "secret"}]}]
    }
    ifaces = await glinet.wifi_ifaces(redact_keys=False)
    assert ifaces["wifi2g"]["key"] == "secret"


async def test_wifi_iface_set_enabled_sends_config_change(glinet):
    glinet._transport.request.side_effect = [
        {"res": [{"ifaces": [{"name": "wifi2g", "key": "k"}]}]},  # wifi get_config
        {},  # wifi set_config ack (discarded)
    ]
    result = await glinet.wifi_iface_set_enabled("wifi2g", enabled=False)
    assert result is None
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args == (
        "call",
        ["wifi", "set_config", {"enabled": False, "iface_name": "wifi2g"}],
        "SID",
    )


async def test_wifi_iface_set_enabled_unknown_iface_raises(glinet):
    glinet._transport.request.return_value = {"res": [{"ifaces": [{"name": "wifi2g", "key": "k"}]}]}
    with pytest.raises(UnexpectedResponse, match="iface_name"):
        await glinet.wifi_iface_set_enabled("no-such-iface", enabled=True)
    # Only the get_config read may have happened; no write for an unknown iface.
    glinet._transport.request.assert_awaited_once()


async def test_wireguard_client_state_new_firmware_returns_status_list(glinet):
    glinet._firmware_version = Version(4, 8, 0)
    glinet._transport.request.return_value = {"status_list": [{"name": "A", "enabled": True}]}
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
    assert await glinet.wireguard_client_list() == [{"name": "G2/P", "group_id": 2, "peer_id": 9}]


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
        [],  # _tailscale_status: not configured/disabled
        {"wan_enabled": False},  # _tailscale_set_config -> get_config
        {"ok": True},  # _tailscale_set_config -> set_config
        {"status": 3},  # recursion: now connected
    ]
    assert await glinet.tailscale_start() is True


async def test_tailscale_start_connecting_then_connected(glinet, monkeypatch):
    # Phase 2, Task 5: patch with an AsyncMock (not a bare no-op) so the retry-
    # sleep path's *execution* is actually asserted, not just tolerated.
    sleep = AsyncMock()
    monkeypatch.setattr("glinet4._routes.tailscale.asyncio.sleep", sleep)
    glinet._transport.request.side_effect = [
        {"status": 4},  # connecting
        {"status": 3},  # connected after the (patched) 3s wait
    ]
    assert await glinet.tailscale_start() is True
    sleep.assert_awaited_once_with(3)


async def test_tailscale_start_aborts_when_login_required(glinet):
    glinet._transport.request.return_value = {"status": 1}
    with pytest.raises(RetryExhausted):
        await glinet.tailscale_start()


async def test_tailscale_stop_when_already_empty_returns_true(glinet):
    glinet._transport.request.return_value = []
    assert await glinet.tailscale_stop() is True


async def test_tailscale_stop_disables_when_connected(glinet):
    glinet._transport.request.side_effect = [
        {"status": 3},  # _tailscale_status: connected
        {"wan_enabled": True},  # _tailscale_set_config -> get_config
        {"ok": True},  # _tailscale_set_config -> set_config
        [],  # recursion: now empty -> True
    ]
    assert await glinet.tailscale_stop() is True


async def test_tailscale_stop_already_disconnected_status_zero_returns_true(glinet):
    glinet._transport.request.return_value = {"status": 0}
    assert await glinet.tailscale_stop() is True


async def test_tailscale_stop_aborts_when_login_required(glinet):
    glinet._transport.request.return_value = {"status": 1}
    with pytest.raises(RetryExhausted):
        await glinet.tailscale_stop()


async def test_wifi_status_extracts_radio_list(glinet):
    glinet._transport.request.return_value = {
        "res": [
            {"band": "2g", "channel": 6, "name": "mt798611", "state": "ready"},
            {"band": "5g", "channel": 149, "name": "mt798612", "state": "ready"},
        ]
    }
    radios = await glinet.wifi_status()
    assert radios == glinet._transport.request.return_value["res"]
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["wifi", "get_status", {}], "SID"
    )


async def test_wifi_status_returns_empty_list_when_key_missing(glinet):
    glinet._transport.request.return_value = {}
    assert await glinet.wifi_status() == []


async def test_wifi_mlo_config_extracts_res(glinet):
    glinet._transport.request.return_value = {
        "res": {"encryptions": ["none"], "ifaces": [], "random_bssid": False}
    }
    config = await glinet.wifi_mlo_config()
    assert config == {"encryptions": ["none"], "ifaces": [], "random_bssid": False}
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["wifi", "get_mlo_config", {}], "SID"
    )


async def test_tailscale_auth_url_returns_url_when_available(glinet):
    glinet._transport.request.return_value = {
        "auth_url": "https://login.tailscale.com/a/0123456789ab"
    }
    assert await glinet.tailscale_auth_url() == "https://login.tailscale.com/a/0123456789ab"
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["tailscale", "get_auth_url", {}], "SID"
    )


async def test_tailscale_auth_url_returns_none_when_not_available(glinet):
    glinet._transport.request.return_value = []
    assert await glinet.tailscale_auth_url() is None


async def test_tailscale_exit_node_list_returns_nodes(glinet):
    # item shape per the firmware's RPC source: ip + location (+ provider for mullvad)
    nodes = [
        {"ip": "100.64.0.2", "location": "Australia, Brisbane"},
        {"ip": "100.64.0.3", "location": "au-bne-wg-001", "provider": "mullvad"},
    ]
    glinet._transport.request.return_value = nodes
    assert await glinet.tailscale_exit_node_list() == nodes
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["tailscale", "get_exit_node_list", {}], "SID"
    )


async def test_tailscale_exit_node_list_empty_when_logged_out(glinet):
    # logged out, the firmware answers a bare list
    glinet._transport.request.return_value = []
    assert await glinet.tailscale_exit_node_list() == []


async def test_tailscale_exit_node_list_unwraps_connected_shape(glinet):
    # connected, the firmware wraps the list: {"exit_node_list": [...]}
    glinet._transport.request.return_value = {
        "exit_node_list": [{"ip": "100.64.0.2", "location": "Australia, Brisbane"}]
    }
    assert await glinet.tailscale_exit_node_list() == [
        {"ip": "100.64.0.2", "location": "Australia, Brisbane"}
    ]


async def test_tailscale_exit_node_list_connected_but_empty(glinet):
    glinet._transport.request.return_value = {"exit_node_list": []}
    assert await glinet.tailscale_exit_node_list() == []


async def test_tailscale_set_exit_node_merges_ip_into_config(glinet):
    glinet._transport.request.side_effect = [
        {"enabled": True, "run_exit_node": False},
        {},
    ]
    await glinet.tailscale_set_exit_node(exit_node_ip="100.64.0.2")
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args == (
        "call",
        [
            "tailscale",
            "set_config",
            {"enabled": True, "run_exit_node": False, "exit_node_ip": "100.64.0.2"},
        ],
        "SID",
    )


async def test_tailscale_set_exit_node_default_clears_with_empty_string(glinet):
    glinet._transport.request.side_effect = [
        {"enabled": True, "exit_node_ip": "100.64.0.2"},
        {},
    ]
    await glinet.tailscale_set_exit_node()
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args[1][2]["exit_node_ip"] == ""


async def test_tailscale_connection_state_handles_status_missing(glinet):
    # transiently observed right after enabling tailscale on fw 4.9
    glinet._transport.request.return_value = {"dns": ["192.0.2.53"]}
    assert await glinet.tailscale_connection_state() == TailscaleConnection.DISCONNECTED


async def test_client_set_blocked_true_adds_to_black_list(glinet):
    glinet._transport.request.return_value = []
    await glinet.client_set_blocked("AA:BB:CC:DD:EE:FF", blocked=True)
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call",
        [
            "black_white_list",
            "set_single_mac",
            {"mode": "black", "operate": "add", "mac": "AA:BB:CC:DD:EE:FF"},
        ],
        "SID",
    )


async def test_client_set_blocked_false_removes_from_black_list(glinet):
    glinet._transport.request.return_value = []
    await glinet.client_set_blocked("AA:BB:CC:DD:EE:FF", blocked=False)
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call",
        [
            "black_white_list",
            "set_single_mac",
            {"mode": "black", "operate": "del", "mac": "AA:BB:CC:DD:EE:FF"},
        ],
        "SID",
    )


async def test_blocked_client_macs_filters_blocked(glinet):
    glinet._transport.request.return_value = {
        "clients": [
            {"mac": "AA", "blocked": True, "online": True},
            {"mac": "BB", "blocked": False, "online": True},
            {"mac": "CC", "blocked": True, "online": False},
        ]
    }
    assert await glinet.blocked_client_macs() == {"AA", "CC"}


async def test_flow_stats_rule_returns_state(glinet):
    glinet._transport.request.return_value = {"enable": False, "type": "app", "time": "day"}
    rule = await glinet.flow_stats_rule()
    assert rule["enable"] is False
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["flow_statistics", "get_statistics_rule", {}], "SID"
    )


async def test_flow_stats_set_enabled_sends_full_rule(glinet):
    glinet._transport.request.return_value = []
    await glinet.flow_stats_set_enabled(enabled=True)
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call",
        [
            "flow_statistics",
            "set_statistics_rule",
            {"enable": True, "type": "app", "time": "day"},
        ],
        "SID",
    )


async def test_flow_stats_set_enabled_passes_type_and_time(glinet):
    glinet._transport.request.return_value = []
    await glinet.flow_stats_set_enabled(enabled=False, stat_type="client", period="month")
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call",
        [
            "flow_statistics",
            "set_statistics_rule",
            {"enable": False, "type": "client", "time": "month"},
        ],
        "SID",
    )


async def test_flow_stats_top_apps_unwraps_enabled_dict(glinet):
    glinet._transport.request.return_value = {
        "max_bytes": "0",
        "period_seconds": 86400,
        "top_apps": [
            {
                "application_id": 42,
                "application_name": "netflix",
                "total_download": 1000,
                "total_upload": 50,
                "total_packets": 12,
            }
        ],
    }
    apps = await glinet.flow_stats_top_apps()
    assert apps[0]["application_name"] == "netflix"
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["flow_statistics", "get_top_app_flow_statistics", {}], "SID"
    )


async def test_flow_stats_top_apps_empty_when_disabled(glinet):
    # disabled, the firmware answers a bare list
    glinet._transport.request.return_value = []
    assert await glinet.flow_stats_top_apps() == []


async def test_network_acceleration_returns_config(glinet):
    glinet._transport.request.return_value = {
        "dpi_enabled": True,
        "enable": False,
        "qos_enabled": False,
        "actype": 1,
    }
    accel = await glinet.network_acceleration()
    assert accel["enable"] is False
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["network", "get_netnat_config", {}], "SID"
    )


async def test_adguard_config_returns_flags(glinet):
    glinet._transport.request.return_value = {"enabled": True, "dns_enabled": True}
    config = await glinet.adguard_config()
    assert config["enabled"] is True
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["adguardhome", "get_config", {}], "SID"
    )


async def test_tor_config_returns_flags(glinet):
    glinet._transport.request.return_value = {"enable": False, "countries": [], "manual": False}
    assert await glinet.tor_config() == {"enable": False, "countries": [], "manual": False}
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["tor", "get_config", {}], "SID"
    )


async def test_zerotier_config_returns_flags(glinet):
    glinet._transport.request.return_value = {
        "enabled": False,
        "wan_enabled": False,
        "lan_enabled": False,
    }
    config = await glinet.zerotier_config()
    assert config["enabled"] is False
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["zerotier", "get_config", {}], "SID"
    )


async def test_led_config_returns_state(glinet):
    glinet._transport.request.return_value = {"led_enable": False}
    config = await glinet.led_config()
    assert config["led_enable"] is False
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["led", "get_config", {}], "SID"
    )


async def test_led_set_enabled_merges_current_config(glinet):
    glinet._transport.request.side_effect = [
        {"led_enable": False},
        {},
    ]
    await glinet.led_set_enabled(enabled=True)
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args == ("call", ["led", "set_config", {"led_enable": True}], "SID")


async def test_firewall_port_forward_list_extracts_rules(glinet):
    glinet._transport.request.return_value = {
        "res": [
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
        ]
    }
    rules = await glinet.firewall_port_forward_list()
    assert rules == glinet._transport.request.return_value["res"]
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["firewall", "get_port_forward_list", {}], "SID"
    )


async def test_firewall_port_forward_list_empty_when_key_missing(glinet):
    glinet._transport.request.return_value = {}
    assert await glinet.firewall_port_forward_list() == []


async def test_firewall_dmz_returns_config(glinet):
    glinet._transport.request.return_value = {"enabled": False}
    dmz = await glinet.firewall_dmz()
    assert dmz["enabled"] is False
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["firewall", "get_dmz", {}], "SID"
    )


async def test_firewall_wan_access_returns_flags(glinet):
    glinet._transport.request.return_value = {
        "enable_https": False,
        "enable_ping": False,
        "enable_ssh": False,
        "enable_whitelist": False,
        "whitelist": [],
    }
    access = await glinet.firewall_wan_access()
    assert access["enable_ssh"] is False
    assert access["whitelist"] == []
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["firewall", "get_wan_access", {}], "SID"
    )


async def test_firewall_rule_list_extracts_rules(glinet):
    glinet._transport.request.return_value = {"res": []}
    assert await glinet.firewall_rule_list() == []
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["firewall", "get_rule_list", {}], "SID"
    )


async def test_ping_fw49_replies_returns_true(glinet):
    glinet._transport.request_long_timeout.return_value = {
        "ping_result": (
            "PING 8.8.8.8 (8.8.8.8): 56 data bytes\n"
            "64 bytes from 8.8.8.8: seq=0 ttl=119 time=9.320 ms\n"
        )
    }
    assert await glinet.ping("8.8.8.8") is True


async def test_ping_fw49_no_replies_returns_false(glinet):
    glinet._transport.request_long_timeout.return_value = {
        "ping_result": "PING 0.0.0.1 (0.0.0.1): 56 data bytes\n"
    }
    assert await glinet.ping("0.0.0.1") is False


async def test_ping_fw49_unreachable_returns_false(glinet):
    glinet._transport.request_long_timeout.return_value = {
        "ping_result": "destination host unreachable"
    }
    assert await glinet.ping("no-such-host.invalid") is False


async def test_ping_old_firmware_empty_result_returns_false(glinet):
    glinet._transport.request_long_timeout.return_value = []
    assert await glinet.ping("8.8.8.8") is False


async def test_wan_cable_state_calls_route_and_returns_flags(glinet):
    glinet._transport.request.return_value = {
        "cable_enabled": True,
        "cable_inserted": True,
        "macclone_enabled": False,
    }
    state = await glinet.wan_cable_state()
    assert state["cable_inserted"] is True
    assert state["macclone_enabled"] is False
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["network", "check_wan_cable", {}], "SID"
    )


async def test_wan_status_calls_route_and_returns_connection_details(glinet):
    glinet._transport.request.return_value = {
        "ipv4": {"dns": ["192.0.2.53"], "gateway": "192.0.2.1", "ip": "192.0.2.10/24"},
        "mode": 0,
        "protocol": "dhcp",
        "status": 1,
    }
    status = await glinet.wan_status()
    assert status["protocol"] == "dhcp"
    assert status["ipv4"]["gateway"] == "192.0.2.1"
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["cable", "get_status"], "SID"
    )


async def test_wan_info_extracts_interface_list(glinet):
    glinet._transport.request.return_value = {
        "wan_info": [
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
        ]
    }
    info = await glinet.wan_info()
    assert info == glinet._transport.request.return_value["wan_info"]
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["lan", "get_wan_info"], "SID"
    )


async def test_wan_info_returns_empty_list_when_key_missing(glinet):
    glinet._transport.request.return_value = {}
    assert await glinet.wan_info() == []


async def test_ethernet_ports_status_extracts_ports(glinet):
    glinet._transport.request.return_value = {
        "ports": [{"duplex": "full", "name": "WAN", "speed": 1000}]
    }
    ports = await glinet.ethernet_ports_status()
    assert ports == [{"duplex": "full", "name": "WAN", "speed": 1000}]
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["cable", "get_ports_status"], "SID"
    )


async def test_ethernet_ports_status_returns_empty_list_when_key_missing(glinet):
    glinet._transport.request.return_value = {}
    assert await glinet.ethernet_ports_status() == []


async def test_network_mode_extracts_mode(glinet):
    glinet._transport.request.return_value = {"mode": "router"}
    assert await glinet.network_mode() == "router"
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["netmode", "get_mode"], "SID"
    )


async def test_network_interfaces_status_extracts_list(glinet):
    glinet._transport.request.return_value = {
        "network": [
            {"interface": "wan", "online": True, "up": True},
            {"interface": "modem_1_1_2_6", "online": True, "up": False},
        ]
    }
    interfaces = await glinet.network_interfaces_status()
    assert interfaces == glinet._transport.request.return_value["network"]
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["system", "get_network_status"], "SID"
    )


async def test_network_interfaces_status_returns_empty_list_when_key_missing(glinet):
    glinet._transport.request.return_value = {}
    assert await glinet.network_interfaces_status() == []


async def test_clients_speed_calls_route_and_returns_rates(glinet):
    glinet._transport.request.return_value = {"speed_rx": 4473, "speed_tx": 2775}
    speed = await glinet.clients_speed()
    assert speed["speed_rx"] == 4473
    assert speed["speed_tx"] == 2775
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["clients", "get_speed", {}], "SID"
    )


async def test_wan_speed_calls_route_and_returns_rates(glinet):
    glinet._transport.request.return_value = {"speed_rx": 4582, "speed_tx": 2926}
    speed = await glinet.wan_speed()
    assert speed["speed_rx"] == 4582
    assert speed["speed_tx"] == 2926
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["clients", "get_wan_speed", {}], "SID"
    )


async def test_router_unixtime_extracts_time(glinet):
    glinet._transport.request.return_value = {"time": 1782705193}
    assert await glinet.router_unixtime() == 1782705193
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["system", "get_unixtime", {}], "SID"
    )


async def test_router_disk_info_returns_mounts(glinet):
    glinet._transport.request.return_value = {
        "root": {"free": 7237193728, "total": 7697334272, "used": 460140544},
        "tmp": {"free": 510251008, "total": 518713344, "used": 8462336},
    }
    info = await glinet.router_disk_info()
    assert info["root"]["total"] == 7697334272
    assert info["tmp"]["used"] == 8462336
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["system", "disk_info", {}], "SID"
    )


async def test_router_usb_info_returns_entries(glinet):
    glinet._transport.request.return_value = [{"label": "USB Port", "value": "usb2.0"}]
    info = await glinet.router_usb_info()
    assert info == [{"label": "USB Port", "value": "usb2.0"}]
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["system", "get_usb_info", {}], "SID"
    )


async def test_router_timezone_config_returns_zone(glinet):
    glinet._transport.request.return_value = {
        "autotimezone_enabled": True,
        "localtime": 1782741193,
        "timestamp": 1782705193,
        "timezone": "ChST-10",
        "tzoffset": "+1000",
        "zonename": "Pacific/Guam",
    }
    config = await glinet.router_timezone_config()
    assert config["zonename"] == "Pacific/Guam"
    assert config["autotimezone_enabled"] is True
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["system", "get_timezone_config", {}], "SID"
    )


async def test_firmware_check_online_no_update_available(glinet):
    glinet._transport.request.return_value = {
        "current_compile_time": "2026-05-20 10:00:00",
        "current_type": "release",
        "current_version": "4.9.0",
    }
    check = await glinet.firmware_check_online()
    assert check["current_version"] == "4.9.0"
    assert "new_version" not in check
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["upgrade", "check_firmware_online", {}], "SID"
    )


async def test_firmware_check_online_update_available(glinet):
    glinet._transport.request.return_value = {
        "current_version": "4.9.0",
        "new_version": "4.9.1",
    }
    check = await glinet.firmware_check_online()
    assert check["new_version"] == "4.9.1"


async def test_upgrade_config_returns_flags(glinet):
    glinet._transport.request.return_value = {"prompt": False, "upgrade_enable": True}
    config = await glinet.upgrade_config()
    assert config["upgrade_enable"] is True
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["upgrade", "get_config", {}], "SID"
    )


async def test_clients_status_calls_route_and_returns_totals(glinet):
    glinet._transport.request.return_value = {
        "auto_remove_offline": False,
        "cable_total": 3,
        "wireless_total": 12,
    }
    status = await glinet.clients_status()
    assert status["cable_total"] == 3
    assert status["wireless_total"] == 12
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["clients", "get_status", {}], "SID"
    )
