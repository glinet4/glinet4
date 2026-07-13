"""DNS, ARP, LAN, IPv6, DDNS, multi-WAN, repeater, tethering, QoS, and SQM
route methods for :class:`glinet4.glinet.GLinet` (mixin).

Multi-WAN (``kmwan``), repeater, and tethering are grouped here alongside the
Task-1 network services rather than split across ``wan.py``/new modules:
``kmwan`` is WAN-adjacent but only ``kmwan`` itself (not repeater or
tethering) would fit ``wan.py``, and neither repeater (WiFi client mode) nor
tethering (modem sharing) is a natural fit for any other existing mixin, so
keeping all seven read-only getters in one module avoids fragmenting a small,
thematically-related read surface across several near-empty ones.

QoS (``qos``) and SQM (``sqm``) -- traffic-shaping features, not WAN uplink
or service-daemon concerns -- are added here for the same reason rather than
into ``services.py``: they complete this task's network-services read
surface. They are, however, two of the FOUR features that conflict with
``services.py``'s NAT acceleration (Parental Control / QoS / SQM / DPI; see
:meth:`~glinet4.glinet.GLinet.network_acceleration_set`); see the
cross-references on :meth:`NetworkRoutes.qos_config` and
:meth:`NetworkRoutes.sqm_config` below.
"""

from typing import TYPE_CHECKING, Any

from .._types import (
    ArpEntry,
    DdnsConfig,
    DdnsStatus,
    DnsConfig,
    DnsProvider,
    Ipv6Config,
    LanInterface,
    MultiWanConfig,
    MultiWanStatus,
    QosConfig,
    RepeaterConfig,
    RepeaterStatus,
    SavedAp,
    SqmConfig,
    TetheringStatus,
)

if TYPE_CHECKING:
    from .._transport import GLinetTransport


