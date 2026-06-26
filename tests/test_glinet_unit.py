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
