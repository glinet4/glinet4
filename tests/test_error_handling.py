"""Unit tests for glinet4.error_handling.raise_for_status."""
# pylint: disable=missing-function-docstring,unused-argument

from typing import Any

import pytest

from glinet4.error_codes import ERROR_CODES
from glinet4.error_handling import (
    AuthenticationError,
    NonZeroResponse,
    TokenError,
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
        # Current behavior raises the builtin ConnectionError for an envelope with neither
        # "result" nor "error". Phase 2 will change this to a library-specific exception type;
        # this test pins today's behavior so that migration is deliberate.
        pytest.param(
            200, {"unexpected": "shape"}, None, ConnectionError, id="missing-result-and-error"
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
