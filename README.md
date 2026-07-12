<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/glinet4/branding/main/assets/dark_logo.png">
    <img alt="glinet4" src="https://raw.githubusercontent.com/glinet4/branding/main/assets/logo.png" width="300">
  </picture>
</p>

# glinet4

[![PyPI](https://img.shields.io/pypi/v/glinet4)](https://pypi.org/project/glinet4/) [![License: GPL-3.0](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

An async Python 3 API wrapper for [GL.iNet](https://www.gl-inet.com/) routers running version 4.x firmware.

GL.iNet routers are built on [OpenWRT](https://openwrt.org/) and expose a local [JSON-RPC API](https://web.archive.org/web/20240121142533/https://dev.gl-inet.com/router-4.x-api/). `glinet4` wraps that API for easy integration into other services such as [Home Assistant](https://www.home-assistant.io/).

> `glinet4` began as a fork of [HarvsG/gli4py](https://github.com/HarvsG/gli4py) (GPL-3.0) and has since grown a much larger API surface. See [NOTICE](NOTICE) for attribution.

## Installation
`pip install glinet4`

## Dev setup
1. Clone the repo
2. Ensure you have Python 3.11 or greater (`python3 -V`) and install [uv](https://docs.astral.sh/uv/).
3. `uv sync` — creates the in-project `.venv` and installs the runtime + dev dependencies.
4. `uvx prek install` — sets up the git pre-commit hooks (ruff, mypy, file hygiene).
   Run them on demand with `uvx prek run --all-files`.
5. The tests run against a **live router**, so copy `.env.example` to `.env` and set at least
   `GLINET_PASSWORD` (and `GLINET_HOST` if not `192.168.8.1`). Without it the live suite is skipped.
6. `uv run pytest -s` to see responses.
7. Build with `uv build`. Releases publish to PyPI automatically on a GitHub Release (trusted publishing).

## Dev setup alongside HA & the Custom component
1. Clone the repo into the vscode `/workspaces/` dir
2. The inside the `ha-env` terminal run `(ha-venv) vscode ➜ /workspaces/core (branch-name) $ pip install -e /workspaces/gli4py `
3. Ensure the custom component has `"python.analysis.extraPaths": ["/workspaces/glinet4/"]` in `.vscode/settings.json`
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

Responses are typed with `TypedDict`s (see `glinet4/_types.py`); the package ships `py.typed`.
The catalogue of routes still to wrap comes from the sanitised device captures in
[glinet-registry](https://github.com/shauneccles/glinet-registry).

Todo list:
- [x] Decide on useful endpoints to expose - see https://github.com/HarvsG/ha-glinet-integration#todo
- [ ] Expose said endpoints (ongoing — see the table above and glinet4/glinet4 issues)
- [x] Package correctly
- [x] Test that dev enviroment is re-producable
- [x] Publish on pip
- [x] Static typing

---

Part of the **[glinet4](https://github.com/glinet4)** project — [glinet4](https://github.com/glinet4/glinet4) (Python library) · [glinet4-ha](https://github.com/glinet4/glinet4-ha) (Home Assistant) · [glinet4-profiler](https://github.com/glinet4/glinet4-profiler) · [glinet4-registry](https://github.com/glinet4/glinet4-registry)
