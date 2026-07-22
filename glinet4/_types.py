"""Typed response shapes for the GL.iNet API.

These are ``TypedDict``s: methods still return plain dicts at runtime, not
model instances. They exist so consumers (and ``mypy --strict``) get response
types. ``total=False`` is used where the router omits keys depending on
firmware/state.
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


class StaticClient(TypedDict, total=False):
    """A static DHCP binding from ``lan get_static_bind_list``."""

    mac: str
    name: str
    ip: str


class RouterLoad(TypedDict, total=False):
    """``system get_load`` — 1/5/15-minute load averages, memory in bytes."""

    load_average: list[float]
    memory_free: int
    memory_buff_cache: int
    memory_total: int


class WifiIface(TypedDict, total=False):
    """A reshaped wifi interface from :meth:`GLinet.wifi_ifaces`."""

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


class FlowStatsRule(TypedDict, total=False):
    """``flow_statistics get_statistics_rule``."""

    enable: bool
    type: str
    time: str


class FlowStatsApp(TypedDict, total=False):
    """An app entry from ``flow_statistics get_top_app_flow_statistics``."""

    application_id: int
    application_name: str
    total_download: int
    total_upload: int
    total_packets: int


class NetworkAcceleration(TypedDict, total=False):
    """``network get_netnat_config`` — the NAT/DPI acceleration state.

    ``dpi_enabled``/``qos_enabled`` flag whether DPI/QoS are currently
    blocking acceleration -- two of the FOUR conflicting features (Parental
    Control / QoS / SQM / DPI; see
    :meth:`~glinet4.glinet.GLinet.network_acceleration_set`). QoS also has
    its own detailed getter, :meth:`~glinet4.glinet.GLinet.qos_config`, as
    does SQM, :meth:`~glinet4.glinet.GLinet.sqm_config`, and Parental
    Control, :meth:`~glinet4.glinet.GLinet.parental_control_config`.
    """

    enable: bool
    dpi_enabled: bool
    qos_enabled: bool
    actype: int


class AdguardConfig(TypedDict, total=False):
    """``adguardhome get_config``."""

    enabled: bool
    dns_enabled: bool


class TorConfig(TypedDict, total=False):
    """``tor get_config``."""

    enable: bool
    manual: bool
    countries: list[str]


class ZerotierConfig(TypedDict, total=False):
    """``zerotier get_config``."""

    enabled: bool
    wan_enabled: bool
    lan_enabled: bool


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


class TailscaleExitNode(TypedDict, total=False):
    """An entry from ``tailscale get_exit_node_list``.

    Shape from the firmware's RPC source (fw 4.9.0): ``ip`` is the node's
    first tailscale IP, ``location`` is "Country, City", the DNS-name prefix,
    or "Unknown location", and ``provider`` is present only for Mullvad nodes.
    """

    ip: str
    location: str
    provider: str


class TailscaleStatus(TypedDict, total=False):
    """``tailscale get_status`` — ``status`` may be absent right after enabling."""

    login_name: str
    status: int
    address_v4: str
    dns: list[str]


class TailscaleConfig(TypedDict, total=False):
    """``tailscale get_config`` — ``exit_node_ip`` present only when one is set."""

    enabled: bool
    wan_enabled: bool
    lan_enabled: bool
    lan_ip: str
    masq: bool
    run_exit_node: bool
    exit_node_ip: str


class OpenVpnServerStatus(TypedDict, total=False):
    """``ovpn-server get_status``.

    On the reference capture (fw 4.9.0, OpenVPN server unconfigured) this is
    a zeroed structure — ``initialization: False``, ``log: ""``,
    ``rx_bytes``/``tx_bytes: 0``, ``status: 0``, ``tunnel_ip: ""`` — rather
    than an error. That is the genuine unconfigured shape.
    """

    initialization: bool
    log: str
    rx_bytes: int
    status: int
    tunnel_ip: str
    tx_bytes: int


class OpenVpnServerConfig(TypedDict, total=False):
    """``ovpn-server get_config``.

    ``dh`` carries the server's Diffie-Hellman parameters (key material);
    treat it as sensitive and avoid logging it wholesale. ``verb`` is a
    string on the wire (e.g. ``"3"``), not an int — typed as captured.
    """

    access_scope: int
    auth: str
    cipher: str
    client_auth: int
    client_to_client: bool
    dh: str
    end: str
    hmac: bool
    initialization: bool
    local_access: bool
    lzo: bool
    mask: str
    mode: str
    port: int
    proto: str
    start: str
    subnetv4: str
    subnetv6: str
    tap_address: str
    tap_mask: str
    verb: str


class OpenVpnServerSetting(TypedDict, total=False):
    """``ovpn-server get_setting`` — LAN access and NAT masquerade flags."""

    local_access: bool
    masq: bool


class VpnRouteRules(TypedDict, total=False):
    """``ovpn-server get_route_list`` — shared shape for VPN server route lists.

    Named generically (not ``OpenVpn*``) because WireGuard's server
    route-list RPC returns the identical ``ipv4_route_rules``/
    ``ipv6_route_rules`` envelope, so a future wrapper for it can reuse this
    type. Both lists are empty in the reference capture (no static routes
    configured); per-entry field names are unverified, so entries are typed
    as untyped dicts rather than guessed.
    """

    ipv4_route_rules: list[dict[str, Any]]
    ipv6_route_rules: list[dict[str, Any]]


class OpenVpnClientGroup(TypedDict, total=False):
    """A group entry from ``ovpn-client get_group_list``'s ``groups``.

    Represents one imported OpenVPN client provider/profile. ``password``
    carries the group's stored OpenVPN auth credential when set; treat
    entries as sensitive and avoid logging them wholesale.
    """

    askpass: str
    askpass_exist: bool
    auth_type: int
    client_count: int
    group_id: int
    group_name: str
    group_type: int
    password: str
    procedure: int
    show: bool
    username: str
    work_mode: str


class WireguardServerPeerStatus(TypedDict, total=False):
    """A per-peer status entry inside ``wg-server get_status``'s ``peers`` list.

    Traffic/handshake stats only — distinct from :class:`WireguardPeer`
    (``wg-server get_peer_list``), which carries the peer's full
    configuration including key material.
    """

    latest_handshake: int
    name: str
    private_ip: str
    public_ip: str
    rx_bytes: int
    tx_bytes: int


class WireguardServerTunnelStatus(TypedDict, total=False):
    """The nested ``server`` object inside ``wg-server get_status`` — overall tunnel status."""

    initialization: bool
    log: str
    rx_bytes: int
    status: int
    tunnel_ip: str
    tx_bytes: int


class WireguardServerStatus(TypedDict, total=False):
    """``wg-server get_status`` — per-peer stats plus overall tunnel status."""

    peers: list[WireguardServerPeerStatus]
    server: WireguardServerTunnelStatus


class WireguardServerConfig(TypedDict, total=False):
    """``wg-server get_config``.

    ``private_key``/``public_key`` are the server's own WireGuard keypair;
    treat this response as sensitive and avoid logging it wholesale.
    """

    address_v4: str
    address_v6: str
    amnezia: str
    initialization: bool
    local_access: bool
    obfuscation: int
    port: int
    private_key: str
    public_key: str


class WireguardServerSetting(TypedDict, total=False):
    """``wg-server get_setting`` — client-to-client, LAN access, and NAT masquerade flags."""

    client_to_client: bool
    local_access: bool
    masq: bool


class WireguardPeer(TypedDict, total=False):
    """A peer entry from ``wg-server get_peer_list``'s ``peers``.

    Carries the peer's full configuration, including key material
    (``public_key``, ``private_key``) and its ``end_point``. This is the
    owner's own peer data returned to the owner — expected for a library —
    but treat entries as sensitive and avoid logging them wholesale.
    """

    allowed_ips: str
    client_ip: str
    deprecated: int
    dns: str
    enabled: bool
    end_point: str
    mtu: int
    name: str
    peer_id: int
    persistent_keepalive: int
    presharedkey_enable: bool
    private_key: str
    public_key: str


class WireguardClientGroup(TypedDict, total=False):
    """A group entry from ``wg-client get_group_list``'s ``groups``.

    Represents one imported WireGuard client provider/profile. ``password``
    carries the group's stored auth credential when set; treat entries as
    sensitive and avoid logging them wholesale.
    """

    auth_type: int
    group_id: int
    group_name: str
    group_type: int
    password: str
    peer_count: int
    procedure: int
    show: bool
    username: str


class VpnClientStatus(TypedDict, total=False):
    """``vpn-client get_status`` — full envelope (mode plus per-tunnel status list).

    ``status_list`` entries reuse :class:`WireguardClientStatus`, the same
    type :meth:`~glinet4.glinet.GLinet.wireguard_client_state` already
    extracts from this identical RPC on current firmware.
    """

    mode: int
    status_list: list[WireguardClientStatus]


class VpnClientTunnelSource(TypedDict, total=False):
    """The ``from`` object inside a :data:`VpnClientDefaultTunnel` entry."""

    type: str


class VpnClientTunnelDestination(TypedDict, total=False):
    """The ``to`` object inside a :data:`VpnClientDefaultTunnel` entry."""

    domain_list: str
    domain_list_len: int
    manual: bool
    type: str


class VpnClientTunnelVia(TypedDict, total=False):
    """The ``via`` object inside a :data:`VpnClientDefaultTunnel` entry."""

    via: str


# ``from`` is a Python keyword, so this entry (``vpn-client get_tunnel``'s
# ``default_tunnels``) uses the functional TypedDict form instead of a class
# body, which cannot have a field literally named ``from``.
VpnClientDefaultTunnel = TypedDict(
    "VpnClientDefaultTunnel",
    {
        "enabled": bool,
        "from": VpnClientTunnelSource,
        "id": str,
        "killswitch": bool,
        "name": str,
        "to": VpnClientTunnelDestination,
        "tunnel_id": int,
        "via": VpnClientTunnelVia,
    },
    total=False,
)


class VpnClientTunnels(TypedDict, total=False):
    """``vpn-client get_tunnel`` — default tunnel policies and configured VPN tunnels.

    ``tunnels`` is empty in the reference capture (no VPN tunnels
    configured), so its per-entry field names are unverified; typed as
    untyped dicts rather than guessed.
    """

    default_tunnels: list[VpnClientDefaultTunnel]
    global_enabled: bool
    tunnels: list[dict[str, Any]]


class DnsConfig(TypedDict, total=False):
    """``dns get_config`` — DNS resolution mode and provider settings.

    ``manual_list``, ``proxy_list``, ``secure_manual_list``, and
    ``servers_list`` are all empty in the reference capture, so their
    per-entry item type (plain strings vs. structured records) is
    unverified; typed as ``list[Any]`` rather than guessed. ``server_auto``
    is non-empty and confirmed as a list of strings.
    """

    controld_id: str
    controld_type: int
    force_dns: bool
    manual_list: list[Any]
    mode: str
    nextdns_id: str
    override_vpn: bool
    proto: str
    proto_manual: str
    provider: str
    proxy_list: list[Any]
    rebind_protection: bool
    secure_manual_list: list[Any]
    server_auto: list[str]
    servers_list: list[Any]


class DnsServerEntry(TypedDict, total=False):
    """A DoH/DoT/DoQ resolver entry inside a :class:`DnsProvider`'s ``server_list``.

    ``address``/``address6`` are the provider's own published resolver IPs
    (e.g. a filtering-DNS vendor's anycast addresses) — public vendor
    constants, not data about the caller or its network.
    """

    address: list[str]
    address6: list[str]
    description: str
    name: str
    url_doh: str
    url_doq: str
    url_dot: str


class DnsProvider(TypedDict, total=False):
    """One entry from ``dns get_info``'s bare list of built-in DNS providers.

    Unlike most list-returning RPCs, ``dns get_info``'s response is a bare
    list of these records, not an ``{key: [...]}`` envelope. Most providers
    carry ``server_list`` (see :class:`DnsServerEntry`) and ``sup_proto``;
    the reference capture's ``nextdns`` entry has only ``provider``/
    ``sup_proto`` (account-specific, resolved elsewhere), and its ``manual``
    entry instead carries ``proto_manual``/``secure_manual_list`` describing
    the caller's own manually-entered servers.
    """

    provider: str
    server_list: list[DnsServerEntry]
    sup_proto: list[str]
    proto_manual: str
    secure_manual_list: list[Any]


class ArpEntry(TypedDict, total=False):
    """An entry from ``network get_arp_list``'s ``entries`` — the router's ARP cache.

    Each entry identifies one of the caller's own LAN clients by MAC and IP
    address (``device`` is the bridge/interface it was seen on, e.g.
    ``br-lan``). Correct for a library to return — the owner is asking their
    own router for their own client list — but treat entries as identifying
    data and avoid logging them wholesale.
    """

    device: str
    ip: str
    mac: str


class LanInterface(TypedDict, total=False):
    """An entry from ``lan get_config_list``'s ``interfaces`` — one LAN/guest/IoT segment's DHCP config.

    Each entry describes one of the router's own network segments (DHCP
    range, gateway, subnet) rather than an individual client, but together
    they map the caller's LAN topology — treat entries as identifying data
    and avoid logging them wholesale. ``transfer_enable``/``wan_isolate``
    are present only on the reference capture's ``guest``/``iot`` entries,
    not its primary ``lan`` entry. ``lpr``'s meaning is not documented by
    the router; kept as captured (empty in the reference capture). ``dns``
    is also empty in every captured interface, so its per-entry item type
    is unverified; typed as ``list[Any]`` rather than guessed (same
    reasoning as ``lpr`` here and the four empty lists on
    :class:`DnsConfig`).
    """

    ap_isolate: int
    dns: list[Any]
    enable: int
    end: str
    gateway: str
    interface: str
    ip: str
    leasetime: str
    lpr: list[Any]
    netmask: str
    start: str
    transfer_enable: int
    wan_isolate: int


class Ipv6Config(TypedDict, total=False):
    """``ipv6 get_ipv6`` — IPv6 enablement and LAN addressing mode."""

    enable: bool
    lan_dns_mode: bool
    lan_mode: str


class DdnsConfig(TypedDict, total=False):
    """``ddns get_config`` — GL.iNet cloud DDNS enrollment.

    ``device_id`` is the router's DDNS device identifier (used to address it
    via GL.iNet's DDNS service) — not a secret credential, but a
    device-identifying value worth treating with the same care as other
    identifying fields in this module.
    """

    device_id: str
    enable_ddns: bool


class DdnsInterfaceAddress(TypedDict, total=False):
    """A per-interface entry inside ``ddns get_status``'s ``ips``."""

    interface: str
    ip: list[str]


