"""Route mixins composed by :class:`glinet4.glinet.GLinet`.

Each module holds one group of the router's JSON-RPC method surface as a
mixin class; the shared machinery the mixins use via ``self`` (the
transport, ``_payload``, and the firmware-version cache) is implemented by
the composing ``GLinet`` class and declared on each mixin under
``if TYPE_CHECKING:`` blocks.
"""

from .clients import ClientsRoutes
from .fan import FanRoutes
from .firewall import FirewallRoutes
from .network import NetworkRoutes
from .services import ServicesRoutes
from .system import SystemRoutes
from .tailscale import TailscaleRoutes
from .vpn import VpnRoutes
from .wan import WanRoutes
from .wifi import WifiRoutes

__all__ = [
    "ClientsRoutes",
    "FanRoutes",
    "FirewallRoutes",
    "NetworkRoutes",
    "ServicesRoutes",
    "SystemRoutes",
    "TailscaleRoutes",
    "VpnRoutes",
    "WanRoutes",
    "WifiRoutes",
]
