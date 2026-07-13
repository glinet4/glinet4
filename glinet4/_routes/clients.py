"""Client-listing and blocking route methods for :class:`glinet4.glinet.GLinet` (mixin)."""

from typing import TYPE_CHECKING, Any

from .._types import Client, ClientsStatus, StaticClient, TrafficSpeed

if TYPE_CHECKING:
    from .._transport import GLinetTransport


class ClientsRoutes:
    """Client RPCs, mixed into :class:`glinet4.glinet.GLinet`."""

    if TYPE_CHECKING:
        _transport: GLinetTransport

        def _payload(self, method: str, params: list[Any]) -> dict[str, Any]:
            """Implemented by the composing :class:`glinet4.glinet.GLinet`."""

    async def clients_speed(self) -> TrafficSpeed:
        """Return aggregate client-side rx/tx rates in bytes per second."""
        result: TrafficSpeed = await self._transport.request(
            self._payload("call", ["clients", "get_speed", {}])
        )
        return result

    async def clients_status(self) -> ClientsStatus:
        """Return wired/wireless client counts."""
        result: ClientsStatus = await self._transport.request(
            self._payload("call", ["clients", "get_status", {}])
        )
        return result

    async def client_set_blocked(self, mac: str, *, blocked: bool) -> None:
        """Block or unblock a client's network access by MAC.

        Adds (``blocked=True``) or removes (``blocked=False``) the MAC from the
        router's black list and restarts the filter service. The client's
        ``blocked`` flag (see :meth:`connected_clients`) reflects the new state
        on the next poll. Assumes the black/white list is in ``black`` mode --
        confirm with
        :meth:`~glinet4.glinet.GLinet.content_filter_config` if unsure.
        The router's acknowledgement carries nothing useful and is discarded;
        confirm the change via :meth:`blocked_client_macs`.
        """
        await self._transport.request(
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
        all_clients = await self.clients_list()
        return {client["mac"] for client in all_clients["clients"] if client.get("blocked")}

    async def clients_list(self) -> dict[str, list[Client]]:
        """Get all clients known to the router."""
        result: dict[str, list[Client]] = await self._transport.request(
            self._payload("call", ["clients", "get_list"])
        )
        return result

    async def static_clients_list(self) -> list[StaticClient]:
        """Return the statically-bound (static DHCP lease) clients."""
        response = await self._transport.request(
            self._payload("call", ["lan", "get_static_bind_list"])
        )
        result: list[StaticClient] = response.get("static_bind_list", [])
        return result

    async def connected_clients(self) -> dict[str, Client]:
        """Return online clients keyed by MAC address."""
        clients: dict[str, Client] = {}
        all_clients = await self.clients_list()
        for client in all_clients["clients"]:
            if client["online"] is True:
                clients[client["mac"]] = client
        return clients
