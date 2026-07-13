"""DNS, ARP, LAN, IPv6, and DDNS route methods for :class:`glinet4.glinet.GLinet` (mixin)."""

from typing import TYPE_CHECKING, Any

from .._types import (
    ArpEntry,
    DdnsConfig,
    DdnsStatus,
    DnsConfig,
    DnsProvider,
    Ipv6Config,
    LanInterface,
)

if TYPE_CHECKING:
    from .._transport import GLinetTransport


class NetworkRoutes:
    """DNS/ARP/LAN/IPv6/DDNS RPCs, mixed into :class:`glinet4.glinet.GLinet`."""

    if TYPE_CHECKING:
        _transport: GLinetTransport

        def _payload(self, method: str, params: list[Any]) -> dict[str, Any]:
            """Implemented by the composing :class:`glinet4.glinet.GLinet`."""

    async def dns_config(self) -> DnsConfig:
        """Return the router's DNS resolution mode and provider settings."""
        result: DnsConfig = await self._transport.request(
            self._payload("call", ["dns", "get_config"])
        )
        return result

    async def dns_providers(self) -> list[DnsProvider]:
        """Return the router's built-in DNS provider catalogue (DoH/DoT/DoQ presets).

        Unlike most list-returning RPCs, ``dns get_info``'s response is a
        bare list, not an ``{key: [...]}`` envelope, so it is returned as
        received. Each entry's ``server_list[].address``/``address6`` are
        the provider's own published resolver IPs (vendor constants, e.g. a
        filtering-DNS vendor's anycast addresses) -- not data about the
        caller or its network.
        """
        result: list[DnsProvider] = await self._transport.request(
            self._payload("call", ["dns", "get_info"])
        )
        return result

    async def arp_table(self) -> list[ArpEntry]:
        """Return the router's ARP cache.

        Each entry identifies one of the caller's own LAN clients (MAC and
        IP address). Correct for a library to return -- the owner is asking
        their own router for their own client list -- but treat entries as
        identifying data and avoid logging them wholesale.
        """
        response = await self._transport.request(
            self._payload("call", ["network", "get_arp_list"])
        )
        result: list[ArpEntry] = response.get("entries", [])
        return result

    async def lan_interfaces(self) -> list[LanInterface]:
        """Return the router's configured LAN/guest/IoT network segments (DHCP config).

        Each entry describes one of the router's own network segments (DHCP
        range, gateway, subnet) rather than an individual client, but
        together they map the caller's LAN topology -- treat entries as
        identifying data and avoid logging them wholesale.
        """
        response = await self._transport.request(
            self._payload("call", ["lan", "get_config_list"])
        )
        result: list[LanInterface] = response.get("interfaces", [])
        return result

    async def ipv6_config(self) -> Ipv6Config:
        """Return the router's IPv6 enablement and LAN addressing mode."""
        result: Ipv6Config = await self._transport.request(
            self._payload("call", ["ipv6", "get_ipv6"])
        )
        return result

    async def ddns_config(self) -> DdnsConfig:
        """Return the router's Dynamic DNS (GL.iNet cloud DDNS) enrollment."""
        result: DdnsConfig = await self._transport.request(
            self._payload("call", ["ddns", "get_config"])
        )
        return result

    async def ddns_status(self) -> DdnsStatus:
        """Return the current DDNS-mapped address and per-interface IPs."""
        result: DdnsStatus = await self._transport.request(
            self._payload("call", ["ddns", "get_status"])
        )
        return result
