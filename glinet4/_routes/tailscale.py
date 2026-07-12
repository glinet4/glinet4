"""Tailscale route methods and state machines for :class:`glinet4.glinet.GLinet` (mixin)."""

import asyncio
from typing import TYPE_CHECKING, Any

from glinet4.enums import TailscaleConnection

from .._types import TailscaleConfig, TailscaleExitNode, TailscaleStatus
from ..error_handling import APIClientError, RetryExhausted, UnexpectedResponse

if TYPE_CHECKING:
    from .._transport import GLinetTransport


def _tailscale_status_label(status: int) -> str:
    """Resolve a raw tailscale status int to its enum name, if known.

    Used when building exception messages from a freshly re-fetched status
    that has not been validated against :class:`TailscaleConnection` yet
    (e.g. future firmware reporting a status outside the known values).
    ``TailscaleConnection(status)`` raises a builtin ``ValueError`` for
    unknown members, which must never escape from inside an
    ``APIClientError`` message-construction path -- fall back to the raw
    int instead of letting that happen.
    """
    try:
        return TailscaleConnection(status).name
    except ValueError:
        return str(status)


class TailscaleRoutes:
    """Tailscale RPCs and connection state machines, mixed into :class:`glinet4.glinet.GLinet`."""

    if TYPE_CHECKING:
        _transport: GLinetTransport

        def _payload(self, method: str, params: list[Any]) -> dict[str, Any]:
            """Implemented by the composing :class:`glinet4.glinet.GLinet`."""

    async def _tailscale_get_config(self) -> TailscaleConfig | bool:
        """Return the tailscale config, or False if unavailable."""
        try:
            config: TailscaleConfig = await self._transport.request(
                self._payload("call", ["tailscale", "get_config"])
            )
        except APIClientError:
            return False
        return config

    async def _tailscale_set_config(self, config_updates: dict[str, Any]) -> None:
        """Merge updates into the tailscale config and apply them (ack discarded)."""
        current_config: dict[str, Any] = await self._transport.request(
            self._payload("call", ["tailscale", "get_config"])
        )
        new_config = current_config | config_updates
        await self._transport.request(
            self._payload("call", ["tailscale", "set_config", new_config])
        )

    async def _tailscale_status(self) -> TailscaleStatus | list[Any]:
        """Return the raw tailscale status."""
        result: TailscaleStatus | list[Any] = await self._transport.request(
            self._payload("call", ["tailscale", "get_status"])
        )
        return result

    async def tailscale_connection_state(self) -> TailscaleConnection:
        """Return the tailscale connection state."""
        state: dict[str, Any] = dict(await self._tailscale_status())
        if not state:
            return TailscaleConnection.DISCONNECTED
        return TailscaleConnection(state.get("status", 0))

    async def tailscale_auth_url(self) -> str | None:
        """Return the tailscale login URL, or None once authentication is complete."""
        response = await self._transport.request(
            self._payload("call", ["tailscale", "get_auth_url", {}])
        )
        if isinstance(response, dict):
            url: str | None = response.get("auth_url")
            return url
        return None

    async def tailscale_exit_node_list(self) -> list[TailscaleExitNode]:
        """Return tailnet nodes usable as exit nodes; empty when none are available.

        Logged out, the firmware answers a bare list; connected, it wraps the
        list as ``{"exit_node_list": [...]}``.
        """
        response = await self._transport.request(
            self._payload("call", ["tailscale", "get_exit_node_list", {}])
        )
        if isinstance(response, dict):
            wrapped: list[TailscaleExitNode] = response.get("exit_node_list", [])
            return wrapped
        result: list[TailscaleExitNode] = response if isinstance(response, list) else []
        return result

    async def tailscale_set_exit_node(self, *, exit_node_ip: str | None = None) -> None:
        """Route the router's traffic through a tailnet exit node.

        ``exit_node_ip`` must come from :meth:`tailscale_exit_node_list`;
        ``None`` (the default) clears the exit node (the firmware clears on
        an empty string). The firmware rejects setting an exit node while
        ``run_exit_node`` is enabled, and applying the change re-runs
        ``tailscale up`` on the router, which briefly interrupts tailscale
        traffic. The router's acknowledgement carries nothing useful and is
        discarded.
        """
        await self._tailscale_set_config({"exit_node_ip": exit_node_ip or ""})

    async def tailscale_configured(self) -> bool:
        """Return True if tailscale is configured."""
        try:
            if await self._tailscale_status() != []:
                return True
        except APIClientError:
            return False
        return await self._tailscale_get_config() is not False

    async def tailscale_start(self) -> bool:
        """Start tailscale, retrying until connected.

        Raises :class:`~glinet4.error_handling.RetryExhausted` if the
        retry-depth guard is hit, if the device is still not connected
        after the "connecting" wait, or if tailscale login/authorisation is
        required (retrying will not help; the caller must complete login via
        :meth:`tailscale_auth_url` first). Raises
        :class:`~glinet4.error_handling.UnexpectedResponse` for a connection
        status outside the known :class:`~glinet4.enums.TailscaleConnection`
        values.
        """
        return await self._tailscale_start(0)

    async def _tailscale_start(self, depth: int) -> bool:
        """Recursive worker for :meth:`tailscale_start`; ``depth`` guards the retries."""
        if depth > 10:
            raise RetryExhausted("Tailscale attempted to connect 10 times with no success")
        response: TailscaleStatus | list[Any] = await self._tailscale_status()
        if isinstance(response, list) and response == []:
            await self._tailscale_set_config({"enabled": True})
            if depth > 0:
                await asyncio.sleep(0.3)
            depth += 1
            return await self._tailscale_start(depth)
        assert isinstance(response, dict)
        status: int = response.get("status", 0)
        if status == 3:
            return True
        if status == 4:
            await asyncio.sleep(3)
            fresh = await self._tailscale_status()
            assert isinstance(fresh, dict)
            status = fresh.get("status", 0)
            if status != 3:
                raise RetryExhausted(
                    "Did not try to start tailscale as device reported 'Connecting' "
                    f"and then 3 seconds later {_tailscale_status_label(status)}"
                )
            return True
        if status in [1, 2]:
            # Not literal exhaustion: login-required is a state no retry can fix (see RetryExhausted docstring).
            raise RetryExhausted(
                "Connection not attempted as authorisation is not complete, due to "
                f"{TailscaleConnection(status).name}"
            )
        raise UnexpectedResponse(f"Unknown connection status: {status}")

    async def tailscale_stop(self) -> bool:
        """Stop tailscale, retrying until disconnected.

        Raises :class:`~glinet4.error_handling.RetryExhausted` if the
        retry-depth guard is hit, or if tailscale login/authorisation is
        required (retrying will not help; the caller must complete login via
        :meth:`tailscale_auth_url` first).
        """
        return await self._tailscale_stop(0)

    async def _tailscale_stop(self, depth: int) -> bool:
        """Recursive worker for :meth:`tailscale_stop`; ``depth`` guards the retries."""
        if depth > 10:
            raise RetryExhausted("Tailscale attempted to disconnect 10 times with no success")
        response: TailscaleStatus | list[Any] = await self._tailscale_status()
        if isinstance(response, list) and response == []:
            return True
        assert isinstance(response, dict)
        status: int = response.get("status", 0)
        if status in [3, 4]:
            await self._tailscale_set_config({"enabled": False})
            if depth > 0:
                await asyncio.sleep(0.3)
            depth += 1
            return await self._tailscale_stop(depth)
        if status in [1, 2]:
            # Not literal exhaustion: login-required is a state no retry can fix (see RetryExhausted docstring).
            raise RetryExhausted(
                "Disconnection not attempted as tailscale authorisation is not "
                f"complete, due to {TailscaleConnection(status).name}. Therefore "
                "tailscale was already not connected"
            )
        return True