class DdnsStatus(TypedDict, total=False):
    """``ddns get_status`` — the DDNS-mapped address and per-interface IPs.

    ``ddns`` is the router's current public IP as resolved via its DDNS
    hostname.
    """

    ddns: str
    ips: list[DdnsInterfaceAddress]
    status: int


class MultiWanInterfaceConfig(TypedDict, total=False):
    """One entry from ``kmwan get_config``'s ``interfaces`` — one WAN-capable interface's failover config.

    ``track_ipv4``/``track_ipv6`` are the addresses the router pings to
    decide whether this interface is up (connectivity-check targets — the
    reference capture's defaults are public DNS resolvers, but the field is
    router-configurable, so no meaning beyond "check target" is assumed).
    ``metric``/``weight`` set failover priority and load-balance weighting.
    ``track_method``/``track_mode``/``track_proto`` are undocumented by the
    router beyond being ints; kept as captured.
    """

    enable_check: bool
    enable_ssl: bool
    interface: str
    metric: int
    track_ipv4: list[str]
    track_ipv6: list[str]
    track_method: int
    track_mode: int
    track_proto: int
    weight: int


class MultiWanConfig(TypedDict, total=False):
    """``kmwan get_config`` — multi-WAN interface failover/load-balance configuration.

    ``mode`` selects the router's multi-WAN strategy (e.g. failover vs.
    load-balance) as an int; undocumented by the router beyond that, kept as
    captured.
    """

    interfaces: list[MultiWanInterfaceConfig]
    mode: int


