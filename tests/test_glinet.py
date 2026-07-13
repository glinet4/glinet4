"""Live tests for the GLinet router API; must be run against a real GLinet router.

Configuration comes from environment variables (e.g. a local ``.env`` file, see
``.env.example``): ``GLINET_HOST`` (default ``http://192.168.8.1``),
``GLINET_USERNAME`` (default ``root``), ``GLINET_PASSWORD`` (required), and
``GLINET_RUN_DISRUPTIVE`` (set truthy to run reboot / VPN-toggle tests).
Without ``GLINET_PASSWORD`` the whole live suite is skipped.
"""

import asyncio
import os

import pytest
from dotenv import load_dotenv
from semver import Version

from glinet4._routes.vpn import NEW_VPN_CLIENT_VERSION
from glinet4.enums import TailscaleConnection
from glinet4.error_handling import NonZeroResponse
from glinet4.glinet import GLinet

load_dotenv()

GLINET_HOST = os.environ.get("GLINET_HOST", "http://192.168.8.1")
GLINET_USERNAME = os.environ.get("GLINET_USERNAME", "root")
GLINET_PASSWORD = os.environ.get("GLINET_PASSWORD")
PERFORM_DISRUPTIVE_TESTS = os.environ.get("GLINET_RUN_DISRUPTIVE", "").lower() in (
    "1",
    "true",
    "yes",
)

# Every test below talks to a real router; skip the module without credentials.
# The module shares one GLinet (and one aiohttp session), so all tests must run
# on one event loop.
pytestmark = [
    pytest.mark.skipif(
        not GLINET_PASSWORD,
        reason="set GLINET_PASSWORD (e.g. in a .env file) to run the live router tests",
    ),
    pytest.mark.asyncio(loop_scope="module"),
]

disruptive = pytest.mark.skipif(
    not PERFORM_DISRUPTIVE_TESTS,
    reason="Disruptive live tests are disabled; set GLINET_RUN_DISRUPTIVE=1 to run them.",
)

router = GLinet(base_url=f"{GLINET_HOST}/rpc")

models = [
    "mt1300",
    "x3000",
    "mt2500",
    "mt2500a",
    "axt1800",
    "a1300",
    "ax1800",
    "sft1200",
    "e750",
    "mv100",
    "mv1000w",
    "s10",
    "s200",
    "s1300",
    "sf1200",
    "b1300",
    "b2200",
    "ap1300",
    "ap1300lte",
    "x1200",
    "x750",
    "x300b",
    "xe300",
    "ar750s",
    "ar750",
    "ar300m",
    "n300",
]


async def test_router_reachable() -> None:
    """Test if the router is reachable."""
    response = await router.router_reachable()
    assert response
    print(response)


async def test_login() -> None:
    """Test logging into the router."""
    assert not router.logged_in
    await router.login(GLINET_USERNAME, GLINET_PASSWORD)
    assert router.logged_in


async def test_router_info() -> None:
    """Test retrieving router information."""
    response = await router.router_info()
    assert "model" in response
    assert "firmware_version" in response
    assert "mac" in response
    print(response)


async def test_router_status() -> None:
    """Test retrieving router status."""
    response = await router.router_status()
    assert "service" in response
    assert "network" in response
    assert "system" in response
    assert "wifi" in response
    system = response.get("system")
    assert "uptime" in system
    assert "load_average" in system
    print(response)


async def test_router_load() -> None:
    """Test retrieving router load information."""
    response = await router.router_load()
    assert "load_average" in response
    assert "memory_free" in response
    assert "memory_total" in response
    print(response)


async def test_router_mac() -> None:
    """Test retrieving the router's MAC address.

    fw >= 4.9.0 removed the dedicated macclone RPC (this used to skip here
    with NonZeroResponse on such firmware); router_mac now derives the MAC
    from system get_info instead, so it should succeed unconditionally.
    """
    response = await router.router_mac()
    assert isinstance(response, str)
    assert response.count(":") == 5
    print(response)


async def test_connected_clients() -> None:
    """Test retrieving connected clients."""
    clients = await router.connected_clients()
    print(len(clients))
    assert len(clients) > 0


async def test_wifi_ifaces() -> None:
    """Test retrieving WiFi interfaces."""
    wifi_ifaces = await router.wifi_ifaces()
    print(wifi_ifaces)
    for iface in wifi_ifaces.values():
        assert "enabled" in iface
        assert "ssid" in iface
        assert "name" in iface
        assert "key" in iface


