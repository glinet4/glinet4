"""Transport and authentication layer for the GL.iNet router API.

This module owns everything that touches the network: the uplink client, the
JSON-RPC request methods, session-id (``sid``) state, and the challenge-response
login flow with its CPU-bound password hashing. It is the only place in the
package that performs I/O — the API layer (``glinet4.glinet.GLinet``) composes a
``GLinetTransport`` and never imports uplink or talks to the client directly.
"""

import asyncio
import hashlib
from typing import Any

from passlib.hash import md5_crypt, sha256_crypt, sha512_crypt
from uplink import (
    AiohttpClient,
    Body,
    Consumer,
    json,
    post,
    response_handler,
    timeout,
)

from .error_handling import (
    APIClientError,
    AuthenticationError,
    UnexpectedResponse,
    raise_for_status,
)


class GLinetTransport(Consumer):  # type: ignore[misc]
    """JSON-RPC transport for the GL.iNet API.

    Owns the uplink client, request methods, ``sid`` state and the login flow.
    """

    def __init__(
        self,
        sid: str | None = None,
        client: AiohttpClient | None = None,
        **kwargs: Any,
    ) -> None:
        self.sid: str | None = sid
        self._logged_in: bool = sid is not None
        client = client or AiohttpClient()
        super().__init__(client=client, **kwargs)

    @staticmethod
    def build_sid_payload(method: str, params: list[Any], sid: str | None = None) -> dict[str, Any]:
        """Build an authenticated JSON-RPC payload.

        Does not mutate ``params``: the session id is prepended into a new list.
        """
        return {
            "method": method,
            "jsonrpc": "2.0",
            "params": [sid, *params],
            "id": 0,
        }

    @staticmethod
    def build_no_auth_payload(method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Build an unauthenticated JSON-RPC payload (challenge / login)."""
        return {
            "method": method,
            "jsonrpc": "2.0",
            "params": params,
            "id": 0,
        }

    @response_handler(raise_for_status)  # type: ignore[untyped-decorator]
    @json  # type: ignore[untyped-decorator]
    @post("")  # type: ignore[untyped-decorator]
    @timeout(2)  # type: ignore[untyped-decorator]
    async def request(self, data: Body) -> Any:
        """Make a JSON-RPC request to the router (2s timeout)."""

    @response_handler(raise_for_status)  # type: ignore[untyped-decorator]
    @json  # type: ignore[untyped-decorator]
    @post("")  # type: ignore[untyped-decorator]
    @timeout(5)  # type: ignore[untyped-decorator]
    async def request_long_timeout(self, data: Body) -> Any:
        """Make a JSON-RPC request to the router (5s timeout)."""

    async def _challenge(self, username: str) -> Any:
        """Request a login challenge to start the login process."""
        challenge_data = self.build_no_auth_payload("challenge", {"username": username})
        return await self.request(challenge_data)

    async def _get_sid(self, username: str, hsh: str) -> Any:
        """Exchange the computed hash for a session id."""
        login_data = self.build_no_auth_payload("login", {"username": username, "hash": hsh})
        return await self.request(login_data)

    async def router_reachable(self, username: str = "root") -> bool:
        """Return True if the router answers a login challenge."""
        try:
            res = await self._challenge(username)
            if res:
                return True
        except APIClientError:
            return False
        return False

    async def login(self, username: str, password: str) -> None:
        """Log in via challenge-response and store the session id.

        Raises :class:`~glinet4.error_handling.AuthenticationError` (or a
        subclass, such as :class:`~glinet4.error_handling.TokenError`)
        unchanged, exactly as reported by the router -- including its
        message, so e.g. a -32000 catalog description survives to the
        caller. Raises :class:`~glinet4.error_handling.UnexpectedResponse`
        if the challenge response is missing an expected key, or if the
        router requested a hashing algorithm this client doesn't implement
        (with the original exception as ``__cause__``). Any other
        :class:`~glinet4.error_handling.APIClientError` is re-raised wrapped
        with the failing type named in the message.
        """

        def _compute_hash(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            alg: int,
            salt: str,
            nonce: str,
            hash_method: str,
            username: str,
            password: str,
        ) -> str:
            """Synchronous helper for CPU-bound hashing."""
            if alg == 1:  # MD5
                cipher_password = md5_crypt.using(salt=salt).hash(password)
            elif alg == 5:  # SHA-256
                cipher_password = sha256_crypt.using(salt=salt, rounds=5000).hash(password)
            elif alg == 6:  # SHA-512
                cipher_password = sha512_crypt.using(salt=salt, rounds=5000).hash(password)
            else:
                raise ValueError(
                    "Router requested unsupported hashing algorithm for cipher password"
                )

            data = f"{username}:{cipher_password}:{nonce}"
            if hash_method == "md5":
                return hashlib.md5(data.encode()).hexdigest()
            if hash_method == "sha256":
                return hashlib.sha256(data.encode()).hexdigest()
            if hash_method == "sha512":
                return hashlib.sha512(data.encode()).hexdigest()
            raise ValueError("Router requested unsupported hashing algorithm for hash")

        try:
            res = await self._challenge(username)
            alg = res["alg"]
            salt = res["salt"]
            nonce = res["nonce"]
            hash_method = res.get("hash-method", "md5")
            hsh = await asyncio.to_thread(
                _compute_hash, alg, salt, nonce, hash_method, username, password
            )
            res = await self._get_sid(username, hsh)
            if "sid" in res:
                self.sid = res["sid"]
                self._logged_in = True
        except AuthenticationError:
            # Let AuthenticationError (and subclasses like TokenError) pass through
            # unwrapped: re-wrapping with a generic message discarded the router's
            # own error text, including the -32000 catalog description.
            raise
        except (KeyError, ValueError) as e:
            # A missing challenge-response key (KeyError) or a hashing/unsupported-
            # algorithm failure (ValueError from _compute_hash) both mean the router
            # didn't give us what login() needed -- an envelope/shape violation, not
            # a programmer error, so surface it as such rather than as a builtin.
            raise UnexpectedResponse(
                f"Unexpected response from the router during login: {e}"
            ) from e
        except APIClientError as e:
            raise APIClientError(
                f"An unexpected error of type {type(e).__name__} has occurred during login: {e}"
            ) from e

    @property
    def logged_in(self) -> bool:
        """Whether a successful login has stored a session id."""
        return self._logged_in