class MultiWanInterfaceStatus(TypedDict, total=False):
    """One entry from ``kmwan get_status``'s ``interfaces`` — one interface's multi-WAN health.

    ``status_v4``/``status_v6`` are per-protocol health state as an int;
    undocumented by the router beyond that, kept as captured.
    """

    interface: str
    status_v4: int
    status_v6: int


class MultiWanStatus(TypedDict, total=False):
    """``kmwan get_status`` — per-interface multi-WAN health status."""

    interfaces: list[MultiWanInterfaceStatus]


class RepeaterConfig(TypedDict, total=False):
    """``repeater get_config`` — WiFi-repeater (client-mode) settings.

    ``macaddr`` is the repeater radio's own MAC address, not a connected
    client's.
    """

    auto: bool
    dfs_support: bool
    macaddr: str
    smart_reconnect: bool


class RepeaterPortalInfo(TypedDict, total=False):
    """The ``portal_info`` object inside ``repeater get_status`` — captive-portal login state.

    ``password`` is already redacted by the router in the reference capture
    (returned as a placeholder string, not the live credential) — treat it
    as sensitive regardless.
    """

    auth_mode: int
    password: str
    username: str
    voucher: str


class RepeaterStatus(TypedDict, total=False):
    """``repeater get_status`` — WiFi-repeater connection state."""

    portal_info: RepeaterPortalInfo
    state: int
    state_s: str