@disruptive
async def test_wifi_ifaces_set_enabled() -> None:
    """Test enabling/disabling a WiFi interface."""

    wifi_ifaces = await router.wifi_ifaces()
    iface = next(iter(wifi_ifaces.values()))
    iface_enabled = iface.get("enabled")

    await router.wifi_iface_set_enabled(iface.get("name"), enabled=not iface_enabled)
    await asyncio.sleep(1)

    wifi_ifaces2 = await router.wifi_ifaces()
    iface_enabled_after = wifi_ifaces2.get(iface.get("name")).get("enabled")
    assert iface_enabled_after != iface_enabled


async def test_wan_upstream_router_detected() -> None:
    """Test the upstream-detection probe returns a bool."""
    response = await router.wan_upstream_router_detected()
    print(response)
    # The edgerouter probe's detected flag is device/firmware dependent (a
    # fw 4.9.0 Flint 2 with working WAN reports 0), so only the type is pinned.
    assert isinstance(response, bool)


async def test_ping() -> None:
    """Test pinging a host."""
    response = await router.ping("google.com")
    assert response
    print(response)
    response = await router.ping("8.8.8.8")
    assert response
    response = await router.ping("0.0.0.1")
    assert not response


async def test_wifi_status() -> None:
    """Test retrieving per-radio wifi status."""
    radios = await router.wifi_status()
    print(radios)
    assert len(radios) > 0
    for radio in radios:
        assert "band" in radio
        assert "state" in radio


async def test_wifi_mlo_config() -> None:
    """Test retrieving the MLO configuration."""
    config = await router.wifi_mlo_config()
    print(config)
    assert isinstance(config, dict)


@disruptive
async def test_client_block_unblock() -> None:
    """Block then unblock a client, verifying the blocked flag round-trips."""
    clients = await router.clients_list()
    target = next(
        (c for c in clients["clients"] if c.get("online") and not c.get("blocked")),
        None,
    )
    if target is None:
        pytest.skip("no unblocked online client to test against")
    mac = target["mac"]
    try:
        await router.client_set_blocked(mac, blocked=True)
        await asyncio.sleep(5)
        assert mac in await router.blocked_client_macs()
    finally:
        await router.client_set_blocked(mac, blocked=False)
        await asyncio.sleep(5)
        assert mac not in await router.blocked_client_macs()


async def test_static_clients_list() -> None:
    """Test retrieving static DHCP bindings (read-only)."""
    bindings = await router.static_clients_list()
    print(bindings)
    assert isinstance(bindings, list)
    for binding in bindings:
        assert "mac" in binding
        assert "ip" in binding


async def test_flow_stats_rule() -> None:
    """Test retrieving the flow-statistics rule."""
    rule = await router.flow_stats_rule()
    print(rule)
    assert rule["enable"] in [True, False]


async def test_flow_stats_top_apps() -> None:
    """Test retrieving top apps (list in both enabled/disabled states)."""
    apps = await router.flow_stats_top_apps()
    print(apps)
    assert isinstance(apps, list)


async def test_network_acceleration() -> None:
    """Test retrieving the NAT acceleration state."""
    accel = await router.network_acceleration()
    print(accel)
    assert accel["enable"] in [True, False]


@disruptive
async def test_flow_stats_enable_disable() -> None:
    """Enable then disable flow statistics, restoring the original state."""
    base = await router.flow_stats_rule()
    if base["enable"]:
        pytest.skip("stats already enabled; not toggling to preserve state")
    try:
        await router.flow_stats_set_enabled(
            enabled=True, stat_type=base["type"], period=base["time"]
        )
        await asyncio.sleep(2)
        assert (await router.flow_stats_rule())["enable"] is True
    finally:
        await router.flow_stats_set_enabled(
            enabled=False, stat_type=base["type"], period=base["time"]
        )
        await asyncio.sleep(2)
        assert (await router.flow_stats_rule())["enable"] is False


async def test_adguard_config() -> None:
    """Test retrieving the AdGuard Home config."""
    config = await router.adguard_config()
    print(config)
    assert config["enabled"] in [True, False]


async def test_tor_config() -> None:
    """Test retrieving the Tor config."""
    config = await router.tor_config()
    print(config)
    assert config["enable"] in [True, False]


