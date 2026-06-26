"""Typed response shapes for the GL.iNet API.

These are ``TypedDict``s, not pydantic models: methods still return plain dicts
at runtime. They exist so consumers (and ``mypy --strict``) get response types.
``total=False`` is used where the router omits keys depending on firmware/state.
"""

from typing import Any, TypedDict


class RouterInfo(TypedDict, total=False):
    """``system get_info`` — at least ``model``/``firmware_version``/``mac``."""

    model: str
    firmware_version: str
    mac: str


class WifiNetwork(TypedDict, total=False):
    """A wifi entry inside router status (``passwd`` is redacted to None)."""

    ssid: str
    passwd: str | None


class RouterStatus(TypedDict, total=False):
    """``system get_status``."""

    service: list[dict[str, Any]]
    network: list[dict[str, Any]]
    system: dict[str, Any]
    wifi: list[WifiNetwork]


class Client(TypedDict, total=False):
    """A single client from ``clients get_list``."""

    mac: str
    online: bool


class WifiIface(TypedDict, total=False):
    """A reshaped wifi interface from :meth:`GLinet.wifi_ifaces_get`."""

    enabled: bool
    encryption: str
    hidden: bool
    guest: bool
    ssid: str
    name: str
    key: str | None


class WireguardClientConfig(TypedDict):
    """A flattened WireGuard peer from :meth:`GLinet.wireguard_client_list`."""

    name: str
    group_id: int
    peer_id: int


class WireguardClientStatus(TypedDict, total=False):
    """A WireGuard client status entry."""

    name: str
    enabled: bool
    status: int
    group_id: int
    peer_id: int
    tunnel_id: int
    rx_bytes: int
    tx_bytes: int


class TailscaleStatus(TypedDict, total=False):
    """``tailscale get_status``."""

    login_name: str
    status: int
    address_v4: str


class TailscaleConfig(TypedDict, total=False):
    """``tailscale get_config``."""

    enabled: bool
    wan_enabled: bool
    lan_enabled: bool
    lan_ip: str
