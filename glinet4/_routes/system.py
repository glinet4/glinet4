"""System route methods for :class:`glinet4.glinet.GLinet` (mixin)."""

import re
from typing import TYPE_CHECKING, Any

from semver import Version

from .._types import DiskInfo, RouterInfo, RouterStatus, TimezoneConfig, UsbInfoEntry
from ..error_handling import UnexpectedResponse

if TYPE_CHECKING:
    from .._transport import GLinetTransport

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


class SystemRoutes:
    """System RPCs, mixed into :class:`glinet4.glinet.GLinet`."""

    if TYPE_CHECKING:
        _transport: GLinetTransport
        _firmware_version: Version | None
        _firmware_version_raw: str | None

        def _payload(self, method: str, params: list[Any]) -> dict[str, Any]:
            """Implemented by the composing :class:`glinet4.glinet.GLinet`."""

    async def router_info(self) -> RouterInfo:
        """Retrieve router information; caches the firmware version.

        Tolerates non-semver firmware version strings (see
        :func:`_parse_firmware_version`): this call never raises for an
        unparseable version, it just caches ``None``. Raises
        :class:`~glinet4.error_handling.UnexpectedResponse` only if the
        response is missing the ``firmware_version`` key entirely (as
        opposed to containing an unparseable value, which is tolerated).
        Callers that genuinely need a comparable version (the WireGuard
        client-API gate, via :meth:`_require_firmware_version`) raise
        separately, with the original string in the message.
        """
        response: RouterInfo = await self._transport.request(
            self._payload("call", ["system", "get_info"])
        )
        if "firmware_version" not in response:
            raise UnexpectedResponse("No firmware version found in router info")
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
