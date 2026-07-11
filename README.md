# gli4py
A aysnc python 3 API wrapper for GL-inet routers with version 4 firmware. [WIP]

[GL-inet](https://www.gl-inet.com/) routers are built on [OpenWRT](https://openwrt.org/). They are highly customizeable but have an attractive user interface.

As part of their modiification of the UI they used to provide a [documented locally accessible API](https://web.archive.org/web/20240121142533/https://dev.gl-inet.com/router-4.x-api/).

I thought it would be handy to develop a python 3 wrapper for the API for easy intergation into other services such as [HomeAssistant](https://www.home-assistant.io/)

## Installation
`pip install gli4py`

## Dev setup
1. Clone the repo
2. Ensure you have Python 3.11 or greater (`python3 -V`) and install [uv](https://docs.astral.sh/uv/).
3. `uv sync` — creates the in-project `.venv` and installs the runtime + dev dependencies.
4. The tests run against a **live router**, so copy `.env.example` to `.env` and set at least
   `GLINET_PASSWORD` (and `GLINET_HOST` if not `192.168.8.1`). Without it the live suite is skipped.
5. `uv run pytest -s` to see responses.
6. Build with `uv build`. Releases publish to PyPI automatically on a GitHub Release (trusted publishing).

## Dev setup alongside HA & the Custom component
1. Clone the repo into the vscode `/workspaces/` dir
2. The inside the `ha-env` terminal run `(ha-venv) vscode ➜ /workspaces/core (branch-name) $ pip install -e /workspaces/gli4py `
3. Ensure the custom component has `"python.analysis.extraPaths": ["/workspaces/gli4py/"]` in `.vscode/settings.json`
4. deactivate the `ha-env` with `deactivate`
5. Do steps 3 onwards above

## API coverage

Session: `login`, `router_reachable`. All other methods require login first.

| Area | Methods |
|---|---|
| System | `router_info`, `router_get_status`, `router_get_load`, `router_mac`, `router_reboot`, `router_unixtime`, `router_disk_info`, `router_usb_info`, `router_timezone_config` |
| Network / WAN | `wan_status`, `wan_cable_state`, `wan_info`, `ethernet_ports_status`, `network_mode`, `network_interfaces_status`, `connected_to_internet`, `ping` |
| Clients | `list_all_clients`, `list_static_clients`, `connected_clients`, `clients_status`, `clients_speed`, `wan_speed` |
| WiFi | `wifi_ifaces_get`, `wifi_iface_set_enabled`, `wifi_status`, `wifi_mlo_config` |
| Firmware | `firmware_check_online`, `upgrade_config` |
| Firewall | `firewall_port_forward_list`, `firewall_dmz`, `firewall_wan_access`, `firewall_rule_list` |
| LED | `led_config`, `led_set_enabled` |
| WireGuard | `wireguard_client_list`, `wireguard_client_state`, `wireguard_client_start`, `wireguard_client_stop` |
| Tailscale | `tailscale_configured`, `tailscale_connection_state`, `tailscale_start`, `tailscale_stop`, `tailscale_auth_url`, `tailscale_exit_node_list` |

Responses are typed with `TypedDict`s (see `gli4py/_types.py`); the package ships `py.typed`.
The catalogue of routes still to wrap comes from the sanitised device captures in
[glinet-registry](https://github.com/shauneccles/glinet-registry).

Todo list:
- [x] Decide on useful endpoints to expose - see https://github.com/HarvsG/ha-glinet-integration#todo
- [ ] Expose said endpoints (ongoing — see the table above and shauneccles/gli4py#14)
- [x] Package correctly
- [x] Test that dev enviroment is re-producable
- [x] Publish on pip
- [x] Static typing
