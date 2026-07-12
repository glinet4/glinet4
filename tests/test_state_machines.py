"""Unit tests for GLinet's retry state machines, firmware routing, and
live-only happy paths (Phase 2, Task 5) -- against a mocked transport.

Split out from ``test_glinet_unit.py`` (which was already ~840 lines) rather
than appended there, to keep both files under the project's ~1000-line
readability guideline. Uses the same mocked-transport ``glinet`` fixture and
``build_sid_payload``-assertion pattern established in that file.
"""
# pylint: disable=missing-function-docstring,protected-access,redefined-outer-name

from unittest.mock import AsyncMock

import pytest

from glinet4.error_handling import FeatureConflictError, RetryExhausted, UnexpectedResponse

# The shared transport-mocked `glinet` fixture lives in conftest.py.


# --- tailscale_start: retry state machine -----------------------------------
# (login-required aborts -> RetryExhausted is already covered by
# test_tailscale_start_aborts_when_login_required in test_glinet_unit.py; the
# branches below were the untested remainder.)


async def test_tailscale_start_depth_limit_exhausted_raises_retry_exhausted(glinet):
    # Call straight past the recursion-depth guard instead of driving 11 real
    # recursions through side_effect: the guard is the first thing the method
    # checks, so the transport should never even be asked.
    with pytest.raises(RetryExhausted, match="10 times"):
        await glinet.tailscale_start(depth=11)
    glinet._transport.request.assert_not_awaited()


async def test_tailscale_start_connecting_then_failed_raises_retry_exhausted(glinet, monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("glinet4.glinet.asyncio.sleep", sleep)
    glinet._transport.request.side_effect = [
        {"status": 4},  # connecting
        {"status": 2},  # still not connected 3s later -> AUTHORIZATION_REQUIRED
    ]
    with pytest.raises(RetryExhausted, match="AUTHORIZATION_REQUIRED"):
        await glinet.tailscale_start()
    sleep.assert_awaited_once_with(3)


async def test_tailscale_start_unknown_status_raises_unexpected_response(glinet):
    glinet._transport.request.return_value = {"status": 42}
    with pytest.raises(UnexpectedResponse, match="42"):
        await glinet.tailscale_start()


async def test_tailscale_start_connecting_then_out_of_enum_status_raises_retry_exhausted(
    glinet, monkeypatch
):
    # Regression test: the "connecting" retry branch re-fetches status and
    # used to build the RetryExhausted message via TailscaleConnection(status)
    # .name unconditionally. A future-firmware status outside the known enum
    # (e.g. 99) made that raise a builtin ValueError instead, escaping the
    # APIClientError hierarchy entirely. It must stay a RetryExhausted with
    # the raw status in the message, not a builtin ValueError.
    sleep = AsyncMock()
    monkeypatch.setattr("glinet4.glinet.asyncio.sleep", sleep)
    glinet._transport.request.side_effect = [
        {"status": 4},  # connecting
        {"status": 99},  # still not connected 3s later -> unknown/future status
    ]
    with pytest.raises(RetryExhausted, match="99"):
        await glinet.tailscale_start()
    sleep.assert_awaited_once_with(3)


async def test_tailscale_start_sleeps_before_retrying_after_first_attempt(glinet, monkeypatch):
    # depth > 0 backoff path: still disabled after the *first* enable attempt,
    # so the loop sleeps 0.3s before recursing again. Every other start test
    # either connects on the first pass or fails outright, so this path (line
    # `if depth > 0: await asyncio.sleep(0.3)`) had no coverage at all.
    sleep = AsyncMock()
    monkeypatch.setattr("glinet4.glinet.asyncio.sleep", sleep)
    glinet._transport.request.side_effect = [
        [],  # depth 0: still disabled
        {"wan_enabled": False},  # _tailscale_set_config -> get_config
        {"ok": True},  # _tailscale_set_config -> set_config
        [],  # depth 1: still disabled -- triggers the 0.3s backoff
        {"wan_enabled": False},
        {"ok": True},
        {"status": 3},  # depth 2: connected
    ]
    assert await glinet.tailscale_start() is True
    sleep.assert_awaited_once_with(0.3)


# --- tailscale_stop: retry state machine ------------------------------------
# (login-required aborts -> RetryExhausted is already covered by
# test_tailscale_stop_aborts_when_login_required in test_glinet_unit.py.)


async def test_tailscale_stop_depth_limit_exhausted_raises_retry_exhausted(glinet):
    with pytest.raises(RetryExhausted, match="10 times"):
        await glinet.tailscale_stop(depth=11)
    glinet._transport.request.assert_not_awaited()


async def test_tailscale_stop_sleeps_before_retrying_after_first_attempt(glinet, monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("glinet4.glinet.asyncio.sleep", sleep)
    glinet._transport.request.side_effect = [
        {"status": 3},  # depth 0: still connected
        {"wan_enabled": True},  # _tailscale_set_config -> get_config
        {"ok": True},  # _tailscale_set_config -> set_config
        {"status": 4},  # depth 1: still connecting -- triggers the 0.3s backoff
        {"wan_enabled": True},
        {"ok": True},
        [],  # depth 2: disconnected
    ]
    assert await glinet.tailscale_stop() is True
    sleep.assert_awaited_once_with(0.3)


# --- _wireguard_set_client_enabled: firmware-version routing ---------------
# (unparseable-firmware -> UnexpectedResponse is already covered by
# test_wireguard_client_start_raises_clear_error_on_unparseable_firmware in
# test_glinet_unit.py; the actual routing bodies below had zero coverage.)


async def test_wireguard_set_client_enabled_new_firmware_routes_to_vpn_client(glinet):
    glinet._transport.request.side_effect = [
        {"firmware_version": "4.9.0"},  # router_info, caches the firmware version
        {"tunnel_id": 7, "enabled": True},  # vpn-client set_tunnel result
    ]
    result = await glinet.wireguard_client_start(group_id=1, peer_or_tunnel_id=7)
    assert result == {"tunnel_id": 7, "enabled": True}
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args == (
        "call",
        ["vpn-client", "set_tunnel", {"enabled": True, "tunnel_id": 7}],
        "SID",
    )


async def test_wireguard_set_client_enabled_old_firmware_start_routes_to_wg_client(glinet):
    glinet._transport.request.side_effect = [
        {"firmware_version": "4.7.0"},
        {"result": "ok"},
    ]
    await glinet.wireguard_client_start(group_id=3, peer_or_tunnel_id=9)
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args == (
        "call",
        ["wg-client", "start", {"group_id": 3, "peer_id": 9}],
        "SID",
    )


async def test_wireguard_set_client_enabled_old_firmware_stop_routes_to_wg_client(glinet):
    glinet._transport.request.side_effect = [
        {"firmware_version": "4.7.0"},
        {"result": "ok"},
    ]
    await glinet.wireguard_client_stop(peer_or_tunnel_id=9)
    last_call = glinet._transport.build_sid_payload.call_args_list[-1]
    assert last_call.args == ("call", ["wg-client", "stop"], "SID")


# --- network_acceleration_set: FeatureConflictError surfaces to the caller -


async def test_network_acceleration_set_surfaces_feature_conflict_error(glinet):
    # Reproduce the real funnel: raise_for_status raises FeatureConflictError
    # from inside transport.request itself (see test_error_handling.py's
    # test_body_level_err_code_with_conflict_wording_raises_feature_conflict_error
    # for the envelope shape this models), so the mock raises from its
    # side_effect rather than returning a value for the write call.
    glinet._transport.request.side_effect = [
        {"actype": 1, "enable": False},  # network_acceleration(): current config
        FeatureConflictError(
            "Request result reported err_code -1 (feature conflict: QoS is enabled)"
        ),
    ]
    with pytest.raises(FeatureConflictError, match="QoS is enabled"):
        await glinet.network_acceleration_set(True)


# --- live-only coverage gaps: happy paths with realistic payloads ----------


async def test_flow_stats_clear_calls_route(glinet):
    glinet._transport.request.return_value = {}
    result = await glinet.flow_stats_clear()
    assert result == {}
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["flow_statistics", "clear_statistics", {}], "SID"
    )


async def test_list_static_clients_returns_bindings(glinet):
    bindings = [
        {"mac": "AA:BB:CC:DD:EE:FF", "ip": "192.168.8.50", "name": "nas", "enabled": True},
    ]
    glinet._transport.request.return_value = bindings
    assert await glinet.list_static_clients() == bindings
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["lan", "get_static_bind_list"], "SID"
    )


