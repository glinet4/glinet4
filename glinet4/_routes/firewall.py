"""Firewall route methods for :class:`glinet4.glinet.GLinet` (mixin)."""

from typing import TYPE_CHECKING, Any

from .._types import DmzConfig, PortForwardRule, WanAccessConfig

if TYPE_CHECKING:
    from .._transport import GLinetTransport


class FirewallRoutes:
    """Firewall RPCs, mixed into :class:`glinet4.glinet.GLinet`."""

    if TYPE_CHECKING:
        _transport: GLinetTransport

        def _payload(self, method: str, params: list[Any]) -> dict[str, Any]:
            """Implemented by the composing :class:`glinet4.glinet.GLinet`."""

    async def firewall_port_forward_list(self) -> list[PortForwardRule]:
        """Return configured port-forward rules."""
        response = await self._transport.request(
            self._payload("call", ["firewall", "get_port_forward_list", {}])
        )
        result: list[PortForwardRule] = response.get("res", [])
        return result

    async def firewall_dmz(self) -> DmzConfig:
        """Return the DMZ configuration."""
        result: DmzConfig = await self._transport.request(
            self._payload("call", ["firewall", "get_dmz", {}])
        )
        return result

    async def firewall_wan_access(self) -> WanAccessConfig:
        """Return which services (ssh/https/ping) are exposed on the WAN side."""
        result: WanAccessConfig = await self._transport.request(
            self._payload("call", ["firewall", "get_wan_access", {}])
        )
        return result

    async def firewall_rule_list(self) -> list[dict[str, Any]]:
        """Return custom firewall rules."""
        response = await self._transport.request(
            self._payload("call", ["firewall", "get_rule_list", {}])
        )
        result: list[dict[str, Any]] = response.get("res", [])
        return result
