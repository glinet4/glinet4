"""Unit tests for glinet4.error_handling.raise_for_status."""
# pylint: disable=missing-function-docstring,unused-argument

from typing import Any

import pytest

from glinet4.error_codes import ERROR_CODES
from glinet4.error_handling import (
    APIClientError,
    AuthenticationError,
    FeatureConflictError,
    NonZeroResponse,
    TokenError,
    UnexpectedResponse,
    UnsuccessfulRequest,
    raise_for_status,
)


class FakeResponse:
    """Minimal stand-in for aiohttp.ClientResponse exposing only what raise_for_status uses."""

    def __init__(
        self,
        status: int,
        json_body: Any = None,
        json_exc: Exception | None = None,
        text_body: str = "",
    ) -> None:
        self.status = status
        self._json_body = json_body
        self._json_exc = json_exc
        self._text_body = text_body

    async def json(self, content_type: Any = None) -> Any:
        if self._json_exc is not None:
            raise self._json_exc
        return self._json_body

    async def text(self) -> str:
        return self._text_body


@pytest.mark.parametrize(
    ("status", "json_body", "json_exc", "expected_exception"),
    [
        pytest.param(
            500, {"error": "server error"}, None, UnsuccessfulRequest, id="non-2xx-status"
        ),
        pytest.param(
            200, None, ValueError("bad json"), UnsuccessfulRequest, id="json-parse-failure"
        ),
        # Phase 2, Task 3: an envelope with neither "result" nor "error" is a shape
        # violation, not a JSON-RPC error the router intentionally reported, so it
        # raises the library-specific UnexpectedResponse rather than a builtin.
        pytest.param(
            200, {"unexpected": "shape"}, None, UnexpectedResponse, id="missing-result-and-error"
        ),
        pytest.param(
            200,
            {"error": {"code": -1, "message": "bad token"}},
            None,
            TokenError,
            id="code-minus-1-is-token-error",
        ),
        pytest.param(
            200,
            {"error": {"code": -32000, "message": "denied"}},
            None,
            AuthenticationError,
            id="code-minus-32000-is-authentication-error",
        ),
        pytest.param(
            200,
            {"error": {"code": -5, "message": "other failure"}},
            None,
            NonZeroResponse,
            id="other-negative-code-is-non-zero-response",
        ),
    ],
)
async def test_raise_for_status_error_branches(status, json_body, json_exc, expected_exception):
    response = FakeResponse(
        status=status, json_body=json_body, json_exc=json_exc, text_body="raw body"
    )
    with pytest.raises(expected_exception):
        await raise_for_status(response)


async def test_exception_message_includes_router_supplied_message():
    response = FakeResponse(
        status=200, json_body={"error": {"code": -5, "message": "a distinctive router message"}}
    )
    with pytest.raises(NonZeroResponse, match="a distinctive router message"):
        await raise_for_status(response)


async def test_result_key_returns_result_value():
    response = FakeResponse(status=200, json_body={"result": {"ok": True}})
    assert await raise_for_status(response) == {"ok": True}


async def test_non_negative_error_code_returns_full_envelope():
    # A response shaped like an error envelope but with a non-negative code (e.g. 0) falls
    # through to returning the raw envelope rather than raising.
    body = {"error": {"code": 0, "message": "ok"}}
    response = FakeResponse(status=200, json_body=body)
    assert await raise_for_status(response) == body


async def test_known_catalog_code_surfaces_description_in_message():
    response = FakeResponse(
        status=200, json_body={"error": {"code": -32601, "message": "no such method"}}
    )
    with pytest.raises(NonZeroResponse, match=ERROR_CODES["-32601"]):
        await raise_for_status(response)


async def test_unknown_code_still_raises_non_zero_response():
    response = FakeResponse(
        status=200, json_body={"error": {"code": -999999, "message": "mystery failure"}}
    )
    with pytest.raises(NonZeroResponse, match="mystery failure"):
        await raise_for_status(response)


# --- Phase 2: disambiguating code -1 (auth vs feature conflict) ---------------


