"""Unit tests for the GLinet transport/auth layer (no hardware)."""
# pylint: disable=missing-function-docstring,redefined-outer-name,protected-access,unused-argument

from unittest.mock import AsyncMock, MagicMock

import aiohttp
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


# --- Phase 2, Task 4: session lifecycle -----------------------------------


class FakeAiohttpResponse:
    """Minimal stand-in for aiohttp.ClientResponse, matching test_error_handling's pattern."""

    def __init__(self, status: int, json_body: object) -> None:
        self.status = status
        self._json_body = json_body

    async def json(self, content_type: object = None) -> object:
        return self._json_body

    async def text(self) -> str:
        return ""


def _mock_aiohttp_session() -> MagicMock:
    """A MagicMock passing isinstance(x, aiohttp.ClientSession), with an async close().

    ``closed`` starts False (mirroring a real, freshly built ClientSession) and
    flips to True once ``close()`` is awaited, so tests can exercise close()'s
    session-state check the same way it behaves against the real thing.
    """
    session = MagicMock(spec=aiohttp.ClientSession)
    session.closed = False

    async def _close() -> None:
        session.closed = True

    session.close = AsyncMock(side_effect=_close)
    return session


async def test_close_is_safe_when_owned_session_never_materialized():
    # No session/client given: uplink's own lazy factory hasn't built a real
    # aiohttp.ClientSession yet (no request has been made). close() must be a
    # safe no-op rather than erroring on the not-yet-instantiated placeholder.
    transport = GLinetTransport(base_url="http://192.168.8.1/rpc")
    await transport.close()


async def test_close_closes_owned_session_once_materialized():
    # Simulate uplink having lazily materialized the real session (as it would
    # after the first request) by poking the internal client's `_session`.
    transport = GLinetTransport(base_url="http://192.168.8.1/rpc")
    mock_session = _mock_aiohttp_session()
    transport._client._session = mock_session
    await transport.close()
    mock_session.close.assert_awaited_once()


async def test_close_does_not_close_injected_session():
    mock_session = _mock_aiohttp_session()
    transport = GLinetTransport(session=mock_session, base_url="http://192.168.8.1/rpc")
    await transport.close()
    mock_session.close.assert_not_awaited()


async def test_close_is_idempotent_on_owned_session():
    transport = GLinetTransport(base_url="http://192.168.8.1/rpc")
    mock_session = _mock_aiohttp_session()
    transport._client._session = mock_session
    await transport.close()
    await transport.close()
    mock_session.close.assert_awaited_once()


async def test_close_recloses_session_materialized_after_first_close():
    # Reviewer-confirmed reproduction: close() on a never-materialized owned
    # session must not permanently mark the transport as closed. If the
    # (reused) transport later materializes a real owned session -- e.g. via
    # uplink's lazy AiohttpClient after a subsequent request -- a second
    # close() must find and close *that* session rather than short-circuiting
    # on a sticky flag set by the earlier no-op.
    transport = GLinetTransport(base_url="http://192.168.8.1/rpc")
    await transport.close()  # no session yet: safe no-op

    # Simulate uplink lazily materializing a real session after reuse.
    mock_session = _mock_aiohttp_session()
    transport._client._session = mock_session
    transport._client._auto_created_session = True

    await transport.close()

    mock_session.close.assert_awaited_once()
    assert transport._client._auto_created_session is False


async def test_async_context_manager_closes_owned_session():
    mock_session = _mock_aiohttp_session()
    async with GLinetTransport(base_url="http://192.168.8.1/rpc") as transport:
        transport._client._session = mock_session
    mock_session.close.assert_awaited_once()


async def test_async_context_manager_does_not_swallow_exceptions():
    mock_session = _mock_aiohttp_session()
    transport = GLinetTransport(base_url="http://192.168.8.1/rpc")
    transport._client._session = mock_session
    with pytest.raises(ValueError, match="boom"):
        async with transport:
            raise ValueError("boom")
    mock_session.close.assert_awaited_once()


async def test_injected_session_routes_requests_through_it():
    fake_session = MagicMock(spec=aiohttp.ClientSession)
    fake_session.request = AsyncMock(
        return_value=FakeAiohttpResponse(200, {"result": {"ok": True}})
    )
    transport = GLinetTransport(session=fake_session, base_url="http://192.168.8.1/rpc")
    result = await transport.request({"method": "call", "jsonrpc": "2.0", "params": [], "id": 0})
    assert result == {"ok": True}
    fake_session.request.assert_awaited_once()