class SavedApMacAddr(TypedDict, total=False):
    """The nested ``macaddr`` object inside a :class:`SavedAp` entry — MAC-randomization settings.

    ``macaddr`` is the MAC the repeater uses/used when associating with this
    saved AP; ``mode``/``update`` describe the randomization policy (e.g.
    ``"random"``/``"none"`` in the reference capture) and are otherwise
    undocumented by the router.
    """

    macaddr: str
    mode: str
    update: str


class SavedAp(TypedDict, total=False):
    """An entry from ``repeater get_saved_ap_list``'s ``res`` — a WiFi network the repeater has saved.

    Each entry names an access point the caller's router has previously
    connected to as a repeater client (``ssid``, and the associating MAC
    inside ``macaddr``) — identifying data about the caller's own devices
    and connection history; avoid logging entries wholesale. ``key`` carries
    the saved network's WiFi key; the reference capture shows the router
    already redacts it (a placeholder string, not the live credential), but
    treat it as sensitive regardless.
    """

    auto_portal: bool
    disguise: bool
    key: str
    macaddr: SavedApMacAddr
    manual: bool
    protocol: str
    ssid: str


class TetheringStatus(TypedDict, total=False):
    """``tethering get_status`` — USB/Bluetooth tethering connection state.

    ``devices`` is empty in the reference capture (no tethering client
    connected), so its per-entry shape is unverified — likely per-device
    identifying info (e.g. a connected phone's MAC), so treat entries as
    identifying data and avoid logging them wholesale once populated.
    ``status`` is always sent by the router (an int; meaning undocumented
    beyond that, kept as captured).
    """

    devices: list[dict[str, Any]]
    status: int