async def test_conflict_message_on_code_minus_1_raises_feature_conflict_error():
    response = FakeResponse(
        status=200,
        json_body={
            "error": {
                "code": -1,
                "message": "Operation conflicts with another enabled feature",
            }
        },
    )
    with pytest.raises(FeatureConflictError):
        await raise_for_status(response)


async def test_plain_minus_1_without_conflict_wording_still_raises_token_error():
    # Unchanged path: a -1 whose message doesn't match the conflict discriminator
    # is still "not logged in" and must keep raising TokenError so existing
    # HA-style "on TokenError, re-login and retry" callers keep working.
    response = FakeResponse(status=200, json_body={"error": {"code": -1, "message": "bad token"}})
    with pytest.raises(TokenError):
        await raise_for_status(response)


async def test_feature_conflict_error_is_caught_by_except_non_zero_response():
    response = FakeResponse(
        status=200,
        json_body={"error": {"code": -1, "message": "feature CONFLICT detected"}},
    )
    with pytest.raises(NonZeroResponse):
        await raise_for_status(response)


async def test_feature_conflict_error_is_caught_by_except_api_client_error():
    response = FakeResponse(
        status=200,
        json_body={"error": {"code": -1, "message": "feature CONFLICT detected"}},
    )
    with pytest.raises(APIClientError):
        await raise_for_status(response)


async def test_feature_conflict_message_match_is_case_insensitive():
    response = FakeResponse(
        status=200,
        json_body={"error": {"code": -1, "message": "CONFLICT: QoS is currently enabled"}},
    )
    with pytest.raises(FeatureConflictError):
        await raise_for_status(response)


# --- Phase 2: body-level err_code inside a successful envelope ----------------


async def test_body_level_err_code_nonzero_raises_non_zero_response_with_message():
    response = FakeResponse(
        status=200,
        json_body={"result": {"err_code": -1, "err_msg": "Missing modem_mode parameter"}},
    )
    with pytest.raises(NonZeroResponse, match="Missing modem_mode parameter"):
        await raise_for_status(response)


async def test_body_level_err_code_with_conflict_wording_raises_feature_conflict_error():
    response = FakeResponse(
        status=200,
        json_body={"result": {"err_code": -1, "err_msg": "feature conflict: QoS enabled"}},
    )
    with pytest.raises(FeatureConflictError):
        await raise_for_status(response)


async def test_body_level_err_code_zero_returns_result_unchanged():
    # Regression guard: a well-behaved response that merely echoes err_code: 0
    # inside its result body must keep returning normally.
    result = {"err_code": 0, "ok": True}
    response = FakeResponse(status=200, json_body={"result": result})
    assert await raise_for_status(response) == result


async def test_body_level_err_code_absent_returns_result_unchanged():
    # Regression guard for every existing getter: a plain dict result with no
    # err_code key at all must keep returning unchanged.
    result = {"ok": True}
    response = FakeResponse(status=200, json_body={"result": result})
    assert await raise_for_status(response) == result


async def test_result_list_returns_unchanged():
    # Regression guard: some endpoints (e.g. flow_stats_top_apps) return a bare
    # list as "result"; the body-level err_code check must not choke on that.
    response = FakeResponse(status=200, json_body={"result": [1, 2, 3]})
    assert await raise_for_status(response) == [1, 2, 3]


# --- Phase 2, Task 3: exception taxonomy consolidation ------------------------


async def test_unexpected_response_is_caught_by_except_api_client_error():
    # Hierarchy contract: UnexpectedResponse must be a genuine APIClientError
    # subclass so `except APIClientError` remains a complete safety net.
    response = FakeResponse(status=200, json_body={"unexpected": "shape"})
    with pytest.raises(APIClientError):
        await raise_for_status(response)


async def test_unexpected_response_message_includes_the_envelope():
    response = FakeResponse(status=200, json_body={"unexpected": "shape"})
    with pytest.raises(UnexpectedResponse, match="unexpected"):
        await raise_for_status(response)
