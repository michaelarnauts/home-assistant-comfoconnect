"""Test setting up the integration."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion


async def test_entities_disabled_by_default(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, snapshot: SnapshotAssertion, init_integration: MockConfigEntry
) -> None:
    """Test which entities are disabled by default: every enabled sensor is a subscription on the bridge, so the less used ones stay off."""
    entries = er.async_entries_for_config_entry(entity_registry, init_integration.entry_id)

    assert sorted(entry.entity_id for entry in entries if entry.disabled_by) == snapshot