class QosConfig(TypedDict, total=False):
    """``qos get_config`` — Quality-of-Service (traffic-shaping) enablement and mode.

    QoS is one of the features that conflicts with NAT acceleration -- see
    :meth:`~glinet4.glinet.GLinet.network_acceleration_set`. ``mode`` is
    reported as a numeric string (e.g. ``"0"``) by the router, not an int;
    undocumented beyond that, kept as captured.
    """

    enable: bool
    mode: str


class SqmConfig(TypedDict, total=False):
    """``sqm get_config`` — Smart Queue Management (bufferbloat mitigation) settings.

    SQM is one of the features that conflicts with NAT acceleration -- see
    :meth:`~glinet4.glinet.GLinet.network_acceleration_set`. ``download``/
    ``upload`` are bandwidth limits (unit undocumented by the router);
    ``qdisc`` names the underlying Linux queuing discipline (e.g.
    ``"fq_codel"``). ``sqm get_status`` doesn't exist on this firmware (RPC
    absent), so there is no ``status`` field here.
    """

    download: int
    enable: bool
    qdisc: str
    upload: int


class ParentalControlConfig(TypedDict, total=False):
    """``parental-control get_config`` — Parental Control enablement and device groups.

    Parental Control is one of the FOUR features that conflict with NAT
    acceleration (Parental Control / QoS / SQM / DPI; see
    :meth:`~glinet4.glinet.GLinet.network_acceleration_set`) -- and, unlike
    the other three, had no getter at all until this one. ``groups`` is
    empty in the reference capture (no parental-control device groups
    configured), so its per-entry shape is unverified and typed as
    ``list[Any]`` rather than guessed; on a configured device each group
    likely carries a schedule plus per-device rules, including the owner's
    own blocked-domain lists and named device assignments -- treat entries
    as identifying/sensitive and avoid logging them wholesale once populated
    (same caution as this module's ARP/LAN entries and
    :class:`WireguardPeer`). ``init``'s meaning is undocumented by the
    router beyond being a bool; kept as captured.
    """

    enable: bool
    groups: list[Any]
    init: bool


class ContentFilterConfig(TypedDict, total=False):
    """``black_white_list get_config`` — the content-filter list's active mode.

    Named for the RPC it wraps (``black_white_list``), not "parental
    control": this is the block-list/allow-list mode toggle that backs
    :meth:`~glinet4.glinet.GLinet.client_set_blocked`, which reads this
    ``mode`` to pick the correct add/remove semantics. A real fw-4.9 device
    returns ``"black"``; the whitelist counterpart is ``"white"``. The router
    publishes no schema for ``mode``, so the full set of accepted values is
    unknown -- any value other than ``"white"`` is treated as blacklist
    semantics. Treat ``mode`` as an opaque router-defined string, not a
    documented enum.
    """

    mode: str


class FanStatus(TypedDict, total=False):
    """``fan get_status`` — the fan's running state and speed.

    ``status`` is truthy while the fan is spinning; ``speed`` is the current
    speed in RPM. Only present on models with a controllable fan (e.g. the
    Flint 2) -- a fanless model answers ``fan get_status`` with a JSON-RPC
    method-not-found error.
    """

    status: bool
    speed: int


class FanConfig(TypedDict, total=False):
    """``fan get_config`` — the fan's temperature thresholds.

    ``temperature`` is the activation threshold (degrees C) set via
    :meth:`~glinet4.glinet.GLinet.fan_set_threshold`; ``warn_temperature`` is
    the high-temperature warning point. Both are model-specific.
    """

    temperature: int
    warn_temperature: int
