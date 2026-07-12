"""WireGuard VPN route methods for :class:`glinet4.glinet.GLinet` (mixin)."""

from typing import TYPE_CHECKING, Any

from semver import Version

from .._types import WireguardClientConfig, WireguardClientStatus

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
