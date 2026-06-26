"""gli4py - A Python library for GL.iNet routers"""

from ._types import (
    Client,
    RouterInfo,
    RouterStatus,
    TailscaleConfig,
    TailscaleStatus,
    WifiIface,
    WireguardClientConfig,
    WireguardClientStatus,
)
from .enums import TailscaleConnection
from .glinet import GLinet

__all__ = [
    "GLinet",
    "TailscaleConnection",
    "Client",
    "RouterInfo",
    "RouterStatus",
    "TailscaleConfig",
    "TailscaleStatus",
    "WifiIface",
    "WireguardClientConfig",
    "WireguardClientStatus",
]
