"""Transport and authentication layer for the GL.iNet router API.

This module owns everything that touches the network: the aiohttp session,
the JSON-RPC request methods, session-id (``sid``) state, and the
challenge-response login flow with its CPU-bound password hashing. It is the
only place in the package that performs I/O — the API layer
(``glinet4.glinet.GLinet``) composes a ``GLinetTransport`` and never talks to
aiohttp directly.
"""

import asyncio
import hashlib
from ssl import SSLContext
from types import TracebackType
from typing import Any

import aiohttp
from passlib.hash import md5_crypt, sha256_crypt, sha512_crypt

from .error_handling import (
    APIClientError,
    AuthenticationError,
    UnexpectedResponse,
    raise_for_status,
)


class GLinetTransport:
    """JSON-RPC transport for the GL.iNet API.

    POSTs JSON-RPC payloads to ``base_url`` over an ``aiohttp.ClientSession``
    and shapes every response through
    :func:`glinet4.error_handling.raise_for_status`. Owns the request methods,
    ``sid`` state and the login flow.

    Session ownership: pass ``session`` to have requests routed through an
    :class:`aiohttp.ClientSession` you manage yourself — this transport will
    never close it. Without ``session``, the transport creates and owns its
    own session (lazily, on first request, since aiohttp sessions must be
    created inside a running event loop while this constructor stays
    synchronous) and :meth:`close` will close it.

    ``request_timeout`` and ``long_timeout`` are total-request timeouts in
    seconds for :meth:`request` and :meth:`request_long_timeout` respectively.
    ``ssl`` is handed through to every request: pass ``False`` (or a custom
    :class:`ssl.SSLContext`) to talk HTTPS to a router with a self-signed
    certificate; the default ``True`` keeps standard certificate checking and
    is ignored entirely for plain ``http://`` URLs.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        base_url: str,
        session: aiohttp.ClientSession | None = None,
        sid: str | None = None,
        request_timeout: float = 2,
        long_timeout: float = 5,
        ssl: bool | SSLContext = True,
    ) -> None:
        self.base_url: str = base_url
        self.sid: str | None = sid
        self._logged_in: bool = sid is not None
        self._owns_session: bool = session is None
        self._session: aiohttp.ClientSession | None = session
        self._request_timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._long_timeout = aiohttp.ClientTimeout(total=long_timeout)
        self._ssl: bool | SSLContext = ssl

    def _get_session(self) -> aiohttp.ClientSession:
        """Return the session to send through, lazily creating an owned one.

        ``self._session`` is only ever ``None`` when this transport owns its
        session (a caller-supplied one is stored at construction and never
        replaced): before the first request, and again after :meth:`close`,
        so a reused transport transparently materializes a fresh session.
        """
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session this transport owns, if any.

        Idempotent: closing resets the owned-session slot, so a second call
        finds nothing to close, while a *reused* transport (request after
        close) materializes a fresh owned session that a later close() will
        find and close again. Never closes a caller-supplied session (passed
        via ``session=``) — ownership belongs to whoever caused the session
        to exist, per the class docstring. Before any request has been made
        the owned session doesn't exist yet, and this returns without error.
        """
        if not self._owns_session:
            return
        session = self._session
        self._session = None
        if session is not None and not session.closed:
            await session.close()

    async def __aenter__(self) -> "GLinetTransport":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

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

    async def _post(self, data: dict[str, Any], client_timeout: aiohttp.ClientTimeout) -> Any:
        """POST a JSON-RPC payload and shape the response via raise_for_status.

        The payload travels as aiohttp's ``json=`` (default ``json.dumps``
        serialization, ``Content-Type: application/json``) — exactly the wire
        shape the pre-rewrite transport stack produced (pinned by the
        wire-shape characterization tests in ``tests/test_transport.py``).
        ``raise_for_status`` reads the body itself, which returns the
        connection to the pool; the ``finally: release()`` covers the paths
        where it raises before the body was fully read, so no request path
        can leak a connection.
        """
        session = self._get_session()
        response = await session.request(
            "POST", self.base_url, json=data, timeout=client_timeout, ssl=self._ssl
        )
        try:
            return await raise_for_status(response)
        finally:
            response.release()

    async def request(self, data: dict[str, Any]) -> Any:
        """Make a JSON-RPC request to the router (default 2s total timeout)."""
        return await self._post(data, self._request_timeout)

    async def request_long_timeout(self, data: dict[str, Any]) -> Any:
        """Make a JSON-RPC request to the router (default 5s total timeout)."""
        return await self._post(data, self._long_timeout)

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
