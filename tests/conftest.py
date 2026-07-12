"""Shared fixtures for the unit suites.

The ``glinet`` fixture is the transport-mocked client used by
``test_glinet_unit.py`` and ``test_state_machines.py`` (extracted here so the
two suites don't carry duplicate copies — pylint R0801).
"""

# pylint: disable=protected-access

from unittest.mock import AsyncMock, MagicMock

import pytest

from glinet4.glinet import GLinet


@pytest.fixture
def glinet():
    """A GLinet client whose transport is fully mocked."""
    g = GLinet(base_url="http://192.168.8.1/rpc")
    g._transport = MagicMock()
    g._transport.request = AsyncMock()
    g._transport.request_long_timeout = AsyncMock()
    g._transport.sid = "SID"
    return g
