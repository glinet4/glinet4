"""Asynchronous client for the GL.iNet router API.

``GLinet`` is the API/protocol layer: thin methods that build JSON-RPC params,
delegate I/O to a :class:`glinet4._transport.GLinetTransport`, and shape the
responses. It owns protocol knowledge (firmware-version VPN routing) and
higher-level orchestration (client filtering, wifi reshaping, the tailscale
connection state machines) but performs no I/O itself.
"""

from types import TracebackType
from typing import Any

import aiohttp
from semver import Version

from ._routes import (
    ClientsRoutes,
    FanRoutes,
    FirewallRoutes,
    NetworkRoutes,
    ServicesRoutes,
    SystemRoutes,
    TailscaleRoutes,
    VpnRoutes,
    WanRoutes,
    WifiRoutes,
)
from ._transport import GLinetTransport
from .error_handling import UnexpectedResponse

# typical base url http://192.168.8.1/rpc


class GLinet(
    SystemRoutes,
    WifiRoutes,
    WanRoutes,
    ClientsRoutes,
    VpnRoutes,
    TailscaleRoutes,
    ServicesRoutes,
    FirewallRoutes,
    NetworkRoutes,
    FanRoutes,
):
    """A Python client for the GL.iNet API (API/protocol layer).

    Supports use as an async context manager, which closes the underlying
    session on exit::

        async with GLinet("http://192.168.8.1/rpc") as router:
            await router.login("root", "password")
            ...

    Pass ``session`` to route requests through an ``aiohttp.ClientSession``
    you manage yourself -- ``GLinet`` will never close a session it didn't
    create (see :meth:`close`).
    """

    def __init__(
        self,
        base_url: str,
        sid: str | None = None,
        session: aiohttp.ClientSession | None = None,
        **kwargs: Any,
    ) -> None:
        self._transport = GLinetTransport(sid=sid, session=session, base_url=base_url, **kwargs)
        self._firmware_version: Version | None = None
        self._firmware_version_raw: str | None = None

    async def close(self) -> None:
        """Close the session this client owns, if any (see :class:`GLinetTransport`).

        Idempotent; never closes a caller-supplied ``session``.
        """
        await self._transport.close()

    async def __aenter__(self) -> "GLinet":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    # --- session / auth delegation -------------------------------------------

    @property
    def sid(self) -> str | None:
        """The current session id (delegated to the transport)."""
        return self._transport.sid

    @sid.setter
    def sid(self, value: str | None) -> None:
        self._transport.sid = value

    @property
    def logged_in(self) -> bool:
        """Whether the client has a valid session (delegated to the transport)."""
        return self._transport.logged_in

    async def login(self, username: str, password: str) -> None:
        """Log in to the router and store the session id."""
        await self._transport.login(username, password)

    async def router_reachable(self, username: str = "root") -> bool:
        """Return True if the router answers a login challenge."""
        return await self._transport.router_reachable(username)

    # --- payload helper ------------------------------------------------------

    def _payload(self, method: str, params: list[Any]) -> dict[str, Any]:
        """Build an authenticated JSON-RPC payload for the current session."""
        return self._transport.build_sid_payload(method, params, self.sid)

    # --- shared firmware-version machinery ------------------------------------

    async def _require_firmware_version(self) -> Version:
        """Return the cached firmware version, fetching it via router_info if needed.

        Raises :class:`~glinet4.error_handling.UnexpectedResponse` with the
        original firmware string if it could not be parsed as a version --
        unlike :meth:`router_info`, the WireGuard client-API routing below
        genuinely needs a comparable version, so this is the one place that
        raises for an unparseable firmware string.
        """
        if self._firmware_version is None:
            await self.router_info()
        firmware_version = self._firmware_version
        if firmware_version is None:
            raise UnexpectedResponse(
                "Cannot determine the WireGuard client API (legacy wg-client "
                "vs. new vpn-client) because the router's firmware version "
                f"{self._firmware_version_raw!r} could not be parsed."
            )
        return firmware_version
