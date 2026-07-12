"""WiFi route methods for :class:`glinet4.glinet.GLinet` (mixin)."""

from typing import TYPE_CHECKING, Any, cast

from .._types import MloConfig, WifiIface, WifiRadioStatus
from ..error_handling import UnexpectedResponse

if TYPE_CHECKING:
    from .._transport import GLinetTransport


class WifiRoutes:
    """WiFi RPCs, mixed into :class:`glinet4.glinet.GLinet`."""

    if TYPE_CHECKING:
        _transport: GLinetTransport

        def _payload(self, method: str, params: list[Any]) -> dict[str, Any]:
            """Implemented by the composing :class:`glinet4.glinet.GLinet`."""

    async def _wifi_config_get(self) -> dict[str, Any]:
        """Retrieve the raw wifi configuration."""
        result: dict[str, Any] = await self._transport.request(
            self._payload("call", ["wifi", "get_config"])
        )
        return result

    async def wifi_status(self) -> list[WifiRadioStatus]:
        """Return per-radio wifi status (band, channel, state)."""
        response = await self._transport.request(self._payload("call", ["wifi", "get_status", {}]))
        result: list[WifiRadioStatus] = response.get("res", [])
        return result

    async def wifi_mlo_config(self) -> MloConfig:
        """Return the MLO (WiFi 7 multi-link) configuration."""
        response = await self._transport.request(
            self._payload("call", ["wifi", "get_mlo_config", {}])
        )
        result: MloConfig = response.get("res", {})
        return result

    async def _wifi_config_set(self, config: dict[str, Any]) -> None:
        """Apply a wifi configuration change (the ack carries nothing useful)."""
        await self._transport.request(self._payload("call", ["wifi", "set_config", config]))

    async def wifi_ifaces(self, *, redact_keys: bool = True) -> dict[str, WifiIface]:
        """Return wifi interfaces keyed by name; keys redacted unless asked."""
        wifi_config = await self._wifi_config_get()
        return {
            iface.get("name"): cast(
                WifiIface, {**iface, "key": None if redact_keys else iface.get("key")}
            )
            for dev in wifi_config.get("res", [])
            for iface in dev.get("ifaces")
        }

    async def wifi_iface_set_enabled(self, iface_name: str, *, enabled: bool) -> None:
        """Enable/disable a wifi interface by name.

        Raises :class:`~glinet4.error_handling.UnexpectedResponse` if
        ``iface_name`` isn't among the interfaces the router currently
        reports (see :meth:`wifi_ifaces`). The router's acknowledgement
        carries nothing useful and is discarded; confirm the change by
        re-reading :meth:`wifi_ifaces`.
        """
        ifaces = await self.wifi_ifaces()
        if iface_name not in ifaces:
            raise UnexpectedResponse("iface_name does not exist")
        await self._wifi_config_set({"enabled": enabled, "iface_name": iface_name})