async def test_router_get_load_returns_load_info(glinet):
    glinet._transport.request.return_value = {
        "load_average": [0.1, 0.05, 0.01],
        "memory_free": 123456,
        "memory_total": 262144,
    }
    load = await glinet.router_get_load()
    assert load["memory_free"] == 123456
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["system", "get_load"], "SID"
    )


async def test_router_mac_returns_factory_mac(glinet):
    glinet._transport.request.return_value = {"factory_mac": "AA:BB:CC:DD:EE:FF"}
    mac = await glinet.router_mac()
    assert mac["factory_mac"] == "AA:BB:CC:DD:EE:FF"
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["macclone", "get_mac"], "SID"
    )


async def test_connected_to_internet_reports_detected_status(glinet):
    glinet._transport.request.return_value = {"detected": 1, "ip": "203.0.113.5"}
    status = await glinet.connected_to_internet()
    assert status["detected"] == 1
    assert status["ip"] == "203.0.113.5"
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["edgerouter", "get_status"], "SID"
    )


async def test_tailscale_get_config_returns_config(glinet):
    glinet._transport.request.return_value = {
        "enabled": True,
        "exit_node_ip": "",
        "run_exit_node": False,
    }
    config = await glinet._tailscale_get_config()
    assert config == {"enabled": True, "exit_node_ip": "", "run_exit_node": False}
    glinet._transport.build_sid_payload.assert_called_once_with(
        "call", ["tailscale", "get_config"], "SID"
    )


async def test_tailscale_configured_true_when_status_non_empty(glinet):
    glinet._transport.request.return_value = {"status": 3}
    assert await glinet.tailscale_configured() is True
    # Short-circuits on a non-empty status; must not also fetch the config.
    glinet._transport.request.assert_awaited_once()