async def test_zerotier_config() -> None:
    """Test retrieving the ZeroTier config."""
    config = await router.zerotier_config()
    print(config)
    assert config["enabled"] in [True, False]


async def test_parental_control_and_content_filter_surface() -> None:
    """Parental Control / content-filter / ACL groups; ``groups`` may hold
    sensitive per-device rules once populated, so only counts are printed."""
    parental = await router.parental_control_config()
    print(f"enable={parental.get('enable')}, {len(parental.get('groups', []))} group(s)")
    assert parental["enable"] in [True, False]
    content_filter = await router.content_filter_config()
    print(content_filter)
    assert "mode" in content_filter
    acl_groups = await router.access_control_groups()
    print(f"{len(acl_groups)} ACL group(s)")
    assert isinstance(acl_groups, list)


async def test_led_config() -> None:
    """Test retrieving the LED configuration."""
    config = await router.led_config()
    print(config)
    assert config["led_enable"] in [True, False]


@disruptive
async def test_led_set_enabled() -> None:
    """Test toggling the LEDs and restoring the original state."""
    original = (await router.led_config())["led_enable"]
    await router.led_set_enabled(enabled=not original)
    assert (await router.led_config())["led_enable"] != original
    await router.led_set_enabled(enabled=original)
    assert (await router.led_config())["led_enable"] == original


async def test_firewall_port_forward_list() -> None:
    """Test retrieving port-forward rules."""
    rules = await router.firewall_port_forward_list()
    print(rules)
    assert isinstance(rules, list)
    for rule in rules:
        assert "enabled" in rule


async def test_firewall_dmz() -> None:
    """Test retrieving the DMZ configuration."""
    dmz = await router.firewall_dmz()
    print(dmz)
    assert dmz["enabled"] in [True, False]


async def test_firewall_wan_access() -> None:
    """Test retrieving WAN service exposure flags."""
    access = await router.firewall_wan_access()
    print(access)
    assert access["enable_ssh"] in [True, False]
    assert access["enable_https"] in [True, False]


async def test_firewall_rule_list() -> None:
    """Test retrieving custom firewall rules."""
    rules = await router.firewall_rule_list()
    print(rules)
    assert isinstance(rules, list)


async def test_firmware_check_online() -> None:
    """Test checking online for a firmware update."""
    check = await router.firmware_check_online()
    print(check)
    assert "current_version" in check


async def test_upgrade_config() -> None:
    """Test retrieving the automatic-upgrade configuration."""
    config = await router.upgrade_config()
    print(config)
    assert config["upgrade_enable"] in [True, False]


async def test_router_unixtime() -> None:
    """Test retrieving the router unix time."""
    unixtime = await router.router_unixtime()
    print(unixtime)
    assert unixtime > 1700000000


async def test_router_disk_info() -> None:
    """Test retrieving disk usage."""
    info = await router.router_disk_info()
    print(info)
    assert info["root"]["total"] > 0
    assert info["tmp"]["total"] > 0


async def test_router_usb_info() -> None:
    """Test retrieving USB port details."""
    info = await router.router_usb_info()
    print(info)
    assert isinstance(info, list)
    for entry in info:
        assert "value" in entry


async def test_router_timezone_config() -> None:
    """Test retrieving the timezone configuration."""
    config = await router.router_timezone_config()
    print(config)
    assert "zonename" in config
    assert config["timestamp"] > 1700000000


async def test_clients_speed() -> None:
    """Test retrieving aggregate client rx/tx rates."""
    speed = await router.clients_speed()
    print(speed)
    assert speed["speed_rx"] >= 0
    assert speed["speed_tx"] >= 0


async def test_wan_speed() -> None:
    """Test retrieving WAN rx/tx rates."""
    speed = await router.wan_speed()
    print(speed)
    assert speed["speed_rx"] >= 0
    assert speed["speed_tx"] >= 0


async def test_clients_status() -> None:
    """Test retrieving wired/wireless client counts."""
    status = await router.clients_status()
    print(status)
    assert status["cable_total"] >= 0
    assert status["wireless_total"] >= 0


async def test_wan_cable_state() -> None:
    """Test retrieving WAN cable state."""
    response = await router.wan_cable_state()
    print(response)
    assert response["cable_enabled"] in [True, False]
    assert response["cable_inserted"] in [True, False]


