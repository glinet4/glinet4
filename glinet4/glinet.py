"""Asynchronous client for the GL.iNet router API.

``GLinet`` is the API/protocol layer: thin methods that build JSON-RPC params,
delegate I/O to a :class:`glinet4._transport.GLinetTransport`, and shape the
responses. It owns protocol knowledge (firmware-version VPN routing) and
higher-level orchestration (client filtering, wifi reshaping, the tailscale
connection state machines) but performs no I/O itself.
"""

import asyncio
import re
from typing import Any, cast

import pydantic
from semver import Version
from uplink import AiohttpClient

from glinet4.enums import TailscaleConnection

from ._transport import GLinetTransport
from ._types import (
    AdguardConfig,
    Client,
    ClientsStatus,
    DiskInfo,
    DmzConfig,
    EthernetPortStatus,
    FirmwareCheck,
    FlowStatsApp,
    FlowStatsRule,
    LedConfig,
    MloConfig,
    NetworkAcceleration,
    NetworkInterfaceStatus,
    PortForwardRule,
    RouterInfo,
    RouterStatus,
    TailscaleConfig,
    TailscaleExitNode,
    TailscaleStatus,
    TimezoneConfig,
    TorConfig,
    TrafficSpeed,
    UpgradeConfig,
    UsbInfoEntry,
    WanAccessConfig,
    WanCableState,
    WanInterfaceInfo,
    WanStatus,
    WifiIface,
    WifiRadioStatus,
    WireguardClientConfig,
    WireguardClientStatus,
    ZerotierConfig,
)
from .error_handling import APIClientError

# Force Pydantic to resolve its lazy imports to prevent HA event loop blocking
_ = pydantic.BaseModel

# typical base url http://192.168.8.1/rpc
# Version(4, 8, 0, 0)'s 4th positional arg is `prerelease`, not a 4th version
# segment, so this is semver prerelease "4.8.0-0" -- below every real 4.8.0
# release. That's intentional: "4.8.0-beta" firmware also compares >= this,
# so beta firmware is routed to the new vpn-client API too.
NEW_VPN_CLIENT_VERSION = Version(4, 8, 0, 0)

_FIRMWARE_VERSION_PREFIX = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _parse_firmware_version(raw: str) -> Version | None:
    """Parse a firmware version string, tolerating non-semver formats.

    Most firmware reports plain 3-segment semver ("4.9.0"), but some report a
    4th build segment ("4.7.0.1"), which strict semver rejects outright.
    Coerce by keeping only the leading numeric major[.minor[.patch]]
    segments and re-parsing those; if the string has no leading numeric
    segment at all, give up and return None rather than raising.
    """
    try:
        return Version.parse(raw)
    except ValueError:
        pass
    match = _FIRMWARE_VERSION_PREFIX.match(raw)
    if match is None:
        return None
    coerced = ".".join(group for group in match.groups() if group is not None)
    try:
        return Version.parse(coerced, optional_minor_and_patch=True)
    except ValueError:
        return None


