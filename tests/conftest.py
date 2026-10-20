"""Pytest configuration."""

import sys
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest
from aiocomfoconnect import Bridge
from homeassistant.const import CONF_HOST
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import PlatformData
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Make custom_components importable, since it isn't installed as a package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from custom_components.comfoconnect.const import CONF_LOCAL_UUID, CONF_UUID, DOMAIN

HOST = "192.0.2.10"
BRIDGE_UUID = "00" * 16
LOCAL_UUID = "11" * 16


@pytest.fixture(autouse=True)
def entity_platform_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Let tests write the state of entities they create without a platform.

    An entity with a translation key needs platform data for its name. Entities that a platform adds get their own.
    """
    monkeypatch.setattr(Entity, "platform_data", PlatformData(None, domain="test", platform_name="comfoconnect"))


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the config entry of a registered bridge."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=HOST,
        unique_id=BRIDGE_UUID,
        data={CONF_HOST: HOST, CONF_UUID: BRIDGE_UUID, CONF_LOCAL_UUID: LOCAL_UUID},
    )


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Don't set up the config entry that a flow creates, nor unload it."""
    with (
        patch("custom_components.comfoconnect.async_setup_entry", return_value=True) as setup_entry,
        patch("custom_components.comfoconnect.async_unload_entry", return_value=True),
    ):
        yield setup_entry


@pytest.fixture
def mock_bridge() -> Generator[MagicMock]:
    """Return the bridge that the config flow finds on the network, or creates itself for a reauth."""
    bridge = create_autospec(Bridge, instance=True)
    bridge.host = HOST
    bridge.uuid = BRIDGE_UUID
    with patch("custom_components.comfoconnect.config_flow.Bridge", return_value=bridge):
        yield bridge


@pytest.fixture
def mock_discover_bridges(mock_bridge: MagicMock) -> Generator[AsyncMock]:
    """Let the config flow discover the bridge."""
    with patch("custom_components.comfoconnect.config_flow.aiocomfoconnect.discover_bridges", return_value=[mock_bridge]) as discover_bridges:
        yield discover_bridges