async def test_wan_status() -> None:
    """Test retrieving WAN connection status."""
    response = await router.wan_status()
    print(response)
    assert "status" in response
    assert "protocol" in response


async def test_wan_info() -> None:
    """Test retrieving WAN interface address details."""
    response = await router.wan_info()
    print(response)
    assert isinstance(response, list)
    for entry in response:
        assert "interface" in entry
        assert "info" in entry


async def test_ethernet_ports_status() -> None:
    """Test retrieving ethernet port link status."""
    ports = await router.ethernet_ports_status()
    print(ports)
    assert isinstance(ports, list)
    for port in ports:
        assert "name" in port


async def test_network_mode() -> None:
    """Test retrieving the operating mode."""
    mode = await router.network_mode()
    print(mode)
    assert isinstance(mode, str)
    assert mode != ""


async def test_network_interfaces_status() -> None:
    """Test retrieving per-interface online/up state."""
    interfaces = await router.network_interfaces_status()
    print(interfaces)
    assert isinstance(interfaces, list)
    for entry in interfaces:
        assert "interface" in entry
        assert entry["online"] in [True, False]


async def test_dns_config() -> None:
    """Test retrieving the DNS resolution mode and provider settings.

    ``server_auto`` (upstream DNS servers) and, on a device where they're
    set, ``nextdns_id``/``controld_id`` (NextDNS/ControlD account
    identifiers) are excluded from the printed output.
    """
    config = await router.dns_config()
    identifying = {"server_auto", "nextdns_id", "controld_id"}
    print({k: v for k, v in config.items() if k not in identifying})
    assert isinstance(config, dict)
    assert "mode" in config


async def test_dns_providers() -> None:
    """Test retrieving the built-in DNS provider catalogue."""
    providers = await router.dns_providers()
    print(providers)
    assert isinstance(providers, list)
    assert len(providers) > 0
    for provider in providers:
        assert "provider" in provider


async def test_arp_table() -> None:
    """Test retrieving the router's ARP cache.

    Entries are the caller's own LAN clients' MAC/IP addresses -- identifying
    data -- so only the entry count is printed, not the raw entries.
    """
    entries = await router.arp_table()
    print(f"{len(entries)} ARP entries")
    assert isinstance(entries, list)
    for entry in entries:
        assert "mac" in entry
        assert "ip" in entry


async def test_lan_interfaces() -> None:
    """Test retrieving the router's LAN/guest/IoT network segment configs.

    Entries map the caller's LAN topology -- identifying data -- so only the
    interface count is printed, not the raw entries.
    """
    interfaces = await router.lan_interfaces()
    print(f"{len(interfaces)} LAN interfaces")
    assert isinstance(interfaces, list)
    assert len(interfaces) > 0
    for iface in interfaces:
        assert "interface" in iface
        assert "netmask" in iface


async def test_ipv6_config() -> None:
    """Test retrieving IPv6 enablement and LAN addressing mode."""
    config = await router.ipv6_config()
    print(config)
    assert config["enable"] in [True, False]
    assert "lan_mode" in config


async def test_ddns_config() -> None:
    """Test retrieving the GL.iNet cloud DDNS enrollment.

    ``device_id`` is a device-identifying value (see
    :class:`~glinet4._types.DdnsConfig`), so it is excluded from the printed
    output.
    """
    config = await router.ddns_config()
    print({k: v for k, v in config.items() if k != "device_id"})
    assert config["enable_ddns"] in [True, False]
    assert "device_id" in config


async def test_ddns_status() -> None:
    """Test retrieving the current DDNS-mapped address and per-interface IPs.

    ``ddns`` is the router's WAN public IP, and each ``ips[]`` entry's ``ip``
    is also a public IP -- only the status code and interface count are
    printed, not the raw addresses.
    """
    status = await router.ddns_status()
    print(f"status={status.get('status')}, {len(status.get('ips', []))} interface(s)")
    assert isinstance(status.get("ips", []), list)
    assert isinstance(status.get("status"), int)


async def test_multiwan_config() -> None:
    """Test retrieving the multi-WAN interface failover/load-balance configuration."""
    config = await router.multiwan_config()
    print(config)
    assert isinstance(config.get("interfaces", []), list)
    assert isinstance(config.get("mode"), int)
    for iface in config.get("interfaces", []):
        assert "interface" in iface
        assert "metric" in iface