class GLinet:
    """A Python client for the GL.iNet API (API/protocol layer)."""

    def __init__(
        self,
        sid: str | None = None,
        client: AiohttpClient | None = None,
        **kwargs: Any,
    ) -> None:
        self._transport = GLinetTransport(sid=sid, client=client, **kwargs)
        self._firmware_version: Version | None = None
        self._firmware_version_raw: str | None = None

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

    @staticmethod
    def gen_sid_payload(method: str, params: list[Any], sid: str | None = None) -> dict[str, Any]:
        """Deprecated compatibility shim for the authenticated payload builder.

        Retained so callers that built payloads via ``GLinet.gen_sid_payload``
        keep working. New code should use the transport's ``build_sid_payload``.
        Like that builder, this does not mutate ``params``.
        """
        return GLinetTransport.build_sid_payload(method, params, sid)

    @staticmethod
    def gen_no_auth_payload(method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Deprecated compatibility shim for the unauthenticated payload builder.

        Retained for backward compatibility; new code should use the
        transport's ``build_no_auth_payload``.
        """
        return GLinetTransport.build_no_auth_payload(method, params)

    # --- raw API methods (one per RPC) ---------------------------------------

    async def router_info(self) -> RouterInfo:
        """Retrieve router information; caches the firmware version.

        Tolerates non-semver firmware version strings (see
        :func:`_parse_firmware_version`): this call never raises for an
        unparseable version, it just caches ``None``. Only callers that
        genuinely need a comparable version (the WireGuard client-API gate,
        via :meth:`_require_firmware_version`) raise, with the original
        string in the message.
        """
        response: RouterInfo = await self._transport.request(
            self._payload("call", ["system", "get_info"])
        )
        if "firmware_version" not in response:
            raise ValueError("No firmware version found in router info")
        self._firmware_version_raw = response["firmware_version"]
        self._firmware_version = _parse_firmware_version(response["firmware_version"])
        return response

    async def router_get_status(self) -> RouterStatus:
        """Retrieve router status, with wifi passwords redacted."""
        response: RouterStatus = await self._transport.request(
            self._payload("call", ["system", "get_status"])
        )
        if "wifi" in response:
            for i, _ in enumerate(response["wifi"]):
                response["wifi"][i]["passwd"] = None
        return response

    async def router_get_load(self) -> Any:
        """Retrieve router load information."""
        return await self._transport.request(self._payload("call", ["system", "get_load"]))

    async def router_unixtime(self) -> int:
        """Return the router's current unix time."""
        response = await self._transport.request(
            self._payload("call", ["system", "get_unixtime", {}])
        )
        time: int = response.get("time", 0)
        return time

    async def router_disk_info(self) -> DiskInfo:
        """Return disk usage for the root and tmp mounts."""
        result: DiskInfo = await self._transport.request(
            self._payload("call", ["system", "disk_info", {}])
        )
        return result

    async def router_usb_info(self) -> list[UsbInfoEntry]:
        """Return details of the router's USB ports."""
        result: list[UsbInfoEntry] = await self._transport.request(
            self._payload("call", ["system", "get_usb_info", {}])
        )
        return result

    async def router_timezone_config(self) -> TimezoneConfig:
        """Return the router's timezone configuration."""
        result: TimezoneConfig = await self._transport.request(
            self._payload("call", ["system", "get_timezone_config", {}])
        )
        return result

    async def router_mac(self) -> Any:
        """Retrieve the router's MAC address."""
        return await self._transport.request(self._payload("call", ["macclone", "get_mac"]))

    async def router_reboot(self, delay: int = 0) -> Any:
        """Reboot the router."""
        return await self._transport.request(
            self._payload("call", ["system", "reboot", {"delay": delay}])
        )

    async def flow_stats_rule(self) -> FlowStatsRule:
        """Return the flow-statistics collection rule (enable/type/period)."""
        result: FlowStatsRule = await self._transport.request(
            self._payload("call", ["flow_statistics", "get_statistics_rule", {}])
        )
        return result

    async def flow_stats_set_enabled(
        self, enabled: bool, stat_type: str = "app", period: str = "day"
    ) -> Any:
        """Enable or disable flow-statistics collection.

        Note: on this hardware the DPI accounting that fills per-app statistics
        rides on NAT acceleration, which conflicts with QoS/SQM. Enabling the
        rule starts the collector, but populated app data also requires
        :meth:`network_acceleration` to be on (see ``network_acceleration_set``).
        """
        return await self._transport.request(
            self._payload(
                "call",
                [
                    "flow_statistics",
                    "set_statistics_rule",
                    {"enable": enabled, "type": stat_type, "time": period},
                ],
            )
        )

    async def flow_stats_top_apps(self) -> list[FlowStatsApp]:
        """Return the top applications by traffic.

        Disabled, the firmware answers a bare list; enabled, it wraps the list
        as ``{"top_apps": [...]}``.
        """
        response = await self._transport.request(
            self._payload("call", ["flow_statistics", "get_top_app_flow_statistics", {}])
        )
        if isinstance(response, dict):
            wrapped: list[FlowStatsApp] = response.get("top_apps", [])
            return wrapped
        return response if isinstance(response, list) else []

    async def flow_stats_clear(self) -> Any:
        """Clear all collected flow statistics."""
        return await self._transport.request(
            self._payload("call", ["flow_statistics", "clear_statistics", {}])
        )

    async def network_acceleration(self) -> NetworkAcceleration:
        """Return the NAT/DPI acceleration state."""
        result: NetworkAcceleration = await self._transport.request(
            self._payload("call", ["network", "get_netnat_config", {}])
        )
        return result

    async def network_acceleration_set(self, enabled: bool) -> Any:
        """Enable or disable NAT acceleration.

        The router rejects the change with ``err_code`` -1 and a message when a
        conflicting feature (Parental Control / QoS / SQM / DPI) is active, so
        callers should surface that message rather than assume success.
        """
        current = await self.network_acceleration()
        return await self._transport.request(
            self._payload(
                "call",
                [
                    "network",
                    "set_netnat_config",
                    {
                        "enable": enabled,
                        "actype": current.get("actype", 1),
                        "wifi_reload": False,
                    },
                ],
            )
        )

    async def adguard_config(self) -> AdguardConfig:
        """Return the AdGuard Home enable/DNS state."""
        result: AdguardConfig = await self._transport.request(
            self._payload("call", ["adguardhome", "get_config", {}])
        )
        return result

    async def tor_config(self) -> TorConfig:
        """Return the Tor client configuration."""
        result: TorConfig = await self._transport.request(
            self._payload("call", ["tor", "get_config", {}])
        )
        return result

    async def zerotier_config(self) -> ZerotierConfig:
        """Return the ZeroTier configuration."""
        result: ZerotierConfig = await self._transport.request(
            self._payload("call", ["zerotier", "get_config", {}])
        )
        return result

    async def led_config(self) -> LedConfig:
        """Return the LED configuration."""
        result: LedConfig = await self._transport.request(
            self._payload("call", ["led", "get_config", {}])
        )
        return result

    async def led_set_enabled(self, enabled: bool) -> Any:
        """Enable or disable the router LEDs, preserving other LED settings."""
        current: dict[str, Any] = dict(await self.led_config())
        new_config = current | {"led_enable": enabled}
        return await self._transport.request(
            self._payload("call", ["led", "set_config", new_config])
        )

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

    async def firmware_check_online(self) -> FirmwareCheck:
        """Check online for a firmware update; ``new_*`` keys appear when one exists."""
        result: FirmwareCheck = await self._transport.request(
            self._payload("call", ["upgrade", "check_firmware_online", {}])
        )
        return result

    async def upgrade_config(self) -> UpgradeConfig:
        """Return the automatic-upgrade configuration."""
        result: UpgradeConfig = await self._transport.request(
            self._payload("call", ["upgrade", "get_config", {}])
        )
        return result

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

    async def connected_to_internet(self) -> Any:
        """Return the upstream/edge-router connectivity status."""
        return await self._transport.request(self._payload("call", ["edgerouter", "get_status"]))

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

    async def clients_speed(self) -> TrafficSpeed:
        """Return aggregate client-side rx/tx rates in bytes per second."""
        result: TrafficSpeed = await self._transport.request(
            self._payload("call", ["clients", "get_speed", {}])
        )
        return result

    async def wan_speed(self) -> TrafficSpeed:
        """Return WAN rx/tx rates in bytes per second."""
        result: TrafficSpeed = await self._transport.request(
            self._payload("call", ["clients", "get_wan_speed", {}])
        )
        return result

    async def clients_status(self) -> ClientsStatus:
        """Return wired/wireless client counts."""
        result: ClientsStatus = await self._transport.request(
            self._payload("call", ["clients", "get_status", {}])
        )
        return result

    async def client_set_blocked(self, mac: str, blocked: bool) -> Any:
        """Block or unblock a client's network access by MAC.

        Adds (``blocked=True``) or removes (``blocked=False``) the MAC from the
        router's black list and restarts the filter service. The client's
        ``blocked`` flag (see :meth:`connected_clients`) reflects the new state
        on the next poll. Assumes the black/white list is in ``black`` mode.
        """
        return await self._transport.request(
            self._payload(
                "call",
                [
                    "black_white_list",
                    "set_single_mac",
                    {
                        "mode": "black",
                        "operate": "add" if blocked else "del",
                        "mac": mac,
                    },
                ],
            )
        )

    async def blocked_client_macs(self) -> set[str]:
        """Return the MACs of all clients currently blocked."""
        all_clients = await self.list_all_clients()
        return {client["mac"] for client in all_clients["clients"] if client.get("blocked")}

    async def list_all_clients(self) -> dict[str, list[Client]]:
        """Get all clients known to the router."""
        result: dict[str, list[Client]] = await self._transport.request(
            self._payload("call", ["clients", "get_list"])
        )
        return result

    async def list_static_clients(self) -> Any:
        """Get all statically-bound clients."""
        return await self._transport.request(self._payload("call", ["lan", "get_static_bind_list"]))

    async def _wifi_config_get(self) -> Any:
        """Retrieve the raw wifi configuration."""
        return await self._transport.request(self._payload("call", ["wifi", "get_config"]))

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

    async def _wifi_config_set(self, config: dict[str, Any]) -> Any:
        """Apply a wifi configuration change."""
        return await self._transport.request(self._payload("call", ["wifi", "set_config", config]))

    # --- higher-level orchestration helpers ----------------------------------

    async def connected_clients(self) -> dict[str, Client]:
        """Return online clients keyed by MAC address."""
        clients: dict[str, Client] = {}
        all_clients = await self.list_all_clients()
        for client in all_clients["clients"]:
            if client["online"] is True:
                clients[client["mac"]] = client
        return clients

    async def wifi_ifaces_get(self, redact_keys: bool = True) -> dict[str, WifiIface]:
        """Return wifi interfaces keyed by name; keys redacted unless asked."""
        wifi_config = await self._wifi_config_get()
        return {
            iface.get("name"): cast(
                WifiIface, {**iface, "key": None if redact_keys else iface.get("key")}
            )
            for dev in wifi_config.get("res", [])
            for iface in dev.get("ifaces")
        }

    async def wifi_iface_set_enabled(self, iface_name: str, enabled: bool) -> Any:
        """Enable/disable a wifi interface by name."""
        ifaces = await self.wifi_ifaces_get()
        if iface_name in ifaces:
            return await self._wifi_config_set({"enabled": enabled, "iface_name": iface_name})
        raise ValueError("iface_name does not exist")

    # --- VPN: WireGuard (firmware-version routing is protocol knowledge) ------

    async def _require_firmware_version(self) -> Version:
        """Return the cached firmware version, fetching it via router_info if needed.

        Raises with the original firmware string if it could not be parsed
        as a version -- unlike :meth:`router_info`, the WireGuard client-API
        routing below genuinely needs a comparable version, so this is the
        one place that raises for an unparseable firmware string.
        """
        if self._firmware_version is None:
            await self.router_info()
        firmware_version = self._firmware_version
        if firmware_version is None:
            raise ValueError(
                "Cannot determine the WireGuard client API (legacy wg-client "
                "vs. new vpn-client) because the router's firmware version "
                f"{self._firmware_version_raw!r} could not be parsed."
            )
        return firmware_version

    async def wireguard_client_list(self) -> list[WireguardClientConfig]:
        """List configured WireGuard client peers."""
        response: dict[str, Any] = await self._transport.request(
            self._payload("call", ["wg-client", "get_all_config_list"])
        )
        configs: list[WireguardClientConfig] = []
        for item in response["config_list"]:
            if item["peers"] == []:
                continue
            for peer in item["peers"]:
                configs.append(
                    {
                        "name": f"{item['group_name']}/{peer['name']}",
                        "group_id": item["group_id"],
                        "peer_id": peer["peer_id"],
                    }
                )
        return configs

    async def wireguard_client_state(self) -> list[WireguardClientStatus]:
        """Return WireGuard client status, normalised to a list."""
        firmware_version = await self._require_firmware_version()
        target_call = "vpn-client" if firmware_version >= NEW_VPN_CLIENT_VERSION else "wg-client"
        response = await self._transport.request(self._payload("call", [target_call, "get_status"]))
        if firmware_version < NEW_VPN_CLIENT_VERSION:
            return [response]
        result: list[WireguardClientStatus] = response.get("status_list", [])
        return result

    async def wireguard_client_start(self, group_id: int, peer_or_tunnel_id: int) -> Any:
        """Start a WireGuard client."""
        return await self._wireguard_set_client_enabled(group_id, peer_or_tunnel_id, True)

    async def wireguard_client_stop(self, peer_or_tunnel_id: int) -> Any:
        """Stop a WireGuard client."""
        return await self._wireguard_set_client_enabled(-1, peer_or_tunnel_id, False)

    async def _wireguard_set_client_enabled(
        self, group_id: int, peer_or_tunnel_id: int, enabled: bool
    ) -> Any:
        """Enable/disable a WireGuard client, routing by firmware version."""
        firmware_version = await self._require_firmware_version()
        if firmware_version >= NEW_VPN_CLIENT_VERSION:
            tunnel_id = peer_or_tunnel_id
            return await self._transport.request(
                self._payload(
                    "call",
                    [
                        "vpn-client",
                        "set_tunnel",
                        {"enabled": enabled, "tunnel_id": tunnel_id},
                    ],
                )
            )
        peer_id = peer_or_tunnel_id
        if enabled:
            return await self._transport.request(
                self._payload(
                    "call",
                    ["wg-client", "start", {"group_id": group_id, "peer_id": peer_id}],
                )
            )
        return await self._transport.request(self._payload("call", ["wg-client", "stop"]))

    # --- VPN: Tailscale ------------------------------------------------------

    async def _tailscale_get_config(self) -> TailscaleConfig | bool:
        """Return the tailscale config, or False if unavailable."""
        try:
            config: TailscaleConfig = await self._transport.request(
                self._payload("call", ["tailscale", "get_config"])
            )
        except APIClientError:
            return False
        return config

    async def _tailscale_set_config(self, config_updates: dict[str, Any]) -> Any:
        """Merge updates into the tailscale config and apply them."""
        current_config: dict[str, Any] = await self._transport.request(
            self._payload("call", ["tailscale", "get_config"])
        )
        new_config = current_config | config_updates
        return await self._transport.request(
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

    async def tailscale_set_exit_node(self, ip: str | None) -> Any:
        """Route the router's traffic through a tailnet exit node.

        ``ip`` must come from :meth:`tailscale_exit_node_list`; ``None``
        clears the exit node (the firmware clears on an empty string). The
        firmware rejects setting an exit node while ``run_exit_node`` is
        enabled, and applying the change re-runs ``tailscale up`` on the
        router, which briefly interrupts tailscale traffic.
        """
        return await self._tailscale_set_config({"exit_node_ip": ip or ""})

    async def tailscale_configured(self) -> bool:
        """Return True if tailscale is configured."""
        try:
            if await self._tailscale_status() != []:
                return True
        except APIClientError:
            return False
        return await self._tailscale_get_config() is not False

    async def tailscale_start(self, depth: int = 0) -> bool:
        """Start tailscale, retrying until connected."""
        if depth > 10:
            raise ConnectionError("Tailscale attempted to connect 10 times with no success")
        response: TailscaleStatus | list[Any] = await self._tailscale_status()
        if isinstance(response, list) and response == []:
            await self._tailscale_set_config({"enabled": True})
            if depth > 0:
                await asyncio.sleep(0.3)
            depth += 1
            return await self.tailscale_start(depth)
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
                raise ConnectionError(
                    "Did not try to start tailscale as device reported 'Connecting' "
                    f"and then 3 seconds later {TailscaleConnection(status).name}"
                )
            return True
        if status in [1, 2]:
            raise ConnectionAbortedError(
                "Connection not attempted as authorisation is not complete, due to "
                f"{TailscaleConnection(status).name}"
            )
        raise ConnectionError(f"Unknown connection status: {status}")

    async def tailscale_stop(self, depth: int = 0) -> bool:
        """Stop tailscale, retrying until disconnected."""
        if depth > 10:
            raise ConnectionError("Tailscale attempted to disconnect 10 times with no success")
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
            return await self.tailscale_stop(depth)
        if status in [1, 2]:
            raise ConnectionAbortedError(
                "Disconnection not attempted as tailscale authorisation is not "
                f"complete, due to {TailscaleConnection(status).name}. Therefore "
                "tailscale was already not connected"
            )
        return True
