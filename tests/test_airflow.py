"""Commissioned airflow settings are available only when explicitly enabled."""

from datetime import timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed


async def test_airflow_disabled_by_default(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    freezer: FrozenDateTimeFactory,
    mock_comfoconnect: dict[str, MagicMock],
    init_integration: MockConfigEntry,
) -> None:
    """Register all four settings as disabled configuration entities without periodic polling."""
    for speed in ("away", "low", "medium", "high"):
        entity_id = f"number.comfoairq_{speed}_airflow_target"
        entry = entity_registry.async_get(entity_id)
        assert entry is not None
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert entry.entity_category.value == "config"
        assert hass.states.get(entity_id) is None
    mock_comfoconnect["get_property_constraints"].reset_mock()
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    mock_comfoconnect["get_property_constraints"].assert_not_awaited()
