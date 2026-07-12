"""Unit tests for the GLinet transport/auth layer (no hardware)."""
# pylint: disable=missing-function-docstring,redefined-outer-name,protected-access,unused-argument

import hashlib
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from aiohttp import web
from aiohttp.client_reqrep import ConnectionKey
from aiohttp.test_utils import TestServer
from passlib.hash import md5_crypt

from glinet4._transport import GLinetTransport
from glinet4.error_handling import (
    APIClientError,
    AuthenticationError,
    TokenError,
    UnexpectedResponse,
    UnsuccessfulRequest,
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


# --- Phase 2, Task 5: sha512 login branch + the generic wrap branch -------


async def test_login_sha512_sets_sid(transport):
    # alg=6 exercises _compute_hash's sha512_crypt cipher-password branch;
    # hash-method="sha512" exercises the outer hashlib.sha512 branch -- both
    # previously untested (only md5/sha256 had coverage).
    transport.request = AsyncMock(
        side_effect=[
            {"alg": 6, "salt": "abc", "nonce": "xyz", "hash-method": "sha512"},
            {"sid": "S3"},
        ]
    )
    await transport.login("root", "pw")
    assert transport.sid == "S3"
    assert transport.logged_in is True


async def test_login_lets_unsuccessful_request_pass_through_unwrapped(transport):
    # Reviewer-found defect (glinet4-ha PR #25): login() used to catch any
    # remaining APIClientError subclass and re-raise it flattened into the
    # bare parent class ("An unexpected error of type X has occurred..."),
    # discarding the concrete type. That broke callers' `except
    # UnsuccessfulRequest` mapping (e.g. HA's cannot_connect) for exactly the
    # case it matters most: a dropped connection during login. The concrete
    # subclass must now survive unchanged, exactly like AuthenticationError
    # already does above.
    transport.request = AsyncMock(side_effect=UnsuccessfulRequest("network hiccup"))
    with pytest.raises(UnsuccessfulRequest, match="network hiccup"):
        await transport.login("root", "pw")


async def test_login_lets_dropped_connection_surface_as_unsuccessful_request():
    # The reviewer's live repro, one layer deeper than the mock above: a
    # dropped connection during the challenge/get_sid round trip raises
    # aiohttp.ClientConnectionError, which _post (not this test) wraps into
    # UnsuccessfulRequest with the original preserved as __cause__. Before the
    # fix, login()'s generic except-clause re-flattened that into a bare
    # APIClientError, so `except UnsuccessfulRequest` around glinet4.login()
    # never fired downstream.
    connection_error = aiohttp.ClientConnectionError("Connection reset by peer")
    session = MagicMock(spec=aiohttp.ClientSession)
    session.request = AsyncMock(side_effect=connection_error)
    dropped_transport = GLinetTransport(session=session, base_url="http://192.168.8.1/rpc")

    with pytest.raises(UnsuccessfulRequest) as exc_info:
        await dropped_transport.login("root", "pw")

    assert exc_info.value.__cause__ is connection_error


async def test_login_lets_unexpected_response_from_malformed_challenge_pass_through_unwrapped():
    # Another APIClientError subclass, exercised through the real
    # raise_for_status path rather than a mocked transport.request: a 200
    # challenge response with neither "result" nor "error" is an
    # envelope-shape violation, so raise_for_status raises UnexpectedResponse
    # directly. login() must let it through unflattened too, not just the two
    # subclasses above.
    session = _wire_session(FakeAiohttpResponse(200, {"nonsense": True}))
    malformed_transport = GLinetTransport(session=session, base_url="http://192.168.8.1/rpc")

    with pytest.raises(UnexpectedResponse, match="nonsense"):
        await malformed_transport.login("root", "pw")


# --- Phase 2, Task 4: session lifecycle -----------------------------------


class FakeAiohttpResponse:
    """Minimal stand-in for aiohttp.ClientResponse, matching test_error_handling's pattern."""

    def __init__(self, status: int, json_body: object) -> None:
        self.status = status
        self._json_body = json_body
        self.released = False

    async def json(self, content_type: object = None) -> object:
        return self._json_body

    async def text(self) -> str:
        return ""

    def release(self) -> None:
        self.released = True


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
    # No session given: the owned session is created lazily on first request
    # (construction is synchronous; aiohttp sessions need a running loop), so
    # before any request there is nothing to close. close() must be a safe
    # no-op rather than erroring on the not-yet-materialized session.
    transport = GLinetTransport(base_url="http://192.168.8.1/rpc")
    await transport.close()


async def test_close_closes_owned_session_once_materialized():
    # Simulate the transport having lazily materialized its owned session (as
    # it would after the first request) by poking `_session`.
    transport = GLinetTransport(base_url="http://192.168.8.1/rpc")
    mock_session = _mock_aiohttp_session()
    transport._session = mock_session
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
    transport._session = mock_session
    await transport.close()
    await transport.close()
    mock_session.close.assert_awaited_once()


async def test_close_recloses_session_materialized_after_first_close():
    # Reviewer-confirmed reproduction (Phase 2): close() on a never-
    # materialized owned session must not permanently mark the transport as
    # closed. If the (reused) transport later materializes a real owned
    # session -- as a request after close() would -- a second close() must
    # find and close *that* session rather than short-circuiting on a sticky
    # flag set by the earlier no-op.
    transport = GLinetTransport(base_url="http://192.168.8.1/rpc")
    await transport.close()  # no session yet: safe no-op

    # Simulate a request after close() lazily materializing a new session.
    mock_session = _mock_aiohttp_session()
    transport._session = mock_session

    await transport.close()

    mock_session.close.assert_awaited_once()


async def test_async_context_manager_closes_owned_session():
    mock_session = _mock_aiohttp_session()
    async with GLinetTransport(base_url="http://192.168.8.1/rpc") as transport:
        transport._session = mock_session
    mock_session.close.assert_awaited_once()


async def test_async_context_manager_does_not_swallow_exceptions():
    mock_session = _mock_aiohttp_session()
    transport = GLinetTransport(base_url="http://192.168.8.1/rpc")
    transport._session = mock_session
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


# --- Phase 3, Task 1: wire-shape characterization --------------------------
#
# These tests pin what the transport actually puts on the wire: the HTTP
# method, the exact URL, and the exact JSON-RPC envelope handed to aiohttp via
# its `json=` kwarg (which fixes both the serialization -- aiohttp's default
# json.dumps -- and the Content-Type: application/json header). They were
# written and ran GREEN against the pre-rewrite transport stack BEFORE the
# plain-aiohttp rewrite, and must stay GREEN, unmodified, after it.
#
# They deliberately assert only the wire-load-bearing kwargs (`json`, and the
# absence of a pre-serialized `data`), not the full kwargs dict: the rewrite
# adds `timeout`/`ssl` kwargs, which change nothing about the bytes of the
# request body or its target.


def _wire_session(*responses: FakeAiohttpResponse) -> MagicMock:
    """A mock aiohttp session answering request() with the given responses."""
    session = MagicMock(spec=aiohttp.ClientSession)
    session.request = AsyncMock(side_effect=list(responses))
    return session


def _posted_json(session: MagicMock, call_index: int = 0) -> object:
    """The (method, url) pair and json= body of the nth session.request call.

    Asserting `"json" in call.kwargs` pins the mock-level half of the
    Content-Type proof: aiohttp derives `Content-Type: application/json`
    (and its default `json.dumps` serialization) from the *presence* of the
    `json=` kwarg alone, never from a manually-set header. The other half --
    that a real server actually receives that header on the wire -- is
    proven by ``test_integration_mixed_requests_through_real_server_pool_one_connection``
    below, which is not mocked.
    """
    call = session.request.call_args_list[call_index]
    assert call.args == ("POST", "http://192.168.8.1/rpc")
    assert "data" not in call.kwargs  # body must go via json=, never pre-serialized
    assert "json" in call.kwargs
    assert "headers" not in call.kwargs  # no manual Content-Type override either
    return call.kwargs["json"]


async def test_wire_sid_call_posts_exact_json_rpc_envelope():
    session = _wire_session(FakeAiohttpResponse(200, {"result": {"ok": True}}))
    transport = GLinetTransport(session=session, base_url="http://192.168.8.1/rpc")
    await transport.request(
        GLinetTransport.build_sid_payload("call", ["system", "get_info"], "SID")
    )
    session.request.assert_awaited_once()
    assert _posted_json(session) == {
        "method": "call",
        "jsonrpc": "2.0",
        "params": ["SID", "system", "get_info"],
        "id": 0,
    }


async def test_wire_no_auth_call_posts_exact_json_rpc_envelope():
    session = _wire_session(FakeAiohttpResponse(200, {"result": {}}))
    transport = GLinetTransport(session=session, base_url="http://192.168.8.1/rpc")
    await transport.request(
        GLinetTransport.build_no_auth_payload("challenge", {"username": "root"})
    )
    session.request.assert_awaited_once()
    assert _posted_json(session) == {
        "method": "challenge",
        "jsonrpc": "2.0",
        "params": {"username": "root"},
        "id": 0,
    }


async def test_wire_long_timeout_call_posts_same_envelope():
    session = _wire_session(FakeAiohttpResponse(200, {"result": {}}))
    transport = GLinetTransport(session=session, base_url="http://192.168.8.1/rpc")
    await transport.request_long_timeout(
        GLinetTransport.build_sid_payload("call", ["diag", "ping", {"addr": "a"}], "SID")
    )
    session.request.assert_awaited_once()
    assert _posted_json(session) == {
        "method": "call",
        "jsonrpc": "2.0",
        "params": ["SID", "diag", "ping", {"addr": "a"}],
        "id": 0,
    }


async def test_wire_login_flow_posts_challenge_then_login_hash():
    # The full challenge-response login, end to end, down to the exact hash
    # bytes on the wire: md5_crypt cipher password over the router's salt,
    # then md5 over "username:cipher:nonce". If the rewrite perturbed the
    # login flow or its hashing in any way, this fails.
    session = _wire_session(
        FakeAiohttpResponse(
            200, {"result": {"alg": 1, "salt": "abc", "nonce": "xyz", "hash-method": "md5"}}
        ),
        FakeAiohttpResponse(200, {"result": {"sid": "SESSION"}}),
    )
    transport = GLinetTransport(session=session, base_url="http://192.168.8.1/rpc")
    await transport.login("root", "password")

    assert session.request.await_count == 2
    assert _posted_json(session, 0) == {
        "method": "challenge",
        "jsonrpc": "2.0",
        "params": {"username": "root"},
        "id": 0,
    }
    cipher_password = md5_crypt.using(salt="abc").hash("password")
    expected_hash = hashlib.md5(f"root:{cipher_password}:xyz".encode()).hexdigest()
    assert _posted_json(session, 1) == {
        "method": "login",
        "jsonrpc": "2.0",
        "params": {"username": "root", "hash": expected_hash},
        "id": 0,
    }
    assert transport.sid == "SESSION"


# --- Phase 3, Task 1: new per-instance knobs and aiohttp lifecycle ---------


async def test_ssl_kwarg_is_passed_through_to_the_request():
    # ssl=False must reach the session call so self-signed-HTTPS users can
    # opt out of certificate checking.
    session = _wire_session(FakeAiohttpResponse(200, {"result": {}}))
    transport = GLinetTransport(session=session, base_url="https://192.168.8.1/rpc", ssl=False)
    await transport.request(GLinetTransport.build_no_auth_payload("challenge", {"username": "u"}))
    assert session.request.call_args.kwargs["ssl"] is False


async def test_ssl_defaults_to_true():
    # ssl=True is aiohttp's own request default (standard certificate
    # checking; ignored entirely for http:// URLs), so the default changes
    # nothing for existing users.
    session = _wire_session(FakeAiohttpResponse(200, {"result": {}}))
    transport = GLinetTransport(session=session, base_url="http://192.168.8.1/rpc")
    await transport.request(GLinetTransport.build_no_auth_payload("challenge", {"username": "u"}))
    assert session.request.call_args.kwargs["ssl"] is True


def _sent_timeout(session: MagicMock) -> aiohttp.ClientTimeout:
    timeout = session.request.call_args.kwargs["timeout"]
    assert isinstance(timeout, aiohttp.ClientTimeout)
    return timeout


async def test_default_timeouts_are_10s_request_and_60s_long():
    # Evidence-based (live Flint 2 run): ordinary RPCs return in well under a
    # second, but diagnostics like `diag ping` block router-side for
    # multiple seconds by design -- 2s/5s were never a real effective
    # timeout under the pre-rewrite transport stack (its @timeout
    # decorators were silently ignored).
    session = _wire_session(
        FakeAiohttpResponse(200, {"result": {}}), FakeAiohttpResponse(200, {"result": {}})
    )
    transport = GLinetTransport(session=session, base_url="http://192.168.8.1/rpc")
    payload = GLinetTransport.build_sid_payload("call", ["system", "get_info"], "SID")
    await transport.request(payload)
    assert _sent_timeout(session).total == 10
    await transport.request_long_timeout(payload)
    assert _sent_timeout(session).total == 60


async def test_per_instance_timeouts_carry_configured_values():
    session = _wire_session(
        FakeAiohttpResponse(200, {"result": {}}), FakeAiohttpResponse(200, {"result": {}})
    )
    transport = GLinetTransport(
        session=session,
        base_url="http://192.168.8.1/rpc",
        request_timeout=0.5,
        long_timeout=30,
    )
    payload = GLinetTransport.build_sid_payload("call", ["system", "get_info"], "SID")
    await transport.request(payload)
    assert _sent_timeout(session).total == 0.5
    await transport.request_long_timeout(payload)
    assert _sent_timeout(session).total == 30


async def test_request_releases_response_even_when_raise_for_status_raises():
    # raise_for_status normally consumes the body (which returns the
    # connection to the pool), but every path -- including raising ones --
    # must end with the response released so no connection can leak.
    error_response = FakeAiohttpResponse(500, {"result": {}})
    session = _wire_session(error_response)
    transport = GLinetTransport(session=session, base_url="http://192.168.8.1/rpc")
    with pytest.raises(UnsuccessfulRequest):
        await transport.request(
            GLinetTransport.build_sid_payload("call", ["system", "get_info"], "SID")
        )
    assert error_response.released is True


async def test_request_timeout_raises_unsuccessful_request_with_seconds_in_message():
    # Defect 1: a bare TimeoutError (raised by aiohttp when a request exceeds
    # its ClientTimeout) must not escape the APIClientError hierarchy. The
    # router's `diag ping` RPC blocks router-side for multiple seconds by
    # design, which is exactly the scenario that trips this in production.
    session = MagicMock(spec=aiohttp.ClientSession)
    session.request = AsyncMock(side_effect=TimeoutError())
    transport = GLinetTransport(session=session, base_url="http://192.168.8.1/rpc")
    with pytest.raises(UnsuccessfulRequest) as exc_info:
        await transport.request(
            GLinetTransport.build_sid_payload("call", ["diag", "ping", {"addr": "0.0.0.1"}], "SID")
        )
    assert isinstance(exc_info.value.__cause__, TimeoutError)
    assert "10" in str(exc_info.value)  # configured request_timeout seconds


async def test_long_timeout_request_timeout_message_reports_long_timeout_seconds():
    session = MagicMock(spec=aiohttp.ClientSession)
    session.request = AsyncMock(side_effect=TimeoutError())
    transport = GLinetTransport(session=session, base_url="http://192.168.8.1/rpc")
    with pytest.raises(UnsuccessfulRequest) as exc_info:
        await transport.request_long_timeout(
            GLinetTransport.build_sid_payload("call", ["diag", "ping", {"addr": "0.0.0.1"}], "SID")
        )
    assert "60" in str(exc_info.value)  # configured long_timeout seconds


async def test_request_client_error_raises_unsuccessful_request_with_cause_preserved():
    # Defect 1: aiohttp.ClientError subclasses (DNS failure, connection
    # refused, etc.) must also be wrapped rather than propagating raw.
    os_error = ConnectionRefusedError("Connection refused")
    connection_key = ConnectionKey(
        host="192.168.8.1",
        port=80,
        is_ssl=False,
        ssl=None,
        proxy=None,
        proxy_auth=None,
        proxy_headers_hash=None,
    )
    client_error = aiohttp.ClientConnectorError(connection_key, os_error)

    session = MagicMock(spec=aiohttp.ClientSession)
    session.request = AsyncMock(side_effect=client_error)
    transport = GLinetTransport(session=session, base_url="http://192.168.8.1/rpc")
    with pytest.raises(UnsuccessfulRequest) as exc_info:
        await transport.request(
            GLinetTransport.build_sid_payload("call", ["system", "get_info"], "SID")
        )
    assert exc_info.value.__cause__ is client_error
    assert "ClientConnectorError" in str(exc_info.value)


async def test_owned_session_materializes_lazily_and_close_resets_it():
    # Construction is synchronous (pinned by test_construction_defaults);
    # the owned aiohttp session only comes to exist inside a running loop,
    # is cached across requests, and close() resets the slot so a reused
    # transport materializes a fresh one.
    transport = GLinetTransport(base_url="http://192.168.8.1/rpc")
    assert transport._session is None
    session = transport._get_session()
    assert isinstance(session, aiohttp.ClientSession)
    assert transport._get_session() is session
    await transport.close()
    assert session.closed
    assert transport._session is None


# --- Phase 3, Task 3: wire-truth verification -------------------------------
#
# The id field: both build_sid_payload and build_no_auth_payload hard-code
# `"id": 0` (see glinet4/_transport.py) -- there is no per-request unique or
# incrementing counter anywhere in this module. That is pinned below as
# CONSTANCY, deliberately, not uniqueness: every payload produced by either
# builder, across any number of calls with different methods/params, carries
# the exact same literal int 0. A regression that started emitting distinct
# or incrementing ids per call (or a string/bool masquerading as one) would
# be a wire-shape change these tests must catch.


def _is_plain_int(value: object) -> bool:
    """True only for a genuine int, excluding bool (a subclass, and 0 == False)."""
    return isinstance(value, int) and not isinstance(value, bool)


def test_sid_payload_id_field_is_the_constant_literal_zero():
    first = GLinetTransport.build_sid_payload("call", ["system", "get_info"], "SID")
    second = GLinetTransport.build_sid_payload("call", ["diag", "ping"], "SID2")
    assert first["id"] == 0
    assert second["id"] == 0
    assert _is_plain_int(first["id"])
    assert _is_plain_int(second["id"])


def test_no_auth_payload_id_field_is_the_constant_literal_zero():
    challenge = GLinetTransport.build_no_auth_payload("challenge", {"username": "root"})
    login = GLinetTransport.build_no_auth_payload("login", {"username": "root", "hash": "h"})
    assert challenge["id"] == 0
    assert login["id"] == 0
    assert _is_plain_int(challenge["id"])
    assert _is_plain_int(login["id"])


async def test_integration_mixed_requests_through_real_server_pool_one_connection():
    """The Task-1 review's deferred aiohttp.web lifecycle integration test.

    Drives five mixed requests -- two successes, a JSON-RPC error (code -1,
    "bad token" -> TokenError), another success, then an HTTP 500 ->
    UnsuccessfulRequest -- through ONE transport against a REAL aiohttp.web
    server bound to a loopback socket (nothing mocked). Afterwards it
    inspects the transport's own aiohttp connector: exactly one pooled
    (idle, reusable) connection and zero acquired (in-flight) connections at
    rest, proving every response -- including both error paths -- is fully
    read and released back to the pool rather than leaking a connection or a
    socket. It also confirms, server-side, that every request actually
    carried `Content-Type: application/json` on the wire: the mock-level
    assertions elsewhere in this file (`_posted_json`) only prove aiohttp
    *would* send that header via the `json=` kwarg; this is the real header,
    received by a real server, closing the other half of that proof.

    No sleeps; a local loopback round-trip is sub-millisecond, so this stays
    well under 1s (confirmed via `pytest --durations`).
    """
    received_content_types: list[str | None] = []
    # (status, body) for each request in order: success, success, token
    # error, success, server error.
    scripted_responses = [
        (200, {"result": {"ok": True}}),
        (200, {"result": {"ok": True}}),
        (200, {"error": {"code": -1, "message": "bad token"}}),
        (200, {"result": {"ok": True}}),
        (500, {"result": {}}),
    ]
    call_count = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal call_count
        received_content_types.append(request.content_type)
        await request.json()  # fully drain the body, as a real router would
        status, body = scripted_responses[call_count]
        call_count += 1
        return web.json_response(body, status=status)

    app = web.Application()
    app.router.add_post("/rpc", handler)
    server = TestServer(app)
    await server.start_server()
    transport = GLinetTransport(base_url=str(server.make_url("/rpc")))
    try:
        payload = GLinetTransport.build_sid_payload("call", ["system", "get_info"], "SID")

        assert await transport.request(payload) == {"ok": True}
        assert await transport.request(payload) == {"ok": True}
        with pytest.raises(TokenError):
            await transport.request(payload)
        assert await transport.request(payload) == {"ok": True}
        with pytest.raises(UnsuccessfulRequest):
            await transport.request(payload)

        assert call_count == len(scripted_responses)
        assert received_content_types == ["application/json"] * len(scripted_responses)

        assert transport._session is not None  # materialized by the first request above
        connector = transport._session.connector
        assert connector is not None
        pooled = sum(len(conns) for conns in connector._conns.values())
        assert pooled == 1
        assert len(connector._acquired) == 0
    finally:
        await transport.close()
        await server.close()
