"""Unit tests for the GLinet transport/auth layer (no hardware)."""
# pylint: disable=missing-function-docstring,redefined-outer-name

from unittest.mock import AsyncMock

import pytest

from glinet4._transport import GLinetTransport
from glinet4.error_handling import (
    APIClientError,
    AuthenticationError,
    TokenError,
    UnexpectedResponse,
)


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


async def test_login_unsupported_alg_raises_unexpected_response(transport):
    # Phase 2, Task 3: a hashing/unsupported-algorithm failure used to be masked as a
    # KeyError ("Parameter Exception:"); it now surfaces as UnexpectedResponse with the
    # original ValueError preserved as __cause__.
    transport.request = AsyncMock(
        side_effect=[{"alg": 99, "salt": "abc", "nonce": "xyz", "hash-method": "md5"}]
    )
    with pytest.raises(UnexpectedResponse) as exc_info:
        await transport.login("root", "pw")
    assert isinstance(exc_info.value.__cause__, ValueError)
    assert "unsupported hashing algorithm" in str(exc_info.value.__cause__)


async def test_login_missing_challenge_key_raises_unexpected_response(transport):
    # A challenge response missing an expected key (envelope/shape violation) also
    # becomes UnexpectedResponse rather than a builtin KeyError.
    transport.request = AsyncMock(side_effect=[{"salt": "abc", "nonce": "xyz"}])
    with pytest.raises(UnexpectedResponse) as exc_info:
        await transport.login("root", "pw")
    assert isinstance(exc_info.value.__cause__, KeyError)


async def test_login_lets_token_error_pass_through_unwrapped(transport):
    # login() must not re-wrap AuthenticationError/TokenError with a generic message:
    # doing so previously shadowed the router's own error text (issue #14).
    transport.request = AsyncMock(
        side_effect=TokenError("Request returned error code -1 (bad token)")
    )
    with pytest.raises(TokenError, match="bad token"):
        await transport.login("root", "pw")


async def test_login_lets_authentication_error_message_survive_including_catalog_text(transport):
    # The -32000 catalog description must survive to the caller instead of being
    # replaced by the generic "Authentication failed during login" message.
    transport.request = AsyncMock(
        side_effect=AuthenticationError(
            "Request returned error code -32000 (denied) - Permission denied"
        )
    )
    with pytest.raises(AuthenticationError, match="Permission denied"):
        await transport.login("root", "pw")
