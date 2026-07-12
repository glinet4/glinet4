"""WAN and network-status route methods for :class:`glinet4.glinet.GLinet` (mixin)."""

from typing import TYPE_CHECKING, Any

from .._types import (
    EthernetPortStatus,
    NetworkInterfaceStatus,
    TrafficSpeed,
    WanCableState,
    WanInterfaceInfo,
    WanStatus,
)

if TYPE_CHECKING:
    from .._transport import GLinetTransport


class WanRoutes:
    """WAN RPCs, mixed into :class:`glinet4.glinet.GLinet`."""

    if TYPE_CHECKING:
        _transport: GLinetTransport

        def _payload(self, method: str, params: list[Any]) -> dict[str, Any]:
            """Implemented by the composing :class:`glinet4.glinet.GLinet`."""

    async def ping(self, address: str) -> bool:
        """Ping an address from the router; True if reachable.

        Firmware 4.9 returns ``{"ping_result": "<ping stdout>"}`` even on
        failure, so reachability means at least one reply line; older
        firmware returns ``[]`` when unsuccessful.
        """
        result = await self._transport.request_long_timeout(
            self._payload("call", ["diag", "ping", {"addr": address}])
        )
        if isinstance(result, dict) and "ping_result" in result:
            return "bytes from" in result["ping_result"]
        return bool(result != [])

    async def wan_upstream_router_detected(self) -> bool:
        """Return True when the router's upstream-router probe reports detection.

        Wraps ``edgerouter get_status``, mapping its ``detected`` field to a
        bool (non-zero means detected). Caveat: the RPC probes for an upstream
        or edge router (a double-NAT indicator), not end-to-end reachability --
        a fw 4.9.0 Flint 2 with a working public WAN has been observed
        reporting ``detected: 0`` -- so use :meth:`ping` when a positive
        internet-reachability answer is needed.

        Routed through the long timeout: the router-side upstream probe
        can block for multiple seconds, the same class of delay
        :meth:`ping`'s ``diag ping`` RPC exhibits.
        """
        response = await self._transport.request_long_timeout(
            self._payload("call", ["edgerouter", "get_status"])
        )
        if isinstance(response, dict):
            return bool(response.get("detected"))
        return False

    async def wan_cable_state(self) -> WanCableState:
        """Return WAN cable presence and macclone flags."""
        result: WanCableState = await self._transport.request(
            self._payload("call", ["network", "check_wan_cable", {}])
        )
        return result

    async def wan_status(self) -> WanStatus:
        """Return the WAN connection status (protocol, IPv4 address/gateway/DNS)."""
        result: WanStatus = await self._transport.request(
            self._payload("call", ["cable", "get_status"])
        )
        return result

    async def wan_info(self) -> list[WanInterfaceInfo]:
        """Return address details for each WAN interface."""
        response = await self._transport.request(self._payload("call", ["lan", "get_wan_info"]))
        result: list[WanInterfaceInfo] = response.get("wan_info", [])
        return result

    async def ethernet_ports_status(self) -> list[EthernetPortStatus]:
        """Return link status for each ethernet port."""
        response = await self._transport.request(
            self._payload("call", ["cable", "get_ports_status"])
        )
        result: list[EthernetPortStatus] = response.get("ports", [])
        return result

    async def network_mode(self) -> str:
        """Return the operating mode (e.g. ``router``, ``ap``, ``repeater``)."""
        response = await self._transport.request(self._payload("call", ["netmode", "get_mode"]))
        mode: str = response.get("mode", "")
        return mode

    async def network_interfaces_status(self) -> list[NetworkInterfaceStatus]:
        """Return online/up state for each network interface."""
        response = await self._transport.request(
            self._payload("call", ["system", "get_network_status"])
        )
        result: list[NetworkInterfaceStatus] = response.get("network", [])
        return result

    async def wan_speed(self) -> TrafficSpeed:
        """Return WAN rx/tx rates in bytes per second."""
        result: TrafficSpeed = await self._transport.request(
            self._payload("call", ["clients", "get_wan_speed", {}])
        )
        return result