async def test_multiwan_status() -> None:
    """Test retrieving per-interface multi-WAN health status."""
    status = await router.multiwan_status()
    print(status)
    assert isinstance(status.get("interfaces", []), list)
    for iface in status.get("interfaces", []):
        assert "interface" in iface
        assert "status_v4" in iface


async def test_repeater_config() -> None:
    """Test retrieving the WiFi-repeater (client-mode) settings.

    ``macaddr`` is the repeater radio's own MAC address -- identifying data
    -- so it is excluded from the printed output.
    """
    config = await router.repeater_config()
    print({k: v for k, v in config.items() if k != "macaddr"})
    assert config["auto"] in [True, False]
    assert "macaddr" in config


async def test_repeater_status() -> None:
    """Test retrieving the WiFi-repeater connection state."""
    status = await router.repeater_status()
    print(status)
    assert "state" in status
    assert "state_s" in status


async def test_repeater_saved_aps() -> None:
    """Test retrieving the WiFi networks the repeater has saved credentials for.

    Entries carry SSIDs and MACs of the caller's own devices -- identifying
    data -- so only the entry count is printed, not the raw entries.
    """
    saved_aps = await router.repeater_saved_aps()
    print(f"{len(saved_aps)} saved APs")
    assert isinstance(saved_aps, list)
    for entry in saved_aps:
        assert "ssid" in entry
        assert "macaddr" in entry


async def test_tethering_status() -> None:
    """Test retrieving USB/Bluetooth tethering connection state.

    ``devices`` may carry identifying info about a connected tethering
    client -- only the device count is printed, not raw entries.
    """
    status = await router.tethering_status()
    print(f"status={status.get('status')}, {len(status.get('devices', []))} device(s)")
    assert isinstance(status.get("devices", []), list)
    assert isinstance(status.get("status"), int)


async def test_tethering_config() -> None:
    """Test retrieving the router's configured tethering profiles.

    Returns a bare list (not an envelope); empty when no tethering profiles
    are configured.
    """
    config = await router.tethering_config()
    print(config)
    assert isinstance(config, list)


async def test_qos_config() -> None:
    """Test retrieving the QoS enable state and mode."""
    config = await router.qos_config()
    print(config)
    assert config["enable"] in [True, False]
    assert "mode" in config


async def test_qos_clients() -> None:
    """Test retrieving per-client QoS bandwidth-limit entries (empty is a valid shape)."""
    clients = await router.qos_clients()
    print(clients)
    assert isinstance(clients, list)


async def test_qos_device_groups() -> None:
    """Test retrieving QoS device-group bandwidth-limit entries (empty is a valid shape)."""
    groups = await router.qos_device_groups()
    print(groups)
    assert isinstance(groups, list)


async def test_sqm_config() -> None:
    """Test retrieving the SQM enable state and bandwidth limits."""
    config = await router.sqm_config()
    print(config)
    assert config["enable"] in [True, False]
    assert "qdisc" in config


async def test_wireguard_client_list() -> None:
    """Test retrieving the list of WireGuard clients."""
    response = await router.wireguard_client_list()
    print(response)
    # assert(response['enable'] in [True,False])


async def test_wireguard_client_state() -> None:
    """Test retrieving the state of the WireGuard client."""
    # We need to get the proper firmware version for this
    info_response = await router.router_info()
    firmware_version = info_response["firmware_version"]
    parsed_version = Version.parse(firmware_version)
    response = await router.wireguard_client_state()
    print(response)
    if not response:
        pytest.skip("no WireGuard client configured on this router")
    first_status = response[0]
    # In newer version, status only exists when enabled is True
    # In older versions, status is always present
    if parsed_version >= NEW_VPN_CLIENT_VERSION:
        assert first_status["enabled"] in [True, False]
    else:
        assert first_status["status"] in [0, 1, 2]


async def test_openvpn_server_status() -> None:
    """Test retrieving OpenVPN server tunnel status."""
    status = await router.openvpn_server_status()
    print(status)
    assert isinstance(status, dict)
    assert status["initialization"] in [True, False]
    assert isinstance(status["status"], int)


async def test_openvpn_server_config() -> None:
    """Test retrieving the OpenVPN server configuration."""
    config = await router.openvpn_server_config()
    print(config)
    assert isinstance(config, dict)
    assert config["client_to_client"] in [True, False]
    assert isinstance(config.get("port"), int)


