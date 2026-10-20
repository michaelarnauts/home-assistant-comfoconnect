"""Test the select platform."""

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, snapshot_platform
from syrupy.assertion import SnapshotAssertion


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up only the select platform."""
    return [Platform.SELECT]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, snapshot: SnapshotAssertion, init_integration: MockConfigEntry
) -> None:
    """Test the select entities of the unit, with what the unit reports."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)
