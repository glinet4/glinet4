"""gli4py - A Python library for GL.iNet routers"""

from ._types import (
    Client,
    EthernetPortStatus,
    NetworkInterfaceStatus,
    RouterInfo,
    RouterStatus,
    TailscaleConfig,
    TailscaleStatus,
    WanCableState,
    WanInterfaceAddress,
    WanInterfaceInfo,
    WanIPv4Status,
    WanStatus,
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
    "EthernetPortStatus",
    "NetworkInterfaceStatus",
    "RouterInfo",
    "RouterStatus",
    "TailscaleConfig",
    "TailscaleStatus",
    "WanCableState",
    "WanInterfaceAddress",
    "WanInterfaceInfo",
    "WanIPv4Status",
    "WanStatus",
    "WifiIface",
    "WireguardClientConfig",
    "WireguardClientStatus",
]
