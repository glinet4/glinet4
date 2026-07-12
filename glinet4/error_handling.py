"""This module contains custom exceptions and a function to handle API response status codes."""

from typing import Any

from aiohttp import ClientResponse

from .error_codes import ERROR_CODES


class APIClientError(Exception):
    """Base class for all exceptions raised by the API client"""


class UnsuccessfulRequest(APIClientError):
    """raised when the status code is not 200"""


class NonZeroResponse(APIClientError):
    """raised when the router responds but with a non 0 code"""


class AuthenticationError(NonZeroResponse):
    """raised when for authentication errors, such as invalid token or password"""


class TokenError(AuthenticationError):
    """Should be raised when the token is invalid or expired"""


class FeatureConflictError(NonZeroResponse):
    """raised when the router refuses a change because a conflicting feature is
    active (e.g. NAT acceleration vs Parental Control / QoS / SQM / DPI on
    ``set_netnat_config``), rather than because the caller isn't authenticated.

    The router reuses JSON-RPC error code -1 for both cases, so this is
    distinguished from :class:`TokenError` by inspecting the error message (see
    ``_FEATURE_CONFLICT_MESSAGE_SUBSTRING``). Unlike a stale-token error,
    retrying after a fresh login will not help: callers should surface the
    message to the user instead of looping on re-authentication.
    """


# The router answers JSON-RPC error code -1 for BOTH "not logged in" and feature
# conflicts (NAT acceleration vs Parental Control/QoS/SQM/DPI on
# `set_netnat_config`; see GLinet.network_acceleration_set's docstring in
# glinet.py). The live capture used to build this library's device fixtures
# (docs/devices/mt6000_4.9.0.json, gitignored) only probes read-only endpoints
# and does not contain a set_netnat_config conflict response to source an exact
# string from. In its absence we fall back to the documented conflict semantics
# from glinet.py and match conservatively: any -1 message mentioning "conflict"
# (case-insensitively) is treated as a feature conflict rather than an auth
# failure.
_FEATURE_CONFLICT_MESSAGE_SUBSTRING = "conflict"


def _is_feature_conflict_message(message: str) -> bool:
    """Return True if a router error message matches the feature-conflict discriminator."""
    return _FEATURE_CONFLICT_MESSAGE_SUBSTRING in message.lower()


def _catalog_suffix(code: int) -> str:
    """Return ' - <description>' for a known GL.iNet error code, or '' if the code is unknown."""
    description = ERROR_CODES.get(str(code))
    if description is None:
        return ""
    return f" - {description}"


async def raise_for_status(response: ClientResponse) -> Any:
    """Checks whether or not the response was successful."""

    # 1. Safely read the body as JSON, falling back to text if it's HTML
    try:
        # content_type=None forces aiohttp to parse it even if the router sends the wrong headers
        res = await response.json(content_type=None)
    except Exception as exc:
        text = await response.text()
        raise UnsuccessfulRequest(
            f"Request failed or returned invalid JSON (Status {response.status}): {text}"
        ) from exc

    # 2. Process the GL.iNet logic
    if 200 <= response.status < 300:
        if "result" in res:
            result = res["result"]
            # Some firmware reports errors INSIDE a successful envelope, as a
            # body-level err_code on the result rather than a top-level "error".
            if isinstance(result, dict):
                err_code = result.get("err_code", 0)
                if err_code:
                    err_message = str(result.get("err_msg", "null"))
                    if _is_feature_conflict_message(err_message):
                        raise FeatureConflictError(
                            f"Request result reported err_code {err_code} ({err_message})"
                        )
                    raise NonZeroResponse(
                        f"Request result reported err_code {err_code} ({err_message})"
                    )
            return result

        if "error" not in res:
            raise ConnectionError(f"Unexpected response from GLinet router {res}")

        if "message" not in res["error"]:
            res["error"]["message"] = "null"

        code = res["error"].get("code", 0)
        if code == -1:
            message = res["error"]["message"]
            if _is_feature_conflict_message(message):
                raise FeatureConflictError(
                    f"Request returned error code -1 ({message}){_catalog_suffix(code)}"
                )
            raise TokenError(f"Request returned error code -1 ({message}){_catalog_suffix(code)}")
        if code == -32000:
            raise AuthenticationError(
                f"Request returned error code -32000 ({res['error']['message']})"
                f"{_catalog_suffix(code)}"
            )
        if code < 0:
            raise NonZeroResponse(
                f"Request returned error code {code} with message: {res['error']['message']}"
                f"{_catalog_suffix(code)}"
            )

        return res

    raise UnsuccessfulRequest(f"Request failed with status {response.status}: {res}")
