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
4. To run tests, create a file called `router_pwd` in the repo root containing the router password.
   The tests run against a **live router** (default `192.168.8.1`), so a reachable GL.iNet device is required.
5. `uv run pytest -s` to see responses.
6. Build with `uv build`. Releases publish to PyPI automatically on a GitHub Release (trusted publishing).

## Dev setup alongside HA & the Custom component
1. Clone the repo into the vscode `/workspaces/` dir
2. The inside the `ha-env` terminal run `(ha-venv) vscode ➜ /workspaces/core (branch-name) $ pip install -e /workspaces/gli4py `
3. Ensure the custom component has `"python.analysis.extraPaths": ["/workspaces/gli4py/"]` in `.vscode/settings.json`
4. deactivate the `ha-env` with `deactivate`
5. Do steps 3 onwards above

Todo list:
- [ ] Decide on useful endpoints to expose - see https://github.com/HarvsG/ha-glinet-integration#todo
- [ ] Expose said endpoints
- [ ] Write remaining
- [x] Package correctly
- [x] Test that dev enviroment is re-producable
- [x] Publish on pip
- [ ] Static typing
