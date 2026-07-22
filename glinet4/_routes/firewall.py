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

    async def firewall_set_dmz(self, *, enabled: bool, dest_ip: str | None = None) -> None:
        """Enable or disable the DMZ host.

        Enabling requires a target: when ``dest_ip`` is omitted, the
        currently-configured host (``dmz_ip`` from :meth:`firewall_dmz`) is
        reused, so a plain toggle-on preserves it; if neither is available a
        :class:`ValueError` is raised rather than sending an ambiguous
        enable-with-no-target. Note the asymmetry between the read and write
        keys: the router reports the target as ``dmz_ip`` but accepts it as
        ``dest_ip`` on the write. Disabling needs no target, so ``dest_ip`` is
        ignored and only ``{"enabled": False}`` is sent. The acknowledgement
        carries nothing useful and is discarded; confirm via :meth:`firewall_dmz`.
        """
        params: dict[str, Any] = {"enabled": enabled}
        if enabled:
            if dest_ip is None:
                dest_ip = (await self.firewall_dmz()).get("dmz_ip")
            if not dest_ip:
                raise ValueError(
                    "enabling the DMZ requires a destination IP, but none was "
                    "given and the router reports no current dmz_ip"
                )
            params["dest_ip"] = dest_ip
        await self._transport.request(self._payload("call", ["firewall", "set_dmz", params]))

    async def firewall_set_wan_access(
        self,
        *,
        https: bool | None = None,
        ping: bool | None = None,
        ssh: bool | None = None,
    ) -> None:
        """Set which services (HTTPS / ping / SSH) are reachable from the WAN.

        A read-modify-write of the whole ``firewall get_wan_access`` config:
        the router's current dict is fetched and only the toggles passed here
        are overridden, so any firmware-specific keys (and the ``whitelist``)
        round-trip untouched. Passing ``None`` (the default) leaves that toggle
        unchanged. The acknowledgement carries nothing useful and is discarded;
        confirm the change via :meth:`firewall_wan_access`.
        """
        config: dict[str, Any] = dict(await self.firewall_wan_access())
        if https is not None:
            config["enable_https"] = https
        if ping is not None:
            config["enable_ping"] = ping
        if ssh is not None:
            config["enable_ssh"] = ssh
        await self._transport.request(self._payload("call", ["firewall", "set_wan_access", config]))
