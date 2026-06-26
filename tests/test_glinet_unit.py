"""Unit tests for GLinet's API/orchestration layer against a mocked transport."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from semver import Version

from gli4py.enums import TailscaleConnection
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