class NetworkRoutes:
    """DNS/ARP/LAN/IPv6/DDNS/multi-WAN/repeater/tethering/QoS/SQM RPCs, mixed into :class:`glinet4.glinet.GLinet`."""

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
        response = await self._transport.request(self._payload("call", ["network", "get_arp_list"]))
        result: list[ArpEntry] = response.get("entries", [])
        return result

    async def lan_interfaces(self) -> list[LanInterface]:
        """Return the router's configured LAN/guest/IoT network segments (DHCP config).

        Each entry describes one of the router's own network segments (DHCP
        range, gateway, subnet) rather than an individual client, but
        together they map the caller's LAN topology -- treat entries as
        identifying data and avoid logging them wholesale.
        """
        response = await self._transport.request(self._payload("call", ["lan", "get_config_list"]))
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

    async def multiwan_config(self) -> MultiWanConfig:
        """Return the router's multi-WAN interface failover/load-balance configuration."""
        result: MultiWanConfig = await self._transport.request(
            self._payload("call", ["kmwan", "get_config"])
        )
        return result

    async def multiwan_status(self) -> MultiWanStatus:
        """Return per-interface multi-WAN health status."""
        result: MultiWanStatus = await self._transport.request(
            self._payload("call", ["kmwan", "get_status"])
        )
        return result

    async def repeater_config(self) -> RepeaterConfig:
        """Return the router's WiFi-repeater (client-mode) settings.

        ``macaddr`` is the repeater radio's own MAC address, not a connected
        client's.
        """
        result: RepeaterConfig = await self._transport.request(
            self._payload("call", ["repeater", "get_config"])
        )
        return result

    async def repeater_status(self) -> RepeaterStatus:
        """Return the router's WiFi-repeater connection state."""
        result: RepeaterStatus = await self._transport.request(
            self._payload("call", ["repeater", "get_status"])
        )
        return result

    async def repeater_saved_aps(self) -> list[SavedAp]:
        """Return the WiFi networks the repeater has saved credentials for.

        Each entry names an access point the caller's router has previously
        connected to as a repeater client (``ssid``, and the associating MAC
        inside ``macaddr``) -- identifying data about the caller's own
        devices and connection history; avoid logging entries wholesale (see
        :class:`~glinet4._types.SavedAp`).
        """
        response = await self._transport.request(
            self._payload("call", ["repeater", "get_saved_ap_list"])
        )
        result: list[SavedAp] = response.get("res", [])
        return result

    async def tethering_status(self) -> TetheringStatus:
        """Return USB/Bluetooth tethering connection state.

        ``devices`` is empty in the reference capture (no tethering client
        connected) -- once populated it likely carries per-device
        identifying info (e.g. a connected phone's MAC); treat entries as
        identifying data and avoid logging them wholesale.
        """
        result: TetheringStatus = await self._transport.request(
            self._payload("call", ["tethering", "get_status"])
        )
        return result

    async def tethering_config(self) -> list[dict[str, Any]]:
        """Return the router's configured tethering (USB/Bluetooth modem) profiles.

        Unlike most list-returning RPCs, ``tethering get_config``'s response
        is a bare list, not an ``{key: [...]}`` envelope (mirrors ``dns
        get_info``, see :meth:`dns_providers`). Empty when no tethering
        profiles are configured (the reference capture's state) -- that is
        the genuine shape, not an error. Entries are untyped dicts pending a
        capture from a device with tethering profiles configured.
        """
        result: list[dict[str, Any]] = await self._transport.request(
            self._payload("call", ["tethering", "get_config"])
        )
        return result

    async def qos_config(self) -> QosConfig:
        """Return the QoS (traffic-shaping) enable state and mode.

        QoS is one of the FOUR features that conflict with NAT acceleration
        (Parental Control / QoS / SQM / DPI): the router refuses to enable
        acceleration while any of them is on (see
        :meth:`~glinet4.glinet.GLinet.network_acceleration_set`). A caller
        deciding whether acceleration can be enabled should check this
        alongside :meth:`sqm_config` and
        :meth:`~glinet4.glinet.GLinet.network_acceleration`'s own
        ``dpi_enabled``/``qos_enabled`` fields, plus Parental Control's own
        getter, :meth:`~glinet4.glinet.GLinet.parental_control_config`.
        """
        result: QosConfig = await self._transport.request(
            self._payload("call", ["qos", "get_config"])
        )
        return result

    async def qos_clients(self) -> list[dict[str, Any]]:
        """Return per-client QoS bandwidth-limit entries.

        Empty when no per-client QoS rules are configured (the reference
        capture's state) -- that is the genuine shape, not an error. Entries
        are untyped dicts pending a capture from a device with QoS client
        rules configured.
        """
        response = await self._transport.request(self._payload("call", ["qos", "get_client_list"]))
        result: list[dict[str, Any]] = response.get("clients", [])
        return result

    async def qos_device_groups(self) -> list[dict[str, Any]]:
        """Return QoS device-group bandwidth-limit entries.

        Empty when no QoS device groups are configured (the reference
        capture's state) -- that is the genuine shape, not an error. Entries
        are untyped dicts pending a capture from a device with QoS device
        groups configured.
        """
        response = await self._transport.request(self._payload("call", ["qos", "get_device_group"]))
        result: list[dict[str, Any]] = response.get("group", [])
        return result

    async def sqm_config(self) -> SqmConfig:
        """Return the SQM (Smart Queue Management / bufferbloat mitigation) settings.

        SQM is one of the FOUR features that conflict with NAT acceleration
        (Parental Control / QoS / SQM / DPI): the router refuses to enable
        acceleration while any of them is on (see
        :meth:`~glinet4.glinet.GLinet.network_acceleration_set`). A caller
        deciding whether acceleration can be enabled should check this
        alongside :meth:`qos_config` and
        :meth:`~glinet4.glinet.GLinet.network_acceleration`'s own
        ``dpi_enabled``/``qos_enabled`` fields, plus Parental Control's own
        getter, :meth:`~glinet4.glinet.GLinet.parental_control_config`.
        """
        result: SqmConfig = await self._transport.request(
            self._payload("call", ["sqm", "get_config"])
        )
        return result
