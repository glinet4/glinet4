"""Unit tests for gli4py enums."""
# pylint: disable=missing-function-docstring

from gli4py.enums import TailscaleConnection


def test_tailscale_connection_is_int_enum():
    assert TailscaleConnection.CONNECTED == 3
    assert int(TailscaleConnection.CONNECTING) == 4
    assert TailscaleConnection(0) is TailscaleConnection.DISCONNECTED
    # value-lookup used by the tailscale error paths
    assert TailscaleConnection(1).name == "LOGIN_REQUIRED"
