"""Static guard: every RPC (service, method) pair glinet4 sends (from
glinet4/glinet.py and the glinet4/_routes/ mixin modules) must be a known
method on a real device, per the captured registry in
tests/data/rpc_catalog.json.

The catalog is a names-only extract of a live capture against an MT6000 on
firmware 4.9.0 (see the main gli4py checkout's
``docs/devices/mt6000_4.9.0.json``, which stays out of this repo and is
gitignored there since the raw capture may carry unsanitised values): for
each ``service``/``method`` the capture recorded a JSON-RPC ``-32601``
(method not found) response, the pair is dropped; everything else (a real
value, or an error caused by something other than the method not existing --
e.g. requiring state/params the read-only catalog probe didn't supply) is
kept, because the RPC endpoint genuinely exists on the device either way.

The capture only probes read-risk methods against a fixed candidate name
list per service, so it under-reports: every write (``set_*``, ``start``,
``stop``, ``reboot``, ``clear_*``) RPC glinet4 sends is absent from it by
construction, and a handful of real read RPCs (outside that candidate list,
e.g. ``clients get_speed``) are absent too. Those are listed in
KNOWN_UNCATALOGUED below, each with a reason.
"""
# pylint: disable=missing-function-docstring

import ast
import json
from pathlib import Path

_GLINET_PACKAGE = Path(__file__).parent.parent / "glinet4"
GLINET_SOURCES = [
    _GLINET_PACKAGE / "glinet.py",
    *sorted((_GLINET_PACKAGE / "_routes").glob("*.py")),
]
CATALOG_PATH = Path(__file__).parent / "data" / "rpc_catalog.json"

# (service, method) pairs glinet4 legitimately sends but that are
# absent from the mt6000 4.9.0 capture. Grouped by why the capture misses
# them; when refreshing the catalog from a new capture, re-check whether any
# of these have since appeared (see the allowlist-rot test below).
KNOWN_UNCATALOGUED: set[tuple[str, str]] = {
    # --- write-risk RPCs: the capture only ever probes risk="read" methods ---
    ("black_white_list", "set_single_mac"),
    ("flow_statistics", "clear_statistics"),
    ("flow_statistics", "set_statistics_rule"),
    ("led", "set_config"),
    ("network", "set_netnat_config"),
    ("system", "reboot"),
    ("tailscale", "set_config"),
    ("vpn-client", "set_tunnel"),
    ("wg-client", "start"),
    ("wg-client", "stop"),
    ("wifi", "set_config"),
    # --- real read RPCs outside the capture tool's fixed per-service probe-name list ---
    ("cable", "get_ports_status"),
    ("clients", "get_speed"),
    ("clients", "get_wan_speed"),
    ("diag", "ping"),
    ("lan", "get_wan_info"),
    ("network", "get_netnat_config"),
    ("system", "get_network_status"),
    ("system", "get_usb_info"),
    ("tailscale", "get_auth_url"),
    ("tailscale", "get_exit_node_list"),
    ("upgrade", "check_firmware_online"),
    # --- probed and confirmed gone on this device/firmware (JSON-RPC -32601) ---
    # superseded by vpn-client on fw >= NEW_VPN_CLIENT_VERSION (4.8.0-0); the
    # capture device runs 4.9.0, so its wg-client no longer answers get_status
    ("wg-client", "get_status"),
}


def _literal_strings(node: ast.expr) -> list[str]:
    """Return every literal string value an expression could evaluate to.

    Handles plain string constants and ``a if cond else b`` ternaries (used
    by the firmware-version VPN-client routing in _routes/vpn.py), which is
    enough to resolve every payload literal glinet4 currently sends.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return _literal_strings(node.body) + _literal_strings(node.orelse)
    return []


def _extract_rpc_pairs(source: str, origin: str = "glinet.py") -> set[tuple[str, str]]:
    """Statically extract every (service, method) pair sent via self._payload("call", [...])."""
    tree = ast.parse(source)

    # Resolve simple `name = <literal or ternary-of-literals>` assignments so
    # a payload built from a variable (e.g. `target_call`) still resolves.
    name_values: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            values = _literal_strings(node.value)
            if values:
                name_values.setdefault(node.targets[0].id, []).extend(values)

    def resolve(node: ast.expr) -> list[str]:
        values = _literal_strings(node)
        if values:
            return values
        if isinstance(node, ast.Name):
            return name_values.get(node.id, [])
        return []

    pairs: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "_payload"):
            continue
        args = node.args
        if len(args) < 2 or not isinstance(args[1], ast.List) or len(args[1].elts) < 2:
            continue
        module_node, method_node = args[1].elts[0], args[1].elts[1]
        modules, methods = resolve(module_node), resolve(method_node)
        resolve_hint = (
            f"could not statically resolve a payload literal at {origin}:{node.lineno} "
            "-- extend _extract_rpc_pairs to handle it"
        )
        assert modules, resolve_hint
        assert methods, resolve_hint
        pairs.update((module, method) for module in modules for method in methods)
    return pairs


def _extract_sent_rpc_pairs() -> set[tuple[str, str]]:
    """Union the extracted pairs across glinet.py and every _routes module."""
    pairs: set[tuple[str, str]] = set()
    for source_path in GLINET_SOURCES:
        pairs |= _extract_rpc_pairs(source_path.read_text(encoding="utf-8"), source_path.name)
    return pairs


def _load_catalog_pairs() -> set[tuple[str, str]]:
    catalog: dict[str, list[str]] = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return {(service, method) for service, methods in catalog.items() for method in methods}


def test_every_sent_rpc_pair_is_known():
    sent_pairs = _extract_sent_rpc_pairs()
    catalog_pairs = _load_catalog_pairs()
    unknown = sorted(sent_pairs - catalog_pairs - KNOWN_UNCATALOGUED)
    assert not unknown, (
        f"RPC pair(s) not found in {CATALOG_PATH}: {unknown}. If these are real "
        "device RPCs missing from the catalog, refresh tests/data/rpc_catalog.json "
        "from a fresh capture; if they're legitimately absent from that capture "
        "(e.g. a write-risk or device-specific method), add them to "
        "KNOWN_UNCATALOGUED with a comment explaining why."
    )


def test_known_uncatalogued_allowlist_is_not_stale():
    """Every KNOWN_UNCATALOGUED entry must still be sent, and still be uncatalogued."""
    sent_pairs = _extract_sent_rpc_pairs()
    catalog_pairs = _load_catalog_pairs()
    stale_sent = sorted(pair for pair in KNOWN_UNCATALOGUED if pair not in sent_pairs)
    stale_catalog = sorted(pair for pair in KNOWN_UNCATALOGUED if pair in catalog_pairs)
    assert not stale_sent, f"KNOWN_UNCATALOGUED pair(s) no longer sent by glinet4: {stale_sent}"
    assert not stale_catalog, (
        f"KNOWN_UNCATALOGUED pair(s) now present in the catalog, remove them: {stale_catalog}"
    )
