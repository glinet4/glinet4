"""Service route methods for :class:`glinet4.glinet.GLinet` (mixin)."""

from typing import TYPE_CHECKING, Any

from .._types import (
    AdguardConfig,
    ContentFilterConfig,
    FirmwareCheck,
    FlowStatsApp,
    FlowStatsRule,
    LedConfig,
    NetworkAcceleration,
    ParentalControlConfig,
    TorConfig,
    UpgradeConfig,
    ZerotierConfig,
)

if TYPE_CHECKING:
    from .._transport import GLinetTransport


class ServicesRoutes:
    """Service RPCs, mixed into :class:`glinet4.glinet.GLinet`."""

    if TYPE_CHECKING:
        _transport: GLinetTransport

        def _payload(self, method: str, params: list[Any]) -> dict[str, Any]:
            """Implemented by the composing :class:`glinet4.glinet.GLinet`."""

    async def flow_stats_rule(self) -> FlowStatsRule:
        """Return the flow-statistics collection rule (enable/type/period)."""
        result: FlowStatsRule = await self._transport.request(
            self._payload("call", ["flow_statistics", "get_statistics_rule", {}])
        )
        return result

    async def flow_stats_set_enabled(
        self, *, enabled: bool, stat_type: str = "app", period: str = "day"
    ) -> None:
        """Enable or disable flow-statistics collection.

        Note: on this hardware the DPI accounting that fills per-app statistics
        rides on NAT acceleration, which conflicts with QoS/SQM. Enabling the
        rule starts the collector, but populated app data also requires
        :meth:`network_acceleration` to be on (see ``network_acceleration_set``).
        The router's acknowledgement carries nothing useful and is discarded;
        confirm the change via :meth:`flow_stats_rule`.
        """
        await self._transport.request(
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

    async def flow_stats_clear(self) -> None:
        """Clear all collected flow statistics (the ack carries nothing useful)."""
        await self._transport.request(
            self._payload("call", ["flow_statistics", "clear_statistics", {}])
        )

    async def network_acceleration(self) -> NetworkAcceleration:
        """Return the NAT/DPI acceleration state."""
        result: NetworkAcceleration = await self._transport.request(
            self._payload("call", ["network", "get_netnat_config", {}])
        )
        return result

    async def network_acceleration_set(self, *, enabled: bool) -> None:
        """Enable or disable NAT acceleration.

        The router rejects the change with JSON-RPC error code -1 when a
        conflicting feature (Parental Control / QoS / SQM / DPI) is active. That
        code is shared with "not logged in" errors, so this raises
        :class:`~glinet4.error_handling.FeatureConflictError` (a
        :class:`~glinet4.error_handling.NonZeroResponse`) rather than
        :class:`~glinet4.error_handling.TokenError` when the router's message
        indicates a conflict, so callers don't loop on re-authentication.
        The router's acknowledgement carries nothing useful and is discarded;
        confirm the change via :meth:`network_acceleration`. To see what
        might be blocking a re-enable: :meth:`network_acceleration` itself
        already reports two of the four via its own ``dpi_enabled``/
        ``qos_enabled`` fields (QoS also has its own detailed getter,
        :meth:`~glinet4.glinet.GLinet.qos_config`); SQM has its own getter,
        :meth:`~glinet4.glinet.GLinet.sqm_config`; and Parental Control has
        its own getter, :meth:`parental_control_config` -- all four conflict
        sources are now inspectable from this library.
        """
        current = await self.network_acceleration()
        await self._transport.request(
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

    async def parental_control_config(self) -> ParentalControlConfig:
        """Return the Parental Control enablement and device groups.

        Parental Control is one of the FOUR features that conflict with NAT
        acceleration (Parental Control / QoS / SQM / DPI; see
        :meth:`network_acceleration_set`) -- and, unlike QoS/SQM/DPI, it had
        no getter at all until this one, so a caller could see the other
        three off and still have no way to explain a
        :class:`~glinet4.error_handling.FeatureConflictError`. See
        :class:`~glinet4._types.ParentalControlConfig` for why ``groups``
        needs careful handling once populated.
        """
        result: ParentalControlConfig = await self._transport.request(
            self._payload("call", ["parental-control", "get_config", {}])
        )
        return result

    async def content_filter_config(self) -> ContentFilterConfig:
        """Return the content-filter (``black_white_list``) active mode.

        This is the block-list/allow-list mode toggle, not Parental Control
        itself (see :meth:`parental_control_config`) -- it backs
        :meth:`~glinet4.glinet.GLinet.client_set_blocked`'s per-MAC
        block/unblock, which assumes ``mode`` is already ``"black"``; use
        this getter to confirm that assumption instead of assuming it. See
        :class:`~glinet4._types.ContentFilterConfig` for what is and isn't
        known about ``mode``'s accepted values.
        """
        result: ContentFilterConfig = await self._transport.request(
            self._payload("call", ["black_white_list", "get_config", {}])
        )
        return result

    async def access_control_groups(self) -> list[dict[str, Any]]:
        """Return the router's ACL (access-control-list) device groups.

        Empty when no ACL groups are configured (the reference capture's
        state) -- that is the genuine shape, not an error. Entries are
        untyped dicts pending a capture from a device with ACL groups
        configured.
        """
        response = await self._transport.request(
            self._payload("call", ["acl", "get_group_list", {}])
        )
        result: list[dict[str, Any]] = response.get("groups", [])
        return result

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

    async def led_set_enabled(self, *, enabled: bool) -> None:
        """Enable or disable the router LEDs, preserving other LED settings.

        The router's acknowledgement carries nothing useful and is discarded;
        confirm the change via :meth:`led_config`.
        """
        current: dict[str, Any] = dict(await self.led_config())
        new_config = current | {"led_enable": enabled}
        await self._transport.request(self._payload("call", ["led", "set_config", new_config]))

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