async def test_openvpn_server_setting() -> None:
    """Test retrieving OpenVPN server LAN-access/masquerade settings."""
    setting = await router.openvpn_server_setting()
    print(setting)
    assert setting["local_access"] in [True, False]
    assert setting["masq"] in [True, False]


async def test_openvpn_server_users() -> None:
    """Test retrieving OpenVPN server user-auth entries."""
    users = await router.openvpn_server_users()
    print(users)
    assert isinstance(users, list)
    if not users:
        pytest.skip("no OpenVPN server users configured on this router")


async def test_openvpn_server_routes() -> None:
    """Test retrieving OpenVPN server route rules."""
    routes = await router.openvpn_server_routes()
    print(routes)
    assert isinstance(routes.get("ipv4_route_rules", []), list)
    assert isinstance(routes.get("ipv6_route_rules", []), list)


async def test_openvpn_client_groups() -> None:
    """Test retrieving OpenVPN client groups."""
    groups = await router.openvpn_client_groups()
    print(groups)
    assert isinstance(groups, list)
    for group in groups:
        assert "group_id" in group
        assert "group_name" in group


async def test_openvpn_client_configs() -> None:
    """Test retrieving OpenVPN client configuration entries."""
    configs = await router.openvpn_client_configs()
    print(configs)
    assert isinstance(configs, list)


async def test_wireguard_server_status() -> None:
    """Test retrieving WireGuard server tunnel status and per-peer stats."""
    status = await router.wireguard_server_status()
    print(status)
    assert isinstance(status, dict)
    server = status.get("server", {})
    if not server:
        pytest.skip("no WireGuard server status on this router")
    assert server["initialization"] in [True, False]
    assert isinstance(server["status"], int)


async def test_wireguard_server_config() -> None:
    """Test retrieving the WireGuard server configuration."""
    config = await router.wireguard_server_config()
    print(config)
    assert isinstance(config, dict)
    assert config["initialization"] in [True, False]
    assert isinstance(config.get("port"), int)


async def test_wireguard_server_setting() -> None:
    """Test retrieving WireGuard server client-to-client/LAN-access/masquerade settings."""
    setting = await router.wireguard_server_setting()
    print(setting)
    assert setting["client_to_client"] in [True, False]
    assert setting["local_access"] in [True, False]
    assert setting["masq"] in [True, False]


async def test_wireguard_server_peers() -> None:
    """Test retrieving WireGuard server peers."""
    peers = await router.wireguard_server_peers()
    # Don't print key material (public_key/private_key) from a live peer record.
    sensitive = ("public_key", "private_key")
    print([{k: v for k, v in peer.items() if k not in sensitive} for peer in peers])
    assert isinstance(peers, list)
    if not peers:
        pytest.skip("no WireGuard server peers configured on this router")
    for peer in peers:
        assert "peer_id" in peer
        assert "name" in peer


async def test_wireguard_server_routes() -> None:
    """Test retrieving WireGuard server route rules."""
    routes = await router.wireguard_server_routes()
    print(routes)
    assert isinstance(routes.get("ipv4_route_rules", []), list)
    assert isinstance(routes.get("ipv6_route_rules", []), list)


async def test_wireguard_client_groups() -> None:
    """Test retrieving WireGuard client groups."""
    groups = await router.wireguard_client_groups()
    print(groups)
    assert isinstance(groups, list)
    for group in groups:
        assert "group_id" in group
        assert "group_name" in group


async def test_wireguard_client_configs() -> None:
    """Test retrieving WireGuard client configuration entries."""
    configs = await router.wireguard_client_configs()
    print(configs)
    assert isinstance(configs, list)


async def test_vpn_client_status() -> None:
    """Test retrieving the vpn-client subsystem's mode and per-tunnel status list."""
    status = await router.vpn_client_status()
    print(status)
    assert isinstance(status.get("mode"), int)
    assert isinstance(status.get("status_list", []), list)


async def test_vpn_client_tunnels() -> None:
    """Test retrieving default tunnel policies and configured VPN tunnels."""
    tunnels = await router.vpn_client_tunnels()
    print(tunnels)
    assert tunnels["global_enabled"] in [True, False]
    assert isinstance(tunnels.get("default_tunnels", []), list)
    assert isinstance(tunnels.get("tunnels", []), list)


