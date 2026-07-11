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


class DiskUsage(TypedDict, total=False):
    """Usage for one mount inside ``system disk_info`` (bytes)."""

    free: int
    total: int
    used: int


class DiskInfo(TypedDict, total=False):
    """``system disk_info``."""

    root: DiskUsage
    tmp: DiskUsage


class UsbInfoEntry(TypedDict, total=False):
    """An entry from ``system get_usb_info``."""

    label: str
    value: str


class TimezoneConfig(TypedDict, total=False):
    """``system get_timezone_config``."""

    autotimezone_enabled: bool
    localtime: int
    timestamp: int
    timezone: str
    tzoffset: str
    zonename: str


class FirmwareCheck(TypedDict, total=False):
    """``upgrade check_firmware_online`` — ``new_*`` keys only when an update exists."""

    current_compile_time: str
    current_type: str
    current_version: str
    new_compile_time: str
    new_type: str
    new_version: str


class UpgradeConfig(TypedDict, total=False):
    """``upgrade get_config``."""

    prompt: bool
    upgrade_enable: bool


class TrafficSpeed(TypedDict, total=False):
    """``clients get_speed`` / ``clients get_wan_speed`` — bytes per second."""

    speed_rx: int
    speed_tx: int


class ClientsStatus(TypedDict, total=False):
    """``clients get_status`` — client-count summary."""

    auto_remove_offline: bool
    cable_total: int
    wireless_total: int


class LedConfig(TypedDict, total=False):
    """``led get_config``."""

    led_enable: bool


class PortForwardRule(TypedDict, total=False):
    """A rule from ``firewall get_port_forward_list``."""

    dest: str
    dest_ip: str
    dest_port: str
    enabled: bool
    id: str
    name: str
    proto: str
    src: str
    src_dport: str


class DmzConfig(TypedDict, total=False):
    """``firewall get_dmz``."""

    enabled: bool
    dmz_ip: str


class WanAccessConfig(TypedDict, total=False):
    """``firewall get_wan_access``."""

    enable_https: bool
    enable_ping: bool
    enable_ssh: bool
    enable_whitelist: bool
    whitelist: list[str]


class WifiRadioStatus(TypedDict, total=False):
    """A radio entry from ``wifi get_status``."""

    band: str
    channel: int
    name: str
    state: str


class MloConfig(TypedDict, total=False):
    """``wifi get_mlo_config`` (the ``res`` object)."""

    encryptions: list[str]
    ifaces: list[dict[str, Any]]
    random_bssid: bool


class WanCableState(TypedDict, total=False):
    """``network check_wan_cable``."""

    cable_enabled: bool
    cable_inserted: bool
    macclone_enabled: bool


class WanIPv4Status(TypedDict, total=False):
    """IPv4 details inside ``cable get_status``."""

    dns: list[str]
    gateway: str
    ip: str


class WanStatus(TypedDict, total=False):
    """``cable get_status`` — WAN connection status."""

    ipv4: WanIPv4Status
    mode: int
    protocol: str
    status: int


class WanInterfaceAddress(TypedDict, total=False):
    """Address details inside a ``lan get_wan_info`` entry."""

    broadcast: str
    ipaddr: str
    netmask: str
    network: str
    prefix: int


class WanInterfaceInfo(TypedDict, total=False):
    """A WAN interface entry from ``lan get_wan_info``."""

    info: WanInterfaceAddress
    interface: str


class EthernetPortStatus(TypedDict, total=False):
    """A port entry from ``cable get_ports_status``."""

    duplex: str
    name: str
    speed: int


class NetworkInterfaceStatus(TypedDict, total=False):
    """An interface entry from ``system get_network_status``."""

    interface: str
    online: bool
    up: bool


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
