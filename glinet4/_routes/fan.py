"""Fan route methods for :class:`glinet4.glinet.GLinet` (mixin).

Payload shapes ported from the ``fan`` module of
vithurshanselvarajah/ha-glinet (GPL-3.0, same licence as this library), which
mapped them against real hardware.
"""

from typing import TYPE_CHECKING, Any

from .._types import FanConfig, FanStatus

if TYPE_CHECKING:
    from .._transport import GLinetTransport

# The router's accepted activation-threshold range (degrees C). Observed on
# the Flint 2; it may be model-specific -- widen these with a capture if
# another model reports a different range.
_MIN_FAN_THRESHOLD_C = 70
_MAX_FAN_THRESHOLD_C = 90


class FanRoutes:
    """Fan RPCs, mixed into :class:`glinet4.glinet.GLinet`.

    Only present on models with a controllable fan (e.g. the Flint 2). On a
    fanless model these RPCs raise a
    :class:`~glinet4.error_handling.NonZeroResponse` (method not found), so
    probe with :meth:`fan_status` before surfacing fan controls.
    """

    if TYPE_CHECKING:
        _transport: GLinetTransport

        def _payload(self, method: str, params: list[Any]) -> dict[str, Any]:
            """Implemented by the composing :class:`glinet4.glinet.GLinet`."""

    async def fan_status(self) -> FanStatus:
        """Return the fan's running state (``status``) and speed in RPM (``speed``)."""
        result: FanStatus = await self._transport.request(
            self._payload("call", ["fan", "get_status", {}])
        )
        return result

    async def fan_config(self) -> FanConfig:
        """Return the fan's temperature thresholds (activation + warning)."""
        result: FanConfig = await self._transport.request(
            self._payload("call", ["fan", "get_config", {}])
        )
        return result

    async def fan_set_threshold(self, temperature: int) -> None:
        """Set the temperature (degrees C) at which the fan switches on.

        ``temperature`` must be within the router's accepted range (70--90 on
        the Flint 2); an out-of-range value raises :class:`ValueError` without
        contacting the router. The router's acknowledgement carries nothing
        useful and is discarded; confirm the change via :meth:`fan_config`.
        """
        if not _MIN_FAN_THRESHOLD_C <= temperature <= _MAX_FAN_THRESHOLD_C:
            raise ValueError(
                f"fan threshold must be between {_MIN_FAN_THRESHOLD_C} and "
                f"{_MAX_FAN_THRESHOLD_C} degrees C, got {temperature}"
            )
        await self._transport.request(
            self._payload("call", ["fan", "set_config", {"temperature": temperature}])
        )

    async def fan_self_test(self, duration: int = 10) -> None:
        """Spin the fan for ``duration`` seconds as a self-test.

        Harmless and self-limiting: the router returns the fan to thermostat
        control when the time elapses. The acknowledgement carries nothing
        useful and is discarded.
        """
        await self._transport.request(
            self._payload("call", ["fan", "set_test", {"test": True, "time": duration}])
        )
