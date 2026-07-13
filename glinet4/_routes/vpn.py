"""WireGuard VPN route methods for :class:`glinet4.glinet.GLinet` (mixin)."""

from typing import TYPE_CHECKING, Any

from semver import Version

from .._types import (
    OpenVpnClientGroup,
    OpenVpnServerConfig,
    OpenVpnServerSetting,
    OpenVpnServerStatus,
    VpnRouteRules,
    WireguardClientConfig,
    WireguardClientStatus,
)

if TYPE_CHECKING:
    from .._transport import GLinetTransport

# Version(4, 8, 0, 0)'s 4th positional arg is `prerelease`, not a 4th version
# segment, so this is semver prerelease "4.8.0-0" -- below every real 4.8.0
# release. That's intentional: "4.8.0-beta" firmware also compares >= this,
# so beta firmware is routed to the new vpn-client API too.
NEW_VPN_CLIENT_VERSION = Version(4, 8, 0, 0)


class VpnRoutes:
    """WireGuard RPCs (firmware-version routed), mixed into :class:`glinet4.glinet.GLinet`."""

    if TYPE_CHECKING:
        _transport: GLinetTransport

        def _payload(self, method: str, params: list[Any]) -> dict[str, Any]:
            """Implemented by the composing :class:`glinet4.glinet.GLinet`."""

        async def _require_firmware_version(self) -> Version:
            """Implemented by the composing :class:`glinet4.glinet.GLinet`."""

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

    async def wireguard_client_start(
        self, *, group_id: int, peer_or_tunnel_id: int
    ) -> dict[str, Any]:
        """Start a WireGuard client.

        Returns the router's acknowledgement as-is (hence ``dict[str, Any]``):
        on firmware >= :data:`NEW_VPN_CLIENT_VERSION` the ``vpn-client
        set_tunnel`` reply echoes the tunnel state (e.g. ``{"tunnel_id": ...,
        "enabled": ...}``); the legacy ``wg-client start`` reply shape is
        undocumented, so no tighter type is promised.
        """
        return await self._wireguard_set_client_enabled(group_id, peer_or_tunnel_id, enabled=True)

    async def wireguard_client_stop(self, peer_or_tunnel_id: int) -> dict[str, Any]:
        """Stop a WireGuard client.

        Returns the router's acknowledgement as-is (hence ``dict[str, Any]``):
        on firmware >= :data:`NEW_VPN_CLIENT_VERSION` the ``vpn-client
        set_tunnel`` reply echoes the tunnel state; the legacy ``wg-client
        stop`` reply shape is undocumented, so no tighter type is promised.
        """
        return await self._wireguard_set_client_enabled(-1, peer_or_tunnel_id, enabled=False)

    async def _wireguard_set_client_enabled(
        self, group_id: int, peer_or_tunnel_id: int, *, enabled: bool
    ) -> dict[str, Any]:
        """Enable/disable a WireGuard client, routing by firmware version."""
        firmware_version = await self._require_firmware_version()
        response: dict[str, Any]
        if firmware_version >= NEW_VPN_CLIENT_VERSION:
            tunnel_id = peer_or_tunnel_id
            response = await self._transport.request(
                self._payload(
                    "call",
                    [
                        "vpn-client",
                        "set_tunnel",
                        {"enabled": enabled, "tunnel_id": tunnel_id},
                    ],
                )
            )
            return response
        peer_id = peer_or_tunnel_id
        if enabled:
            response = await self._transport.request(
                self._payload(
                    "call",
                    ["wg-client", "start", {"group_id": group_id, "peer_id": peer_id}],
                )
            )
            return response
        response = await self._transport.request(self._payload("call", ["wg-client", "stop"]))
        return response

    # --- OpenVPN server (read-only) ---------------------------------------

    async def openvpn_server_status(self) -> OpenVpnServerStatus:
        """Return OpenVPN server tunnel status.

        On a router with the OpenVPN server unconfigured (the reference
        capture's state) this returns a zeroed structure -- e.g.
        ``initialization: False``, ``log: ""``, ``rx_bytes``/``tx_bytes: 0``,
        ``status: 0``, ``tunnel_ip: ""`` -- rather than an error. That is the
        genuine unconfigured shape, not a failure to fetch.
        """
        result: OpenVpnServerStatus = await self._transport.request(
            self._payload("call", ["ovpn-server", "get_status"])
        )
        return result

    async def openvpn_server_config(self) -> OpenVpnServerConfig:
        """Return the configured OpenVPN server parameters (cipher, subnet, ports, ...)."""
        result: OpenVpnServerConfig = await self._transport.request(
            self._payload("call", ["ovpn-server", "get_config"])
        )
        return result

    async def openvpn_server_setting(self) -> OpenVpnServerSetting:
        """Return OpenVPN server LAN-access and NAT masquerade settings."""
        result: OpenVpnServerSetting = await self._transport.request(
            self._payload("call", ["ovpn-server", "get_setting"])
        )
        return result

    async def openvpn_server_users(self) -> list[dict[str, Any]]:
        """Return configured OpenVPN server user-auth entries.

        Empty when no OpenVPN server users are configured (the reference
        capture's state) -- that is the genuine shape, not an error. Entries
        are untyped dicts pending a capture from a configured device.
        """
        response = await self._transport.request(
            self._payload("call", ["ovpn-server", "get_user_list"])
        )
        result: list[dict[str, Any]] = response.get("user_list", [])
        return result

    async def openvpn_server_routes(self) -> VpnRouteRules:
        """Return OpenVPN server IPv4/IPv6 static route rules.

        Empty on the reference capture (no static routes configured) --
        that is the genuine shape, not an error. The return type
        (:class:`~glinet4._types.VpnRouteRules`) is named generically
        because WireGuard's server route-list RPC returns the identical
        envelope.
        """
        result: VpnRouteRules = await self._transport.request(
            self._payload("call", ["ovpn-server", "get_route_list"])
        )
        return result

    # --- OpenVPN client (read-only) ----------------------------------------

    async def openvpn_client_groups(self) -> list[OpenVpnClientGroup]:
        """Return configured OpenVPN client groups (imported providers/profiles).

        ``password`` carries the group's stored OpenVPN auth credential when
        set -- treat entries as sensitive and avoid logging them wholesale.
        """
        response = await self._transport.request(
            self._payload("call", ["ovpn-client", "get_group_list"])
        )
        result: list[OpenVpnClientGroup] = response.get("groups", [])
        return result

    async def openvpn_client_configs(self) -> list[dict[str, Any]]:
        """Return all imported OpenVPN client configuration entries.

        Empty when no OpenVPN client profiles are imported (the reference
        capture's state) -- that is the genuine shape, not an error. Entries
        are untyped dicts pending a capture from a configured device.
        """
        response = await self._transport.request(
            self._payload("call", ["ovpn-client", "get_all_config_list"])
        )
        result: list[dict[str, Any]] = response.get("config_list", [])
        return result
