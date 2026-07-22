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


@pytest.mark.parametrize(
    ("mode", "blocked", "expected_operate"),
    [
        # Blacklist mode: a listed MAC is denied, so blocking adds it.
        ("black", True, "add"),
        ("black", False, "del"),
        # Whitelist mode: a listed MAC is the only one *allowed*, so the
        # add/del semantics invert -- blocking removes it from the list.
        ("white", True, "del"),
        ("white", False, "add"),
    ],
)
async def test_client_set_blocked_respects_list_mode(glinet, mode, blocked, expected_operate):
    # content_filter_config() is read first, then the set_single_mac write.
    glinet._transport.request.side_effect = [{"mode": mode}, []]
    await glinet.client_set_blocked("AA:BB:CC:DD:EE:FF", blocked=blocked)
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args[0] == "call"
    assert last_call.args[1] == [
        "black_white_list",
        "set_single_mac",
        {"mode": mode, "operate": expected_operate, "mac": "AA:BB:CC:DD:EE:FF"},
    ]


async def test_client_set_blocked_reads_active_mode_first(glinet):
    # The mode must be read from the router, not assumed.
    glinet._transport.request.side_effect = [{"mode": "white"}, []]
    await glinet.client_set_blocked("AA:BB:CC:DD:EE:FF", blocked=True)
    first_call = glinet._transport.build_sid_payload.call_args_list[0]
    assert first_call.args[1] == ["black_white_list", "get_config", {}]


async def test_client_set_blocked_defaults_to_blacklist_when_mode_absent(glinet):
    # A router that returns no `mode` is treated as the factory-default
    # blacklist, preserving the historical behaviour.
    glinet._transport.request.side_effect = [{}, []]
    await glinet.client_set_blocked("AA:BB:CC:DD:EE:FF", blocked=True)
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args[1][2] == {
        "mode": "black",
        "operate": "add",
        "mac": "AA:BB:CC:DD:EE:FF",
    }


async def test_blocked_client_macs_filters_blocked(glinet):
    glinet._transport.request.return_value = {
        "clients": [
            {"mac": "AA", "blocked": True, "online": True},
            {"mac": "BB", "blocked": False, "online": True},
            {"mac": "CC", "blocked": True, "online": False},
        ]
    }
    assert await glinet.blocked_client_macs() == {"AA", "CC"}


async def test_fan_set_threshold_sends_temperature(glinet):
    glinet._transport.request.return_value = {}
    await glinet.fan_set_threshold(80)
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call",
        ["fan", "set_config", {"temperature": 80}],
        "SID",
    )


@pytest.mark.parametrize("temperature", [70, 80, 90])
async def test_fan_set_threshold_accepts_range_bounds(glinet, temperature):
    glinet._transport.request.return_value = {}
    await glinet.fan_set_threshold(temperature)
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args[1][2] == {"temperature": temperature}


@pytest.mark.parametrize("temperature", [69, 91, 0, 200])
async def test_fan_set_threshold_rejects_out_of_range(glinet, temperature):
    with pytest.raises(ValueError, match="between 70 and 90"):
        await glinet.fan_set_threshold(temperature)
    # A rejected value must never reach the router.
    glinet._transport.request.assert_not_awaited()


async def test_fan_self_test_defaults_to_ten_seconds(glinet):
    glinet._transport.request.return_value = {}
    await glinet.fan_self_test()
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call",
        ["fan", "set_test", {"test": True, "time": 10}],
        "SID",
    )


async def test_fan_self_test_accepts_custom_duration(glinet):
    glinet._transport.request.return_value = {}
    await glinet.fan_self_test(duration=5)
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args[1] == ["fan", "set_test", {"test": True, "time": 5}]


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


async def test_led_set_enabled_merges_current_config(glinet):
    glinet._transport.request.side_effect = [
        {"led_enable": False},
        {},
    ]
    await glinet.led_set_enabled(enabled=True)
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args == ("call", ["led", "set_config", {"led_enable": True}], "SID")


async def test_firewall_set_dmz_enable_falls_back_to_current_ip(glinet):
    # Enabling without an explicit IP reuses the currently-configured target.
    glinet._transport.request.side_effect = [
        {"enabled": False, "dmz_ip": "192.168.8.100"},  # firewall get_dmz
        {},  # firewall set_dmz ack
    ]
    await glinet.firewall_set_dmz(enabled=True)
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args == (
        "call",
        ["firewall", "set_dmz", {"enabled": True, "dest_ip": "192.168.8.100"}],
        "SID",
    )


async def test_firewall_set_dmz_disable_sends_only_enabled_without_reading(glinet):
    glinet._transport.request.return_value = {}
    await glinet.firewall_set_dmz(enabled=False)
    # Disabling needs no target IP, so there is no read-back.
    glinet._transport.request.assert_awaited_once()
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args == ("call", ["firewall", "set_dmz", {"enabled": False}], "SID")


async def test_firewall_set_dmz_explicit_ip_skips_read(glinet):
    glinet._transport.request.return_value = {}
    await glinet.firewall_set_dmz(enabled=True, dest_ip="10.0.0.5")
    glinet._transport.request.assert_awaited_once()
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args == (
        "call",
        ["firewall", "set_dmz", {"enabled": True, "dest_ip": "10.0.0.5"}],
        "SID",
    )


async def test_firewall_set_dmz_disable_ignores_dest_ip(glinet):
    # A dest_ip passed alongside disable is meaningless and must be dropped, so
    # the write is unambiguously "turn the DMZ off".
    glinet._transport.request.return_value = {}
    await glinet.firewall_set_dmz(enabled=False, dest_ip="10.0.0.5")
    glinet._transport.request.assert_awaited_once()
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args == ("call", ["firewall", "set_dmz", {"enabled": False}], "SID")


async def test_firewall_set_dmz_enable_without_resolvable_target_raises(glinet):
    # Enabling with neither an explicit IP nor a stored dmz_ip is an invalid
    # write; raise instead of sending an ambiguous enable-with-no-target.
    glinet._transport.request.return_value = {"enabled": False}  # get_dmz, no dmz_ip
    with pytest.raises(ValueError, match="destination IP"):
        await glinet.firewall_set_dmz(enabled=True)
    # Only the get_dmz read may have happened; no set_dmz write.
    glinet._transport.request.assert_awaited_once()
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args[1] == ["firewall", "get_dmz", {}]


async def test_firewall_set_wan_access_flips_only_given_toggles(glinet):
    # Read-modify-write: only the SSH toggle changes; the rest round-trips.
    glinet._transport.request.side_effect = [
        {
            "enable_https": False,
            "enable_ping": True,
            "enable_ssh": False,
            "enable_whitelist": False,
            "whitelist": [],
        },
        {},
    ]
    await glinet.firewall_set_wan_access(ssh=True)
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args == (
        "call",
        [
            "firewall",
            "set_wan_access",
            {
                "enable_https": False,
                "enable_ping": True,
                "enable_ssh": True,
                "enable_whitelist": False,
                "whitelist": [],
            },
        ],
        "SID",
    )


async def test_firewall_set_wan_access_preserves_unknown_keys(glinet):
    # Echoing the router's own dict keeps firmware-specific keys we don't model.
    glinet._transport.request.side_effect = [
        {"enable_ssh": False, "some_future_key": 7},
        {},
    ]
    await glinet.firewall_set_wan_access(https=True)
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args[1][2] == {
        "enable_ssh": False,
        "some_future_key": 7,
        "enable_https": True,
    }


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