@disruptive
async def test_wireguard_start() -> None:
    """Test starting the WireGuard client."""

    status_list = await router.wireguard_client_state()
    if status_list is None or len(status_list) == 0:
        pytest.skip("No WireGuard client configured, skipping test.")
        return

    first_status = status_list[0]
    group_id = first_status["group_id"]
    peer_id = first_status["peer_id"]
    tunnel_id = first_status.get("tunnel_id")

    result = await router.wireguard_client_start(
        group_id=group_id, peer_or_tunnel_id=tunnel_id or peer_id
    )
    print("RESULT: ", result)
    assert result["tunnel_id"] == tunnel_id

    # Wait for the client to connect or timeout with 10 seconds
    for i in range(10):
        status_list = await router.wireguard_client_state()
        first_status = status_list[0]
        if (
            "status" in first_status
            and first_status["status"] == 1
            and "enabled" in first_status
            and first_status["enabled"]
        ):
            break
        await asyncio.sleep(1)

        if i == 9:
            pytest.fail("WireGuard client took too long to connect.")


@disruptive
async def test_wireguard_stop() -> None:
    """Test stopping the WireGuard client."""

    info_response = await router.router_info()
    firmware_version = info_response["firmware_version"]
    status_list = await router.wireguard_client_state()
    if status_list is None or len(status_list) == 0:
        pytest.skip("No WireGuard client configured, skipping test.")
        return

    first_status = status_list[0]
    tunnel_id = first_status["tunnel_id"]

    result = await router.wireguard_client_stop(tunnel_id)
    print("RESULT: ", result)
    assert result["tunnel_id"] == tunnel_id

    parsed_version = Version.parse(firmware_version)

    # Wait for the client to disconnect or timeout with 10 seconds
    for i in range(10):
        status_list = await router.wireguard_client_state()
        first_status = status_list[0]
        # In newer version, status only exists when enabled is True
        # In older versions, status is always present
        if parsed_version >= NEW_VPN_CLIENT_VERSION:
            if "enabled" in first_status and not first_status["enabled"]:
                break
        elif "status" in first_status and first_status["status"] == 0:
            break

        await asyncio.sleep(1)

        if i == 9:
            pytest.fail("WireGuard client took too long to disconnect.")


async def test_tailscale_status() -> None:
    """Test retrieving the Tailscale status."""
    response = await router._tailscale_status()  # pylint: disable=protected-access
    print(response)
    assert dict(response).get("status", 0) in [0, 1, 2, 3, 4] or response == []


async def test_tailscale_connection() -> None:
    """Test retrieving the Tailscale connection state."""
    response = await router.tailscale_connection_state()
    print(response)
    assert isinstance(response, TailscaleConnection)


async def test_tailscale_configured() -> None:
    """Test checking if Tailscale is configured."""
    response = await router.tailscale_configured()
    print("Tailscale configured:", response)
    assert response in [True, False]


async def test_tailscale_get_config() -> None:
    """Test retrieving the Tailscale configuration."""
    response = await router._tailscale_get_config()  # pylint: disable=protected-access
    print(response["enabled"])
    assert response["enabled"] in [True, False]


async def test_tailscale_auth_url() -> None:
    """Test retrieving the tailscale auth URL."""
    url = await router.tailscale_auth_url()
    print(url)
    assert url is None or url.startswith("https://")


async def test_tailscale_exit_node_list() -> None:
    """Test retrieving the tailscale exit-node list."""
    nodes = await router.tailscale_exit_node_list()
    print(nodes)
    assert isinstance(nodes, list)


@disruptive
async def test_tailscale_start() -> None:
    """Test starting Tailscale."""
    result = await router.tailscale_start()
    print(result)
    assert result in [True, False]


@disruptive
async def test_tailscale_stop() -> None:
    """Test stopping Tailscale."""
    result = await router.tailscale_stop()
    print(result)
    assert result in [True, False]


@disruptive
async def test_router_reboot() -> None:
    """Test rebooting the router."""
    response = await router.router_reboot()
    print(response)
    print("waiting `15s` for router to shutdown")
    await asyncio.sleep(15)
    while not await router.router_reachable():
        print("waiting for router to wake")
        await asyncio.sleep(1)
    with pytest.raises(NonZeroResponse):
        await router.router_info()
